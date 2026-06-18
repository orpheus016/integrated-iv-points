#include <SPI.h>

// Hardware Pin Definitions
const int relayPins[4] = {5, 4, 3, 2}; // Stage 3, Stage 2, Stage 1, Stage 0
const int RELAY_ON  = HIGH;
const int RELAY_OFF = LOW;

const unsigned int switchDelay_us = 5000; // Break-before-make delay

// Global State
int currentStage = 0;

// ADS1256 Register Values & Pins
double VREF = 2.50; 
int32_t registerData = 0;
const byte CS_pin = 7;
const byte DRDY_pin = 6;
const byte RESET_pin = 8; 

uint8_t registerAddress; 
uint8_t registerValueR; 
uint8_t registerValueW; 
String PrintMessage; 

const float STAGE_CURRENTS_MA[4] = {4.0, 8.0, 12.0, 20.0};

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  initialize_ADS1256();
  reset_ADS1256();
  userDefaultRegisters();
  printInstructions();

  for (int i = 0; i < 4; i++) {
    pinMode(relayPins[i], OUTPUT);
    digitalWrite(relayPins[i], RELAY_OFF);
  }

  // Enforce explicit base state (Stage 0)
  digitalWrite(relayPins[0], RELAY_ON); 
  currentStage = 0;
}

void loop() {
  if (Serial.available() > 0) {
    char commandCharacter = Serial.read();

    switch (commandCharacter) {
      case 'i': { // Explicit Stage Command from Python Host
        int targetStage = Serial.parseInt();
        if (targetStage >= 0 && targetStage <= 3) {
          transitionToStage(targetStage);
        }
        break;
      }
      
      case 'r': {
        Serial.println(F("*Which register to read?"));
        while (!Serial.available());
        registerAddress = Serial.parseInt();
        PrintMessage = "*Value of register " + String(registerAddress) + " is " + String(readRegister(registerAddress));
        Serial.println(PrintMessage);
        PrintMessage = "";   
        break;
      }

      case 'w': {
        Serial.println(F("*Which Register to write?"));
        while (!Serial.available());
        registerAddress = Serial.parseInt();
        Serial.println(F("*Which Value to write?"));
        while (!Serial.available());
        registerValueW = Serial.parseInt();
        writeRegister(registerAddress, registerValueW);
        delay(500);    
        PrintMessage = "*The value of the register now is: " + String(readRegister(registerAddress));
        Serial.println(PrintMessage);
        PrintMessage = "";
        break;
      }
		
      case 'R':
        reset_ADS1256();
        break;

      case 's':
        SPI.transfer(B00001111); // SDATAC
        break;

      case 'p':
        printInstructions();
        break;

      case 'C': {
        int posCh = 0;
        int negCh = 1;
        delay(10);
        if (Serial.available() > 0) {
          char nextChar = Serial.peek();
          if (isDigit(nextChar)) {
            posCh = Serial.parseInt();
            negCh = Serial.parseInt();
          }
        }
        streamContinuous_CSV(posCh, negCh);
        break;
      }
    }
  }
}

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
  Serial.println(F("*Reset DONE!"));
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

void streamContinuous_CSV(int posCh, int negCh) {
  posCh = constrain(posCh, 0, 8);
  negCh = constrain(negCh, 0, 8);
  uint8_t muxValue = (posCh << 4) | negCh;

  while (digitalRead(DRDY_pin)) {} 
  SPI.beginTransaction(SPISettings(1920000, MSBFIRST, SPI_MODE1));
  digitalWrite(CS_pin, LOW);
  SPI.transfer(0x50 | 1);   // WREG to MUX [cite: 92]
  SPI.transfer(0x00);       
  SPI.transfer(muxValue); 
  digitalWrite(CS_pin, HIGH); 
  SPI.endTransaction();

  // Issue SYNC/WAKEUP to reset filter initially
  SPI.beginTransaction(SPISettings(1920000, MSBFIRST, SPI_MODE1)); 
  digitalWrite(CS_pin, LOW); 
  SPI.transfer(B11111100); // SYNC [cite: 76, 94]
  delayMicroseconds(4); 
  SPI.transfer(B11111111); // WAKEUP [cite: 77, 95]
  digitalWrite(CS_pin, HIGH); 
  SPI.endTransaction();

  Serial.println(F("*STREAM_START")); 
  bool stopStream = false;
  
  while (!stopStream) {
    // Intercept serial commands mid-stream
    if (Serial.available() > 0) {
      char incomingChar = Serial.read();
      
      if (incomingChar == 's') { // Stop stream command
        stopStream = true; 
        break;
      }
      else if (incomingChar == 'i') { // Dynamic stage switch command
        int targetStage = Serial.parseInt();
        if (targetStage >= 0 && targetStage <= 3) {
          transitionToStage(targetStage);
          
          // Enforce 70ms Settling Delay (5ms relay + 60ms ADC Sinc3 filter flush)
          delay(70);
          
          // Explicitly clear any stale conversions by re-syncing the ADC
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

    // Standard Polling for DRDY
    while (digitalRead(DRDY_pin)) {}

    SPI.beginTransaction(SPISettings(1920000, MSBFIRST, SPI_MODE1)); 
    digitalWrite(CS_pin, LOW); 
     
    SPI.transfer(B00000001); // RDATA command [cite: 79, 99]
    delayMicroseconds(10);   // t6 delay [cite: 80, 100]
    
    registerData = 0; 
    registerData |= SPI.transfer(0xFF); registerData <<= 8;         
    registerData |= SPI.transfer(0xFF); registerData <<= 8;
    registerData |= SPI.transfer(0xFF); 
    
    digitalWrite(CS_pin, HIGH);
    SPI.endTransaction();

    // 24-bit Sign Extension Fix
    if ((registerData & 0x00800000) != 0) { 
      registerData |= 0xFF000000; 
    }
    
    double v = ((2.0 * VREF) / 8388607.0) * (int32_t)registerData;
    
    // Output transmission packet to host
    Serial.print(v, 8); 
    Serial.print(","); 
    // Current stage to current output
    if (currentStage == 0) {
      Serial.println(4);
    } 
    else if (currentStage == 1) {
      Serial.println(8);
    }
    else if (currentStage == 2) {
      Serial.println(12);
    }
    else {
      Serial.println(20);
    }
  }
  Serial.println(F("*STREAM_STOP")); 
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
  Serial.println(F("*Register defaults updated!"));
}

void printInstructions() {
  PrintMessage = String("*Commands:\n") +
                 "*r [reg] - Read Reg\n" +
                 "*w [reg] [val] - Write Reg\n" +
                 "*i [0-3] - Direct Stage Select\n" +
                 "*C - Continuous CSV stream\n";
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