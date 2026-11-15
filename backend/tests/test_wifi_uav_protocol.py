import unittest
from unittest import mock

from models.wifi_uav_rc import WifiUavRcModel
from protocols.wifi_uav_rc_protocol_adapter import WifiUavRcProtocolAdapter
from protocols.wifi_uav_video_protocol import WifiUavVideoProtocolAdapter
from utils.wifi_uav_mcu import describe_mcu_message, parse_mcu_packet
from utils.wifi_uav_packets import NEUTRAL_EXTENDED_COMMAND, VERSION_QUERY
from utils.wifi_uav_variants import get_wifi_uav_capabilities, map_wifi_uav_variant_from_ssid


class WifiUavRcProtocolTests(unittest.TestCase):
    def _adapter(self, variant="fld"):
        adapter = WifiUavRcProtocolAdapter.__new__(WifiUavRcProtocolAdapter)
        adapter._ctr1 = 0
        adapter._ctr2 = 1
        adapter._ctr3 = 2
        adapter.capabilities = get_wifi_uav_capabilities(variant)
        return adapter

    def _command_at(self, adapter, model, now):
        target = "protocols.wifi_uav_rc_protocol_adapter.time.monotonic"
        with mock.patch(target, return_value=now):
            return adapter.build_control_packet(model)[24]

    def test_takeoff_bit_is_held_then_released(self):
        model = WifiUavRcModel()
        adapter = self._adapter()
        hold = adapter.COMMAND_HOLD_S

        model.takeoff()
        self.assertEqual(self._command_at(adapter, model, 100.0) & 0x01, 0x01)
        self.assertEqual(self._command_at(adapter, model, 100.0 + hold / 2) & 0x01, 0x01)
        self.assertEqual(self._command_at(adapter, model, 100.0 + hold) & 0x01, 0x00)

    def test_click_during_hold_does_not_extend_it(self):
        model = WifiUavRcModel()
        adapter = self._adapter()
        hold = adapter.COMMAND_HOLD_S

        model.takeoff()
        self._command_at(adapter, model, 100.0)
        model.land()
        self.assertEqual(self._command_at(adapter, model, 100.0 + hold / 2) & 0x01, 0x01)
        self.assertEqual(self._command_at(adapter, model, 100.0 + hold) & 0x01, 0x00)

    def test_estop_cancels_held_takeoff(self):
        model = WifiUavRcModel()
        adapter = self._adapter()
        hold = adapter.COMMAND_HOLD_S

        model.takeoff()
        self._command_at(adapter, model, 100.0)
        model.emergency_stop()
        command = self._command_at(adapter, model, 100.01)
        self.assertEqual(command & 0x03, 0x02)
        self.assertEqual(self._command_at(adapter, model, 100.01 + hold / 2) & 0x03, 0x02)
        self.assertEqual(self._command_at(adapter, model, 100.01 + hold) & 0x03, 0x00)

    def test_estop_suppresses_takeoff_during_stop_hold(self):
        model = WifiUavRcModel()
        adapter = self._adapter()
        hold = adapter.COMMAND_HOLD_S

        model.emergency_stop()
        self.assertEqual(self._command_at(adapter, model, 100.0) & 0x03, 0x02)
        model.takeoff()
        self.assertEqual(self._command_at(adapter, model, 100.05) & 0x03, 0x02)
        self.assertEqual(self._command_at(adapter, model, 100.0 + hold) & 0x03, 0x00)

    def test_mcu_parser_rejects_declared_payload_past_packet_end(self):
        packet = bytearray(self._mcu_packet(bytes((1, 101))))
        packet[8:10] = (999).to_bytes(2, "little")
        self.assertIsNone(parse_mcu_packet(bytes(packet)))

    def test_held_command_keeps_checksum_valid(self):
        model = WifiUavRcModel()
        adapter = self._adapter()
        target = "protocols.wifi_uav_rc_protocol_adapter.time.monotonic"

        model.takeoff()
        with mock.patch(target, return_value=100.0):
            adapter.build_control_packet(model)
        with mock.patch(target, return_value=100.1):
            packet = adapter.build_control_packet(model)

        self.assertEqual(packet[36], packet[20] ^ packet[21] ^ packet[22] ^ packet[23] ^ packet[24] ^ packet[25])

    def _requests_sent_with(self, rc_adapter):
        video = WifiUavVideoProtocolAdapter.__new__(WifiUavVideoProtocolAdapter)
        video._rc_adapter = rc_adapter
        video._target_ports = (8800,)
        video._dbg = lambda *args, **kwargs: None
        video._build_ack_slots = lambda frame_id: []
        sent = []
        video._safe_sendto = lambda payload, port, label: sent.append(payload) or True
        video._send_frame_request(5)
        return sent

    def test_video_requests_carry_latest_command(self):
        model = WifiUavRcModel()
        adapter = self._adapter()
        model.takeoff()
        adapter.build_control_packet(model)

        requests = self._requests_sent_with(adapter)

        self.assertEqual(len(requests), 2)
        for request in requests:
            self.assertEqual(request[18:38], adapter.latest_command)
            self.assertEqual(request[24] & 0x01, 0x01)
            self.assertEqual(request[37], 0x99)

    def _mcu_packet(self, message):
        total = 12 + len(message)
        return (
            b"\x93\x04" + total.to_bytes(2, "little") + (7).to_bytes(4, "little")
            + len(message).to_bytes(2, "little") + b"\x00\x00" + message
        )

    def test_mcu_packet_parsing_rejects_other_packets(self):
        self.assertEqual(parse_mcu_packet(self._mcu_packet(b"\x01\x69")), b"\x01\x69")
        self.assertIsNone(parse_mcu_packet(b"\x93\x01" + bytes(60)))
        self.assertIsNone(parse_mcu_packet(self._mcu_packet(b"\x01\x69") + b"\x00"))

    def test_mcu_messages_are_described(self):
        self.assertEqual(describe_mcu_message(b"\x01\x69"), "MCU busy")
        self.assertEqual(describe_mcu_message(b"\x01\x6a"), "MCU disconnected")
        self.assertIn("battery=0x2a", describe_mcu_message(b"\x88\x00\x01\x2a\x10\x00\x55"))
        new = describe_mcu_message(b"\x01\x65BL608_V1 20240426 (FLOW)")
        self.assertIn("flow firmware", new)
        self.assertIn("extended commands supported", new)
        self.assertIn("NOT supported", describe_mcu_message(b"\x01\x65BL608_V1 20200101"))

    def _video_for_mcu_tests(self):
        video = WifiUavVideoProtocolAdapter.__new__(WifiUavVideoProtocolAdapter)
        video._target_ports = (8800,)
        video._version_known = False
        video._version_queries_left = 3
        video._next_version_query = 0.0
        video._last_mcu_log = {}
        video._unknown_packet_types = set()
        video.sent = []
        video._safe_sendto = lambda payload, port, label: video.sent.append(payload) or True
        return video

    def test_mcu_packets_are_consumed_and_stop_version_queries(self):
        video = self._video_for_mcu_tests()
        video._maybe_query_version()
        self.assertEqual(video.sent, [VERSION_QUERY])

        self.assertIsNone(video.handle_payload(self._mcu_packet(b"\x01\x65BL608_V1 20240426")))
        self.assertTrue(video._version_known)

        video._next_version_query = 0.0
        video._maybe_query_version()
        self.assertEqual(video.sent, [VERSION_QUERY])

    def test_version_queries_are_limited(self):
        video = self._video_for_mcu_tests()
        for _ in range(10):
            video._next_version_query = 0.0
            video._maybe_query_version()
        self.assertEqual(len(video.sent), 3)

    def test_unrecognized_packets_are_ignored(self):
        video = self._video_for_mcu_tests()
        self.assertIsNone(video.handle_payload(b"\x12\x34\x56"))
        self.assertIn(b"\x12\x34", video._unknown_packet_types)

    def test_video_requests_are_neutral_without_a_command(self):
        for request in self._requests_sent_with(None):
            self.assertEqual(request[18:38], NEUTRAL_EXTENDED_COMMAND)

    def test_camera_tilt_is_packed_into_extended_command_bits(self):
        model = WifiUavRcModel()
        model.set_camera_tilt_state(1)
        adapter = self._adapter()

        packet = adapter.build_control_packet(model)

        self.assertEqual(packet[24] & 0xC0, 0x40)
        self.assertEqual(packet[36], packet[20] ^ packet[21] ^ packet[22] ^ packet[23] ^ packet[24] ^ packet[25])
        self.assertEqual(model.camera_tilt_state, 0)

    def test_camera_tilt_up_uses_second_ptz_state(self):
        model = WifiUavRcModel()
        model.set_camera_tilt_state(2)
        adapter = self._adapter()

        packet = adapter.build_control_packet(model)

        self.assertEqual(packet[24] & 0xC0, 0x80)

    def test_fld_high_speed_uses_k417_axis_order(self):
        model = WifiUavRcModel()
        model.set_speed_index(2)
        model.yaw = 10
        model.pitch = 255
        model.throttle = 255
        model.roll = 240
        adapter = self._adapter()

        packet = adapter.build_control_packet(model)

        self.assertEqual(packet[20:24], bytes([240, 255, 255, 10]))

    def test_uav_high_speed_uses_app_axis_order(self):
        model = WifiUavRcModel()
        model.set_speed_index(2)
        model.yaw = 10
        model.pitch = 255
        model.throttle = 255
        model.roll = 240
        adapter = self._adapter("uav")

        packet = adapter.build_control_packet(model)

        self.assertEqual(packet[20:24], bytes([10, 255, 255, 240]))

    def test_low_speed_scales_yaw_pitch_roll_but_not_throttle(self):
        model = WifiUavRcModel()
        model.set_speed_index(0)
        model.yaw = 255
        model.pitch = 255
        model.throttle = 255
        model.roll = 255
        adapter = self._adapter()

        packet = adapter.build_control_packet(model)

        self.assertEqual(packet[20:24], bytes([166, 166, 255, 166]))

    def test_flow_ssids_use_legacy_compatible_default_variant(self):
        self.assertEqual(map_wifi_uav_variant_from_ssid("FLOW_123456"), "fld")
        self.assertEqual(map_wifi_uav_variant_from_ssid("FlOW_123456"), "fld")


if __name__ == "__main__":
    unittest.main()
