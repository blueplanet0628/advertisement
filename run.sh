#!/bin/bash
# Video Player Launcher Script for Ubuntu/Raspberry Pi
# Supports: start, play, stop, exit commands

# Set strict error handling
set -euo pipefail

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Auto-detect and use virtual environment if available
if [ -d "$SCRIPT_DIR/venv" ] && [ -f "$SCRIPT_DIR/venv/bin/python3" ]; then
    PYTHON_CMD="$SCRIPT_DIR/venv/bin/python3"
    echo "Using virtual environment: $SCRIPT_DIR/venv"
else
    PYTHON_CMD="python3"
    echo "Warning: Virtual environment not found. Using system Python."
fi

# Configuration
MAIN_SCRIPT="run.py"

# Fix Qt platform plugin issues
export QT_QPA_PLATFORM_PLUGIN_PATH=""
export QT_DEBUG_PLUGINS=0
unset QT_PLUGIN_PATH

# Ensure DISPLAY is set (default to physical :0)
if [ -z "${DISPLAY:-}" ]; then
    export DISPLAY=:0
fi

# If running as root from cron, wire this process to the active desktop session
if [ "$(id -u)" -eq 0 ]; then
    # Try to detect the active graphical user (seat0) and its UID
    DESKTOP_USER=""
    DESKTOP_UID=""

    if command -v loginctl >/dev/null 2>&1; then
        # Pick the first active session on seat0 (common for local console)
        SESSION_LINE="$(loginctl list-sessions --no-legend 2>/dev/null | awk '$3=="seat0" && $2!="" {print; exit}')"
        if [ -n "$SESSION_LINE" ]; then
            DESKTOP_UID="$(echo "$SESSION_LINE" | awk '{print $2}')"
            DESKTOP_USER="$(id -nu "$DESKTOP_UID" 2>/dev/null || true)"
        fi
        # Fallback: take any active session
        if [ -z "$DESKTOP_USER" ]; then
            SESSION_LINE="$(loginctl list-sessions --no-legend 2>/dev/null | awk '$1!="" {print; exit}')"
            if [ -n "$SESSION_LINE" ]; then
                DESKTOP_UID="$(echo "$SESSION_LINE" | awk '{print $2}')"
                DESKTOP_USER="$(id -nu "$DESKTOP_UID" 2>/dev/null || true)"
            fi
        fi
    fi

    # Additional fallbacks when loginctl isn't helpful
    if [ -z "$DESKTOP_USER" ]; then
        # User owning the console often maps to the active desktop user
        if [ -e /dev/console ]; then
            DESKTOP_USER="$(stat -c '%U' /dev/console 2>/dev/null || true)"
        fi
    fi
    if [ -n "$DESKTOP_USER" ] && [ -z "$DESKTOP_UID" ]; then
        DESKTOP_UID="$(id -u "$DESKTOP_USER" 2>/dev/null || true)"
    fi

    # Wire X11 auth to the desktop user's authority cookie
    if [ -z "${XAUTHORITY:-}" ] && [ -n "$DESKTOP_USER" ]; then
        # Common location
        if [ -f "/home/$DESKTOP_USER/.Xauthority" ]; then
            export XAUTHORITY="/home/$DESKTOP_USER/.Xauthority"
        fi
        # Snap/Ubuntu variants sometimes place it under XDG_RUNTIME_DIR
        if [ -z "${XAUTHORITY:-}" ] && [ -n "$DESKTOP_UID" ] && [ -f "/run/user/$DESKTOP_UID/gdm/Xauthority" ]; then
            export XAUTHORITY="/run/user/$DESKTOP_UID/gdm/Xauthority"
        fi
    fi

    # Set XDG runtime and DBus session (needed by many desktops)
    if [ -n "$DESKTOP_UID" ]; then
        export XDG_RUNTIME_DIR="/run/user/$DESKTOP_UID"
        if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ] && [ -S "/run/user/$DESKTOP_UID/bus" ]; then
            export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$DESKTOP_UID/bus"
        fi
    fi

    # Force Qt to use X11/XWayland when DISPLAY is present
    if [ -n "${DISPLAY:-}" ]; then
        export QT_QPA_PLATFORM="xcb"
    fi

    # Helpful diagnostics (only when interactive shell has a TTY)
    if [ -t 1 ]; then
        echo "Running as root; bound to desktop user: ${DESKTOP_USER:-unknown} (UID: ${DESKTOP_UID:-?})"
        echo "DISPLAY=${DISPLAY:-unset} XAUTHORITY=${XAUTHORITY:-unset} DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-unset}"
    fi
fi

# Function to show usage
show_usage() {
    echo "Video Player Launcher"
    echo "====================="
    echo "Usage:"
    echo "  $0 start <background_image>  - Start GUI with background (auto-restart if running)"
    echo "  $0 play <file> <duration>    - Play file for duration seconds"
    echo "  $0 stop                      - Stop playback and return to background"
    echo "  $0 rotate <angle>            - Rotate display: 0, 90, 180, or 270 degrees"
    echo "  $0 exit                      - Exit GUI"
    echo ""
    echo "Examples:"
    echo "  sudo -u pi $0 start /home/pi/background.jpg"
    echo "  sudo -u pi $0 play /home/pi/data/test1.mp4 10"
    echo "  sudo -u pi $0 rotate 90"
    echo "  sudo -u pi $0 stop"
    echo "  sudo -u pi $0 exit"
    echo ""
}

