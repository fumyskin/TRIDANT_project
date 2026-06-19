#!/usr/bin/env bash
#
# capture_serial.sh — log CodeCell (ESP32-C6) serial output to band-specific files.
#
# Routing:
#   * If a line starts with a band tag (GNSS… / V2X…), it is routed to that band.
#   * Otherwise it goes to the band you pass on the command line (the fallback).
#
# Why a fallback band: the firmware emits raw mV + orientation and leaves the
# band label to the host side, so the serial stream itself usually isn't
# band-tagged. You tell the script which band this capture session is for.
# If you later add a "GNSS"/"V2X" prefix to your Serial.print lines, the script
# splits the stream into both files automatically with no other changes.
#
# Usage:
#   ./capture_serial.sh GNSS                  # fallback band = GNSS
#   ./capture_serial.sh V2X  /dev/ttyACM0     # explicit port
#   PORT=/dev/ttyACM1 BAUD=115200 ./capture_serial.sh GNSS
#
set -euo pipefail

# ---- config (env-overridable) -------------------------------------------
PORT="${PORT:-${2:-/dev/ttyACM0}}"
BAUD="${BAUD:-${3:-115200}}"
LOGDIR="${LOGDIR:-../logs}"

GNSS_LOG="$LOGDIR/GNSS.log"
V2X_LOG="$LOGDIR/V2X.log"

# ---- args ---------------------------------------------------------------
usage() { echo "Usage: $0 <GNSS|V2X> [port] [baud]" >&2; exit 1; }

BAND="${1:-}"
case "${BAND^^}" in
    GNSS) FALLBACK_LOG="$GNSS_LOG" ;;
    V2X)  FALLBACK_LOG="$V2X_LOG"  ;;
    *)    usage ;;
esac

# ---- preflight ----------------------------------------------------------
[ -e "$PORT" ] || { echo "ERROR: $PORT not found. Is the CodeCell plugged in?" >&2; exit 1; }

# Single-owner rule: refuse to start if something else already holds the port
# (serial monitor, BLE bridge, a second copy of this script).
if command -v fuser >/dev/null 2>&1 && fuser "$PORT" >/dev/null 2>&1; then
    echo "ERROR: $PORT is already open (serial monitor or BLE bridge?)." >&2
    echo "       Close it first — e.g.  fuser -k $PORT" >&2
    exit 1
fi

mkdir -p "$LOGDIR"

# raw + -echo  -> clean, unmodified lines.
# -hupcl       -> don't drop modem-control lines on close, which reduces the
#                 chance of resetting the C6 when the script exits.
# (On native-USB CDC the baud value is nominal; the line settings are what matter.)
stty -F "$PORT" "$BAUD" raw -echo -hupcl 2>/dev/null \
    || echo "WARN: stty could not fully configure $PORT (continuing)" >&2

# ---- routing ------------------------------------------------------------
route() {
    local ts="$1" line="$2" file
    case "$line" in
        GNSS*|gnss*|Gnss*) file="$GNSS_LOG" ;;
        V2X*|v2x*|V2x*)    file="$V2X_LOG"  ;;
        *)                 file="$FALLBACK_LOG" ;;
    esac
    printf '%s %s\n' "$ts" "$line" >> "$file"   # to log
    printf '%s %s\n' "$ts" "$line"              # live to terminal
}

write_banner() {
    local tag="$1" t; t="$(date '+%Y-%m-%dT%H:%M:%S%z')"
    echo "# ---- session $tag $t  port=$PORT baud=$BAUD  fallback=${BAND^^} ----" >> "$FALLBACK_LOG"
}

# ---- clean shutdown -----------------------------------------------------
cleanup() { write_banner "end  "; echo; echo "Stopped."; exit 0; }
trap cleanup INT TERM

# ---- run ----------------------------------------------------------------
write_banner "start"
echo "Logging $PORT → $LOGDIR/  (fallback band: ${BAND^^}).  Ctrl-C to stop."

while IFS= read -r line; do
    [ -n "$line" ] || continue
    ts="$(date '+%Y-%m-%dT%H:%M:%S.%3N')"
    route "$ts" "$line"
done < "$PORT"

# Reached only if the device stops feeding lines (e.g. unplugged).
write_banner "end  "
echo "Serial closed (device disconnected?)."