"""
HD Video Advertisement Player - H.264 Optimized
================================================

Performance Optimizations:
- H.264 hardware-accelerated video decoding (VAAPI/VDPAU/DXVA2)
- Multi-threaded frame decoding for reduced CPU load
- Zero-copy frame processing where possible
- High-quality scaling with Qt SmoothTransformation
- Optimized A/V synchronization with adaptive frame dropping
- Efficient memory management with frame caching
- Qt rendering optimizations for smooth HD playback

This player provides smooth, high-definition video playback with minimal
CPU overhead by leveraging hardware acceleration and efficient algorithms.
"""

import sys
import os
import socket
import json
import argparse
from pathlib import Path
from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow, QGraphicsOpacityEffect
from PyQt5.QtCore import QTimer, Qt, QThread, pyqtSignal, QPropertyAnimation, QEasingCurve, QSocketNotifier
from PyQt5.QtGui import QPixmap, QImage, QImageReader, QColorSpace, QTransform
import cv2
import numpy as np
from ffpyplayer.player import MediaPlayer
import time


# IPC Configuration
IPC_SOCKET_PATH = '/tmp/video_player_ipc.sock'
IPC_PORT = 45678


class VideoThread(QThread):
    """
    Thread for smooth HD video playback with H.264 hardware acceleration

    Features:
    - Hardware-accelerated H.264 decoding
    - Multi-threaded frame processing
    - Synchronized audio playback
    - Efficient memory management
    """
    frame_ready = pyqtSignal(np.ndarray)
    playback_finished = pyqtSignal(np.ndarray)

    def __init__(self, video_path, duration=0):
        super().__init__()
        self.video_path = video_path
        self.duration = duration
        self.running = True
        self.player = None

    def run(self):
        """Play video with synchronized audio - QQ Player style smooth playback"""
        try:
            # Create MediaPlayer with H.264 hardware acceleration and optimized settings
            ff_opts = {
                'paused': False,
                'autoexit': False,
                # Hardware acceleration for H.264 (reduces CPU load significantly)
                'vcodec': 'h264',  # Prefer H.264 codec
                'hwaccel': 'auto',  # Auto-detect hardware acceleration (VAAPI/VDPAU/DXVA2)
                # Threading optimizations
                'threads': '4',  # Multi-threaded decoding
                'thread_type': 'frame',  # Frame-level threading for better performance
                # High-quality output settings
                'flags': 'low_delay',  # Low latency decoding
                # NOTE: Removed 'flags2': 'fast' to avoid lower-quality decode shortcuts
                # Frame dropping prevention
                'framedrop': False,  # Don't drop frames for quality
                # Buffering optimizations
                'analyzeduration': '1000000',  # 1 second analysis (faster startup)
                'probesize': '5000000',  # 5MB probe size (balanced)
                # High-quality scaling for RGB conversion (libswscale)
                'sws_flags': 'lanczos+accurate_rnd+full_chroma_int',  # Best chroma and scaling quality
                # Audio initialization optimizations
                'sync': 'audio',  # Sync to audio stream for better A/V sync
            }

            self.player = MediaPlayer(self.video_path, ff_opts=ff_opts)
            
            # CRITICAL: Set volume to 100% immediately to prevent audio cutoff
            # Without this, audio may start at 0 or very low volume
            try:
                self.player.set_volume(1.0)
                print("Audio volume set to 100%")
            except Exception as e:
                print(f"Warning: Could not set volume: {e}")
            
            # Wait briefly for audio device initialization to prevent startup cutoff
            # This ensures audio is ready before playback starts
            time.sleep(0.1)  # 100ms initialization delay for audio device

            start_time = time.time()
            last_frame = None
            frame_count = 0

            # Performance tracking for smooth playback
            last_pts = 0
            audio_pts = 0
            behind_streak = 0

            print(f"Starting smooth playback: {self.video_path}")

            # Main playback loop - synchronized to audio
            while self.running:
                # Check duration limit
                if self.duration > 0:
                    elapsed = time.time() - start_time
                    if elapsed >= self.duration:
                        print(f"Duration limit reached: {elapsed:.2f}s")
                        break

                # Get frame with timing info
                frame_data, val = self.player.get_frame()

                if val == 'eof':
                    print("End of file reached")
                    break
                elif val == 'paused':
                    time.sleep(0.01)
                    continue

                if frame_data is None:
                    # No frame ready yet, small wait
                    time.sleep(0.002)
                    continue

                # Extract image and presentation timestamp
                img, pts = frame_data

                if img is None:
                    continue

                # Get audio/video sync info
                audio_pts = self.player.get_pts()

                # Convert image to numpy array (RGB format) - OPTIMIZED
                try:
                    width, height = img.get_size()
                    buf = img.to_bytearray()[0]
                    # Single copy operation - more efficient memory usage
                    # Using np.frombuffer with copy for thread safety
                    frame_rgb = np.frombuffer(buf, dtype=np.uint8).reshape(height, width, 3).copy()

                    # Emit frame for display (no additional copies)
                    last_frame = frame_rgb
                    self.frame_ready.emit(frame_rgb)
                    frame_count += 1

                except Exception as e:
                    print(f"Frame conversion error: {e}")
                    continue

                # A/V sync: Calculate delay based on audio position (OPTIMIZED)
                if audio_pts > 0 and pts > 0:
                    delay = pts - audio_pts

                    # Smooth sync adjustment with adaptive frame drop for performance
                    if delay > 0.002:  # Video ahead of audio (>2ms)
                        # Sleep proportionally but cap to reduce jitter
                        sleep_time = min(delay * 0.8, 0.04)  # 80% of delay, max 40ms
                        time.sleep(sleep_time)
                        behind_streak = 0
                    elif delay < -0.015:  # Video behind audio (>15ms)
                        behind_streak += 1
                        if behind_streak >= 3:
                            # Skip frame to catch up and reduce CPU load
                            continue
                    else:
                        # In sync - minimal sleep to yield CPU
                        behind_streak = 0
                        time.sleep(0.0005)
                else:
                    # No audio sync available, minimal sleep to avoid busy loop
                    time.sleep(0.0008)

                last_pts = pts

            print(f"Playback finished: {frame_count} frames, {time.time() - start_time:.2f}s")

        except Exception as e:
            print(f"Playback error: {e}")
            import traceback
            traceback.print_exc()

        finally:
            # Clean shutdown
            if self.player:
                try:
                    self.player.close_player()
                except:
                    pass
                self.player = None

            # Send last frame
            if last_frame is not None:
                self.playback_finished.emit(last_frame)
            else:
                self.playback_finished.emit(np.array([]))

    def stop(self):
        """Stop playback"""
        self.running = False
        if self.player:
            try:
                self.player.close_player()
            except:
                pass
            self.player = None


