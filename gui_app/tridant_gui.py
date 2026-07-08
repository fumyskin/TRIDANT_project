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

try:
    from scipy.interpolate import PchipInterpolator, CubicSpline
    _HAVE_SCIPY = True
except ImportError:
    _HAVE_SCIPY = False


# ============================================================================
# BLE / wire config
# ============================================================================
DEVICE_NAME  = "TRIDANT"  
SERVICE_UUID = "97dcc426-d11e-476e-95e2-79f064720640"
CHAR_UUID    = "aae3a4f0-8e88-4bd0-8047-c6a8c2312a3d"
PROFILE      = "GNSS_1G575"   # key into protocol.PROFILES

AZ_FIELD     = "phi"       # field swept for the azimuth cut
EL_FIELD     = "elev"      # field swept for the elevation cut

# ============================================================================
# CALIBRATION  —  used when dBm is computed from mv (the default path).
# ============================================================================
# AD8317: P_dBm = (mv - intercept_mv) / slope_mv_per_db   (slope negative).
# Slope sets pattern SHAPE; intercept only shifts the absolute reference and is
# normalized out for pattern work. Replace placeholders with real two-point cal.
BAND = "GNSS"   # "GNSS" (L1 ~1.575 GHz) or "V2X" (~5.9 GHz) — selects the LPD cal
CAL = {
    "GNSS": dict(slope_mv_per_db=-25.0, intercept_mv=510.0),   # L1  ~1.575 GHz
    "V2X":  dict(slope_mv_per_db=-25.0, intercept_mv=608.0),   #     ~5.9   GHz
}
PLAUSIBLE_DBM = (-90.0, 10.0)

def mv_to_dbm(mv, band):
    c = CAL[band]
    return (mv - c["intercept_mv"]) / c["slope_mv_per_db"]

# ============================================================================
# Binning / cut / interpolation config  (names mirror plot_pattern.py)
# ============================================================================
BIN_DEG      = 2.0         # angular bin width
GRID_DEG     = 1.0
DB_FLOOR     = -40.0       # radial floor; deep nulls clip here (centre of plot)
SAMPLE_HISTORY = 6000      #?

REDUCE      = "mean"
INTERP      = "pchip"      #pchip (null-safe)
MAX_GAP_DEG = 20.0

#Plane-cut selection
CUT_MODE    = "auto"
CUT_TOL_DEG = 10.0
EL_REF_DEG  = 0.0
AZ_REF_DEG  = 0.0
MIN_CUT_PTS = 8
MIN_CUT_SPAN_DEG = 60.0


# ============================================================================
# Shared state
# ============================================================================
sample_q     = queue.Queue()
status       = {"state": "starting", "cal": 0, "count": 0}
status_lock  = threading.Lock()

# raw ring of {phi, theta, elev, dbm} - touched only on the main thread
raw_buf = deque(maxlen=SAMPLE_HISTORY)
rate_ts = deque(maxlen=30)

def set_status(**kw):
    with status_lock:
        status.update(kw)


 
# ============================================================================
# BLE thread
# ============================================================================
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

# ============================================================================
# Ingest
# ============================================================================

def drain_queue():
    while True:
        try:
            s = sample_q.get_nowait()
        except queue.Empty:
            break
        dbm = mv_to_dbm(s["mv"], BAND)
        if not (PLAUSIBLE_DBM[0] <= dbm <= PLAUSIBLE_DBM[1]):
            continue
        raw_buf.append({"phi": s[AZ_FIELD], "elev": s[EL_FIELD], "dbm": dbm})
        rate_ts.append(time.time())
        with status_lock:
            status["cal"] = s["cal"]
            status["count"] += 1

# Pipeline ?
def _wrap180(a):
    return (a + 180.0) % 360.0 - 180.0

def _coverage(angle, periodic):
    if len(angle) < 2:
        return 0.0
    a = np.sort(np.asarray(angle) % 360.0)
    if periodic:
        gaps = np.diff(np.concatenate([a, [a[0] + 360.0]]))
        return 360.0 - gaps.max()
    return a[-1] - a[0]


