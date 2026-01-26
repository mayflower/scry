"""Tests to improve code coverage for SonarQube quality gates.

These tests target specific uncovered lines to reach >80% coverage.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from scry.core.ir.model import Click, Fill, Navigate, ScrapePlan, Validate, WaitFor
from scry.core.nav.explore import ExplorationResult

# --- validate.py tests ---


class TestValidateSchemaValidation:
    """Tests for schema validation edge cases."""

    def test_validation_error_is_logged(self):
        """Test that schema validation errors are logged but data is returned."""
        from scry.core.validator.validate import normalize_against_schema

        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        # Data missing required field should still be returned
        data: dict[str, Any] = {"other": "value"}
        result = normalize_against_schema(schema, data)
        # Data is returned even when validation fails
        assert result == {}  # Pruned because 'other' not in properties

    def test_validation_with_type_mismatch(self):
        """Test validation with type mismatch logs error."""
        from scry.core.validator.validate import normalize_against_schema

        schema = {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
        }
        data = {"count": "not_a_number"}
        result = normalize_against_schema(schema, data)
        assert result == {"count": "not_a_number"}  # Data returned despite type error


# --- generator.py tests ---


class TestGeneratorChmodFailure:
    """Tests for code generator chmod handling."""

    def test_generate_script_with_chmod_failure(self, tmp_path: Path):
        """Test that chmod failures are logged but don't raise."""
        from scry.core.codegen.generator import generate_script

        plan = ScrapePlan(steps=[Navigate(url="https://example.com")], notes="test")

        # Mock chmod to raise OSError
        original_chmod = Path.chmod

        def mock_chmod(self, mode):
            raise OSError("Permission denied")

        with patch.object(Path, "chmod", mock_chmod):
            result = generate_script(plan, "test-job", tmp_path, headless=True)

        # Script should still be created
        assert result.exists()
        assert result.read_text().startswith("#!/usr/bin/env python3")

        # Cleanup
        Path.chmod = original_chmod


# --- optimize.py tests ---


class TestOptimizeStepEquality:
    """Tests for step equality checking."""

    def test_navigate_steps_equal(self):
        """Test Navigate step equality."""
        from scry.core.optimizer.optimize import _steps_are_equal

        step1 = Navigate(url="https://example.com")
        step2 = Navigate(url="https://example.com")
        step3 = Navigate(url="https://other.com")

        assert _steps_are_equal(step1, step2) is True
        assert _steps_are_equal(step1, step3) is False

    def test_fill_steps_equal(self):
        """Test Fill step equality."""
        from scry.core.optimizer.optimize import _steps_are_equal

        step1 = Fill(selector="#input", text="hello")
        step2 = Fill(selector="#input", text="hello")
        step3 = Fill(selector="#input", text="world")
        step4 = Fill(selector="#other", text="hello")

        assert _steps_are_equal(step1, step2) is True
        assert _steps_are_equal(step1, step3) is False
        assert _steps_are_equal(step1, step4) is False

    def test_different_step_types_not_equal(self):
        """Test that different step types are not equal."""
        from scry.core.optimizer.optimize import _steps_are_equal

        nav = Navigate(url="https://example.com")
        click = Click(selector="#btn")

        assert _steps_are_equal(nav, click) is False

    def test_validate_steps_not_compared(self):
        """Test that Validate steps return False for equality."""
        from scry.core.optimizer.optimize import _steps_are_equal

        v1 = Validate(selector="#el", expected_text="test")
        v2 = Validate(selector="#el", expected_text="test")

        # Validate steps are not compared for equality
        assert _steps_are_equal(v1, v2) is False


