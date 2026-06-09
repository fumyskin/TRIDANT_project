#pragma once
#include <stdint.h>

void ble_task_start();
void ble_task_setup_ble();
void ble_task_start_advertising();
void ble_task_set_value();
bool ble_task_has_clients();
void ble_task_run_application_loop();
