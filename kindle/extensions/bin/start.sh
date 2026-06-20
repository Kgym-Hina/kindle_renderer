#!/bin/sh

BASE=/mnt/us/extensions/kindle-dashboard
PIDFILE="$BASE/dashboard.pid"
LOG="$BASE/logs/dashboard.log"
BIN="$BASE/bin/dashboard-kindle"
CONFIG="$BASE/config"
IMAGE_DIR="$BASE/bin"
PATH="/usr/sbin:/usr/bin:/sbin:/bin:/usr/local/sbin:/usr/local/bin"

export PATH

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

{
  echo "[$(date)] starting dashboard"
  echo "PATH=$PATH"
  echo "BIN=$BIN"
  echo "CONFIG=$CONFIG"
  echo "IMAGE_DIR=$IMAGE_DIR"
} >> "$LOG"

if command -v setsid >/dev/null 2>&1; then
  echo "LAUNCH_MODE=setsid+nohup" >> "$LOG"
  KINDLE_DASHBOARD_BASE="$IMAGE_DIR" \
  KINDLE_DASHBOARD_CONFIG="$CONFIG" \
  setsid nohup "$BIN" >> "$LOG" 2>&1 </dev/null &
else
  echo "LAUNCH_MODE=nohup" >> "$LOG"
  KINDLE_DASHBOARD_BASE="$IMAGE_DIR" \
  KINDLE_DASHBOARD_CONFIG="$CONFIG" \
  nohup "$BIN" >> "$LOG" 2>&1 </dev/null &
fi

echo $! > "$PIDFILE"
echo "Dashboard started"
