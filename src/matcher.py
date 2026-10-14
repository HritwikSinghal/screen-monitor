"""Scale-tolerant template matching.

The on-screen size of the target (e.g. a broadcaster watermark) follows the
size of the window showing it: fullscreening a 1912px-wide window on a 4K
monitor doubles it, shrinking the window halves it, and a single-scale
``matchTemplate`` then never matches. ``TemplateMatcher`` searches a set of
template scales, remembers the one that last matched so the steady state costs
a single match, and only re-sweeps when the frame size changes or (throttled)
while the target is missing.
"""

import time
from collections.abc import Callable, Sequence

import cv2
import numpy as np

# Template scale factors in frame pixels, relative to the template image's own
# size. The NCC peak is narrow (a real watermark scored 0.86 at the right scale
# and 0.62 one 15% step away), so steps are ~8%. 0.25-3x covers the target in
# anything from a quarter-size window to a fullscreen 4K one.
DEFAULT_SCALES: tuple[float, ...] = tuple(
    float(s) for s in np.geomspace(0.25, 3.0, num=33)
)

# Each scale is matched on the coarsest frame pyramid level (frame halved L
# times) where the template is still at least this many pixels. Smaller
# templates carry too little structure for NCC to be discriminative; larger
# ones waste CPU, since matching cost grows with frame area. Scales whose
# full-resolution size is already below this are dropped.
MIN_TEMPLATE_PX = 20
MAX_PYRAMID_LEVEL = 4

# Sweeps run coarse-to-fine: every scale is first matched (grayscale only) one
# pyramid level down, where the template may be as small as this, and only the
# best COARSE_CANDIDATES peaks above COARSE_THRESHOLD are re-scored at full
# detail around their location. This cuts a sweep over a 4K frame ~4x.
COARSE_MIN_PX = 10
COARSE_THRESHOLD = 0.5
COARSE_CANDIDATES = 5

# While the target is missing (e.g. during an ad), a full scale sweep runs at
# most this often; the cached scale is still checked every frame, so the
# target reappearing at the same size is detected immediately.
RESWEEP_INTERVAL_SEC = 1.0


