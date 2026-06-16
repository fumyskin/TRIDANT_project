import asyncio
import json
import websockets
from bleak import BleakScanner, BleakClient

SERVICE_UUID        = "97dcc426-d11e-476e-95e2-79f064720640"
CHARACTERISTIC_UUID = "aae3a4f0-8e88-4bd0-8047-c6a8c2312a3d"

connected_clients = set()

async def notify_handler(sender, data):
    value = float(int.from_bytes(data, byteorder='little', signed=False))
    message = json.dumps({"value": value})
    print(f"ESP32 value: {value}")
    for ws in list(connected_clients):
        try:
            await ws.send(message)
        except:
            connected_clients.discard(ws)

async def ws_handler(websocket):
    connected_clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        connected_clients.discard(websocket)

async def ble_task():
    print("Scanning for ESP32_BLE...")
    device = await BleakScanner.find_device_by_name("ESP32_BLE")
    if not device:
        print("ESP32_BLE not found!")
        return

    async with BleakClient(device) as client:
        print(f"Connected to {device.name}")
        await client.start_notify(CHARACTERISTIC_UUID, notify_handler)
        await asyncio.Future()  # run forever

async def main():
    ws_server = await websockets.serve(ws_handler, "localhost", 8765)
    print("WebSocket server on ws://localhost:8765")
    await asyncio.gather(ws_server.serve_forever(), ble_task())

asyncio.run(main())