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


class TestExtractorHelperFunctions:
    """Tests for extractor helper functions added to reduce cognitive complexity."""

    def test_extract_list_items_from_container(self):
        """Should extract text from list items in a container."""
        from bs4 import BeautifulSoup

        from scry.core.extractor.extract import _extract_list_items_from_container

        html = """
        <ul class="items">
            <li>Item 1</li>
            <li>Item 2</li>
            <li>Item 3</li>
        </ul>
        """
        soup = BeautifulSoup(html, "html.parser")
        container = soup.find("ul")
        result = _extract_list_items_from_container(container)
        assert result == ["Item 1", "Item 2", "Item 3"]

    def test_extract_list_items_empty_container(self):
        """Should return empty list for container without items."""
        from bs4 import BeautifulSoup

        from scry.core.extractor.extract import _extract_list_items_from_container

        html = "<ul class='empty'></ul>"
        soup = BeautifulSoup(html, "html.parser")
        container = soup.find("ul")
        result = _extract_list_items_from_container(container)
        assert result == []

    def test_extract_text_from_class_matches(self):
        """Should extract text from elements matching class pattern."""
        from bs4 import BeautifulSoup

        from scry.core.extractor.extract import _extract_text_from_class_matches

        html = """
        <div>
            <span class="tag-item">Tag 1</span>
            <span class="tag-item">Tag 2</span>
            <span class="other">Other</span>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = _extract_text_from_class_matches(soup, "tag")
        assert "Tag 1" in result
        assert "Tag 2" in result

    def test_extract_text_from_class_matches_with_limit(self):
        """Should respect limit parameter."""
        from bs4 import BeautifulSoup

        from scry.core.extractor.extract import _extract_text_from_class_matches

        html = """
        <div>
            <span class="item">1</span>
            <span class="item">2</span>
            <span class="item">3</span>
            <span class="item">4</span>
            <span class="item">5</span>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        result = _extract_text_from_class_matches(soup, "item", limit=3)
        assert len(result) == 3

    def test_is_feature_array(self):
        """Should correctly identify feature arrays."""
        from scry.core.extractor.extract import _is_feature_array

        assert _is_feature_array("features", "string") is True
        assert _is_feature_array("feature_list", "string") is True
        assert _is_feature_array("features", "object") is False
        assert _is_feature_array("tags", "string") is False

    def test_is_tag_array(self):
        """Should correctly identify tag arrays."""
        from scry.core.extractor.extract import _is_tag_array

        assert _is_tag_array("tags", "string") is True
        assert _is_tag_array("tag_list", "string") is True
        assert _is_tag_array("tags", "object") is False
        assert _is_tag_array("features", "string") is False

    def test_is_link_array(self):
        """Should correctly identify link arrays."""
        from scry.core.extractor.extract import _is_link_array

        assert _is_link_array("links", "string") is True
        assert _is_link_array("urls", "object") is True
        assert _is_link_array("link_list", "string") is True
        assert _is_link_array("images", "string") is False

    def test_is_image_array(self):
        """Should correctly identify image arrays."""
        from scry.core.extractor.extract import _is_image_array

        assert _is_image_array("images", "string") is True
        assert _is_image_array("img_list", "string") is True
        assert _is_image_array("images", "object") is False
        assert _is_image_array("links", "string") is False

    def test_result_or_none(self):
        """Should return result if non-empty, None otherwise."""
        from scry.core.extractor.extract import _result_or_none

        assert _result_or_none([1, 2, 3]) == [1, 2, 3]
        assert _result_or_none([]) is None
        assert _result_or_none(["item"]) == ["item"]