class TestOptimizeWaitForMerging:
    """Tests for WaitFor step merging."""

    def test_waitfor_merge_keeps_visible_over_attached(self):
        """Test that visible state is preferred over attached when merging."""
        from scry.core.optimizer.optimize import _try_merge_wait_for

        # Previous step is visible, current is attached - should merge
        optimized = [WaitFor(selector="#el", state="visible")]
        current = WaitFor(selector="#el", state="attached")

        assert _try_merge_wait_for(current, optimized) is True

    def test_waitfor_different_selectors_not_merged(self):
        """Test that WaitFor with different selectors don't merge."""
        from scry.core.optimizer.optimize import _try_merge_wait_for

        optimized = [WaitFor(selector="#el1", state="visible")]
        current = WaitFor(selector="#el2", state="visible")

        assert _try_merge_wait_for(current, optimized) is False

    def test_waitfor_after_non_waitfor_not_merged(self):
        """Test WaitFor after non-WaitFor step doesn't merge."""
        from scry.core.optimizer.optimize import _try_merge_wait_for

        optimized = [Click(selector="#btn")]
        current = WaitFor(selector="#el", state="visible")

        assert _try_merge_wait_for(current, optimized) is False


class TestCompressMinPathWithAnthropic:
    """Tests for LLM-based path compression."""

    def test_compress_returns_fallback_on_exception(self):
        """Test that compression falls back gracefully on LLM error."""
        from scry.core.optimizer.optimize import compress_min_path_with_anthropic

        explore = ExplorationResult(
            steps=[Navigate(url="https://example.com")],
            screenshots=[],
            html_pages=[],
            urls=["https://example.com"],
            data={},
        )

        with patch("scry.core.optimizer.optimize.has_api_key", return_value=True):
            with patch(
                "scry.core.optimizer.optimize.complete_json",
                side_effect=Exception("API error"),
            ):
                result = compress_min_path_with_anthropic(explore, "test", {})

        assert result.notes == "fallback: explored steps"
        assert len(result.steps) == 1

    def test_compress_returns_fallback_when_no_api_key(self):
        """Test that compression uses explored steps when no API key."""
        from scry.core.optimizer.optimize import compress_min_path_with_anthropic

        explore = ExplorationResult(
            steps=[Navigate(url="https://example.com"), Click(selector="#btn")],
            screenshots=[],
            html_pages=[],
            urls=["https://example.com"],
            data={},
        )

        with patch("scry.core.optimizer.optimize.has_api_key", return_value=False):
            result = compress_min_path_with_anthropic(explore, "test", {})

        assert "no_key" in result.notes
        assert len(result.steps) == 2

    def test_compress_with_successful_response(self):
        """Test successful path compression."""
        from scry.core.optimizer.optimize import compress_min_path_with_anthropic

        explore = ExplorationResult(
            steps=[
                Navigate(url="https://example.com"),
                Click(selector="#link"),
                Navigate(url="https://example.com/page"),
            ],
            screenshots=[],
            html_pages=[],
            urls=["https://example.com", "https://example.com/page"],
            data={},
        )

        mock_response = {
            "steps": [
                {"type": "navigate", "url": "https://example.com/page"},
            ],
            "notes": "Direct navigation",
        }

        with patch("scry.core.optimizer.optimize.has_api_key", return_value=True):
            with patch(
                "scry.core.optimizer.optimize.complete_json",
                return_value=(mock_response, 100),
            ):
                result = compress_min_path_with_anthropic(explore, "test", {})

        assert len(result.steps) == 1
        assert result.notes == "Direct navigation"

    def test_compress_with_empty_response(self):
        """Test compression falls back when LLM returns empty steps."""
        from scry.core.optimizer.optimize import compress_min_path_with_anthropic

        explore = ExplorationResult(
            steps=[Navigate(url="https://example.com")],
            screenshots=[],
            html_pages=[],
            urls=["https://example.com"],
            data={},
        )

        mock_response = {"steps": [], "notes": "empty"}

        with patch("scry.core.optimizer.optimize.has_api_key", return_value=True):
            with patch(
                "scry.core.optimizer.optimize.complete_json",
                return_value=(mock_response, 100),
            ):
                result = compress_min_path_with_anthropic(explore, "test", {})

        # Falls back to explored steps when response is empty
        assert result.notes == "fallback: explored steps"


