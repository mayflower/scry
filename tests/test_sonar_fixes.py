"""Tests to verify SonarQube issue fixes remain stable.

These tests ensure that the fixes for various code quality issues
detected by SonarQube don't regress.
"""

from __future__ import annotations

import inspect

from scry.core.codegen.generator import _wrap_in_try_except
from scry.core.optimizer.optimize import _improve_selector
from scry.core.optimizer.selectors import improve_selector_resilience


class TestImproveSelectorFix:
    """Tests for _improve_selector function fix.

    SonarQube S3516: Function should not always return the same value.
    """

    def test_normalizes_whitespace(self):
        """Selector whitespace should be normalized."""
        selector = "div.class1    .class2"
        result = _improve_selector(selector)
        assert "    " not in result
        assert result == "div.class1 .class2"

    def test_stable_attribute_preserved(self):
        """Stable attributes like data-testid should be preserved."""
        selector = '[data-testid="login-button"]'
        result = _improve_selector(selector)
        assert result == selector

    def test_id_selector_preserved(self):
        """ID selectors should be preserved."""
        selector = "#main-content"
        result = _improve_selector(selector)
        assert result == selector

    def test_complex_selector_simplified(self):
        """Selectors with many classes should be simplified."""
        selector = "div.class1.class2.class3.class4.class5"
        result = _improve_selector(selector)
        # Should keep tag and first 3 classes (4 parts total)
        assert result.count(".") <= 3

    def test_nth_child_removed(self):
        """Fragile nth-child selectors should be removed."""
        selector = "ul li:nth-child(3)"
        result = _improve_selector(selector)
        assert ":nth-child" not in result

    def test_returns_different_values(self):
        """Function should return different values for different inputs."""
        selectors = [
            "div.a.b.c.d.e",  # Simplified
            "#simple",  # Unchanged
            '[data-testid="x"]',  # Unchanged
            "li:nth-child(5)",  # nth-child removed
        ]
        results = [_improve_selector(s) for s in selectors]

        # At least some results should be different from their inputs
        differences = sum(1 for s, r in zip(selectors, results, strict=True) if s != r)
        assert differences >= 2, "Function should modify at least some selectors"


class TestSimplifySelectorFix:
    """Tests for improve_selector_resilience with str.replace optimization.

    SonarQube S5361: Use str.replace instead of re.sub for simple patterns.
    """

    def test_removes_first_child(self):
        """Should remove :first-child pseudo-selector."""
        selector = "ul li:first-child"
        result = improve_selector_resilience(selector)
        assert ":first-child" not in result

    def test_removes_last_child(self):
        """Should remove :last-child pseudo-selector."""
        selector = "ul li:last-child"
        result = improve_selector_resilience(selector)
        assert ":last-child" not in result

    def test_removes_nth_child_with_number(self):
        """Should remove :nth-child(n) pseudo-selector."""
        selector = "ul li:nth-child(3)"
        result = improve_selector_resilience(selector)
        assert ":nth-child" not in result

    def test_preserves_stable_selectors(self):
        """Stable attribute selectors should be preserved."""
        selector = '[data-testid="menu-item"]'
        result = improve_selector_resilience(selector)
        assert result == selector


class TestCodeGeneratorFix:
    """Tests for code generator duplicate literal fix.

    SonarQube S1192: Define constants for duplicated string literals.
    """

    def test_wrap_in_try_except_basic(self):
        """Helper function should wrap code in try/except."""
        lines = _wrap_in_try_except(
            ["page.click('.btn')"],
            "Failed to click",
        )
        code = "\n".join(lines)
        assert "try:" in code
        assert "except Exception as e:" in code
        assert "Failed to click" in code

    def test_wrap_in_try_except_multiple_lines(self):
        """Should handle multiple action lines."""
        lines = _wrap_in_try_except(
            [
                "page.click('.btn')",
                "page.wait_for_timeout(1000)",
                "page.screenshot()",
            ],
            "Action failed",
        )
        code = "\n".join(lines)
        assert code.count("page.") == 3

    def test_wrap_in_try_except_custom_indent(self):
        """Should support custom indentation."""
        lines = _wrap_in_try_except(
            ["action()"],
            "Error",
            indent="    ",
        )
        # First line should start with the custom indent
        assert lines[0].startswith("    ")


class TestBrowserExecutorConstants:
    """Tests for browser executor error message constants.

    SonarQube S1192: Define constants for duplicated string literals.
    """

    def test_error_constants_exist(self):
        """Error message constants should be defined."""
        from scry.adapters.browser_executor import (
            _ERR_COORD_FORMAT,
            _ERR_REF_OR_COORD_REQUIRED,
            _ERR_START_COORD_FORMAT,
        )

        assert _ERR_REF_OR_COORD_REQUIRED == "Either ref or coordinate is required"
        assert _ERR_COORD_FORMAT == "coordinate must be [x, y]"
        assert _ERR_START_COORD_FORMAT == "start_coordinate must be [x, y]"


