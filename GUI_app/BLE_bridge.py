import asyncio
import json
import ssl  
import websockets
from bleak import BleakScanner, BleakClient

SERVICE_UUID        = "97dcc426-d11e-476e-95e2-79f064720640"
CHARACTERISTIC_UUID = "aae3a4f0-8e88-4bd0-8047-c6a8c2312a3d"

connected_clients = set()

async def notify_handler(sender, data):
    try:
        text = data.decode("utf-8").strip()
        roll, pitch, yaw = [float(x) for x in text.split(",")]
        message = json.dumps({"roll": roll, "pitch": pitch, "yaw": yaw})
        print(f"[BLE] Roll: {roll:.2f}  Pitch: {pitch:.2f}  Yaw: {yaw:.2f}")
        for ws in list(connected_clients):
            try:
                await ws.send(message)
            except:
                connected_clients.discard(ws)
    except Exception as e:
        print(f"[ERROR] Failed to parse BLE data: {data!r} — {e}")

async def ws_handler(websocket):
    connected_clients.add(websocket)
    print(f"[WS] Client connected — total: {len(connected_clients)}")
    try:
        await websocket.wait_closed()
    finally:
        connected_clients.discard(websocket)
        print(f"[WS] Client disconnected — total: {len(connected_clients)}")

async def ble_task():
    print("[BLE] Scanning for ESP32_BLE...")
    device = await BleakScanner.find_device_by_name("ESP32_BLE", timeout=10.0)
    if not device:
        print("[BLE] ESP32_BLE not found!")
        return
    print(f"[BLE] Found device: {device.name} ({device.address})")
    async with BleakClient(device) as client:
        print(f"[BLE] Connected to {device.name}")
        await client.start_notify(CHARACTERISTIC_UUID, notify_handler)
        await asyncio.Future()  # run forever

async def main():
    # 💡 Create the standard TLS context
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(certfile='cert.pem', keyfile='key.pem')

    # ⚠️ FIXES FOR BROWSER WEBSOCKET HANDSHAKE REJECTIONS:
    # 1. Disable ALPN requirements so browsers like Firefox/Chrome don't fail handshakes
    ssl_context.set_alpn_protocols([]) 
    
    # 2. Tell Python not to worry about strict hostname verification for local loopback IPs
    ssl_context.check_hostname = False 

    # Bind the server specifically to localhost loopback
    ws_server = await websockets.serve(
        ws_handler, 
        "127.0.0.1", 
        8765, 
        ssl=ssl_context
    )
    
    print("[WS] Secure WebSocket server running on wss://127.0.0.1:8765")
    await asyncio.gather(ws_server.serve_forever(), ble_task())

if __name__ == "__main__":
    asyncio.run(main())