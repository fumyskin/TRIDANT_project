// bno_task.h
#pragma once
#include <cstdint>

struct BnoSample {
    float azimuth_deg;
    float elevation_deg;
    float polar_deg;
    float qi, qj, qk, qr;
    float accuracy_rad;
};

void bno_task_warmup(uint32_t ms);
void bno_task_capture_zero(void);
void bno_task_init(void);    // call from setup() before bno_task_start()
void bno_task_start(void);
bool bno_task_get_latest(BnoSample* out);