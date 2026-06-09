#include "ble_task.h"
#include <Arduino.h>
#include <NimBLEDevice.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>

// configuration: will use nrf connect for now
#define MAX_CONNECTIONS 1
#define SERVICE_UUID        "97dcc426-d11e-476e-95e2-79f064720640"
#define CHARACTERISTIC_UUID "aae3a4f0-8e88-4bd0-8047-c6a8c2312a3d"
#define DEVICE_NAME         "ESP32_BLE"

// constexpr tells compiler that the value should be evaluated at compile times
static constexpr uint32_t TX_BURST_MS       = 200;
static constexpr uint32_t IDLE_BETWEEN_MS   = 5000;
static constexpr uint32_t IDLE_POLL_MS      = 100;

namespace {
    NimBLEServer*         pServer    = nullptr;
    NimBLECharacteristic* pChar      = nullptr;
    NimBLEAdvertising*    pAdv       = nullptr;

    TaskHandle_t  bleTaskHandle = nullptr;
    QueueHandle_t bleQueue      = nullptr;

    double   sensorValue = 0.0;
    uint16_t connIDs[MAX_CONNECTIONS];
    volatile int connCount = 0;

    enum BleCommand {
        BLE_START_SETUP,
        BLE_START_ADV,
        BLE_STOP_ADV
    };
}

// NimBLE ovverrides
class ServerCallbacks : public NimBLEServerCallbacks {
    void onConnect(NimBLEServer* server, NimBLEConnInfo& connInfo) override {
        uint16_t conn_id = connInfo.getConnHandle();
        if (connCount < MAX_CONNECTIONS) {
            connIDs[connCount++] = conn_id;
        }
        Serial.printf("Client connected, conn id: %u\n", conn_id);
        NimBLEDevice::startAdvertising();
    }

    void onDisconnect(NimBLEServer* server, NimBLEConnInfo& connInfo, int reason) override {
        uint16_t conn_id = connInfo.getConnHandle();
        for (int i = 0; i < connCount; i++) {
            if (connIDs[i] == conn_id) {
                for (int j = i; j < connCount - 1; j++) {
                    connIDs[j] = connIDs[j + 1];
                }
                connCount--;
                break;
            }
        }
        Serial.printf("Client disconnected, conn id: %u\n", conn_id);
    }
};

// task body
static void bleTask(void* parameter){
    NimBLEDevice::init(DEVICE_NAME);
    pServer = NimBLEDevice::createServer();
    pServer->setCallbacks(new ServerCallbacks()); //!!

    NimBLEService* pService = nullptr;
    BleCommand cmd;

    for(;;){
        if(xQueueReceive(bleQueue, &cmd, portMAX_DELAY) != pdTRUE) continue;

        switch(cmd){
            case BLE_START_SETUP:
                pService = pServer->createService(SERVICE_UUID);
                pChar = pService->createCharacteristic(
                    CHARACTERISTIC_UUID,
                    NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::INDICATE
                );
                pService->start();
                pAdv = NimBLEDevice::getAdvertising();
                pAdv->addServiceUUID(SERVICE_UUID);
                pAdv->enableScanResponse(false);
                break;
            
            case BLE_START_ADV:
                Serial.println("Received command BLE_START_ADV");
                NimBLEDevice::startAdvertising();
                pChar->setValue((uint8_t*)&sensorValue, sizeof(double));
                pChar->indicate();
                break;
            
            case BLE_STOP_ADV:
                Serial.println("Received command BLE_STOP_ADV");
                NimBLEDevice::stopAdvertising();
                break;
        }
    }
}

// public API
void ble_task_start() {
    bleQueue = xQueueCreate(5, sizeof(BleCommand));
    xTaskCreate(bleTask, "BLE Task", 4096, nullptr, 1, &bleTaskHandle);
}

void ble_task_setup_ble() {
    BleCommand c = BLE_START_SETUP;
    xQueueSend(bleQueue, &c, portMAX_DELAY);
    Serial.println("Setting up the BLE");
    delay(1);  // keep the existing breathing-room delay for now
}

void ble_task_start_advertising() {
    BleCommand c = BLE_START_ADV;
    xQueueSend(bleQueue, &c, portMAX_DELAY);
    Serial.println("Starting BLE advertisement");
    delay(1);
}

void ble_task_set_value(double v) {
    sensorValue = v;  
}

bool ble_task_has_clients() {
    return connCount > 0;
}

void ble_task_run_application_loop() {
    if (connCount > 0) {
        ble_task_set_value((double)esp_random());
        BleCommand c = BLE_START_ADV;
        xQueueSend(bleQueue, &c, portMAX_DELAY);
        delay(TX_BURST_MS);

        c = BLE_STOP_ADV;
        xQueueSend(bleQueue, &c, portMAX_DELAY);
        delay(IDLE_BETWEEN_MS);
    } else {
        delay(IDLE_POLL_MS);
    }
}