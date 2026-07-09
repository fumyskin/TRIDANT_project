# protocol.py — byte-locked to sample.h
import struct

SAMPLE_FMT  = "<fffHB"           # phi, theta, elev, mv, cal
SAMPLE_SIZE = struct.calcsize(SAMPLE_FMT)   # == 15
assert SAMPLE_SIZE == 15

# Host-owned calibration. Per-frequency profiles live here, not in firmware.
PROFILES = {
    "GNSS_1G575": {"slope_mv_per_db": -22.0, "intercept_mv": 315.0},
    "V2X_5G9":  {"slope_mv_per_db": -22.0, "intercept_mv": 352.0},  
}

def unpack(buf, profile="V2X_5G9"):
    phi, theta, elev, mv, cal = struct.unpack(SAMPLE_FMT, buf)
    p = PROFILES[profile]
    dbm = (mv - p["intercept_mv"]) / p["slope_mv_per_db"]
    return {"phi": phi, "theta": theta, "elev": elev,
            "mv": mv, "dbm": dbm, "cal": cal}