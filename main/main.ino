// =====================================================
// MAIN FILE (.ino)
// =====================================================

#include "XYControl.h"
#include "ZControl.h"
#include "temperature.h"
#include "instrument.h"

#define FAN 42
#define VRX_PIN A1
#define VRY_PIN A0
#define SW_PIN 43

volatile bool singlePointMode = false;

unsigned long lastTempUpdate = 0;
const unsigned long tempInterval = 2000;

// =====================================================
// JOYSTICK DIAMETER LIMIT
// =====================================================
float joystickDiameter = 0.0;
float joystickRadius = 0.0;

// =====================================================
// GLOBAL FLAGS
// =====================================================
volatile bool emergencyStop = false;
volatile bool isHoming = false;

// =====================================================
// FUNCTION PROTOTYPES
// =====================================================
bool checkEmergencyEnd();
void handleEmergencyReset();
void runJoystickMode();
void setupInstrument();

bool insideCircle(long targetXSteps, long targetYSteps);

// =====================================================
// CHECK FOR END COMMAND
// =====================================================
bool checkEmergencyEnd() {

  if (Serial.available() > 0) {

    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if (cmd.equalsIgnoreCase("END")) {

      emergencyStop = true;

      return true;
    }
  }

  return emergencyStop;
}

// =====================================================
// HANDLE EMERGENCY RESET
// =====================================================
void handleEmergencyReset() {

  isHoming = true;

  digitalWrite(VAC, LOW);

  // =============================================
  // SINGLE POINT
  // only home Z
  // =============================================
  if (singlePointMode) {

    homeZ();
  }

  // =============================================
  // MULTI POINT / MANUAL
  // normal full home
  // =============================================
  else {

    homeZ();
    homeXY();
  }

  emergencyStop = false;
  isHoming = false;

  singlePointMode = false;
}

// =====================================================
// CHECK IF POSITION IS INSIDE CIRCLE
// =====================================================
bool insideCircle(long targetXSteps, long targetYSteps) {

  // convert steps -> cm
  float xCm = (targetXSteps / stepsPerCm) / 2.0;
  float yCm = (targetYSteps / stepsPerCm) / 2.0;

  float distanceSquared = (xCm * xCm) + (yCm * yCm);
  float radiusSquared = joystickRadius * joystickRadius;

  return distanceSquared <= radiusSquared;
}

// =====================================================
// SETUP
// =====================================================
void setup() {

  Serial.begin(115200);

  Serial.setTimeout(50);

  initTemperatureSensors();
  //printMLX();
  pinMode(FAN, OUTPUT);

  digitalWrite(FAN, LOW);
  delay(1000);
  digitalWrite(FAN, HIGH);

  pinMode(SW_PIN, INPUT_PULLUP);
  setupInstrument();


  setupXY();
  setupZ();

  homeZ();
  homeXY();

  //printMLX();
}

// =====================================================
// MAIN LOOP
// =====================================================
void loop() {

  // =============================================
  // HANDLE EMERGENCY
  // =============================================
  if (emergencyStop) {

    handleEmergencyReset();
    return;
  }

  // =============================================
  // TEMPERATURE UPDATE
  // =============================================
  /*
  if (millis() - lastTempUpdate >= tempInterval) {

    printSHT();

    lastTempUpdate = millis();
  }
  */

  // =============================================
  // SERIAL COMMANDS
  // =============================================
  if (Serial.available() > 0) {

    String input = Serial.readStringUntil('\n');
    input.trim();

    // =========================================
    // MANUAL MODE
    // =========================================
    if (input.startsWith("m")) {

      int spaceIndex = input.indexOf(' ');

      // default = unlimited movement
      joystickDiameter = 0;
      joystickRadius = 0;

      // example:
      // m 10.16
      if (spaceIndex > 0) {

        joystickDiameter = input.substring(spaceIndex + 1).toFloat();

        if (joystickDiameter > 0) {

          joystickRadius = joystickDiameter / 2.0;
        }
      }

      runJoystickMode();
    }

    // =========================================
    // AUTO MODES
    // =========================================
    else {

      int spaceIndex = input.indexOf(' ');

      if (spaceIndex > 0) {

        int mode = input.substring(0, spaceIndex).toInt();
        float diameter = input.substring(spaceIndex + 1).toFloat();

        if (diameter <= 0) return;

        // =====================================
        // MODE 1
        // =====================================
        if (mode == 1) {

          runSequence1(diameter);
        }

        // =====================================
        // MODE 5
        // =====================================
        else if (mode == 5) {

          runSequence5(diameter);
        }

        // =====================================
        // MODE 9
        // =====================================
        else if (mode == 9) {

          runSequence9(diameter);
        }
      }
    }
  }
}

