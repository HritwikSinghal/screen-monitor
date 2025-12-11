import pytest
import cv2
import numpy as np
from screen_monitor.main import check_image_presence



def test_check_image_presence_found():
    # Create a sample screen and target image
    screen = np.zeros((100, 100, 3), dtype=np.uint8)
    target_img = np.zeros((50, 50, 3), dtype=np.uint8)

    # Draw the target image in the center of the screen
    cv2.rectangle(screen, (25, 25), (75, 75), (255, 0, 0), -1)

    # Check if the target image is found
    assert check_image_presence(screen, target_img) == True

def test_check_image_presence_not_found():
    # Create a sample screen and target image
    screen = np.zeros((100, 100, 3), dtype=np.uint8)
    target_img = np.zeros((50, 50, 3), dtype=np.uint8)

    # Check if the target image is not found
    assert check_image_presence(screen, target_img) == False

def test_check_image_presence_threshold():
    # Create a sample screen and target image
    screen = np.zeros((100, 100, 3), dtype=np.uint8)
    target_img = np.zeros((50, 50, 3), dtype=np.uint8)

    # Draw the target image in the center of the screen with low intensity
    cv2.rectangle(screen, (25, 25), (75, 75), (10, 0, 0), -1)

    # Check if the target image is not found due to low threshold
    assert check_image_presence(screen, target_img, threshold=0.9) == False

def test_check_image_presence_threshold_high():
    # Create a sample screen and target image
    screen = np.zeros((100, 100, 3), dtype=np.uint8)
    target_img = np.zeros((50, 50, 3), dtype=np.uint8)

    # Draw the target image in the center of the screen with high intensity
    cv2.rectangle(screen, (25, 25), (75, 75), (255, 0, 0), -1)

    # Check if the target image is found due to high threshold
    assert check_image_presence(screen, target_img, threshold=0.7) == True

def test_check_image_presence_empty_target():
    # Create a sample screen and empty target image
    screen = np.zeros((100, 100, 3), dtype=np.uint8)
    target_img = None

    # Check if the function raises an error when target image is empty
    with pytest.raises(TypeError):
        check_image_presence(screen, target_img)

def test_check_image_presence_empty_screen():
    # Create a sample empty screen and target image
    screen = None
    target_img = np.zeros((50, 50, 3), dtype=np.uint8)

    # Check if the function raises an error when screen is empty
    with pytest.raises(TypeError):
        check_image_presence(screen, target_img)