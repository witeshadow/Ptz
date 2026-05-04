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
        self.assertIn('id="cut-live-btn"', self.html)

    def test_explicit_scan_and_atem_mapping_hints_present(self):
        self.assertIn("ATEM Source Number", self.html)
        self.assertIn("ATEM bus status:", self.html)
        self.assertIn("PTZ scan uses:", self.html)
        self.assertIn("Current routed source:", self.html)
        self.assertIn("Direct Camera Capture", self.html)
        self.assertIn("Used when ATEM routing is off, or when", self.html)
        self.assertIn("Local Preview PIP", self.html)
        self.assertIn("Preview Device", self.html)
        self.assertIn("Confirmed Camera Stop", self.html)
        self.assertIn("Manual Dwell", self.html)
        self.assertIn("Local Preview", self.html)
        self.assertIn("USB Webcam", self.html)
        self.assertIn("SDI Out 4", self.html)
        self.assertIn("Source Label", self.html)
        self.assertIn("e.g. Multiview", self.html)
        self.assertIn("Scan source:", self.html)
        self.assertIn("Scan Output", self.html)
        self.assertIn("Active Cam", self.html)
        self.assertIn("Route to:", self.html)

    def test_positions_state_and_capture_integration(self):
        # positions initialized in state
        self.assertIn("positions: {},", self.html)
        # positions loaded from settings response
        self.assertIn(
            "if (s.positions) state.positions = { ...s.positions };", self.html
        )
        # position stored from /api/capture response
        self.assertIn(
            "if (data.position) state.positions[presetKey(cam, preset)] = data.position;",
            self.html,
        )
        # position stored from /api/image (webcam fallback) response
        self.assertIn(
            "if (webcamData.position) state.positions[presetKey(cam, preset)] = webcamData.position;",
            self.html,
        )
        # position cleared on image delete
        self.assertIn("delete state.positions[presetKey(activeCam, n)];", self.html)
        # position shown as tooltip on preset button
        self.assertIn(
            "Pan: ${pos.pan_hex}  Tilt: ${pos.tilt_hex}  Zoom: ${pos.zoom_hex}",
            self.html,
        )

    def test_snap_on_drift(self):
        # state and threshold
        self.assertIn("const snapNeeded = Object.create(null);", self.html)
        self.assertIn("const SNAP_POSITION_THRESHOLD = 10;", self.html)
        # helper functions exist
        self.assertIn("function posDiff(a, b)", self.html)
        self.assertIn("function clearSnapNeeded(cam, preset)", self.html)
        # drift check triggered after successful recall
        self.assertIn("checkPositionAfterRecall(n, recallCamIdx);", self.html)
        # needs-snap class applied when drift detected
        self.assertIn("btn.classList.add('needs-snap');", self.html)
        # needs-snap cleared after a new capture
        self.assertIn("clearSnapNeeded(cam, preset);", self.html)

    def test_active_cam_capture_mode(self):
        # ACT button exists in toolbar with correct data-src
        self.assertIn('data-src="active"', self.html)
        # captureFrame bypasses ATEM output map when captureSource is 'active'
        self.assertIn("state.captureSource !== 'active'", self.html)
        # updateCaptureModeVisibility shows direct capture settings for active mode
        self.assertIn("state.captureSource === 'active'", self.html)
        # changing capture source refreshes settings panel and status hints
        self.assertIn("updateCaptureModeVisibility();", self.html)
        self.assertIn("updateCameraStatusHints();", self.html)

    def test_joystick_state_is_normalized_and_visible(self):
        self.assertIn(
            'id="joystick-settings-section" class="gsp-extra-card gsp-mobile-section active" data-mobile-tab="atem"',
            self.html,
        )
        self.assertNotIn(
            'id="joystick-settings-section" class="gsp-extra-card gsp-mobile-section active" data-mobile-tab="atem" style="display:none;"',
            self.html,
        )
        self.assertIn("function normalizeJoystickSettings(value)", self.html)
        self.assertIn("joystick: normalizeJoystickSettings(),", self.html)
        self.assertIn(
            "if (s.joystick) state.joystick = normalizeJoystickSettings(s.joystick);",
            self.html,
        )
        self.assertIn(
            "const js = state.joystick = normalizeJoystickSettings(state.joystick);",
            self.html,
        )
        self.assertIn("state.joystick = normalizeJoystickSettings({", self.html)


if __name__ == "__main__":
    unittest.main()
