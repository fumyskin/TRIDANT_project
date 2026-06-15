/*
  Example: CodeCell Basics 
  Boards: CodeCell C3 / CodeCell C3 Light / CodeCell C6 / CodeCell C6 Drive

  Overview:
  - Shows the minimal setup to initialize CodeCell and its sensors.
  - You choose which sensors to enable via macros passed to Init().
  - Run() handles timing, sensor reads, and power/LED management.
  - This example enables the Light sensor and prints live readings.

  Arduino IDE Setup:
  - Make sure the ESP32 boards package is installed (Boards Manager → "esp32" by Espressif).

  For CodeCell C6 (ESP32-C6):
  - Board: ESP32C6 Dev Module
  - USB CDC On Boot: Enabled   // required for Serial over USB
  - CPU Frequency: 160 MHz
  - Flash Size: 8 MB (64 Mb)
  - Partition Scheme: 8M with SPIFFS (3 MB APP / 1.5 MB SPIFFS)
  - Port: Select the COM port for your CodeCell C6

  Init() Macros:
  - LIGHT                          // Light + proximity sensing
  - MOTION_ACCELEROMETER           // 3-axis acceleration
  - MOTION_GYRO                    // 3-axis angular velocity
  - MOTION_MAGNETOMETER            // 3-axis magnetic field
  - MOTION_LINEAR_ACC              // Linear acceleration
  - MOTION_GRAVITY                 // Gravity vector
  - MOTION_ROTATION                // Roll, pitch, yaw (with mag)
  - MOTION_ROTATION_NO_MAG         // Roll, pitch, yaw (no mag)
  - MOTION_STEP_COUNTER            // Step count
  - MOTION_STATE                   // On table / Stationary / Stable / In motion
  - MOTION_TAP_DETECTOR            // Tap detection
  - MOTION_ACTIVITY                // Activity classification

  Examples:
  - myCodeCell.Init(LIGHT);                                 // Light only
  - myCodeCell.Init(LIGHT + MOTION_ROTATION);               // Light + orientation
  - myCodeCell.Init(LIGHT + MOTION_ROTATION + MOTION_STATE);// Light + orientation + state

  Run() Loop:
  - Example: myCodeCell.Run(10) returns true at 10 Hz (every 100 ms)
  - Read all enabled sensors at this rate (Range: 1Hz - 100Hz)
  - The same call updates power status, reads enabled sensors, and drives the status LED.
  - Low battery behavior: below ~3.3 V the LED blinks red 10×, then the unit sleeps until USB is connected.
  - While on USB: the loop() keeps running; LED shows charging/charged status.

  Reading Sensors:
  - Light_ProximityRead()
  - Light_WhiteRead()
  - Light_AmbientRead()
  - Motion_TapRead()
  - Motion_StepCounterRead()
  - Motion_StateRead()
  - Motion_ActivityRead()
  - Motion_AccelerometerRead(float &x, float &y, float &z)
  - Motion_GyroRead(float &x, float &y, float &z)
  - Motion_MagnetometerRead(float &x, float &y, float &z)
  - Motion_GravityRead(float &x, float &y, float &z)
  - Motion_LinearAccRead(float &x, float &y, float &z)
  - Motion_RotationRead(float &roll, float &pitch, float &yaw)
  - Motion_RotationNoMagRead(float &roll, float &pitch, float &yaw)
  - Motion_RotationVectorRead(float &vec_r, float &vec_i, float &vec_j, float &vec_k)

  Power Readings:
  - PowerStateRead():
    * 0 = Running from LiPo Battery
    * 1 = Running from USB Power
    * 2 = Power Initializing
    * 3 = Battery Low
    * 4 = Battery Fully Charged
    * 5 = Battery Charging

  - BatteryVoltageRead()
    * Returns the LiPo voltage in millivolts (e.g., 3720 ≈ 3.72 V).
    * Useful for precise thresholds, logging, or battery graphs.
  
  - BatteryLevelRead()
    * Returns the battery level as a percentage:
        1–100  = Approximate state of charge (%)
        101     = Battery is charging (on USB and charging)
        102     = USB powered (bypassing battery for system power)
    * Handy for quick UI indicators without manual voltage-to-% mapping.

  Example (Battery):
  - int mv = myCodeCell.BatteryVoltageRead();   // e.g. 3720 (mV)
  - uint16_t lvl = myCodeCell.BatteryLevelRead();
    // if (lvl <= 100) { show percent }
    // else if (lvl == 101) { show "Charging" }
    // else if (lvl == 102) { show "USB Power" }

  GPIO Control:
  - myCodeCell.pinWrite(uint8_t pin, bool value);              // Write HIGH/LOW to pin
  - myCodeCell.pinRead(uint8_t pin);                           // Read digital pin state
  - myCodeCell.pinPWM(uint8_t pin, uint16_t freq, uint8_t dc); // Generate PWM (frequency, duty cycle)
  - myCodeCell.pinADC(uint8_t pin);                            // Read analog value from pin

  LED Control:
  - myCodeCell.LED_SetBrightness(0);   // Switch off the CodeCell LED
  - myCodeCell.LED_SetBrightness(10);  // Set LED to full brightness

  Sleep:
  - myCodeCell.SleepTimer(uint16_t sleep_sec);
  - myCodeCell.SleepProximityTrigger(uint16_t threshold);  // C6 hardware only
  - myCodeCell.SleepLightTrigger(uint16_t threshold);      // C6 hardware only
  - myCodeCell.SleepDarkTrigger(uint16_t threshold);       // C6 hardware only
  - myCodeCell.SleepTapTrigger();                          // C6 hardware only

  MicroLink App:
  - Download the CodeCell MicroLink library to connect with the companion smartphone App

  Tips:
  - Combine macros with + to enable multiple sensors.
  - Use myCodeCell.PrintSensors() to dump all enabled readings to Serial.
  - Learn more with tutorials: https://microbots.io/pages/learn-codecell
*/