class _Pyramid:
    """Lazily built half-resolution levels of one frame, BGR and gray."""

    def __init__(self, bgr: np.ndarray):
        self._bgr = [bgr]
        self._gray: dict[int, np.ndarray] = {}

    def bgr(self, level: int) -> np.ndarray:
        while len(self._bgr) <= level:
            prev = self._bgr[-1]
            size = (max(1, prev.shape[1] // 2), max(1, prev.shape[0] // 2))
            self._bgr.append(cv2.resize(prev, size, interpolation=cv2.INTER_AREA))
        return self._bgr[level]

    def gray(self, level: int) -> np.ndarray:
        if level not in self._gray:
            self._gray[level] = cv2.cvtColor(self.bgr(level), cv2.COLOR_BGR2GRAY)
        return self._gray[level]


class _Scale:
    __slots__ = ("bgr", "coarse_gray", "coarse_level", "gray", "level", "scale")

    def __init__(self, template: np.ndarray, scale: float, level: int):
        self.scale = scale
        self.level = level
        self.bgr = _resize(template, scale / 2**level)
        self.gray = cv2.cvtColor(self.bgr, cv2.COLOR_BGR2GRAY)
        coarse = scale / 2 ** (level + 1)
        if level < MAX_PYRAMID_LEVEL and min(template.shape[:2]) * coarse >= COARSE_MIN_PX:
            self.coarse_level = level + 1
            self.coarse_gray = cv2.cvtColor(_resize(template, coarse), cv2.COLOR_BGR2GRAY)
        else:
            self.coarse_level = level
            self.coarse_gray = self.gray


def _resize(img: np.ndarray, factor: float) -> np.ndarray:
    size = (max(1, round(img.shape[1] * factor)), max(1, round(img.shape[0] * factor)))
    interp = cv2.INTER_AREA if factor < 1 else cv2.INTER_CUBIC
    return cv2.resize(img, size, interpolation=interp)


class TemplateMatcher:
    """Matches a BGR template against BGR frames.

    Candidates are found with grayscale NCC and confirmed with colour NCC on a
    small region around the grayscale peak. Grayscale alone lets round,
    high-contrast shapes in ads (a cricket-ball "O") score ~0.75-0.8 against a
    round badge; colour pushed the same ad frame down to ~0.6 while the real
    badge stayed ~0.95.

    Once found, only a small region around the last hit is checked per frame,
    so the steady state is cheap even on a 4K monitor capture. A full sweep
    runs when the frame size changes, or at most every ``resweep_interval``
    seconds while the target is not at its last position.
    """

    def __init__(
        self,
        template: np.ndarray,
        threshold: float = 0.8,
        scales: Sequence[float] = DEFAULT_SCALES,
        resweep_interval: float = RESWEEP_INTERVAL_SEC,
        clock: Callable[[], float] = time.monotonic,
    ):
        if template.ndim != 3 or template.shape[2] != 3:
            raise ValueError("template must be a 3-channel BGR image")
        self.threshold = threshold
        self.resweep_interval = resweep_interval
        self._clock = clock
        side = min(template.shape[:2])
        self._scales: list[_Scale] = []
        for s in scales:
            if side * s < MIN_TEMPLATE_PX:
                continue
            level = 0
            while level < MAX_PYRAMID_LEVEL and side * s / 2 ** (level + 1) >= MIN_TEMPLATE_PX:
                level += 1
            self._scales.append(_Scale(template, s, level))
        if not self._scales:
            raise ValueError("template too small for every configured scale")
        # Last hit: (index into self._scales, x, y) in that scale's level coords.
        self._hit: tuple[int, int, int] | None = None
        self._frame_shape: tuple[int, ...] | None = None
        self._last_sweep = float("-inf")
        # Best confirmed score from the last match() that actually scored
        # (None when it was throttled or the frame was unusable); logged on
        # mute transitions so a threshold that is too tight is visible.
        self.last_score: float | None = None

    @property
    def cached_scale(self) -> float | None:
        return None if self._hit is None else self._scales[self._hit[0]].scale

    def _score_near(
        self, pyr: _Pyramid, idx: int, x: int, y: int, margin: int
    ) -> tuple[float, int, int]:
        """Best confirmed score for scale ``idx`` within ``margin`` px of (x, y)."""
        sc = self._scales[idx]
        gray = pyr.gray(sc.level)
        th, tw = sc.gray.shape
        x0, y0 = max(0, x - margin), max(0, y - margin)
        roi = gray[y0 : y + th + margin, x0 : x + tw + margin]
        if roi.shape[0] < th or roi.shape[1] < tw:
            return -1.0, x, y
        _, peak, _, (px, py) = cv2.minMaxLoc(cv2.matchTemplate(roi, sc.gray, cv2.TM_CCOEFF_NORMED))
        x, y = x0 + px, y0 + py
        if peak < self.threshold:
            return float(peak), x, y
        # Small margin so the colour peak can sit a pixel or two off the
        # grayscale one without the ROI clipping the template.
        m = 2
        roi = pyr.bgr(sc.level)[max(0, y - m) : y + th + m, max(0, x - m) : x + tw + m]
        return float(cv2.matchTemplate(roi, sc.bgr, cv2.TM_CCOEFF_NORMED).max()), x, y

    def _sweep(self, pyr: _Pyramid) -> tuple[tuple[int, int, int] | None, float]:
        candidates = []
        for idx, sc in enumerate(self._scales):
            gray = pyr.gray(sc.coarse_level)
            th, tw = sc.coarse_gray.shape
            if th > gray.shape[0] or tw > gray.shape[1]:
                continue
            _, peak, _, (x, y) = cv2.minMaxLoc(
                cv2.matchTemplate(gray, sc.coarse_gray, cv2.TM_CCOEFF_NORMED)
            )
            if peak >= COARSE_THRESHOLD:
                k = 2 ** (sc.coarse_level - sc.level)
                candidates.append((peak, idx, x * k, y * k))
        candidates.sort(reverse=True)
        best, best_score = None, -1.0
        for _, idx, x, y in candidates[:COARSE_CANDIDATES]:
            score, x, y = self._score_near(pyr, idx, x, y, margin=4)
            if score > best_score:
                best, best_score = (idx, x, y), score
        return (best if best_score >= self.threshold else None), best_score

    def match(self, screen: np.ndarray | None) -> bool:
        """True if the template is visible in ``screen`` (BGR) at any scale."""
        self.last_score = None
        if screen is None or screen.ndim != 3 or screen.shape[2] != 3 or screen.size == 0:
            return False
        resized = screen.shape != self._frame_shape
        self._frame_shape = screen.shape
        pyr = _Pyramid(screen)
        if not resized:
            if self._hit is not None:
                idx, x, y = self._hit
                score, x, y = self._score_near(pyr, idx, x, y, margin=8)
                self.last_score = score
                if score >= self.threshold:
                    self._hit = (idx, x, y)
                    return True
            if self._clock() - self._last_sweep < self.resweep_interval:
                return False

        self._last_sweep = self._clock()
        hit, score = self._sweep(pyr)
        if self.last_score is None or score > self.last_score:
            self.last_score = score
        if hit is None:
            # Keep the old hit: once the ad ends the target usually returns
            # where, and at the size, it was before.
            return False
        self._hit = hit
        return True
