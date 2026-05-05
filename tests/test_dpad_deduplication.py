"""Tests for D-pad warning deduplication logic in public/index.html.

PR: Fix: Deduplicate invalid D-pad warning to prevent console spam

The change introduces a `lastDpadValid` flag so that the console.warn about
invalid D-pad button indices is only emitted once per valid→invalid transition,
rather than on every gamepad poll cycle while indices remain invalid.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "public" / "index.html"


class TestDpadDeduplicationFlag(unittest.TestCase):
    """Tests that the lastDpadValid flag is correctly declared and initialized."""

    @classmethod
    def setUpClass(cls):
        cls.html = INDEX_HTML.read_text(encoding="utf-8")

    def test_lastDpadValid_variable_declared(self):
        """lastDpadValid must be declared as a module-level variable."""
        self.assertIn("let lastDpadValid", self.html)

    def test_lastDpadValid_initialized_to_true(self):
        """lastDpadValid must start as true so the first invalid call always warns."""
        self.assertIn("let lastDpadValid = true;", self.html)

    def test_lastDpadValid_declaration_near_dpad_state(self):
        """lastDpadValid should be declared in the same region as the other dpad state variables."""
        idx_dpad_state = self.html.index("let dpadState")
        idx_last_dpad_state = self.html.index("let lastDpadState")
        idx_last_dpad_valid = self.html.index("let lastDpadValid = true;")
        # All three declarations should be within 500 characters of each other
        positions = sorted([idx_dpad_state, idx_last_dpad_state, idx_last_dpad_valid])
        self.assertLess(
            positions[-1] - positions[0],
            500,
            "lastDpadValid should be declared near the other dpad state variables",
        )


class TestDpadDeduplicationGuard(unittest.TestCase):
    """Tests that console.warn is guarded by the lastDpadValid flag."""

    @classmethod
    def setUpClass(cls):
        cls.html = INDEX_HTML.read_text(encoding="utf-8")

    def test_warn_is_guarded_by_lastDpadValid(self):
        """The console.warn for invalid indices must be inside an if (lastDpadValid) block."""
        self.assertIn("if (lastDpadValid)", self.html)
        # Verify the guard and the warn are in proximity
        idx_guard = self.html.index("if (lastDpadValid)")
        idx_warn = self.html.index(
            "console.warn('[D-PAD] Invalid button indices for profile:"
        )
        self.assertLess(
            abs(idx_guard - idx_warn),
            200,
            "The if (lastDpadValid) guard must be immediately before the console.warn",
        )

    def test_warn_message_content_preserved(self):
        """The console.warn message text must be unchanged from before the PR."""
        self.assertIn(
            "console.warn('[D-PAD] Invalid button indices for profile:'", self.html
        )

    def test_warn_references_cfg_model(self):
        """The warn must still log cfg.model for diagnosability."""
        # Verify the warn line includes cfg.model
        warn_idx = self.html.index(
            "console.warn('[D-PAD] Invalid button indices for profile:"
        )
        warn_line_end = self.html.index("\n", warn_idx)
        warn_line = self.html[warn_idx:warn_line_end]
        self.assertIn("cfg.model", warn_line)

    def test_warn_references_dpadMap(self):
        """The warn must still log dpadMap for diagnosability."""
        warn_idx = self.html.index(
            "console.warn('[D-PAD] Invalid button indices for profile:"
        )
        warn_line_end = self.html.index("\n", warn_idx)
        warn_line = self.html[warn_idx:warn_line_end]
        self.assertIn("dpadMap", warn_line)

    def test_warn_references_buttons_length(self):
        """The warn must still log the number of gamepad buttons."""
        warn_idx = self.html.index(
            "console.warn('[D-PAD] Invalid button indices for profile:"
        )
        warn_line_end = self.html.index("\n", warn_idx)
        warn_line = self.html[warn_idx:warn_line_end]
        self.assertIn("gamepad.buttons.length", warn_line)


class TestDpadDeduplicationInvalidBranch(unittest.TestCase):
    """Tests that lastDpadValid is correctly set to false in the invalid branch."""

    @classmethod
    def setUpClass(cls):
        cls.html = INDEX_HTML.read_text(encoding="utf-8")
        # Isolate the updateDpadInput function body for scoped assertions
        fn_start = cls.html.index("function updateDpadInput(gamepad, cfg)")
        # Find the closing brace of the function by looking for the next top-level function
        fn_end = cls.html.index("function getAutoCutDelaySeconds", fn_start)
        cls.fn_body = cls.html[fn_start:fn_end]

    def test_lastDpadValid_set_false_in_invalid_branch(self):
        """lastDpadValid must be set to false when button indices are invalid."""
        self.assertIn("lastDpadValid = false;", self.fn_body)

    def test_lastDpadValid_false_comes_after_guard(self):
        """Setting lastDpadValid=false must come AFTER the if (lastDpadValid) guard,
        so repeated invalid calls skip the warning after the first."""
        idx_guard = self.fn_body.index("if (lastDpadValid)")
        idx_set_false = self.fn_body.index("lastDpadValid = false;")
        self.assertGreater(
            idx_set_false,
            idx_guard,
            "lastDpadValid = false must come after the if (lastDpadValid) guard",
        )

    def test_dpadState_reset_still_occurs_on_invalid(self):
        """dpadState must still be reset to all-false when indices are invalid."""
        # The reset should still happen regardless of the guard
        self.assertIn(
            "dpadState = { up: false, down: false, left: false, right: false };",
            self.fn_body,
        )

    def test_lastDpadState_reset_still_occurs_on_invalid(self):
        """lastDpadState must still be reset in the invalid branch."""
        self.assertIn("lastDpadState = { ...dpadState };", self.fn_body)

    def test_gamepad_pan_reset_still_occurs_on_invalid(self):
        """gamepadState.pan must still be reset to 0 when indices are invalid."""
        self.assertIn("gamepadState.pan = 0;", self.fn_body)

    def test_gamepad_tilt_reset_still_occurs_on_invalid(self):
        """gamepadState.tilt must still be reset to 0 when indices are invalid."""
        self.assertIn("gamepadState.tilt = 0;", self.fn_body)

    def test_early_return_still_present_after_invalid(self):
        """The early return must still be present in the invalid branch so valid
        processing is skipped when indices are bad."""
        # Find the invalid branch (after !validIndices check)
        invalid_block_start = self.fn_body.index("if (!validIndices)")
        invalid_block_end = self.fn_body.index("lastDpadValid = true;", invalid_block_start)
        invalid_block = self.fn_body[invalid_block_start:invalid_block_end]
        self.assertIn("return;", invalid_block)


class TestDpadDeduplicationValidBranch(unittest.TestCase):
    """Tests that lastDpadValid is reset to true in the valid branch."""

    @classmethod
    def setUpClass(cls):
        cls.html = INDEX_HTML.read_text(encoding="utf-8")
        fn_start = cls.html.index("function updateDpadInput(gamepad, cfg)")
        fn_end = cls.html.index("function getAutoCutDelaySeconds", fn_start)
        cls.fn_body = cls.html[fn_start:fn_end]

    def test_lastDpadValid_set_true_in_valid_branch(self):
        """lastDpadValid must be reset to true after successful validation so a
        future invalid state re-triggers the warning."""
        self.assertIn("lastDpadValid = true;", self.fn_body)

    def test_lastDpadValid_true_comes_after_invalid_check(self):
        """lastDpadValid=true assignment must be outside (after) the invalid branch,
        meaning it only executes when indices are actually valid."""
        idx_invalid_block = self.fn_body.index("if (!validIndices)")
        # The `lastDpadValid = true;` that comes after the invalid block
        idx_set_true = self.fn_body.index("lastDpadValid = true;")
        self.assertGreater(
            idx_set_true,
            idx_invalid_block,
            "lastDpadValid = true must appear after the if (!validIndices) block",
        )

    def test_lastDpadValid_true_not_inside_invalid_block(self):
        """lastDpadValid=true must not appear inside the invalid (!validIndices) block,
        which would neutralize the deduplication."""
        idx_invalid_block_start = self.fn_body.index("if (!validIndices)")
        # The invalid block ends at the `return;` before lastDpadValid=true
        idx_true = self.fn_body.index("lastDpadValid = true;")
        # The early return in the invalid branch comes before lastDpadValid=true
        early_return_idx = self.fn_body.rindex("return;", idx_invalid_block_start, idx_true)
        self.assertLess(
            early_return_idx,
            idx_true,
            "The early return in the invalid branch must precede lastDpadValid = true",
        )


class TestDpadDeduplicationTransitionLogic(unittest.TestCase):
    """Tests that verify the overall deduplication pattern is structurally correct."""

    @classmethod
    def setUpClass(cls):
        cls.html = INDEX_HTML.read_text(encoding="utf-8")
        fn_start = cls.html.index("function updateDpadInput(gamepad, cfg)")
        fn_end = cls.html.index("function getAutoCutDelaySeconds", fn_start)
        cls.fn_body = cls.html[fn_start:fn_end]

    def test_deduplication_pattern_order(self):
        """Verify the complete deduplication pattern appears in the correct order:
        1. if (lastDpadValid) { warn }
        2. lastDpadValid = false
        3. [early return]
        4. lastDpadValid = true
        """
        idx_guard = self.fn_body.index("if (lastDpadValid)")
        idx_set_false = self.fn_body.index("lastDpadValid = false;")
        idx_set_true = self.fn_body.index("lastDpadValid = true;")

        self.assertLess(idx_guard, idx_set_false, "Guard must come before set-false")
        self.assertLess(idx_set_false, idx_set_true, "Set-false must come before set-true")

    def test_only_one_lastDpadValid_false_assignment(self):
        """There should be exactly one place where lastDpadValid is set to false."""
        count = self.fn_body.count("lastDpadValid = false;")
        self.assertEqual(count, 1, "lastDpadValid should be set to false exactly once")

    def test_only_one_lastDpadValid_true_assignment_in_function(self):
        """There should be exactly one place where lastDpadValid is set to true
        inside updateDpadInput (the initialization outside doesn't count)."""
        count = self.fn_body.count("lastDpadValid = true;")
        self.assertEqual(count, 1, "lastDpadValid should be set to true exactly once inside updateDpadInput")

    def test_no_lastDpadValid_true_inside_guard_block(self):
        """The if (lastDpadValid) block must not set lastDpadValid back to true,
        which would cause warn to fire every time regardless."""
        idx_guard_open = self.fn_body.index("if (lastDpadValid)")
        # Find the closing brace of the guard block (next closing brace)
        idx_guard_close = self.fn_body.index("}", idx_guard_open)
        guard_block_contents = self.fn_body[idx_guard_open:idx_guard_close]
        self.assertNotIn(
            "lastDpadValid = true",
            guard_block_contents,
            "The if (lastDpadValid) guard block must not reset lastDpadValid to true",
        )

    def test_updateDpadInput_function_exists(self):
        """The updateDpadInput function must still exist in the file."""
        self.assertIn("function updateDpadInput(gamepad, cfg)", self.fn_body)

    def test_validIndices_check_still_present(self):
        """The validation of button indices must still be present."""
        self.assertIn("const validIndices", self.fn_body)
        self.assertIn("if (!validIndices)", self.fn_body)


if __name__ == "__main__":
    unittest.main()
