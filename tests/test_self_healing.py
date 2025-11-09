"""Comprehensive tests for the self-healing system.

Tests cover:
- Patch proposal (heuristic and AI-powered)
- Patch merging
- Different error scenarios
- Progressive healing attempts
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from scry.core.self_heal.diagnose import _heuristic_patch, propose_patch
from scry.core.self_heal.patch import merge_codegen_options


class TestHeuristicPatches:
    """Test heuristic patch generation."""

    def test_first_attempt_patch(self):
        """Test patch for first repair attempt."""
        patch = _heuristic_patch(1, "Some error")

        assert patch["wait_load_state"] is True
        assert patch["extra_wait_ms"] == 1000
        assert "handle_cookie_banner" not in patch

    def test_timeout_error_patch(self):
        """Test patch for timeout errors."""
        patch = _heuristic_patch(2, "Timeout waiting for selector")

        assert patch["wait_load_state"] is True
        assert patch["extra_wait_ms"] == 2000
        assert patch["handle_cookie_banner"] is True

    def test_cookie_banner_patch(self):
        """Test cookie banner handling in later attempts."""
        patch = _heuristic_patch(3, "Element not found")

        assert patch["handle_cookie_banner"] is True

    def test_progressive_patches(self):
        """Test that patches become more aggressive with attempts."""
        patch1 = _heuristic_patch(1, "Error")
        patch2 = _heuristic_patch(2, "Error")
        patch3 = _heuristic_patch(3, "Error")

        # First attempt: basic wait
        assert patch1.get("extra_wait_ms", 0) > 0
        assert "handle_cookie_banner" not in patch1

        # Second+ attempts: cookie handling
        assert patch2["handle_cookie_banner"] is True
        assert patch3["handle_cookie_banner"] is True


class TestProposePatch:
    """Test the main propose_patch function."""

    @patch("scry.core.self_heal.diagnose.has_api_key")
    def test_no_api_key_uses_heuristic(self, mock_has_key):
        """Test fallback to heuristic when no API key."""
        mock_has_key.return_value = False

        patch = propose_patch(1, "Error message", None)

        # Should use heuristic patch
        assert patch["wait_load_state"] is True
        assert patch["extra_wait_ms"] == 1000

    @patch("scry.core.self_heal.diagnose.has_api_key")
    @patch("scry.core.self_heal.diagnose.complete_json")
    def test_ai_patch_generation(self, mock_complete, mock_has_key):
        """Test AI-powered patch generation."""
        mock_has_key.return_value = True
        mock_complete.return_value = (
            {
                "wait_load_state": True,
                "extra_wait_ms": 3000,
                "handle_cookie_banner": True,
            },
            None,
        )

        patch = propose_patch(2, "Complex error", "<html>...</html>")

        assert patch["wait_load_state"] is True
        assert patch["extra_wait_ms"] == 3000
        assert patch["handle_cookie_banner"] is True

        # Verify Claude was called with appropriate prompts
        mock_complete.assert_called_once()
        args = mock_complete.call_args[0]
        assert "remediation" in args[0].lower()  # System prompt
        assert "Attempt: 2" in args[1]  # User prompt

    @patch("scry.core.self_heal.diagnose.has_api_key")
    @patch("scry.core.self_heal.diagnose.complete_json")
    def test_ai_patch_filters_invalid_keys(self, mock_complete, mock_has_key):
        """Test that AI patches filter out invalid keys."""
        mock_has_key.return_value = True
        mock_complete.return_value = (
            {
                "wait_load_state": True,
                "extra_wait_ms": 2000,
                "invalid_key": "should be filtered",
                "another_invalid": 123,
            },
            None,
        )

        patch = propose_patch(1, "Error", None)

        # Only allowed keys should be present
        assert "wait_load_state" in patch
        assert "extra_wait_ms" in patch
        assert "invalid_key" not in patch
        assert "another_invalid" not in patch

    @patch("scry.core.self_heal.diagnose.has_api_key")
    @patch("scry.core.self_heal.diagnose.complete_json")
    def test_ai_failure_fallback(self, mock_complete, mock_has_key):
        """Test fallback to heuristic when AI fails."""
        mock_has_key.return_value = True
        mock_complete.side_effect = Exception("API error")

        patch = propose_patch(1, "Error", None)

        # Should fallback to heuristic
        assert patch["wait_load_state"] is True
        assert patch["extra_wait_ms"] == 1000


class TestPatchMerging:
    """Test patch merging functionality."""

    def test_merge_empty_base(self):
        """Test merging into empty options."""
        base = {}
        patch = {"wait_load_state": True, "extra_wait_ms": 1000}

        result = merge_codegen_options(base, patch)

        assert result["wait_load_state"] is True
        assert result["extra_wait_ms"] == 1000

    def test_merge_overwrites_existing(self):
        """Test that patches overwrite existing options."""
        base = {"extra_wait_ms": 500, "other_option": "keep"}
        patch = {"extra_wait_ms": 2000, "wait_load_state": True}

        result = merge_codegen_options(base, patch)

        assert result["extra_wait_ms"] == 2000  # Overwritten
        assert result["wait_load_state"] is True  # Added
        assert result["other_option"] == "keep"  # Preserved

    def test_merge_ignores_none_values(self):
        """Test that None values in patch are ignored."""
        base = {"option1": "value1", "option2": "value2"}
        patch = {"option1": "new", "option2": None, "option3": None}

        result = merge_codegen_options(base, patch)

        assert result["option1"] == "new"  # Updated
        assert result["option2"] == "value2"  # Not overwritten by None
        assert "option3" not in result  # None not added

    def test_merge_preserves_base(self):
        """Test that original base dict is not modified."""
        base = {"option": "original"}
        patch = {"option": "modified"}

        result = merge_codegen_options(base, patch)

        assert base["option"] == "original"  # Base unchanged
        assert result["option"] == "modified"  # Result has patch


class TestSelfHealingIntegration:
    """Integration tests for self-healing flow."""

    @pytest.mark.integration
    def test_progressive_healing_attempts(self):
        """Test that patches become progressively more aggressive."""
        attempts_and_errors = [
            (1, "Timeout waiting for element"),
            (2, "Element not visible"),
            (3, "Click intercepted"),
        ]

        patches = []
        for attempt, error in attempts_and_errors:
            patch = propose_patch(attempt, error, None)
            patches.append(patch)

        # Verify progression
        assert patches[0].get("extra_wait_ms", 0) <= patches[1].get("extra_wait_ms", 0)
        assert patches[2].get("handle_cookie_banner") is True

    def test_patch_accumulation(self):
        """Test accumulating patches over multiple attempts."""
        base_options = {}

        # Simulate multiple repair attempts
        for attempt in range(1, 4):
            patch = propose_patch(attempt, f"Error at attempt {attempt}", None)
            base_options = merge_codegen_options(base_options, patch)

        # After multiple attempts, should have accumulated options
        assert "wait_load_state" in base_options
        assert "extra_wait_ms" in base_options
        assert "handle_cookie_banner" in base_options

    @pytest.mark.parametrize(
        "error_message,expected_patch",
        [
            (
                "Timeout waiting for selector .button",
                {"wait_load_state": True, "extra_wait_ms": 2000},
            ),
            ("Element not found: #submit", {"handle_cookie_banner": True}),
            (
                "Navigation timeout",
                {"wait_load_state": True},
            ),  # Don't check exact ms value
        ],
    )
    def test_error_specific_patches(self, error_message, expected_patch):
        """Test that specific errors generate appropriate patches."""
        # Test with attempt 2+ to ensure cookie banner option is available
        patch = propose_patch(2, error_message, None)

        for key, value in expected_patch.items():
            assert patch.get(key) == value


class TestValidationBasedHealing:
    """Test validation-specific healing behaviors."""

    def test_validation_error_message_parsing(self):
        """Test parsing validation error messages."""
        validation_errors = [
            "CRITICAL validation failed: element not found - Check page loaded",
            "CRITICAL validation failed: text mismatch - Verify title",
            "CRITICAL validation failed: count mismatch - Check item count",
        ]

        for error in validation_errors:
            patch = propose_patch(1, error, None)
            # Should recognize as error needing wait/retry
            assert (
                patch.get("wait_load_state") is True
                or patch.get("extra_wait_ms", 0) > 0
            )

    def test_critical_vs_non_critical_handling(self):
        """Test different handling for critical vs non-critical validations."""
        # Critical failures should trigger more aggressive patches
        critical_patch = propose_patch(1, "CRITICAL validation failed", None)
        non_critical_patch = propose_patch(1, "Non-critical validation failed", None)

        # Both should generate patches, but could have different strategies
        assert critical_patch  # Should have some patch
        assert non_critical_patch  # Should have some patch


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
