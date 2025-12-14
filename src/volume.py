import os
import platform
import subprocess


class VolumeController:
    def __init__(self):
        self.system = platform.system().lower()

        if self.system == "darwin":  # macOS
            # Check if osascript is available
            if not self._command_exists("osascript"):
                raise RuntimeError(
                    "osascript not found. Required for macOS volume control."
                )

        elif self.system == "linux":
            # Check if pactl or amixer is available
            if self._command_exists("pactl"):
                self.linux_cmd = "pactl"
            elif self._command_exists("amixer"):
                self.linux_cmd = "amixer"
            else:
                raise RuntimeError(
                    "Neither pactl nor amixer found. Install pulseaudio or alsa-utils."
                )

        elif self.system == "windows":
            try:
                from ctypes import cast, POINTER
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(
                    IAudioEndpointVolume._iid_, CLSCTX_ALL, None
                )
                self.volume_control = cast(interface, POINTER(IAudioEndpointVolume))
            except ImportError:
                raise RuntimeError(
                    "pycaw not found. Install it using: pip install pycaw"
                )
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