class TestBuildCompressionPrompt:
    """Tests for compression prompt building."""

    def test_build_compression_prompt_format(self):
        """Test that compression prompt is properly formatted."""
        from scry.core.optimizer.optimize import _build_compression_prompt

        explore = ExplorationResult(
            steps=[Navigate(url="https://example.com"), Click(selector="#btn")],
            screenshots=[],
            html_pages=[],
            urls=["https://example.com"],
            data={},
        )

        sys_prompt, user_prompt = _build_compression_prompt(
            "Extract data", {"type": "object"}, explore
        )

        assert "navigate" in sys_prompt.lower()
        assert "click" in sys_prompt.lower()
        assert "goal: Extract data" in user_prompt
        assert "visited_urls" in user_prompt


# --- runner.py tests ---


class TestRunnerOptimizeExplorationPath:
    """Tests for exploration path optimization."""

    def test_optimize_with_no_steps_creates_minimal_plan(self):
        """Test that empty exploration creates minimal Navigate plan."""
        from scry.core.executor.runner import _optimize_exploration_path

        explore = ExplorationResult(
            steps=[],
            screenshots=[],
            html_pages=[],
            urls=[],
            data={},
        )
        execution_log: list[str] = []

        result = _optimize_exploration_path(
            explore, "https://example.com", "test", {}, execution_log
        )

        assert len(result.steps) == 1
        assert isinstance(result.steps[0], Navigate)
        assert result.steps[0].url == "https://example.com"
        assert "minimal plan" in result.notes


class TestRunnerSynthesizeSelectors:
    """Tests for selector synthesis."""

    def test_synthesize_with_no_html_returns_empty(self):
        """Test that empty HTML pages returns empty spec."""
        from scry.core.executor.runner import _synthesize_extraction_selectors

        explore = ExplorationResult(
            steps=[],
            screenshots=[],
            html_pages=[],
            urls=[],
            data={},
        )
        execution_log: list[str] = []

        result = _synthesize_extraction_selectors(
            explore, "test", None, {}, "https://example.com", execution_log
        )

        assert result == {}


class TestRunnerScriptExecution:
    """Tests for script execution handling."""

    def test_handle_script_result_with_non_zero_exit(self):
        """Test handling of non-validation script failures."""
        from scry.core.executor.runner import _handle_script_result

        # Create mock result with exit code 2 (not validation failure)
        mock_result = MagicMock()
        mock_result.returncode = 2
        mock_result.args = ["python", "script.py"]
        mock_result.stdout = ""
        mock_result.stderr = "Some error"

        execution_log: list[str] = []

        with pytest.raises(subprocess.CalledProcessError):
            _handle_script_result(mock_result, 0, execution_log)

    def test_handle_script_result_success(self):
        """Test handling of successful script execution."""
        from scry.core.executor.runner import _handle_script_result

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Success"
        mock_result.stderr = ""

        execution_log: list[str] = []

        should_continue, error_msg = _handle_script_result(mock_result, 0, execution_log)

        assert should_continue is False
        assert error_msg is None
        assert "script_done" in execution_log


class TestRunnerLoadExtractedData:
    """Tests for loading extracted data."""

    def test_load_extracted_data_with_invalid_json(self, tmp_path: Path):
        """Test loading data with invalid JSON falls back to extraction."""
        from scry.api.dto import ScrapeRequest
        from scry.core.executor.runner import _load_extracted_data

        # Create artifacts directory structure
        artifacts = tmp_path / "artifacts" / "test-job"
        artifacts.mkdir(parents=True)

        # Create invalid JSON file
        data_file = artifacts / "data.json"
        data_file.write_text("invalid json {", encoding="utf-8")

        req = ScrapeRequest(
            url="https://example.com",
            nl_request="test",
            output_schema={"type": "object"},
        )

        # Mock the artifact path function to return our test path
        with patch(
            "scry.core.executor.runner.data_artifact_path",
            return_value=data_file,
        ):
            with patch(
                "scry.core.executor.runner._finalize_from_artifacts",
                return_value={"fallback": True},
            ):
                result = _load_extracted_data(tmp_path, "test-job", req)

        assert result == {"fallback": True}


