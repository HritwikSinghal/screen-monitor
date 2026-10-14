import logging
import signal
import time

import cv2
import numpy as np

from src.capture import Capture, TokenStore
from src.matcher import TemplateMatcher
from src.volume import VolumeController

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

POLL_INTERVAL_SEC = 0.05


def capture_screen(client: Capture) -> np.ndarray | None:
    """Pull the latest frame from the persistent PipeWire stream (BGR, HxWx3)."""
    try:
        return client.get_frame()
    except Exception:
        logger.exception("Frame capture failed")
        return None


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

    with Capture(token_store) as client:
        try:
            while True:
                screen = capture_screen(client)
                if screen is None:
                    time.sleep(POLL_INTERVAL_SEC)
                    continue

                image_present = matcher.match(screen)

                if not image_present and not was_muted:
                    try:
                        volume_control.mute()
                    except Exception:
                        logger.exception("Mute failed; leaving was_muted=False to retry")
                    else:
                        was_muted = True
                        logger.info("Target image not found - Audio muted")
                elif image_present and was_muted:
                    try:
                        volume_control.unmute()
                    except Exception:
                        logger.exception("Unmute failed; will retry next tick")
                    else:
                        was_muted = False
                        logger.info("Target image found - Audio unmuted")

                time.sleep(POLL_INTERVAL_SEC)

        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
        except Exception:
            logger.exception("Monitor loop crashed")
        finally:
            if was_muted:
                try:
                    volume_control.unmute()
                except Exception:
                    logger.exception("Failed to unmute on shutdown; audio may remain muted")
