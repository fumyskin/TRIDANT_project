#include "ble_task.h"
#include <Arduino.h>
#include <NimBLEDevice.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>

#define MAX_CONNECTIONS 1
#define SERVICE_UUID        "97dcc426-d11e-476e-95e2-79f064720640"
#define CHARACTERISTIC_UUID "aae3a4f0-8e88-4bd0-8047-c6a8c2312a3d"
#define DEVICE_NAME         "TRIDANT"   // was "ESP32_BLE" — scan for this now

namespace {
    NimBLEServer*         pServer = nullptr;
    NimBLECharacteristic* pChar   = nullptr;
    NimBLEAdvertising*    pAdv     = nullptr;

    TaskHandle_t  bleTaskHandle = nullptr;
    QueueHandle_t bleQueue      = nullptr;

    uint16_t connIDs[MAX_CONNECTIONS];
    volatile int connCount = 0;

    enum BleCommand : uint8_t {
        BLE_START_SETUP,
        BLE_START_ADV,
        BLE_STOP_ADV,
        BLE_TX
    };

    // One message type flows through the queue. `sample` is meaningful
    // only for BLE_TX; lifecycle commands ignore it.
    struct BleMsg {
        BleCommand cmd;
        Sample     sample;
    };
}

class ServerCallbacks : public NimBLEServerCallbacks {
    void onConnect(NimBLEServer* server, NimBLEConnInfo& connInfo) override {
        uint16_t conn_id = connInfo.getConnHandle();
        if (connCount < MAX_CONNECTIONS) connIDs[connCount++] = conn_id;
        Serial.printf("Client connected, conn id: %u\n", conn_id);
        // No re-advertise here: single slot stays quiet once connected.
    }

    void onDisconnect(NimBLEServer* server, NimBLEConnInfo& connInfo, int reason) override {
        uint16_t conn_id = connInfo.getConnHandle();
        for (int i = 0; i < connCount; i++) {
            if (connIDs[i] == conn_id) {
                for (int j = i; j < connCount - 1; j++) connIDs[j] = connIDs[j + 1];
                connCount--;
                break;
            }
        }
        Serial.printf("Client disconnected (reason %d), conn id: %u\n", reason, conn_id);
        NimBLEDevice::startAdvertising();   // allow reconnect between sweeps
    }
};

static void bleTask(void* parameter) {
    NimBLEDevice::init(DEVICE_NAME);
    pServer = NimBLEDevice::createServer();
    pServer->setCallbacks(new ServerCallbacks());

    NimBLEService* pService = nullptr;
    BleMsg msg;

    for (;;) {
        if (xQueueReceive(bleQueue, &msg, portMAX_DELAY) != pdTRUE) continue;

        switch (msg.cmd) {
            case BLE_START_SETUP:
                pService = pServer->createService(SERVICE_UUID);
                pChar = pService->createCharacteristic(
                    CHARACTERISTIC_UUID,
                    NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY
                );
                pService->start();
                pAdv = NimBLEDevice::getAdvertising();
                pAdv->addServiceUUID(SERVICE_UUID);
                pAdv->enableScanResponse(false);
                break;

            case BLE_START_ADV:
                Serial.println("BLE_START_ADV");
                NimBLEDevice::startAdvertising();
                break;

            case BLE_STOP_ADV:
                Serial.println("BLE_STOP_ADV");
                NimBLEDevice::stopAdvertising();
                break;

            case BLE_TX:
                if (pChar && connCount > 0) {
                    pChar->setValue((uint8_t*)&msg.sample, sizeof(Sample));
                    pChar->notify();
                }
                break;
        }
    }
}

// ---- public API ----
void ble_task_start() {
    bleQueue = xQueueCreate(8, sizeof(BleMsg));
    xTaskCreate(bleTask, "BLE Task", 4096, nullptr, 1, &bleTaskHandle);
}

void ble_task_setup_ble() {
    BleMsg m{ BLE_START_SETUP, {} };
    xQueueSend(bleQueue, &m, portMAX_DELAY);
    Serial.println("Setting up the BLE");
    delay(1);
}

void ble_task_start_advertising() {
    BleMsg m{ BLE_START_ADV, {} };
    xQueueSend(bleQueue, &m, portMAX_DELAY);
    Serial.println("Starting BLE advertisement");
    delay(1);
}

void ble_task_send_sample(const Sample& s) {
    BleMsg m{ BLE_TX, s };
    // Non-blocking: drop on backpressure rather than stall the 10 Hz loop.
    xQueueSend(bleQueue, &m, 0);
}

bool ble_task_has_clients() { return connCount > 0; }