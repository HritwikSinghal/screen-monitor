# This is a sample Python script.

# Press ⌃R to execute it or replace it with your code.
# Press Double ⇧ to search everywhere for classes, files, tool windows, actions, and settings.

import numpy as np
import pyautogui
import time
from PIL import Image
import cv2
import platform
import subprocess
import os


class VolumeController:
    def __init__(self):
        self.system = platform.system().lower()

        if self.system == "darwin":  # macOS
            # Check if osascript is available
            if not self._command_exists("osascript"):
                raise RuntimeError("osascript not found. Required for macOS volume control.")

        elif self.system == "linux":
            # Check if pactl or amixer is available
            if self._command_exists("pactl"):
                self.linux_cmd = "pactl"
            elif self._command_exists("amixer"):
                self.linux_cmd = "amixer"
            else:
                raise RuntimeError("Neither pactl nor amixer found. Install pulseaudio or alsa-utils.")

        elif self.system == "windows":
            try:
                from ctypes import cast, POINTER
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                self.volume_control = cast(interface, POINTER(IAudioEndpointVolume))
            except ImportError:
                raise RuntimeError("pycaw not found. Install it using: pip install pycaw")
        else:
            raise RuntimeError(f"Unsupported operating system: {self.system}")

    def _command_exists(self, cmd):
        """Check if a command exists in the system"""
        return any(
            os.access(os.path.join(path, cmd), os.X_OK)
            for path in os.environ["PATH"].split(os.pathsep)
        )

    def mute(self):
        """Mute system audio"""
        try:
            if self.system == "darwin":  # macOS
                subprocess.run(["osascript", "-e", "set volume with output muted"])

            elif self.system == "linux":
                if self.linux_cmd == "pactl":
                    subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"])
                else:  # amixer
                    subprocess.run(["amixer", "-q", "set", "Master", "mute"])

            elif self.system == "windows":
                self.volume_control.SetMute(1, None)

        except Exception as e:
            print(f"Error while muting: {e}")

    def unmute(self):
        """Unmute system audio"""
        try:
            if self.system == "darwin":  # macOS
                subprocess.run(["osascript", "-e", "set volume without output muted"])

            elif self.system == "linux":
                if self.linux_cmd == "pactl":
                    subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"])
                else:  # amixer
                    subprocess.run(["amixer", "-q", "set", "Master", "unmute"])

            elif self.system == "windows":
                self.volume_control.SetMute(0, None)

        except Exception as e:
            print(f"Error while unmuting: {e}")


def capture_screen():
    """Capture the screen and return as numpy array"""
    screenshot = pyautogui.screenshot()
    return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)


def load_target_image(image_path):
    """Load and prepare the target image"""
    target_img = cv2.imread(image_path)
    if target_img is None:
        raise ValueError(f"Could not load image from {image_path}")
    return target_img


def check_image_presence(screen, target_img, threshold=0.8):
    """
    Check if target image is present in screen
    Returns: True if image is found, False otherwise
    """
    result = cv2.matchTemplate(screen, target_img, cv2.TM_CCOEFF_NORMED)
    return np.max(result) >= threshold


def main():
    # Initialize volume control
    try:
        volume_control = VolumeController()
    except RuntimeError as e:
        print(f"Error initializing volume control: {e}")
        return

    # Load the target image
    try:
        target_img = load_target_image('target_image.png')
    except ValueError as e:
        print(f"Error loading target image: {e}")
        return

    print("Monitoring started. Press Ctrl+C to stop.")
    was_muted = False

    try:
        while True:
            # Capture screen
            screen = capture_screen()

            # Check for image presence
            image_present = check_image_presence(screen, target_img)

            # Control volume based on image presence
            if not image_present and not was_muted:
                volume_control.mute()
                print("Target image not found - Audio muted")
                was_muted = True
            elif image_present and was_muted:
                volume_control.unmute()
                print("Target image found - Audio unmuted")
                was_muted = False

            # Wait for 0.1 second before next check
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nMonitoring stopped by user")
        # Ensure audio is unmuted when stopping
        volume_control.unmute()
    except Exception as e:
        print(f"An error occurred: {e}")
        # Ensure audio is unmuted on error
        volume_control.unmute()


if __name__ == "__main__":
    main()
