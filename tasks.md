# Tasks
Screen monitoring tool: XDG ScreenCast portal + PipeWire capture, mutes audio when a target image disappears from screen.

## Bug hunt (2026-04-20)

### Critical (fixed in this session)
- [x] C1 — D-Bus Response signal race: `invoke()` fired before `AddMatch` was guaranteed flushed — `src/capture.py:130-140`
- [x] C2 — PipeWire fd leak on stop/failure; ownership not clear between session and pipeline — `src/capture.py:295-349`
- [x] C3 — Session leak on stale-token retry: old handle/fd not released before second attempt — `src/capture.py:167-179`
- [x] C4 — Unsafe `captured["code"]` / `results["session_handle"]` access — `src/capture.py:206-208`

### High (fixed in this session)
- [x] H1 — `invoke()` synchronous exception left GLib loop running until 180 s timeout — `src/capture.py:138-140`
- [x] H2 — `bus_name=` filter should resolve well-known name to unique name — `src/capture.py:130-136`
- [x] H3 — `volume.py` swallowed `pactl`/`amixer` non-zero exits, diverging `was_muted` from reality — `src/volume.py:68-87`
- [x] H4 — `cv2.matchTemplate` crashed on template > screen or channel mismatch — `src/process.py:31-33`
- [x] H5 — No SIGTERM handler; `was_muted` not reconciled on shutdown error path — `src/process.py:52-80`
- [x] H6 — Unsafe `results["session_handle"]` access — `src/capture.py:208`

### Medium (open)
- [x] M1 — Replace `re.sub` with `.lstrip(":").replace(".", "_")` — src/capture.py:99
- [x] M2 — Drop `hasattr(Gst, "SECOND")` fallback (fail loudly on broken GStreamer) — src/capture.py:42
- [ ] M3 — `TokenStore.save` orphan `.tmp` on crash; use `O_EXCL` — src/capture.py:71-78
- [ ] M4 — File-perm race; create with 0o600 atomically via `os.open(O_EXCL, 0o600)` — src/capture.py:75-77
- [ ] M5 — Hardcoded `target_image.png` path relative to CWD — src/process.py:45
- [x] M6 — `_command_exists` crashes when PATH is unset; prefer `shutil.which` — src/volume.py
- [ ] M7 — Wrong row-stride heuristic; use `GstVideoMeta` — src/capture.py:329-340
- [ ] M8 — `try_pull_sample` None conflates timeout vs EOS; check `appsink.props.eos` — src/capture.py:318-320
- [ ] M9 — Prefer `Gst.is_initialized()` to class flag — src/capture.py:281,289-293
- [ ] M10 — Raise log level on session close failure — src/capture.py:273
- [x] M11 — Replace `traceback.print_exc()` with `logger.exception` + consecutive-failure backoff — src/process.py (backoff not added)

### Low (open)
- [x] L1 — Replace `print` with `logger` across process.py — src/process.py
- [ ] L2 — Lock the Gst init path or rely on GStreamer's own idempotency — src/capture.py:281
- [ ] L3 — Wrap each cleanup call in `Capture.stop` with try/except — src/capture.py:376-382
- [ ] L4 — Add tests for 0o600 file perms; integration test for portal flow gated by env var
- [ ] L5 — Per-call portal timeouts (short for non-interactive CreateSession/OpenPipeWireRemote) — src/capture.py:41
- [ ] L6 — Add `gst-plugins-bad` to flake.nix defensively — flake.nix:24-28

## Simplify pass (2026-04-20)
- [x] Unify `mute`/`unmute` into `_set_mute(bool)` dispatch — src/volume.py
- [x] Fix missing `from e` on pycaw ImportError — src/volume.py
- [x] Switch `subprocess.run(capture_output=True)` to `stdout=DEVNULL, stderr=PIPE` — src/volume.py
- [x] Replace custom `_install_sigterm_handler` with `signal.default_int_handler` — src/process.py
- [x] Extract `POLL_INTERVAL_SEC = 0.1` constant — src/process.py
- [x] `videoconvert n-threads=2` → `n-threads=0` for portability — src/capture.py
