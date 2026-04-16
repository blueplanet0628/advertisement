#!/usr/bin/env bash
set -euo pipefail

# Function to check if a package exists in the repository
package_exists() {
    apt-cache show "$1" &>/dev/null
}

# Function to get the correct package name (tries t64 first, falls back to non-t64)
get_package_name() {
    local base_name="$1"
    if package_exists "${base_name}t64"; then
        echo "${base_name}t64"
    elif package_exists "${base_name}"; then
        echo "${base_name}"
    else
        echo "${base_name}"  # Return original if neither exists
    fi
}

echo "🔧 Step 1: Update system packages..."
sudo apt update

echo "📦 Step 2: Install Python 3, pip, and venv..."
sudo apt install -y python3 python3-pip python3-venv

echo ""
echo "🐍 Step 3: Creating virtual environment..."
# Ensure current directory is writable by the current user
sudo chown -R $USER:$USER "$(pwd)"

# Remove any existing venv to avoid permission conflicts
rm -rf venv

# Create virtual environment with system site packages
python3 -m venv --system-site-packages venv
echo "✓ Virtual environment created at ./venv"
echo ""

echo "📚 Step 4: Installing system dependencies..."
echo "   → Installing PyQt5 system packages..."
sudo apt install -y python3-pyqt5 pyqt5-dev-tools

echo "   → Installing OpenCV system dependencies..."
# Auto-detect correct package name for this distribution
GLIB_PKG=$(get_package_name "libglib2.0-0")
echo "      (Using $GLIB_PKG for this system)"
sudo apt install -y libgl1 "$GLIB_PKG" \
                    libavcodec-extra libavformat-dev libswscale-dev

echo "   → Installing FFmpeg libraries for audio-video sync..."
sudo apt install -y ffmpeg libavutil-dev libavcodec-dev libavformat-dev \
                    libswresample-dev libavfilter-dev libavdevice-dev \
                    libsdl2-dev libsdl2-mixer-2.0-0

echo "   → Installing X11 libraries for Qt GUI..."
sudo apt install -y libxcb-xinerama0 libx11-xcb1 libxkbcommon-x11-0 libxcb-icccm4 \
                    libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
                    libxcb-shape0 libxcb-sync1 libxcb-xfixes0 libxrender1

echo "   → Installing Qt5 core libraries..."
sudo apt install -y libqt5gui5 libqt5core5a libqt5widgets5 libqt5opengl5 \
                    libqt5x11extras5 libqt5dbus5 libqt5network5

echo "   → Installing Qt5 Multimedia for video playback..."
sudo apt install -y libqt5multimedia5 libqt5multimedia5-plugins python3-pyqt5.qtmultimedia \
                    qtmultimedia5-dev

echo "   → Installing GStreamer multimedia framework..."
sudo apt install -y gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
                    gstreamer1.0-plugins-bad gstreamer1.0-libav gstreamer1.0-alsa \
                    gstreamer1.0-pulseaudio gstreamer1.0-x libgstreamer1.0-0 \
                    libgstreamer-plugins-base1.0-0

echo "   → Installing additional video codec libraries..."
sudo apt install -y libx264-dev libx265-dev libvpx-dev libopus-dev

echo ""
echo "⚡ Step 5: Setting up Python environment..."
source venv/bin/activate

echo "   → Upgrading pip..."
pip install --upgrade pip

echo "   → Replacing OpenCV with headless version..."
pip uninstall -y opencv-python || true
pip install opencv-python-headless==4.12.0.88

echo "   → Installing remaining Python requirements..."
pip install -r requirements.txt

echo ""
echo "✅ Setup complete! Virtual environment is ready at ./venv"