def extract_cut(samples, kind):
    if not samples:
        return np.array([]), np.array([]), "-"
    phi = np.array([s["phi"] for s in samples], float)
    elev = np.array([s["elev"] for s in samples], float)
    dbm = np.array([s["dbm"]  for s in samples], float)

    periodic = True                         # both cuts are periodic now: az over
                                            # phi, el over the unfolded vertical angle
    if kind == "az":
        angle = phi
        plane = np.abs(_wrap180(elev - EL_REF_DEG)) <= CUT_TOL_DEG
    else:
        # Elevation cut lives in the vertical plane through AZ_REF_DEG. Raw 'elev'
        # is a latitude bounded to [-90,90]: it folds at the poles and can never
        # trace a full vertical loop. Select the plane (front AND back halves,
        # pole-robust) and unfold into a continuous phi_v in [0,360).
        d = _wrap180(phi - AZ_REF_DEG)
        line_dist = np.minimum(np.abs(d), 180.0 - np.abs(d))  # dist to plane LINE
        near_pole = np.abs(elev) >= (90.0 - CUT_TOL_DEG)      # az meaningless here
        plane = (line_dist <= CUT_TOL_DEG) | near_pole
        angle = _unfold_elev(phi, elev, AZ_REF_DEG)

    if CUT_MODE == "all":
        sel, mode = np.ones(len(angle), bool), "all"
    elif CUT_MODE == "plane":
        if plane.any():
            sel, mode = plane, "plane"
        else:
            sel, mode = np.ones(len(angle), bool), "all(fallback)"
    else:  # auto: true cut when it is dense enough, else all-samples
        span = _coverage(angle[plane], periodic) if plane.any() else 0.0
        if plane.sum() >= MIN_CUT_PTS and span >= MIN_CUT_SPAN_DEG:
            sel, mode = plane, "plane"
        else:
            sel, mode = np.ones(len(angle), bool), "all"
 
    return angle[sel] % 360.0, dbm[sel], mode


def bin_reduce(angle, dbm, periodic):
    """Merge near-duplicate angles; reduce in the LINEAR (mW) domain."""
    if len(angle) == 0:
        return angle, dbm
    nb = int(round(360.0 / BIN_DEG))
    keys = np.round(angle / BIN_DEG).astype(int)
    if periodic:
        keys %= nb
    mw = 10.0 ** (dbm / 10.0)
    centers, red = [], []
    for k in np.unique(keys):
        m = keys == k
        # Periodic: nominal bin centre (k*BIN_DEG). Taking the sample mean here
        # would average across the 0/360 seam for the wrap bin and produce a
        # non-monotonic centre — which breaks pchip. Non-periodic (elevation):
        # sample mean is safe and slightly more faithful.
        centers.append((k % nb) * BIN_DEG if periodic else angle[m].mean())
        red.append(np.median(mw[m]) if REDUCE == "median" else mw[m].mean())
    centers = np.array(centers)
    order = np.argsort(centers)
    return centers[order], (10.0 * np.log10(np.array(red)))[order]
 
# helper for unfolding
def _unfold_elev(phi, elev, az0):
    """Unfold latitude-style elevation into a continuous vertical-plane angle.

    Raw elevation = atan2(vz, hypot(vx,vy)) is a latitude in [-90,90]; a full
    360° sweep in a vertical plane folds it at the poles while the azimuth flips
    ~180°. Use that flip to reflect the 'back' hemisphere so the result runs
    continuously 0->360 around the vertical circle:
        el    0 -> +90 ->  0 -> -90 ->  0
        phi_v 0 ->  90 ->180 ->270 ->360
    Poles join seamlessly (both branches agree at |el|=90)."""
    d = _wrap180(phi - az0)                 # signed az offset from plane front
    front = np.abs(d) <= 90.0
    return np.where(front, elev % 360.0, 180.0 - elev) % 360.0



def _gap_mask(grid, ang, periodic, max_gap):
    """False where a grid point sits in an unmeasured gap wider than max_gap."""
    a = np.sort(np.asarray(ang) % 360.0)
    keep = np.ones_like(grid, bool)
    if len(a) < 2:
        return keep
    if periodic:
        edges = np.concatenate([a, [a[0] + 360.0]])
        g = grid % 360.0
        for lo, hi in zip(edges[:-1], edges[1:]):
            if hi - lo > max_gap:
                keep &= ~(((g > lo) & (g < hi)) | ((g + 360.0 > lo) & (g + 360.0 < hi)))
    else:
        for lo, hi in zip(a[:-1], a[1:]):
            if hi - lo > max_gap:
                keep &= ~((grid > lo) & (grid < hi))
    return keep


def interpolate(angle, dbm, periodic):
    if len(angle) < 2:
        return angle, dbm
    if periodic:
        grid = np.arange(0.0, 360.0, GRID_DEG)
    else:
        grid = np.linspace(angle.min(), angle.max(),
                           max(2, int((angle.max() - angle.min()) / GRID_DEG) + 1))
    method = INTERP
    if method != "linear" and not _HAVE_SCIPY:
        method = "linear"
    if method == "linear":
        di = (np.interp(grid, angle, dbm, period=360.0) if periodic
              else np.interp(grid, angle, dbm))
    else:
        if periodic:
            x = np.concatenate([angle - 360.0, angle, angle + 360.0])
            y = np.concatenate([dbm, dbm, dbm])
        else:
            x, y = angle, dbm
        f = PchipInterpolator(x, y) if method == "pchip" else CubicSpline(x, y)
        di = f(grid)
    di = np.where(_gap_mask(grid, angle, periodic, MAX_GAP_DEG), di, np.nan)
    return grid, di
 

