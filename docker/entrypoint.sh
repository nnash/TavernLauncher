#!/bin/sh
set -e

# First run: create the Wine prefix (persisted via the /wine volume).
if [ ! -f "$WINEPREFIX/system.reg" ]; then
    echo "Initializing Wine prefix..."
    xvfb-run -a wineboot --init >/dev/null 2>&1 || true
    wineserver -w || true
fi

# The launcher is native Python; the game runs under Wine. Point %APPDATA% at
# the prefix's Roaming folder so both see the same saves, logs and config.
USER_DIR="$WINEPREFIX/drive_c/users/$(id -un)"
[ -d "$USER_DIR" ] || USER_DIR="$WINEPREFIX/drive_c/users/root"
export APPDATA="$USER_DIR/AppData/Roaming"
mkdir -p "$APPDATA"

cd /launcher
exec xvfb-run -a python3 -m server.headless "$@"