class TestRunnerHelperFunctions:
    """Tests for runner helper functions added to reduce cognitive complexity."""

    def test_handle_validation_failure_with_validation_error(self):
        """Should extract validation error from stderr."""
        from unittest.mock import MagicMock

        from scry.core.executor.runner import _handle_validation_failure

        script_result = MagicMock()
        script_result.stderr = "Error: CRITICAL validation failed: element not found"
        script_result.stdout = ""

        result = _handle_validation_failure(script_result)
        assert result == "Error: CRITICAL validation failed: element not found"

    def test_handle_validation_failure_in_stdout(self):
        """Should extract validation error from stdout if not in stderr."""
        from unittest.mock import MagicMock

        from scry.core.executor.runner import _handle_validation_failure

        script_result = MagicMock()
        script_result.stderr = ""
        script_result.stdout = "CRITICAL validation failed: selector mismatch"

        result = _handle_validation_failure(script_result)
        assert result == "CRITICAL validation failed: selector mismatch"

    def test_handle_validation_failure_no_error(self):
        """Should return None if no validation error found."""
        from unittest.mock import MagicMock

        from scry.core.executor.runner import _handle_validation_failure

        script_result = MagicMock()
        script_result.stderr = "Some other error"
        script_result.stdout = ""

        result = _handle_validation_failure(script_result)
        assert result is None

    def test_should_retry_validation_within_attempts(self):
        """Should return retry=True when within max attempts."""
        from unittest.mock import MagicMock, patch

        from scry.core.executor.runner import _should_retry_validation

        script_result = MagicMock()
        script_result.stderr = "CRITICAL validation failed: test"
        script_result.stdout = ""
        execution_log = []

        with patch("scry.core.executor.runner.settings") as mock_settings:
            mock_settings.max_repair_attempts = 3
            should_retry, error_msg = _should_retry_validation(script_result, 0, execution_log)

        assert should_retry is True
        assert error_msg is not None
        assert "validation_failed" in execution_log

    def test_should_retry_validation_exhausted(self):
        """Should return retry=False when attempts exhausted."""
        from unittest.mock import MagicMock, patch

        from scry.core.executor.runner import _should_retry_validation

        script_result = MagicMock()
        script_result.stderr = "CRITICAL validation failed: test"
        script_result.stdout = ""
        execution_log = []

        with patch("scry.core.executor.runner.settings") as mock_settings:
            mock_settings.max_repair_attempts = 2
            should_retry, error_msg = _should_retry_validation(script_result, 1, execution_log)

        assert should_retry is False
        assert error_msg is None
        assert "validation_repair_exhausted" in execution_log

    def test_handle_script_error_within_attempts(self):
        """Should return retry=True when within max attempts."""
        from subprocess import CalledProcessError
        from unittest.mock import patch

        from scry.core.executor.runner import _handle_script_error

        error = CalledProcessError(1, "python script.py", "", "Test error")
        execution_log = []

        with patch("scry.core.executor.runner.settings") as mock_settings:
            mock_settings.max_repair_attempts = 3
            should_retry, error_msg = _handle_script_error(error, 0, execution_log)

        assert should_retry is True
        assert error_msg == "Test error"

    def test_handle_script_error_exhausted(self):
        """Should return retry=False when attempts exhausted."""
        from subprocess import CalledProcessError
        from unittest.mock import patch

        from scry.core.executor.runner import _handle_script_error

        error = CalledProcessError(1, "python script.py", "", "Test error")
        execution_log = []

        with patch("scry.core.executor.runner.settings") as mock_settings:
            mock_settings.max_repair_attempts = 2
            should_retry, error_msg = _handle_script_error(error, 1, execution_log)

        assert should_retry is False
        assert error_msg is None
        assert "script_failed" in execution_log


class TestNotifyProgress:
    """Tests for _notify_progress helper in runner.py."""

    def test_notify_progress_calls_callback(self):
        """Should call the callback with the payload."""
        from unittest.mock import MagicMock

        from scry.core.executor.runner import _notify_progress

        callback = MagicMock()
        payload = {"step": 1, "status": "ok"}
        _notify_progress(callback, payload, "test")
        callback.assert_called_once_with(payload)

    def test_notify_progress_none_callback(self):
        """Should do nothing when callback is None."""
        from scry.core.executor.runner import _notify_progress

        _notify_progress(None, {"step": 1}, "test")  # Should not raise

    def test_notify_progress_swallows_exception(self):
        """Should catch and log exceptions from the callback."""
        from unittest.mock import MagicMock

        from scry.core.executor.runner import _notify_progress

        callback = MagicMock(side_effect=RuntimeError("callback failed"))
        _notify_progress(callback, {"step": 1}, "test")  # Should not raise


class TestNotifyExplorationProgress:
    """Tests for _notify_exploration_progress helper in playwright_explorer.py."""

    def test_notify_exploration_progress_calls_callback(self):
        """Should call the callback with the payload."""
        from unittest.mock import MagicMock

        from scry.adapters.playwright_explorer import _notify_exploration_progress

        callback = MagicMock()
        payload = {"step": 0, "action": "navigated"}
        _notify_exploration_progress(callback, payload, "step 0")
        callback.assert_called_once_with(payload)

    def test_notify_exploration_progress_none_callback(self):
        """Should do nothing when callback is None."""
        from scry.adapters.playwright_explorer import _notify_exploration_progress

        _notify_exploration_progress(None, {"step": 0}, "step 0")

    def test_notify_exploration_progress_swallows_exception(self):
        """Should catch and log exceptions from the callback."""
        from unittest.mock import MagicMock

        from scry.adapters.playwright_explorer import _notify_exploration_progress

        callback = MagicMock(side_effect=ValueError("broken"))
        _notify_exploration_progress(callback, {"step": 1}, "step 1")
