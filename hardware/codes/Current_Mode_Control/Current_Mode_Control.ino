/*
  Arduino Mega -> 4CH Relay Current Mode Switching
  ACTIVE HIGH relay logic:
    HIGH = Relay ON
    LOW  = Relay OFF

  Relay topology:
    Pin5 = Base/default path
    Pin4 = Stage 1
    Pin3 = Stage 2
    Pin2 = Stage 3

  Thresholds [PLACEHOLDER]:
    R <= 12.7553          -> Stage 0 (Pin25)
    12.7553 < R <= 35.6846 -> Stage 1 (Pin24)
    35.6846 < R <= 79.9224 -> Stage 2 (Pin23)
    R > 79.9224           -> Stage 3 (Pin22)

  RULES:
  1. Adjacent ascending:
      New relay ON first, delay, old relay OFF
  2. Adjacent descending:
      Lower relay ON first, delay, higher relay OFF
  3. Jumping multiple stages:
      Current relay OFF first,
      then target relay ON
      (per your request)

  Example:
    Stage3 -> Stage1:
      Pin22 OFF
      delay
      Pin24 ON
*/

const int relayPins[4] = {
  5, // Stage 0, di mega 25,24,23,22
  4, // Stage 1
  3, // Stage 2
  2  // Stage 3
};

const int RELAY_ON  = HIGH;
const int RELAY_OFF = LOW;

const float THRESHOLD_1 = 12.7553;
const float THRESHOLD_2 = 35.6846;
const float THRESHOLD_3 = 79.9224;

// Delay for relay settling
const unsigned int switchDelay_us = 5000;

int currentStage = 0;
float resistanceValue = 0.0;

void setup() {
  Serial.begin(115200);

  for (int i = 0; i < 4; i++) {
    pinMode(relayPins[i], OUTPUT);
    digitalWrite(relayPins[i], RELAY_OFF);
  }

  // Default base state
  digitalWrite(relayPins[0], RELAY_ON);

  Serial.println("Enter resistance value:");
}

void loop() {
  if (Serial.available() > 0) {

    resistanceValue = Serial.parseFloat();

    while (Serial.available()) {
      Serial.read();
    }

    Serial.print("Resistance: ");
    Serial.println(resistanceValue, 4);

    int targetStage = determineStage(resistanceValue);

    if (targetStage != currentStage) {
      transitionToStage(targetStage);
    }

    Serial.print("Current Stage: ");
    Serial.println(currentStage);

    Serial.println("Enter next resistance:");
  }
}

// Determine stage from resistance
int determineStage(float R) {
  if (R <= THRESHOLD_1) {
    return 0;
  }
  else if (R <= THRESHOLD_2) {
    return 1;
  }
  else if (R <= THRESHOLD_3) {
    return 2;
  }
  else {
    return 3;
  }
}

// Relay transition manager
void transitionToStage(int targetStage) {

  // Adjacent move (ascending or descending)
  if (abs(targetStage - currentStage) == 1) {

    // Turn ON target first
    digitalWrite(relayPins[targetStage], RELAY_ON);
    delayMicroseconds(switchDelay_us);

    // Turn OFF previous
    digitalWrite(relayPins[currentStage], RELAY_OFF);
  }

  // Jump move (>1 stage difference)
  else {

    // Turn OFF current first
    digitalWrite(relayPins[currentStage], RELAY_OFF);
    delayMicroseconds(switchDelay_us);

    // Turn ON target
    digitalWrite(relayPins[targetStage], RELAY_ON);
  }

  currentStage = targetStage;

  Serial.print("Switched to Stage ");
  Serial.println(targetStage);
}