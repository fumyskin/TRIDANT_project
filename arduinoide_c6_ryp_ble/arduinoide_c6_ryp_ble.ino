#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>  // Crucial for standard BLE notifications
#include <CodeCell.h>

#define MAX_CONNECTIONS     1
#define SERVICE_UUID        "97dcc426-d11e-476e-95e2-79f064720640"
#define CHARACTERISTIC_UUID "aae3a4f0-8e88-4bd0-8047-c6a8c2312a3d"
#define DEVICE_NAME         "ESP32_BLE"

CodeCell myCodeCell;

BLEServer* pServer         = nullptr;
BLECharacteristic* pCharacteristic = nullptr;
bool               deviceConnected = false;
bool               oldDeviceConnected = false;

// --- Classical BLE Server Callbacks ---
class ServerCallbacks : public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) override {
        deviceConnected = true;
        Serial.println("[BLE] Client connected");
    }

    void onDisconnect(BLEServer* pServer) override {
        deviceConnected = false;
        Serial.println("[BLE] Client disconnected");
    }
};

void setup() {
    Serial.begin(115200);
    while (!Serial) delay(100);  // Wait for serial on USB-CDC
    Serial.println("\n[BOOT] Starting up...");

    // Init CodeCell
    Serial.println("[BOOT] Initializing CodeCell (MOTION_ROTATION)...");
    delay(100);
    myCodeCell.Init(MOTION_ROTATION + MOTION_STATE);
    delay(100);
    Serial.println("[BOOT] CodeCell initialized");

    // Init Classical BLE
    Serial.printf("[BLE] Initializing standard BLE as \"%s\"...\n", DEVICE_NAME);
    BLEDevice::init(DEVICE_NAME);

    pServer = BLEDevice::createServer();
    pServer->setCallbacks(new ServerCallbacks());
    Serial.println("[BLE] Server created");

    BLEService* pService = pServer->createService(SERVICE_UUID);
    Serial.printf("[BLE] Service created — UUID: %s\n", SERVICE_UUID);

    // Create characteristic with read and notify properties
    pCharacteristic = pService->createCharacteristic(
        CHARACTERISTIC_UUID,
        BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY
    );
    
    // ⚠️ IMPORTANT: Standard BLE needs this descriptor explicitly attached 
    // to allow apps like nRF Connect to subscribe to notifications.
    pCharacteristic->addDescriptor(new BLE2902());
    
    Serial.printf("[BLE] Characteristic created — UUID: %s (READ | NOTIFY)\n",
                  CHARACTERISTIC_UUID);

    // Start the service
    pService->start();
    Serial.println("[BLE] Service started");

    // Configure and start advertising
    BLEAdvertising* pAdvertising = BLEDevice::getAdvertising();
    pAdvertising->addServiceUUID(SERVICE_UUID);
    pAdvertising->setScanResponse(true);
    pAdvertising->setMinPreferred(0x06);  // Helps with iOS connection pairing issues
    pAdvertising->setMinPreferred(0x12);
    
    BLEDevice::startAdvertising();
    Serial.println("[BLE] Advertising started — waiting for client...\n");
}

void loop() {
    // Run at 20 Hz (~50ms intervals) completely non-blocking
    if (myCodeCell.Run(20)) {
        float roll = 0.0f, pitch = 0.0f, yaw = 0.0f;
        
        // Fetch fresh calculation data from CodeCell
        myCodeCell.Motion_RotationRead(roll, pitch, yaw);

        char payload[48];
        snprintf(payload, sizeof(payload), "%.2f,%.2f,%.2f", roll, pitch, yaw);

        pCharacteristic->setValue(payload);

        if (deviceConnected) {
            pCharacteristic->notify();
            Serial.printf("[IMU] Roll: %7.2f  Pitch: %7.2f  Yaw: %7.2f  →  BLE notified\n",
                          roll, pitch, yaw);
        } else {
            Serial.printf("[IMU] Roll: %7.2f  Pitch: %7.2f  Yaw: %7.2f  (no client)\n",
                          roll, pitch, yaw);
        }
    }
    
    // Housekeeping: Handle clean disconnection/re-advertising tracking
    if (!deviceConnected && oldDeviceConnected) {
        delay(500); // Give the bluetooth stack time to breathe
        pServer->startAdvertising(); // Restart advertising so new devices can see it
        Serial.println("[BLE] Connection lost. Restarted advertising.");
        oldDeviceConnected = deviceConnected;
    }
    
    if (deviceConnected && !oldDeviceConnected) {
        // Device connected housekeeping
        oldDeviceConnected = deviceConnected;
    }
}