class IPCServerThread(QThread):
    """Thread for handling IPC socket server"""
    command_received = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.running = True
        self.server_socket = None

    def run(self):
        """Run IPC server"""
        try:
            # Create Unix domain socket
            if os.path.exists(IPC_SOCKET_PATH):
                os.remove(IPC_SOCKET_PATH)

            self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server_socket.bind(IPC_SOCKET_PATH)
            self.server_socket.listen(5)
            self.server_socket.settimeout(1.0)  # Timeout for checking self.running

            print(f"IPC Server listening on {IPC_SOCKET_PATH}")

            while self.running:
                try:
                    client_socket, _ = self.server_socket.accept()
                    data = client_socket.recv(4096).decode('utf-8')

                    if data:
                        try:
                            command = json.loads(data)
                            print(f"Received command: {command}")
                            self.command_received.emit(command)

                            # Send acknowledgment
                            client_socket.send(b"OK")
                        except json.JSONDecodeError as e:
                            print(f"Invalid JSON: {e}")
                            client_socket.send(b"ERROR")

                    client_socket.close()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"IPC error: {e}")

        except Exception as e:
            print(f"IPC server error: {e}")
        finally:
            if self.server_socket:
                self.server_socket.close()
            if os.path.exists(IPC_SOCKET_PATH):
                os.remove(IPC_SOCKET_PATH)

    def stop(self):
        """Stop IPC server"""
        self.running = False