def build_cut(samples, kind):
    """Full pipeline -> (line_theta_rad, line_r_dB, mark_theta_rad, mark_r_dB, mode).
    r is normalized so peak = 0 dB, floored at DB_FLOOR; NaN marks a gap."""
    periodic = True
    angle, dbm, mode = extract_cut(samples, kind)
    if len(angle) == 0:
        empty = np.array([])
        return empty, empty, empty, empty, mode
 
    c_ang, c_dbm = bin_reduce(angle, dbm, periodic)
    peak = np.nanmax(c_dbm)
 
    # markers = measured bin centers (truth)
    mark_r = np.clip(c_dbm - peak, DB_FLOOR, 0.0)
    mark_th = np.radians(c_ang)
 
    if len(c_ang) < 2:                      # not enough for a curve; markers only
        return np.array([]), np.array([]), mark_th, mark_r, mode
 
    grid, di = interpolate(c_ang, c_dbm, periodic)
    line_r = np.where(np.isnan(di), np.nan, np.clip(di - peak, DB_FLOOR, 0.0))
 
    if periodic:                            # close the loop ONLY if wrap is covered
        grid = np.append(grid, 360.0)       # (NaN at index 0 leaves it open)
        line_r = np.append(line_r, line_r[0])
    return np.radians(grid), line_r, mark_th, mark_r, mode
 


# Plots

fig = plt.figure(figsize=(12, 6.5))
ax_az = fig.add_subplot(1, 2, 1, projection="polar")
ax_el = fig.add_subplot(1, 2, 2, projection="polar")
 
for ax, title in ((ax_az, "Azimuth cut"), (ax_el, "Elevation cut")):
    ax.set_ylim(DB_FLOOR, 0)
    ax.set_yticks([0, -10, -20, -30, -40])
    ax.set_title(title, pad=18)
    ax.grid(True, alpha=0.4)

# Azimuth: compass style — 0° (front) at top, clockwise.
ax_az.set_theta_zero_location("N")
ax_az.set_theta_direction(1)

# Elevation: vertical-plane view — phi_v=0 front horizon (right), 90 zenith (top),
# 180 back horizon (left), 270 nadir (bottom).
ax_el.set_theta_zero_location("E")
ax_el.set_theta_direction(1)
 
(line_az,) = ax_az.plot([], [], lw=1.8, zorder=3)
(line_el,) = ax_el.plot([], [], lw=1.8, zorder=3)
(mark_az,) = ax_az.plot([], [], "o", ms=3.0, alpha=0.5, zorder=4)
(mark_el,) = ax_el.plot([], [], "o", ms=3.0, alpha=0.5, zorder=4)
status_text = fig.text(0.5, 0.025, "", ha="center", family="monospace", fontsize=10)
 
 
def update(_frame):
    drain_queue()
    samples = list(raw_buf)                 # snapshot (main-thread only, cheap)
 
    lt_a, lr_a, mt_a, mr_a, mode_a = build_cut(samples, "az")
    lt_e, lr_e, mt_e, mr_e, mode_e = build_cut(samples, "el")
    line_az.set_data(lt_a, lr_a); mark_az.set_data(mt_a, mr_a)
    line_el.set_data(lt_e, lr_e); mark_el.set_data(mt_e, mr_e)
 
    rate = 0.0
    if len(rate_ts) >= 2:
        dt = rate_ts[-1] - rate_ts[0]
        if dt > 0:
            rate = (len(rate_ts) - 1) / dt
 
    with status_lock:
        st = dict(status)
    status_text.set_text(
        f"[{st['state']}]  band={BAND}  cut az:{mode_a}/el:{mode_e}  "
        f"rate={rate:4.1f} Hz  cal={st['cal']}/3  samples={st['count']}"
        f"    ('c' clear  ·  'q' quit)"
    )
    return line_az, line_el, mark_az, mark_el, status_text
 
 
def on_key(event):
    if event.key == "c":
        raw_buf.clear()
        with status_lock:
            status["count"] = 0
    elif event.key == "q":
        plt.close(fig)
 
 
def main():
    threading.Thread(target=ble_thread, daemon=True).start()
    fig.canvas.mpl_connect("key_press_event", on_key)
    _ani = FuncAnimation(fig, update, interval=100, blit=False, cache_frame_data=False)
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    plt.show()
 
 
if __name__ == "__main__":
    main()
 
