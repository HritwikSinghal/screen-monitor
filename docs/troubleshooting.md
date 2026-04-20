# Troubleshooting

## Failure Modes

| Symptom | Root Cause | Fix |
|---------|------------|-----|
| Tool hangs for 180 seconds, then exits with `RuntimeError("Portal call timed out")` | Portal service (org.freedesktop.portal.Desktop) is not running or not responding | Start your desktop session (GNOME, KDE, etc.), or ensure the portal daemon is running: `systemctl --user status xdg-desktop-portal` |
| `RuntimeError: Failed to build GStreamer pipeline. Ensure 'gst-plugin-pipewire' and 'gst-plugins-good' are installed.` | Missing GStreamer plugins for PipeWire (src/capture.py:306-309) | Install `gst-plugin-pipewire` and `gst-plugins-good`: Arch `sudo pacman -S gst-plugin-pipewire gst-plugins-good`, Ubuntu `sudo apt install gstreamer1.0-plugins-good gstreamer1.0-pipewire` |
| `RuntimeError: No frame available from PipeWire stream (timeout)` | PipeWire node is stale or the stream died (src/capture.py:320) | Restart the tool; the stream will be re-established |
| Source picker reappears after it was shown on first run | Cached token was revoked (user disabled permission in GNOME Settings) OR compositor rejected the token after an upgrade | The tool automatically detects this, clears the cache, and shows the picker again (src/capture.py:174-177). No action needed. If you want to force re-prompting, delete `~/.local/share/screen-monitor/portal.json` |
| Manual token revocation needed | User wants to force a fresh picker on next run | Delete `~/.local/share/screen-monitor/portal.json` or (if XDG_DATA_HOME is set) `$XDG_DATA_HOME/screen-monitor/portal.json` |
| Linux volume control fails silently | `pactl` is missing (src/volume.py:18-22) | Install `pipewire-pulse` for the pactl wrapper. Falls back to `amixer` (ALSA); for best results, ensure `pulseaudio-alsa` or `pipewire-alsa` is installed. Manual check: `pactl info` should succeed |
| `RuntimeError: pycaw not found` on Windows (src/volume.py:43) | pycaw library not installed | Install: `pip install pycaw` or `uv pip install pycaw` |

## Notes on Automatic Recovery

**Token staleness is automatic.** The tool catches `_PortalCallError` from the Start call (src/capture.py:169-179) and retries without the cached token. In nearly all cases, you will not see the manual token deletion as necessary—the tool self-heals.

**Picker re-appearance is not a bug.** If the source picker reappears after it was shown on a prior run, it means either:
1. You revoked the permission in GNOME Settings -> Privacy -> Screen Recording
2. The compositor was upgraded and invalidated the old token

Either way, the tool will re-establish consent with a fresh picker. This is the intended behavior.

## Debugging

Enable debug logging by setting the log level in `main.py` (line 12):

```python
logger.setLevel(logging.DEBUG)
```

Or export `PYTHONUNBUFFERED=1` and check stderr for detailed GStreamer and D-Bus messages.

For D-Bus diagnostic info, use:
```bash
gdbus introspect --session --dest org.freedesktop.portal.Desktop --object-path /org/freedesktop/portal/desktop
```

For PipeWire stream info, use:
```bash
pw-dump
```
