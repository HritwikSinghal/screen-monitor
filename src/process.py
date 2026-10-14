import logging
import signal
import time

import cv2
import numpy as np

from src.capture import Capture, CaptureStreamError, TokenStore
from src.matcher import TemplateMatcher
from src.volume import VolumeController

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 0.05
# While capture keeps failing, poll slower and log a summary at most this
# often instead of a traceback every tick.
CAPTURE_FAILURE_BACKOFF_SEC = 1.0
CAPTURE_FAILURE_LOG_INTERVAL_SEC = 60.0


class _CaptureFailures:
    """Logs the first capture failure in full, then rate-limited summaries."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self.count = 0
        self._last_log = 0.0

    def failed(self) -> None:
        self.count += 1
        now = self._clock()
        if self.count == 1:
            logger.exception("Frame capture failed")
            self._last_log = now
        elif now - self._last_log >= CAPTURE_FAILURE_LOG_INTERVAL_SEC:
            logger.error("Frame capture still failing (%d consecutive failures)", self.count)
            self._last_log = now

    def succeeded(self) -> None:
        if self.count:
            logger.info("Frame capture recovered after %d failures", self.count)
            self.count = 0


def capture_screen(client: Capture, failures: _CaptureFailures) -> np.ndarray | None:
    """Pull the latest frame from the persistent PipeWire stream (BGR, HxWx3).

    Returns None on a transient failure. CaptureStreamError propagates: the
    stream is gone and polling it again only repeats the error.
    """
    try:
        frame = client.get_frame()
    except CaptureStreamError:
        raise
    except Exception:
        failures.failed()
        return None
    failures.succeeded()
    return frame


def _score(matcher: TemplateMatcher) -> str:
    s = matcher.last_score
    return "n/a" if s is None else f"{s:.2f}"


def load_target_image(image_path):
    target_img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if target_img is None:
        raise ValueError(f"Could not load image from {image_path}")
    return target_img


def start(reselect: bool = False):
    try:
        volume_control = VolumeController()
    except RuntimeError as e:
        logger.error("Error initializing volume control: %s", e)
        return

    try:
        logger.info("Loading target image")
        matcher = TemplateMatcher(load_target_image("target_image.png"))
        logger.info("Loaded target image")
    except ValueError as e:
        logger.error("Error loading target image: %s", e)
        return

    # Route SIGTERM (e.g. systemd stop) through the same KeyboardInterrupt path
    # as Ctrl+C so shutdown unmutes audio and releases the portal session
    # instead of getting killed mid-frame with audio muted.
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    logger.info("Monitoring started. Press Ctrl+C to stop.")
    was_muted = False

    token_store = TokenStore()
    if reselect:
        # Without a restore token the portal shows its picker again.
        token_store.clear()
        logger.info("Cleared remembered capture source; the picker will be shown")

    failures = _CaptureFailures()
    with Capture(token_store) as client:
        try:
            while True:
                screen = capture_screen(client, failures)
                if screen is None:
                    time.sleep(CAPTURE_FAILURE_BACKOFF_SEC)
                    continue

                image_present = matcher.match(screen)

                if not image_present and not was_muted:
                    try:
                        volume_control.mute()
                    except Exception:
                        logger.exception("Mute failed; leaving was_muted=False to retry")
                    else:
                        was_muted = True
                        logger.info(
                            "Target image not found (score %s < %.2f) - Audio muted",
                            _score(matcher), matcher.threshold,
                        )
                elif image_present and was_muted:
                    try:
                        volume_control.unmute()
                    except Exception:
                        logger.exception("Unmute failed; will retry next tick")
                    else:
                        was_muted = False
                        logger.info(
                            "Target image found (score %s, scale %s) - Audio unmuted",
                            _score(matcher), matcher.cached_scale,
                        )

                time.sleep(POLL_INTERVAL_SEC)

        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
        except CaptureStreamError as e:
            # Already logged with diagnostics where it was detected; exiting
            # unmutes below instead of freezing the mute state on a dead stream.
            logger.error("Capture stream is gone, stopping: %s", e)
        except Exception:
            logger.exception("Monitor loop crashed")
        finally:
            if was_muted:
                try:
                    volume_control.unmute()
                except Exception:
                    logger.exception("Failed to unmute on shutdown; audio may remain muted")
