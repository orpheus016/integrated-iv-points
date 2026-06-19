#ifndef INSTRUMENT_H
#define INSTRUMENT_H

#include <SPI.h>

// Hardware Pin Definitions
const int relayPins[4] = {30, 32, 34, 36}; // Stage 3, Stage 2, Stage 1, Stage 0
const int validPins[4] = {22, 24, 26, 28}; // Validation Relays
const int RELAY_ON  = HIGH;
const int RELAY_OFF = LOW;

const unsigned int switchDelay_us = 5000; // Break-before-make delay

// Global State
int currentStage = 0;

// ADS1256 Register Values & Pins
double VREF = 2.50;
int32_t registerData = 0;

const byte CS_pin = 53;
const byte DRDY_pin = 38;
const byte RESET_pin = 40;

uint8_t registerAddress;
uint8_t registerValueR;
uint8_t registerValueW;
String PrintMessage;

const float STAGE_CURRENTS_MA[4] = {4.0, 8.0, 12.0, 20.0};

void transitionToStage(int targetStage);
unsigned long readRegister(uint8_t registerAddress);
void writeRegister(uint8_t registerAddress, uint8_t registerValueW);
void reset_ADS1256();
void initialize_ADS1256();
void userDefaultRegisters();
void printInstructions();
void sendDirectCommand(uint8_t directCommand);
void streamContinuous_CSV(int posCh, int negCh);
void setupInstrument();

unsigned long readRegister(uint8_t registerAddress) {
  while (digitalRead(DRDY_pin)) {}
  SPI.beginTransaction(SPISettings(1920000, MSBFIRST, SPI_MODE1));
  digitalWrite(CS_pin, LOW);
  SPI.transfer(0x10 | registerAddress);
  SPI.transfer(0x00);
  delayMicroseconds(5);
  registerValueR = SPI.transfer(0xFF);
  digitalWrite(CS_pin, HIGH);
  SPI.endTransaction();
  return registerValueR;
}

void writeRegister(uint8_t registerAddress, uint8_t registerValueW) {
  while (digitalRead(DRDY_pin)) {}
  SPI.beginTransaction(SPISettings(1920000, MSBFIRST, SPI_MODE1));
  digitalWrite(CS_pin, LOW);
  delayMicroseconds(5);
  SPI.transfer(0x50 | registerAddress);
  SPI.transfer(0x00);
  SPI.transfer(registerValueW);
  digitalWrite(CS_pin, HIGH);
  SPI.endTransaction();
}

void reset_ADS1256() {
  SPI.beginTransaction(SPISettings(1920000, MSBFIRST, SPI_MODE1));
  digitalWrite(CS_pin, LOW);
  delayMicroseconds(10);
  SPI.transfer(0xFE); // Reset Command
  delay(2);
  SPI.transfer(0x0F); // SDATAC
  delayMicroseconds(100);
  digitalWrite(CS_pin, HIGH);
  SPI.endTransaction();
  //Serial.println(F("*Reset DONE!"));
}

void initialize_ADS1256() {
  pinMode(CS_pin, OUTPUT);
  digitalWrite(CS_pin, LOW);
  SPI.begin();
  pinMode(DRDY_pin, INPUT);
  pinMode(RESET_pin, OUTPUT);
  digitalWrite(RESET_pin, LOW);
  delay(500);
  digitalWrite(RESET_pin, HIGH);
  delay(500);
}

void userDefaultRegisters() {
  delay(500);
  writeRegister(0x00, B00110110); // STATUS (ACAL & BUFEN enabled)
  delay(200);
  writeRegister(0x01, B00000001); // MUX AIN0+AIN1
  delay(200);
  writeRegister(0x02, B00000000); // ADCON PGA = 1
  delay(200);
  writeRegister(0x03, B01100011); // DRATE = 50 SPS
  delay(500);
  sendDirectCommand(B11110000);   // SELFCAL
  //Serial.println(F("*Register defaults updated!"));
}

void printInstructions() {
  PrintMessage = String("*Commands:\n") +
                 "*r [reg] - Read Reg\n" +
                 "*w [reg] [val] - Write Reg\n" +
                 "*i [0-3] - Direct Stage Select\n" +
                 "*C - Continuous CSV stream\n" +
                 "*FINISH - Stop Continuous Stream\n";
  Serial.println(PrintMessage);
  PrintMessage = "";
}

void transitionToStage(int targetStage) {
  if (targetStage == currentStage) return;

  // Adjacent Transition Logic (Break-before-make emulation protection)
  if (abs(targetStage - currentStage) == 1) {
    digitalWrite(relayPins[targetStage], RELAY_ON);
    delayMicroseconds(switchDelay_us);
    digitalWrite(relayPins[currentStage], RELAY_OFF);
  } else {
    digitalWrite(relayPins[currentStage], RELAY_OFF);
    delayMicroseconds(switchDelay_us);
    digitalWrite(relayPins[targetStage], RELAY_ON);
  }
  currentStage = targetStage;
}

