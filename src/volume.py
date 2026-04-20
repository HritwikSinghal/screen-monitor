import logging
import platform
import shutil
import subprocess

logger = logging.getLogger(__name__)


class VolumeController:
    def __init__(self):
        self.system = platform.system().lower()

        if self.system == "darwin":
            if shutil.which("osascript") is None:
                raise RuntimeError(
                    "osascript not found. Required for macOS volume control."
                )

        elif self.system == "linux":
            if shutil.which("pactl"):
                self.linux_cmd = "pactl"
            elif shutil.which("amixer"):
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
            except ImportError as e:
                raise RuntimeError(
                    "pycaw not found. Install it using: pip install pycaw"
                ) from e
        else:
            raise RuntimeError(f"Unsupported operating system: {self.system}")

    def _run_checked(self, argv):
        try:
            subprocess.run(
                argv, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
            )
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode(errors="replace").strip() if e.stderr else ""
            raise RuntimeError(
                f"{argv[0]} failed (exit {e.returncode}): {stderr or '(no stderr)'}"
            ) from e
        except FileNotFoundError as e:
            raise RuntimeError(f"{argv[0]} not found on PATH") from e

    def _set_mute(self, muted: bool) -> None:
        if self.system == "darwin":
            flag = "with" if muted else "without"
            self._run_checked(["osascript", "-e", f"set volume {flag} output muted"])
        elif self.system == "linux":
            if self.linux_cmd == "pactl":
                self._run_checked(
                    ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if muted else "0"]
                )
            else:  # amixer
                self._run_checked(
                    ["amixer", "-q", "set", "Master", "mute" if muted else "unmute"]
                )
        elif self.system == "windows":
            self.volume_control.SetMute(1 if muted else 0, None)

    def mute(self):
        """Mute system audio. Raises RuntimeError on failure."""
        self._set_mute(True)

    def unmute(self):
        """Unmute system audio. Raises RuntimeError on failure."""
        self._set_mute(False)
