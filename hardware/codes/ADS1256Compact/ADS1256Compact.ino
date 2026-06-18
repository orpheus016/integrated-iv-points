/*Information

 * PRESSSSS "E" TO RUN THE CODE PROPERLY

 * The code is written by Curious Scientist
 * https://curiousscientist.tech
 * 
 * Playlist for more ADS1256-related videos
 * https://www.youtube.com/playlist?list=PLaeIi4Gbl1T-RpVNM8uKdiV1G_3t5jCIu
 * 
 * If you use the code, please subscribe to my channel
 * https://www.youtube.com/c/CuriousScientist?sub_confirmation=1
 * 
 * I also accept donations
 * https://www.paypal.com/donate/?hosted_button_id=53CNKJLRHAYGQ
 * 
 * The code belongs to the following video
 * https://youtu.be/rsi9o5PQzwM
 * 
 */
//--------------------------------------------------------------------------------
/*
The green board has a RESET pin and the blue does not.
Therefore, for the blue board, the reset function is disabled.

BUFEN should be enabled for precise measurement, but in that case, the max input voltage
cannot be higher than AVDD-2 V. 
*/
//--------------------------------------------------------------------------------
// Pin configuration - STM32F103 [Arduino]: Pins in square brackets [xx] are for Arduino Uno or Nano.
/*
SPI default pins:
MOSI  - PA7[11] // DIN
MISO  - PA6[12] // DOUT
SCK	  - PA5[13] // SCLK
SS	  -	PA4[10] // CS9
--------------------
--------------------
MOSI: Master OUT Slave IN -> DIN
MISO: Master IN Slave OUT -> DOUT
--------------------
--------------------
Other pins - You can assign them to any pins
RST	  -	PA3 
DRDY  - PA2 // this is an interrupt pin
PDWN  - +3.3 V
PDWN - PA1 (Alternatively, if you want to switch it)
*/
//--------------------------------------------------------------------------------
//Clock rate
/*
	f_CLKIN = 7.68 MHz
	tau = 130.2 ns
*/
//--------------------------------------------------------------------------------
//REGISTERS
/*
REG   VAL     USE
0     54      Status Register, Everything Is Default, Except ACAL and BUFEN
1     1       Multiplexer Register, AIN0 POS, AIN1 NEG [w1 0x01 since 0000 AIN0 = 0, 0001 AIN1 = 1 -> w1 1 DIFF USE THIS!; w1 8 since AINCOM = 10000 = 8, 08 = 8; 0x28 = 40 for single AIN2]
2     0       ADCON, Everything is OFF, PGA = 1 [w2 0, PGA = 1; w2 1, PGA = 2; w2 2, PGA = 4; w2 3, PGA = 8; w2 4, PGA = 16]
3     99      DataRate = 50 SPS
4     225     GPIO, Everything Is Default
*/
//--------------------------------------------------------------------------------
#include <SPI.h> //SPI communication
//--------------------------------------------------------------------------------
// The setup() function runs once each time the micro-controller starts
void setup()
{
	Serial.begin(115200);  //We will need high datarate, so it should be a high baud rate
  delay(1000);
  
	Serial.println("*ADS1256 Initialization...."); //Some message
	initialize_ADS1256(); //run the initialization function 
 
  delay(1000);
	Serial.println("*Initialization finished!"); //Confirmation message
 
	reset_ADS1256(); //Reset the ADS1256
	userDefaultRegisters(); //Set up the default registers
	printInstructions(); //Print the instructions for the commands used in the code
 
}

//--------------------------------------------------------------------------------
//Variables
double VREF = 2.50; //Value of V_ref. In case of internal V_ref, it is 2.5 V
double voltage = 0; //Converted RAW bits. 
double resistance = 0;
const byte RELAY_PIN = 9; // Pin untuk kontrol arus
int CS_Value; //we use this to store the value of the bool, since we don't want to directly modify the CS_pin

