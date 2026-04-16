#!/bin/bash
# Cron-safe wrapper for advertisement playlist
# Logs to: /tmp/realrun_YYYY-MM-DD_HH-MM-SS.log

# Fail fast on errors
set -euo pipefail

# Change to repo directory (critical for cron)
# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || { echo "ERROR: Cannot cd to $SCRIPT_DIR"; exit 1; }

# Ensure minimal environment for GUI apps under cron
export DISPLAY="${DISPLAY:-:0}"
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

# Log file with timestamp
LOG_FILE="/tmp/realrun_$(date +%Y-%m-%d_%H-%M-%S).log"

# Log wrapper function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "=== Playlist Starting ==="
log "Working directory: $(pwd)"
log "DISPLAY=$DISPLAY PATH=$PATH"

# Run playlist (each command logs to the main log)
{
    ./run.sh start ./data/background.jpg
    ./run.sh play ./data/test1.mp4 60
    ./run.sh play ./data/test1.jpg 1
    ./run.sh play ./data/test2.jpg 1
    ./run.sh play ./data/test2.mp4 20
    ./run.sh play ./data/test3.jpg 5
    ./run.sh stop
    ./run.sh exit
} 2>&1 | tee -a "$LOG_FILE"

log "=== Playlist Complete ==="

# Cleanup old logs (keep last 7 days)
find /tmp -name "realrun_*.log" -type f -mtime +7 -delete 2>/dev/null || true