class AdPlayerWindow(QMainWindow):
    def __init__(self, background_image=None):
        super().__init__()

        self.background_image = background_image
        self.current_file = None
        self.video_thread = None
        self.is_transitioning = False
        self.pending_command = None
        self.is_playing_media = False  # Track if actively playing media
        self.rotation_angle = 90  # Image rotation angle: 0, 90, 180, or 270 degrees

        # Setup window with optimized rendering for smooth playback
        self.setWindowTitle('HD Video Player - H.264 Optimized')

        # Enable optimized rendering attributes for smooth HD video playback
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WA_NoSystemBackground, False)
        self.setAttribute(Qt.WA_DontCreateNativeAncestors, True)
        self.setAttribute(Qt.WA_NativeWindow, True)
        # Additional performance optimizations for HD content
        self.setAttribute(Qt.WA_PaintOnScreen, False)  # Use off-screen buffer for smoother rendering
        self.setAttribute(Qt.WA_StaticContents, True)  # Content doesn't change unless we update it

        self.showFullScreen()

        # Create label for displaying content with performance optimization
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("background-color: black;")
        self.label.setScaledContents(False)  # Manual scaling for control
        self.setCentralWidget(self.label)

        # Setup opacity effect for smooth transitions
        self.opacity_effect = QGraphicsOpacityEffect(self.label)
        self.label.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(1.0)

        # Setup fade animation (150ms transition)
        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_animation.setDuration(150)
        self.fade_animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.fade_animation.finished.connect(self.on_fade_finished)

        # Timer for media display
        self.media_timer = QTimer()
        self.media_timer.timeout.connect(self.on_media_timeout)

        # Start IPC server
        self.ipc_thread = IPCServerThread()
        self.ipc_thread.command_received.connect(self.handle_ipc_command)
        self.ipc_thread.start()

        # Delay background display until window is fully initialized
        if self.background_image and os.path.exists(self.background_image):
            QTimer.singleShot(100, self.display_initial_background)

    def display_initial_background(self):
        """Display initial background after window is fully initialized"""
        if self.background_image and os.path.exists(self.background_image):
            self.display_image(self.background_image, 0, is_background=True)

    def handle_ipc_command(self, command):
        """Handle commands received via IPC"""
        cmd_type = command.get('command')

        if cmd_type == 'PLAY':
            filepath = command.get('file')
            duration = command.get('duration', 0)
            if filepath:
                self.play_media(filepath, duration)

        elif cmd_type == 'STOP':
            # Ignore STOP commands during active media playback
            if self.is_playing_media:
                print("Ignoring STOP command - media is actively playing")
                return
            self.stop_playback(return_to_background=True)

        elif cmd_type == 'EXIT':
            self.close()

        elif cmd_type == 'ROTATE':
            # 機能3: 画像回転機能 (90°, 180°, 270°)
            angle = command.get('angle', 0)
            if angle in [0, 90, 180, 270]:
                self.rotation_angle = angle
                print(f"Rotation set to {angle} degrees")
                # Clear video cache to recalculate with new rotation
                if hasattr(self, '_cached_video_size'):
                    delattr(self, '_cached_video_size')
                # Refresh current display if something is showing
                if self.current_file and os.path.exists(self.current_file):
                    ext = Path(self.current_file).suffix.lower()
                    if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp']:
                        # Re-display current image with new rotation
                        self.display_image(self.current_file, 0, is_background=False)
            else:
                print(f"Invalid rotation angle: {angle}. Must be 0, 90, 180, or 270.")

    def display_image(self, image_path, duration, is_background=False):
        """Display image with smart full-screen sizing, aspect ratio preservation, and rotation support"""
        try:
            reader = QImageReader(image_path)
            reader.setAutoTransform(True)
            q_image = reader.read()
            if q_image.isNull():
                print(f"Error displaying image {image_path}: failed to load")
                return

            # Set sRGB color space for proper color reproduction
            try:
                q_image.setColorSpace(QColorSpace.SRgb)
            except Exception:
                pass  # Gracefully handle older Qt versions

            # Apply rotation if needed (before scaling to preserve quality)
            if self.rotation_angle != 0:
                transform = QTransform()
                transform.rotate(self.rotation_angle)
                q_image = q_image.transformed(transform, Qt.SmoothTransformation)

            # Get screen size - use actual screen geometry
            from PyQt5.QtWidgets import QApplication
            screen = QApplication.primaryScreen()
            screen_geometry = screen.geometry()
            screen_width = screen_geometry.width()
            screen_height = screen_geometry.height()

            # Fallback to label size if needed
            if screen_width <= 0 or screen_height <= 0:
                screen_size = self.label.size()
                screen_width = screen_size.width()
                screen_height = screen_size.height()

            # 元の画像サイズとアスペクト比を記録（デバッグ用）
            original_width = q_image.width()
            original_height = q_image.height()
            original_aspect = original_width / original_height if original_height > 0 else 0

            if is_background:
                # Fill screen while preserving aspect, then center-crop (high quality)
                scaled = q_image.scaled(screen_width, screen_height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                x = max(0, (scaled.width() - screen_width) // 2)
                y = max(0, (scaled.height() - screen_height) // 2)
                q_image = scaled.copy(x, y, screen_width, screen_height)
            else:
                # 機能1&2: モニターサイズに合わせて最大表示枠を決定し、アスペクト比を保持
                # Fit inside the screen with aspect preserved (high quality) - maximum display area
                q_image = q_image.scaled(screen_width, screen_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                
                # デバッグ情報: アスペクト比と最大表示枠の検証
                display_width = q_image.width()
                display_height = q_image.height()
                display_aspect = display_width / display_height if display_height > 0 else 0
                
                # アスペクト比が保持されているかチェック
                aspect_preserved = abs(original_aspect - display_aspect) < 0.001
                # 最大表示枠が使われているかチェック（幅または高さのいずれかがモニターサイズに近い）
                uses_max_area = (abs(display_width - screen_width) < 2) or (abs(display_height - screen_height) < 2)
                
                print(f"[画像表示検証] ファイル: {os.path.basename(image_path)}")
                print(f"  元のサイズ: {original_width}x{original_height} (アスペクト比: {original_aspect:.4f})")
                print(f"  モニター: {screen_width}x{screen_height} (アスペクト比: {screen_width/screen_height:.4f})")
                print(f"  表示サイズ: {display_width}x{display_height} (アスペクト比: {display_aspect:.4f})")
                print(f"  機能1(最大表示枠): {'✓' if uses_max_area else '✗'} 機能2(アスペクト比保持): {'✓' if aspect_preserved else '✗'}")

            pixmap = QPixmap.fromImage(q_image)
            self.label.setPixmap(pixmap)

            # Set timer if duration specified
            if duration > 0:
                self.media_timer.start(int(duration * 1000))
                if not is_background:
                    self.is_playing_media = True  # Mark as actively playing

        except Exception as e:
            print(f"Error displaying image {image_path}: {e}")

    def display_video(self, video_path, duration):
        """Display video with smart full-screen sizing"""
        try:
            # Stop any running video thread
            if self.video_thread and self.video_thread.isRunning():
                self.video_thread.stop()
                self.video_thread.wait()

            # Clear cached video size to recalculate for new video
            if hasattr(self, '_cached_video_size'):
                delattr(self, '_cached_video_size')
            if hasattr(self, '_cached_display_size'):
                delattr(self, '_cached_display_size')

            # Create and start video thread
            self.video_thread = VideoThread(video_path, duration)
            self.video_thread.frame_ready.connect(self.update_frame)
            self.video_thread.playback_finished.connect(self.on_video_finished)
            try:
                self.video_thread.setPriority(QThread.HighPriority)
            except Exception:
                pass
            self.is_playing_media = True  # Mark as actively playing
            self.video_thread.start()

        except Exception as e:
            print(f"Error displaying video {video_path}: {e}")

    def update_frame(self, frame):
        """Update display with new video frame - OPTIMIZED for smooth playback with HD quality, aspect ratio preservation, and rotation"""
        try:
            # Get frame dimensions
            height, width, channel = frame.shape

            # Account for rotation when calculating display size
            # If rotated 90 or 270 degrees, swap width and height for scaling calculations
            display_width = width
            display_height = height
            if self.rotation_angle in [90, 270]:
                display_width, display_height = display_height, display_width

            # Check if video resolution or rotation changed or cache doesn't exist
            cache_key = f"{width}x{height}_rot{self.rotation_angle}"
            if not hasattr(self, '_cached_video_size') or self._cached_video_size != cache_key:
                from PyQt5.QtWidgets import QApplication
                screen = QApplication.primaryScreen()
                screen_geometry = screen.geometry()
                screen_width = screen_geometry.width()
                screen_height = screen_geometry.height()

                # Fallback to label size if needed
                if screen_width <= 0 or screen_height <= 0:
                    screen_size = self.label.size()
                    screen_width = screen_size.width()
                    screen_height = screen_size.height()

                # 機能1&2: モニターサイズに合わせて最大表示枠を決定し、アスペクト比を保持
                # Calculate optimal scaling to fit full screen while maintaining aspect ratio
                scale = min(screen_width / display_width, screen_height / display_height)
                new_width = int(display_width * scale)
                new_height = int(display_height * scale)

                # Cache dimensions and scaling mode for this video resolution and rotation
                self._cached_video_size = cache_key
                self._cached_display_size = (new_width, new_height)
                # ALWAYS use SmoothTransformation for maximum quality (removes downscaling artifacts)
                self._cached_transform_mode = Qt.SmoothTransformation

                print(f"Video size adjusted: {width}x{height} → {new_width}x{new_height} (screen: {screen_width}x{screen_height}, scale: {scale:.2f}, rotation: {self.rotation_angle}°)")
            else:
                new_width, new_height = self._cached_display_size

            # Direct conversion to QImage - zero-copy when possible
            bytes_per_line_src = 3 * width
            # Use the frame data buffer directly without intermediate copies
            q_image_src = QImage(frame.data, width, height, bytes_per_line_src, QImage.Format_RGB888)

            # Set sRGB color space for proper color reproduction (avoids washed-out colors)
            try:
                q_image_src.setColorSpace(QColorSpace.SRgb)
            except Exception:
                pass  # Gracefully handle older Qt versions without full color space support

            # Apply rotation if needed (before scaling to preserve quality)
            if self.rotation_angle != 0:
                transform = QTransform()
                transform.rotate(self.rotation_angle)
                q_image_src = q_image_src.transformed(transform, Qt.SmoothTransformation)

            # High-quality scaling using cached transformation mode
            transform_mode = getattr(self, '_cached_transform_mode', Qt.SmoothTransformation)
            q_image_scaled = q_image_src.scaled(new_width, new_height, Qt.KeepAspectRatio, transform_mode)

            # Convert to pixmap and display
            pixmap = QPixmap.fromImage(q_image_scaled)
            self.label.setPixmap(pixmap)

        except Exception as e:
            print(f"Error updating frame: {e}")

    def play_media(self, filepath, duration):
        """Play media file with smooth transition"""
        if not os.path.exists(filepath):
            print(f"Warning: File not found: {filepath}")
            return

        print(f"Playing: {filepath} (duration: {duration}s)")

        # Stop current playback
        self.media_timer.stop()

        # Determine file type
        ext = Path(filepath).suffix.lower()
        is_image = ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp']

        # Store current file
        self.current_file = filepath

        # Fade out and switch
        if self.opacity_effect.opacity() > 0:
            self.pending_command = {'type': 'play', 'file': filepath, 'duration': duration, 'is_image': is_image}
            self.fade_out()
        else:
            # Direct play if already faded
            if is_image:
                self.display_image(filepath, duration, is_background=False)
            else:
                self.display_video(filepath, duration)
            self.fade_in()

    def stop_playback(self, return_to_background=True):
        """Stop current playback and optionally return to background"""
        print("Stopping playback...")

        # Clear playing flag
        self.is_playing_media = False

        # Stop timers
        self.media_timer.stop()

        # Stop video thread
        if self.video_thread and self.video_thread.isRunning():
            self.video_thread.stop()
            self.video_thread.wait()

        # Return to background only if explicitly requested
        if return_to_background and self.background_image and os.path.exists(self.background_image):
            self.pending_command = {'type': 'background'}
            self.fade_out()

    def on_media_timeout(self):
        """Called when media duration expires - stay on last frame"""
        # Don't return to background automatically
        # Just stop the timer and wait for next command
        self.media_timer.stop()
        self.is_playing_media = False  # Media playback finished
        print("Media duration completed")

    def on_video_finished(self, last_frame):
        """Called when video playback finishes - hold last frame cleanly"""
        # Don't return to background automatically
        # Display the last frame as a static image to prevent freezing
        self.is_playing_media = False  # Media playback finished
        if last_frame is not None and last_frame.size > 0:
            self.update_frame(last_frame)
            print("Video finished - holding last frame")
        else:
            print("Video finished - no frames captured")

    def fade_in(self):
        """Fade in current content"""
        self.fade_animation.setStartValue(0.0)
        self.fade_animation.setEndValue(1.0)
        self.fade_animation.start()

    def fade_out(self):
        """Fade out current content"""
        if self.is_transitioning:
            return

        self.is_transitioning = True

        # Stop video during transition
        if self.video_thread and self.video_thread.isRunning():
            self.video_thread.stop()
            self.video_thread.wait()

        self.fade_animation.setStartValue(1.0)
        self.fade_animation.setEndValue(0.0)
        self.fade_animation.start()

    def on_fade_finished(self):
        """Called when fade animation completes"""
        if self.pending_command:
            cmd = self.pending_command
            self.pending_command = None

            if cmd['type'] == 'play':
                # Switch to new content
                if cmd['is_image']:
                    self.display_image(cmd['file'], cmd['duration'], is_background=False)
                else:
                    self.display_video(cmd['file'], cmd['duration'])
                self.fade_in()
            elif cmd['type'] == 'background':
                # Return to background
                self.display_image(self.background_image, 0, is_background=True)
                self.fade_in()

        self.is_transitioning = False

    def keyPressEvent(self, event):
        """Handle key press"""
        if event.key() == Qt.Key_Q or event.key() == Qt.Key_Escape:
            self.close()

    def closeEvent(self, event):
        """Clean up on close"""
        # Stop IPC server
        if self.ipc_thread and self.ipc_thread.isRunning():
            self.ipc_thread.stop()
            self.ipc_thread.wait()

        # Stop video thread
        if self.video_thread and self.video_thread.isRunning():
            self.video_thread.stop()
            self.video_thread.wait()

        event.accept()


def send_ipc_command(command):
    """Send command to running instance via IPC"""
    try:
        client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client_socket.settimeout(2.0)
        client_socket.connect(IPC_SOCKET_PATH)

        # Send command
        client_socket.send(json.dumps(command).encode('utf-8'))

        # Wait for response
        response = client_socket.recv(1024).decode('utf-8')
        client_socket.close()

        return response == "OK"
    except Exception as e:
        print(f"IPC send error: {e}")
        return False


def is_instance_running():
    """Check if instance is already running"""
    return os.path.exists(IPC_SOCKET_PATH)


def kill_existing_instance():
    """Kill existing instance"""
    import subprocess
    import time

    try:
        # First try to send exit command via IPC
        if is_instance_running():
            print("Sending exit command to existing instance...")
            try:
                command = {'command': 'EXIT'}
                send_ipc_command(command)
                time.sleep(0.01)  # Wait for graceful shutdown
            except:
                pass

        # If still running, force kill (excluding current process)
        current_pid = os.getpid()
        result = subprocess.run(
            ["pgrep", "-f", "python.*run.py"],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                if pid and pid.strip() and int(pid) != current_pid:
                    print(f"Killing process {pid}...")
                    subprocess.run(["kill", "-9", pid], check=False)

        # Clean up socket
        if os.path.exists(IPC_SOCKET_PATH):
            os.remove(IPC_SOCKET_PATH)

        time.sleep(0.01)  # Wait for cleanup

    except Exception as e:
        print(f"Error killing instance: {e}")


def main():
    parser = argparse.ArgumentParser(description='Video Player with IPC Control')
    parser.add_argument('--start', metavar='BACKGROUND', help='Start GUI with background image')
    parser.add_argument('--play', nargs=2, metavar=('FILE', 'DURATION'), help='Play file with duration')
    parser.add_argument('--stop', action='store_true', help='Stop playback')
    parser.add_argument('--exit', action='store_true', help='Exit GUI')
    parser.add_argument('--rotate', type=int, metavar='ANGLE', choices=[0, 90, 180, 270], help='Rotate display: 0, 90, 180, or 270 degrees')
    parser.add_argument('--single-instance', action='store_true', help='Enable single instance mode')

    args = parser.parse_args()

    # Handle --start command
    if args.start:
        # Kill existing instance if single-instance mode
        if args.single_instance and is_instance_running():
            print("Existing instance found. Restarting...")
            kill_existing_instance()

        # Enable HiDPI scaling for high-resolution displays
        # Must be set BEFORE creating QApplication
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

        # Start new GUI instance
        app = QApplication(sys.argv)
        window = AdPlayerWindow(background_image=args.start)
        sys.exit(app.exec_())

    # Handle --play command
    elif args.play:
        import time
        filepath, duration = args.play
        duration = int(duration)

        if is_instance_running():
            command = {'command': 'PLAY', 'file': filepath, 'duration': duration}
            if send_ipc_command(command):
                print(f"Play command sent: {filepath}")

                # Give the GUI enough time to finish playback and its fade transitions
                transition_buffer = 0.45  # 150 ms fade-in + 150 ms fade-out + audio spin-up cushion
                wait_time = max(duration, 1) + transition_buffer
                print(f"Waiting {wait_time:.2f}s for playback to complete...")
                time.sleep(wait_time)
                print("Playback completed")
            else:
                print("Failed to send play command")
        else:
            print("No running instance found. Use --start first.")
            sys.exit(1)

    # Handle --stop command
    elif args.stop:
        if is_instance_running():
            command = {'command': 'STOP'}
            if send_ipc_command(command):
                print("Stop command sent")
            else:
                print("Failed to send stop command")
        else:
            print("No running instance found")

    # Handle --exit command
    elif args.exit:
        if is_instance_running():
            command = {'command': 'EXIT'}
            if send_ipc_command(command):
                print("Exit command sent")
            else:
                print("Failed to send exit command")
        else:
            print("No running instance found")

    # Handle --rotate command
    elif args.rotate is not None:
        if is_instance_running():
            command = {'command': 'ROTATE', 'angle': args.rotate}
            if send_ipc_command(command):
                print(f"Rotation set to {args.rotate} degrees")
            else:
                print("Failed to send rotate command")
        else:
            print("No running instance found. Use --start first.")

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