#include <CodeCell.h>

CodeCell myCodeCell;

#define BUTTON_PIN 21 // GPIO21 pin connected to button
#define CHARGE_LED_PIN 22 //GPIO22 pin connected to LED
#define LPD_VOLTAGE_PIN 1 //GPIO01 pin connected to Vout of LPD

float Roll = 0.0;
float Pitch = 0.0;
float Yaw = 0.0;

int lastState = HIGH; // the previous state from the input pin
int currentState;     // the current reading from the input pin

float lpdVoltage = 0.0;

void setup() {
  Serial.begin(115200);  // Start USB serial at 115200 baud (enable USB_CDC_On_Boot for Serial)

  pinMode(1, )
  pinMode(21, INPUT_PULLUP); // config GPIO21 as input pin and enable the internal pull-up resistor
  pinMode(22, OUTPUT) // config GPIO22 as output pin for charge status LED
  myCodeCell.Intit(MOTION_ROTATION);

  // Add your custom initialization below
}

void loop() {
  
  if(myCodeCell.BatteryVoltageRead() <= 20){
    digitalWrite(CHARGE_LED_PIN, HIGH);
  }else{
    digitalWrite(CHARGE_LED_PIN, LOW);
  }

  if (myCodeCell.Run(10)) {     // Run every 10 Hz
    currentState = digitalRead(BUTTON_PIN);

    if(lastState == LOW && currentState == HIGH){
      myCodeCell.Motion_RotationRead(Roll, Pitch, Yaw); // Read latest rotation values
      Serial.printf("Roll: %.2f°, Pitch: %.2f°, Yaw: %.2f°\n", Roll, Pitch, Yaw); // Print  output

      //ALL CODE FOR BLUETOOTH TRANSMISSION OF COMPUTED DATA
    }

    lastState = currentState;
  }


}
