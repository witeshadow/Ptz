"""Frontend contract tests for public/index.html."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "public" / "index.html"


class TestFrontendContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX_HTML.read_text(encoding="utf-8")

    def test_compact_camera_strip_present(self):
        self.assertIn('id="fill-cam-strip"', self.html)
        self.assertNotIn('id="fill-cam-select"', self.html)

    def test_delete_image_is_edit_mode_only(self):
        # Clear button is always visible in edit mode (opacity-based, not hover-gated)
        self.assertIn(
            ".preset-btn.edit-mode.has-image .preset-clear { display: flex;",
            self.html,
        )
        self.assertNotIn(
            ".preset-btn.has-image:hover .preset-clear { display: flex; }",
            self.html,
        )

    def test_atem_pill_supports_off_wait_and_connected_states(self):
        self.assertIn("ATEM Off", self.html)
        self.assertIn("ATEM Wait", self.html)
        self.assertIn("ATEM P${program} V${preview}", self.html)

    def test_explicit_scan_and_atem_mapping_hints_present(self):
        self.assertIn("ATEM Source Number", self.html)
        self.assertIn("ATEM bus status:", self.html)
        self.assertIn("PTZ scan uses:", self.html)
        self.assertIn("Current routed source:", self.html)
        self.assertIn("USB Webcam", self.html)
        self.assertIn("SDI Out 4", self.html)
        self.assertIn("Source Label", self.html)
        self.assertIn("e.g. Multiview", self.html)
        self.assertIn("Used For Scans", self.html)


if __name__ == "__main__":
    unittest.main()
