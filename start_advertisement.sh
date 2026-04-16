#!/bin/bash
# GUI-aware startup script for advertisement player
# This script waits for the desktop environment to be ready before starting

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Portrait advertising monitor — keep equal to DISPLAY_ROTATION_DEGREES in realrun.sh
DISPLAY_ROTATION_DEGREES=90

# Log function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> /tmp/advertisement_startup.log
}

log "=== Advertisement Player Startup ==="
log "Script directory: $SCRIPT_DIR"

# Function to check if GUI is ready
wait_for_gui() {
    local max_wait=120  # Maximum wait time in seconds (longer for slow boot)
    local waited=0

    log "Waiting for GUI environment to be ready..."

    while [ $waited -lt $max_wait ]; do
        # Check if DISPLAY is set and X server is responding
        if [ -n "$DISPLAY" ] && xset q >/dev/null 2>&1; then
            # Check if we can get window manager info
            if wmctrl -m >/dev/null 2>&1; then
                log "GUI environment is ready (waited ${waited}s)"
                return 0
            fi
        fi

        sleep 2
        waited=$((waited + 2))
        log "Still waiting for GUI... (${waited}s)"
    done

    log "WARNING: GUI not ready after ${max_wait}s, starting anyway"
    return 1
}

# Set up environment for GUI applications
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"

# If running as root, try to find the correct user session
if [ "$(id -u)" -eq 0 ]; then
    log "Running as root, finding user session..."

    # Try to get the display from running processes
    DISPLAY_FROM_PROC=$(ps aux | grep -o 'DISPLAY=:[0-9]*' | head -1 | cut -d'=' -f2)
    if [ -n "$DISPLAY_FROM_PROC" ]; then
        export DISPLAY="$DISPLAY_FROM_PROC"
        log "Found DISPLAY from process: $DISPLAY"
    fi

    # Try to find XAUTHORITY
    XAUTH_FROM_PROC=$(ps aux | grep -o 'XAUTHORITY=[^ ]*' | head -1 | cut -d'=' -f2)
    if [ -n "$XAUTH_FROM_PROC" ]; then
        export XAUTHORITY="$XAUTH_FROM_PROC"
        log "Found XAUTHORITY from process: $XAUTHORITY"
    fi
fi

log "Environment: DISPLAY=$DISPLAY, XAUTHORITY=$XAUTHORITY"

# Wait for GUI to be ready
wait_for_gui

# Check if another instance is already running
if pgrep -f "run.py.*--start" >/dev/null; then
    log "Advertisement player is already running, skipping startup"
    exit 0
fi

# Start the advertisement player
log "Starting advertisement player..."
log "Using SCRIPT_DIR=$SCRIPT_DIR"
if [ -x "$SCRIPT_DIR/realrun.sh" ]; then
    "$SCRIPT_DIR/realrun.sh" >> /tmp/advertisement_startup.log 2>&1 &
    log "realrun.sh launched as background process"
    
    # Wait for player to initialize
    sleep 3
    
    # First cycle only: realrun.sh re-applies the same angle after every ./run.sh start
    log "Applying ${DISPLAY_ROTATION_DEGREES}-degree rotation..."
    if [ -x "$SCRIPT_DIR/run.sh" ]; then
        "$SCRIPT_DIR/run.sh" rotate "$DISPLAY_ROTATION_DEGREES" >> /tmp/advertisement_startup.log 2>&1
        log "Rotation command executed (${DISPLAY_ROTATION_DEGREES} degrees)"
    else
        log "WARNING: $SCRIPT_DIR/run.sh not executable"
    fi
else
    log "ERROR: $SCRIPT_DIR/realrun.sh not executable or not found"
fi

log "Startup script completed"
