// =========================
// FILE: TemperatureSensors.h
// =========================

#ifndef TEMPERATURE_H
#define TEMPERATURE_H

#include <Wire.h>
//#include <Adafruit_SHT31.h>
#include <Adafruit_MLX90614.h>

// Create sensor objects
//Adafruit_SHT31 sht31 = Adafruit_SHT31();
Adafruit_MLX90614 mlx = Adafruit_MLX90614();


// =========================
// Initialize Sensors
// =========================
bool initTemperatureSensors() {
  Wire.begin();
  //Serial.println("Sensor initializing");
  bool status = true;

  // Init SHT31
  //if (!sht31.begin(0x44)) {
    //Serial.println("SHT31 not found");
    //status = false;
  //} //else {
    //Serial.println("SHT31 initialized");
  //}

  // Init MLX90614
  if (!mlx.begin()) {
    Serial.println("MLX90614 not found");
    status = false;
  } //else {
    //Serial.println("MLX90614 initialized");
  //}
  //Serial.println("Sensor initialized");
  return status;
}


// =========================
// Print SHT31 Values
// =========================
//void printSHT() {

  //float temp = sht31.readTemperature();
  //float hum  = sht31.readHumidity();

  //Serial.print("SHT");
  //Serial.println(temp);
//}


// =========================
// Print MLX90614 Values
// =========================
void printMLX() {

  float objectTemp  = mlx.readObjectTempC();
  float ambientTemp = mlx.readAmbientTempC();

  Serial.print("MLX");
  Serial.println(objectTemp);

  delay(1000);

}

#endif