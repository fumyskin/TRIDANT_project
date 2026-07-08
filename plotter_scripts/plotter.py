#!/usr/bin/env python3
"""
plot_pattern.py — turn CodeCell mV/orientation logs into antenna pattern plots.

Reads one or more capture logs (as written by capture_serial.sh / capture_ble.py),
converts the AD8318 detector millivolts to power in dBm with a per-band calibration,
and draws
two polar antenna-pattern cuts: an azimuth cut and an elevation cut. Measured
points are shown as markers; a null-safe interpolation draws the "continuous"
pattern through them.

    python plot_pattern.py logs/GNSS.log
    python plot_pattern.py logs/GNSS.log logs/V2X.log --normalize
    python plot_pattern.py logs/GNSS.log --dbm-source firmware   # use the P_dBm column

Column layout is read from the log's header line automatically (e.g.
"phi_deg,theta_deg,elev_deg,P_dBm,mv,cal"); the FIELD map below is only the
fallback when no header is present.

Dependencies: numpy, matplotlib (required); scipy (optional, for pchip/cubic).
    pip install numpy matplotlib scipy --break-system-packages
"""

import argparse
import os
import re
import sys

import numpy as np
import matplotlib.pyplot as plt

try:
    from scipy.interpolate import PchipInterpolator, CubicSpline
    _HAVE_SCIPY = True
except ImportError:
    _HAVE_SCIPY = False


# ============================================================================
# 1. LOG FORMAT
# ============================================================================
# Column positions are normally taken from the header line in the log. This
# FIELD map is the fallback if a file has no header. Order matches the packed
# struct as currently emitted: phi, theta, elev, P_dBm, mv, cal.
FIELD = {"az": 0, "el": 2, "mv": 3}

# Header-name -> canonical field. Add aliases here if your header differs.
HEADER_ALIASES = {
    "phi": "az", "phi_deg": "az", "az": "az", "az_deg": "az", "azimuth": "az",
    "elev": "el", "elev_deg": "el", "el": "el", "el_deg": "el", "elevation": "el",
    "theta": "theta", "theta_deg": "theta",
    "p_dbm": "dbm", "pdbm": "dbm", "dbm": "dbm",
    "mv": "mv", "millivolts": "mv",
    "cal": "cal", "calacc": "cal", "cal_acc": "cal",
}

# ============================================================================
# 2. CALIBRATION  —  used when dBm is computed from mv (the default path).
# ============================================================================
# AD8318: P_dBm = (mv - intercept_mv) / slope_mv_per_db   (slope negative).
# Slope sets pattern SHAPE; intercept only shifts the absolute reference and is
# normalized out for pattern work. Replace placeholders with real two-point cal.
CAL = {
    "GNSS": dict(slope_mv_per_db=-25.0, intercept_mv=510.0),   # L1  ~1.575 GHz
    "V2X":  dict(slope_mv_per_db=-25.0, intercept_mv=608.0),   #     ~5.9   GHz
}

def two_point(p1_dbm, v1_mv, p2_dbm, v2_mv):
    """Derive (slope_mv_per_db, intercept_mv) from two measured points."""
    slope = (v2_mv - v1_mv) / (p2_dbm - p1_dbm)
    return slope, v1_mv - slope * p1_dbm

# ============================================================================
# 3. GUARDS & GEOMETRY
# ============================================================================
WARMUP_DISCARD = 0
SAT_MV         = 2400.0
DROP_SATURATED = False
PLAUSIBLE_DBM  = (-90.0, 10.0)   # applied only to mv-derived dBm

CUT_TOL_DEG      = 10.0   # plane-cut acceptance: |orthogonal angle - ref| <= this
EL_REF_DEG       = 0.0    # elevation plane held during an azimuth sweep
AZ_REF_DEG       = 0.0    # azimuth   plane held during an elevation sweep
MIN_CUT_PTS      = 8      # auto mode: a plane cut needs at least this many points...
MIN_CUT_SPAN_DEG = 60.0   # ...spanning at least this many degrees, else use all samples
MAX_GAP_DEG      = 20.0   # break the continuous curve across gaps wider than this
BIN_DEG          = 1.0
GRID_DEG         = 1.0

