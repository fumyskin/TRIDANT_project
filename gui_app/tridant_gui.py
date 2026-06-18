"""
TRIDANT host GUI — native, no web app.

Architecture (plane separation preserved, seam = in-process queue):
    BLE thread  : Bleak asyncio loop, scans/connects, unpacks 15-byte Sample,
                  drops dicts onto a thread-safe queue. Never touches matplotlib.
    Main thread : matplotlib polar plots, drains the queue on a timer, bins by
                  angle, plots the per-bin MEDIAN in normalized dB.

The Bleak side is identical to what a WebSocket bridge would use, so this is
reusable verbatim if you ever swap the presentation layer for a browser app.

Run:  pip install bleak matplotlib numpy
      python tridant_gui.py
Keys: 'c' clears the accumulated pattern, 'q' quits.
"""

import asyncio
import threading
import queue
import time
from collections import deque, defaultdict

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from bleak import BleakScanner, BleakClient

import protocol

# ---------------------------------------------------------------- config ----
DEVICE_NAME  = "TRIDANT"   # set to whatever your board advertises (else "ESP32_BLE")
SERVICE_UUID = "97dcc426-d11e-476e-95e2-79f064720640"
CHAR_UUID    = "aae3a4f0-8e88-4bd0-8047-c6a8c2312a3d"
PROFILE      = "V2X_5G9"   # key into protocol.PROFILES

BIN_DEG      = 2.0         # angular bin width
DB_FLOOR     = -40.0       # radial floor; deep nulls clip here (centre of plot)
BIN_HISTORY  = 50          # samples retained per bin (bounds memory; recent-weighted)

AZ_FIELD     = "phi"       # field swept for the azimuth cut
EL_FIELD     = "elev"      # field swept for the elevation cut  (switch to "theta" if needed)

# ----------------------------------------------------------- shared state ----
sample_q     = queue.Queue()
status       = {"state": "starting", "profile": PROFILE, "cal": 0, "count": 0}
status_lock  = threading.Lock()


def set_status(**kw):
    with status_lock:
        status.update(kw)


# ------------------------------------------------------------- BLE thread ----
def notification_handler(_sender, data: bytearray):
    if len(data) != protocol.SAMPLE_SIZE:
        return
    sample_q.put(protocol.unpack(bytes(data), PROFILE))


async def ble_main():
    while True:
        try:
            set_status(state="scanning")
            dev = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=10.0)
            if dev is None:
                # fallback: match by advertised service UUID
                dev = await BleakScanner.find_device_by_filter(
                    lambda d, ad: SERVICE_UUID.lower()
                    in [u.lower() for u in (ad.service_uuids or [])],
                    timeout=10.0,
                )
            if dev is None:
                set_status(state="device not found, retrying")
                await asyncio.sleep(2)
                continue

            set_status(state="connecting")
            async with BleakClient(dev) as client:
                set_status(state="connected")
                await client.start_notify(CHAR_UUID, notification_handler)
                while client.is_connected:
                    await asyncio.sleep(0.5)
            set_status(state="disconnected, retrying")
        except Exception as e:
            set_status(state=f"error: {e}")
            await asyncio.sleep(2)


def ble_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(ble_main())


# ---------------------------------------------------------------- binning ----
az_bins  = defaultdict(lambda: deque(maxlen=BIN_HISTORY))
el_bins  = defaultdict(lambda: deque(maxlen=BIN_HISTORY))
rate_ts  = deque(maxlen=30)


def bin_index(angle_deg: float) -> int:
    return int((angle_deg % 360.0) // BIN_DEG)


def drain_queue():
    while True:
        try:
            s = sample_q.get_nowait()
        except queue.Empty:
            break
        az_bins[bin_index(s[AZ_FIELD])].append(s["dbm"])
        el_bins[bin_index(s[EL_FIELD])].append(s["dbm"])
        rate_ts.append(time.time())
        with status_lock:
            status["cal"] = s["cal"]
            status["count"] += 1


def curve(bins):
    """Per-bin median -> (theta_rad, dBm)."""
    if not bins:
        return np.array([]), np.array([])
    idxs = sorted(bins.keys())
    th = np.deg2rad([(i + 0.5) * BIN_DEG for i in idxs])
    r  = np.array([np.median(bins[i]) for i in idxs])
    return th, r


def normalize(r):
    """Peak -> 0 dB, clipped to the floor. Preserves nulls; no temporal smoothing."""
    if r.size == 0:
        return r
    return np.clip(r - r.max(), DB_FLOOR, 0.0)


# ----------------------------------------------------------------- plots ----
fig = plt.figure(figsize=(12, 6.5))
ax_az = fig.add_subplot(1, 2, 1, projection="polar")
ax_el = fig.add_subplot(1, 2, 2, projection="polar")

for ax, title in ((ax_az, "Azimuth cut"), (ax_el, "Elevation cut")):
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)          # clockwise, compass-style
    ax.set_ylim(DB_FLOOR, 0)
    ax.set_yticks([0, -10, -20, -30, -40])
    ax.set_title(title, pad=18)

(line_az,) = ax_az.plot([], [], lw=1.8)
(line_el,) = ax_el.plot([], [], lw=1.8)
status_text = fig.text(0.5, 0.025, "", ha="center", family="monospace", fontsize=10)


def update(_frame):
    drain_queue()

    th_a, r_a = curve(az_bins)
    th_e, r_e = curve(el_bins)
    r_a, r_e = normalize(r_a), normalize(r_e)

    if th_a.size:  # close the loop for a continuous curve
        line_az.set_data(np.append(th_a, th_a[0]), np.append(r_a, r_a[0]))
    if th_e.size:
        line_el.set_data(np.append(th_e, th_e[0]), np.append(r_e, r_e[0]))

    rate = 0.0
    if len(rate_ts) >= 2:
        dt = rate_ts[-1] - rate_ts[0]
        if dt > 0:
            rate = (len(rate_ts) - 1) / dt

    with status_lock:
        st = dict(status)
    status_text.set_text(
        f"[{st['state']}]   profile={st['profile']}   "
        f"rate={rate:4.1f} Hz   cal={st['cal']}/3   samples={st['count']}"
        f"      ('c' clear  ·  'q' quit)"
    )
    return line_az, line_el, status_text


def on_key(event):
    if event.key == "c":
        az_bins.clear()
        el_bins.clear()
        with status_lock:
            status["count"] = 0
    elif event.key == "q":
        plt.close(fig)


def main():
    threading.Thread(target=ble_thread, daemon=True).start()
    fig.canvas.mpl_connect("key_press_event", on_key)
    # blit=False: polar + text overlay is finicky to blit; 10 fps is cheap anyway.
    _ani = FuncAnimation(fig, update, interval=100, blit=False, cache_frame_data=False)
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    plt.show()


if __name__ == "__main__":
    main()