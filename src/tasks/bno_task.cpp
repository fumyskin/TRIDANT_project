// bno_task.cpp  — MOTION_ROTATION_NO_MAG (gyro+accel, interference-proof)
#include "bno_task.h"
#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>
#include <math.h>
#include <CodeCell.h>
#include <BNO085.h>          // type behind the wrapper, for the accuracy byte

CodeCell myCodeCell;
extern BNO085 Motion;        // global IMU object defined inside the CodeCell lib

namespace {
constexpr int RUN_RATE_HZ = 10;

QueueHandle_t latestQueue   = nullptr;
TaskHandle_t  bnoTaskHandle = nullptr;

float            yaw_offset     = 0.0f;   // captured zero -> start-relative azimuth
volatile uint8_t cal_accuracy   = 0;      // game-RV fusion readiness, 0..3
volatile bool    zero_requested = false;

inline float wrap360(float deg) {
    deg = fmodf(deg, 360.0f);
    if (deg < 0.0f) deg += 360.0f;
    return deg;
}

void fill_sample(float roll, float pitch, float yaw, BnoSample* s) {
    s->azimuth_deg = wrap360(yaw - yaw_offset);

    // Elevation from pitch — CONFIRM axis against your physical mount.
    s->elevation_deg = pitch;
    s->polar_deg     = 90.0f - s->elevation_deg;
    if (s->polar_deg < 0.0f)   s->polar_deg = 0.0f;
    if (s->polar_deg > 180.0f) s->polar_deg = 180.0f;
}

float read_yaw_blocking() {
    float r = 0, p = 0, y = 0;
    while (!myCodeCell.Run(RUN_RATE_HZ)) {
        delay(5);
    }
    myCodeCell.Motion_RotationNoMagRead(r, p, y);
    return wrap360(y);
}
} // namespace

static void bnoTask(void*) {
    float roll = 0, pitch = 0, yaw = 0;
    for (;;) {
        if (myCodeCell.Run(RUN_RATE_HZ)) {
            myCodeCell.Motion_RotationNoMagRead(roll, pitch, yaw);
            cal_accuracy = Motion.getRot_Accuracy() & 0x03;   // mask off delay bits

            if (zero_requested) {              // single-owner runtime re-zero
                yaw_offset = wrap360(yaw);
                zero_requested = false;
            }

            BnoSample sample = {};
            fill_sample(roll, pitch, yaw, &sample);

            // Real game-rotation quaternion (valid: only game-RV is enabled here).
            sample.qr = Motion.getGameReal();
            sample.qi = Motion.getGameI();
            sample.qj = Motion.getGameJ();
            sample.qk = Motion.getGameK();

            sample.accuracy_rad = 0.0f;        // no radian estimate for game-RV
            xQueueOverwrite(latestQueue, &sample);
        }
        vTaskDelay(1);
    }
}

// Hold the board DEAD STILL on a stable surface for the whole window so the BNO
// can detect stationarity and compute the gyro zero-rate offset. This is what
// kills the 1°/s drift?? Returns the achieved fusion accuracy.
bool bno_task_calibrate(uint32_t still_ms, uint8_t target_acc) {
    float r, p, y;
    uint32_t start = millis();
    while (millis() - start < still_ms) {
        if (myCodeCell.Run(RUN_RATE_HZ)) {
            myCodeCell.Motion_RotationNoMagRead(r, p, y);
            cal_accuracy = Motion.getRot_Accuracy() & 0x03;
        }
        delay(5);
    }
    return cal_accuracy >= target_acc;
}

void bno_task_init(void) {
    myCodeCell.Init(MOTION_ROTATION_NO_MAG);
    // The wrapper never enables gyro calibration -> ZRO uncorrected -> ~1°/s drift.
    // Turn on accel+gyro dynamic calibration so the fusion estimates and removes
    // the gyro bias during stillness -> THERE EXISTS A FUNCTION ON CODECELL LIBRARY YES!!
    Motion.setCalibrationConfig(SH2_CAL_ACCEL | SH2_CAL_GYRO);
}

void bno_task_capture_zero(void) {
    yaw_offset = read_yaw_blocking();
}

void bno_task_request_zero(void) { zero_requested = true; }

uint8_t bno_task_cal_accuracy(void) { return cal_accuracy; }

void bno_task_start(void) {
    latestQueue = xQueueCreate(1, sizeof(BnoSample));
    xTaskCreate(bnoTask, "BNO Task", 8192, nullptr, 1, &bnoTaskHandle);
}

bool bno_task_get_latest(BnoSample* out) {
    if (!latestQueue || !out) return false;
    return xQueuePeek(latestQueue, out, 0) == pdTRUE;
}
