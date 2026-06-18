"""
Live Antenna Pattern Plotter
Reads CSV lines from ESP32 serial port and plots two live 2D polar cuts
side by side: the azimuth pattern (binned on phi) and the elevation pattern
(binned on elev), like standard antenna-pattern graphs.

Usage:
    pip install pyserial matplotlib numpy
    python antenna_pattern.py --port COM3            # Windows
    python antenna_pattern.py --port /dev/ttyUSB0    # Linux/Mac
    python antenna_pattern.py --port /dev/ttyUSB0 --baud 115200
    python antenna_pattern.py --port /dev/ttyUSB0 --dyn-range 30 --bin 5
"""

import argparse
import threading
from collections import deque

import serial
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# ── CLI args ─────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Live 2D polar antenna pattern")
parser.add_argument("--port",  default="/dev/ttyUSB0", help="Serial port")
parser.add_argument("--baud",  type=int, default=115200)
parser.add_argument("--bin",   type=float, default=5.0,
                    help="Angular bin size in degrees (default 5°)")
parser.add_argument("--dyn-range", type=float, default=40.0,
                    help="Radial dynamic range in dB below peak (default 40)")
parser.add_argument("--min-samples", type=int, default=3,
                    help="Minimum samples per bin before plotting that bin")
parser.add_argument("--window", type=int, default=20,
                    help="Rolling-mean window per bin (most-recent N samples)")
parser.add_argument("--warmup", type=int, default=10,
                    help="Discard the first N valid CSV lines after open")
parser.add_argument("--dbm-min", type=float, default=-70.0,
                    help="Reject samples weaker than this (dBm)")
parser.add_argument("--dbm-max", type=float, default=10.0,
                    help="Reject samples stronger than this (dBm)")
args = parser.parse_args()

# Number of angular bins covering 0..360
NBINS    = int(round(360.0 / args.bin))
BIN_DEGS = np.arange(NBINS) * args.bin

# ── Shared state (protected by a lock) ───────────────────────────────────────
lock    = threading.Lock()
# One bounded deque per bin → rolling window of the most recent samples.
# Two parallel sets of buckets: one keyed by azimuth bin, one by elevation bin.
buckets_az = {a: deque(maxlen=args.window) for a in BIN_DEGS}
buckets_el = {a: deque(maxlen=args.window) for a in BIN_DEGS}
samples = 0   # total samples accepted (shared: each goes into both planes)


def snap_key(angle_deg):
    """Snap an angle to the nearest known bin center key in BIN_DEGS."""
    bin_deg = (round(angle_deg / args.bin) * args.bin) % 360.0
    return BIN_DEGS[int(round(bin_deg / args.bin)) % NBINS]


def serial_reader():
    """Background thread: reads lines, parses CSV, fills both bin sets."""
    global samples
    try:
        ser = serial.Serial(args.port, args.baud, timeout=1)
        print(f"[serial] opened {args.port} @ {args.baud}")
    except serial.SerialException as e:
        print(f"[serial] ERROR: {e}")
        return

    warmup_remaining = args.warmup

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
            phi_deg  = float(parts[0])   # azimuth
            elev_deg = float(parts[2])   # elevation
            p_dbm    = float(parts[3])   # RF power
        except ValueError:
            continue

        # Reject physically implausible readings (boot-time mv=0 gives +80 dBm,
        # detector saturation at the low end gives big positive values too)
        if not (args.dbm_min <= p_dbm <= args.dbm_max):
            continue

        # Discard the first few valid lines after opening the port — covers
        # any residual boot-time garbage and lets sensors settle
        if warmup_remaining > 0:
            warmup_remaining -= 1
            continue

        with lock:
            # Same sample lands in both planes, keyed by its own angle
            buckets_az[snap_key(phi_deg)].append(p_dbm)
            buckets_el[snap_key(elev_deg)].append(p_dbm)
            samples += 1


# ── Start reader thread ───────────────────────────────────────────────────────
t = threading.Thread(target=serial_reader, daemon=True)
t.start()

# ── Matplotlib: two polar subplots side by side ───────────────────────────────
DYN = args.dyn_range
fig = plt.figure(figsize=(13, 7), facecolor="#0d1117")


