// bno_task.h
#pragma once

struct BnoSample {
    float azimuth_deg;
    float elevation_deg;
    float polar_deg;
    float qi, qj, qk, qr;
    float accuracy_rad;
};

void bno_task_init(void);    // call from setup() before bno_task_start()
void bno_task_start(void);
bool bno_task_get_latest(BnoSample* out);