#pragma once
#include <stdint.h>
#include "sample.h"

void ble_task_start();
void ble_task_setup_ble();
void ble_task_start_advertising();
bool ble_task_has_clients();
void ble_task_send_sample(const Sample& s);

