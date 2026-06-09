/*
   The design of creating the BLE server is:
   1. Create a BLE Server
   2. Create a BLE Service
   3. Create a BLE Characteristic on the Service
   4. Create a BLE Descriptor on the characteristic
   5. Start the service.
   6. Start advertising.
*/

#include <Arduino.h>
//#include <CodeCell.h>
#include <NimBLEDevice.h>
#include <esp_random.h>

#define MAX_CONNECTIONS 1
#define SERVICE_UUID        "97dcc426-d11e-476e-95e2-79f064720640" // Use the website https://www.uuidgenerator.net/ to generate UUIDs
#define CHARACTERISTIC_UUID "aae3a4f0-8e88-4bd0-8047-c6a8c2312a3d"

NimBLEServer *pServer = NULL;
NimBLECharacteristic *pCharacteristic = NULL;
NimBLEAdvertising *pAdvertising = NULL;

TaskHandle_t bleTaskHandle;
QueueHandle_t bleQueue;  //mailbox on RAM
double sensorValue = 0;
uint16_t connIDs[MAX_CONNECTIONS];
int connCount = 0;

enum BleCommand { // commands used by the main core to control the ble task
  BLE_START_SETUP,
  BLE_START_ADV,
  BLE_STOP_ADV
};
BleCommand setup_cmd, loop_cmd;

class ServerCallbacks: 
public NimBLEServerCallbacks{
  void onConnect(NimBLEServer* server, NimBLEConnInfo& connInfo) override {
    uint16_t conn_id = connInfo.getConnHandle();
    if (conn_id < MAX_CONNECTIONS){
      connIDs[connCount++] = conn_id;
    }
    Serial.print("Client connected, connection id: ");
    Serial.println(conn_id);
    NimBLEDevice::startAdvertising();
  }

  void onDisconnect(NimBLEServer* server, NimBLEConnInfo& connInfo, int reason) override{
    uint16_t conn_id = connInfo.getConnHandle();
    for(int i = 0; i < connCount; i++){
      if(connIDs[i] == conn_id){
        for(int j = i; j < connCount - 1; j++){
          connIDs[j] = connIDs[j + 1];
        }
        connCount--;
        break;
      }
    }
    Serial.print("Client disconnected, connection id: ");
    Serial.println(conn_id);
  }
};

void disconnectAllClients() {
  for (int i = 0; i < connCount; i++) {
    pServer->disconnect(connIDs[i]);
  }
  Serial.println("All clients disconnected");
  connCount = 0;
}

// restart from here
void bleTask(void *parameter) {
  BleCommand cmd;

  NimBLEDevice::init("ESP32_BLE");
  pServer = NimBLEDevice::createServer();
  pServer->setCallbacks(new ServerCallbacks());

  NimBLEService *pService = NULL;
  
  for (;;) {
    if (xQueueReceive(bleQueue, &cmd, portMAX_DELAY)) {   // wait for commands
      switch (cmd) {
        case BLE_START_SETUP:
          pService = pServer->createService(SERVICE_UUID);
          pCharacteristic = pService->createCharacteristic(
            CHARACTERISTIC_UUID,
            NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::INDICATE // set indicate for ACKs (tcp-like transmission)
          );

          pService->start();

          pAdvertising = NimBLEDevice::getAdvertising();
          pAdvertising->addServiceUUID(SERVICE_UUID);
          pAdvertising->enableScanResponse(false);
          break;
          
        case BLE_START_ADV:
          Serial.println("Received command BLE_START_ADV");
          NimBLEDevice::startAdvertising(); // make the ESP32 endpoint visible to clients for BLE connections
          pCharacteristic->setValue((uint8_t*)&sensorValue, sizeof(double));  // need to check if js decodes this with same LSB order
          pCharacteristic->indicate();
          break;

        case BLE_STOP_ADV:
          Serial.println("Received command BLE_STOP_ADV");
          NimBLEDevice::stopAdvertising(); // stop using the antenna to keep connections alive
          //disconnectAllClients(); // got to remove active connections to not use the antenna
          break;

        default:
          Serial.print("Received unrecognized command: ");
          Serial.println(cmd);
          break;
      }
    }
  }
}



void setup() {
  Serial.begin(115200);
  delay(500);  // give some breath to USB CDC 
  

  bleQueue = xQueueCreate(5, sizeof(BleCommand)); // max 5 items in the queue (should not really reach even two but who knows)
  xTaskCreate(bleTask, "BLE Task", 4096, NULL, 1, &bleTaskHandle);

  setup_cmd = BLE_START_SETUP;
  xQueueSend(bleQueue, &setup_cmd, portMAX_DELAY);
  Serial.println("Setting up the BLE");
  delay(1);
  
  setup_cmd = BLE_START_ADV;
  xQueueSend(bleQueue, &setup_cmd, portMAX_DELAY);
  Serial.println("Starting BLE advertisement");
  delay(1);
  
}

// loop() starts polling for new connections
void loop() {
  if (connCount) {
    sensorValue = (double)esp_random();  // shared data access here before sending start_adv, act as semaphore
    loop_cmd = BLE_START_ADV;
    xQueueSend(bleQueue, &loop_cmd, portMAX_DELAY);  // bleQueue is the mailbox; loop() sends loop_cmd to bleQueue for BLETask to read and act upon it

    delay(200); // wait for data transmission
    loop_cmd = BLE_STOP_ADV;
    xQueueSend(bleQueue, &loop_cmd, portMAX_DELAY);

    delay(5000);
  }else{
    delay(100); // no busy loop when idle
  }
}