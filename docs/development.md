# Development

## Project Layout

```
screen-monitor/
+-- main.py                          # Entry point; logging setup
+-- src/
|   +-- __init__.py
|   +-- capture.py                   # ScreenCast + PipeWire session (Capture facade, ScreenCastSession, PipeWireCapture, TokenStore)
|   +-- process.py                   # Main loop: frame capture, image detection, volume control
|   +-- volume.py                    # Platform-specific audio mute/unmute
+-- tests/
|   +-- __init__.py
|   +-- test_capture_token_store.py  # TokenStore unit tests (10 tests)
+-- docs/
|   +-- README.md
|   +-- architecture.md
|   +-- zero-blink-capture.md
|   +-- portal-flow.md
|   +-- troubleshooting.md
|   +-- development.md               # This file
+-- pyproject.toml                   # Project metadata and dependencies
+-- uv.lock                          # Lockfile for reproducible installs
+-- flake.nix                        # Nix flake: apps, devShell, pinned toolchain
+-- flake.lock                       # Nix flake input pins
+-- README.md                        # User-facing: install, run, motivation
```

## Python Version

Requires Python >= 3.11.11. Specified in `pyproject.toml`.

## Running Tests

```bash
python3 -m pytest tests/ -v   # with system/uv Python
nix run .#test                # via the flake
```

This runs all tests in `tests/test_capture_token_store.py`. There are 10 tests covering:
- TokenStore.load() behavior (missing file, corrupt JSON, missing key)
- TokenStore.save() and round-trip persistence
- Directory creation with 0o700 permissions
- Atomic writes via temporary file
- TokenStore.clear() idempotency
- XDG_DATA_HOME and fallback path resolution

All tests must pass before considering changes complete.

## Extension: Custom Capture Backend

To add a new screen capture backend (e.g., X11, Wayland native, etc.), implement a class with this interface and pass it to `Capture`:

```python
class MyCapture:
    def start(self) -> "MyCapture":
        """Initialize and return self."""
        pass

    def get_frame(self) -> np.ndarray:
        """Return a numpy array of shape (height, width, 3) in BGR format."""
        pass

    def stop(self) -> None:
        """Clean up resources."""
        pass

    def __enter__(self) -> "MyCapture":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
```

The current implementation (`PipeWireCapture`) is an example. The public `Capture` facade (src/capture.py:352) accepts a `TokenStore` and internally uses `ScreenCastSession` + `PipeWireCapture`.

To swap backends, you would either:
1. Modify `Capture.start()` to instantiate your backend instead of `PipeWireCapture`, or
2. Create a new facade class mirroring `Capture`'s interface

## Target Image Contract

The target image is loaded at `src/process.py:45`:

```python
target_img = load_target_image("target_image.png")
```

**Contract:**
- File path is hardcoded as `target_image.png` (relative to the current working directory)
- Must be a valid image readable by OpenCV (`cv2.imread()`)
- Color space: BGR (OpenCV native)
- Used with `cv2.matchTemplate(screen, target_img, cv2.TM_CCOEFF_NORMED)` at line 32
- Matched at threshold >= 0.8 (normalized cross-correlation coefficient)
- Must be smaller than the screen resolution (matchTemplate requires template <= image)

The threshold of 0.8 is a reasonable default for identifying watermarks and UI elements. Adjust if false positives or false negatives occur.

## Logging Setup

Logging is initialized in `main.py` at line 9:

```python
logging.basicConfig(format='%(asctime)s: %(name)s: %(levelname)s: %(lineno)d: %(message)s')
```

Each module uses per-module loggers:

```python
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # module-specific level
```

All log messages include:
- Timestamp
- Module name (via `__name__`)
- Level (DEBUG, INFO, WARNING, ERROR)
- Line number

Set the root logger level in `main.py` or individual module levels in `src/process.py`, `src/capture.py`, etc.

## Dependency Management

Dependencies are declared in `pyproject.toml` and locked in `uv.lock` for reproducible builds. The project supports two parallel workflows: `uv` (canonical) and `nix` (via `flake.nix`).

### uv

```bash
uv sync           # install deps into .venv
uv run main.py    # run the app
```

`uv` resolves against `uv.lock`, so versions are exact and reproducible across machines that share the same lockfile.

### Nix

```bash
nix run .#start   # run the app
nix run .#test    # run tests
nix develop       # drop into a shell with the full toolchain + uv
```

The flake builds a Python environment from nixpkgs and wires up `GI_TYPELIB_PATH` + `GST_PLUGIN_PATH` so GStreamer/PipeWire resolve correctly without system packages.

### Parity: uv vs Nix

Both paths run the same source code against the same portal + D-Bus + PipeWire interfaces, but they are **not** bit-identical:

| Aspect | `uv` | `nix` |
| --- | --- | --- |
| Lockfile | `uv.lock` (exact pins) | `flake.lock` (nixpkgs snapshot) |
| Python version | Whatever satisfies `>=3.11.11` | Pinned to `python312` in `flake.nix` |
| OpenCV | `opencv-python` PyPI wheel (bundles FFmpeg/codecs) | `opencv4` from nixpkgs (built against nixpkgs FFmpeg) |
| GStreamer | System `/usr/lib/gstreamer-1.0` | Nix-store build of `gst_all_1` |
| PipeWire plugin | System `pipewiresrc` | `${pkgs.pipewire}/lib/gstreamer-1.0/libgstpipewire.so` |
| Windows extras (`pycaw`, `comtypes`) | Present in lock, platform-gated | Omitted (Linux-only flake) |

Practical implications:

- **Versions drift.** Package versions under Nix will differ from `uv.lock` because nixpkgs has its own release cadence. If you need bit-for-bit parity with `uv.lock`, migrate the flake to [`uv2nix`](https://github.com/pyproject-nix/uv2nix) — it consumes `uv.lock` directly.
- **ABI surface.** The app talks to the user's session D-Bus bus and PipeWire socket, both shared across Nix/uv. If the nixpkgs PipeWire build is far from your system PipeWire daemon's version, `pipewiresrc` can theoretically mismatch on the wire protocol. Rare in practice; PipeWire holds its protocol stable.
- **Codec coverage.** `opencv-python` (pip) and `opencv4` (nix) have different built-in backends. For `cv2.imread` + `cv2.matchTemplate` on a PNG this is irrelevant. It would matter if you later add video decoding.

Treat `uv` as the source of truth for dependency versions. The flake is a convenience for users who want a hermetic run without touching system packages.

No CI is configured yet. Before proposing a PR, ensure tests pass locally under at least one of the two workflows.

## Known Limitations

1. **No CI pipeline.** Tests run locally only; no automated checks on pull requests.
2. **Platform-specific volume control.** Linux prefers `pactl`; falls back to `amixer`. macOS uses `osascript`. Windows uses `pycaw`. Each platform has its own failure modes.
3. **Fixed target image path.** The image path is hardcoded; no configuration file or CLI flag yet.
4. **No window-relative capture on X11.** The tool works on Wayland (via the portal) and supports both monitor and window capture via the portal's source picker.
