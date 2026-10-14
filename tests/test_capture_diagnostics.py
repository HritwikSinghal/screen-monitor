import logging

import pytest

from src import capture
from src.capture import CaptureStreamError, Gst, PipeWireCapture
from src.process import _CaptureFailures


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def make_capture(clock: FakeClock) -> PipeWireCapture:
    cap = PipeWireCapture(pipewire_fd=-1, node_id=42, clock=clock)
    cap._on_fresh_frame(64, 48, "BGR")
    return cap


def stall_warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if "No new frames" in r.getMessage()]


def test_stall_warning_backs_off_by_doubling(caplog):
    clock = FakeClock()
    cap = make_capture(clock)
    with caplog.at_level(logging.WARNING, logger="src.capture"):
        for t in range(2, 200, 2):
            clock.now = t
            cap._on_timeout()
    # Warnings at 30s, 60s, 120s -- not one per timeout.
    assert len(stall_warnings(caplog)) == 3
    assert "node=42" in stall_warnings(caplog)[0]


def test_resume_is_logged_only_after_a_warned_stall(caplog):
    clock = FakeClock()
    cap = make_capture(clock)
    with caplog.at_level(logging.INFO, logger="src.capture"):
        clock.now = 10
        cap._on_timeout()
        cap._on_fresh_frame(64, 48, "BGR")
        assert not any("resumed" in r.getMessage() for r in caplog.records)

        clock.now = 50
        cap._on_timeout()
        cap._on_fresh_frame(64, 48, "BGR")
    assert any("Frames resumed after 40.0s" in r.getMessage() for r in caplog.records)


def test_resume_rearms_stall_warning_at_base_interval(caplog):
    clock = FakeClock()
    cap = make_capture(clock)
    clock.now = 70
    cap._on_timeout()  # warns, next threshold doubles
    cap._on_fresh_frame(64, 48, "BGR")
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="src.capture"):
        clock.now = 70 + capture.STALL_WARN_SEC
        cap._on_timeout()
    assert len(stall_warnings(caplog)) == 1


def test_frame_size_change_is_logged(caplog):
    cap = make_capture(FakeClock())
    with caplog.at_level(logging.INFO, logger="src.capture"):
        cap._on_fresh_frame(64, 48, "BGR")
        cap._on_fresh_frame(128, 96, "BGR")
    changes = [r.getMessage() for r in caplog.records if "frame format" in r.getMessage()]
    assert len(changes) == 1
    assert "64x48 BGR -> 128x96 BGR" in changes[0]


def _videotestsrc_capture(num_buffers: int) -> PipeWireCapture:
    """A PipeWireCapture whose pipeline is a finite videotestsrc instead of PipeWire."""
    PipeWireCapture._ensure_gst()
    cap = PipeWireCapture(pipewire_fd=-1, node_id=0)
    cap.pipeline = Gst.parse_launch(
        f"videotestsrc name=src num-buffers={num_buffers} "
        "! video/x-raw,width=64,height=48 ! videoconvert ! video/x-raw,format=BGR "
        "! appsink name=sink sync=false"
    )
    cap.appsink = cap.pipeline.get_by_name("sink")
    cap._bus = cap.pipeline.get_bus()
    cap.pipeline.set_state(Gst.State.PLAYING)
    return cap


def test_eos_raises_stream_error_and_stays_fatal():
    cap = _videotestsrc_capture(num_buffers=2)
    try:
        frames = 0
        with pytest.raises(CaptureStreamError):
            for _ in range(10):
                frame = cap.get_frame()
                assert frame.shape == (48, 64, 3)
                frames += 1
        assert frames == 2
        # Later polls fail fast instead of blocking on a dead pipeline.
        with pytest.raises(CaptureStreamError):
            cap.get_frame()
    finally:
        cap.stop()


def test_failure_logging_is_rate_limited(caplog):
    clock = FakeClock()
    failures = _CaptureFailures(clock=clock)
    with caplog.at_level(logging.INFO, logger="src.process"):
        for t in range(120):
            clock.now = t
            try:
                raise RuntimeError("boom")
            except RuntimeError:
                failures.failed()
        failures.succeeded()
    messages = [r.getMessage() for r in caplog.records]
    assert messages.count("Frame capture failed") == 1
    assert sum("still failing" in m for m in messages) == 1
    assert messages[-1] == "Frame capture recovered after 120 failures"
