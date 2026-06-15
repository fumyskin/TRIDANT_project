#include <Arduino.h>
#include <tasks/sensor_task.h>
#include "tasks/bno_task.h"
#include <CodeCell.h>
#include <Wire.h>

// Refer to APD8317 documentation for correct parametrization:
// correct calibration:
constexpr float LPD_SLOPE_MV_PER_DB = -22.0f; // mV/dBm
constexpr float LPD_INTERCEPT_MV    = 15.0f; // dBm

static float mv_to_dbm(int mv) {
    return ((float)mv - LPD_INTERCEPT_MV) / LPD_SLOPE_MV_PER_DB;
}

BnoSample ang;

void setup() {
    Serial.begin(115200);
    delay(2000);
    Serial.println("BOOT");

    sensor_task_start();
    bno_task_init();        // do BNO Init() in main thread
    Serial.println("Move device in figure-8 for calibration...");
    bno_task_warmup(15000);   // 15 s of active sensor ticking
    Serial.println("Capturing zero — hold still");
    delay(500);    
    bno_task_capture_zero();
    bno_task_start();       // then start the task that only does Run/Read

    Serial.println("tasks started");
    Serial.println("phi_deg,theta_deg,elev_deg,P_dBm,mv");
}

void loop() {
    int mv = 0;
    bool haveP   = sensor_task_get_latest_mv(&mv);
    bool haveAng = bno_task_get_latest(&ang);

    if (haveP && haveAng) {
        Serial.printf("%.1f,%.1f,%.1f,%.2f,%d\n",
                      ang.azimuth_deg,
                      ang.polar_deg,
                      ang.elevation_deg,
                      mv_to_dbm(mv),
                      mv);
    } else {
        Serial.printf("waiting: haveP=%d haveAng=%d\n", haveP, haveAng);
    }
    delay(100);   // ~10 Hz logging, matches the BNO Run(10) rate
}




// void setup() {
//   Serial.begin(115200);
//   delay(500);
//   Serial.println("=== boot ===");
//   sensor_task_start();
// }

// void loop() {
//   int mv = 0;
//   if (sensor_task_get_latest_mv(&mv)) {
//     Serial.printf("LDR mV = %d\n", mv);
//   } else {
//     Serial.println("no sample yet");
//   }
//   delay(500);
// }


// CodeCell myCodeCell;

// float Roll = 0.0;
// float Pitch = 0.0;
// float Yaw = 0.0;

// void setup() {
//   Serial.begin(115200);              // Start serial monitor
//   myCodeCell.Init(MOTION_ROTATION);  // Enable rotation sensing
// }

// void loop() {
//   if (myCodeCell.Run(10)) {          // Run loop at 10 Hz
//     myCodeCell.Motion_RotationRead(Roll, Pitch, Yaw);
//     Serial.printf("Roll: %.2f°, Pitch: %.2f°, Yaw: %.2f°\n", Roll, Pitch, Yaw);
//   }
// }





// #include <Arduino.h>
// #include <tasks/sensor_task.h>
// #include "tasks/bno_task.h"

// // --- From your detector's datasheet (AD8318-like placeholders) ---
// constexpr float LPD_SLOPE_MV_PER_DB = -25.0f;   // mV per dB (negative for most LPDs)
// constexpr float LPD_INTERCEPT_MV    = 2000.0f;  // output mV at 0 dBm reference

// static float mv_to_dbm(int mv) {
//     return ((float)mv - LPD_INTERCEPT_MV) / LPD_SLOPE_MV_PER_DB;
// }

// void setup() {
//     Serial.begin(115200);
//     delay(500);
//     sensor_task_start();
//     bno_task_start();
// }

// void loop() {
//     int mv = 0;
//     BnoSample ang;
//     bool haveP   = sensor_task_get_latest_mv(&mv);
//     bool haveAng = bno_task_get_latest(&ang);

//     if (haveP && haveAng) {
//         Serial.printf("%.1f,%.1f,%.1f,%.1f\n",
//                       ang.azimuth_deg, ang.polar_deg,
//                       ang.elevation_deg, mv_to_dbm(mv));
//     } else {
//         Serial.printf("waiting: haveP=%d haveAng=%d\n", haveP, haveAng);
//     }
//     delay(100);
// }