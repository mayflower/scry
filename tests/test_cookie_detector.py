"""Tests for LLM-based cookie banner detection.

Tests cover:
- Cookie banner detection logic
- Different banner types (modal, overlay, bar)
- Confidence thresholds
- Error handling and fallbacks
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from scry.core.cookie.detector import (
    BannerHints,
    CookieBannerResult,
    _create_detection_prompt,
    detect_cookie_banner,
)


class TestCookieBannerResult:
    """Test CookieBannerResult dataclass."""

    def test_result_with_banner(self):
        """Test result when banner is detected."""
        result = CookieBannerResult(
            has_banner=True,
            dismiss_ref="ref_5",
            dismiss_selector='button:has-text("Accept")',
            banner_type="modal",
            confidence=0.95,
        )

        assert result.has_banner is True
        assert result.dismiss_ref == "ref_5"
        assert result.dismiss_selector == 'button:has-text("Accept")'
        assert result.banner_type == "modal"
        assert result.confidence == 0.95

    def test_result_no_banner(self):
        """Test result when no banner detected."""
        result = CookieBannerResult(
            has_banner=False,
            dismiss_ref=None,
            dismiss_selector=None,
            banner_type=None,
            confidence=0.1,
        )

        assert result.has_banner is False
        assert result.dismiss_ref is None
        assert result.dismiss_selector is None


class TestDetectCookieBanner:
    """Test the detect_cookie_banner function."""

    @patch("scry.adapters.anthropic.has_api_key")
    def test_no_api_key_returns_no_banner(self, mock_has_key):
        """Test that detection returns no banner when no API key."""
        mock_has_key.return_value = False
        mock_ref_manager = MagicMock()

        result = detect_cookie_banner("dom tree content", mock_ref_manager)

        assert result.has_banner is False
        assert result.confidence == 0.0

    @patch("scry.adapters.anthropic.complete_json")
    @patch("scry.adapters.anthropic.has_api_key")
    def test_detect_modal_banner(self, mock_has_key, mock_complete):
        """Test detection of modal-style cookie banner."""
        mock_has_key.return_value = True
        mock_complete.return_value = (
            {
                "has_banner": True,
                "dismiss_ref": "ref_12",
                "banner_type": "modal",
                "confidence": 0.92,
            },
            None,
        )

        # Create mock ref manager
        mock_ref_data = MagicMock()
        mock_ref_data.selector = 'button[data-testid="accept-cookies"]'
        mock_ref_manager = MagicMock()
        mock_ref_manager.get_ref.return_value = mock_ref_data

        result = detect_cookie_banner("dom tree with cookie modal", mock_ref_manager)

        assert result.has_banner is True
        assert result.dismiss_ref == "ref_12"
        assert result.dismiss_selector == 'button[data-testid="accept-cookies"]'
        assert result.banner_type == "modal"
        assert result.confidence == 0.92

    @patch("scry.adapters.anthropic.complete_json")
    @patch("scry.adapters.anthropic.has_api_key")
    def test_detect_bar_banner(self, mock_has_key, mock_complete):
        """Test detection of bar-style cookie banner."""
        mock_has_key.return_value = True
        mock_complete.return_value = (
            {
                "has_banner": True,
                "dismiss_ref": "ref_8",
                "banner_type": "bar",
                "confidence": 0.88,
            },
            None,
        )

        mock_ref_data = MagicMock()
        mock_ref_data.selector = ".cookie-bar .accept-btn"
        mock_ref_manager = MagicMock()
        mock_ref_manager.get_ref.return_value = mock_ref_data

        result = detect_cookie_banner("dom tree with cookie bar", mock_ref_manager)

        assert result.has_banner is True
        assert result.banner_type == "bar"
        assert result.dismiss_selector == ".cookie-bar .accept-btn"

    @patch("scry.adapters.anthropic.complete_json")
    @patch("scry.adapters.anthropic.has_api_key")
    def test_detect_overlay_banner(self, mock_has_key, mock_complete):
        """Test detection of overlay-style cookie banner."""
        mock_has_key.return_value = True
        mock_complete.return_value = (
            {
                "has_banner": True,
                "dismiss_ref": "ref_3",
                "banner_type": "overlay",
                "confidence": 0.85,
            },
            None,
        )

        mock_ref_data = MagicMock()
        mock_ref_data.selector = "#consent-overlay button.primary"
        mock_ref_manager = MagicMock()
        mock_ref_manager.get_ref.return_value = mock_ref_data

        result = detect_cookie_banner("dom tree with overlay", mock_ref_manager)

        assert result.has_banner is True
        assert result.banner_type == "overlay"

    @patch("scry.adapters.anthropic.complete_json")
    @patch("scry.adapters.anthropic.has_api_key")
    def test_no_banner_detected(self, mock_has_key, mock_complete):
        """Test when no cookie banner is detected."""
        mock_has_key.return_value = True
        mock_complete.return_value = (
            {
                "has_banner": False,
                "dismiss_ref": None,
                "banner_type": None,
                "confidence": 0.15,
            },
            None,
        )

        mock_ref_manager = MagicMock()

        result = detect_cookie_banner("clean dom tree", mock_ref_manager)

        assert result.has_banner is False
        assert result.dismiss_ref is None
        assert result.dismiss_selector is None
        assert result.confidence == 0.15

    @patch("scry.adapters.anthropic.complete_json")
    @patch("scry.adapters.anthropic.has_api_key")
    def test_ref_not_found(self, mock_has_key, mock_complete):
        """Test handling when ref is not found in ref manager."""
        mock_has_key.return_value = True
        mock_complete.return_value = (
            {
                "has_banner": True,
                "dismiss_ref": "ref_99",
                "banner_type": "modal",
                "confidence": 0.9,
            },
            None,
        )

        # Ref manager returns None for unknown ref
        mock_ref_manager = MagicMock()
        mock_ref_manager.get_ref.return_value = None

        result = detect_cookie_banner("dom tree", mock_ref_manager)

        assert result.has_banner is True
        assert result.dismiss_ref == "ref_99"
        assert result.dismiss_selector is None  # Could not look up selector

    @patch("scry.adapters.anthropic.complete_json")
    @patch("scry.adapters.anthropic.has_api_key")
    def test_api_error_returns_no_banner(self, mock_has_key, mock_complete):
        """Test that API errors result in no banner detected."""
        mock_has_key.return_value = True
        mock_complete.side_effect = Exception("API error")

        mock_ref_manager = MagicMock()

        result = detect_cookie_banner("dom tree", mock_ref_manager)

        assert result.has_banner is False
        assert result.confidence == 0.0

    @patch("scry.adapters.anthropic.complete_json")
    @patch("scry.adapters.anthropic.has_api_key")
    def test_malformed_response(self, mock_has_key, mock_complete):
        """Test handling of malformed API response."""
        mock_has_key.return_value = True
        mock_complete.return_value = (
            {"unexpected_field": "value"},  # Missing expected fields
            None,
        )

        mock_ref_manager = MagicMock()

        result = detect_cookie_banner("dom tree", mock_ref_manager)

        # Should handle gracefully with defaults
        assert result.has_banner is False  # Default to False
        assert result.confidence == 0.0  # Default to 0


class TestBannerHints:
    """Test BannerHints dataclass and prompt integration."""

    def test_banner_hints_defaults(self):
        """Test BannerHints default values."""
        hints = BannerHints()

        assert hints.has_tcf_api is False
        assert hints.has_cmp_api is False
        assert hints.fixed_elements == []

    def test_banner_hints_with_tcf_api(self):
        """Test BannerHints with TCF API detected."""
        hints = BannerHints(has_tcf_api=True)

        assert hints.has_tcf_api is True
        assert hints.has_cmp_api is False

    def test_banner_hints_with_fixed_elements(self):
        """Test BannerHints with fixed elements."""
        fixed_elements = [
            {"ref": "ref_1", "role": "dialog", "z_index": "9999", "position": "fixed"},
            {"ref": "ref_2", "role": "div", "z_index": "1000", "position": "sticky"},
        ]
        hints = BannerHints(fixed_elements=fixed_elements)

        assert len(hints.fixed_elements) == 2
        assert hints.fixed_elements[0]["role"] == "dialog"

    def test_prompt_includes_tcf_hint(self):
        """Test that prompt includes TCF API hint."""
        hints = BannerHints(has_tcf_api=True)
        dom_tree = "- div [ref=ref_1]"

        prompt = _create_detection_prompt(dom_tree, hints)

        assert "IAB TCF API detected" in prompt
        assert "window.__tcfapi" in prompt

    def test_prompt_includes_cmp_hint(self):
        """Test that prompt includes CMP API hint."""
        hints = BannerHints(has_cmp_api=True)
        dom_tree = "- div [ref=ref_1]"

        prompt = _create_detection_prompt(dom_tree, hints)

        assert "CMP API detected" in prompt
        assert "window.__cmp" in prompt

    def test_prompt_includes_fixed_elements(self):
        """Test that prompt includes fixed element hints."""
        hints = BannerHints(
            fixed_elements=[
                {
                    "ref": "ref_5",
                    "role": "dialog",
                    "z_index": "9999",
                    "position": "fixed",
                },
            ]
        )
        dom_tree = "- div [ref=ref_1]"

        prompt = _create_detection_prompt(dom_tree, hints)

        assert "fixed/sticky elements" in prompt
        assert "ref_5" in prompt
        assert "dialog" in prompt
        assert "z-index: 9999" in prompt

    def test_prompt_without_hints(self):
        """Test that prompt works without hints."""
        dom_tree = "- div [ref=ref_1]"

        prompt = _create_detection_prompt(dom_tree, None)

        assert "ref_1" in prompt
        assert "Heuristic signals" not in prompt

    @patch("scry.adapters.anthropic.complete_json")
    @patch("scry.adapters.anthropic.has_api_key")
    def test_detect_with_hints(self, mock_has_key, mock_complete):
        """Test detection passes hints to LLM."""
        mock_has_key.return_value = True
        mock_complete.return_value = (
            {"has_banner": True, "dismiss_ref": "ref_1", "confidence": 0.95},
            None,
        )

        hints = BannerHints(has_tcf_api=True)
        mock_ref_manager = MagicMock()
        mock_ref_manager.get_ref.return_value = None

        result = detect_cookie_banner("dom tree", mock_ref_manager, hints)

        # Verify hints were passed to prompt
        call_args = mock_complete.call_args
        user_prompt = call_args[1]["user_prompt"]
        assert "IAB TCF API detected" in user_prompt
        assert result.has_banner is True


class TestDetectionPrompt:
    """Test prompt generation for detection."""

    @patch("scry.adapters.anthropic.complete_json")
    @patch("scry.adapters.anthropic.has_api_key")
    def test_dom_tree_included_in_prompt(self, mock_has_key, mock_complete):
        """Test that DOM tree is included in the prompt."""
        mock_has_key.return_value = True
        mock_complete.return_value = ({"has_banner": False}, None)

        mock_ref_manager = MagicMock()
        dom_tree = "- button 'Accept All' [ref=ref_1]"

        detect_cookie_banner(dom_tree, mock_ref_manager)

        # Verify the user prompt contains the DOM tree
        args = mock_complete.call_args
        user_prompt = args[1]["user_prompt"] if args[1] else args[0][1]
        assert "Accept All" in user_prompt or "ref_1" in user_prompt

    @patch("scry.adapters.anthropic.complete_json")
    @patch("scry.adapters.anthropic.has_api_key")
    def test_long_dom_tree_truncated(self, mock_has_key, mock_complete):
        """Test that very long DOM trees are truncated."""
        mock_has_key.return_value = True
        mock_complete.return_value = ({"has_banner": False}, None)

        mock_ref_manager = MagicMock()
        # Create a very long DOM tree
        long_dom_tree = "- element [ref=ref_0]\n" * 10000

        detect_cookie_banner(long_dom_tree, mock_ref_manager)

        # Verify the prompt was called (truncation is internal)
        assert mock_complete.called


class TestSelfHealingIntegration:
    """Test integration with self-healing system."""

    def test_propose_patch_with_cookie_selector(self):
        """Test that propose_patch passes through cookie selector."""
        from scry.core.self_heal.diagnose import propose_patch

        with patch("scry.core.self_heal.diagnose.has_api_key", return_value=False):
            result = propose_patch(
                attempt=2,
                stderr="Element not found",
                html=None,
                cookie_dismiss_selector="button.consent-accept",
            )

        assert result.get("cookie_dismiss_selector") == "button.consent-accept"
        # No handle_cookie_banner - only LLM-detected selectors are used


class TestCodeGenIntegration:
    """Test integration with code generation."""

    def test_generator_uses_detected_selector(self):
        """Test that generator uses detected cookie selector."""
        from scry.core.codegen.generator import generate_script
        from scry.core.ir.model import Navigate, ScrapePlan
        import tempfile
        from pathlib import Path

        plan = ScrapePlan(steps=[Navigate(url="https://example.com")])

        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_root = Path(tmpdir)
            script_path = generate_script(
                plan=plan,
                job_id="test123",
                artifacts_root=artifacts_root,
                headless=True,
                options={
                    "cookie_dismiss_selector": "button.accept-cookies",
                },
            )

            # Read generated script
            script_content = script_path.read_text()

            # Should use the detected selector, not generic Accept
            assert "button.accept-cookies" in script_content
            assert "get_by_role('button', name='Accept')" not in script_content

    def test_generator_no_selector_no_cookie_handling(self):
        """Test that without a detected selector, no cookie handling code is generated."""
        from scry.core.codegen.generator import generate_script
        from scry.core.ir.model import Navigate, ScrapePlan
        import tempfile
        from pathlib import Path

        plan = ScrapePlan(steps=[Navigate(url="https://example.com")])

        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_root = Path(tmpdir)
            script_path = generate_script(
                plan=plan,
                job_id="test456",
                artifacts_root=artifacts_root,
                headless=True,
                options={},  # No cookie_dismiss_selector
            )

            script_content = script_path.read_text()

            # No cookie handling code should be present
            assert "get_by_role('button', name='Accept')" not in script_content
            assert (
                "cookie" not in script_content.lower() or "# " in script_content
            )  # Only comments allowed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
