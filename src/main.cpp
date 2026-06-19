#include <Arduino.h>
#include <tasks/sensor_task.h>
#include "tasks/bno_task.h"
#include "tasks/ble_task.h"
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
    bno_task_init();
    bno_task_calibrate(8000, 3);   // ~8 s DEAD STILL on a table — gyro ZRO settles here
    bno_task_capture_zero();
    bno_task_start();

    //ble_task_start(); // create task + queue
    //ble_task_setup_ble(); // build service + characteristic
    //ble_task_start_advertising(); // go discoverable

    Serial.println("tasks started");
    Serial.println("phi_deg,theta_deg,elev_deg,P_dBm,mv,cal");   // <- added ,cal
}

void loop() {
    int mv = 0;
    bool haveP   = sensor_task_get_latest_mv(&mv);
    bool haveAng = bno_task_get_latest(&ang);
    uint32_t acc = bno_task_cal_accuracy();

    if (haveP && haveAng) {
        Serial.printf("%.1f,%.1f,%.1f,%.2f,%d, %u\n",
                      ang.azimuth_deg,
                      ang.polar_deg,
                      ang.elevation_deg,
                      mv_to_dbm(mv),
                      mv,
                      acc);
        //if (ble_task_has_clients()){
        //    Sample s;
        //    s.phi_deg = ang.azimuth_deg;
        //    s.theta_deg = ang.polar_deg;
        //    s.elev_deg = ang.elevation_deg;
        //    s.mv = (uint16_t)mv;
        //    s.acc = (uint8_t)acc;
        //    ble_task_send_sample(s);
        //}
    } else {
        Serial.printf("waiting: haveP=%d haveAng=%d cal=%u\n", haveP, haveAng, acc);
    }
    delay(100);   // ~10 Hz logging, matches the BNO Run(10) rate
}