def make_polar_axis(pos, title):
    """Build and style one polar cut; return its mutable artists + ticks."""
    ax = fig.add_subplot(pos, projection="polar", facecolor="#0d1117")
    ax.set_theta_zero_location("N")   # 0° at top
    ax.set_theta_direction(-1)        # clockwise, like a compass
    ax.tick_params(colors="#88a0b8")
    ax.spines["polar"].set_color("#2a3a4a")
    ax.yaxis.label.set_color("#88a0b8")
    ax.grid(color="#1e2e3e", linestyle="--", linewidth=0.6)

    # Fixed radial axis: 0 at center = (peak - dyn_range), outer rim = peak
    ax.set_ylim(0, DYN)
    r_ticks = np.linspace(0, DYN, 5)
    ax.set_yticks(r_ticks)
    # Tick labels are updated each frame to show actual dBm values

    line, = ax.plot([], [], color="#00e5ff", linewidth=1.8, alpha=0.9)
    fill_patch, = ax.fill([0], [0], color="#00e5ff", alpha=0.12)

    ax.set_title(title, color="#cde4f5", pad=18, fontsize=12, fontweight="bold")
    status_text = ax.text(0.5, -0.10, "waiting for data…",
                          transform=ax.transAxes, ha="center",
                          color="#88a0b8", fontsize=9)
    return {"ax": ax, "line": line, "fill": fill_patch,
            "status": status_text, "r_ticks": r_ticks}


plot_az = make_polar_axis(121, "Azimuth cut (φ)")
plot_el = make_polar_axis(122, "Elevation cut (elev)")

suptitle = fig.suptitle("Antenna Pattern (live)", color="#cde4f5",
                        fontsize=14, fontweight="bold")


def compute_means(buckets):
    """Mean dBm per bin, or NaN if the bin lacks enough samples."""
    return np.array([
        np.mean(buckets[a]) if len(buckets[a]) >= args.min_samples else np.nan
        for a in BIN_DEGS
    ])


def render_plot(p, means):
    """Draw one cut from its per-bin means. Each cut normalises to its own peak."""
    ax = p["ax"]
    line = p["line"]
    fill_patch = p["fill"]
    status_text = p["status"]
    r_ticks = p["r_ticks"]

    n_filled = int(np.sum(~np.isnan(means)))
    if n_filled == 0:
        line.set_data([], [])
        fill_patch.set_xy(np.zeros((1, 2)))
        status_text.set_text("no bins ready yet")
        return

    # Peak is the strongest mean across all populated bins
    p_peak = np.nanmax(means)
    p_min  = np.nanmin(means)

    # Map dBm → radial position: peak sits at outer rim (=DYN),
    # peak − DYN dB sits at center (=0). NaN bins stay NaN so the
    # line breaks across gaps instead of bridging them with chords.
    r = means - p_peak + DYN
    r = np.where(np.isnan(r), np.nan, np.clip(r, 0, DYN))

    # Close the loop ONLY if the wrap-around bin (0°) is itself populated;
    # otherwise leave it open so we don't draw a chord across the gap.
    angles_deg = np.concatenate([BIN_DEGS, [360.0]])
    r_closed   = np.concatenate([r, [r[0]]])
    angles_rad = np.radians(angles_deg)

    line.set_data(angles_rad, r_closed)

    # Fill polygon: build from finite points only, so gaps don't create
    # weird triangles back to the origin
    finite = np.isfinite(r_closed)
    if finite.sum() >= 3:
        fill_patch.set_xy(np.column_stack([angles_rad[finite], r_closed[finite]]))
    else:
        fill_patch.set_xy(np.zeros((1, 2)))

    # Tick labels: convert radial position back to dBm for display
    tick_dbm = r_ticks + (p_peak - DYN)
    ax.set_yticklabels([f"{v:.0f} dBm" for v in tick_dbm],
                       color="#88a0b8", fontsize=7)

    status_text.set_text(
        f"{n_filled}/{NBINS} bins  ·  {p_min:.1f}…{p_peak:.1f} dBm  ·  "
        f"peak−{DYN:.0f} dB"
    )


def update(_frame):
    with lock:
        means_az = compute_means(buckets_az)
        means_el = compute_means(buckets_el)
        n_samp   = samples

    render_plot(plot_az, means_az)
    render_plot(plot_el, means_el)

    if n_samp == 0:
        suptitle.set_text("Antenna Pattern (live)  ·  waiting for data…")
    else:
        suptitle.set_text(f"Antenna Pattern (live)  ·  {n_samp} samples")

    return (plot_az["line"], plot_az["fill"],
            plot_el["line"], plot_el["fill"])


ani = animation.FuncAnimation(fig, update, interval=200, blit=False)

plt.tight_layout()
plt.show()