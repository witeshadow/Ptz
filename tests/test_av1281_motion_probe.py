"""Tests for the AV-1281 VISCA motion probe script."""

import unittest

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
        payload = bytes([0x90, 0x50, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0xFF])
        self.assertEqual(probe.parse_pan_tilt_payload(payload), (0x1234, 0x5678))

    def test_parse_zoom_or_focus_payload(self):
        payload = bytes([0x90, 0x50, 0x00, 0x0A, 0x0B, 0x0C, 0xFF])
        self.assertEqual(probe.parse_zoom_or_focus_payload(payload), 0x0ABC)

    def test_parse_pan_tilt_rejects_non_nibble_bytes(self):
        payload = bytes([0x90, 0x50, 0x10, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0xFF])
        self.assertIsNone(probe.parse_pan_tilt_payload(payload))


if __name__ == "__main__":
    unittest.main()
