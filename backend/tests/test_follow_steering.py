"""Follow steering must settle on a still person, not swing back and forth."""
import unittest

from plugins.follow.box_smoother import BoxSmoother
from plugins.follow.follow_controller import FollowController


def controller(**kwargs):
    settings = dict(
        yaw_deadzone=0.12, yaw_speed=10, yaw_max_speed=30, pitch_deadzone=0.02,
        pitch_speed=15, pitch_max_speed=30, min_box_width=0.18, max_box_width=0.40,
    )
    settings.update(kwargs)
    return FollowController(**settings)


def fly_toward_still_person(rate, delay, seconds=30.0):
    """Model of the real drone's turning. Returns the offsets seen and direction changes."""
    ctrl = controller()
    step, decide_every = 1 / 90, 1 / 11
    heading = turn_rate = stick = 0.0
    history = [(0.0, 0.0)]
    start_offset = 0.3
    offsets, changes, last_direction = [], 0, 0
    now = next_decision = 0.0
    while now < seconds:
        turn_rate += (rate * stick - turn_rate) * step / 0.15
        heading += turn_rate * step
        history.append((now, heading))
        if now >= next_decision:
            next_decision = now + decide_every
            seen = [h for t, h in history if t <= now - delay][-1] if now >= delay else 0.0
            offset = start_offset - seen
            yaw, _ = ctrl.compute(0.5 + offset, 0.3, now)
            stick = yaw / 100
            offsets.append(offset)
            direction = (yaw > 0) - (yaw < 0)
            if direction and last_direction and direction != last_direction:
                changes += 1
            if direction:
                last_direction = direction
        now += step
    return offsets, changes


class SteeringTests(unittest.TestCase):
    def test_settles_on_a_still_person_at_measured_drone_speeds(self):
        for rate in (1.35, 2.35, 3.0, 4.18):
            for delay in (0.15, 0.3, 0.45):
                with self.subTest(rate=rate, delay=delay):
                    offsets, changes = fly_toward_still_person(rate, delay)
                    settled = offsets[len(offsets) // 2:]
                    self.assertLess(max(abs(o) for o in settled), 0.13)
                    self.assertLessEqual(changes, 1)

    def test_small_offset_is_left_alone(self):
        yaw, _ = controller().compute(0.58, 0.3, 0.0)
        self.assertEqual(yaw, 0)

    def test_stops_turning_while_the_last_turn_is_still_on_its_way(self):
        ctrl = controller()
        first, _ = ctrl.compute(0.8, 0.3, 0.0)
        self.assertGreater(first, 0)
        # The video hasn't caught up yet, and the person still looks far off center.
        later = [ctrl.compute(0.8, 0.3, t / 10)[0] for t in range(1, 5)]
        self.assertLess(later[-1], first)

    def test_invert_yaw_flips_the_command(self):
        yaw, _ = controller(invert_yaw=True).compute(0.9, 0.3, 0.0)
        self.assertLess(yaw, 0)

    def test_turns_toward_a_far_person_before_flying_forward(self):
        yaw, pitch = controller().compute(0.85, 0.05, 0.0)
        self.assertGreater(yaw, 0)
        self.assertEqual(pitch, 0)

    def test_backs_away_when_too_close_even_off_center(self):
        _, pitch = controller().compute(0.85, 0.7, 0.0)
        self.assertLess(pitch, 0)

    def test_distance_move_runs_until_well_inside_the_range(self):
        ctrl = controller()
        self.assertLess(ctrl.compute(0.5, 0.45, 0.0)[1], 0)
        self.assertLess(ctrl.compute(0.5, 0.40, 0.1)[1], 0)
        self.assertEqual(ctrl.compute(0.5, 0.36, 0.2)[1], 0)
        self.assertEqual(ctrl.compute(0.5, 0.41, 0.3)[1], 0)

    def test_commands_ease_in_and_stop_at_once(self):
        limit = FollowController.limit_rise
        self.assertEqual(limit(0.0, 30.0, 10.0), 10.0)
        self.assertEqual(limit(0.0, -30.0, 10.0), -10.0)
        self.assertEqual(limit(30.0, 0.0, 10.0), 0.0)
        self.assertEqual(limit(20.0, -30.0, 10.0), -10.0)


class BoxSmootherTests(unittest.TestCase):
    def test_a_one_frame_width_spike_is_ignored(self):
        smoother = BoxSmoother()
        for i in range(8):
            smoother.update((0.3, 0, 0.6, 1), i / 10)
        _, width = smoother.update((0.05, 0, 0.95, 1), 0.8)
        self.assertAlmostEqual(width, 0.3)

    def test_a_real_width_change_gets_through(self):
        smoother = BoxSmoother()
        for i in range(8):
            smoother.update((0.3, 0, 0.6, 1), i / 10)
        for i in range(8, 20):
            _, width = smoother.update((0.2, 0, 0.8, 1), i / 10)
        self.assertAlmostEqual(width, 0.6)

    def test_a_box_cut_off_by_the_frame_edge_does_not_count_as_far_away(self):
        smoother = BoxSmoother()
        smoother.update((0.3, 0, 0.6, 1), 0.0)
        for i in range(1, 15):
            _, width = smoother.update((0.0, 0, 0.1, 1), i / 10)
        self.assertAlmostEqual(width, 0.3)

    def test_center_follows_quickly(self):
        smoother = BoxSmoother()
        smoother.update((0.1, 0, 0.3, 1), 0.0)
        for i in range(1, 6):
            center, _ = smoother.update((0.6, 0, 0.8, 1), i / 10)
        self.assertGreater(center, 0.65)


if __name__ == "__main__":
    unittest.main()
