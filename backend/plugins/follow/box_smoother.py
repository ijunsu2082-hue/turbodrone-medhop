"""Steady the detected box, so steering doesn't chase detector jitter or moving arms."""
from __future__ import annotations

from collections import deque
from statistics import median


class BoxSmoother:
    """
    Filters the target box before it is used for steering.

    Side-to-side position must stay quick, so it gets a light filter. Box width is
    only a rough guide to distance and changes whenever arms move, so it takes the
    median of about the last second.
    """

    # A box cut off by the frame edge is narrower than the person really is.
    EDGE_MARGIN = 0.02
    # Wider than this, the person is too close whether or not the box is cut off.
    CLIPPED_WIDTH_LIMIT = 0.5

    def __init__(self, center_alpha: float = 0.6, width_window_s: float = 1.0):
        self.center_alpha = center_alpha
        self.width_window_s = width_window_s
        self.reset()

    def reset(self) -> None:
        self._recent_centers: deque[float] = deque(maxlen=3)
        self._center: float | None = None
        self._widths: deque[tuple[float, float]] = deque()

    def update(self, box: tuple[float, float, float, float], now: float) -> tuple[float, float]:
        """Add a detection and return the steady (center_x, width)."""
        x1, _, x2, _ = box
        center, width = (x1 + x2) / 2, x2 - x1

        self._recent_centers.append(center)
        middle = median(self._recent_centers)
        if self._center is None:
            self._center = middle
        else:
            self._center += self.center_alpha * (middle - self._center)

        clipped = x1 <= self.EDGE_MARGIN or x2 >= 1.0 - self.EDGE_MARGIN
        if not clipped or width >= self.CLIPPED_WIDTH_LIMIT or not self._widths:
            self._widths.append((now, width))
        while len(self._widths) > 1 and now - self._widths[0][0] > self.width_window_s:
            self._widths.popleft()

        return self._center, median(w for _, w in self._widths)