//Pins
const byte CS_pin = 7;	//goes to CS on ADS1256, is it safe to use the default ss pin instead
const byte DRDY_pin = 6;  //goes to DRDY on ADS1256
const byte RESET_pin = 8; //goes to RST on ADS1256 
//const byte PDWN_PIN = PA1; //Goes to the PDWN/SYNC/RESET pin (notice, that some boards have different pins!)
//The above pins are described for STM32. For Arduino, you have to use a different pin definition ("PA" is not used in "PA4)

//Values for registers
uint8_t registerAddress; //address of the register, both for reading and writing - selects the register
uint8_t registerValueR; //this is used to READ a register
uint8_t registerValueW; //this is used to WRTIE a register
int32_t registerData; //this is used to store the data read from the register (for the AD-conversion)
uint8_t directCommand; //this is used to store the direct command for sending a command to the ADS1256
String ConversionResults; //Stores the result of the AD conversion
String PrintMessage; //this is used to concatenate stuff into before printing it out. 

//--------------------------------------------------------------------------------

void loop()
{
	if (Serial.available() > 0) 
	{
		char commandCharacter = Serial.read(); //we use characters (letters) for controlling the switch-case	

		switch (commandCharacter) //based on the command character, we decide what to do
		{
		case 'r': //this case is used to READ the value of a register
      //Relevant info on registers: https://youtu.be/wUEx6pEHi2c
			//Ask the user to pick a register //Register map: Table 23 in the Datasheet
			Serial.println("*Which register to read?"); //I put the "*" in front of every text message, so my processing software ignores them
      registerAddress = Serial.parseInt(); //we parse the entered number as an integer and pass it to the registerAddress variable
			//Wait for the input; Example command: "r 1". This will read the register 1 which is the MUX register (they start at 0!)
			while (!Serial.available());
			//Text before the print - string concatenation
      PrintMessage = "*Value of register " + String(registerAddress) + " is " + String(readRegister(registerAddress));
			Serial.println(PrintMessage); //printing the confirmation message
      PrintMessage = ""; //reset the value of the variable     
			break;

		case 'w': //this case is used to WRITE the value of a register
			//Ask the user to pick a register
			Serial.println("*Which Register to write?");
			//Wait for the input
			while (!Serial.available());
			registerAddress = Serial.parseInt(); //Store the register in serialData
			//Ask for the value we want to write
			Serial.println("*Which Value to write?");
			//wait for the input; 
      //Example command: "w1 1". This will write the value 1 in the MUX register. This will set the AIN0(+) + AIN1(-) as the input. w1 8 for AIN0 AINCOM
			while (!Serial.available());
			registerValueW = Serial.parseInt();

			//Write the serialData register with the recent input value (Serial.parseInt())
			writeRegister(registerAddress, registerValueW); //The writeRegister() function expects 2 arguments
      delay(500); //wait      
      PrintMessage = "*The value of the register now is: " + String(readRegister(registerAddress));    			
			Serial.println(PrintMessage); //printing a confirmation message
			PrintMessage = "";
			break;
		
		case 'R': //this does a RESET on the ADS1256

			reset_ADS1256(); //the reset_ADS1256() function resets all the register values

			break;

		case 's': //SDATAC - Stop Read Data Continously

			SPI.transfer(B00001111); //Sending a direct code for SDATAC // Figure 33 in datasheet
			break;

    case 'p': //Printing the instructions

      printInstructions(); //this function prints the commands used to control the ADS1256
      break;

    case 'E': // Command baru untuk AIN0-AIN1 setiap 0.5s
      
      readContinuous_AIN0_AIN1();
      break;

    case 'C': // Continuous CSV stream with dynamic channels
      {
        int posCh = 0; // Default to AIN0
        int negCh = 1; // Default to AIN1

        delay(10); // Wait a tiny bit for the serial buffer to catch up

        // Check if there are numbers immediately following the 'C'
        if (Serial.available() > 0) {
          char nextChar = Serial.peek();
          // If the next character is a digit, parse the two numbers
          if (isDigit(nextChar)) {
            posCh = Serial.parseInt();
            negCh = Serial.parseInt();
          }
        }
        
        // Pass the channels to our stream function
        streamContinuous_CSV(posCh, negCh);
      }
      break;
		}
	}
}

