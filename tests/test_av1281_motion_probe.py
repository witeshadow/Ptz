"""Tests for the AV-1281 VISCA motion probe script."""

import socket
import unittest
from unittest.mock import patch

from scripts import av1281_motion_probe as probe


class TestViscaParsing(unittest.TestCase):
    def test_ack_and_completion_allow_any_socket_nibble(self):
        ack = probe.classify_visca_payload(bytes([0x90, 0x42, 0xFF]))
        completion = probe.classify_visca_payload(bytes([0x90, 0x53, 0xFF]))

        self.assertIsNotNone(ack)
        self.assertEqual(ack.kind, "ack")
        self.assertEqual(ack.socket_number, 2)

        self.assertIsNotNone(completion)
        self.assertEqual(completion.kind, "completion")
        self.assertEqual(completion.socket_number, 3)

    def test_parse_pan_tilt_payload(self):
        payload = bytes(
            [0x90, 0x50, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0xFF]
        )
        self.assertEqual(probe.parse_pan_tilt_payload(payload), (0x1234, 0x5678))

    def test_parse_zoom_or_focus_payload(self):
        payload = bytes([0x90, 0x50, 0x00, 0x0A, 0x0B, 0x0C, 0xFF])
        self.assertEqual(probe.parse_zoom_or_focus_payload(payload), 0x0ABC)

    def test_parse_pan_tilt_rejects_non_nibble_bytes(self):
        payload = bytes(
            [0x90, 0x50, 0x10, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0xFF]
        )
        self.assertIsNone(probe.parse_pan_tilt_payload(payload))


class TestSendInquiry(unittest.TestCase):
    def test_timeout_reports_sent_inquiry_and_observed_replies(self):
        class FakeSocket:
            def settimeout(self, _timeout):
                return None

        recv_calls = []

        def fake_recv(_sock, _transport):
            recv_calls.append(True)
            if len(recv_calls) == 1:
                return bytes([0x90, 0x41, 0xFF])
            raise socket.timeout()

        with (
            patch("scripts.av1281_motion_probe.send_command"),
            patch("scripts.av1281_motion_probe.recv_payload", side_effect=fake_recv),
            patch("scripts.av1281_motion_probe.time.monotonic", side_effect=[0.0, 0.1, 0.2, 1.1]),
        ):
            with self.assertRaises(TimeoutError) as ctx:
                probe.send_inquiry(
                    FakeSocket(),
                    "10.0.0.1",
                    1259,
                    bytes([0x81, 0x09, 0x06, 0x12, 0xFF]),
                    "raw-udp",
                    probe.SequenceCounter(),
                    1.0,
                    probe.parse_pan_tilt_payload,
                )

        self.assertIn("to 81090612ff", str(ctx.exception))
        self.assertIn("saw 9041ff", str(ctx.exception))


class _FakeProbeSocket:
    def bind(self, _addr):
        return None

    def settimeout(self, _timeout):
        return None

    def getsockname(self):
        return ("0.0.0.0", 52381)

    def close(self):
        return None


class TestProbePreset(unittest.TestCase):
    def test_preserves_completion_when_settle_polling_fails(self):
        completion = probe.ViscaReply("completion", 0x90, 0x51, b"\x90\x51\xff", 1)

        with (
            patch("socket.socket", return_value=_FakeProbeSocket()),
            patch("scripts.av1281_motion_probe.send_command"),
            patch(
                "scripts.av1281_motion_probe.wait_for_completion",
                return_value=([completion], True),
            ),
            patch(
                "scripts.av1281_motion_probe.query_motion_sample",
                side_effect=TimeoutError("inquiry timeout"),
            ),
            patch(
                "scripts.av1281_motion_probe.time.monotonic",
                side_effect=[0.0, 0.0, 0.0],
            ),
        ):
            result = probe.probe_preset(
                ip="10.0.0.1",
                port=52381,
                camera_address=1,
                preset=5,
                transport="sony-udp",
                local_port=None,
                completion_timeout=2.0,
                settle_timeout=8.0,
                poll_interval=0.2,
                stable_count=3,
                inquiry_timeout=1.0,
                include_focus=False,
                require_settle=True,
                verbose=False,
            )

        self.assertTrue(result.saw_completion)
        self.assertEqual(result.replies, [completion])
        self.assertFalse(result.settled)
        self.assertIsNone(result.error)

    def test_reports_error_when_no_completion_arrived_before_polling_failure(self):
        with (
            patch("socket.socket", return_value=_FakeProbeSocket()),
            patch("scripts.av1281_motion_probe.send_command"),
            patch(
                "scripts.av1281_motion_probe.wait_for_completion",
                return_value=([], False),
            ),
            patch(
                "scripts.av1281_motion_probe.query_motion_sample",
                side_effect=TimeoutError("inquiry timeout"),
            ),
            patch(
                "scripts.av1281_motion_probe.time.monotonic",
                side_effect=[0.0, 0.0, 0.0],
            ),
        ):
            result = probe.probe_preset(
                ip="10.0.0.1",
                port=52381,
                camera_address=1,
                preset=5,
                transport="sony-udp",
                local_port=None,
                completion_timeout=2.0,
                settle_timeout=8.0,
                poll_interval=0.2,
                stable_count=3,
                inquiry_timeout=1.0,
                include_focus=False,
                require_settle=True,
                verbose=False,
            )

        self.assertFalse(result.saw_completion)
        self.assertEqual(result.replies, [])
        self.assertFalse(result.settled)
        self.assertEqual(result.error, "inquiry timeout")


if __name__ == "__main__":
    unittest.main()
