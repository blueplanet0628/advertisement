#!/bin/bash
# Systemd service setup script for advertisement player
# Alternative to cron - more reliable for GUI applications

SERVICE_FILE="advertisement.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_FILE"
AD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Setting up systemd service for advertisement player..."

# Check if we're running as root
if [ "$(id -u)" -ne 0 ]; then
    echo "This script must be run as root (sudo)"
    exit 1
fi

# Copy service file
cp "$AD_DIR/$SERVICE_FILE" "$SERVICE_PATH"
echo "✓ Service file copied to $SERVICE_PATH"

# Update service file with correct paths
sed -i "s|/home/pi/advertisement|$AD_DIR|g" "$SERVICE_PATH"

# Reload systemd
systemctl daemon-reload
echo "✓ Systemd reloaded"

# Enable the service
systemctl enable advertisement.service
echo "✓ Service enabled"

# Start the service
systemctl start advertisement.service
echo "✓ Service started"

# Show status
echo ""
echo "Service status:"
systemctl status advertisement.service --no-pager

echo ""
echo "To check logs:"
echo "journalctl -u advertisement.service -f"
echo ""
echo "To stop the service:"
echo "sudo systemctl stop advertisement.service"
echo ""
echo "To disable auto-start:"
echo "sudo systemctl disable advertisement.service"
