#!/bin/sh

BASE=/mnt/us/extensions/kindle-dashboard
PIDFILE="$BASE/dashboard.pid"
LOG="$BASE/logs/dashboard.log"
BIN="$BASE/bin/dashboard-kindle"
CONFIG="$BASE/config"
IMAGE_DIR="$BASE/bin"

mkdir -p "$BASE/logs"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Dashboard already running"
  exit 0
fi

if [ ! -x "$BIN" ]; then
  echo "Missing binary: $BIN"
  exit 1
fi

if [ ! -f "$CONFIG" ]; then
  echo "Missing config: $CONFIG"
  exit 1
fi

cd "$IMAGE_DIR" || exit 1

KINDLE_DASHBOARD_BASE="$IMAGE_DIR" \
KINDLE_DASHBOARD_CONFIG="$CONFIG" \
nohup "$BIN" > "$LOG" 2>&1 &

echo $! > "$PIDFILE"
echo "Dashboard started"
