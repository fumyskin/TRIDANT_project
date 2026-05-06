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
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <esp_gatts_api.h>
#include <esp_random.h>

#define MAX_CONNECTIONS 3
#define SERVICE_UUID        "97dcc426-d11e-476e-95e2-79f064720640" // Use the website https://www.uuidgenerator.net/ to generate UUIDs
#define CHARACTERISTIC_UUID "aae3a4f0-8e88-4bd0-8047-c6a8c2312a3d"
BLEServer *pServer = NULL;
BLECharacteristic *pCharacteristic = NULL;
BLE2902 *descriptor_2902 = NULL;

TaskHandle_t bleTaskHandle;
QueueHandle_t bleQueue;
double sensorValue = 0;
uint16_t connIDs[MAX_CONNECTIONS];
int connCount = 0;


enum BleCommand { // commands used by the main core to control the ble task
  BLE_START_SETUP,
  BLE_START_ADV,
  BLE_STOP_ADV
};
BleCommand setup_cmd, loop_cmd;

void gattsEventHandler(   // lower level API to get the connection IDs to be able to remove each single clients
  esp_gatts_cb_event_t event,
  esp_gatt_if_t gatts_if,
  esp_ble_gatts_cb_param_t *param
) {
  switch (event) {
    case ESP_GATTS_CONNECT_EVT: {
      uint16_t conn_id = param->connect.conn_id;
      if (connCount < MAX_CONNECTIONS) {
        connIDs[connCount++] = conn_id;
      }
      Serial.print("Client connected, connection id: ");
      Serial.println(conn_id);
      break;
    }

    case ESP_GATTS_DISCONNECT_EVT: {
      uint16_t conn_id = param->disconnect.conn_id; // get the disconnected client reference
      for (int i = 0; i < connCount; i++) {
        if (connIDs[i] == conn_id) {
          for (int j = i; j < connCount - 1; j++) {
            connIDs[j] = connIDs[j + 1];          // remove it from the list of connections (overwritten by shifting to the left the ids)
          }
          connCount--;
          break;
        }
      }

      Serial.print("Client disconnected, connection id: ");
      Serial.println(conn_id);
      break;
    }

    default:
      break;
  }
}
void disconnectAllClients() {
  for (int i = 0; i < connCount; i++) {
    pServer->disconnect(connIDs[i]);
  }
  Serial.println("All clients disconnected");
  connCount = 0;
}

void bleTask(void *parameter) {
  BleCommand cmd;
  BLEDevice::init("ESP32_BLE");
  pServer = BLEDevice::createServer();
  esp_ble_gatts_register_callback(gattsEventHandler);
  BLEService *pService;
  BLEAdvertising *pAdvertising;
  
  for (;;) {
    if (xQueueReceive(bleQueue, &cmd, portMAX_DELAY)) {   // wait for commands
      switch (cmd) {
        case BLE_START_SETUP:
          pService = pServer->createService(SERVICE_UUID);
          pCharacteristic = pService->createCharacteristic(
            CHARACTERISTIC_UUID,
            BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_INDICATE // set indicate for ACKs (tcp-like transmission)
          );

          pCharacteristic->addDescriptor(new BLE2902());  // BLE object 0x2902 needed for clients to enable indications
          pService->start();

          pAdvertising = BLEDevice::getAdvertising();
          pAdvertising->addServiceUUID(SERVICE_UUID);
          pAdvertising->setScanResponse(false);
          pAdvertising->setMinPreferred(0x0);  // 0x0 to not post connection preferences (MinPreferred used to specify connection intervals and latency)
          break;
        case BLE_START_ADV:
          Serial.println("Received command BLE_START_ADV");
          BLEDevice::startAdvertising(); // make the ESP32 endpoint visible to clients for BLE connections
          pCharacteristic->setValue((uint8_t*)&sensorValue, sizeof(double));  // need to check if js decodes this with same LSB order
          pCharacteristic->notify();
          break;

        case BLE_STOP_ADV:
          Serial.println("Received command BLE_STOP_ADV");
          pAdvertising->stop(); // stop sending notifications data
          disconnectAllClients(); // got to remove active connections to not use the antenna
          BLEDevice::stopAdvertising(); // stop using the antenna to keep connections alive
          break;
        default:
          Serial.print("Received unrecognized command: ");
          Serial.println(cmd);
          break;
      }
    }else{
      vTaskDelay(pdMS_TO_TICKS(2));  // wait before checking the queue again
    }
  }
}



void setup() {
  Serial.begin(115200);
  

  bleQueue = xQueueCreate(5, sizeof(BleCommand)); // max 5 items in the queue (should not really reach even two but who knows)
  xTaskCreate(
    bleTask,
    "BLE Task",
    4096,
    NULL,
    1,
    &bleTaskHandle
  );

  setup_cmd = BLE_START_SETUP;
  xQueueSend(bleQueue, &setup_cmd, portMAX_DELAY);
  Serial.println("Setting up the BLE");
  delay(1);
  
  setup_cmd = BLE_START_ADV;
  xQueueSend(bleQueue, &setup_cmd, portMAX_DELAY);
  Serial.println("Starting BLE advertisement");
  delay(1);
  
}

void loop() {
  if (connCount) {
    sensorValue = (double)esp_random();  // shared data access here before sending start_adv, act as semaphore
    loop_cmd = BLE_START_ADV;
    xQueueSend(bleQueue, &loop_cmd, portMAX_DELAY);

    delay(200); // wait for data transmission
    loop_cmd = BLE_STOP_ADV;
    xQueueSend(bleQueue, &loop_cmd, portMAX_DELAY);

    delay(5000);
  }
}