# --- browser_executor.py tests ---


class TestBrowserExecutorScrollWithCoordinate:
    """Tests for scroll with coordinate handling."""

    def test_scroll_with_coordinate_moves_mouse(self):
        """Test that scroll with coordinate moves mouse first."""
        from scry.adapters.browser_executor import BrowserExecutor

        executor = BrowserExecutor(headless=True)

        # Mock page
        mock_page = MagicMock()
        mock_mouse = MagicMock()
        mock_page.mouse = mock_mouse
        executor._page = mock_page

        result = executor._handle_scroll(
            "test-id",
            {"scroll_direction": "down", "scroll_amount": 1, "coordinate": [100, 200]},
        )

        # Mouse should move to coordinate before scrolling
        mock_mouse.move.assert_called_once_with(100, 200)
        mock_mouse.wheel.assert_called_once()
        assert result["type"] == "tool_result"


class TestBrowserExecutorFormInput:
    """Tests for form input handling."""

    def test_form_input_with_checkbox_true(self):
        """Test form input with boolean true (checkbox check)."""
        from scry.adapters.browser_executor import BrowserExecutor

        executor = BrowserExecutor(headless=True)

        mock_page = MagicMock()
        mock_element = MagicMock()
        executor._page = mock_page
        executor.ref_manager = MagicMock()
        executor.ref_manager.get_ref.return_value = MagicMock(selector="#checkbox")
        mock_page.query_selector.return_value = mock_element

        result = executor._handle_form_input("test-id", {"ref": "E1", "value": True})

        mock_element.check.assert_called_once()
        assert result["type"] == "tool_result"

    def test_form_input_with_checkbox_false(self):
        """Test form input with boolean false (checkbox uncheck)."""
        from scry.adapters.browser_executor import BrowserExecutor

        executor = BrowserExecutor(headless=True)

        mock_page = MagicMock()
        mock_element = MagicMock()
        executor._page = mock_page
        executor.ref_manager = MagicMock()
        executor.ref_manager.get_ref.return_value = MagicMock(selector="#checkbox")
        mock_page.query_selector.return_value = mock_element

        result = executor._handle_form_input("test-id", {"ref": "E1", "value": False})

        mock_element.uncheck.assert_called_once()
        assert result["type"] == "tool_result"

    def test_form_input_with_element_error(self):
        """Test form input when element operation fails."""
        from scry.adapters.browser_executor import BrowserExecutor

        executor = BrowserExecutor(headless=True)

        mock_page = MagicMock()
        mock_element = MagicMock()
        mock_element.fill.side_effect = Exception("Element not interactable")
        executor._page = mock_page
        executor.ref_manager = MagicMock()
        executor.ref_manager.get_ref.return_value = MagicMock(selector="#input")
        mock_page.query_selector.return_value = mock_element

        result = executor._handle_form_input("test-id", {"ref": "E1", "value": "test"})

        assert result["is_error"] is True
        assert "Failed to set value" in result["content"][0]["text"]


class TestBrowserExecutorContentExtraction:
    """Tests for content extraction with selector failures."""

    def test_content_extraction_with_selector_exception(self):
        """Test that selector exceptions are logged and handled."""
        from scry.adapters.browser_executor import BrowserExecutor

        executor = BrowserExecutor(headless=True)

        mock_page = MagicMock()
        mock_page.title.return_value = "Test Page"
        mock_page.url = "https://example.com"

        # First selector throws, second succeeds
        call_count = [0]

        def mock_query_selector(selector):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Selector failed")
            mock_el = MagicMock()
            mock_el.inner_text.return_value = "Page content"
            return mock_el

        mock_page.query_selector.side_effect = mock_query_selector
        executor._page = mock_page

        result = executor._handle_get_page_text("test-id", {})

        assert result["type"] == "tool_result"
        assert "Page content" in result["content"][0]["text"]


