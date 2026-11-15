import queue
import time
import unittest
from unittest import mock

import numpy as np

from models.wifi_uav_rc import WifiUavRcModel
from plugins.follow.follow_plugin import FollowPlugin
from protocols.wifi_uav_rc_protocol_adapter import WifiUavRcProtocolAdapter
from services.flight_controller import FlightController
from utils.wifi_uav_variants import get_wifi_uav_capabilities


class FakeModel:
    def __init__(self, speed_scale=1.0):
        self.strategy = "previous"
        self.expo_factor = 0.5
        self.speed_scale = speed_scale

    def set_strategy(self, strategy):
        self.strategy = strategy


class FakeFlightController:
    def __init__(self, model):
        self.model = model
        self.axes = (0.0, 0.0)
        self.manual = False

    def manual_override_active(self):
        return self.manual

    def set_axes_from(self, source, throttle, yaw, pitch, roll):
        self.axes = (yaw, pitch)


class FakeBox:
    def __init__(self, xyxy, conf):
        self.xyxy = [mock.Mock(tolist=lambda: xyxy)]
        self.conf = [conf]


def detector(xyxy, conf=0.9):
    return mock.Mock(side_effect=lambda *a, **k: [mock.Mock(boxes=[FakeBox(xyxy, conf)])])


FRAME = np.zeros((360, 640, 3), dtype=np.uint8)
FAR_RIGHT_PERSON = [560, 100, 620, 300]  # right of center, far away


