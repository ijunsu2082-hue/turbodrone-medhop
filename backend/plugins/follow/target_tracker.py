"""Decide which detection is the person being followed, across imperfect frames."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

TRACKING = "tracking"    # seen in this frame
HOLDING = "holding"      # missed for a moment; assume nothing changed
SEARCHING = "searching"  # missed for longer; try to get them back in view
LOST = "lost"            # gave up; hover until someone is seen again

Box = tuple[float, float, float, float]  # x1, y1, x2, y2 as fractions of the frame


@dataclass(frozen=True)
class Detection:
    box: Box
    confidence: float

    @property
    def width(self) -> float:
        return self.box[2] - self.box[0]

    @property
    def center_x(self) -> float:
        return (self.box[0] + self.box[2]) / 2

    @property
    def area(self) -> float:
        return self.width * (self.box[3] - self.box[1])


@dataclass(frozen=True)
class TrackResult:
    state: str
    target: Optional[Detection]  # the person, or where they were last seen
    lost_for: float = 0.0


def _overlap(a: Box, b: Box) -> float:
    """Intersection over union of two boxes."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


class TargetTracker:
    """
    Locks on to one person and stays with them through weak or missed detections.

    A new lock needs a confident detection on two frames in a row, so one false
    detection can't send the drone after a coat rack. Once locked, a much weaker
    detection is enough as long as it is where the person was.
    """

    def __init__(
        self,
        acquire_confidence: float = 0.35,
        keep_confidence: float = 0.15,
        hold_s: float = 0.5,
        search_s: float = 2.5,
        max_jump: float = 0.25,
    ) -> None:
        self.acquire_confidence = acquire_confidence
        self.keep_confidence = keep_confidence
        self.hold_s = hold_s
        self.search_s = search_s
        self.max_jump = max_jump
        self._target: Optional[Detection] = None
        self._last_seen = 0.0
        self._candidate: Optional[Detection] = None

    @property
    def locked(self) -> bool:
        return self._target is not None

    def update(self, detections: Sequence[Detection], now: float) -> TrackResult:
        match = self._match_locked(detections) if self.locked else self._acquire(detections)
        if match is not None:
            self._target = match
            self._last_seen = now
            return TrackResult(TRACKING, match)

        if not self.locked:
            return TrackResult(LOST, None)

        lost_for = now - self._last_seen
        if lost_for <= self.hold_s:
            return TrackResult(HOLDING, self._target, lost_for)
        if lost_for <= self.search_s:
            return TrackResult(SEARCHING, self._target, lost_for)

        last = self._target
        self._target = None
        self._candidate = None
        return TrackResult(LOST, last, lost_for)

    def _match_locked(self, detections: Sequence[Detection]) -> Optional[Detection]:
        target = self._target
        nearby = [
            d for d in detections
            if d.confidence >= self.keep_confidence
            and (
                _overlap(d.box, target.box) > 0.05
                or abs(d.center_x - target.center_x) < self.max_jump
            )
        ]
        if nearby:
            return max(nearby, key=lambda d: (_overlap(d.box, target.box), d.confidence))
        # They may have moved fast, or the frame jumped. Trust a confident detection.
        confident = [d for d in detections if d.confidence >= self.acquire_confidence]
        return max(confident, key=lambda d: d.area) if confident else None

    def _acquire(self, detections: Sequence[Detection]) -> Optional[Detection]:
        confident = [d for d in detections if d.confidence >= self.acquire_confidence]
        if not confident:
            self._candidate = None
            return None
        best = max(confident, key=lambda d: d.area)
        previous = self._candidate
        self._candidate = best
        if previous is not None and _overlap(previous.box, best.box) > 0.1:
            return best
        return None
