#!/bin/sh

set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
PLUGIN_NAME="kindle-dashboard"
DIST_DIR="$ROOT/dist"
PKG_ROOT="$DIST_DIR/$PLUGIN_NAME"
BIN_DIR="$PKG_ROOT/bin"
ZIP_PATH="$DIST_DIR/${PLUGIN_NAME}.zip"

rm -rf "$PKG_ROOT"
mkdir -p "$BIN_DIR"

echo "Building ARMv7 binary..."
(
  cd "$ROOT"
  GOOS=linux GOARCH=arm GOARM=7 go build -o "$BIN_DIR/dashboard-kindle" .
)

echo "Assembling KUAL plugin..."
cp "$ROOT/extensions/config.xml" "$PKG_ROOT/config.xml"
cp "$ROOT/extensions/menu.json" "$PKG_ROOT/menu.json"
cp "$ROOT/extensions/bin/start.sh" "$BIN_DIR/start.sh"
cp "$ROOT/extensions/bin/stop.sh" "$BIN_DIR/stop.sh"
cp "$ROOT/config" "$PKG_ROOT/config"

chmod 755 "$BIN_DIR/dashboard-kindle" "$BIN_DIR/start.sh" "$BIN_DIR/stop.sh"

echo "Creating zip package..."
rm -f "$ZIP_PATH"
(
  cd "$DIST_DIR"
  zip -r "$ZIP_PATH" "$PLUGIN_NAME"
)

echo "Package ready: $ZIP_PATH"
