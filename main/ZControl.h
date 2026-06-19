#ifndef Z_CONTROL_H
#define Z_CONTROL_H

#define EN_Z 31
#define STEP_Z 29
#define DIR_Z 27

#define Z_MIN 35
#define Z_MAX 37

// =====================================================
// EXTERNAL FLAGS
// =====================================================
extern volatile bool emergencyStop;
extern volatile bool isHoming;

// =====================================================
// FUNCTION DECLARATIONS
// =====================================================
bool checkEmergencyEnd();

void printMLX();
void streamContinuous_CSV(int posCh = 0, int negCh = 1);
void setupInstrument();

unsigned long temp0 = 0;
const unsigned long temp1 = 2000;

// =====================================================
// SETUP Z
// =====================================================
void setupZ() {

  pinMode(EN_Z, OUTPUT);

  pinMode(STEP_Z, OUTPUT);
  pinMode(DIR_Z, OUTPUT);

  pinMode(Z_MIN, INPUT_PULLUP);
  pinMode(Z_MAX, INPUT_PULLUP);

  digitalWrite(EN_Z, LOW);
}

// =====================================================
// SINGLE STEP
// =====================================================
void stepZ(int dly) {

  digitalWrite(STEP_Z, HIGH);
  delayMicroseconds(dly);

  digitalWrite(STEP_Z, LOW);
  delayMicroseconds(dly);
}

// =====================================================
// MOVE Z
// =====================================================
void moveZ(int steps, int dly) {

  for (int i = 0; i < steps; i++) {

    // =============================================
    // STOP ONLY IF NOT HOMING
    // =============================================
    if (checkEmergencyEnd() && !isHoming) return;

    // =============================================
    // LIMIT CHECKS
    // =============================================
    if (digitalRead(DIR_Z) == HIGH &&
        digitalRead(Z_MIN) == LOW) return;

    if (digitalRead(DIR_Z) == LOW &&
        digitalRead(Z_MAX) == LOW) return;

    stepZ(dly);
  }
}

// =====================================================
// HOME Z
// =====================================================
void homeZ() {

  digitalWrite(EN_Z, LOW);

  // =============================================
  // MOVE UP TO Z_MAX
  // =============================================
  digitalWrite(DIR_Z, LOW);

  while (digitalRead(Z_MAX) == HIGH) {

    // allow homing during emergency reset
    if (checkEmergencyEnd() && !isHoming) return;

    stepZ(600);
  }

  // =============================================
  // BACK OFF
  // =============================================
  digitalWrite(DIR_Z, HIGH);

  moveZ(400, 600);

  digitalWrite(EN_Z, HIGH);

}

// =====================================================
// Z PROBE
// =====================================================
void zProbe(bool fullReturn) {

  digitalWrite(EN_Z, LOW);

  // =============================================
  // GO DOWN
  // =============================================
  digitalWrite(DIR_Z, HIGH);

  if (checkEmergencyEnd() && !isHoming) return;

  // =============================================
  // FAST APPROACH
  // =============================================
  for (int i = 0; i < 4; i++) {

    if (digitalRead(Z_MIN) == LOW) break;

    if (checkEmergencyEnd() && !isHoming) return;

    moveZ(2000, 600);
  }

  // =============================================
  // SLOW APPROACH
  // =============================================
  while (digitalRead(Z_MIN) == HIGH) {

    if (checkEmergencyEnd() && !isHoming) return;

    moveZ(4, 1000);
  }

  // =============================================
  // TEMPERATURE
  // =============================================
  printMLX();
  Serial.println("STARTSTREAM");
  streamContinuous_CSV();

  //delay(2000);

  // =============================================
  // RETURN
  // =============================================
  if (fullReturn) {

    digitalWrite(VAC, LOW);

    // move upward to home
    digitalWrite(DIR_Z, LOW);

    while (digitalRead(Z_MAX) == HIGH) {

      if (checkEmergencyEnd() && !isHoming) return;

      stepZ(600);
    }

    // back off
    digitalWrite(DIR_Z, HIGH);

    moveZ(400, 600);
  }

  else {

    // partial lift
    digitalWrite(DIR_Z, LOW);

    moveZ(3000, 600);
  }

  digitalWrite(EN_Z, HIGH);
}

#endif