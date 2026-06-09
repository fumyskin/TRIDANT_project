#pragma once
#include <stdint.h>
#include <stdbool.h>

// really necessary ?
#ifdef __cplusplus
extern "C" {
#endif

// start the sensor sampling task. Call once at boot.
void sensor_task_start(void);

// Non-blocking. Returns true and writes the latest sample (mV) into *out
// if at least one sample has been taken; returns false otherwise.
bool sensor_task_get_latest_mv(int* out);

#ifdef __cplusplus
}
#endif