//--------------------------------------------------------------------------------
//Functions

//Reading registers
//DIN should receive 2 command bytes
//1st command byte: address of the register (for example MUX: 1 / 01h / 0000 0001)
//2nd command byte: number of bytes to read (0000 0001 - 1 byte)
//delay between the end of the command and the beginning of the shifting out of the data on DOUT is t6 = 50 * tau_CLKIN
// 50 * 130.2 ns = 6510 ns = 6.51 us
//Seems like, according to the SPI analyzer, 5 us delay is sufficient. 
//When writing the register, the time between the last clock for RREG command an the first clock of the answer is t = 6.5 us.

unsigned long readRegister(uint8_t registerAddress) //Function for READING a selected register
{
  //Relevant video: https://youtu.be/KQ0nWjM-MtI
  while (digitalRead(DRDY_pin)) {} //we "stuck" here until the DRDY changes its state
	
	SPI.beginTransaction(SPISettings(1920000, MSBFIRST, SPI_MODE1));
	//SPI_MODE1 = output edge: rising, data capture: falling; clock polarity: 0, clock phase: 1.

	//CS must stay LOW during the entire sequence [Ref: P34, T24]
 
	digitalWrite(CS_pin, LOW); //CS_pin goes LOW
	
	SPI.transfer(0x10 | registerAddress); //0x10 = RREG

	SPI.transfer(0x00);

	delayMicroseconds(5); //see t6 in the datasheet

	registerValueR = SPI.transfer(0xFF);	//0xFF is sent to the ADS1256 which returns us the register value

	digitalWrite(CS_pin, HIGH); //CS_pin goes HIGH
	SPI.endTransaction();

	return registerValueR; //return the registers value
}

void writeRegister(uint8_t registerAddress, uint8_t registerValueW)
{	
  //Relevant video: https://youtu.be/KQ0nWjM-MtI
   while (digitalRead(DRDY_pin)) {} //we "stuck" here until the DRDY changes its state  
  
	SPI.beginTransaction(SPISettings(1920000, MSBFIRST, SPI_MODE1));
	//SPI_MODE1 = output edge: rising, data capture: falling; clock polarity: 0, clock phase: 1.  

	//CS must stay LOW during the entire sequence [Ref: P34, T24]

  digitalWrite(CS_pin, LOW); //CS_pin goes LOW
  
  delayMicroseconds(5); //see t6 in the datasheet
  
	SPI.transfer(0x50 | registerAddress); // 0x50 = WREG

	SPI.transfer(0x00);	

	SPI.transfer(registerValueW); //we write the value to the above selected register
	
	digitalWrite(CS_pin, HIGH); //CS_pin goes HIGH
	SPI.endTransaction();
}

void reset_ADS1256()
{
	SPI.beginTransaction(SPISettings(1920000, MSBFIRST, SPI_MODE1)); // initialize SPI with  clock, MSB first, SPI Mode1

	digitalWrite(CS_pin, LOW); //CS_pin goes LOW

	delayMicroseconds(10); //wait

	SPI.transfer(0xFE); //Reset

	delay(2); //Minimum 0.6 ms required for Reset to finish.

	SPI.transfer(0x0F); //Issue SDATAC

	delayMicroseconds(100);

	digitalWrite(CS_pin, HIGH); //CS_pin goes HIGH

	SPI.endTransaction();

 Serial.println("*Reset DONE!"); //confirmation message
}

