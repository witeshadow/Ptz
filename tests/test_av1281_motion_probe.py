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


if __name__ == "__main__":
    unittest.main()
