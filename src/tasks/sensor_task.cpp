#include "sensor_task.h"
#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>
#include <CodeCell.h>

extern CodeCell myCodeCell;   // declared in bno_task.cpp as the shared instance

namespace {
constexpr uint8_t  LDR_PIN          = 1;     // GPIO1 — change if your LDR is on a different pin
constexpr uint32_t SAMPLE_PERIOD_MS = 100;

QueueHandle_t latestQueue = nullptr;
TaskHandle_t  sensorTaskHandle = nullptr;
}

static void sensorTask(void*)
{
    for (;;) {
        // pinADC returns 0..4095 raw counts; convert to mV assuming 3.3V reference -> wrong, the reference is 2.5V for codecell c6 ADC
        uint32_t acc = 0;
        const int N = 32;
        for (int i = 0; i < N; ++i) acc += analogReadMilliVolts(LDR_PIN);
        int value_mv = acc / N;
        xQueueOverwrite(latestQueue, &value_mv);
        vTaskDelay(pdMS_TO_TICKS(SAMPLE_PERIOD_MS));
    }
}

void sensor_task_start(void)
{
    latestQueue = xQueueCreate(1, sizeof(int));
    xTaskCreate(sensorTask, "Sensor Task", 4096, nullptr, 1, &sensorTaskHandle);
}

bool sensor_task_get_latest_mv(int* out)
{
    if (!latestQueue || !out) return false;
    return xQueuePeek(latestQueue, out, 0) == pdTRUE;
}