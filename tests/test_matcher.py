import cv2
import numpy as np
import pytest

from src.matcher import TemplateMatcher


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def make_template() -> np.ndarray:
    """A 96x96 synthetic badge: concentric rings plus an off-centre mark."""
    tpl = np.full((96, 96, 3), 40, np.uint8)
    cv2.circle(tpl, (48, 48), 44, (200, 120, 30), -1)
    cv2.circle(tpl, (48, 48), 30, (40, 90, 200), 6)
    cv2.rectangle(tpl, (38, 30), (58, 50), (60, 220, 250), -1)
    cv2.line(tpl, (10, 85), (85, 10), (0, 0, 0), 4)
    return tpl


def make_screen(width: int, template: np.ndarray | None, rel_size: float = 0.05) -> np.ndarray:
    """A 16:9 noisy frame with ``template`` pasted near the top-left corner.

    The template's rendered size is proportional to the frame width, mimicking
    a video watermark that grows when its window is resized.
    """
    height = round(width * 9 / 16)
    rng = np.random.default_rng(width)
    screen = rng.integers(60, 120, (height, width, 3), dtype=np.uint8)
    if template is not None:
        side = round(width * rel_size)
        scaled = cv2.resize(template, (side, side), interpolation=cv2.INTER_AREA)
        y, x = round(height * 0.04), round(width * 0.03)
        screen[y : y + side, x : x + side] = scaled
    return screen


@pytest.mark.parametrize("width", [1280, 1912, 2560, 3840])
def test_matches_regardless_of_window_size(width):
    tpl = make_template()
    matcher = TemplateMatcher(tpl)
    assert matcher.match(make_screen(width, tpl))


def test_no_match_when_target_absent():
    matcher = TemplateMatcher(make_template())
    assert not matcher.match(make_screen(1912, None))


@pytest.mark.parametrize(
    "screen",
    [None, np.zeros((0, 0, 3), np.uint8), np.zeros((100, 100), np.uint8), np.zeros((10, 10, 3), np.uint8)],
)
def test_degenerate_screens_do_not_match_or_crash(screen):
    assert not TemplateMatcher(make_template()).match(screen)


def test_rejects_grayscale_template():
    with pytest.raises(ValueError):
        TemplateMatcher(np.zeros((50, 50), np.uint8))


def test_same_shape_in_wrong_colours_is_rejected():
    """Grayscale-identical but colour-different shapes must not match.

    Swapping B and R keeps the structure, and nearly the luminance pattern,
    while the colour NCC confirmation should reject it.
    """
    tpl = make_template()
    impostor = make_screen(1912, tpl[:, :, ::-1].copy())
    assert not TemplateMatcher(tpl).match(impostor)


def test_sweep_throttled_while_absent_but_immediate_on_resize():
    tpl = make_template()
    clock = FakeClock()
    matcher = TemplateMatcher(tpl, clock=clock, resweep_interval=1.0)
    present_small = make_screen(1912, tpl)
    assert matcher.match(present_small)
    small_scale = matcher.cached_scale

    # Same frame size, target gone (ad): no sweep inside the interval.
    sweeps = []
    original = matcher._sweep
    matcher._sweep = lambda pyr: sweeps.append(1) or original(pyr)
    absent = make_screen(1912, None)
    clock.now = 0.5
    assert not matcher.match(absent)
    assert sweeps == []  # only the last position was re-checked
    clock.now = 1.5
    assert not matcher.match(absent)
    assert sweeps == [1]  # throttle elapsed: one full sweep

    # Frame size changes and the target's relative size with it (e.g. a
    # monitor capture where only the video window grew): sweep runs at once
    # even though the throttle interval has not elapsed.
    clock.now = 1.6
    assert matcher.match(make_screen(3840, tpl, rel_size=0.04))
    assert matcher.cached_scale != small_scale


def _desktop_with_window(window_w: int, tpl: np.ndarray, at: tuple[int, int]) -> np.ndarray:
    """A 4K monitor capture with a ``make_screen`` window pasted at ``at``."""
    rng = np.random.default_rng(7)
    desk = rng.integers(20, 60, (2160, 3840, 3), dtype=np.uint8)
    win = make_screen(window_w, tpl)
    x, y = at
    desk[y : y + win.shape[0], x : x + win.shape[1]] = win
    return desk


@pytest.mark.parametrize("window_w", [960, 1912, 3000])
def test_monitor_capture_finds_target_in_any_window_size(window_w):
    tpl = make_template()
    assert TemplateMatcher(tpl).match(_desktop_with_window(window_w, tpl, (300, 200)))


def test_moved_target_found_again_after_throttled_resweep():
    tpl = make_template()
    clock = FakeClock()
    matcher = TemplateMatcher(tpl, clock=clock, resweep_interval=1.0)
    assert matcher.match(_desktop_with_window(1912, tpl, (300, 200)))
    moved = _desktop_with_window(1912, tpl, (1500, 900))
    clock.now = 0.5
    assert not matcher.match(moved)  # tracked position is empty; throttled
    clock.now = 1.5
    assert matcher.match(moved)