# Check if script exists
if [ ! -f "$MAIN_SCRIPT" ]; then
    echo "Error: $MAIN_SCRIPT not found in $SCRIPT_DIR"
    exit 1
fi

# Check arguments
if [ $# -lt 1 ]; then
    show_usage
    exit 1
fi

COMMAND="$1"

# Handle commands
case "$COMMAND" in
    "start")
        if [ $# -lt 2 ]; then
            echo "Error: background image path required"
            show_usage
            exit 1
        fi
        BACKGROUND_IMAGE="$2"

        # Validate background image exists
        if [ ! -f "$BACKGROUND_IMAGE" ]; then
            echo "Warning: Background image '$BACKGROUND_IMAGE' not found"
            # Continue anyway - run.py will handle it
        fi

        echo "Starting Video Player GUI with background: $BACKGROUND_IMAGE"

        # --single-instance flag will auto-restart if already running
        # Run in background (temporarily logging to /tmp for debugging)
        "$PYTHON_CMD" "$MAIN_SCRIPT" --start "$BACKGROUND_IMAGE" --single-instance > /tmp/video_player_stdout.log 2> /tmp/video_player_stderr.log &
        GUI_PID=$!

        # Actively wait for IPC readiness instead of a fixed sleep
        SOCKET="/tmp/video_player_ipc.sock"
        READY_WAIT_SECS=15
        start_ts=$(date +%s)

        while true; do
            # Break if process died during startup
            if ! ps -p $GUI_PID > /dev/null 2>&1; then
                echo "ERROR: GUI process exited during startup"
                exit 1
            fi

            # Socket present and accepting connections?
            if [ -S "$SOCKET" ]; then
                if "$PYTHON_CMD" - <<'PY'
import socket, json, sys
SOCK = "/tmp/video_player_ipc.sock"
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(0.5)
try:
    s.connect(SOCK)
    s.send(json.dumps({"command": "PING"}).encode("utf-8"))
    try:
        _ = s.recv(2)
    except Exception:
        pass
    sys.exit(0)
except Exception:
    sys.exit(1)
finally:
    try:
        s.close()
    except Exception:
        pass
PY
                then
                    echo "GUI ready (IPC up)"
                    break
                fi
            fi

            # Timeout handling
            if [ $(( $(date +%s) - start_ts )) -ge $READY_WAIT_SECS ]; then
                echo "WARNING: GUI started but IPC not ready after ${READY_WAIT_SECS}s"
                break
            fi
            sleep 0.2
        done

        # Final confirmation
        if ps -p $GUI_PID > /dev/null 2>&1; then
            echo "GUI started successfully (PID: $GUI_PID)"
        else
            echo "ERROR: GUI failed to start!"
            exit 1
        fi
        ;;

    "play")
        if [ $# -lt 3 ]; then
            echo "Error: file path and duration required"
            show_usage
            exit 1
        fi
        FILE_PATH="$2"
        DURATION="$3"

        # Validate file exists
        if [ ! -f "$FILE_PATH" ]; then
            echo "Error: File '$FILE_PATH' not found"
            exit 1
        fi

        # Validate duration is a number
        if ! [[ "$DURATION" =~ ^[0-9]+$ ]]; then
            echo "Error: Duration must be a positive integer (seconds)"
            exit 1
        fi

        echo "Playing: $FILE_PATH for $DURATION seconds"
        "$PYTHON_CMD" "$MAIN_SCRIPT" --play "$FILE_PATH" "$DURATION" --single-instance
        ;;

    "stop")
        echo "Stopping playback..."
        "$PYTHON_CMD" "$MAIN_SCRIPT" --stop
        echo "Playback stopped. Returned to background."
        ;;

    "rotate")
        if [ $# -lt 2 ]; then
            echo "Error: rotation angle required (0, 90, 180, or 270)"
            show_usage
            exit 1
        fi
        ANGLE="$2"

        # Validate angle is one of the allowed values
        if ! [[ "$ANGLE" =~ ^(0|90|180|270)$ ]]; then
            echo "Error: Rotation angle must be 0, 90, 180, or 270"
            exit 1
        fi

        echo "Setting rotation to $ANGLE degrees..."
        "$PYTHON_CMD" "$MAIN_SCRIPT" --rotate "$ANGLE"
        ;;

    "exit")
        echo "Exiting GUI..."
        "$PYTHON_CMD" "$MAIN_SCRIPT" --exit

        # Wait for clean shutdown
        sleep 0.5
        echo "GUI closed."
        ;;

    *)
        echo "Error: Unknown command '$COMMAND'"
        show_usage
        exit 1
        ;;
esac

exit 0
