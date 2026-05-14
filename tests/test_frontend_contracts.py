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

    def test_delete_image_is_hidden(self):
        # Clear button is hidden in the new per-preset edit design
        self.assertRegex(
            self.html,
            r"\.preset-clear\s*\{[^}]*display:\s*none;",
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

    def test_live_protection_and_manage_copy_are_explicit(self):
        self.assertIn(
            "Protect Live Camera is on. Switch away from the live camera or turn protection off to modify this mapping.",
            self.html,
        )
        self.assertIn(
            "Protect Live Camera is on. Label changes are safe, but recapturing the image is blocked while this camera is live on ATEM program.",
            self.html,
        )
        self.assertIn(
            "Tap Manage on a preset to rename it or recapture its image",
            self.html,
        )
        self.assertIn("Follow Active Camera", self.html)
        self.assertIn('<option value="off">Off</option>', self.html)
        self.assertIn('id="preset-manage-sheet"', self.html)
        self.assertIn("manageBtn.className = 'preset-manage';", self.html)

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
        self.assertIn("delete state.positions[presetKey(cam, preset)];", self.html)
        # position shown as tooltip on preset button
        self.assertIn(
            "Pan: ${pos.pan_hex}  Tilt: ${pos.tilt_hex}  Zoom: ${pos.zoom_hex}",
            self.html,
        )

    def test_image_cache_busting_stays_newer_than_boot_urls(self):
        self.assertIn("const prev = imageVersions[key] || bootImageVersion;", self.html)
        self.assertIn("imageVersions[key] = Math.max(Date.now(), prev + 1);", self.html)

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
        self.assertIn("Needs Recapture", self.html)
        self.assertIn("open Manage to recapture", self.html)

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

    def test_live_scan_controls_validate_atem_bus_selection(self):
        self.assertIn("if (btnScanEl) btnScanEl.style.display = '';", self.html)
        self.assertIn(
            "elCaptureToggle.style.display = state.atem.enabled ? 'flex' : 'none';",
            self.html,
        )
        self.assertIn("function validateAtemCaptureSelection(camIdx)", self.html)
        self.assertIn(
            "${camName} is not on ATEM ${busLabel}. Put it there first or switch scan source.",
            self.html,
        )

    def test_status_pill_wraps_long_errors_and_preserves_full_copy(self):
        self.assertIn("#status.multiline #status-text {", self.html)
        self.assertIn("const multiline = type === 'error' && msg.length > 32;", self.html)
        self.assertIn("elStatus.title = msg;", self.html)
        self.assertIn("#status.warning {", self.html)
        self.assertIn("Recapture stopped at preset ${recallFailure.preset}", self.html)
        self.assertIn(
            "ATEM ${busLabel} capture needs a reported output. Use Active Cam routing or an SDI output instead of USB Webcam.",
            self.html,
        )

    def test_build_indicator_uses_version_endpoint(self):
        self.assertIn("function applyBuildVersion(version)", self.html)
        self.assertIn("fetch('/api/version')", self.html)
        self.assertIn(
            "elBuildCommit.title = `${branch} @ ${shortCommit} (${dirty}, ${defaultState})`;",
            self.html,
        )

    def test_auto_cut_uses_trigger_to_skip_fallback_delay(self):
        self.assertIn(
            "const usingCompletionFallback = trigger === 'completion';",
            self.html,
        )
        self.assertIn(
            "const usingTimeoutFallback = trigger === 'timeout';",
            self.html,
        )
        self.assertIn(
            "const effectiveDelayMs = usingTimeoutFallback",
            self.html,
        )
        self.assertIn(
            "waiting up to ${delayLabel}s more for fallback max",
            self.html,
        )
        self.assertIn(
            "? 'on VISCA completion'",
            self.html,
        )
        self.assertIn(
            "? 'on fallback max timeout'",
            self.html,
        )

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
        self.assertIn("function normalizeVirtualJoystickSettings(value)", self.html)
        self.assertIn("joystick: normalizeJoystickSettings(),", self.html)
        self.assertIn("virtualJoystick: normalizeVirtualJoystickSettings(),", self.html)
        self.assertIn(
            "if (s.joystick) state.joystick = normalizeJoystickSettings(s.joystick);",
            self.html,
        )
        self.assertIn(
            "if (s.virtualJoystick) state.virtualJoystick = normalizeVirtualJoystickSettings(s.virtualJoystick);",
            self.html,
        )
        self.assertIn(
            "const js = state.joystick = normalizeJoystickSettings(state.joystick);",
            self.html,
        )
        self.assertIn(
            "state.virtualJoystick = normalizeVirtualJoystickSettings(state.virtualJoystick);",
            self.html,
        )
        self.assertIn("state.joystick = normalizeJoystickSettings({", self.html)

    def test_virtual_joystick_response_curve_and_snapback_guard_present(self):
        self.assertIn("let lastVirtualJoystickCommand = { pan: 0, tilt: 0 };", self.html)
        self.assertIn(
            "let pendingVirtualJoystickDirection = { pan: 0, tilt: 0 };",
            self.html,
        )
        self.assertIn("const DEFAULT_VIRTUAL_JOYSTICK_RESPONSE_EXPONENT = 1.35;", self.html)
        self.assertIn("const VIRTUAL_JOYSTICK_AXIS_STEP = 0.05;", self.html)
        self.assertIn("function applyVirtualJoystickResponseCurve(value)", self.html)
        self.assertIn(
            "return Math.sign(n) * Math.pow(Math.abs(n), DEFAULT_VIRTUAL_JOYSTICK_RESPONSE_EXPONENT);",
            self.html,
        )
        self.assertIn("function quantizeVirtualJoystickAxis(value)", self.html)
        self.assertIn(
            "function applyVirtualJoystickSnapbackGuard(next, previous, axis)",
            self.html,
        )
        self.assertIn(
            "if (pendingVirtualJoystickDirection[axis] !== nextDirection) {",
            self.html,
        )
        self.assertIn(
            "pendingVirtualJoystickDirection[axis] = nextDirection;",
            self.html,
        )
        self.assertIn(
            "pan = applyVirtualJoystickSnapbackGuard(pan, lastVirtualJoystickCommand.pan, 'pan');",
            self.html,
        )
        self.assertIn(
            "tilt = applyVirtualJoystickSnapbackGuard(tilt, lastVirtualJoystickCommand.tilt, 'tilt');",
            self.html,
        )

    def test_ptz_stop_retries_are_retained_after_centering(self):
        self.assertIn("const PTZ_STOP_RETRY_COUNT = 8;", self.html)
        self.assertIn("const PTZ_STOP_RETRY_INTERVAL_MS = 120;", self.html)
        self.assertIn("stopResendRemaining: 0,", self.html)
        self.assertIn("function clearPtzStopRetryTimer()", self.html)
        self.assertIn("function schedulePtzStopRetry()", self.html)
        self.assertIn("void flushPtzDriveController();", self.html)
        self.assertIn("ptzDriveController.stopResendRemaining = PTZ_STOP_RETRY_COUNT;", self.html)
        self.assertIn("schedulePtzStopRetry();", self.html)

    def test_virtual_joystick_deadzone_uses_smaller_default(self):
        self.assertIn("const DEFAULT_VIRTUAL_JOYSTICK_DEADZONE = 0.10;", self.html)
        self.assertIn(": DEFAULT_VIRTUAL_JOYSTICK_DEADZONE;", self.html)
        self.assertIn("const deadzone = state.virtualJoystick?.deadzone ?? DEFAULT_VIRTUAL_JOYSTICK_DEADZONE;", self.html)
        self.assertIn("deadzone: DEFAULT_VIRTUAL_JOYSTICK_DEADZONE,", self.html)

    def test_virtual_joystick_zoom_slider_drives_combined_command(self):
        self.assertIn("let virtualJoystickCommand = { pan: 0, tilt: 0, zoom: 0 };", self.html)
        self.assertIn("let virtualZoomTouchId = null;", self.html)
        self.assertIn('id="joystick-zoom-slider"', self.html)
        self.assertIn('id="joystick-zoom-track"', self.html)
        self.assertIn('id="joystick-zoom-thumb"', self.html)
        self.assertIn("function sendVirtualJoystickCommand(", self.html)
        self.assertIn("function stopVirtualJoystickZoom()", self.html)
        self.assertIn("function setVirtualJoystickZoom(direction)", self.html)
        self.assertIn("function applyVirtualZoomDeadzone(value)", self.html)
        self.assertIn("const VIRTUAL_ZOOM_DEADZONE = 0.08;", self.html)
        self.assertIn("function positionVirtualZoomThumb(zoom = virtualJoystickCommand.zoom)", self.html)
        self.assertIn("function updateVirtualZoomFromClientY(clientY)", self.html)
        self.assertIn("function resetVirtualZoomSlider()", self.html)
        self.assertIn("elJoystickZoomSlider.style.display = 'block';", self.html)
        self.assertIn("sendVirtualJoystickCommand(pan, tilt, virtualJoystickCommand.zoom);", self.html)
        self.assertIn("virtualZoomTouchId = touch.identifier;", self.html)
        self.assertIn("updateVirtualZoomFromClientY(touch.clientY);", self.html)
        self.assertIn("resetVirtualZoomSlider();", self.html)

    def test_virtual_joystick_zoom_slider_uses_mobile_friendly_sizes(self):
        self.assertIn("width:60px; height:176px;", self.html)
        self.assertIn("width:44px; height:44px;", self.html)
        self.assertIn("zoomControlWidth: 60,", self.html)
        self.assertIn("zoomControlWidth: 72,", self.html)
        self.assertIn("zoomControlWidth: 84,", self.html)
        self.assertIn("zoomThumbSize: 44,", self.html)
        self.assertIn("zoomThumbSize: 50,", self.html)
        self.assertIn("zoomThumbSize: 58,", self.html)
        self.assertIn("elJoystickZoomSlider.style.width = `${metrics.zoomControlWidth}px`;", self.html)
        self.assertIn("elJoystickZoomThumb.style.width = `${metrics.zoomThumbSize}px`;", self.html)

    def test_virtual_joystick_size_controls_present(self):
        self.assertIn('id="f-virtual-joystick-size"', self.html)
        self.assertIn('id="joystick-size-btn"', self.html)
        self.assertIn("const VIRTUAL_JOYSTICK_SIZE_ORDER = ['normal', 'double', 'fullscreen'];", self.html)
        self.assertIn("function applyVirtualJoystickLayout()", self.html)
        self.assertIn("function cycleVirtualJoystickSize()", self.html)
        self.assertIn("setVirtualJoystickSize(next);", self.html)

    def test_dpad_invalid_warn_is_deduplicated(self):
        # Deduplication guard variable is initialized to true (valid by default).
        self.assertIn("let lastDpadValid = true;", self.html)

        # The warn is wrapped in a conditional so it fires only on the first
        # invalid frame, not on every subsequent polling cycle.
        self.assertIn("if (lastDpadValid) {", self.html)
        self.assertIn(
            "console.warn('[D-PAD] Invalid button indices for profile:'",
            self.html,
        )

        # Guard is set to false immediately after the conditional warn so that
        # repeated invalid frames are suppressed.
        self.assertIn("lastDpadValid = false;", self.html)

        # Guard is reset to true when indices become valid again, so a
        # subsequent invalid→invalid transition will warn once more.
        self.assertIn("lastDpadValid = true;", self.html)

    def test_dpad_warn_not_called_unconditionally(self):
        # The warn must only appear inside the `if (lastDpadValid)` guard, never
        # at the surrounding indentation level (which would mean it fires every
        # polling frame regardless of state).
        #
        # The guarded block looks like (4-space indent inside the if(!validIndices)
        # branch, 6-space inside the if(lastDpadValid) block):
        #
        #   if (lastDpadValid) {
        #     console.warn('[D-PAD] ...
        #
        # Use a newline-anchored substring so that the indentation comparison is
        # against the beginning of the physical line rather than an arbitrary
        # mid-line slice.
        guarded_warn = (
            "if (lastDpadValid) {\n"
            "        console.warn('[D-PAD] Invalid button indices for profile:'"
        )
        # A warn that starts a line with fewer spaces than the guarded form
        # would indicate the call escaped the guard.  The actual indented line
        # starts with 8 spaces; a 6-space-anchored line prefix cannot be a
        # substring of that because the character after the 6 spaces would be
        # a space, not 'c'.
        unguarded_line = "\n      console.warn('[D-PAD] Invalid button indices for profile:'"
        self.assertIn(guarded_warn, self.html)
        self.assertNotIn(unguarded_line, self.html)

    def test_dpad_valid_reset_is_outside_invalid_branch(self):
        # `lastDpadValid = true` must appear *after* the invalid-indices block
        # so that recovery from invalid back to valid is correctly tracked.
        #
        # str.index("lastDpadValid = true;") would match the *initializer*
        # `let lastDpadValid = true;` which comes first.  Instead we search for
        # `lastDpadValid = false;` first, then locate `lastDpadValid = true;`
        # *starting from that position* to confirm the reset-to-true comes later.
        idx_false = self.html.index("lastDpadValid = false;")
        idx_true_after_false = self.html.find("lastDpadValid = true;", idx_false)
        self.assertGreater(
            idx_true_after_false,
            idx_false,
            "lastDpadValid = true must appear after lastDpadValid = false in source",
        )

    def test_dpad_invalid_branch_resets_state(self):
        # On invalid indices the D-pad state, last-state, and gamepad pan/tilt
        # must all be zeroed/cleared so that no stale movement is emitted.
        # These lines were pre-existing but the PR preserves them; assert they
        # remain consistent with the new guard logic.
        self.assertIn(
            "dpadState = { up: false, down: false, left: false, right: false };",
            self.html,
        )
        self.assertIn("lastDpadState = { ...dpadState };", self.html)
        self.assertIn("gamepadState.pan = 0;", self.html)
        self.assertIn("gamepadState.tilt = 0;", self.html)


if __name__ == "__main__":
    unittest.main()
