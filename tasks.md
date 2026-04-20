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

## Tracing subsystem (2026-04-20)

In progress. Brainstorming via `superpowers:brainstorming` skill. Sections 1–2 approved; spec doc not yet written. Resume at Section 3.

### Decisions locked (brainstorming Q1–Q5)
- Goal: (A) per-stage latency + (C) call-flow visibility
- Backends: NDJSON file + Pyroscope, running side-by-side
- Pyroscope infra: local, launched via new Nix flake app (no pre-existing server)
- Scope: full coverage — every stage, sub-spans inside `Capture.get_frame`, each subprocess call in `volume.py`
- Enable/disable: env-var gated, zero overhead when unset
  - `SCREEN_MONITOR_TRACE=1` → NDJSON on
  - `PYROSCOPE_SERVER_ADDRESS=http://localhost:4040` → Pyroscope on

### Brainstorming / design progress
- [x] Section 1 — Architecture (approved; revised after `/arch-review`)
- [x] Section 2 — NDJSON span schema (approved)
- [ ] Section 3 — Instrumentation call sites (capture.py, process.py, main.py)
- [ ] Section 4 — Nix flake apps + packaging (pyproject.toml, flake.nix)
- [ ] Section 5 — Testing plan
- [ ] Write spec to `docs/superpowers/specs/2026-04-20-tracing-design.md` + commit
- [ ] Spec self-review + user review gate
- [ ] Invoke `superpowers:writing-plans` to produce implementation plan
- [ ] Implement per plan
- [ ] User-facing doc at `docs/tracing.md` (final deliverable the user asked for)

### Architecture decisions (Section 1, post arch-review)
- Single `src/tracing.py` module; one primitive `span()` contextmanager; `trace_span` is a 3-line decorator wrapper (no independent logic)
- Propagation via `contextvars.ContextVar[Span | None]` (not attr-threaded `iteration_id`)
- NDJSON backend = `logging.handlers.QueueHandler` + `QueueListener` + `RotatingFileHandler` (50 MB × 3 backups). No hand-rolled thread.
- Pyroscope tagging is opt-in per span; only 4 spans tag: `iteration`, `capture`, `template_match`, `mute_toggle`. Sub-spans (subprocess, buf_map) are NDJSON-only — `oncpu=True, gil_only=True` won't sample them anyway.
- Pyroscope failure mode: tri-state. Unset = no-op. Set + import OK = configure. Set + ImportError = `logger.error` + `sys.exit(2)` (no silent degradation).
- Instrumentation placement:
  - Decorate `Capture.get_frame` (stage `capture`) and `check_image_presence` (stage `template_match`).
  - Inline `with span(...)` inside `get_frame` for `appsink_pull` and `buf_map_to_ndarray`.
  - Wrap `volume_control.mute()`/`unmute()` **at call site in `process.py`** — `volume.py` stays tracing-import-free.
  - `process.py` main loop opens parent `iteration` span that children inherit via ContextVar.
- Timing: `time.time_ns()` for `start_wall_ns`, `time.perf_counter_ns()` for `duration_ns`. NTP-safe.
- Span ID: `secrets.token_hex(8)` (avoid `uuid4` `/dev/urandom` read on hot path); `__slots__` on `Span` dataclass.
- OTel-shaped public API (`trace_id`, `span_id`, `parent_span_id`, `name`, `start_ns`, `end_ns`, `attributes`, `status`) so future swap to `opentelemetry-sdk` is mechanical.
- `init_tracing()` idempotent via module-level `_initialized` guard.
- Ordering in `main.py`: `init_tracing()` → (Pyroscope configures + installs SIGPROF) → `process.start()` (which installs SIGTERM). Pyroscope signal setup must precede ours.
- `pyroscope-io` under `[project.optional-dependencies] tracing = [...]` in `pyproject.toml`, not top-level deps. Bare `pip install` stays slim.
- Three Nix apps:
  - `start` — unchanged, no tracing
  - `trace-file` — sets `SCREEN_MONITOR_TRACE=1`, no Pyroscope server (the 10× more common mode)
  - `trace` — starts `pkgs.pyroscope` server on :4040, sets both env vars, tears server down on exit
- Budget: tracing should add <2% to iteration wall time at 15 fps; measure once before merge.

### NDJSON schema (Section 2)
Base fields: `trace_id`, `span_id`, `parent_span_id`, `name`, `start_wall_ns`, `duration_ns`, `status` (`ok`/`error`), `error?` (`{type, message}` only, no stack), `iteration?` (copied from parent for grep-ability), `attributes`.

Stage-specific attrs:
- `iteration` → `{iteration_n}`
- `capture` → `{frame_w, frame_h, channels}` or `{frame: null}` on timeout
- `appsink_pull` → `{timeout_ns, got_sample, eos}`
- `buf_map_to_ndarray` → `{bytes, stride}`
- `template_match` → `{threshold, score, matched, screen_shape, target_shape}`
- `mute_toggle` → `{from, to, reason}`  (`reason` ∈ `image_lost`/`image_found`)
- `pactl_set_mute` → `{argv, returncode, duration_ns}`

Shutdown summary line (appended once via `atexit`, also printed to stderr):
```
{"kind":"summary","trace_id":...,"run_duration_s":...,"iterations":N,"stages":{"capture":{"count":N,"p50_us":...,"p95_us":...,"p99_us":...,"max_us":...,"errors":0}, ...}}
```

File: `~/.local/share/screen-monitor/traces/trace.ndjson`, rotated at 50 MB × 3 backups (~25 min/rotation at 15 fps × ~7 spans/iter).

Deliberately excluded: full stack traces, raw frame bytes, match matrices, thread/PID.

### Arch-review follow-ups to verify during implementation
- [ ] Confirm `python312Packages.pyroscope-io` exists on pinned nixpkgs channel (or use `buildPythonPackage` fallback)
- [ ] Confirm `pkgs.pyroscope` server package exists on pinned nixpkgs channel
- [ ] Measure <2% overhead budget at 15 fps: `SCREEN_MONITOR_TRACE=1` vs unset
- [ ] Decide: summary line in same NDJSON file, or separate `run-summary.json`? (current plan: same file, `kind:"summary"` discriminator)

### Remaining design questions for next session
- **Section 3**: exact line-level edits in `capture.py:~370–397` (sub-span around `buf.map`/`np.frombuffer`/`.copy()`), `process.py:~68–97` (iteration span + mute-toggle wrap + `load_target_image` span?), `main.py` (init_tracing before start).
- **Section 4**: `flake.nix` text for `trace-file` / `trace`; Pyroscope server launch+teardown shell (trap EXIT); does `pkgs.pyroscope` need a writable data dir?
- **Section 5**: tests for ContextVar propagation across nested spans; summary percentile math; env-var gating no-op has zero allocations; NDJSON round-trip integration test; verify `volume.py` has no `tracing` import (grep test).

### Files to create/modify (implementation phase)
- Create: `src/tracing.py`, `tests/test_tracing.py`, `docs/tracing.md`, `docs/superpowers/specs/2026-04-20-tracing-design.md`
- Modify: `main.py` (call `init_tracing()`), `src/process.py` (iteration span + mute-toggle wrap + decorate `check_image_presence`), `src/capture.py` (decorate `get_frame` + sub-spans), `pyproject.toml` (optional `tracing` extra), `flake.nix` (pyroscope-io in pythonEnv, `trace-file` and `trace` apps)
- Do NOT touch: `src/volume.py` (must stay tracing-import-free per arch-review)