void initialize_ADS1256()	//starting up the chip by making the necessary steps. This is in the setup() of the Arduino code.
{
	//Setting up the pins first
	//Chip select
	pinMode(CS_pin, OUTPUT); //Chip select is an output
	digitalWrite(CS_pin, LOW); //Chip select LOW

	SPI.begin(); //start SPI (Arduino/STM32 - ADS1256 communication protocol)
  //The STM32-ADS1256 development board uses a different SPI channel (SPI_2)
  //For more info: https://youtu.be/3Rlr0FCffr0

	CS_Value = CS_pin; //We store the value of the CS_pin in a variable

	//DRDY
	pinMode(DRDY_pin, INPUT); //DRDY is an input
	pinMode(RESET_pin, OUTPUT); //RESET pin is an output
	digitalWrite(RESET_pin, LOW); //RESET is set to low 

  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, LOW); // Default OFF (Mode 4mA)

	delay(500); // Wait

	digitalWrite(RESET_pin, HIGH); //RESET is set to high

	delay(500); // Wait

}

void readContinuous_AIN0_AIN1() 
{
  // --- KONFIGURASI MUX KE AIN0-AIN1 ---
  // Kita harus set register MUX dulu agar yakin membaca Differential AIN0-AIN1
  while (digitalRead(DRDY_pin)) {} 
  
  SPI.beginTransaction(SPISettings(1920000, MSBFIRST, SPI_MODE1));
  digitalWrite(CS_pin, LOW);
  SPI.transfer(0x50 | 1);   // WREG ke Register 1 (MUX)
  SPI.transfer(0x00);       // 1 byte
  SPI.transfer(B00000001);  // Value: AIN0(P) - AIN1(N)
  digitalWrite(CS_pin, HIGH);
  SPI.endTransaction();

  // Sync & Wakeup (Reset ADC filter)
  SPI.beginTransaction(SPISettings(1920000, MSBFIRST, SPI_MODE1));
  digitalWrite(CS_pin, LOW);
  SPI.transfer(B11111100); // SYNC
  delayMicroseconds(4);
  SPI.transfer(B11111111); // WAKEUP
  digitalWrite(CS_pin, HIGH);
  SPI.endTransaction();

  Serial.println("*Continuous Read AIN0-AIN1 (0.5s). Kirim 's' untuk stop.");

  // --- LOOP PEMBACAAN (Berdasarkan logic readSingle) ---
  while (Serial.read() != 's') 
  {
    registerData = 0; 
  
    // Wait for DRDY to go LOW
    while (digitalRead(DRDY_pin)) {} 

    SPI.beginTransaction(SPISettings(1920000, MSBFIRST, SPI_MODE1));
    digitalWrite(CS_pin, LOW); 
     
    // Issue RDATA command
    SPI.transfer(B00000001);

    // Wait t6 time 
    delayMicroseconds(10); 

    // Step out the data
    registerData |= SPI.transfer(0x0F); 
    registerData <<= 8;         
    registerData |= SPI.transfer(0x0F); 
    registerData <<= 8;         
    registerData |= SPI.transfer(0x0F); 

 
    // --- FORMAT OUTPUT SESUAI REQUEST ANDA ---
    Serial.println("==============================");
    Serial.print("ADC Reading: ");
    Serial.println(registerData); // Raw data
    Serial.print("Voltage Reading (V): ");
    convertToVoltage(registerData); // Voltage & print
    Serial.print("Current Reading (mA): "); // Asumsi arus 100mA (0.1A)
    if (digitalRead(RELAY_PIN) == HIGH) 
    {
      // Jika Pin 7 ON (High Current Mode)
      Serial.println("100"); // Asumsi arus 100mA (0.1A)
    } 
    else 
    {
      // Jika Pin 7 OFF (Low Current Mode)
      Serial.println("4"); // Arus 4mA (0.004A)
    }
    
    // voltageToResistance(registerData); // Migrate convertToVoltage to here
    Serial.println("==============================");  
   
    digitalWrite(CS_pin, HIGH); 
    SPI.endTransaction();

    delay(500); // Interval 0.5 detik
  }
}