_TS_RE = re.compile(r"^\s*\d{4}-\d{2}-\d{2}T[\d:.\-+]+\s+")
_BANDS = ("GNSS", "V2X")


# ============================================================================
# Parsing
# ============================================================================
def band_from_name(path):
    name = os.path.basename(path).upper()
    for b in _BANDS:
        if b in name:
            return b
    return None

def _is_header(tokens):
    hits = sum(1 for t in tokens if t.lower() in HEADER_ALIASES)
    floats = 0
    for t in tokens:
        try:
            float(t); floats += 1
        except ValueError:
            pass
    return hits >= 2 and floats == 0

def parse_file(path):
    """band -> list of (az, el, mv, dbm); mv or dbm may be NaN if not present."""
    default_band = band_from_name(path)
    fmap = dict(FIELD)
    out, skipped = {}, 0
    with open(path) as fh:
        for raw in fh:
            line = _TS_RE.sub("", raw.strip())
            if not line or line.startswith("#"):
                continue
            toks = re.split(r"[,\s]+", line.strip())
            band = default_band
            if toks and toks[0].upper() in _BANDS:
                band, toks = toks[0].upper(), toks[1:]
            if _is_header(toks):
                fm = {}
                for i, t in enumerate(toks):
                    key = HEADER_ALIASES.get(t.lower())
                    if key:
                        fm[key] = i
                if "az" in fm and "el" in fm and ("mv" in fm or "dbm" in fm):
                    fmap = fm
                continue
            nums = []
            for t in toks:                          # keep positions stable
                try:
                    nums.append(float(t))
                except ValueError:
                    nums.append(None)
            def get(key):
                i = fmap.get(key)
                if i is None or i >= len(nums) or nums[i] is None:
                    return float("nan")
                return nums[i]
            az, el, mv, dbm = get("az"), get("el"), get("mv"), get("dbm")
            if band is None or np.isnan(az) or np.isnan(el) or (np.isnan(mv) and np.isnan(dbm)):
                skipped += 1
                continue
            out.setdefault(band, []).append((az, el, mv, dbm))
    if skipped:
        print(f"  {os.path.basename(path)}: skipped {skipped} non-data line(s)",
              file=sys.stderr)
    return out


def mv_to_dbm(mv, band):
    if band not in CAL:
        raise SystemExit(f"No calibration for band '{band}'. Add it to CAL.")
    c = CAL[band]
    return (mv - c["intercept_mv"]) / c["slope_mv_per_db"]


# ============================================================================
# Cut extraction, binning, interpolation
# ============================================================================
def _wrap180(a):
    return (a + 180.0) % 360.0 - 180.0

def _coverage(angle, periodic):
    """Angular span actually covered by the points, in degrees."""
    if len(angle) < 2:
        return 0.0
    a = np.sort(angle % 360.0)
    if periodic:
        gaps = np.diff(np.concatenate([a, [a[0] + 360.0]]))
        return 360.0 - gaps.max()          # span once the biggest empty arc is removed
    return a[-1] - a[0]


