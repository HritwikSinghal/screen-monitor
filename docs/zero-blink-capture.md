# Zero-Blink Capture

## Why the Screenshot Portal Blinks

The XDG Screenshot portal (`org.freedesktop.portal.Screenshot`) captures a single frame on demand. Each `Screenshot.Screenshot()` D-Bus call:
1. Triggers compositor round-trip
2. Waits for compositor to grab and composite the frame
3. Returns the image

At 10 Hz (100 ms per capture), this requires 10 round-trips per second, each causing a visible repaint on screen. The result is a rapid on-off blink that is distracting during live streaming.

## Why ScreenCast + PipeWire Does Not Blink

The XDG ScreenCast portal (`org.freedesktop.portal.ScreenCast`) opens a **persistent stream** via PipeWire:

1. One D-Bus call to establish the session and negotiate permissions
2. User picks a source (monitor or window) on first run
3. Compositor allocates a ring buffer in shared memory and pushes frames at screen refresh rate
4. Application reads from the ring buffer without any further portal round-trips
5. No compositor repaints — the ring buffer always contains the latest composited frame

This eliminates the blink because frame delivery is decoupled from the application's pull rate. Frames are buffered server-side; the client simply drains the latest available sample.

## GStreamer Pipeline

The pipeline is constructed at `src/capture.py:298-301`:

```
pipewiresrc fd={pipewire_fd} path={node_id} do-timestamp=true ! videoconvert ! video/x-raw,format=BGR ! appsink name=sink max-buffers=1 drop=true sync=false emit-signals=false
```

**pipewiresrc**: reads raw frames from the PipeWire fd and node_id  
**do-timestamp=true**: adds GStreamer timestamps for synchronization  
**videoconvert**: converts to the target color space  
**video/x-raw,format=BGR**: requests BGR (OpenCV native) output  
**appsink**: exposes frames to Python; `max-buffers=1 drop=true` ensures we always grab the latest frame, discarding any backlog

## Token Lifecycle

### First Run: No Cached Token

1. `TokenStore.load()` returns None (no `portal.json` yet)
2. `_select_sources()` is called without a `restore_token` option
3. Compositor displays the source picker (monitor or window)
4. User selects; D-Bus Start returns `restore_token` in the response
5. `TokenStore.save(token)` atomically writes to `~/.local/share/screen-monitor/portal.json`

See `src/capture.py:181-186`.

### Subsequent Runs: Cached Token

1. `TokenStore.load()` returns the cached token
2. `_select_sources()` includes `restore_token` in the options dict (line 224)
3. Compositor recognizes the token and skips the picker
4. Session opens silently; user sees no dialog

See `src/capture.py:168-170`.

### Persist Mode

The `persist_mode` option (line 219) is set to `PERSIST_UNTIL_REVOKED` (value 2, defined at line 39):

- Value 0 (SESSION): token valid only during this session
- Value 1 (UNTIL_EXPLICIT_REVOKE): token persists until user revokes via Settings
- Value 2 (UNTIL_REVOKED, alias): token persists until **either** revocation OR compositor upgrade

Setting `persist_mode=2` tells the compositor: "I expect this token to live indefinitely (or until I revoke it)."

### Stale Token Recovery

If a cached token is rejected (e.g., user revoked permission, or compositor was upgraded and invalidated old tokens), the `Start` call fails at `src/capture.py:247-248` with response code != 0.

Recovery logic at lines 169-179:
1. `ScreenCastSession.open()` catches `_PortalCallError` from `_open_with()`
2. If the error occurred in `Start` (not CreateSession or SelectSources), and a `restore_token` was used, the code assumes the token is stale
3. `self._token_store.clear()` removes the cached token
4. `self._open_with(None)` retries with a fresh picker

This is automatic; users rarely need to manually delete `portal.json`. The tool self-heals on token revocation.

## Atomic Writes

`TokenStore.save()` at `src/capture.py:71-78` uses the atomic write pattern to prevent corruption on crash:

```python
def save(self, token: str) -> None:
    directory = os.path.dirname(self.path)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    tmp = self.path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"restore_token": token}, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, self.path)
```

Steps:
1. Write to a temporary file with a predictable name
2. Change permissions to 0o600 (user read/write only)
3. Atomically rename (mv) the temp file to the final path

If the process crashes between chmod and replace, the corrupt `.tmp` file is left behind; on next run, `load()` will ignore it (FileNotFoundError in try/except), and a fresh token will be acquired.

## Inspiration: speedofsound

This pattern (write to `$XDG_DATA_HOME`, load on launch) mirrors the GSettings fallback in [speedofsound](https://github.com/zugaldia/speedofsound):

```kotlin
// speedofsound/core/src/main/kotlin/com/zugaldia/speedofsound/core/desktop/settings/PropertiesStore.kt
// (simplified)
fun save(key: String, value: String) {
    val file = File(dataDir, "settings.json")
    val tmpFile = File(dataDir, "settings.json.tmp")
    // write to tmp, then atomic rename
}

fun load(): Properties {
    val file = File(dataDir, "settings.json")
    // load or return default
}
```

screen-monitor applies the same philosophy: preferences are stored outside the application binary, in user-owned directories, following XDG conventions.

## Constants

Defined at `src/capture.py:26-42`:

| Constant | Value | Purpose |
|----------|-------|---------|
| PERSIST_UNTIL_REVOKED | 2 | persist_mode for indefinite token lifetime |
| PORTAL_CALL_TIMEOUT_SEC | 180 | max wait for portal response (user may be slow picking a source) |
| FRAME_PULL_TIMEOUT_NS | 2 * Gst.SECOND | max wait for a frame from PipeWire |

The 180-second timeout accommodates first-run scenarios where the user might take time to pick a monitor or window.