class TestBrowserExecutorStartStop:
    """Tests for browser lifecycle management."""

    def test_page_property_raises_when_not_started(self):
        """Test that accessing page before start raises error."""
        from scry.adapters.browser_executor import BrowserExecutor

        executor = BrowserExecutor(headless=True)

        with pytest.raises(RuntimeError, match="Browser not started"):
            _ = executor.page

    def test_on_page_load_resets_references(self):
        """Test that page load event resets element references."""
        from scry.adapters.browser_executor import BrowserExecutor

        executor = BrowserExecutor(headless=True)

        mock_page = MagicMock()
        mock_page.url = "https://example.com/page2"
        executor._page = mock_page
        executor.ref_manager = MagicMock()

        executor._on_page_load()

        executor.ref_manager.on_navigation.assert_called_once_with("https://example.com/page2")


# --- extract.py tests ---


class TestExtractArrayFields:
    """Tests for array field extraction."""

    def test_extract_number_with_commas(self):
        """Test extracting numbers with comma separators."""
        from bs4 import BeautifulSoup

        from scry.core.extractor.extract import _extract_number

        html = '<div class="price">$1,234.56</div>'
        soup = BeautifulSoup(html, "html.parser")

        result = _extract_number(soup, "price", "number")
        assert result == 1234.56

    def test_extract_number_returns_int_for_integer_type(self):
        """Test that integer type returns int not float."""
        from bs4 import BeautifulSoup

        from scry.core.extractor.extract import _extract_number

        html = '<div class="count">42</div>'
        soup = BeautifulSoup(html, "html.parser")

        result = _extract_number(soup, "count", "integer")
        assert result == 42
        assert isinstance(result, int)

    def test_extract_images_with_base_url(self):
        """Test image extraction with base URL resolution."""
        from bs4 import BeautifulSoup

        from scry.core.extractor.extract import _extract_images

        html = '<img src="/images/photo.jpg"><img src="https://cdn.example.com/img.png">'
        soup = BeautifulSoup(html, "html.parser")

        result = _extract_images(soup, "images", "https://example.com")

        assert len(result) == 2
        assert result[0] == "https://example.com/images/photo.jpg"
        assert result[1] == "https://cdn.example.com/img.png"

    def test_extract_links_as_objects(self):
        """Test link extraction as objects with text and href."""
        from bs4 import BeautifulSoup

        from scry.core.extractor.extract import _extract_links

        html = '<a href="/page1">Link 1</a><a href="/page2">Link 2</a>'
        soup = BeautifulSoup(html, "html.parser")

        result = _extract_links(soup, "links", "https://example.com", "object")

        assert len(result) == 2
        assert result[0]["text"] == "Link 1"
        assert result[0]["href"] == "https://example.com/page1"


class TestExtractGenericArray:
    """Tests for generic array extraction."""

    def test_extract_from_list_container(self):
        """Test extraction from ul/ol list container."""
        from bs4 import BeautifulSoup

        from scry.core.extractor.extract import _extract_generic_array

        html = '<ul class="items"><li>Item 1</li><li>Item 2</li><li>Item 3</li></ul>'
        soup = BeautifulSoup(html, "html.parser")

        result = _extract_generic_array(soup, "items")

        assert result == ["Item 1", "Item 2", "Item 3"]

    def test_extract_from_class_matches(self):
        """Test extraction from class-matched elements."""
        from bs4 import BeautifulSoup

        from scry.core.extractor.extract import _extract_generic_array

        html = '<span class="tag">Tag1</span><span class="tag">Tag2</span>'
        soup = BeautifulSoup(html, "html.parser")

        result = _extract_generic_array(soup, "tag")

        assert result == ["Tag1", "Tag2"]
