#!/bin/bash
# Gensyn Watchdog - Monitors and restarts if screen is missing

SCREEN_NAME="gensyn"
LAUNCHER="/root/gensyn-bot/gensyn_launcher.sh"
LOG_FILE="/root/gensyn_watchdog.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# Check if gensyn screen exists
if ! screen -ls | grep -q "$SCREEN_NAME"; then
    log "WARNING: Gensyn screen not found. Restarting..."
    "$LAUNCHER" >> "$LOG_FILE" 2>&1
    if [ $? -eq 0 ]; then
        log "SUCCESS: Gensyn restarted by watchdog"
    else
        log "ERROR: Watchdog failed to restart Gensyn"
    fi
else
    log "OK: Gensyn screen is running"
fi
