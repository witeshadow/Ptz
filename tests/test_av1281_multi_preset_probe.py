"""Tests for the AV-1281 multi-preset probe script."""

import unittest

from scripts import av1281_multi_preset_probe as batch_probe


class TestPresetSpecParsing(unittest.TestCase):
    def test_parse_single_values_and_ranges(self):
        self.assertEqual(batch_probe.parse_preset_spec("1,3,5-7"), [1, 3, 5, 6, 7])

    def test_parse_descending_range(self):
        self.assertEqual(batch_probe.parse_preset_spec("7-5"), [7, 6, 5])

    def test_parse_rejects_empty_input(self):
        with self.assertRaises(ValueError):
            batch_probe.parse_preset_spec(" , ")


if __name__ == "__main__":
    unittest.main()