void streamContinuous_CSV(int posCh, int negCh) 
{
  // Constrain inputs to valid ADS1256 channels (0-7 for AIN0-AIN7, 8 for AINCOM)
  posCh = constrain(posCh, 0, 8);
  negCh = constrain(negCh, 0, 8);
  
  // Calculate the MUX byte. Example for C1 2: (1 << 4) | 2 = B00010010
  uint8_t muxValue = (posCh << 4) | negCh;

  // --- CONFIGURE MUX ---
  while (digitalRead(DRDY_pin)) {} 
  
  SPI.beginTransaction(SPISettings(1920000, MSBFIRST, SPI_MODE1));
  digitalWrite(CS_pin, LOW);
  SPI.transfer(0x50 | 1);   // WREG to Register 1 (MUX)
  SPI.transfer(0x00);       
  SPI.transfer(muxValue);   // Apply the dynamic MUX value
  digitalWrite(CS_pin, HIGH);
  SPI.endTransaction();

  // --- Sync & Wakeup (Reset ADC filter) ---
  SPI.beginTransaction(SPISettings(1920000, MSBFIRST, SPI_MODE1));
  digitalWrite(CS_pin, LOW);
  SPI.transfer(B11111100); // SYNC
  delayMicroseconds(4);
  SPI.transfer(B11111111); // WAKEUP
  digitalWrite(CS_pin, HIGH);
  SPI.endTransaction();

  // Send a header so Python knows the stream is starting
  Serial.println("*STREAM_START");

  bool stopStream = false;
  while (!stopStream) 
  {
    // Check if Python sent the 's' command to stop
    if (Serial.available() > 0) {
      if (Serial.read() == 's') {
        stopStream = true;
        break;
      }
    }

    registerData = 0;
    while (digitalRead(DRDY_pin)) {} // Wait for DRDY

    SPI.beginTransaction(SPISettings(1920000, MSBFIRST, SPI_MODE1));
    digitalWrite(CS_pin, LOW); 
     
    SPI.transfer(B00000001); // Issue RDATA command
    delayMicroseconds(10);   // Wait t6 time 
    
    registerData |= SPI.transfer(0x0F); 
    registerData <<= 8;         
    registerData |= SPI.transfer(0x0F); 
    registerData <<= 8;
    registerData |= SPI.transfer(0x0F); 
    
    digitalWrite(CS_pin, HIGH); 
    SPI.endTransaction();

    // --- CONVERT TO VOLTAGE ---
    if (registerData >> 23 == 1) { 
      registerData = registerData - 16777216;
    }
    double v = ((2 * VREF) / 8388608) * registerData; 

    // --- GET CURRENT STATE ---
    /*
    int current_mA = 4; // Default Low Current Mode
    if (digitalRead(RELAY_PIN) == HIGH) {
      current_mA = 100; // High Current Mode
    }
    */

    // --- PRINT CSV FORMAT ---
    Serial.println(v, 8);
    //Serial.print(",");
    //Serial.println(current_mA);
  }
  Serial.println("*STREAM_STOP");
}

void sendDirectCommand(uint8_t directCommand)
{
	//Direct commands can be found in the datasheet Page 34, Table 24. 
  //Use binary, hex or dec format. 
	//Here, we want to use everything EXCEPT: RDATA, RDATAC, SDATAC, RREG, WREG
	//We don't want to involve DRDY here. We just write, but don't read anything.

	//Start SPI
	SPI.beginTransaction(SPISettings(1700000, MSBFIRST, SPI_MODE1));

	digitalWrite(CS_pin, LOW); //REF: P34: "CS must stay low during the entire command sequence"

	delayMicroseconds(5); //t6 - maybe not necessary

	SPI.transfer(directCommand); //Send Command

	delayMicroseconds(5); //t6 - maybe not necessary

	digitalWrite(CS_pin, HIGH); //REF: P34: "CS must stay low during the entire command sequence"

	SPI.endTransaction();

}

