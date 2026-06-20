#!/bin/sh

BASE=/mnt/us/extensions/kindle-dashboard
PIDFILE="$BASE/dashboard.pid"

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE")"

  if kill -0 "$PID" 2>/dev/null; then
    kill -TERM "$PID" 2>/dev/null
  fi

  COUNT=0
  while kill -0 "$PID" 2>/dev/null; do
    COUNT=$((COUNT + 1))
    if [ "$COUNT" -ge 20 ]; then
      kill -KILL "$PID" 2>/dev/null
      break
    fi
    sleep 1
  done

  rm -f "$PIDFILE"
fi

echo "Dashboard stopped"
