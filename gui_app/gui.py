"""
Live Antenna Pattern Plotter
Reads CSV lines from ESP32 serial port and plots a live 2D polar pattern.

Usage:
    pip install pyserial matplotlib numpy
    python antenna_pattern.py --port COM3          # Windows
    python antenna_pattern.py --port /dev/ttyUSB0  # Linux/Mac
    python antenna_pattern.py --port /dev/ttyUSB0 --baud 115200
"""

import argparse
import threading
import serial
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from collections import defaultdict

# ── CLI args ─────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Live 2D polar antenna pattern")
parser.add_argument("--port",  default="/dev/ttyUSB0", help="Serial port")
parser.add_argument("--baud",  type=int, default=115200)
parser.add_argument("--bin",   type=float, default=5.0,
                    help="Angular bin size in degrees (default 5°)")
args = parser.parse_args()

# ── Shared state (protected by a lock) ───────────────────────────────────────
lock    = threading.Lock()
# Maps azimuth_bin (deg) → list of P_dBm values received in that bin
buckets = defaultdict(list)   # raw accumulator
samples = 0                   # total samples received

def serial_reader():
    """Background thread: reads lines, parses CSV, fills buckets."""
    global samples
    try:
        ser = serial.Serial(args.port, args.baud, timeout=1)
        print(f"[serial] opened {args.port} @ {args.baud}")
    except serial.SerialException as e:
        print(f"[serial] ERROR: {e}")
        return

    while True:
        try:
            raw = ser.readline().decode("utf-8", errors="ignore").strip()
        except Exception:
            continue

        # Expected format: phi_deg,theta_deg,elev_deg,P_dBm,mv
        # Skip header / status lines
        parts = raw.split(",")
        if len(parts) != 5:
            continue
        try:
            phi_deg = float(parts[0])   # azimuth
            p_dbm   = float(parts[3])   # RF power
        except ValueError:
            continue

        # Snap to nearest bin
        bin_deg = round(phi_deg / args.bin) * args.bin
        bin_deg = bin_deg % 360.0

        with lock:
            buckets[bin_deg].append(p_dbm)
            samples += 1

# ── Start reader thread ───────────────────────────────────────────────────────
t = threading.Thread(target=serial_reader, daemon=True)
t.start()

# ── Matplotlib polar plot setup ───────────────────────────────────────────────
fig = plt.figure(figsize=(7, 7), facecolor="#0d1117")
ax  = fig.add_subplot(111, projection="polar", facecolor="#0d1117")

ax.set_theta_zero_location("N")   # 0° at top (North)
ax.set_theta_direction(-1)        # clockwise, like a compass
ax.tick_params(colors="#88a0b8")
ax.spines["polar"].set_color("#2a3a4a")
ax.yaxis.label.set_color("#88a0b8")
ax.grid(color="#1e2e3e", linestyle="--", linewidth=0.6)

# Dynamic r-axis will be set each frame
line, = ax.plot([], [], color="#00e5ff", linewidth=1.8, alpha=0.9)
fill  = ax.fill([], [], color="#00e5ff", alpha=0.12)

title = ax.set_title("Antenna Pattern (live)", color="#cde4f5",
                      pad=18, fontsize=13, fontweight="bold")
status_text = ax.text(0.5, -0.08, "waiting for data…",
                      transform=ax.transAxes, ha="center",
                      color="#88a0b8", fontsize=9)

def update(_frame):
    with lock:
        snap    = dict(buckets)
        n_samp  = samples

    if not snap:
        return line, *fill

    # Average dBm per bin, then build arrays sorted by angle
    angles_deg = sorted(snap.keys())
    powers_dbm = [np.mean(snap[a]) for a in angles_deg]

    # Close the loop for plotting
    angles_deg_c = angles_deg + [angles_deg[0]]
    powers_dbm_c = powers_dbm + [powers_dbm[0]]

    angles_rad = np.radians(angles_deg_c)

    # Normalise: shift so minimum = 0 for nice radial display
    p_arr  = np.array(powers_dbm_c)
    p_min  = p_arr.min()
    p_norm = p_arr - p_min          # all ≥ 0

    line.set_data(angles_rad, p_norm)

    # Rebuild fill patch
    fill[0].set_xy(np.column_stack([angles_rad, p_norm]))

    # Annotate r-axis with real dBm values
    r_max = p_norm.max() if p_norm.max() > 0 else 1
    ax.set_ylim(0, r_max * 1.1)
    ticks     = np.linspace(0, r_max, 5)
    tick_dbm  = ticks + p_min
    ax.set_yticks(ticks)
    ax.set_yticklabels([f"{v:.0f} dBm" for v in tick_dbm],
                       color="#88a0b8", fontsize=7)

    status_text.set_text(
        f"{n_samp} samples  ·  {len(snap)} bins  ·  "
        f"range {p_arr.min():.1f}…{p_arr.max():.1f} dBm"
    )
    return line, *fill

ani = animation.FuncAnimation(fig, update, interval=200, blit=False)

plt.tight_layout()
plt.show()