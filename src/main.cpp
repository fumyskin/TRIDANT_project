#include <Arduino.h>
#include <tasks/sensor_task.h>
#include "tasks/bno_task.h"
#include <CodeCell.h>
#include <Wire.h>

// Refer to APD8317 documentation for correct parametrization:
// correct calibration:
// NOTE: V2X and GNSS require different x intercepts: deal with it 
constexpr float LPD_SLOPE_MV_PER_DB = -25.0f; // mV/dBm
constexpr float LPD_INTERCEPT_MV    = 2100.0f; // mV

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



