import time
from collections import deque


class FollowController:
    """
    Calculates yaw/pitch commands to keep a target centered and at a stable distance.

    Commands grow with the error: the stated speed at the edge of the deadzone, up
    to the max speed when the target is at the frame edge (yaw), or far too near or
    far away (pitch). A gentle fixed command gets the target back when it is lost.

    The drone keeps turning for a moment after a command, and the video shows it late.
    Steering on what the video shows right now overshoots the target and swings back
    and forth forever, so yaw allows for the turn that is still on its way.
    """

    # Measured on the real drone: full stick turns the view about this many frame
    # widths per second, and a command takes about this long to fully reach the video.
    TURN_RATE = 3.0
    TURN_LATENCY_S = 0.5
    # Yaw: once turning, keep going until the target is this close to center.
    YAW_STOP_ZONE = 0.05
    # Pitch: once moving, keep going until this far inside the wanted size range.
    PITCH_STOP_MARGIN = 0.03
    # Don't fly forward at a target this far off center. Turn toward it first.
    FORWARD_CENTER_LIMIT = 0.25

    def __init__(
        self,
        yaw_deadzone: float = 0.15,
        pitch_deadzone: float = 0.02,
        min_box_width: float = 0.30,
        max_box_width: float = 0.80,
        invert_yaw: bool = False,
        invert_pitch: bool = False,
        yaw_speed: float = 20.0,
        pitch_speed: float = 20.0,
        yaw_max_speed: float | None = None,
        pitch_max_speed: float | None = None,
        search_yaw_speed: float = 25.0,
        backoff_speed: float = 25.0,
        backoff_s: float = 1.5,
    ):
        self.yaw_deadzone = yaw_deadzone
        self.pitch_deadzone = pitch_deadzone
        self.min_box_width = min_box_width
        self.max_box_width = max_box_width
        self.invert_yaw = invert_yaw
        self.invert_pitch = invert_pitch
        self.yaw_speed = self._limit(yaw_speed)
        self.pitch_speed = self._limit(pitch_speed)
        self.yaw_max_speed = self.yaw_speed if yaw_max_speed is None else max(self.yaw_speed, self._limit(yaw_max_speed))
        self.pitch_max_speed = self.pitch_speed if pitch_max_speed is None else max(self.pitch_speed, self._limit(pitch_max_speed))
        self.search_yaw_speed = self._limit(search_yaw_speed)
        self.backoff_speed = self._limit(backoff_speed)
        self.backoff_s = backoff_s
        self.reset()

    def reset(self) -> None:
        """Forget any move in progress."""
        self._turning = False
        self._distance_direction = 0
        self._recent_turns: deque[tuple[float, float]] = deque()

    @staticmethod
    def limit_rise(previous: float, target: float, max_change: float) -> float:
        """Ease into a stronger command, to avoid jerks. Slowing down is immediate."""
        if previous * target < 0:
            previous = 0.0
        if abs(target) <= abs(previous):
            return target
        return max(previous - max_change, min(previous + max_change, target))

    @staticmethod
    def _limit(speed: float) -> float:
        return min(100.0, max(0.0, speed))

    @staticmethod
    def _ramp(low: float, high: float, amount: float) -> float:
        return low + (high - low) * min(1.0, max(0.0, amount))

    def _turn_on_the_way(self, now: float) -> float:
        """How far, in frame widths, recent commands will still move the target in view."""
        while self._recent_turns and now - self._recent_turns[0][0] > self.TURN_LATENCY_S:
            self._recent_turns.popleft()
        total = 0.0
        turns = list(self._recent_turns)
        for (started, turn), (ended, _) in zip(turns, turns[1:] + [(now, 0.0)]):
            total += turn / 100.0 * (ended - started)
        return total * self.TURN_RATE

    def compute(self, box_center_x: float, box_width: float, now: float | None = None) -> tuple[float, float]:
        """
        Compute yaw and pitch commands.

        Args:
            box_center_x: Normalized x position of box center (0.0 = left, 1.0 = right)
            box_width: Normalized width of box (0.0 to 1.0)

        Returns:
            (yaw, pitch) commands in range -100 to 100
        """
        now = time.monotonic() if now is None else now

        # Yaw: rotate to center the target horizontally
        error_x = box_center_x - 0.5
        error_size = abs(error_x)
        expected_error = error_x - self._turn_on_the_way(now)
        expected_size = abs(expected_error)
        if expected_size < self.YAW_STOP_ZONE:
            self._turning = False
        elif expected_size > self.yaw_deadzone:
            self._turning = True

        turn = 0.0
        if self._turning:
            amount = max(0.0, expected_size - self.yaw_deadzone) / (0.5 - self.yaw_deadzone)
            turn = self._ramp(self.yaw_speed, self.yaw_max_speed, amount)
            if expected_error < 0:
                turn = -turn
        self._recent_turns.append((now, turn))
        yaw = -turn if self.invert_yaw else turn

        # Pitch: move forward/backward to keep target at desired size
        too_far = self.min_box_width - self.pitch_deadzone
        too_close = self.max_box_width + self.pitch_deadzone
        if box_width < too_far:
            self._distance_direction = 1
        elif box_width > too_close:
            self._distance_direction = -1
        elif self._distance_direction > 0 and box_width >= self.min_box_width + self.PITCH_STOP_MARGIN:
            self._distance_direction = 0
        elif self._distance_direction < 0 and box_width <= self.max_box_width - self.PITCH_STOP_MARGIN:
            self._distance_direction = 0

        pitch = 0.0
        if self._distance_direction > 0 and error_size <= self.FORWARD_CENTER_LIMIT:
            pitch = self._ramp(self.pitch_speed, self.pitch_max_speed, max(0.0, too_far - box_width) / too_far)
        elif self._distance_direction < 0:
            pitch = -self._ramp(self.pitch_speed, self.pitch_max_speed, max(0.0, box_width - too_close) / (1.0 - too_close))
        if self.invert_pitch:
            pitch = -pitch

        return yaw, pitch

    def recover(self, last_center_x: float, last_width: float, lost_for: float) -> tuple[float, float]:
        """
        Compute a command to get a lost target back in view.

        If they were too close, back away for a moment: detection fails when a
        person fills the frame. Otherwise turn toward the side they were last seen.
        """
        if last_width >= self.max_box_width:
            if lost_for > self.backoff_s:
                return 0.0, 0.0
            return 0.0, self.backoff_speed if self.invert_pitch else -self.backoff_speed

        error_x = last_center_x - 0.5
        if abs(error_x) <= self.yaw_deadzone:
            return 0.0, 0.0
        yaw = self.search_yaw_speed if (error_x > 0) != self.invert_yaw else -self.search_yaw_speed
        return yaw, 0.0