def extract_cut(rows, band, kind, args):
    """kind 'az'|'el'. Returns angle[deg], dbm, saturated_mask."""
    az  = np.array([r[0] for r in rows], float)
    el  = np.array([r[1] for r in rows], float)
    mv  = np.array([r[2] for r in rows], float)
    fwd = np.array([r[3] for r in rows], float)
    if WARMUP_DISCARD:
        az, el, mv, fwd = (a[WARMUP_DISCARD:] for a in (az, el, mv, fwd))

    periodic = (kind == "az")
    if kind == "az":
        plane, angle_full = np.abs(_wrap180(el - EL_REF_DEG)) <= CUT_TOL_DEG, az
    else:
        plane, angle_full = np.abs(_wrap180(az - AZ_REF_DEG)) <= CUT_TOL_DEG, el

    if args.cut == "all":
        sel = np.ones_like(mv, bool)
    elif args.cut == "plane":
        sel = plane if plane.any() else np.ones_like(mv, bool)
        if not plane.any():
            print(f"  {band} {kind}-cut: no samples in the reference plane — using all.",
                  file=sys.stderr)
    else:  # auto: fall back to all samples when the plane cut is too sparse
        span = _coverage(angle_full[plane], periodic) if plane.any() else 0.0
        if plane.sum() >= MIN_CUT_PTS and span >= MIN_CUT_SPAN_DEG:
            sel = plane
        else:
            sel = np.ones_like(mv, bool)
            print(f"  {band} {kind}-cut: plane cut has {plane.sum()} pts over {span:.0f} "
                  f"deg — too sparse, plotting all samples vs {kind}. (For a true cut, "
                  f"hold the other axis fixed while sweeping {kind}.)", file=sys.stderr)

    angle, mv, fwd = angle_full[sel], mv[sel], fwd[sel]
    sat = np.where(np.isnan(mv), False, mv >= SAT_MV)
    if DROP_SATURATED and sat.any():
        keep = ~sat
        angle, mv, fwd, sat = angle[keep], mv[keep], fwd[keep], sat[keep]

    use_fw = (args.dbm_source == "firmware") and not np.all(np.isnan(fwd))
    if args.dbm_source == "firmware" and np.all(np.isnan(fwd)):
        print(f"  {band} {kind}-cut: no P_dBm column — computing from mv instead.",
              file=sys.stderr)
    if use_fw:
        dbm = fwd
    else:
        dbm = mv_to_dbm(mv, band)
        ok = (dbm >= PLAUSIBLE_DBM[0]) & (dbm <= PLAUSIBLE_DBM[1])
        angle, dbm, sat = angle[ok], dbm[ok], sat[ok]
    return angle % 360.0, dbm, sat


def bin_average(angle, dbm, periodic):
    """Merge near-duplicate angles; average in the LINEAR domain (mW), not in dB."""
    if len(angle) == 0:
        return angle, dbm
    keys = np.round(angle / BIN_DEG).astype(int)
    if periodic:
        keys %= int(round(360.0 / BIN_DEG))
    mw = 10.0 ** (dbm / 10.0)
    centers, means = [], []
    for k in np.unique(keys):
        m = keys == k
        centers.append(angle[m].mean())
        means.append(mw[m].mean())
    centers = np.array(centers)
    order = np.argsort(centers)
    return centers[order], (10.0 * np.log10(np.array(means)))[order]


def _gap_mask(grid, ang, periodic, max_gap):
    """False where a grid point sits in an unmeasured gap wider than max_gap deg."""
    a = np.sort(ang % 360.0)
    keep = np.ones_like(grid, bool)
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


def interpolate(angle, dbm, periodic, method):
    if len(angle) < 2:
        return angle, dbm
    if periodic:
        grid = np.arange(0.0, 360.0, GRID_DEG)
    else:
        grid = np.linspace(angle.min(), angle.max(),
                           max(2, int((angle.max() - angle.min()) / GRID_DEG) + 1))
    if method != "linear" and not _HAVE_SCIPY:
        print("  scipy not installed — using linear interpolation.", file=sys.stderr)
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


