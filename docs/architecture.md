# Architecture

## Module Overview

screen-monitor is organized in three layers: wiring, session management, and capture.

### main.py

Entry point that initializes logging (basicConfig at line 9) and calls `src.process.start()`.

### src/process.py

The main event loop. Owned by `start()` at line 36:
- Line 54: `with Capture() as client:` — opens a persistent ScreenCast session
- Line 56: Enters a `while True` loop
- Line 57: Calls `capture_screen(client)` -> `Capture.get_frame()` (line 18)
- Line 62: Checks if the target image is present in the captured frame via `check_image_presence()` (line 31-33)
- Lines 65, 69: Calls `VolumeController.mute()` and `.unmute()` based on the image presence

**Mute logic clarification**: The tool mutes audio when the target image is ABSENT (`not image_present` at line 64) and unmutes when the target image is FOUND (`image_present` at line 68). This matches the streaming use case: mute during ads (when the watermark disappears), unmute when live content resumes (watermark reappears).

### src/capture.py

Provides the `Capture` class and the portal session machinery.

#### Capture (line 352)
Public façade for screen capture. Context manager pattern:
- `__enter__` (line 384): calls `start()` which opens the session and stream
- `__exit__` (line 387): calls `stop()` which closes both
- `start()` (line 360): creates `ScreenCastSession` and `PipeWireCapture`, returns self
- `get_frame()` (line 371): returns numpy BGR array (HxWx3) from `PipeWireCapture.get_frame()`
- `stop()` (line 376): cleans up session and stream

#### ScreenCastSession (line 156)
Manages the XDG ScreenCast portal session lifecycle:
- `open()` (line 167): tries to load a cached `restore_token` and open the session. If the Start call fails with a stale token, clears it and retries with a fresh picker.
- `_create_session()` (line 190): D-Bus CreateSession call
- `_select_sources()` (line 210): D-Bus SelectSources call; triggers the picker on first run if no `restore_token`
- `_start()` (line 235): D-Bus Start call; returns streams and the new `restore_token`
- `_open_pipewire_remote()` (line 258): D-Bus OpenPipeWireRemote call; returns file descriptor
- `close()` (line 266): closes the portal session

Produces:
- `node_id` (int): PipeWire node identifier
- `pipewire_fd` (int): file descriptor for the PipeWire stream

#### PipeWireCapture (line 278)
GStreamer-based frame consumer:
- `start()` (line 295): builds and plays the GStreamer pipeline using pipewiresrc
- `get_frame()` (line 315): pulls the latest sample and decodes it to numpy BGR (HxWx3)
- `stop()` (line 345): tears down the pipeline

#### TokenStore (line 45)
Persists the ScreenCast `restore_token` to `~/.local/share/screen-monitor/portal.json`:
- `load()`: returns the cached token or None
- `save(token)`: atomically writes token with 0o600 permissions (`.tmp` + `chmod` + `os.replace()`)
- `clear()`: removes the file (idempotent)

### src/volume.py

Platform-specific audio mute/unmute:
- Linux (lines 18-22): prefers `pactl` over `amixer`; falls back if pactl is missing
- macOS (line 57): uses `osascript`
- Windows (lines 32-38): uses `pycaw`

## Data Flow

```
main.py
  |_ process.start()
       |_ VolumeController()          [src/volume.py]
       |_ load_target_image()         [src/process.py]
       |_ with Capture() as client:   [src/capture.py]
            |
            |_ Capture.start()
            |    |_ ScreenCastSession.open()
            |    |    |_ D-Bus: CreateSession
            |    |    |_ D-Bus: SelectSources
            |    |    |_ D-Bus: Start  -> restore_token cached to portal.json
            |    |    |_ D-Bus: OpenPipeWireRemote  -> pipewire_fd, node_id
            |    |_ PipeWireCapture.start()
            |         |_ GStreamer pipeline (pipewiresrc -> videoconvert -> appsink)
            |
            |_ loop:
                 screen = Capture.get_frame()   -> numpy BGR array
                 check_image_presence(screen, target_img)
                 VolumeController.mute() / .unmute()
```

## Key Design Patterns

### Context Manager
`Capture` implements `__enter__` and `__exit__` to ensure session cleanup on exception or early exit.

### Async Request-Response
Portal methods are asynchronous. `_run_portal_call()` (line 111) waits for a Response signal on a request object path via GLib MainLoop. All three portal calls (CreateSession, SelectSources, Start) follow this pattern.

### Token Caching and Retry
First run: user picks a source. `restore_token` is saved. Subsequent runs: token is supplied to SelectSources, picker is skipped. If the token becomes stale (revoked or compositor upgraded), the Start call fails, the token is cleared, and the request is retried with a fresh picker (lines 169-179).

### Atomic File Writes
TokenStore avoids corruption on crash: write to a temp file, chmod to 0o600, then atomic rename (lines 74-78).
