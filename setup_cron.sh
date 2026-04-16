#!/bin/bash
# Cron setup script for advertisement player auto-start
# This script adds a cron job to start the advertisement player on boot

# Get the absolute path to the advertisement directory
AD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_PATH="$AD_DIR/start_advertisement.sh"

# Check if script exists
if [ ! -f "$SCRIPT_PATH" ]; then
    echo "Error: $SCRIPT_PATH not found!"
    exit 1
fi

echo "Setting up cron job for advertisement player auto-start..."
echo "Script path: $SCRIPT_PATH"

# Create a temporary cron file
TEMP_CRON=$(mktemp)

# Export current crontab
crontab -l > "$TEMP_CRON" 2>/dev/null || true

# Check if our cron job already exists
if grep -q "start_advertisement.sh" "$TEMP_CRON"; then
    echo "Cron job already exists. Removing old one..."
    # Remove existing advertisement cron jobs
    sed -i '/start_advertisement\.sh/d' "$TEMP_CRON"
    sed -i '/Advertisement player/d' "$TEMP_CRON"
fi

# Add the new cron job
echo "# Advertisement player auto-start (waits for GUI to be ready)" >> "$TEMP_CRON"
echo "@reboot $SCRIPT_PATH" >> "$TEMP_CRON"

# Install the new crontab
crontab "$TEMP_CRON"
echo "✓ Cron job added successfully!"
echo "The advertisement player will start automatically after reboot when GUI is ready."

# Clean up
rm -f "$TEMP_CRON"

# Show current crontab for verification
echo ""
echo "Current crontab entries:"
crontab -l

echo ""
echo "To test the cron job manually:"
echo "$SCRIPT_PATH"
echo ""
echo "To remove the cron job, run: crontab -r"
