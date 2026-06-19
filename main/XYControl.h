// =====================================================
// XYControl.h
// =====================================================

#ifndef XY_CONTROL_H
#define XY_CONTROL_H

#define EN_XY 25

#define STEP_X 15
#define DIR_X 17

#define STEP_Y 23
#define DIR_Y 19

#define X_MIN 3
#define X_MAX 5

#define Y_MIN 2
#define Y_MAX 4

#define VAC 39

const float stepsPerCm = 2000.0;
const int stepDelay = 600;

extern volatile bool singlePointMode;

// =====================================================
// SHARED VARIABLES
// =====================================================
long currentX = 0;
long currentY = 0;

unsigned long lastPrintMove = 0;
const int printIntervalMove = 200;

bool cekHome = false;

// =====================================================
// EXTERNAL FLAGS
// =====================================================
extern volatile bool emergencyStop;
extern volatile bool isHoming;

// =====================================================
// FUNCTION DECLARATIONS
// =====================================================
void setupXY();
void homeXY();

void runSequence1(float d);
void runSequence5(float d);
void runSequence9(float d);

void runPoints(float pts[][2], int count);

void moveTo(float xCm, float yCm);

void moveStep(int stepPin,
              int dirPin,
              int dir);

void zProbe(bool fullReturn);

bool checkEmergencyEnd();

// =====================================================
// SETUP
// =====================================================
void setupXY() {

  pinMode(EN_XY, OUTPUT);

  pinMode(STEP_X, OUTPUT);
  pinMode(DIR_X, OUTPUT);

  pinMode(STEP_Y, OUTPUT);
  pinMode(DIR_Y, OUTPUT);

  pinMode(VAC, OUTPUT);

  pinMode(X_MIN, INPUT_PULLUP);
  pinMode(X_MAX, INPUT_PULLUP);

  pinMode(Y_MIN, INPUT_PULLUP);
  pinMode(Y_MAX, INPUT_PULLUP);

  digitalWrite(EN_XY, LOW);

  digitalWrite(VAC, LOW);
}

// =====================================================
// HOME XY
// =====================================================
void homeXY() {

  while (digitalRead(X_MIN) == HIGH ||
         digitalRead(Y_MIN) == HIGH) {

    // stop only if NOT currently homing
    if (emergencyStop && !isHoming) return;

    if (digitalRead(X_MIN) == HIGH) {

      moveStep(STEP_X, DIR_X, LOW);
    }

    if (digitalRead(Y_MIN) == HIGH) {

      moveStep(STEP_Y, DIR_Y, LOW);
    }

    delayMicroseconds(stepDelay + 200);
  }

  currentX = 0;
  currentY = 0;

  cekHome = true;

  moveTo(7.5, 7.675);

  cekHome = false;

  currentX = 0;
  currentY = 0;

  Serial.println(currentX);
  Serial.println(currentY);
}

// =====================================================
// MODE 1
// =====================================================
void runSequence1(float d) {

  float pts[1][2] = {
    {0,0}
  };

  singlePointMode = true;
  runPoints(pts, 1);
  if (!emergencyStop){
  singlePointMode = false;
  }
  Serial.println("0");
  Serial.println("0");
}

// =====================================================
// MODE 5
// =====================================================
void runSequence5(float d) {

  float R = d;

  float pts[5][2] = {

    {0,0},

    {(2.0/3.0)*R,0},

    {0,-(2.0/3.0)*R},

    {-(2.0/3.0)*R,0},

    {0,(2.0/3.0)*R}
  };

  runPoints(pts, 5);
}

// =====================================================
// MODE 9
// =====================================================
void runSequence9(float d) {

  float R = d;

  float pts[9][2] = {

    {0,0},

    {(2.0/3.0)*R,0},

    {0.47*R,-0.47*R},

    {0,-(2.0/3.0)*R},

    {-0.47*R,-0.47*R},

    {-(2.0/3.0)*R,0},

    {-0.47*R,0.47*R},

    {0,(2.0/3.0)*R},

    {0.47*R,0.47*R}
  };

  runPoints(pts, 9);
}

// =====================================================
// RUN POINTS
// =====================================================
void runPoints(float pts[][2], int count) {

  digitalWrite(VAC, HIGH);

  for (int i = 0; i < count; i++) {

    if (emergencyStop && !isHoming) return;

    // =========================================
    // SHOW TARGET POINT
    // =========================================
    //Serial.print("TARGET X: ");
    //Serial.println(pts[i][0], 3);

    //Serial.print("TARGET Y: ");
    //Serial.println(pts[i][1], 3);

    // =========================================
    // MOVE
    // =========================================
    moveTo(pts[i][0], pts[i][1]);

    Serial.println(-(currentX / stepsPerCm) /2);

    Serial.println(-(currentY / stepsPerCm) /2);

    if (emergencyStop && !isHoming) return;

    zProbe(i == count - 1);
  }

  digitalWrite(VAC, LOW);

  if (count != 1) {

    homeXY();
  }
}

// =====================================================
// MOVE TO
// =====================================================
void moveTo(float xCm, float yCm) { //xCm & yCm = koordinat tujuan

  long tx = xCm * stepsPerCm;
  long ty = yCm * stepsPerCm;

  long dx = tx - currentX;
  long dy = ty - currentY;

  long steps = max(abs(dx), abs(dy));

  if (steps == 0) return;

  float xInc = dx / (float)steps;
  float yInc = dy / (float)steps;

  float xAcc = currentX;
  float yAcc = currentY;

  for (long i = 0; i < steps; i++) {

    // stop only outside homing
    if (checkEmergencyEnd() && !isHoming) return;

    xAcc += xInc;
    yAcc += yInc;

    long nX = round(xAcc);
    long nY = round(yAcc);

    // =============================================
    // X
    // =============================================
    if (nX != currentX) {

      if (nX > currentX &&
          digitalRead(X_MAX) == HIGH) {

        moveStep(STEP_X, DIR_X, HIGH);
        currentX++;
      }

      else if (nX < currentX &&
               digitalRead(X_MIN) == HIGH) {

        moveStep(STEP_X, DIR_X, LOW);
        currentX--;
      }
    }

    // =============================================
    // Y
    // =============================================
    if (nY != currentY) {

      if (nY > currentY &&
          digitalRead(Y_MAX) == HIGH) {

        moveStep(STEP_Y, DIR_Y, HIGH);
        currentY++;
      }

      else if (nY < currentY &&
               digitalRead(Y_MIN) == HIGH) {

        moveStep(STEP_Y, DIR_Y, LOW);
        currentY--;
      }
    }

    // =============================================
    // POSITION PRINT
    // =============================================
    if (millis() - lastPrintMove >= printIntervalMove) {

      lastPrintMove = millis();

      float xOut = -(currentX / stepsPerCm)/2;
      float yOut = -(currentY / stepsPerCm)/2;

      if (!cekHome) {

        Serial.println(xOut);
        Serial.println(yOut);
      }
    }

    delayMicroseconds(stepDelay);
  }
}

// =====================================================
// SINGLE STEP
// =====================================================
void moveStep(int stepPin,
              int dirPin,
              int dir) {

  digitalWrite(dirPin, dir);

  digitalWrite(stepPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(stepPin, LOW);
}

#endif