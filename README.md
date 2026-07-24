# TRIDANT project
 
**T**wo-band **R**adiation-pattern **I**nstrument for **D**irectional **ANT**enna
characterization — a portable system that measures and visualizes 2D antenna
radiation patterns (azimuth and elevation cuts) in two bands:
 
- **GNSS L1** — ~1.575 GHz
- **V2X** — ~5.9 GHz
A hand-aimed sensor head streams raw RF power and orientation over Bluetooth Low
Energy to a host computer, which calibrates the samples, bins them by angle, and
draws live polar radiation-pattern plots.
 
> Built for the IEEE AP-S Student Design Contest.
 
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
├── 3d_models/                # printing models for the components used in the demo
│
├── logs/      logs_ble/      # captured sessions (serial / BLE)
└── plots/                    # rendered pattern figures
``` 
---
 
## How it works
 
The firmware stays deliberately thin: it emits **raw sensor values only** — the
AD8317 detector output in millivolts plus a quaternion-derived boresight
orientation. All calibration, coordinate transformation, and visualization live
**host-side**, in Python. This keeps captured logs re-calibratable after the
fact and means changing bands never requires reflashing.
 
```
  ┌─────────────────────────┐        BLE          ┌──────────────────────────┐
  │  ESP32-C6 (CodeCell)    │   15-byte Sample    │  Host (Python)           │
  │                         │  ───────────────▶  │                          │
  │  BNO085 IMU  → orient.  │  phi, theta, elev,  │  calibrate mV → dBm      │
  │  AD8317 LPD  → mV       │  mv, cal            │  bin by angle → polar    │
  └─────────────────────────┘                     │ live plot / CSV / offline│
                                                  └──────────────────────────┘
```
The wire format is a single source of truth shared across the language boundary (`src/tasks/sample.h` on the firmware side, `gui_app/protocol.py` on the host side), verified with `static_assert` in C++ and `struct.calcsize` in Python:
 
```cpp
struct Sample { float phi, theta, elev;  uint16_t mv;  uint8_t cal; }  // 15 bytes
protocol.SAMPLE_FMT = "<fffHB"                                          // 15 bytes
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
 
---

The repo has two independent halves — set up whichever you need.
 
### 1. Firmware (PlatformIO)
 
`platformio.ini` pins the board (`esp32-c6-devkitm-1`), the pioarduino
ESP32 platform, and the required libraries (NimBLE-Arduino, CodeCell), so the
dependencies install themselves on the first build.
 
```bash
pip install platformio          # skip if you use the VS Code extension
 
pio run                         # build (downloads libs on first run)
pio run -t upload               # flash over USB
pio device monitor              # serial monitor @ 115200
```

### 2. Host tooling (Python)
 
Use a virtual environment so the dependencies stay isolated:
 
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
 
pip install -r requirements.txt
```
 
---
 
## Usage
### Live pattern GUI
 
Real-time polar plots over BLE. Scans for the sensor head, connects, and draws
azimuth and elevation cuts as you sweep.
 
```bash
python gui_app/tridant_gui.py
```
 
Keys: `c` clears the accumulated pattern, `q` quits.
 

### Capture raw samples over BLE
 
Logs raw wire values (mV, not dBm) to CSV so the session stays re-calibratable
and re-plottable later.
 
```bash
python gui_app/capture_ble.py                      # timestamped CSV
python gui_app/capture_ble.py -o dipole_az.csv     # explicit file
python gui_app/capture_ble.py --dbm --band GNSS    # add dBm column + live peak
```

### Capture over serial (USB)
 
Logs the CodeCell's serial output into band-specific files under `logs/`.
Run it from inside `scripts/` (the default log directory is `../logs`):
 
```bash
cd scripts
./logger.sh GNSS                 # fallback band = GNSS
./logger.sh V2X /dev/ttyACM0     # explicit port
```
 
### Plot a captured log offline
 
```bash
python plotter_scripts/plotter.py logs/GNSS.log --normalize
python plotter_scripts/plotter.py logs/GNSS.log logs/V2X.log
```
 
---
## Calibration & configuration
 
Calibration is host-owned. Per-band detector profiles (slope in mV/dB and
intercept in mV) live in `gui_app/protocol.py`:
 
```python
PROFILES = {
    "GNSS_1G575": {"slope_mv_per_db": -25.0, "intercept_mv": 510.0},
    "V2X_5G9":    {"slope_mv_per_db": -25.0, "intercept_mv": 608.0},
}
```
 
The conversion is `P_dBm = (mv − intercept_mv) / slope_mv_per_db`. For
**normalized** pattern shape, intercept errors cancel and only the slope
matters; a **fixed absolute** radial axis additionally needs a calibrated
intercept and a known peak power.
 
To set the radial limits (`R_MIN` / `R_MAX`) for a band, find the peak by
sweeping the main beam with `capture_ble.py --dbm --band <BAND>` and reading the
live `peak` value. See **`gui_app/parameters.md`** for the full per-band
procedure and the current tuning values.
 
---
 
## Wire protocol
 
| Field   | Type      | Meaning                              |
|---------|-----------|--------------------------------------|
| `phi`   | float32   | azimuth (deg)                        |
| `theta` | float32   | polar/elevation angle (deg)          |
| `elev`  | float32   | elevation (deg)                      |
| `mv`    | uint16    | AD8317 detector output (millivolts)  |
| `cal`   | uint8     | IMU calibration status               |
 
Packed little-endian as `"<fffHB"` = **15 bytes**. Any change here must be made
in both `src/tasks/sample.h` and `gui_app/protocol.py`, or the two sides will
disagree.
 
---
 
## License