void userDefaultRegisters()
{
	// This function is "manually" updating the values of the registers then reads them back.
	// This function should be used in the setup() after performing an initialization-reset process 
  // I use the below listed settings for my "startup configuration"
	/*
		REG   VAL     USE
		0     54      Status Register, Everything Is Default, Except ACAL and BUFEN
		1     1       Multiplexer Register, AIN0 POS, AIN1 POS
		2     0       ADCON, Everything is OFF, PGA = 1 [w2 0, PGA = 1; w2 1, PGA = 2; w2 2, PGA = 4; w2 3, PGA = 8; w2 4, PGA = 16]
		3     99      DataRate = 50 SPS		
    */	
    
	//We update the 4 registers that we are going to use
  
	delay(500);
  
  writeRegister(0x00, B00110110); //STATUS                      
	delay(200);
	writeRegister(0x01, B00000001); //MUX AIN0+AIN1
	delay(200);
	writeRegister(0x02, B00000000); //ADCON default PGA = 1
	delay(200);
	writeRegister(0x03, B01100011); //DRATE - DEC[99] - 50 SPS
	delay(500);
  sendDirectCommand(B11110000);	// SELFCAL
	Serial.println("*Register defaults updated!");
}

void printInstructions()
{
	//This function should be in the setup() and it shows the commands

 PrintMessage = "*Use the following letters to send a command to the device:" + String("\n") 
  + "*r - Read a register. Example: 'r1' - reads the register 1" + String("\n") 
  + "*w - Write a register. Example: 'w1 8' - changes the value of the 1st register to 8." + String("\n") 
  + "*E - Membaca AIN0-AIN1 (Differential) setiap 0.5 detik." + String("\n")
  + "*R - Reset ADS1256. Example: 'R' - Resets the device, everything is set to default." + String("\n")  
  + "*C - Continuous read AIN0-AIN1 ADS1256. Further feature improvement C0 1, C1 2, C2 4, and etc" + String("\n");

  Serial.println(PrintMessage);
  PrintMessage = ""; //Reset (empty) variable.
}

void convertToVoltage(int32_t registerData)
{
  if (long minus = registerData >> 23 == 1) //if the 24th bit (sign) is 1, the number is negative
    {
      registerData = registerData - 16777216;  //conversion for the negative sign
      //"mirroring" around zero
    }

    voltage = ((2*VREF) / 8388608)*registerData; //2.5 = Vref; 8388608 = 2^{23} - 1

    //Basically, dividing the positive range with the resolution and multiplying with the bits   
    
    Serial.println(voltage, 8); //print it on serial, 8 decimals    
    voltage = 0; //reset voltage
}


//--------------------------------------------------------------------------------
//end of code
//--------------------------------------------------------------------------------
//Good to know things
/*
TAU = 1/f = 1/7.68 MHz = 130.2 ns

For a 7.68 MHz ADC clock, the SCLK may not exceed 1.92 MHz.

Binary to decimal is read from right to left
8 bit = 1 byte

0000 0001 = 1 (2^0)
0000 0011 = 3 (2^0 + 2^1)
1000 0001 = 129 (2^0 + 2^7)

PAGE 34 of the datasheet, Table 24: Command definitions
RREG and WREG require a second command byte plus data. 
The ORDER bit in the STATUS register sets the order of the bits within the output data.
CS must stay LOW during the entire sequence.

The operator '|' is the bitwise OR operator. 
Example:
0  0  1  1    operand1
0  1  0  1    operand2
----------
0  1  1  1    (operand1 | operand2) - returned result
//---------------------------------------------------

DRDY goes LOW when new data is available. - When all the 24 bits have been read back, it goes back to HIGH.

The operator '|=' is the compound bitwise operator.

OUTPUT CODES //REF Page23 Table16

1: Vin (AIN_P - AIN_N) > (2Vref)/PGA
	7FFFFFh = 8388607 = 0111 1111 1111 1111 1111 1111

2: Vin (AIN_P - AIN_N) < (-2Vref)/PGA *((2^23)/(2^23 -1))
	800000h = 8388608 = 1000 0000 0000 0000 0000 0000
*/