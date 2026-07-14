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
// --- Antenna boresight in BODY frame. +X matches your current azimuth convention.
// was: constexpr float BORESIGHT_BX = 1.0f, BORESIGHT_BY = 0.0f, BORESIGHT_BZ = 0.0f;
constexpr float BORESIGHT_BX = 0.0f, BORESIGHT_BY = 1.0f, BORESIGHT_BZ = 0.0f;

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

// Rotate a body-frame unit vector into world frame by quaternion (w,x,y,z) = R(q)*b
inline void rotate_body_to_world(float w, float x, float y, float z,
                                 float bx, float by, float bz,
                                 float& vx, float& vy, float& vz) {
  vx = (1.f-2.f*(y*y+z*z))*bx + 2.f*(x*y-w*z)*by     + 2.f*(x*z+w*y)*bz;
  vy = 2.f*(x*y+w*z)*bx       + (1.f-2.f*(x*x+z*z))*by + 2.f*(y*z-w*x)*bz;
  vz = 2.f*(x*z-w*y)*bx       + 2.f*(y*z+w*x)*by       + (1.f-2.f*(x*x+y*y))*bz;
}

void fill_sample(float roll, float pitch, float yaw, BnoSample* s) {
    s->azimuth_deg = wrap360(yaw - yaw_offset);

    // Elevation from pitch — CONFIRM axis against your physical mount.
    s->elevation_deg = pitch;
    s->polar_deg     = 90.0f - s->elevation_deg;
    if (s->polar_deg < 0.0f)   s->polar_deg = 0.0f;
    if (s->polar_deg > 180.0f) s->polar_deg = 180.0f;
}

void fill_sample_q(float w, float x, float y, float z, BnoSample* s) {
  float vx, vy, vz;
  rotate_body_to_world(w, x, y, z, BORESIGHT_BX, BORESIGHT_BY, BORESIGHT_BZ, vx, vy, vz);
  float az = atan2f(vy, vx) * RAD_TO_DEG;              // [-180,180]
  float el = atan2f(vz, hypotf(vx, vy)) * RAD_TO_DEG;  // [-90,90] — bounded, no asin clamp needed
  s->azimuth_deg   = wrap360(az - yaw_offset);
  s->elevation_deg = el;
  s->polar_deg     = 90.0f - el;                       // [0,180] by construction; clamp now redundant
}

float read_yaw_blocking() {  // now reads boresight azimuth
  while (!myCodeCell.Run(RUN_RATE_HZ)) delay(5);
  float w=Motion.getGameReal(), x=Motion.getGameI(), y=Motion.getGameJ(), z=Motion.getGameK();
  float vx, vy, vz;
  rotate_body_to_world(w, x, y, z, BORESIGHT_BX, BORESIGHT_BY, BORESIGHT_BZ, vx, vy, vz);
  return atan2f(vy, vx) * RAD_TO_DEG;
}
} // namespace

static void bnoTask(void*) {
    for (;;) {
        if (myCodeCell.Run(RUN_RATE_HZ)) {
            cal_accuracy = Motion.getRot_Accuracy() & 0x03;   // mask off delay bits

            float w = Motion.getGameReal();
            float x = Motion.getGameI();
            float y = Motion.getGameJ();
            float z = Motion.getGameK();

            if (zero_requested) {              // re-zero in azimuth space, not Euler yaw
                float vx, vy, vz;
                rotate_body_to_world(w, x, y, z,
                                     BORESIGHT_BX, BORESIGHT_BY, BORESIGHT_BZ,
                                     vx, vy, vz);
                yaw_offset = atan2f(vy, vx) * RAD_TO_DEG;
                zero_requested = false;
            }

            BnoSample sample = {};
            fill_sample_q(w, x, y, z, &sample);
            sample.qr = w; sample.qi = x; sample.qj = y; sample.qk = z;

            sample.accuracy_rad = 0.0f;        // no radian estimate for game-RV
            xQueueOverwrite(latestQueue, &sample);
        }
        vTaskDelay(1);
    }
}

// 2) spinning RUn() in loop so that BNO can detect stationairity and settle the gyro ZRO -> want accuracy = 3
// Hold the board DEAD STILL on a stable surface for the whole window so the BNO
// can detect stationarity and compute the gyro zero-rate offset. This is what
// kills the 1°/s drift Returns the achieved fusion accuracy.
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

// 1) selecting game rotation vector + gyro offset estimation 
void bno_task_init(void) {
    myCodeCell.Init(MOTION_ROTATION_NO_MAG);
    // The wrapper never enables gyro calibration -> ZRO uncorrected -> ~1°/s drift.
    // Turn on accel+gyro dynamic calibration so the fusion estimates and removes
    // the gyro bias during stillness -> THERE EXISTS A FUNCTION ON CODECELL LIBRARY YES!!
    Motion.setCalibrationConfig(SH2_CAL_ACCEL | SH2_CAL_GYRO);
}

// 3) takes quaternion, rotates boresight vecotr into world frame, stores azimuth as yaw_offset
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


