import logging
import time
import traceback

import cv2
import numpy as np

from src.capture import Capture
from src.volume import VolumeController

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def capture_screen(client: Capture) -> np.ndarray | None:
    """Pull the latest frame from the persistent PipeWire stream (BGR, HxWx3)."""
    try:
        return client.get_frame()
    except Exception:
        traceback.print_exc()
        return None


def load_target_image(image_path):
    target_img = cv2.imread(image_path)
    if target_img is None:
        raise ValueError(f"Could not load image from {image_path}")
    return target_img


def check_image_presence(screen, target_img, threshold=0.8):
    result = cv2.matchTemplate(screen, target_img, cv2.TM_CCOEFF_NORMED)
    return np.max(result) >= threshold


def start():
    try:
        volume_control = VolumeController()
    except RuntimeError as e:
        print(f"Error initializing volume control: {e}")
        return

    try:
        print("loading target image")
        target_img = load_target_image("target_image.png")
        print("loaded target image")
    except ValueError as e:
        print(f"Error loading target image: {e}")
        return

    print("Monitoring started. Press Ctrl+C to stop.")
    was_muted = False

    with Capture() as client:
        try:
            while True:
                screen = capture_screen(client)
                if screen is None:
                    time.sleep(0.1)
                    continue

                image_present = check_image_presence(screen, target_img)

                if not image_present and not was_muted:
                    volume_control.mute()
                    print("Target image not found - Audio muted")
                    was_muted = True
                elif image_present and was_muted:
                    volume_control.unmute()
                    print("Target image found - Audio unmuted")
                    was_muted = False

                time.sleep(0.1)

        except KeyboardInterrupt:
            print("\nMonitoring stopped by user")
            volume_control.unmute()
        except Exception as e:
            print(f"An error occurred: {e}")
            volume_control.unmute()
