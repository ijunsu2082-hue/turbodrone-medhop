import unittest

from plugins.follow.follow_controller import FollowController
from plugins.follow.target_tracker import HOLDING, LOST, SEARCHING, TRACKING, Detection, TargetTracker


def person(x=0.5, width=0.2, confidence=0.9):
    return Detection((x - width / 2, 0.2, x + width / 2, 0.9), confidence)


class TargetTrackerTests(unittest.TestCase):
    def _locked(self, **kwargs):
        tracker = TargetTracker(**kwargs)
        tracker.update([person()], 0.0)
        self.assertEqual(tracker.update([person()], 0.1).state, TRACKING)
        return tracker

    def test_one_false_detection_does_not_lock(self):
        tracker = TargetTracker()
        self.assertEqual(tracker.update([person()], 0.0).state, LOST)
        self.assertEqual(tracker.update([], 0.1).state, LOST)
        self.assertEqual(tracker.update([person()], 0.2).state, LOST)
        self.assertEqual(tracker.update([person()], 0.3).state, TRACKING)

    def test_weak_detection_cannot_start_a_lock(self):
        tracker = TargetTracker()
        for t in range(5):
            self.assertEqual(tracker.update([person(confidence=0.2)], t * 0.1).state, LOST)

    def test_weak_detection_keeps_a_lock(self):
        tracker = self._locked()
        self.assertEqual(tracker.update([person(confidence=0.2)], 0.2).state, TRACKING)

    def test_weak_detection_elsewhere_is_ignored(self):
        tracker = self._locked()
        self.assertEqual(tracker.update([person(x=0.95, confidence=0.2)], 0.2).state, HOLDING)

    def test_stays_on_the_same_person_when_a_bigger_one_appears(self):
        tracker = self._locked()
        result = tracker.update([person(x=0.95, width=0.4), person(x=0.52)], 0.2)
        self.assertAlmostEqual(result.target.center_x, 0.52)

    def test_confident_detection_after_a_jump_is_followed(self):
        tracker = self._locked()
        result = tracker.update([person(x=0.95)], 0.2)
        self.assertEqual(result.state, TRACKING)
        self.assertAlmostEqual(result.target.center_x, 0.95)

    def test_lost_person_goes_hold_search_lost_then_needs_a_new_lock(self):
        tracker = self._locked(hold_s=0.5, search_s=2.0)
        self.assertEqual(tracker.update([], 0.4).state, HOLDING)
        self.assertEqual(tracker.update([], 1.5).state, SEARCHING)
        self.assertEqual(tracker.update([], 2.2).state, LOST)
        self.assertFalse(tracker.locked)
        self.assertEqual(tracker.update([person()], 2.3).state, LOST)
        self.assertEqual(tracker.update([person()], 2.4).state, TRACKING)


class FollowControllerTests(unittest.TestCase):
    def _controller(self, **kwargs):
        defaults = dict(
            yaw_deadzone=0.1, min_box_width=0.2, max_box_width=0.4, pitch_deadzone=0.02,
            yaw_speed=20, pitch_speed=20, yaw_max_speed=40, pitch_max_speed=35,
        )
        return FollowController(**{**defaults, **kwargs})

    def test_centered_and_right_distance_means_hover(self):
        self.assertEqual(self._controller().compute(0.5, 0.3), (0.0, 0.0))

    def test_yaw_grows_with_error_and_has_the_right_sign(self):
        ctrl = self._controller()
        self.assertAlmostEqual(ctrl.compute(0.61, 0.3, now=0.0)[0], 20.5, places=1)
        self.assertEqual(ctrl.compute(1.0, 0.3, now=0.0)[0], 40)
        self.assertEqual(ctrl.compute(0.0, 0.3, now=0.0)[0], -40)

    def test_pitch_moves_closer_when_far_and_back_when_close(self):
        ctrl = self._controller()
        self.assertGreater(ctrl.compute(0.5, 0.05)[1], 20)
        self.assertLess(ctrl.compute(0.5, 0.5)[1], -20)
        self.assertEqual(ctrl.compute(0.5, 1.0)[1], -35)

    def test_recover_backs_away_only_briefly_when_they_were_too_close(self):
        ctrl = self._controller(backoff_speed=25, backoff_s=1.5)
        self.assertEqual(ctrl.recover(0.5, 0.6, 1.0), (0.0, -25))
        self.assertEqual(ctrl.recover(0.5, 0.6, 2.0), (0.0, 0.0))

    def test_recover_turns_toward_last_seen_side(self):
        ctrl = self._controller(search_yaw_speed=25)
        self.assertEqual(ctrl.recover(0.9, 0.2, 1.0), (25, 0.0))
        self.assertEqual(ctrl.recover(0.1, 0.2, 1.0), (-25, 0.0))
        self.assertEqual(ctrl.recover(0.5, 0.2, 1.0), (0.0, 0.0))

    def test_invert_flags_apply_to_recovery(self):
        ctrl = self._controller(invert_yaw=True, invert_pitch=True, search_yaw_speed=25, backoff_speed=25)
        self.assertEqual(ctrl.recover(0.9, 0.2, 1.0), (-25, 0.0))
        self.assertEqual(ctrl.recover(0.5, 0.6, 1.0), (0.0, 25))


if __name__ == "__main__":
    unittest.main()
