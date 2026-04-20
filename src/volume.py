import logging
import os
import platform
import subprocess

logger = logging.getLogger(__name__)


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

    def _run_checked(self, argv):
        try:
            subprocess.run(argv, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode(errors="replace").strip() if e.stderr else ""
            raise RuntimeError(
                f"{argv[0]} failed (exit {e.returncode}): {stderr or '(no stderr)'}"
            ) from e
        except FileNotFoundError as e:
            raise RuntimeError(f"{argv[0]} not found on PATH") from e

    def mute(self):
        """Mute system audio. Raises RuntimeError on failure."""
        if self.system == "darwin":
            self._run_checked(["osascript", "-e", "set volume with output muted"])
        elif self.system == "linux":
            if self.linux_cmd == "pactl":
                self._run_checked(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"])
            else:  # amixer
                self._run_checked(["amixer", "-q", "set", "Master", "mute"])
        elif self.system == "windows":
            self.volume_control.SetMute(1, None)

    def unmute(self):
        """Unmute system audio. Raises RuntimeError on failure."""
        if self.system == "darwin":
            self._run_checked(["osascript", "-e", "set volume without output muted"])
        elif self.system == "linux":
            if self.linux_cmd == "pactl":
                self._run_checked(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"])
            else:  # amixer
                self._run_checked(["amixer", "-q", "set", "Master", "unmute"])
        elif self.system == "windows":
            self.volume_control.SetMute(0, None)
