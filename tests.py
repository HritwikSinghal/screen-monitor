import cv2
import numpy as np
import pytest

# Assuming the function definition is in main.py
from main import check_image_presence

def test_exact_match():
    # Create a screen with an exact match of the target image
    screen = np.zeros((100, 100), dtype=np.uint8)
    target_img = cv2.imread('path_to_target_image.png', cv2.IMREAD_GRAYSCALE)
    assert check_image_presence(screen, target_img) == True

def test_partial_match():
    # Create a screen with a partial match of the target image
    screen = np.zeros((100, 100), dtype=np.uint8)
    target_img = cv2.imread('path_to_target_image.png', cv2.IMREAD_GRAYSCALE)[:50, :50]
    assert check_image_presence(screen, target_img) == True

def test_no_match():
    # Create a screen with no match of the target image
    screen = np.zeros((100, 100), dtype=np.uint8)
    target_img = cv2.imread('path_to_another_image.png', cv2.IMREAD_GRAYSCALE)
    assert check_image_presence(screen, target_img) == False

def test_threshold_high():
    # Test with a high threshold
    screen = np.zeros((100, 100), dtype=np.uint8)
    target_img = cv2.imread('path_to_target_image.png', cv2.IMREAD_GRAYSCALE)
    assert check_image_presence(screen, target_img, threshold=0.9) == False

def test_threshold_low():
    # Test with a low threshold
    screen = np.zeros((100, 100), dtype=np.uint8)
    target_img = cv2.imread('path_to_target_image.png', cv2.IMREAD_GRAYSCALE)
    assert check_image_presence(screen, target_img, threshold=0.7) == True

def test_empty_screen():
    # Test with an empty screen
    screen = np.zeros((100, 100), dtype=np.uint8)
    target_img = np.zeros((50, 50), dtype=np.uint8)
    assert check_image_presence(screen, target_img) == False

def test_empty_target_image():
    # Test with an empty target image
    screen = np.zeros((100, 100), dtype=np.uint8)
    target_img = np.zeros((0, 0), dtype=np.uint8)
    assert check_image_presence(screen, target_img) == False

def test_nonexistent_target_image():
    # Test with a non-existent target image
    screen = np.zeros((100, 100), dtype=np.uint8)
    target_img_path = 'path_to_non_existent_image.png'
    with pytest.raises(FileNotFoundError):
        check_image_presence(screen, target_img_path)

if __name__ == "__main__":
    pytest.main()