# ============================================================================
# Plotting
# ============================================================================
def plot_cut(ax, datasets, title, periodic, args):
    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    vals = [d for _, _, d, _ in datasets if len(d)]
    peak = np.concatenate(vals).max() if vals else 0.0
    if args.normalize:                       # shape only: 0 dB at peak
        shift, floor, top = -peak, -args.dyn_range, 0.0
    elif args.rmax is not None:              # fixed absolute axis — matches the GUI
        shift = 0.0
        top = args.rmax
        floor = args.rmin if args.rmin is not None else args.rmax - args.dyn_range
    else:                                    # absolute dBm, axis auto-ranged to peak
        shift, floor, top = 0.0, peak - args.dyn_range, peak + 1.0

    for i, (label, angle, dbm, sat) in enumerate(datasets):
        if len(angle) == 0:
            continue
        c = colors[i % len(colors)]
        a_avg, d_avg = bin_average(angle, dbm, periodic)
        g, di = interpolate(a_avg, d_avg, periodic, args.interp)
        ax.plot(np.radians(g), np.clip(di + shift, floor, top),
                "-", color=c, lw=1.6, label=label, zorder=3)
        d_pts = np.clip(dbm + shift, floor, top)
        ax.plot(np.radians(angle), d_pts, "o", color=c, ms=3.5, alpha=0.55, zorder=4)
        if sat.any():
            ax.plot(np.radians(angle[sat]), d_pts[sat], "x", color="red",
                    ms=6, mew=1.4, zorder=5)

    ax.set_title(title, pad=18, fontsize=12, weight="bold")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_rlim(floor, top)
    ax.set_rlabel_position(135)
    ax.text(np.radians(135), floor, "dB" if args.normalize else "dBm",
            ha="center", va="top", fontsize=8, alpha=0.7)
    ax.grid(True, alpha=0.4)


def main():
    ap = argparse.ArgumentParser(description="Plot antenna pattern cuts from CodeCell logs.")
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--dbm-source", choices=["mv", "firmware"], default="mv",
                    help="'mv' recomputes dBm host-side via CAL (default); "
                         "'firmware' uses the P_dBm column from the log as-is")
    ap.add_argument("--cut", choices=["auto", "plane", "all"], default="auto",
                    help="'auto' uses a fixed-reference plane cut but falls back to all "
                         "samples when that cut is too sparse (default); 'plane' forces "
                         "the cut; 'all' plots every sample against the axis")
    ap.add_argument("--interp", choices=["pchip", "linear", "cubic"], default="pchip")
    ap.add_argument("--normalize", action="store_true", help="0 dB at peak")
    ap.add_argument("--rmax", type=float, default=None,
                    help="fixed outer edge in dBm (matches the GUI's R_MAX); "
                         "omit to auto-range to the peak")
    ap.add_argument("--rmin", type=float, default=None,
                    help="fixed centre floor in dBm; defaults to rmax - dyn_range")
    ap.add_argument("--dyn-range", type=float, default=40.0)
    ap.add_argument("--save", default=None)
    args = ap.parse_args()

    data = {}
    for path in args.logs:
        if not os.path.exists(path):
            print(f"warning: {path} not found, skipping", file=sys.stderr)
            continue
        for band, rows in parse_file(path).items():
            data.setdefault(band, []).extend(rows)
    if not data:
        raise SystemExit("No usable samples found in the given logs.")

    az_sets, el_sets = [], []
    for band, rows in sorted(data.items()):
        az_sets.append((band, *extract_cut(rows, band, "az", args)))
        el_sets.append((band, *extract_cut(rows, band, "el", args)))
        print(f"{band}: {len(rows)} samples  "
              f"(az-cut {len(az_sets[-1][1])}, el-cut {len(el_sets[-1][1])})  "
              f"dBm source: {args.dbm_source}")

    fig, (ax_az, ax_el) = plt.subplots(
        1, 2, figsize=(12, 6.2), subplot_kw={"projection": "polar"})
    plot_cut(ax_az, az_sets, "Azimuth cut", True, args)
    plot_cut(ax_el, el_sets, "Elevation cut", False, args)

    h, l = ax_az.get_legend_handles_labels()
    if h:
        fig.legend(h, l, loc="lower center", ncol=len(l), frameon=False,
                   bbox_to_anchor=(0.5, 0.0))
    fig.suptitle("Antenna radiation pattern", fontsize=14, weight="bold")
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    if args.save:
        fig.savefig(args.save, dpi=150, bbox_inches="tight")
        print(f"saved {args.save}")
    plt.show()


if __name__ == "__main__":
    main()