void sendDirectCommand(uint8_t directCommand) {
  SPI.beginTransaction(SPISettings(1700000, MSBFIRST, SPI_MODE1));
  digitalWrite(CS_pin, LOW);
  delayMicroseconds(5);
  SPI.transfer(directCommand);
  delayMicroseconds(5);
  digitalWrite(CS_pin, HIGH);
  SPI.endTransaction();
}

void streamContinuous_CSV(int posCh, int negCh) {
  posCh = constrain(posCh, 0, 8);
  negCh = constrain(negCh, 0, 8);
  uint8_t muxValue = (posCh << 4) | negCh;

  while (digitalRead(DRDY_pin)) {}
  SPI.beginTransaction(SPISettings(1920000, MSBFIRST, SPI_MODE1));
  digitalWrite(CS_pin, LOW);
  SPI.transfer(0x50 | 1);
  SPI.transfer(0x00);
  SPI.transfer(muxValue);
  digitalWrite(CS_pin, HIGH);
  SPI.endTransaction();

  // Initial filter reset
  SPI.beginTransaction(SPISettings(1920000, MSBFIRST, SPI_MODE1));
  digitalWrite(CS_pin, LOW);
  SPI.transfer(B11111100); // SYNC
  delayMicroseconds(4);
  SPI.transfer(B11111111); // WAKEUP
  digitalWrite(CS_pin, HIGH);
  SPI.endTransaction();

  Serial.println(F("STARTSTREAM")); 

  const unsigned long streamDuration = 5000; 
  unsigned long startTime = millis();

  while ((millis() - startTime) < streamDuration) {

    // Optional: still allow stage changes during streaming
    if (Serial.available() > 0) {
      String command = Serial.readStringUntil('\n');
      command.trim();

      if (command.startsWith("i")) {
        int spaceIndex = command.indexOf(' ');
        if (spaceIndex > 0) {
          int targetStage = command.substring(spaceIndex + 1).toInt();

          if (targetStage >= 0 && targetStage <= 3) {
            transitionToStage(targetStage);

            delay(70);

            SPI.beginTransaction(SPISettings(1920000, MSBFIRST, SPI_MODE1));
            digitalWrite(CS_pin, LOW);
            SPI.transfer(B11111100); // SYNC
            delayMicroseconds(4);
            SPI.transfer(B11111111); // WAKEUP
            digitalWrite(CS_pin, HIGH);
            SPI.endTransaction();
          }
        }
      }
    }

    while (digitalRead(DRDY_pin)) {}

    SPI.beginTransaction(SPISettings(1920000, MSBFIRST, SPI_MODE1));
    digitalWrite(CS_pin, LOW);

    SPI.transfer(B00000001); // RDATA
    delayMicroseconds(10);

    registerData = 0;
    registerData |= SPI.transfer(0xFF);
    registerData <<= 8;
    registerData |= SPI.transfer(0xFF);
    registerData <<= 8;
    registerData |= SPI.transfer(0xFF);

    digitalWrite(CS_pin, HIGH);
    SPI.endTransaction();

    if ((registerData & 0x00800000) != 0) {
      registerData |= 0xFF000000;
    }

    double v = ((2.0 * VREF) / 8388607.0) * (int32_t)registerData;
    
    // Output transmission packet to host
    Serial.print("V");
    Serial.println(v,8); 
    Serial.print("I"); 
    // Current stage to current output
    if (currentStage == 0) {
      Serial.println(0.004,3);
    } 
    else if (currentStage == 1) {
      Serial.println(0.008,3);
    }
    else if (currentStage == 2) {
      Serial.println(0.012,3);
    }
    else {
      Serial.println(0.020,3);
    }
  }

  Serial.println("STOPSTREAM");
}

void setupInstrument(){

  initialize_ADS1256();
  reset_ADS1256();
  userDefaultRegisters();
  //printInstructions();

  for (int i = 0; i < 4; i++) {
    pinMode(relayPins[i], OUTPUT);
    digitalWrite(relayPins[i], RELAY_OFF);
  }

  // Enforce explicit base state (Stage 0)
  digitalWrite(relayPins[0], RELAY_ON); 
  currentStage = 0;

  //Validation Switch RELAY_ON for switch to validation with resistors
  for (int j = 0; j < 4; j++) {
    pinMode(validPins[j], OUTPUT);
    digitalWrite(validPins[j], RELAY_OFF);
  }
}

#endif