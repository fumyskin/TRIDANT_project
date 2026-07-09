#!/usr/bin/env python3
"""
TRIDANT BLE capture — the Bluetooth analogue of scripts/logger.sh.

Receives Samples over BLE exactly like tridant_gui.py (same scan/connect/notify
path), unpacks each 15-byte Sample with protocol.unpack, and writes the RAW
fields to a CSV log while echoing them to the terminal so you can watch live.

Raw on purpose: this logs the wire values (mv, not dBm). No calibration, no
plausibility filtering, no normalization — that all lives host-side in
plot_pattern.py, so the log stays re-calibratable and re-plottable later.

Run:  pip install bleak
      python capture_ble.py                       # -> tridant_YYYYmmdd_HHMMSS.csv
      python capture_ble.py -o dipole_az.csv       # explicit file
      python capture_ble.py -o -                    # CSV to stdout (pipe it)
      python capture_ble.py --fields phi,theta,elev,mv,cal   # pin column order
      python capture_ble.py --quiet                 # counter only, no row echo
      python capture_ble.py --dbm --band GNSS       # add dbm column + live peak
Stop: Ctrl-C  (the log is flushed per row, so a kill still leaves a usable file)
"""
import argparse
import asyncio
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from bleak import BleakScanner, BleakClient
import protocol

# BLE / wire config (identical to tridant_gui.py)
DEVICE_NAME  = "TRIDANT"
SERVICE_UUID = "97dcc426-d11e-476e-95e2-79f064720640"
CHAR_UUID    = "aae3a4f0-8e88-4bd0-8047-c6a8c2312a3d"
DEFAULT_PROFILE = "V2X_5G9"     # key into protocol.PROFILES; must match the sweep

# Calibration for the optional --dbm column (mirrors tridant_gui.py).
# AD8318: P_dBm = (mv - intercept_mv) / slope_mv_per_db  (slope negative).
# PLACEHOLDERS — replace with your real two-point cal.
CAL = {
    "GNSS": dict(slope_mv_per_db=-22.0, intercept_mv=315.0),   # L1  ~1.575 GHz
    "V2X":  dict(slope_mv_per_db=-22.0, intercept_mv=352.0),   #     ~5.9   GHz
}

def mv_to_dbm(mv, band):
    c = CAL[band]
    return (mv - c["intercept_mv"]) / c["slope_mv_per_db"]


def eprint(*a):
    print(*a, file=sys.stderr, flush=True)


def fmt(v):
    """CSV-safe formatting: fixed-point floats (no sci-notation), ints/str as-is."""
    return f"{v:.4f}" if isinstance(v, float) else str(v)


class Capture:
    def __init__(self, args):
        self.profile = args.profile
        self.fields  = [f.strip() for f in args.fields.split(",")] if args.fields else None
        self.quiet   = args.quiet
        self.stop    = False
        self.connected = False
        self.count   = 0
        self.rate_ts = deque(maxlen=30)
        self.header  = None

        self.dbm     = args.dbm
        self.band    = args.band
        self.peak    = float("-inf")   # running max dBm, for boresight aiming
        self.warned_no_mv = False


        self.to_stdout = args.output == "-"
        self.dest = "<stdout>" if self.to_stdout else str(args.output)
        self.sink = sys.stdout if self.to_stdout else open(args.output, "w", buffering=1)
        # echo rows to the terminal only when the CSV isn't already going there
        self.echo = (not self.quiet) and (not self.to_stdout)

        if self.dbm:
            c = CAL[self.band]
            eprint(f"dbm column: band={self.band} "
                   f"slope={c['slope_mv_per_db']} intercept={c['intercept_mv']} "
                   f"(placeholder — edit CAL for real values; peak is offset-free)")
 


    #output
    def _emit_header(self, sample):
        hdr = self.fields or list(sample.keys())
        if self.dbm and "dbm" not in hdr:      # additive: mv stays, dbm appended
            hdr = hdr + ["dbm"]
        self.header = hdr
        eprint(f"fields: {','.join(self.header)}")
        self.sink.write(",".join(self.header) + "\n")


    def write_sample(self, sample):
        if self.header is None:
            self._emit_header(sample)
        row = ",".join(fmt(sample.get(k, "")) for k in self.header)
        self.sink.write(row + "\n")
        self.count += 1
        self.rate_ts.append(time.time())
        if self.echo:
            eprint(row + (f"   peak={self.peak:6.1f} dBm"
                          if self.dbm and self.peak > float("-inf") else ""))


    def rate(self):
        if len(self.rate_ts) >= 2:
            dt = self.rate_ts[-1] - self.rate_ts[0]
            if dt > 0:
                return (len(self.rate_ts) - 1) / dt
        return 0.0

    def close(self):
        if not self.to_stdout:
            self.sink.close()

    # -- BLE callback ------------------------------------------------------
    def on_notify(self, _sender, data: bytearray):
        if len(data) != protocol.SAMPLE_SIZE:
            return
        s = protocol.unpack(bytes(data), self.profile)
        if self.dbm:
            if "mv" in s:
                d = mv_to_dbm(s["mv"], self.band)
                s["dbm"] = d
                if d > self.peak:
                    self.peak = d
            elif not self.warned_no_mv:
                eprint("warning: no 'mv' field in sample; --dbm has nothing to convert")
                self.warned_no_mv = True
        self.write_sample(s)


