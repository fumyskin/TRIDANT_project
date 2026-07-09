# TRIDANT_project
Repository for microcontroller programming  repo of experimental setup of the multi-function Dielectric Resonator Antenna

**This README is still in progress**

We introduce the bluetooth-based telemetry and data measurements system for the Dielectric Resonator Antenna design proposed for the IEEE AP-S Antenna design contest. 
The simple design of the architeture aims to function as a didatic toolkit for understanding live the antenna patterns received by the antenna transmitter.

We suggest the following passages :
1) read the **INSTRUCTIONS.pdf** (not inerted yet) and instructions for building and setting up the demonstration setup hardware.
2) refer to the rest of this README for downloading the code setup.

---
 
## Repository layout
 
```
TRIDANT_project/
├── platformio.ini            # firmware build config (board, libs, flags)
├── src/
│   ├── main.cpp              # FreeRTOS task setup, entry point
│   └── tasks/
│       ├── ble_task.*        # NimBLE server, Sample notify
│       ├── bno_task.*        # BNO085 orientation → boresight vector
│       ├── sensor_task.*     # AD8317 ADC read
│       └── sample.h          # wire contract (byte-locked to protocol.py)
├── test/
│   └── protocol_test.cpp     # wire-format sanity checks
│
├── gui_app/
│   ├── tridant_gui.py        # live BLE GUI (matplotlib polar plots)
│   ├── capture_ble.py        # BLE → CSV logger (raw mV, re-calibratable)
│   ├── protocol.py           # Sample unpack + host-side calibration profiles
│   └── parameters.md         # per-band R_MIN/R_MAX and calibration notes
├── plotter_scripts/
│   ├── plotter.py            # offline log → polar pattern plots
│   └── interpolation_AD.py   # interpolation experiments
├── scripts/
│   └── logger.sh             # serial (USB) → band-split log files
│
├── logs/      logs_ble/      # captured sessions (serial / BLE)
└── plots/                    # rendered pattern figures
``` 
---
 
## Prerequisites
 
- **Firmware:** [PlatformIO](https://platformio.org/) (CLI or the VS Code
  extension). A CodeCell / ESP32-C6 board on a USB port (e.g. `/dev/ttyACM0`).
- **Host tooling:** Python 3.9+ and a working BLE adapter.

---

## Repository Installation

Clone the repository:
 
```bash
git clone https://github.com/fumyskin/TRIDANT_project.git
cd TRIDANT_project
```
 
The repo has two independent halves — set up whichever you need.
 
---

## INSTALLING THE TOOLCHAIN
Before cloning the code, it's important to setup the correct toolchain for the code to properly compilet

### Requirenments
```bash
pip install -r requirements.txt
```

### Firmware
```bash
# one-time: install PlatformIO Core (if not using the VS Code extension)
pip install platformio

pio run                    # build (auto-installs lib_deps the first time)
pio run -t upload          # flash to the board over USB
pio device monitor         # open serial @ 115200 to watch output

```

## INSTALLING THE REPO



### PLATFORMIO CAVEATS

## HOW TO USE THE SYSTEM



