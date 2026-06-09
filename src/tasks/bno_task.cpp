// bno_task.cpp
#include "bno_task.h"
#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>
#include <esp_log.h>
#include <math.h>
#include <CodeCell.h>

CodeCell myCodeCell;

namespace {
constexpr int  RUN_RATE_HZ = 10;
const char* TAG = "BNO";

QueueHandle_t latestQueue   = nullptr;
TaskHandle_t  bnoTaskHandle = nullptr;

constexpr float RAD2DEG = 57.2957795f;

inline float wrap360(float deg) {
    deg = fmodf(deg, 360.0f);
    if (deg < 0.0f) deg += 360.0f;
    return deg;
}
}

// Tilt-compensated heading from accelerometer + magnetometer.
// ax,ay,az: gravity vector (m/s^2 or g; only the direction matters)
// mx,my,mz: magnetic field (uT)
// Outputs azimuth (0..360) and elevation/polar angles in degrees.
static void compute_angles(float ax, float ay, float az,
                           float mx, float my, float mz,
                           BnoSample* s)
{
    // Pitch and roll from gravity vector.
    float pitch = atan2f(-ax, sqrtf(ay * ay + az * az));   // rotation around Y
    float roll  = atan2f(ay, az);                          // rotation around X

    // Tilt-compensate the magnetometer into the horizontal plane.
    float cp = cosf(pitch), sp = sinf(pitch);
    float cr = cosf(roll),  sr = sinf(roll);

    float mx_h = mx * cp + mz * sp;
    float my_h = mx * sr * sp + my * cr - mz * sr * cp;

    float yaw = atan2f(-my_h, mx_h) * RAD2DEG;   // heading

    s->azimuth_deg   = wrap360(yaw);
    s->elevation_deg = pitch * RAD2DEG;
    s->polar_deg     = 90.0f - s->elevation_deg;
    if (s->polar_deg < 0.0f)   s->polar_deg = 0.0f;
    if (s->polar_deg > 180.0f) s->polar_deg = 180.0f;

    // Stash raw vectors for post-processing if you want them.
    s->qi = ax; s->qj = ay; s->qk = az; s->qr = 0.0f;
}

static void bnoTask(void*)
{
    // Init was already done in bno_task_init()
    float ax = 0, ay = 0, az = 0;
    float mx = 0, my = 0, mz = 0;

    for (;;) {
        if (myCodeCell.Run(RUN_RATE_HZ)) {
            myCodeCell.Motion_AccelerometerRead(ax, ay, az);
            myCodeCell.Motion_MagnetometerRead(mx, my, mz);

            BnoSample sample = {};
            compute_angles(ax, ay, az, mx, my, mz, &sample);
            sample.accuracy_rad = 0.0f;

            xQueueOverwrite(latestQueue, &sample);
        }
        vTaskDelay(1);
    }
}

void bno_task_init(void)
{
    myCodeCell.Init(MOTION_ACCELEROMETER + MOTION_MAGNETOMETER);
}

void bno_task_start(void)
{
    latestQueue = xQueueCreate(1, sizeof(BnoSample));
    xTaskCreate(bnoTask, "BNO Task", 8192, nullptr, 1, &bnoTaskHandle);
}

bool bno_task_get_latest(BnoSample* out)
{
    if (!latestQueue || !out) return false;
    return xQueuePeek(latestQueue, out, 0) == pdTRUE;
}


// // bno_task.cpp
// #include "bno_task.h"
// #include <Arduino.h>
// #include <freertos/FreeRTOS.h>
// #include <freertos/task.h>
// #include <freertos/queue.h>
// #include <esp_log.h>
// #include <math.h>
// #include <CodeCell.h>

// namespace {
// constexpr int  RUN_RATE_HZ = 20;        // IMU update rate
// const char* TAG = "BNO";

// QueueHandle_t latestQueue   = nullptr;  // depth 1, overwrite slot
// TaskHandle_t  bnoTaskHandle = nullptr;

// CodeCell myCodeCell;

// constexpr float RAD2DEG = 57.2957795f;

// inline float wrap360(float deg) {
//     deg = fmodf(deg, 360.0f);
//     if (deg < 0.0f) deg += 360.0f;
//     return deg;
// }
// }

// // Quaternion -> antenna spherical angles.
// // TUNE THIS to match how the CodeCell is mounted on your positioner.
// static void quat_to_angles(float qi, float qj, float qk, float qr, BnoSample* s)
// {
//     float yaw   = atan2f(2.0f * (qr * qk + qi * qj),
//                          1.0f - 2.0f * (qj * qj + qk * qk)) * RAD2DEG;
//     float pitch = asinf (2.0f * (qr * qj - qk * qi)) * RAD2DEG;

//     s->azimuth_deg   = wrap360(yaw);
//     s->elevation_deg = pitch;
//     s->polar_deg     = 90.0f - pitch;
//     if (s->polar_deg < 0.0f)   s->polar_deg = 0.0f;
//     if (s->polar_deg > 180.0f) s->polar_deg = 180.0f;
// }

// static void bnoTask(void*)
// {
//     myCodeCell.Init(MOTION_ROTATION);   // enable rotation-vector fusion
//     ESP_LOGI(TAG, "CodeCell BNO085 rotation vector enabled");

//     for (;;) {
//         // Run(Hz) returns true at the requested cadence; it paces the loop.
//         if (myCodeCell.Run(RUN_RATE_HZ)) {
//             BnoSample sample = {};

//             // Quaternion read: order is (r, i, j, k) — real part first.
//             float vr = 0, vi = 0, vj = 0, vk = 0;
//             myCodeCell.Motion_RotationVectorRead(vr, vi, vj, vk);

//             sample.qr = vr;
//             sample.qi = vi;
//             sample.qj = vj;
//             sample.qk = vk;

//             quat_to_angles(sample.qi, sample.qj, sample.qk, sample.qr, &sample);
//             sample.accuracy_rad = 0.0f;

//             xQueueOverwrite(latestQueue, &sample);
//         }
//         // No vTaskDelay needed: Run(Hz) blocks/paces internally. Yield briefly
//         // so the idle task and watchdog are happy if Run returns immediately.
//         vTaskDelay(1);
//     }
// }

// void bno_task_start(void)
// {
//     latestQueue = xQueueCreate(1, sizeof(BnoSample));
//     xTaskCreate(bnoTask, "BNO Task", 8192, nullptr, 1, &bnoTaskHandle);
// }

// bool bno_task_get_latest(BnoSample* out)
// {
//     if (!latestQueue || !out) return false;
//     return xQueuePeek(latestQueue, out, 0) == pdTRUE;
// }