async def ble_loop(cap: Capture):
    """Scan -> connect -> notify, with reconnect. Mirrors tridant_gui.ble_main."""
    while not cap.stop:
        try:
            eprint("scanning…")
            dev = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=10.0)
            if dev is None:  # fallback: match by advertised service UUID
                dev = await BleakScanner.find_device_by_filter(
                    lambda d, ad: SERVICE_UUID.lower()
                    in [u.lower() for u in (ad.service_uuids or [])],
                    timeout=10.0,
                )
            if dev is None:
                eprint("device not found, retrying")
                await asyncio.sleep(2)
                continue

            eprint(f"connecting to {dev.address}…")
            async with BleakClient(dev) as client:
                cap.connected = True
                eprint("connected — logging to " + cap.dest)
                await client.start_notify(CHAR_UUID, cap.on_notify)
                while client.is_connected and not cap.stop:
                    await asyncio.sleep(0.5)
            cap.connected = False
            if not cap.stop:
                eprint("disconnected, retrying")
        except Exception as e:
            cap.connected = False
            eprint(f"error: {e}")
            await asyncio.sleep(2)


async def status_loop(cap: Capture):
    """One-line live counter (carriage-return) when rows aren't being echoed."""
    if cap.echo:            # rows already scrolling; a CR line would fight them
        return
    while not cap.stop:
        await asyncio.sleep(1.0)
        state = "conn" if cap.connected else "…"
        peak = (f" peak={cap.peak:6.1f}dBm"
                if cap.dbm and cap.peak > float("-inf") else "")
        sys.stderr.write(
            f"\r[{state}] n={cap.count} rate={cap.rate():4.1f} Hz{peak} -> {cap.dest}   "
        )
        sys.stderr.flush()


async def main(cap: Capture):
    tasks = [asyncio.create_task(ble_loop(cap)), asyncio.create_task(status_loop(cap))]
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass


def parse_args():
    p = argparse.ArgumentParser(description="TRIDANT BLE raw-data logger.")

    log_dir = Path("logs_ble")
    log_dir.mkdir(exist_ok=True)


    filename = datetime.now().strftime("tridant_%Y%m%d_%H%M%S.csv")
    default_out = log_dir/filename

    p.add_argument("-o", "--output", default=default_out,
                   help="CSV path, or '-' for stdout (default: timestamped file)")
    p.add_argument("--profile", default=DEFAULT_PROFILE,
                   help=f"protocol.PROFILES key (default: {DEFAULT_PROFILE})")
    p.add_argument("--fields", default=None,
                   help="comma-separated column order, e.g. phi,theta,elev,mv,cal "
                        "(default: every field protocol.unpack returns)")
    p.add_argument("--quiet", action="store_true",
                   help="suppress per-row echo; show only the live counter")
    p.add_argument("--dbm", action="store_true",
                   help="append a computed dbm column (mv is kept) and show running peak")
    p.add_argument("--band", default="GNSS", choices=sorted(CAL),
                   help="CAL band for the dbm column (default: GNSS)")
    return p.parse_args()



if __name__ == "__main__":
    cap = Capture(parse_args())
    try:
        asyncio.run(main(cap))
    except KeyboardInterrupt:
        cap.stop = True
    finally:
        cap.close()
        eprint(f"\nstopped — {cap.count} samples -> {cap.dest}")