class TestPlaywrightExplorerUnusedParams:
    """Tests for playwright explorer unused parameter handling.

    SonarQube S1172: Unused parameters should be marked or removed.
    """

    def test_explore_accepts_progress_callback(self):
        """explore_with_playwright() should accept progress_callback even if unused."""
        from scry.adapters.playwright_explorer import explore_with_playwright

        # Should not raise - parameter exists in signature
        sig = inspect.signature(explore_with_playwright)
        assert "progress_callback" in sig.parameters

    def test_explore_with_browser_tools_accepts_login_params(self):
        """_explore_with_browser_tools() should accept login_params."""
        from scry.adapters.playwright_explorer import _explore_with_browser_tools

        sig = inspect.signature(_explore_with_browser_tools)
        assert "login_params" in sig.parameters


class TestCodeGeneratorConstants:
    """Tests for code generator extraction constants.

    SonarQube S1192: Define constants for duplicated string literals.
    """

    def test_extraction_indent_constant(self):
        """Extraction indent constant should be 16 spaces (4 levels)."""
        from scry.core.codegen.generator import _EXTRACT_INDENT, _EXTRACT_TRY

        assert _EXTRACT_INDENT == "                "  # 16 spaces
        assert len(_EXTRACT_INDENT) == 16
        assert f"{_EXTRACT_INDENT}try:" == _EXTRACT_TRY

    def test_basic_indent_constants(self):
        """Basic indent constants should be defined correctly."""
        from scry.core.codegen.generator import (
            _EXCEPT_BLOCK,
            _INDENT,
            _NESTED_INDENT,
            _TRY_BLOCK,
        )

        assert _INDENT == "        "  # 8 spaces
        assert len(_INDENT) == 8
        assert f"{_INDENT}    " == _NESTED_INDENT  # 12 spaces
        assert f"{_INDENT}try:" == _TRY_BLOCK
        assert f"{_INDENT}except Exception as e:" == _EXCEPT_BLOCK


class TestImproveSelectorEdgeCases:
    """Additional edge case tests for _improve_selector.

    Ensure comprehensive coverage of all code paths.
    """

    def test_data_test_attribute_preserved(self):
        """data-test attribute should also be preserved."""
        selector = '[data-test="button"]'
        result = _improve_selector(selector)
        assert result == selector

    def test_aria_label_preserved(self):
        """aria-label attribute should be preserved."""
        selector = '[aria-label="Close"]'
        result = _improve_selector(selector)
        assert result == selector

    def test_id_with_space_not_treated_as_stable(self):
        """ID selector with descendant should not be treated as simple ID."""
        selector = "#parent .child"
        result = _improve_selector(selector)
        # This is not a simple #id selector, so may be modified
        assert result is not None

    def test_nth_child_complex_pattern(self):
        """Should handle various nth-child patterns."""
        selectors = [
            "li:nth-child(2n+1)",
            "div:nth-child(odd)",
            "span:nth-child(even)",
        ]
        for selector in selectors:
            result = _improve_selector(selector)
            assert ":nth-child" not in result

    def test_empty_selector(self):
        """Empty selector should return empty string."""
        result = _improve_selector("")
        assert result == ""

    def test_whitespace_only_selector(self):
        """Whitespace-only selector should be normalized to empty."""
        result = _improve_selector("   ")
        assert result == ""


class TestSimplifySelectorEdgeCases:
    """Additional edge case tests for improve_selector_resilience.

    SonarQube S5361: Ensure str.replace optimization works correctly.
    """

    def test_deeply_nested_selector_simplified(self):
        """Deeply nested selectors should be simplified to last 2 levels."""
        selector = "html body div main section article p span"
        result = improve_selector_resilience(selector)
        # Should keep only last 2 levels
        assert result.count(" ") <= 1

    def test_name_attribute_preserved(self):
        """name= attribute should be preserved."""
        selector = '[name="email"]'
        result = improve_selector_resilience(selector)
        assert result == selector

    def test_combined_pseudo_selectors_removed(self):
        """Multiple pseudo-selectors should all be removed."""
        selector = "ul li:first-child:nth-child(1)"
        result = improve_selector_resilience(selector)
        assert ":first-child" not in result
        assert ":nth-child" not in result


class TestWrapInTryExceptEdgeCases:
    """Additional edge case tests for _wrap_in_try_except helper."""

    def test_empty_action_lines(self):
        """Should handle empty action lines list."""
        lines = _wrap_in_try_except([], "No actions")
        code = "\n".join(lines)
        assert "try:" in code
        assert "except Exception as e:" in code
        assert "No actions" in code

    def test_error_message_with_special_chars(self):
        """Should handle error messages with special characters."""
        lines = _wrap_in_try_except(
            ["action()"],
            "Failed: selector='div.class'",
        )
        code = "\n".join(lines)
        assert "selector='div.class'" in code

    def test_deeply_nested_indent(self):
        """Should support deeply nested indentation."""
        indent = "                "  # 16 spaces
        lines = _wrap_in_try_except(
            ["nested_action()"],
            "Deep error",
            indent=indent,
        )
        assert lines[0].startswith(indent)
        assert lines[0] == f"{indent}try:"
