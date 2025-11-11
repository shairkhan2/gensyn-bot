#!/bin/bash
# Gensyn Safe Launcher - Prevents multiple screens and ensures clean start

SCREEN_NAME="gensyn"
BACKUP_DIR="/root/gensyn-bot/backup-userdata"
TARGET_DIR="/root/rl-swarm/modal-login/temp-data"
WORK_DIR="/root/rl-swarm"
LOG_FILE="/root/gensyn_launcher.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== Gensyn Launcher Started ==="

# Step 1: Kill any existing gensyn screens
log "Checking for existing gensyn screens..."
if screen -ls | grep -q "$SCREEN_NAME"; then
    log "Found existing gensyn screen(s), killing..."
    screen -S "$SCREEN_NAME" -X quit 2>/dev/null
    sleep 2
    
    # Force kill if still exists
    if screen -ls | grep -q "$SCREEN_NAME"; then
        log "Force killing stubborn screens..."
        pkill -9 -f "SCREEN.*$SCREEN_NAME" 2>/dev/null
        sleep 1
    fi
fi

# Step 2: Verify no screen exists
if screen -ls | grep -q "$SCREEN_NAME"; then
    log "ERROR: Failed to kill existing screen. Aborting."
    exit 1
fi

log "No existing screens found. Proceeding..."

# Step 3: Restore backup files
log "Restoring backup files..."
mkdir -p "$TARGET_DIR"

BACKUP_RESTORED=false
for file in userData.json userApiKey.json; do
    if [ -f "$BACKUP_DIR/$file" ]; then
        cp "$BACKUP_DIR/$file" "$TARGET_DIR/$file"
        if [ -f "$TARGET_DIR/$file" ]; then
            log "Restored: $file"
            BACKUP_RESTORED=true
        else
            log "WARNING: Failed to restore $file"
        fi
    else
        log "WARNING: Backup not found: $file"
    fi
done

if [ "$BACKUP_RESTORED" = true ]; then
    log "Backup restoration complete"
else
    log "WARNING: No backup files were restored"
fi

# Wait for filesystem sync
sleep 1

# Step 4: Final check before launch
if screen -ls | grep -q "$SCREEN_NAME"; then
    log "ERROR: Screen appeared during backup restore. Aborting."
    exit 1
fi

# Step 5: Launch Gensyn in screen
log "Launching Gensyn in screen session..."
cd "$WORK_DIR" || exit 1

screen -dmS "$SCREEN_NAME" bash -c "python3 -m venv .venv && source .venv/bin/activate && ./run_rl_swarm.sh"

# Step 6: Verify launch
sleep 2
if screen -ls | grep -q "$SCREEN_NAME"; then
    log "SUCCESS: Gensyn launched successfully"
    exit 0
else
    log "ERROR: Failed to launch Gensyn screen"
    exit 1
fi