// =====================================================
// JOYSTICK MODE
// =====================================================
void runJoystickMode() {

  bool active = true;

  digitalWrite(VAC, HIGH);

  while (active) {

    // =========================================
    // EMERGENCY CHECK
    // =========================================
    if (checkEmergencyEnd()) {

      active = false;
      break;
    }

    // =========================================
    // READ JOYSTICK
    // =========================================
    int xVal = analogRead(VRX_PIN);
    int yVal = analogRead(VRY_PIN);

    // =========================================
    // X AXIS
    // =========================================
    if (xVal < 300 && digitalRead(X_MIN) == HIGH) {

      long nextX = currentX - 1;

      if (joystickRadius <= 0 || insideCircle(nextX, currentY)) {

        moveStep(STEP_X, DIR_X, LOW);
        currentX--;
      }
    }

    else if (xVal > 700 && digitalRead(X_MAX) == HIGH) {

      long nextX = currentX + 1;

      if (joystickRadius <= 0 || insideCircle(nextX, currentY)) {

        moveStep(STEP_X, DIR_X, HIGH);
        currentX++;
      }
    }

    // =========================================
    // Y AXIS
    // =========================================
    if (yVal < 300 && digitalRead(Y_MIN) == HIGH) {

      long nextY = currentY - 1;

      if (joystickRadius <= 0 || insideCircle(currentX, nextY)) {

        moveStep(STEP_Y, DIR_Y, LOW);
        currentY--;
      }
    }

    else if (yVal > 700 && digitalRead(Y_MAX) == HIGH) {

      long nextY = currentY + 1;

      if (joystickRadius <= 0 || insideCircle(currentX, nextY)) {

        moveStep(STEP_Y, DIR_Y, HIGH);
        currentY++;
      }
    }

    // =========================================
    // PROBE BUTTON
    // =========================================
    if (digitalRead(SW_PIN) == LOW) {

      delay(200);

      Serial.println("Confirm");

      bool waitingForConfirm = true;

      while (waitingForConfirm) {

        // =====================================
        // ONLY CHECK FLAG
        // =====================================
        if (emergencyStop) {

          active = false;
          waitingForConfirm = false;
          break;
        }

        // =====================================
        // SERIAL RESPONSE
        // =====================================
        if (Serial.available() > 0) {

          String response = Serial.readStringUntil('\n');
          response.trim();

          // =================================
          // END
          // =================================
          if (response.equalsIgnoreCase("END")) {

            emergencyStop = true;

            active = false;
            waitingForConfirm = false;

            break;
          }

          // =================================
          // YES
          // =================================
          else if (response.equalsIgnoreCase("Y")) {

            zProbe(false);

            waitingForConfirm = false;
          }

          // =================================
          // NO
          // =================================
          else if (response.equalsIgnoreCase("N")) {

            waitingForConfirm = false;
          }
        }
      }

      // =========================================
      // WAIT RELEASE
      // =========================================
      while (digitalRead(SW_PIN) == LOW) {

        if (emergencyStop) {

          active = false;
          break;
        }
      }
    }

    // =========================================
    // POSITION PRINT
    // =========================================
    if (millis() - lastPrintMove >= printIntervalMove) {

      lastPrintMove = millis();

      Serial.print("X: ");
      Serial.println(-(currentX / stepsPerCm) / 2);

      Serial.print("Y: ");
      Serial.println(-(currentY / stepsPerCm) / 2);
    }

    delayMicroseconds(stepDelay);
  }

  digitalWrite(VAC, LOW);
}