class FollowPluginTests(unittest.TestCase):
    def _frame_source(self):
        while self.plugin.running:
            try:
                yield self.frames.get(timeout=0.02)
            except queue.Empty:
                continue

    def _start(self, model=None, command_timeout="0.3"):
        self.model = model or FakeModel()
        self.fc = FakeFlightController(self.model)
        self.frames = queue.Queue()
        with mock.patch.dict("os.environ", {"FOLLOW_COMMAND_TIMEOUT": command_timeout}), mock.patch(
            "plugins.follow.follow_plugin.YOLO", return_value=detector(FAR_RIGHT_PERSON)
        ):
            self.plugin = FollowPlugin("FollowPlugin", self.fc, self._frame_source())
            self.plugin.start()
        self.addCleanup(self.plugin.stop)
        return self.plugin

    def _wait_for(self, predicate, timeout=2.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return True
            self.frames.put(FRAME)
            time.sleep(0.06)
        return False

    def _start_steering(self, **kwargs):
        plugin = self._start(**kwargs)
        self.assertTrue(self._wait_for(lambda: self.fc.axes != (0.0, 0.0)))
        return plugin

    def test_steers_toward_a_person(self):
        self._start_steering(command_timeout="5")
        yaw, pitch = self.fc.axes
        self.assertGreater(yaw, 0)
        # Off center and too far away: it turns first, and doesn't fly forward yet.
        self.assertEqual(pitch, 0)
        self.assertEqual(self.plugin.status["state"], "tracking")

    def test_hovers_and_reports_when_video_freezes(self):
        self._start_steering()
        deadline = time.time() + 2
        while time.time() < deadline and self.fc.axes != (0, 0):
            time.sleep(0.02)
        self.assertEqual(self.fc.axes, (0, 0))
        self.assertEqual(self.plugin.status["state"], "no_video")

    def test_stop_hovers_and_restores_settings(self):
        plugin = self._start_steering(command_timeout="5")
        plugin.stop()
        self.assertEqual(self.fc.axes, (0, 0))
        self.assertEqual(self.model.strategy, "previous")
        self.assertEqual(self.model.expo_factor, 0.5)

    def test_commands_are_the_same_real_stick_amount_at_any_speed_tier(self):
        self._start_steering(command_timeout="5")
        full_scale_pitch = self.fc.axes[1]
        self.plugin.stop()
        self._start_steering(model=FakeModel(speed_scale=0.6), command_timeout="5")
        self.assertAlmostEqual(self.fc.axes[1], full_scale_pitch / 0.6)

    def test_never_exceeds_full_stick_at_low_tier(self):
        self._start_steering(model=FakeModel(speed_scale=0.3), command_timeout="5")
        self.assertLessEqual(abs(self.fc.axes[0]), 1.0)

    def test_sends_nothing_while_the_user_flies_by_hand(self):
        self._start_steering(command_timeout="5")
        self.fc.manual = True
        self.fc.axes = ("user", "user")
        for _ in range(3):
            self.frames.put(FRAME)
            time.sleep(0.06)
        self.assertEqual(self.fc.axes, ("user", "user"))
        self.assertTrue(self.plugin.status["paused"])

    def test_no_command_after_stop_during_detection(self):
        plugin = self._start_steering(command_timeout="5")

        def stop_mid_detection(*args, **kwargs):
            plugin.running = False
            return []

        plugin.model = mock.Mock(side_effect=stop_mid_detection)
        self.fc.axes = (0.0, 0.0)
        time.sleep(0.1)
        self.frames.put(FRAME)
        deadline = time.time() + 1
        while time.time() < deadline and not plugin.model.called:
            time.sleep(0.01)
        time.sleep(0.05)
        self.assertEqual(self.fc.axes, (0.0, 0.0))

    def test_retries_at_low_resolution_when_nothing_is_found(self):
        plugin = self._start(command_timeout="5")
        calls = []

        def only_finds_at_close_range(img, imgsz, **kwargs):
            calls.append(imgsz)
            boxes = [FakeBox([0, 0, 640, 360], 0.9)] if imgsz == plugin.CLOSE_RANGE_IMG_SIZE else []
            return [mock.Mock(boxes=boxes)]

        plugin.model = only_finds_at_close_range
        self.assertEqual(len(plugin._detect(FRAME)), 1)
        self.assertEqual(calls, [plugin.img_size, plugin.CLOSE_RANGE_IMG_SIZE])


class ManualOverrideTests(unittest.TestCase):
    def _controller(self):
        return FlightController(mock.Mock(), mock.Mock())

    def test_plugin_commands_apply_normally(self):
        fc = self._controller()
        fc.set_axes_from("follow", 0, 0.5, 0, 0)
        self.assertEqual(fc.yaw_dir, 0.5)

    def test_user_beats_plugin_until_the_hold_ends(self):
        fc = self._controller()
        fc.note_manual_input()
        fc.set_axes_from("frontend", 0, 0.9, 0, 0)
        fc.set_axes_from("follow", 0, 0.1, 0, 0)
        fc.set_axes_from("unknown", 0, 0.2, 0, 0)
        self.assertEqual(fc.yaw_dir, 0.9)

        fc._manual_until = 0.0
        fc.set_axes_from("follow", 0, 0.1, 0, 0)
        self.assertEqual(fc.yaw_dir, 0.1)

    def test_hold_can_be_longer_for_takeoff(self):
        fc = self._controller()
        fc.note_manual_input(5.0)
        self.assertGreater(fc._manual_until - time.monotonic(), 4.0)
        self.assertTrue(fc.manual_override_active())

    def test_stopping_a_plugin_always_applies(self):
        fc = self._controller()
        fc.yaw_dir = 0.5
        fc.note_manual_input()
        fc.set_axes_from("follow-stop", 0, 0, 0, 0)
        self.assertEqual(fc.yaw_dir, 0)


class AdapterPulseTests(unittest.TestCase):
    def _adapter(self):
        adapter = WifiUavRcProtocolAdapter.__new__(WifiUavRcProtocolAdapter)
        adapter._ctr1, adapter._ctr2, adapter._ctr3 = 0, 1, 2
        adapter.capabilities = get_wifi_uav_capabilities("fld")
        return adapter

    def _command(self, adapter, model, now):
        with mock.patch("protocols.wifi_uav_rc_protocol_adapter.time.monotonic", return_value=now):
            return adapter.build_control_packet(model)[24]

    def test_quick_tilt_click_lasts_the_minimum_pulse(self):
        adapter, model = self._adapter(), WifiUavRcModel()
        pulse = adapter.TILT_MIN_PULSE_S
        model.set_camera_tilt_state(2)
        self.assertEqual(self._command(adapter, model, 100.0) & 0xC0, 0x80)
        self.assertEqual(self._command(adapter, model, 100.0 + pulse / 2) & 0xC0, 0x80)
        self.assertEqual(self._command(adapter, model, 100.0 + pulse) & 0xC0, 0x00)

    def test_tilt_can_reverse_during_the_pulse(self):
        adapter, model = self._adapter(), WifiUavRcModel()
        model.set_camera_tilt_state(2)
        self._command(adapter, model, 100.0)
        model.set_camera_tilt_state(1)
        self.assertEqual(self._command(adapter, model, 100.1) & 0xC0, 0x40)

    def test_calibrate_bit_is_held_then_released(self):
        adapter, model = self._adapter(), WifiUavRcModel()
        model.calibrate_gyro()
        self.assertEqual(self._command(adapter, model, 100.0) & 0x04, 0x04)
        self.assertEqual(self._command(adapter, model, 100.0 + adapter.COMMAND_HOLD_S / 2) & 0x04, 0x04)
        self.assertEqual(self._command(adapter, model, 100.0 + adapter.COMMAND_HOLD_S) & 0x04, 0x00)

    def test_speed_scale_matches_tier(self):
        model = WifiUavRcModel()
        model.set_speed_index(0)
        self.assertEqual(model.speed_scale, 0.30)


if __name__ == "__main__":
    unittest.main()
