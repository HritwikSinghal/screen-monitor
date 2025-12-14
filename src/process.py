import time
import traceback

import cv2
import numpy as np
import pyscreenshot
import logging

from src.volume import VolumeController
from src.capture import Capture

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def capture_screen(client):
    """Capture the screen and return as numpy array"""
    print("Capturing screen")
    try:
        # pyautogui cannot take SS in wayland.
        # screenshot = pyautogui.screenshot()

        # logger.debug("Starting xdg")
        # # screenshot = client.start()
        # client.start()

        screenshot = pyscreenshot.grab()
        return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    except:
        traceback.print_exc()


def load_target_image(image_path):
    """Load and prepare the target image"""
    target_img = cv2.imread(image_path)
    if target_img is None:
        raise ValueError(f"Could not load image from {image_path}")
    return target_img


def check_image_presence(screen, target_img, threshold=0.8):
    """
    Check if target image is present in screen
    Returns: True if image is found, False otherwise
    """
    result = cv2.matchTemplate(screen, target_img, cv2.TM_CCOEFF_NORMED)
    return np.max(result) >= threshold


def start():
    # Initialize volume control
    try:
        volume_control = VolumeController()
    except RuntimeError as e:
        print(f"Error initializing volume control: {e}")
        return

    # Load the target image
    try:
        print("loading target image")
        target_img = load_target_image("target_image.png")
        print("loaded target image")
    except ValueError as e:
        print(f"Error loading target image: {e}")
        return

    print("Monitoring started. Press Ctrl+C to stop.")
    was_muted = False

    client = Capture()
    try:
        while True:
            # Capture screen
            screen = capture_screen(client)

            # Check for image presence
            image_present = check_image_presence(screen, target_img)

            # Control volume based on image presence
            if not image_present and not was_muted:
                volume_control.mute()
                print("Target image not found - Audio muted")
                was_muted = True
            elif image_present and was_muted:
                volume_control.unmute()
                print("Target image found - Audio unmuted")
                was_muted = False

            # Wait for 0.1 second before next check
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nMonitoring stopped by user")
        # Ensure audio is unmuted when stopping
        volume_control.unmute()
    except Exception as e:
        print(f"An error occurred: {e}")
        # Ensure audio is unmuted on error
        volume_control.unmute()
