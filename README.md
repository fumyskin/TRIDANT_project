### YPR Reading BLE Web GUI (Development Branch)

The **YPR_reading_BLE_web_GUI** branch implements a real-time telemetry system for monitoring the orientation of an experimental dielectric resonator antenna platform.

### System Overview

An ESP32-based **CodeCell** acquires inertial measurement unit (IMU) data and computes **Roll, Pitch, and Yaw (YPR)** values. These measurements are streamed via **Bluetooth Low Energy (BLE) notifications** to a host machine.

### Data Pipeline

The system is structured as a multi-stage communication chain:

**ESP32 CodeCell → BLE → Python Bridge → Secure WebSocket Server → HTTPS Web Interface**

### Python Bridge Layer

A Python application acts as an intermediary between hardware and the web interface. It:
- Connects to the ESP32 via BLE
- Parses incoming YPR data
- Converts telemetry into JSON format
- Broadcasts updates to connected WebSocket clients

### Web Interface

A browser-based dashboard subscribes to the WebSocket stream and provides:
- Real-time line charts for Roll, Pitch, and Yaw
- Numeric readouts of current orientation
- Connection status monitoring

### Deployment

The web server runs locally over **HTTPS using self-signed certificates** generated for Windows development environments. The system is intended for:
- Board testing
- Sensor validation
- Experimental antenna characterization