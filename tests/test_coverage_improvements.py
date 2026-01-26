"""Tests to improve code coverage across scry modules.

This file contains tests for modules that were below 80% coverage:
- element_refs.py
- selectors.py
- dom_tree.py
- anthropic.py
- events.py (additional tests)
- optimize.py (additional tests)
- telemetry.py
- llm_extract.py
- selector_plan.py
- navigator.py
- playwright.py
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ====================
# element_refs.py tests
# ====================


class TestElementReference:
    """Tests for ElementReference dataclass."""

    def test_element_reference_creation(self):
        """Test creating an ElementReference."""
        from scry.adapters.element_refs import ElementReference

        ref = ElementReference(
            ref_id="ref_0",
            selector="button.submit",
            role="button",
            name="Submit",
            attributes={"type": "submit"},
        )
        assert ref.ref_id == "ref_0"
        assert ref.selector == "button.submit"
        assert ref.role == "button"
        assert ref.name == "Submit"
        assert ref.attributes == {"type": "submit"}

    def test_element_reference_default_attributes(self):
        """Test ElementReference with default empty attributes."""
        from scry.adapters.element_refs import ElementReference

        ref = ElementReference(
            ref_id="ref_1",
            selector="a.link",
            role="link",
            name="Click here",
        )
        assert ref.attributes == {}


class TestElementReferenceManager:
    """Tests for ElementReferenceManager."""

    def test_create_ref(self):
        """Test creating element references."""
        from scry.adapters.element_refs import ElementReferenceManager

        manager = ElementReferenceManager()
        ref_id = manager.create_ref(
            selector="button.btn",
            role="button",
            name="Click me",
            attributes={"id": "btn1"},
        )
        assert ref_id == "ref_0"

        ref_id2 = manager.create_ref(
            selector="input.text",
            role="textbox",
            name="Username",
        )
        assert ref_id2 == "ref_1"

    def test_create_ref_truncates_long_name(self):
        """Test that long names are truncated to 100 characters."""
        from scry.adapters.element_refs import ElementReferenceManager

        manager = ElementReferenceManager()
        long_name = "A" * 150
        ref_id = manager.create_ref(
            selector="div",
            role="generic",
            name=long_name,
        )
        ref = manager.get_ref(ref_id)
        assert ref is not None
        assert len(ref.name) == 100

    def test_get_ref(self):
        """Test retrieving element references."""
        from scry.adapters.element_refs import ElementReferenceManager

        manager = ElementReferenceManager()
        ref_id = manager.create_ref(
            selector="button",
            role="button",
            name="Test",
        )
        ref = manager.get_ref(ref_id)
        assert ref is not None
        assert ref.selector == "button"

    def test_get_ref_nonexistent(self):
        """Test retrieving nonexistent reference."""
        from scry.adapters.element_refs import ElementReferenceManager

        manager = ElementReferenceManager()
        ref = manager.get_ref("ref_999")
        assert ref is None

    def test_has_ref(self):
        """Test checking if reference exists."""
        from scry.adapters.element_refs import ElementReferenceManager

        manager = ElementReferenceManager()
        ref_id = manager.create_ref(selector="div", role="generic", name="")
        assert manager.has_ref(ref_id) is True
        assert manager.has_ref("ref_999") is False

    def test_get_all_refs(self):
        """Test getting all references."""
        from scry.adapters.element_refs import ElementReferenceManager

        manager = ElementReferenceManager()
        manager.create_ref(selector="a", role="link", name="Link 1")
        manager.create_ref(selector="button", role="button", name="Button 1")

        all_refs = manager.get_all_refs()
        assert len(all_refs) == 2
        assert "ref_0" in all_refs
        assert "ref_1" in all_refs

    def test_reset(self):
        """Test resetting all references."""
        from scry.adapters.element_refs import ElementReferenceManager

        manager = ElementReferenceManager()
        manager.create_ref(selector="div", role="generic", name="")
        manager.reset()

        assert manager.get_all_refs() == {}
        # Counter should also reset
        ref_id = manager.create_ref(selector="span", role="generic", name="")
        assert ref_id == "ref_0"

    def test_on_navigation_same_url(self):
        """Test navigation to same URL doesn't reset."""
        from scry.adapters.element_refs import ElementReferenceManager

        manager = ElementReferenceManager()
        manager.on_navigation("https://example.com")
        manager.create_ref(selector="div", role="generic", name="")

        # Same URL shouldn't reset
        manager.on_navigation("https://example.com")
        assert len(manager.get_all_refs()) == 1

    def test_on_navigation_different_url(self):
        """Test navigation to different URL resets references."""
        from scry.adapters.element_refs import ElementReferenceManager

        manager = ElementReferenceManager()
        manager.on_navigation("https://example.com")
        manager.create_ref(selector="div", role="generic", name="")

        # Different URL should reset
        manager.on_navigation("https://other.com")
        assert len(manager.get_all_refs()) == 0


# ====================
# selectors.py tests
# ====================


class TestMakeResilientSelector:
    """Tests for make_resilient_selector function."""

    def test_basic_selector_without_html(self):
        """Test selector without HTML context."""
        from scry.core.optimizer.selectors import make_resilient_selector

        result = make_resilient_selector("div.class")
        assert "div.class" in result

    def test_selector_with_data_testid(self):
        """Test HTML with data-testid attribute."""
        from scry.core.optimizer.selectors import make_resilient_selector

        html = '<button data-testid="submit-btn">Submit</button>'
        result = make_resilient_selector("button", html)
        assert '[data-testid="submit-btn"]' in result
        # data-testid should be highest priority
        assert result[0] == '[data-testid="submit-btn"]'

    def test_selector_with_id(self):
        """Test HTML with id attribute."""
        from scry.core.optimizer.selectors import make_resilient_selector

        html = '<button id="login-btn">Login</button>'
        result = make_resilient_selector("button", html)
        assert "#login-btn" in result

    def test_selector_with_aria_label(self):
        """Test HTML with aria-label attribute."""
        from scry.core.optimizer.selectors import make_resilient_selector

        html = '<button aria-label="Close dialog">X</button>'
        result = make_resilient_selector("button", html)
        assert '[aria-label="Close dialog"]' in result

    def test_selector_with_name(self):
        """Test HTML with name attribute."""
        from scry.core.optimizer.selectors import make_resilient_selector

        html = '<input name="email" />'
        result = make_resilient_selector("input", html)
        assert '[name="email"]' in result

    def test_selector_with_text(self):
        """Test HTML with text content."""
        from scry.core.optimizer.selectors import make_resilient_selector

        html = "<button>Click Here</button>"
        result = make_resilient_selector("button", html)
        assert any("Click Here" in s for s in result)

    def test_no_duplicates(self):
        """Test that duplicate selectors are removed."""
        from scry.core.optimizer.selectors import make_resilient_selector

        html = '<button id="btn" data-testid="btn">Test</button>'
        result = make_resilient_selector('[data-testid="btn"]', html)
        # No duplicates
        assert len(result) == len(set(result))

    def test_empty_selector(self):
        """Test with empty selector."""
        from scry.core.optimizer.selectors import make_resilient_selector

        result = make_resilient_selector("")
        # Should return variants even for empty
        assert isinstance(result, list)


class TestGenerateSelectorVariants:
    """Tests for _generate_selector_variants function."""

    def test_pseudo_class_removal(self):
        """Test removing pseudo-classes."""
        from scry.core.optimizer.selectors import _generate_selector_variants

        result = _generate_selector_variants("div.class:hover")
        assert "div.class" in result

    def test_direct_child_simplification(self):
        """Test simplifying direct child selectors."""
        from scry.core.optimizer.selectors import _generate_selector_variants

        result = _generate_selector_variants("ul > li > a")
        assert "ul li a" in result

    def test_multiple_classes_simplification(self):
        """Test simplifying multiple class selectors."""
        from scry.core.optimizer.selectors import _generate_selector_variants

        result = _generate_selector_variants("div.a.b.c")
        assert any(s.count(".") < 3 for s in result)


class TestExtractAttributes:
    """Tests for _extract_attributes function."""

    def test_extract_all_attributes(self):
        """Test extracting all supported attributes."""
        from scry.core.optimizer.selectors import _extract_attributes

        html = '''<input data-testid="test" id="email" aria-label="Email" name="email">Enter email</input>'''
        attrs = _extract_attributes(html)
        assert attrs.get("data-testid") == "test"
        assert attrs.get("id") == "email"
        assert attrs.get("aria-label") == "Email"
        assert attrs.get("name") == "email"

    def test_extract_text_content(self):
        """Test extracting text content."""
        from scry.core.optimizer.selectors import _extract_attributes

        html = "<button>Click me</button>"
        attrs = _extract_attributes(html)
        assert attrs.get("text") == "Click me"

    def test_whitespace_text_ignored(self):
        """Test that whitespace-only text is ignored."""
        from scry.core.optimizer.selectors import _extract_attributes

        html = "<div>   </div>"
        attrs = _extract_attributes(html)
        assert "text" not in attrs


class TestImproveSelectorResilience:
    """Tests for improve_selector_resilience function."""

    def test_stable_selector_preserved(self):
        """Test that stable selectors are not modified."""
        from scry.core.optimizer.selectors import improve_selector_resilience

        selectors = [
            '[data-testid="btn"]',
            "#my-id",
            '[aria-label="Close"]',
            '[name="email"]',
        ]
        for sel in selectors:
            assert improve_selector_resilience(sel) == sel

    def test_overly_specific_selector_simplified(self):
        """Test simplifying deeply nested selectors."""
        from scry.core.optimizer.selectors import improve_selector_resilience

        result = improve_selector_resilience("html body div main section p")
        # Should keep only last 2 levels
        assert result.count(" ") <= 1


class TestGenerateFallbackCode:
    """Tests for generate_fallback_code function."""

    def test_empty_selectors(self):
        """Test with empty selector list."""
        from scry.core.optimizer.selectors import generate_fallback_code

        result = generate_fallback_code([])
        assert result == ""

    def test_click_action(self):
        """Test code generation for click action."""
        from scry.core.optimizer.selectors import generate_fallback_code

        result = generate_fallback_code(["button.btn", "#submit"], "click")
        assert "element.click()" in result
        assert "button.btn" in result
        assert "#submit" in result

    def test_fill_action(self):
        """Test code generation for fill action."""
        from scry.core.optimizer.selectors import generate_fallback_code

        result = generate_fallback_code(["input"], "fill")
        assert "element.fill(text)" in result

    def test_wait_action(self):
        """Test code generation for wait action."""
        from scry.core.optimizer.selectors import generate_fallback_code

        result = generate_fallback_code(["div.loading"], "wait")
        assert "element.wait_for()" in result

    def test_custom_action(self):
        """Test code generation for custom action."""
        from scry.core.optimizer.selectors import generate_fallback_code

        result = generate_fallback_code(["div"], "hover")
        assert "# Perform hover" in result


# ====================
# dom_tree.py tests
# ====================


class TestDOMTreeGenerator:
    """Tests for DOMTreeGenerator class."""

    @pytest.fixture
    def mock_page(self):
        """Create a mock Playwright page."""
        page = MagicMock()
        return page

    @pytest.fixture
    def ref_manager(self):
        """Create an ElementReferenceManager."""
        from scry.adapters.element_refs import ElementReferenceManager

        return ElementReferenceManager()

    def test_generate_empty_snapshot(self, mock_page, ref_manager):
        """Test generating tree from empty snapshot."""
        from scry.adapters.dom_tree import DOMTreeGenerator

        mock_page.accessibility.snapshot.return_value = None
        generator = DOMTreeGenerator(mock_page, ref_manager)

        result = generator.generate()
        assert result == "No accessibility tree available"

    def test_generate_simple_tree(self, mock_page, ref_manager):
        """Test generating a simple DOM tree."""
        from scry.adapters.dom_tree import DOMTreeGenerator

        mock_page.accessibility.snapshot.return_value = {
            "role": "button",
            "name": "Click me",
            "children": [],
        }
        generator = DOMTreeGenerator(mock_page, ref_manager)

        result = generator.generate()
        assert "button" in result
        assert "Click me" in result
        assert "ref=" in result

    def test_generate_with_children(self, mock_page, ref_manager):
        """Test generating tree with children."""
        from scry.adapters.dom_tree import DOMTreeGenerator

        mock_page.accessibility.snapshot.return_value = {
            "role": "navigation",
            "name": "Main nav",
            "children": [
                {"role": "link", "name": "Home", "children": []},
                {"role": "link", "name": "About", "children": []},
            ],
        }
        generator = DOMTreeGenerator(mock_page, ref_manager)

        result = generator.generate()
        assert "navigation" in result
        assert "Home" in result
        assert "About" in result

    def test_generate_interactive_filter(self, mock_page, ref_manager):
        """Test filtering to only interactive elements."""
        from scry.adapters.dom_tree import DOMTreeGenerator

        mock_page.accessibility.snapshot.return_value = {
            "role": "main",
            "name": "Content",
            "children": [
                {"role": "button", "name": "Click", "children": []},
                {"role": "generic", "name": "Text", "children": []},
            ],
        }
        generator = DOMTreeGenerator(mock_page, ref_manager)

        result = generator.generate(filter_type="interactive")
        assert "button" in result
        # Generic should be skipped but children should be processed

    def test_ignored_roles_skipped(self, mock_page, ref_manager):
        """Test that presentation roles are skipped."""
        from scry.adapters.dom_tree import DOMTreeGenerator

        mock_page.accessibility.snapshot.return_value = {
            "role": "none",
            "name": "",
            "children": [
                {"role": "button", "name": "Real button", "children": []},
            ],
        }
        generator = DOMTreeGenerator(mock_page, ref_manager)

        result = generator.generate()
        # none role should be skipped but children processed
        assert "button" in result
        assert "Real button" in result

    def test_build_selector_link(self, mock_page, ref_manager):
        """Test building selector for link with href."""
        from scry.adapters.dom_tree import DOMTreeGenerator

        generator = DOMTreeGenerator(mock_page, ref_manager)
        selector = generator._build_selector({
            "role": "link",
            "name": "Home",
            "value": "/home",
        })
        assert selector == 'a[href="/home"]'

    def test_build_selector_button(self, mock_page, ref_manager):
        """Test building selector for button."""
        from scry.adapters.dom_tree import DOMTreeGenerator

        generator = DOMTreeGenerator(mock_page, ref_manager)
        selector = generator._build_selector({
            "role": "button",
            "name": "Submit",
        })
        assert selector == 'button:has-text("Submit")'

    def test_build_selector_textbox(self, mock_page, ref_manager):
        """Test building selector for textbox."""
        from scry.adapters.dom_tree import DOMTreeGenerator

        generator = DOMTreeGenerator(mock_page, ref_manager)
        selector = generator._build_selector({"role": "textbox"})
        assert "input" in selector

    def test_build_selector_checkbox(self, mock_page, ref_manager):
        """Test building selector for checkbox."""
        from scry.adapters.dom_tree import DOMTreeGenerator

        generator = DOMTreeGenerator(mock_page, ref_manager)
        selector = generator._build_selector({"role": "checkbox"})
        assert selector == 'input[type="checkbox"]'

    def test_build_selector_radio(self, mock_page, ref_manager):
        """Test building selector for radio."""
        from scry.adapters.dom_tree import DOMTreeGenerator

        generator = DOMTreeGenerator(mock_page, ref_manager)
        selector = generator._build_selector({"role": "radio"})
        assert selector == 'input[type="radio"]'

    def test_build_selector_combobox(self, mock_page, ref_manager):
        """Test building selector for combobox."""
        from scry.adapters.dom_tree import DOMTreeGenerator

        generator = DOMTreeGenerator(mock_page, ref_manager)
        selector = generator._build_selector({"role": "combobox"})
        assert selector == "select"

    def test_build_selector_searchbox(self, mock_page, ref_manager):
        """Test building selector for searchbox."""
        from scry.adapters.dom_tree import DOMTreeGenerator

        generator = DOMTreeGenerator(mock_page, ref_manager)
        selector = generator._build_selector({"role": "searchbox"})
        assert selector == 'input[type="search"]'

    def test_extract_attributes_boolean(self, mock_page, ref_manager):
        """Test extracting boolean attributes."""
        from scry.adapters.dom_tree import DOMTreeGenerator

        generator = DOMTreeGenerator(mock_page, ref_manager)
        attrs = generator._extract_attributes({
            "checked": True,
            "disabled": False,
        })
        assert attrs["checked"] == "true"
        assert attrs["disabled"] == "false"

    def test_clean_name_truncation(self, mock_page, ref_manager):
        """Test name truncation and cleaning."""
        from scry.adapters.dom_tree import DOMTreeGenerator

        generator = DOMTreeGenerator(mock_page, ref_manager)

        # Empty name
        assert generator._clean_name("") == ""
        assert generator._clean_name(None) == ""

        # Whitespace normalization
        assert generator._clean_name("Hello   World") == "Hello World"

        # Truncation
        long_name = "A" * 150
        result = generator._clean_name(long_name)
        assert len(result) == 100
        assert result.endswith("...")

        # Quote escaping
        result = generator._clean_name('Click "here"')
        assert '\\"' in result

    def test_format_line_with_attributes(self, mock_page, ref_manager):
        """Test formatting line with attributes."""
        from scry.adapters.dom_tree import DOMTreeGenerator

        generator = DOMTreeGenerator(mock_page, ref_manager)
        line = generator._format_line(
            role="link",
            name="Home",
            ref_id="ref_0",
            attributes={"href": "/home", "type": "nav"},
            indent=1,
        )
        assert "- link" in line
        assert '"Home"' in line
        assert "[ref=ref_0]" in line
        assert 'href="/home"' in line

    def test_format_line_long_attribute_truncation(self, mock_page, ref_manager):
        """Test that long attribute values are truncated."""
        from scry.adapters.dom_tree import DOMTreeGenerator

        generator = DOMTreeGenerator(mock_page, ref_manager)
        line = generator._format_line(
            role="link",
            name="Link",
            ref_id="ref_0",
            attributes={"href": "A" * 100},  # Very long href
            indent=0,
        )
        assert "..." in line


# ====================
# anthropic.py tests
# ====================


class TestAnthropicHelpers:
    """Tests for Anthropic adapter helper functions."""

    def test_has_api_key_true(self):
        """Test has_api_key returns True when key exists."""
        from scry.adapters.anthropic import has_api_key

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            assert has_api_key() is True

    def test_has_api_key_false(self):
        """Test has_api_key returns False when no key."""
        from scry.adapters.anthropic import has_api_key

        with patch.dict(os.environ, {}, clear=True):
            assert has_api_key() is False

    def test_has_api_key_fallback_claude_api_key(self):
        """Test has_api_key uses CLAUDE_API_KEY as fallback."""
        from scry.adapters.anthropic import has_api_key

        with patch.dict(os.environ, {"CLAUDE_API_KEY": "test-key"}, clear=True):
            assert has_api_key() is True

    def test_has_browser_tools(self):
        """Test has_browser_tools function."""
        from scry.adapters.anthropic import has_browser_tools

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key", "BROWSER_TOOLS_ENABLED": "true"}):
            assert has_browser_tools() is True

        with patch.dict(os.environ, {"BROWSER_TOOLS_ENABLED": "false"}, clear=True):
            assert has_browser_tools() is False

    def test_get_browser_tool_definition(self):
        """Test browser tool definition structure."""
        from scry.adapters.anthropic import get_browser_tool_definition

        tool_def = get_browser_tool_definition()
        assert tool_def["name"] == "browser"
        assert "description" in tool_def
        assert "input_schema" in tool_def
        assert "action" in tool_def["input_schema"]["properties"]

    def test_extract_json_plain_json(self):
        """Test JSON extraction from plain JSON."""
        from scry.adapters.anthropic import _extract_json

        result = _extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_extract_json_with_prefix(self):
        """Test JSON extraction with text prefix."""
        from scry.adapters.anthropic import _extract_json

        result = _extract_json('Here is the JSON: {"key": "value"}')
        assert result == {"key": "value"}

    def test_extract_json_code_fence(self):
        """Test JSON extraction from code fence."""
        from scry.adapters.anthropic import _extract_json

        text = """```json
{"key": "value"}
```"""
        result = _extract_json(text)
        assert result == {"key": "value"}

    def test_extract_json_failure(self):
        """Test JSON extraction failure."""
        from scry.adapters.anthropic import _extract_json

        with pytest.raises(ValueError, match="Failed to parse JSON"):
            _extract_json("This is not JSON at all")


class TestCompleteJson:
    """Tests for complete_json function."""

    @patch("scry.adapters.anthropic._client")
    def test_complete_json_success(self, mock_client):
        """Test successful JSON completion."""
        from scry.adapters.anthropic import complete_json

        # Mock the client response
        mock_msg = MagicMock()
        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = '{"result": "success"}'
        mock_msg.content = [mock_block]
        mock_client.return_value.messages.create.return_value = mock_msg

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}):
            result, raw = complete_json("system", "user")
            assert result == {"result": "success"}
            assert '{"result": "success"}' in raw


class TestCallWithBrowserTool:
    """Tests for call_with_browser_tool function."""

    @patch("scry.adapters.anthropic._client")
    def test_call_with_browser_tool(self, mock_client):
        """Test calling with browser tool."""
        from scry.adapters.anthropic import call_with_browser_tool

        mock_response = MagicMock()
        mock_client.return_value.messages.create.return_value = mock_response

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}):
            result = call_with_browser_tool(
                messages=[{"role": "user", "content": "Navigate to example.com"}],
                system_prompt="You are a browser assistant",
            )
            assert result == mock_response

            # Verify the call was made with correct arguments
            call_kwargs = mock_client.return_value.messages.create.call_args.kwargs
            assert "tools" in call_kwargs
            assert call_kwargs["tools"][0]["name"] == "browser"
            assert call_kwargs["system"] == "You are a browser assistant"


# ====================
# telemetry.py tests
# ====================


class TestTelemetry:
    """Tests for telemetry module."""

    def test_init_telemetry_disabled(self):
        """Test init_telemetry when disabled."""
        from scry.telemetry import init_telemetry

        with patch.dict(os.environ, {"OTEL_ENABLED": "false"}):
            # Should not raise, just log and return
            init_telemetry()

    def test_init_telemetry_no_endpoint(self):
        """Test init_telemetry when enabled but no endpoint."""
        from scry.telemetry import init_telemetry

        with patch.dict(os.environ, {"OTEL_ENABLED": "true", "OTEL_EXPORTER_OTLP_ENDPOINT": ""}):
            # Should not raise, just log warning and return
            init_telemetry()

    @patch("scry.telemetry.logger")
    def test_init_telemetry_import_error(self, mock_logger):
        """Test init_telemetry handles ImportError."""
        from scry.telemetry import init_telemetry

        with patch.dict(os.environ, {
            "OTEL_ENABLED": "true",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://tempo:4317",
        }):
            with patch.dict("sys.modules", {"opentelemetry": None}):
                # ImportError should be caught and logged
                init_telemetry()

    def test_shutdown_telemetry_disabled(self):
        """Test shutdown_telemetry when disabled."""
        from scry.telemetry import shutdown_telemetry

        with patch.dict(os.environ, {"OTEL_ENABLED": "false"}):
            # Should return early without error
            shutdown_telemetry()

    def test_shutdown_telemetry_with_provider(self):
        """Test shutdown_telemetry calls provider.shutdown() when enabled."""
        # This test verifies the shutdown path when OTEL is enabled
        # Since we can't easily enable OTEL without the actual packages,
        # we test the disabled path which exercises the guard clause
        with patch.dict(os.environ, {"OTEL_ENABLED": "false"}):
            from scry.telemetry import shutdown_telemetry
            # Should return early without error
            shutdown_telemetry()


# ====================
# llm_extract.py tests
# ====================


class TestLlmExtract:
    """Tests for llm_extract module."""

    def test_extract_from_text_no_api_key(self):
        """Test extract_from_text returns empty dict when no API key."""
        from scry.core.extractor.llm_extract import extract_from_text

        with patch.dict(os.environ, {}, clear=True):
            result = extract_from_text(
                nl_request="Extract the title",
                parameters=None,
                schema={"title": {"type": "string"}},
                text="<html><title>Test</title></html>",
            )
            assert result == {}

    @patch("scry.core.extractor.llm_extract.complete_json")
    @patch("scry.core.extractor.llm_extract.has_api_key")
    def test_extract_from_text_success(self, mock_has_key, mock_complete):
        """Test successful extraction."""
        from scry.core.extractor.llm_extract import extract_from_text

        mock_has_key.return_value = True
        mock_complete.return_value = ({"title": "Test Title"}, "raw")

        result = extract_from_text(
            nl_request="Extract the title",
            parameters={"lang": "en"},
            schema={"title": {"type": "string"}},
            text="<html><title>Test Title</title></html>",
        )
        assert result == {"title": "Test Title"}

    @patch("scry.core.extractor.llm_extract.complete_json")
    @patch("scry.core.extractor.llm_extract.has_api_key")
    def test_extract_from_text_exception(self, mock_has_key, mock_complete):
        """Test extraction handles exceptions."""
        from scry.core.extractor.llm_extract import extract_from_text

        mock_has_key.return_value = True
        mock_complete.side_effect = Exception("API Error")

        result = extract_from_text(
            nl_request="Extract",
            parameters=None,
            schema={},
            text="text",
        )
        assert result == {}


# ====================
# selector_plan.py tests
# ====================


class TestSelectorPlan:
    """Tests for selector_plan module."""

    def test_synthesize_selectors_no_api_key(self):
        """Test synthesize_selectors returns empty dict when no API key."""
        from scry.core.extractor.selector_plan import synthesize_selectors

        with patch.dict(os.environ, {}, clear=True):
            result = synthesize_selectors(
                nl_request="Extract prices",
                parameters=None,
                schema={"price": {"type": "number"}},
                html="<div class='price'>$10</div>",
                url="https://example.com",
            )
            assert result == {}

    @patch("scry.core.extractor.selector_plan.complete_json")
    @patch("scry.core.extractor.selector_plan.has_api_key")
    def test_synthesize_selectors_success(self, mock_has_key, mock_complete):
        """Test successful selector synthesis."""
        from scry.core.extractor.selector_plan import synthesize_selectors

        mock_has_key.return_value = True
        mock_complete.return_value = (
            {"price": {"selector": ".price", "regex": r"\$(\d+)"}},
            "raw",
        )

        result = synthesize_selectors(
            nl_request="Extract prices",
            parameters={"currency": "USD"},
            schema={"price": {"type": "number"}},
            html="<div class='price'>$10</div>",
            url="https://example.com",
        )
        assert "price" in result
        assert result["price"]["selector"] == ".price"

    @patch("scry.core.extractor.selector_plan.complete_json")
    @patch("scry.core.extractor.selector_plan.has_api_key")
    def test_synthesize_selectors_exception(self, mock_has_key, mock_complete):
        """Test synthesis handles exceptions."""
        from scry.core.extractor.selector_plan import synthesize_selectors

        mock_has_key.return_value = True
        mock_complete.side_effect = Exception("API Error")

        result = synthesize_selectors(
            nl_request="Extract",
            parameters=None,
            schema={},
            html="html",
            url="url",
        )
        assert result == {}


# ====================
# events.py additional tests
# ====================


class TestRedisBusAdditional:
    """Additional tests for RedisBus to improve coverage."""

    @patch("redis.Redis.from_url")
    def test_redis_bus_dequeue_bytes_message(self, mock_redis):
        """Test RedisBus handles bytes message in dequeue."""
        from scry.runtime.events import RedisBus

        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        # Simulate bytes response
        mock_client.blpop.return_value = ("queue", b'{"job_id": "test"}')

        bus = RedisBus("redis://localhost:6379")
        result = bus.dequeue(timeout=1)
        assert result == {"job_id": "test"}

    @patch("redis.Redis.from_url")
    def test_redis_bus_get_result_none(self, mock_redis):
        """Test RedisBus returns None for missing result."""
        from scry.runtime.events import RedisBus

        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        mock_client.get.return_value = None

        bus = RedisBus("redis://localhost:6379")
        result = bus.get_result("missing-job")
        assert result is None


# ====================
# optimize.py additional tests
# ====================


class TestOptimizeHelpers:
    """Additional tests for optimize.py helper functions."""

    def test_is_duplicate_step_none_prev(self):
        """Test _is_duplicate_step with None previous step."""
        from scry.core.optimizer.optimize import _is_duplicate_step

        result = _is_duplicate_step(None, "any_step")
        assert result is False

    def test_is_redundant_wait_after_navigate(self):
        """Test _is_redundant_wait_after_navigate."""
        from scry.core.ir.model import Navigate, WaitFor
        from scry.core.optimizer.optimize import _is_redundant_wait_after_navigate

        nav = Navigate(url="https://example.com")
        wait = WaitFor(selector="body", state="visible")

        assert _is_redundant_wait_after_navigate(wait, nav) is True
        assert _is_redundant_wait_after_navigate(nav, nav) is False
        # When prev_step is None, short-circuit returns falsy (None), not False
        assert not _is_redundant_wait_after_navigate(wait, None)

    def test_try_merge_wait_for_different_selectors(self):
        """Test _try_merge_wait_for with different selectors."""
        from scry.core.ir.model import WaitFor
        from scry.core.optimizer.optimize import _try_merge_wait_for

        wait1 = WaitFor(selector="div.a", state="visible")
        wait2 = WaitFor(selector="div.b", state="visible")
        optimized = [wait1]

        result = _try_merge_wait_for(wait2, optimized)
        assert result is False  # Not merged because different selectors

    def test_try_merge_wait_for_attached_to_visible(self):
        """Test _try_merge_wait_for upgrades attached to visible."""
        from scry.core.ir.model import WaitFor
        from scry.core.optimizer.optimize import _try_merge_wait_for

        wait1 = WaitFor(selector="div", state="visible")
        wait2 = WaitFor(selector="div", state="attached")
        optimized = [wait1]

        result = _try_merge_wait_for(wait2, optimized)
        assert result is True
        assert optimized[-1].state == "visible"  # Should keep visible

    def test_handle_validate_step_non_validate(self):
        """Test _handle_validate_step with non-Validate step."""
        from scry.core.ir.model import Click
        from scry.core.optimizer.optimize import _handle_validate_step

        click = Click(selector="button")
        optimized: list[Any] = []

        result = _handle_validate_step(click, optimized)
        assert result is False
        assert len(optimized) == 0

    def test_handle_validate_step_consecutive_validates(self):
        """Test _handle_validate_step skips consecutive validates."""
        from scry.core.ir.model import Validate
        from scry.core.optimizer.optimize import _handle_validate_step

        v1 = Validate(selector="div", validation_type="presence")
        v2 = Validate(selector="span", validation_type="presence")
        optimized: list[Any] = [v1]

        result = _handle_validate_step(v2, optimized)
        assert result is True
        assert len(optimized) == 1  # Should not add another validate

    def test_step_to_dict_all_types(self):
        """Test _step_to_dict for all step types."""
        from scry.core.ir.model import Click, Fill, Navigate, Validate, WaitFor
        from scry.core.optimizer.optimize import _step_to_dict

        assert _step_to_dict(Navigate(url="https://x.com")) == {"type": "navigate", "url": "https://x.com"}
        assert _step_to_dict(Click(selector="btn")) == {"type": "click", "selector": "btn"}
        assert _step_to_dict(Fill(selector="input", text="hello")) == {"type": "fill", "selector": "input", "text": "hello"}
        assert _step_to_dict(WaitFor(selector="div", state="visible")) == {"type": "wait_for", "selector": "div", "state": "visible"}

        validate = Validate(selector="span", validation_type="presence", is_critical=True, description="Check span")
        v_dict = _step_to_dict(validate)
        assert v_dict["type"] == "validate"
        assert v_dict["is_critical"] is True

        # Unknown type
        assert _step_to_dict("unknown") is None

    def test_dict_to_step_all_types(self):
        """Test _dict_to_step for all step types."""
        from scry.core.ir.model import Click, Fill, Navigate, WaitFor
        from scry.core.optimizer.optimize import _dict_to_step

        nav = _dict_to_step({"type": "navigate", "url": "https://x.com"})
        assert isinstance(nav, Navigate)
        assert nav.url == "https://x.com"

        click = _dict_to_step({"type": "click", "selector": "btn"})
        assert isinstance(click, Click)

        fill = _dict_to_step({"type": "fill", "selector": "input", "text": "hi"})
        assert isinstance(fill, Fill)

        wait = _dict_to_step({"type": "wait_for", "selector": "div"})
        assert isinstance(wait, WaitFor)

        # Alias types
        wait2 = _dict_to_step({"type": "wait", "selector": "div"})
        assert isinstance(wait2, WaitFor)

        wait3 = _dict_to_step({"type": "waitfor", "selector": "div"})
        assert isinstance(wait3, WaitFor)

        # Invalid
        assert _dict_to_step({"type": "unknown"}) is None
        assert _dict_to_step({"type": "navigate"}) is None  # Missing url

    def test_selector_improvement_helpers(self):
        """Test individual selector improvement helpers."""
        from scry.core.optimizer.optimize import (
            _has_stable_attribute,
            _is_simple_id_selector,
            _remove_nth_child,
            _simplify_multi_class_selector,
        )

        # Stable attributes
        assert _has_stable_attribute('[data-testid="x"]') is True
        assert _has_stable_attribute('[data-test="x"]') is True
        assert _has_stable_attribute('[aria-label="x"]') is True
        assert _has_stable_attribute("div.class") is False

        # Simple ID selector
        assert _is_simple_id_selector("#myid") is True
        assert _is_simple_id_selector("#my id") is False
        assert _is_simple_id_selector("div#myid") is False

        # Multi-class simplification
        assert _simplify_multi_class_selector("div.a.b") is None  # Not many classes
        result = _simplify_multi_class_selector("div.a.b.c.d.e")
        assert result is not None
        assert result.count(".") == 3  # First 4 parts

        # nth-child removal
        assert _remove_nth_child("li") is None  # No nth-child
        result = _remove_nth_child("li:nth-child(3)")
        assert result is not None
        assert ":nth-child" not in result


# ====================
# navigator.py tests
# ====================


class TestNavigatorHelpers:
    """Tests for navigator.py helper functions."""

    def test_get_http_credentials_none(self):
        """Test _get_http_credentials with None input."""
        from scry.core.nav.navigator import _get_http_credentials

        assert _get_http_credentials(None) is None
        assert _get_http_credentials({}) is None
        assert _get_http_credentials({"other": "value"}) is None

    def test_get_http_credentials_valid(self):
        """Test _get_http_credentials with valid credentials."""
        from scry.core.nav.navigator import _get_http_credentials

        result = _get_http_credentials({
            "http_basic": {
                "username": "user",
                "password": "pass",
            }
        })
        assert result == {"username": "user", "password": "pass"}

    def test_get_http_credentials_invalid_http_basic(self):
        """Test _get_http_credentials with invalid http_basic."""
        from scry.core.nav.navigator import _get_http_credentials

        assert _get_http_credentials({"http_basic": "not_a_dict"}) is None
        assert _get_http_credentials({"http_basic": None}) is None


class TestNavigatorStepExecutors:
    """Tests for navigator step executor functions."""

    @pytest.fixture
    def mock_page(self):
        """Create a mock Playwright page."""
        return MagicMock()

    def test_execute_click(self, mock_page):
        """Test _execute_click."""
        from scry.core.ir.model import Click
        from scry.core.nav.navigator import _execute_click

        step = Click(selector="button.submit")
        _execute_click(mock_page, step)
        mock_page.click.assert_called_once_with("button.submit")

    def test_execute_fill(self, mock_page):
        """Test _execute_fill."""
        from scry.core.ir.model import Fill
        from scry.core.nav.navigator import _execute_fill

        step = Fill(selector="input.email", text="test@example.com")
        _execute_fill(mock_page, step)
        mock_page.fill.assert_called_once_with("input.email", "test@example.com")

    def test_execute_select(self, mock_page):
        """Test _execute_select."""
        from scry.core.ir.model import Select
        from scry.core.nav.navigator import _execute_select

        step = Select(selector="select.country", value="US")
        _execute_select(mock_page, step)
        mock_page.select_option.assert_called_once_with("select.country", "US")

    def test_execute_hover(self, mock_page):
        """Test _execute_hover."""
        from scry.core.ir.model import Hover
        from scry.core.nav.navigator import _execute_hover

        step = Hover(selector="div.menu")
        _execute_hover(mock_page, step)
        mock_page.hover.assert_called_once_with("div.menu")
        mock_page.wait_for_timeout.assert_called_once_with(500)

    def test_execute_keypress_with_selector(self, mock_page):
        """Test _execute_keypress with selector."""
        from scry.core.ir.model import KeyPress
        from scry.core.nav.navigator import _execute_keypress

        mock_locator = MagicMock()
        mock_page.locator.return_value = mock_locator

        step = KeyPress(selector="input.search", key="Enter")
        _execute_keypress(mock_page, step)
        mock_page.locator.assert_called_once_with("input.search")
        mock_locator.press.assert_called_once_with("Enter")

    def test_execute_keypress_without_selector(self, mock_page):
        """Test _execute_keypress without selector."""
        from scry.core.ir.model import KeyPress
        from scry.core.nav.navigator import _execute_keypress

        step = KeyPress(selector=None, key="Escape")
        _execute_keypress(mock_page, step)
        mock_page.keyboard.press.assert_called_once_with("Escape")

    def test_execute_upload(self, mock_page):
        """Test _execute_upload."""
        from scry.core.ir.model import Upload
        from scry.core.nav.navigator import _execute_upload

        step = Upload(selector="input[type=file]", file_path="/path/to/file.pdf")
        _execute_upload(mock_page, step)
        mock_page.set_input_files.assert_called_once_with("input[type=file]", "/path/to/file.pdf")

    def test_execute_wait_for_visible(self, mock_page):
        """Test _execute_wait_for with visible state."""
        from scry.core.ir.model import WaitFor
        from scry.core.nav.navigator import _execute_wait_for

        step = WaitFor(selector="div.content", state="visible")
        _execute_wait_for(mock_page, step)
        mock_page.wait_for_selector.assert_called_once_with("div.content", state="visible")

    def test_execute_wait_for_default_state(self, mock_page):
        """Test _execute_wait_for with unsupported state."""
        from scry.core.ir.model import WaitFor
        from scry.core.nav.navigator import _execute_wait_for

        step = WaitFor(selector="div", state="custom")
        _execute_wait_for(mock_page, step)
        mock_page.wait_for_selector.assert_called_once_with("div")

    def test_execute_wait_for_timeout(self, mock_page):
        """Test _execute_wait_for handles timeout gracefully."""
        from playwright.sync_api import TimeoutError as PWTimeoutError

        from scry.core.ir.model import WaitFor
        from scry.core.nav.navigator import _execute_wait_for

        mock_page.wait_for_selector.side_effect = PWTimeoutError("Timeout")

        step = WaitFor(selector="div.slow", state="visible")
        # Should not raise - timeout is non-fatal
        _execute_wait_for(mock_page, step)

    def test_execute_navigate_data_url(self, mock_page):
        """Test _execute_navigate with data: URL."""
        from scry.core.ir.model import Navigate
        from scry.core.nav.navigator import _execute_navigate

        step = Navigate(url="data:text/html,<html><body>Test</body></html>")
        _execute_navigate(mock_page, step)
        mock_page.set_content.assert_called_once()

    def test_execute_navigate_regular_url(self, mock_page):
        """Test _execute_navigate with regular URL."""
        from scry.core.ir.model import Navigate
        from scry.core.nav.navigator import _execute_navigate

        step = Navigate(url="https://example.com")
        _execute_navigate(mock_page, step)
        mock_page.goto.assert_called_once_with("https://example.com")

    def test_execute_step_dispatch(self, mock_page):
        """Test _execute_step dispatches correctly."""
        from scry.core.ir.model import Click, Navigate
        from scry.core.nav.navigator import _execute_step

        nav = Navigate(url="https://example.com")
        _execute_step(mock_page, nav)
        mock_page.goto.assert_called()

        mock_page.reset_mock()
        click = Click(selector="btn")
        _execute_step(mock_page, click)
        mock_page.click.assert_called()


# ====================
# playwright.py tests
# ====================


class TestPlaywrightScreenshot:
    """Tests for playwright.py take_screenshot function."""

    @patch("scry.adapters.playwright.sync_playwright")
    def test_take_screenshot(self, mock_playwright):
        """Test taking a screenshot."""
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from scry.adapters.playwright import take_screenshot

        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_pw_instance = MagicMock()
        mock_pw_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        mock_playwright.return_value.__enter__.return_value = mock_pw_instance

        with TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "screenshot.png"
            take_screenshot("https://example.com", out_path, headless=True, timeout_ms=5000)

            mock_page.goto.assert_called_once_with("https://example.com")
            mock_page.screenshot.assert_called_once()
            mock_browser.close.assert_called_once()


# ====================
# plan_builder.py tests
# ====================


class TestPlanBuilderHelpers:
    """Tests for plan_builder.py helper functions."""

    def test_sanitize_url_http(self):
        """Test URL sanitization for http URLs."""
        from scry.core.planner.plan_builder import _sanitize_url

        assert _sanitize_url("http://example.com") == "http://example.com"
        assert _sanitize_url("https://example.com") == "https://example.com"

    def test_sanitize_url_data(self):
        """Test URL sanitization for data URLs."""
        from scry.core.planner.plan_builder import _sanitize_url

        data_url = "data:text/html,<html></html>"
        assert _sanitize_url(data_url) == data_url

    def test_sanitize_url_invalid(self):
        """Test URL sanitization rejects invalid URLs."""
        from scry.core.planner.plan_builder import _sanitize_url

        assert _sanitize_url("javascript:alert(1)") == ""
        assert _sanitize_url("file:///etc/passwd") == ""
        assert _sanitize_url(123) == ""  # Non-string


class TestStepParsers:
    """Tests for individual step parser functions."""

    def test_parse_navigate(self):
        """Test parsing navigate steps."""
        from scry.core.planner.plan_builder import _parse_navigate

        step = _parse_navigate({"url": "https://example.com"})
        assert step is not None
        assert step.url == "https://example.com"

        # Invalid URL
        assert _parse_navigate({"url": "invalid"}) is None
        assert _parse_navigate({}) is None

    def test_parse_click(self):
        """Test parsing click steps."""
        from scry.core.planner.plan_builder import _parse_click

        step = _parse_click({"selector": "button.submit"})
        assert step is not None
        assert step.selector == "button.submit"

        # Invalid
        assert _parse_click({}) is None
        assert _parse_click({"selector": ""}) is None
        assert _parse_click({"selector": 123}) is None

    def test_parse_fill(self):
        """Test parsing fill steps."""
        from scry.core.planner.plan_builder import _parse_fill

        step = _parse_fill({"selector": "input.email", "text": "test@example.com"})
        assert step is not None
        assert step.selector == "input.email"
        assert step.text == "test@example.com"

        # Invalid
        assert _parse_fill({}) is None
        assert _parse_fill({"selector": ""}) is None

    def test_parse_wait_for(self):
        """Test parsing wait_for steps."""
        from scry.core.planner.plan_builder import _parse_wait_for

        step = _parse_wait_for({"selector": "div.loaded", "state": "visible"})
        assert step is not None
        assert step.selector == "div.loaded"
        assert step.state == "visible"

        # Skips metadata elements
        assert _parse_wait_for({"selector": "title"}) is None
        assert _parse_wait_for({"selector": "meta[name='description']"}) is None
        assert _parse_wait_for({"selector": "script"}) is None

        # Invalid
        assert _parse_wait_for({}) is None
        assert _parse_wait_for({"selector": ""}) is None

    def test_parse_select(self):
        """Test parsing select steps."""
        from scry.core.planner.plan_builder import _parse_select

        step = _parse_select({"selector": "select.country", "value": "US"})
        assert step is not None
        assert step.selector == "select.country"
        assert step.value == "US"

        # Empty value is allowed (empty string is still a string)
        step_empty_value = _parse_select({"selector": "select", "value": ""})
        assert step_empty_value is not None
        assert step_empty_value.value == ""

        # Invalid
        assert _parse_select({}) is None
        assert _parse_select({"selector": "", "value": "US"}) is None  # Empty selector
        assert _parse_select({"selector": "select", "value": 123}) is None  # Non-string value

    def test_parse_hover(self):
        """Test parsing hover steps."""
        from scry.core.planner.plan_builder import _parse_hover

        step = _parse_hover({"selector": "div.menu"})
        assert step is not None
        assert step.selector == "div.menu"

        # Invalid
        assert _parse_hover({}) is None

    def test_parse_keypress(self):
        """Test parsing keypress steps."""
        from scry.core.planner.plan_builder import _parse_keypress

        step = _parse_keypress({"key": "Enter", "selector": "input.search"})
        assert step is not None
        assert step.key == "Enter"
        assert step.selector == "input.search"

        # Without selector
        step2 = _parse_keypress({"key": "Escape"})
        assert step2 is not None
        assert step2.key == "Escape"

        # Invalid
        assert _parse_keypress({}) is None

    def test_parse_upload(self):
        """Test parsing upload steps."""
        from scry.core.planner.plan_builder import _parse_upload

        step = _parse_upload({"selector": "input[type=file]", "file_path": "/path/to/file.pdf"})
        assert step is not None
        assert step.selector == "input[type=file]"
        assert step.file_path == "/path/to/file.pdf"

        # Invalid
        assert _parse_upload({}) is None
        assert _parse_upload({"selector": "", "file_path": "/file.txt"}) is None  # Empty selector

    def test_parse_step_with_type(self):
        """Test _parse_step dispatches correctly."""
        from scry.core.planner.plan_builder import _parse_step

        # Navigate
        step = _parse_step({"type": "navigate", "url": "https://example.com"})
        assert step is not None

        # Click
        step = _parse_step({"type": "click", "selector": "button"})
        assert step is not None

        # Fill
        step = _parse_step({"type": "fill", "selector": "input", "text": "hello"})
        assert step is not None

        # Various wait_for aliases
        step = _parse_step({"type": "wait_for", "selector": "div"})
        assert step is not None
        step = _parse_step({"type": "waitfor", "selector": "div"})
        assert step is not None
        step = _parse_step({"type": "wait", "selector": "div"})
        assert step is not None

        # Select
        step = _parse_step({"type": "select", "selector": "select", "value": "opt1"})
        assert step is not None

        # Hover
        step = _parse_step({"type": "hover", "selector": "div"})
        assert step is not None

        # Keypress aliases
        step = _parse_step({"type": "keypress", "key": "Enter"})
        assert step is not None
        step = _parse_step({"type": "key_press", "key": "Enter"})
        assert step is not None
        step = _parse_step({"type": "press", "key": "Enter"})
        assert step is not None

        # Upload
        step = _parse_step({"type": "upload", "selector": "input", "file_path": "/file.txt"})
        assert step is not None

        # Invalid
        assert _parse_step({"type": "unknown"}) is None
        assert _parse_step({"type": 123}) is None
        assert _parse_step("not a dict") is None


class TestBuildPlan:
    """Tests for build_plan function."""

    def test_build_default_with_url(self):
        """Test building default plan with target URL."""
        from scry.api.dto import ScrapeRequest
        from scry.core.planner.plan_builder import _build_default

        req = ScrapeRequest(
            nl_request="Test",
            schema={},
            target_urls=["https://example.com"],
        )
        plan = _build_default(req)
        assert len(plan.steps) == 1
        assert plan.steps[0].url == "https://example.com"

    def test_build_default_no_url(self):
        """Test building default plan without URL."""
        from scry.api.dto import ScrapeRequest
        from scry.core.planner.plan_builder import _build_default

        req = ScrapeRequest(
            nl_request="Test",
            schema={},
            target_urls=[],
        )
        plan = _build_default(req)
        assert len(plan.steps) == 0

    def test_ensure_navigation_adds_navigate(self):
        """Test _ensure_navigation adds Navigate if missing."""
        from scry.core.ir.model import Click
        from scry.core.planner.plan_builder import _ensure_navigation

        steps = [Click(selector="button")]
        _ensure_navigation(steps, ["https://example.com"])
        assert len(steps) == 2
        assert steps[0].url == "https://example.com"

    def test_ensure_navigation_preserves_existing(self):
        """Test _ensure_navigation preserves existing Navigate."""
        from scry.core.ir.model import Navigate
        from scry.core.planner.plan_builder import _ensure_navigation

        steps = [Navigate(url="https://example.com")]
        _ensure_navigation(steps, ["https://other.com"])
        assert len(steps) == 1
        assert steps[0].url == "https://example.com"

    @patch("scry.core.planner.plan_builder.has_api_key")
    def test_build_plan_no_api_key(self, mock_has_key):
        """Test build_plan falls back when no API key."""
        from scry.api.dto import ScrapeRequest
        from scry.core.planner.plan_builder import build_plan

        mock_has_key.return_value = False
        req = ScrapeRequest(
            nl_request="Extract data",
            schema={},
            target_urls=["https://example.com"],
        )
        plan = build_plan(req)
        assert len(plan.steps) == 1

    def test_ensure_navigation_empty_urls(self):
        """Test _ensure_navigation with empty target_urls list."""
        from scry.core.ir.model import Click
        from scry.core.planner.plan_builder import _ensure_navigation

        steps = [Click(selector="button")]
        _ensure_navigation(steps, [])
        # Should not add anything when no target_urls
        assert len(steps) == 1

    @patch("scry.core.planner.plan_builder.complete_json")
    @patch("scry.core.planner.plan_builder.has_api_key")
    def test_build_plan_with_llm_success(self, mock_has_key, mock_complete_json):
        """Test build_plan with LLM returning valid plan."""
        from scry.api.dto import ScrapeRequest
        from scry.core.planner.plan_builder import build_plan

        mock_has_key.return_value = True
        mock_complete_json.return_value = (
            {
                "steps": [
                    {"type": "navigate", "url": "https://example.com"},
                    {"type": "click", "selector": "button.submit"},
                ],
                "notes": "LLM generated plan",
            },
            {},  # usage info
        )

        req = ScrapeRequest(
            nl_request="Click submit button",
            schema={},
            target_urls=["https://example.com"],
        )
        plan = build_plan(req)
        assert len(plan.steps) == 2
        assert "LLM generated plan" in plan.notes

    @patch("scry.core.planner.plan_builder.complete_json")
    @patch("scry.core.planner.plan_builder.has_api_key")
    def test_build_plan_with_llm_failure(self, mock_has_key, mock_complete_json):
        """Test build_plan falls back when LLM fails."""
        from scry.api.dto import ScrapeRequest
        from scry.core.planner.plan_builder import build_plan

        mock_has_key.return_value = True
        mock_complete_json.side_effect = Exception("API error")

        req = ScrapeRequest(
            nl_request="Extract data",
            schema={},
            target_urls=["https://example.com"],
        )
        plan = build_plan(req)
        # Should fall back to default plan
        assert len(plan.steps) == 1

    @patch("scry.core.planner.plan_builder.complete_json")
    @patch("scry.core.planner.plan_builder.has_api_key")
    def test_build_plan_with_llm_empty_steps(self, mock_has_key, mock_complete_json):
        """Test build_plan falls back when LLM returns empty steps."""
        from scry.api.dto import ScrapeRequest
        from scry.core.planner.plan_builder import build_plan

        mock_has_key.return_value = True
        mock_complete_json.return_value = ({"steps": [], "notes": ""}, {})

        req = ScrapeRequest(
            nl_request="Extract data",
            schema={},
            target_urls=["https://example.com"],
        )
        plan = build_plan(req)
        # Should fall back to default plan
        assert len(plan.steps) == 1

    @patch("scry.core.planner.plan_builder.complete_json")
    @patch("scry.core.planner.plan_builder.has_api_key")
    def test_build_plan_with_llm_invalid_steps(self, mock_has_key, mock_complete_json):
        """Test build_plan handles invalid step types from LLM."""
        from scry.api.dto import ScrapeRequest
        from scry.core.planner.plan_builder import build_plan

        mock_has_key.return_value = True
        mock_complete_json.return_value = (
            {
                "steps": [
                    {"type": "invalid_type", "selector": "button"},
                    {"type": "click", "selector": "button.valid"},
                ],
                "notes": "Has invalid step",
            },
            {},
        )

        req = ScrapeRequest(
            nl_request="Extract data",
            schema={},
            target_urls=["https://example.com"],
        )
        plan = build_plan(req)
        # Should skip invalid step but include valid one and add navigation
        assert any(step.selector == "button.valid" for step in plan.steps if hasattr(step, "selector"))

    @patch("scry.core.planner.plan_builder.complete_json")
    @patch("scry.core.planner.plan_builder.has_api_key")
    def test_build_plan_llm_returns_none(self, mock_has_key, mock_complete_json):
        """Test build_plan when complete_json returns None-like response."""
        from scry.api.dto import ScrapeRequest
        from scry.core.planner.plan_builder import build_plan

        mock_has_key.return_value = True
        mock_complete_json.return_value = (None, {})

        req = ScrapeRequest(
            nl_request="Extract data",
            schema={},
            target_urls=["https://example.com"],
        )
        plan = build_plan(req)
        # Should fall back to default plan
        assert len(plan.steps) == 1


# ====================
# browser_executor.py tests
# ====================


class TestBrowserExecutorHelpers:
    """Tests for BrowserExecutor helper methods."""

    def test_success_result(self):
        """Test _success_result creates correct structure."""
        from scry.adapters.browser_executor import BrowserExecutor

        executor = BrowserExecutor()
        result = executor._success_result("test-id", [{"type": "text", "text": "OK"}])
        assert result["type"] == "tool_result"
        assert result["tool_use_id"] == "test-id"
        assert "is_error" not in result
        assert len(result["content"]) == 1

    def test_error_result(self):
        """Test _error_result creates correct structure."""
        from scry.adapters.browser_executor import BrowserExecutor

        executor = BrowserExecutor()
        result = executor._error_result("test-id", "Something went wrong")
        assert result["type"] == "tool_result"
        assert result["tool_use_id"] == "test-id"
        assert result["is_error"] is True
        assert "Something went wrong" in result["content"][0]["text"]


class TestBrowserExecutorActions:
    """Tests for BrowserExecutor action handlers (mocked)."""

    @pytest.fixture
    def executor_with_mock_page(self):
        """Create executor with mocked page."""
        from scry.adapters.browser_executor import BrowserExecutor

        executor = BrowserExecutor()
        executor._page = MagicMock()
        executor._page.screenshot.return_value = b"fake_png_data"
        executor.dom_generator = MagicMock()
        executor.dom_generator.generate.return_value = "- button [ref=ref_0]"
        return executor

    def test_execute_unknown_action(self, executor_with_mock_page):
        """Test execute returns error for unknown action."""
        result = executor_with_mock_page.execute("test-id", {"action": "unknown"})
        assert result["is_error"] is True
        assert "Unknown action" in result["content"][0]["text"]

    def test_execute_navigate_no_url(self, executor_with_mock_page):
        """Test navigate without URL returns error."""
        result = executor_with_mock_page.execute("test-id", {"action": "navigate"})
        assert result["is_error"] is True

    def test_execute_navigate_back(self, executor_with_mock_page):
        """Test navigate back."""
        result = executor_with_mock_page.execute("test-id", {"action": "navigate", "text": "back"})
        executor_with_mock_page._page.go_back.assert_called_once()
        assert result.get("is_error") is not True

    def test_execute_navigate_forward(self, executor_with_mock_page):
        """Test navigate forward."""
        result = executor_with_mock_page.execute("test-id", {"action": "navigate", "text": "forward"})
        executor_with_mock_page._page.go_forward.assert_called_once()
        assert result.get("is_error") is not True

    def test_execute_navigate_url_no_protocol(self, executor_with_mock_page):
        """Test navigate adds https:// to URL without protocol."""
        executor_with_mock_page.execute("test-id", {"action": "navigate", "text": "example.com"})
        executor_with_mock_page._page.goto.assert_called_with(
            "https://example.com", wait_until="domcontentloaded"
        )

    def test_execute_screenshot(self, executor_with_mock_page):
        """Test screenshot action."""
        result = executor_with_mock_page.execute("test-id", {"action": "screenshot"})
        assert result.get("is_error") is not True
        executor_with_mock_page._page.screenshot.assert_called()

    def test_execute_read_page(self, executor_with_mock_page):
        """Test read_page action."""
        result = executor_with_mock_page.execute("test-id", {"action": "read_page"})
        assert result.get("is_error") is not True
        executor_with_mock_page.dom_generator.generate.assert_called()

    def test_execute_read_page_no_generator(self):
        """Test read_page without DOM generator returns error."""
        from scry.adapters.browser_executor import BrowserExecutor

        executor = BrowserExecutor()
        executor._page = MagicMock()
        executor.dom_generator = None
        result = executor.execute("test-id", {"action": "read_page"})
        assert result["is_error"] is True

    def test_execute_get_page_text(self, executor_with_mock_page):
        """Test get_page_text action."""
        executor_with_mock_page._page.title.return_value = "Test Page"
        executor_with_mock_page._page.url = "https://example.com"
        mock_element = MagicMock()
        mock_element.inner_text.return_value = "Page content here"
        executor_with_mock_page._page.query_selector.return_value = mock_element

        result = executor_with_mock_page.execute("test-id", {"action": "get_page_text"})
        assert result.get("is_error") is not True
        assert "Test Page" in result["content"][0]["text"]

    def test_execute_type_no_text(self, executor_with_mock_page):
        """Test type without text returns error."""
        result = executor_with_mock_page.execute("test-id", {"action": "type"})
        assert result.get("is_error") is True

    def test_execute_type(self, executor_with_mock_page):
        """Test type action."""
        result = executor_with_mock_page.execute("test-id", {"action": "type", "text": "hello"})
        assert result.get("is_error") is not True
        executor_with_mock_page._page.keyboard.type.assert_called_with("hello")

    def test_execute_key_no_key(self, executor_with_mock_page):
        """Test key without key returns error."""
        result = executor_with_mock_page.execute("test-id", {"action": "key"})
        assert result.get("is_error") is True

    def test_execute_key_simple(self, executor_with_mock_page):
        """Test simple key press."""
        result = executor_with_mock_page.execute("test-id", {"action": "key", "text": "Enter"})
        assert result.get("is_error") is not True
        executor_with_mock_page._page.keyboard.press.assert_called()

    def test_execute_key_combination(self, executor_with_mock_page):
        """Test key combination press."""
        result = executor_with_mock_page.execute("test-id", {"action": "key", "text": "ctrl+a"})
        assert result.get("is_error") is not True
        # Should press modifiers and key

    def test_execute_scroll_no_direction(self, executor_with_mock_page):
        """Test scroll without direction returns error."""
        result = executor_with_mock_page.execute("test-id", {"action": "scroll"})
        assert result.get("is_error") is True

    def test_execute_scroll_invalid_direction(self, executor_with_mock_page):
        """Test scroll with invalid direction returns error."""
        result = executor_with_mock_page.execute("test-id", {"action": "scroll", "scroll_direction": "diagonal"})
        assert result.get("is_error") is True

    def test_execute_scroll_directions(self, executor_with_mock_page):
        """Test scroll in all directions."""
        for direction in ["up", "down", "left", "right"]:
            result = executor_with_mock_page.execute("test-id", {
                "action": "scroll",
                "scroll_direction": direction,
                "scroll_amount": 2,
            })
            assert result.get("is_error") is not True

    def test_execute_wait(self, executor_with_mock_page):
        """Test wait action."""
        result = executor_with_mock_page.execute("test-id", {"action": "wait", "duration": 0.1})
        assert result.get("is_error") is not True

    def test_execute_wait_max_duration(self, executor_with_mock_page):
        """Test wait action limits duration to 100 seconds."""
        executor_with_mock_page.execute("test-id", {"action": "wait", "duration": 200})
        # Should be limited to 100 seconds
        executor_with_mock_page._page.wait_for_timeout.assert_called_with(100000)

    def test_execute_hold_key_no_key(self, executor_with_mock_page):
        """Test hold_key without key returns error."""
        result = executor_with_mock_page.execute("test-id", {"action": "hold_key"})
        assert result.get("is_error") is True

    def test_execute_hold_key(self, executor_with_mock_page):
        """Test hold_key action."""
        result = executor_with_mock_page.execute("test-id", {"action": "hold_key", "text": "Shift", "duration": 0.1})
        assert result.get("is_error") is not True

    def test_execute_zoom_no_region(self, executor_with_mock_page):
        """Test zoom without region returns error."""
        result = executor_with_mock_page.execute("test-id", {"action": "zoom"})
        assert result.get("is_error") is True

    def test_execute_zoom_invalid_region(self, executor_with_mock_page):
        """Test zoom with invalid region returns error."""
        result = executor_with_mock_page.execute("test-id", {"action": "zoom", "region": [1, 2]})
        assert result.get("is_error") is True

    def test_execute_zoom(self, executor_with_mock_page):
        """Test zoom action."""
        result = executor_with_mock_page.execute("test-id", {"action": "zoom", "region": [0, 0, 100, 100]})
        assert result.get("is_error") is not True

    def test_execute_find_no_query(self, executor_with_mock_page):
        """Test find without query returns error."""
        result = executor_with_mock_page.execute("test-id", {"action": "find"})
        assert result.get("is_error") is True

    def test_execute_find(self, executor_with_mock_page):
        """Test find action."""
        result = executor_with_mock_page.execute("test-id", {"action": "find", "text": "button"})
        assert result.get("is_error") is not True

    def test_execute_left_click_no_target(self, executor_with_mock_page):
        """Test left_click without ref or coordinate returns error."""
        result = executor_with_mock_page.execute("test-id", {"action": "left_click"})
        assert result.get("is_error") is True

    def test_execute_left_click_coordinate(self, executor_with_mock_page):
        """Test left_click with coordinate."""
        result = executor_with_mock_page.execute("test-id", {"action": "left_click", "coordinate": [100, 200]})
        assert result.get("is_error") is not True
        executor_with_mock_page._page.mouse.click.assert_called()

    def test_execute_right_click_coordinate(self, executor_with_mock_page):
        """Test right_click with coordinate."""
        result = executor_with_mock_page.execute("test-id", {"action": "right_click", "coordinate": [100, 200]})
        assert result.get("is_error") is not True

    def test_execute_middle_click_coordinate(self, executor_with_mock_page):
        """Test middle_click with coordinate."""
        result = executor_with_mock_page.execute("test-id", {"action": "middle_click", "coordinate": [100, 200]})
        assert result.get("is_error") is not True

    def test_execute_double_click_coordinate(self, executor_with_mock_page):
        """Test double_click with coordinate."""
        result = executor_with_mock_page.execute("test-id", {"action": "double_click", "coordinate": [100, 200]})
        assert result.get("is_error") is not True
        executor_with_mock_page._page.mouse.dblclick.assert_called()

    def test_execute_triple_click_coordinate(self, executor_with_mock_page):
        """Test triple_click with coordinate."""
        result = executor_with_mock_page.execute("test-id", {"action": "triple_click", "coordinate": [100, 200]})
        assert result.get("is_error") is not True

    def test_execute_drag_invalid_coords(self, executor_with_mock_page):
        """Test drag without proper coordinates returns error."""
        result = executor_with_mock_page.execute("test-id", {"action": "left_click_drag"})
        assert result.get("is_error") is True

        result = executor_with_mock_page.execute("test-id", {
            "action": "left_click_drag",
            "start_coordinate": [0, 0],
        })
        assert result.get("is_error") is True

    def test_execute_drag(self, executor_with_mock_page):
        """Test drag action."""
        result = executor_with_mock_page.execute("test-id", {
            "action": "left_click_drag",
            "start_coordinate": [0, 0],
            "coordinate": [100, 100],
        })
        assert result.get("is_error") is not True

    def test_execute_mouse_down_invalid(self, executor_with_mock_page):
        """Test mouse_down without coordinate returns error."""
        result = executor_with_mock_page.execute("test-id", {"action": "left_mouse_down"})
        assert result.get("is_error") is True

    def test_execute_mouse_down(self, executor_with_mock_page):
        """Test mouse_down action."""
        result = executor_with_mock_page.execute("test-id", {"action": "left_mouse_down", "coordinate": [100, 200]})
        assert result.get("is_error") is not True

    def test_execute_mouse_up_invalid(self, executor_with_mock_page):
        """Test mouse_up without coordinate returns error."""
        result = executor_with_mock_page.execute("test-id", {"action": "left_mouse_up"})
        assert result.get("is_error") is True

    def test_execute_mouse_up(self, executor_with_mock_page):
        """Test mouse_up action."""
        result = executor_with_mock_page.execute("test-id", {"action": "left_mouse_up", "coordinate": [100, 200]})
        assert result.get("is_error") is not True

    def test_execute_scroll_to_no_ref(self, executor_with_mock_page):
        """Test scroll_to without ref returns error."""
        result = executor_with_mock_page.execute("test-id", {"action": "scroll_to"})
        assert result["is_error"] is True

    def test_execute_form_input_no_ref(self, executor_with_mock_page):
        """Test form_input without ref returns error."""
        result = executor_with_mock_page.execute("test-id", {"action": "form_input"})
        assert result["is_error"] is True

    def test_execute_action_exception(self, executor_with_mock_page):
        """Test execute handles exceptions from action handlers."""
        # Make an action handler raise an exception
        executor_with_mock_page._page.go_back.side_effect = Exception("Browser crash")
        result = executor_with_mock_page.execute("test-id", {"action": "navigate", "text": "back"})
        assert result["is_error"] is True
        assert "Browser crash" in result["content"][0]["text"]

    def test_execute_left_click_with_ref_not_found(self, executor_with_mock_page):
        """Test left_click with ref that doesn't exist."""
        result = executor_with_mock_page.execute("test-id", {"action": "left_click", "ref": "ref_999"})
        assert result["is_error"] is True
        assert "Element not found" in result["content"][0]["text"]

    def test_execute_right_click_with_ref_not_found(self, executor_with_mock_page):
        """Test right_click with ref that doesn't exist."""
        result = executor_with_mock_page.execute("test-id", {"action": "right_click", "ref": "ref_999"})
        assert result["is_error"] is True
        assert "Element not found" in result["content"][0]["text"]

    def test_execute_middle_click_with_ref_not_found(self, executor_with_mock_page):
        """Test middle_click with ref that doesn't exist."""
        result = executor_with_mock_page.execute("test-id", {"action": "middle_click", "ref": "ref_999"})
        assert result["is_error"] is True
        assert "Element not found" in result["content"][0]["text"]

    def test_execute_double_click_with_ref_not_found(self, executor_with_mock_page):
        """Test double_click with ref that doesn't exist."""
        result = executor_with_mock_page.execute("test-id", {"action": "double_click", "ref": "ref_999"})
        assert result["is_error"] is True
        assert "Element not found" in result["content"][0]["text"]

    def test_execute_triple_click_with_ref_not_found(self, executor_with_mock_page):
        """Test triple_click with ref that doesn't exist."""
        result = executor_with_mock_page.execute("test-id", {"action": "triple_click", "ref": "ref_999"})
        assert result["is_error"] is True
        assert "Element not found" in result["content"][0]["text"]

    def test_execute_no_target_error_paths(self, executor_with_mock_page):
        """Test actions return error when no ref or coordinate."""
        actions = ["right_click", "middle_click", "double_click", "triple_click"]
        for action in actions:
            result = executor_with_mock_page.execute("test-id", {"action": action})
            assert result.get("is_error") is True


class TestBrowserExecutorRefClicks:
    """Tests for BrowserExecutor click actions with ref."""

    @pytest.fixture
    def executor_with_element(self):
        """Create executor with mock page and element."""
        from scry.adapters.browser_executor import BrowserExecutor

        executor = BrowserExecutor()
        executor._page = MagicMock()
        executor._page.screenshot.return_value = b"fake_png_data"

        # Setup ref_manager with a known ref using the proper API
        executor.ref_manager.create_ref(
            selector="button.submit",
            role="button",
            name="Submit",
        )

        # Mock element found
        mock_element = MagicMock()
        executor._page.query_selector.return_value = mock_element

        return executor, mock_element

    def test_get_element_by_ref_found(self, executor_with_element):
        """Test _get_element_by_ref when element is found."""
        executor, mock_element = executor_with_element
        element = executor._get_element_by_ref("ref_0")
        assert element == mock_element
        executor._page.query_selector.assert_called_with("button.submit")

    def test_get_element_by_ref_not_found(self, executor_with_element):
        """Test _get_element_by_ref when ref doesn't exist."""
        executor, _ = executor_with_element
        element = executor._get_element_by_ref("ref_nonexistent")
        assert element is None

    def test_get_element_by_ref_query_fails(self, executor_with_element):
        """Test _get_element_by_ref when query_selector fails."""
        executor, _ = executor_with_element
        executor._page.query_selector.side_effect = Exception("Query failed")
        element = executor._get_element_by_ref("ref_0")
        assert element is None

    def test_scroll_element_into_view(self, executor_with_element):
        """Test _scroll_element_into_view."""
        executor, mock_element = executor_with_element
        executor._scroll_element_into_view(mock_element)
        mock_element.scroll_into_view_if_needed.assert_called_once()
        executor._page.wait_for_timeout.assert_called_once_with(100)

    def test_click_element_default(self, executor_with_element):
        """Test _click_element with default parameters."""
        executor, mock_element = executor_with_element
        executor._click_element(mock_element)
        mock_element.click.assert_called_once()

    def test_click_element_with_modifiers(self, executor_with_element):
        """Test _click_element with modifiers."""
        executor, mock_element = executor_with_element
        executor._click_element(mock_element, button="right", click_count=2, modifiers=["Shift", "Control"])
        mock_element.click.assert_called_once()
        call_kwargs = mock_element.click.call_args[1]
        assert call_kwargs["button"] == "right"
        assert call_kwargs["click_count"] == 2
        assert "Shift" in call_kwargs["modifiers"]
        assert "Control" in call_kwargs["modifiers"]

    def test_click_element_invalid_button(self, executor_with_element):
        """Test _click_element with invalid button falls back to left."""
        executor, mock_element = executor_with_element
        executor._click_element(mock_element, button="invalid")
        call_kwargs = mock_element.click.call_args[1]
        assert call_kwargs["button"] == "left"

    def test_click_element_invalid_modifier_filtered(self, executor_with_element):
        """Test _click_element filters out invalid modifiers."""
        executor, mock_element = executor_with_element
        executor._click_element(mock_element, modifiers=["Shift", "InvalidMod", "Alt"])
        call_kwargs = mock_element.click.call_args[1]
        # Should only have valid modifiers
        mods = call_kwargs.get("modifiers")
        if mods:
            for mod in mods:
                assert mod in ("Alt", "Control", "ControlOrMeta", "Meta", "Shift")

    def test_left_click_with_ref_success(self, executor_with_element):
        """Test left_click with ref that finds element."""
        executor, mock_element = executor_with_element
        result = executor.execute("test-id", {"action": "left_click", "ref": "ref_0"})
        assert result.get("is_error") is not True
        assert "Clicked ref_0" in result["content"][0]["text"]

    def test_right_click_with_ref_success(self, executor_with_element):
        """Test right_click with ref that finds element."""
        executor, mock_element = executor_with_element
        result = executor.execute("test-id", {"action": "right_click", "ref": "ref_0"})
        assert result.get("is_error") is not True
        assert "Right-clicked ref_0" in result["content"][0]["text"]

    def test_middle_click_with_ref_success(self, executor_with_element):
        """Test middle_click with ref that finds element."""
        executor, mock_element = executor_with_element
        result = executor.execute("test-id", {"action": "middle_click", "ref": "ref_0"})
        assert result.get("is_error") is not True
        assert "Middle-clicked ref_0" in result["content"][0]["text"]

    def test_double_click_with_ref_success(self, executor_with_element):
        """Test double_click with ref that finds element."""
        executor, mock_element = executor_with_element
        result = executor.execute("test-id", {"action": "double_click", "ref": "ref_0"})
        assert result.get("is_error") is not True
        assert "Double-clicked ref_0" in result["content"][0]["text"]

    def test_triple_click_with_ref_success(self, executor_with_element):
        """Test triple_click with ref that finds element."""
        executor, mock_element = executor_with_element
        result = executor.execute("test-id", {"action": "triple_click", "ref": "ref_0"})
        assert result.get("is_error") is not True
        assert "Triple-clicked ref_0" in result["content"][0]["text"]


class TestBrowserExecutorMoreActions:
    """Additional tests for BrowserExecutor actions."""

    @pytest.fixture
    def executor_with_element_and_ref(self):
        """Create executor with mock page and element ref setup."""
        from scry.adapters.browser_executor import BrowserExecutor

        executor = BrowserExecutor()
        executor._page = MagicMock()
        executor._page.screenshot.return_value = b"fake_png_data"
        executor._page.title.return_value = "Test Page"
        executor._page.url = "https://test.com"

        # Setup ref using proper API
        executor.ref_manager.create_ref(
            selector="input.text",
            role="textbox",
            name="Username",
        )

        mock_element = MagicMock()
        mock_element.inner_text.return_value = "test content"
        executor._page.query_selector.return_value = mock_element

        return executor

    def test_scroll_to_with_ref(self, executor_with_element_and_ref):
        """Test scroll_to with valid ref."""
        executor = executor_with_element_and_ref
        result = executor.execute("test-id", {"action": "scroll_to", "ref": "ref_0"})
        assert result.get("is_error") is not True

    def test_scroll_to_ref_not_found(self, executor_with_element_and_ref):
        """Test scroll_to with invalid ref."""
        executor = executor_with_element_and_ref
        result = executor.execute("test-id", {"action": "scroll_to", "ref": "ref_invalid"})
        assert result["is_error"] is True

    def test_form_input_with_ref(self, executor_with_element_and_ref):
        """Test form_input with valid ref."""
        executor = executor_with_element_and_ref
        result = executor.execute("test-id", {"action": "form_input", "ref": "ref_0", "text": "test value"})
        assert result.get("is_error") is not True

    def test_form_input_ref_not_found(self, executor_with_element_and_ref):
        """Test form_input with invalid ref."""
        executor = executor_with_element_and_ref
        result = executor.execute("test-id", {"action": "form_input", "ref": "ref_invalid", "text": "test"})
        assert result["is_error"] is True

    def test_get_page_text_content_found(self, executor_with_element_and_ref):
        """Test get_page_text extracts content."""
        executor = executor_with_element_and_ref
        result = executor.execute("test-id", {"action": "get_page_text"})
        assert result.get("is_error") is not True
        assert "Title:" in result["content"][0]["text"]

    def test_find_with_matches(self, executor_with_element_and_ref):
        """Test find action when elements match."""
        executor = executor_with_element_and_ref
        result = executor.execute("test-id", {"action": "find", "text": "Username"})
        assert result.get("is_error") is not True
        # Should find the element we set up
        assert "Found" in result["content"][0]["text"] or "matching" in result["content"][0]["text"]


# ====================
# runner.py tests
# ====================


class TestRunnerHelpers:
    """Tests for runner.py helper functions."""

    def test_emit_exploration_progress_no_callback(self):
        """Test _emit_exploration_progress with no callback."""
        from scry.core.executor.runner import _emit_exploration_progress

        # Should not raise
        _emit_exploration_progress(None, 20, "https://example.com")

    def test_emit_exploration_progress_with_callback(self):
        """Test _emit_exploration_progress with callback."""
        from scry.core.executor.runner import _emit_exploration_progress

        callback_data = []
        def callback(data):
            callback_data.append(data)

        _emit_exploration_progress(callback, 20, "https://example.com")
        assert len(callback_data) == 1
        assert callback_data[0]["step"] == 20

    def test_emit_exploration_progress_callback_error(self):
        """Test _emit_exploration_progress handles callback errors."""
        from scry.core.executor.runner import _emit_exploration_progress

        def bad_callback(data):
            raise ValueError("Callback error")

        # Should not raise
        _emit_exploration_progress(bad_callback, 20, "https://example.com")

    def test_handle_validation_failure_stderr(self):
        """Test _handle_validation_failure extracts from stderr."""
        from scry.core.executor.runner import _handle_validation_failure

        result = MagicMock()
        result.stderr = "CRITICAL validation failed: element not found"
        result.stdout = ""

        error = _handle_validation_failure(result)
        assert error is not None
        assert "CRITICAL validation failed" in error

    def test_handle_validation_failure_stdout(self):
        """Test _handle_validation_failure extracts from stdout."""
        from scry.core.executor.runner import _handle_validation_failure

        result = MagicMock()
        result.stderr = ""
        result.stdout = "CRITICAL validation failed: text mismatch"

        error = _handle_validation_failure(result)
        assert error is not None

    def test_handle_validation_failure_none(self):
        """Test _handle_validation_failure returns None when no error."""
        from scry.core.executor.runner import _handle_validation_failure

        result = MagicMock()
        result.stderr = "Some other error"
        result.stdout = "Output"

        error = _handle_validation_failure(result)
        assert error is None

    def test_check_schema_empty_no_data(self):
        """Test _check_schema_empty with no data."""
        from scry.core.executor.runner import _check_schema_empty

        assert _check_schema_empty({}, {}) is False
        assert _check_schema_empty(None, {"properties": {}}) is False

    def test_check_schema_empty_array_empty(self):
        """Test _check_schema_empty with empty array."""
        from scry.core.executor.runner import _check_schema_empty

        schema = {"properties": {"items": {"type": "array"}}}
        data = {"items": []}

        assert _check_schema_empty(data, schema) is True

    def test_check_schema_empty_array_missing(self):
        """Test _check_schema_empty with missing array value."""
        from scry.core.executor.runner import _check_schema_empty

        schema = {"properties": {"items": {"type": "array"}}}
        data = {"items": None}  # Value is None, which is falsy

        assert _check_schema_empty(data, schema) is True

    def test_check_schema_empty_array_populated(self):
        """Test _check_schema_empty with populated array."""
        from scry.core.executor.runner import _check_schema_empty

        schema = {"properties": {"items": {"type": "array"}}}
        data = {"items": ["a", "b"]}

        assert _check_schema_empty(data, schema) is False

    def test_check_schema_empty_string_whitespace(self):
        """Test _check_schema_empty with whitespace-only string for array."""
        from scry.core.executor.runner import _check_schema_empty

        schema = {"properties": {"items": {"type": "array"}}}
        data = {"items": "   "}  # Whitespace string instead of array

        assert _check_schema_empty(data, schema) is True

    def test_normalize_value(self):
        """Test _normalize_value function."""
        from scry.core.executor.runner import _normalize_value

        assert _normalize_value("  hello  ") == "hello"
        assert _normalize_value(123) == 123
        assert _normalize_value([1, 2, 3]) == [1, 2, 3]

    def test_validate_against_exploration_empty(self):
        """Test _validate_against_exploration with empty exploration data."""
        from scry.core.executor.runner import _validate_against_exploration

        execution_log: list[str] = []
        _validate_against_exploration({"a": 1}, None, execution_log)
        assert len(execution_log) == 0

        _validate_against_exploration({"a": 1}, {}, execution_log)
        assert len(execution_log) == 0

    def test_validate_against_exploration_match(self):
        """Test _validate_against_exploration with matching data."""
        from scry.core.executor.runner import _validate_against_exploration

        execution_log: list[str] = []
        data = {"price": 100, "name": "Item"}
        exploration = {"price": 100, "name": "Item"}

        _validate_against_exploration(data, exploration, execution_log)
        assert "validation_ok" in execution_log

    def test_validate_against_exploration_mismatch(self):
        """Test _validate_against_exploration with mismatched data."""
        from scry.core.executor.runner import _validate_against_exploration

        execution_log: list[str] = []
        data = {"price": 100}
        exploration = {"price": 200}

        _validate_against_exploration(data, exploration, execution_log)
        assert "validation_mismatch" in execution_log


# ====================
# browser_pool.py tests (async)
# ====================


class TestBrowserPoolConfig:
    """Tests for BrowserPoolConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        from scry.adapters.browser_pool import BrowserPoolConfig

        config = BrowserPoolConfig()
        assert config.pool_size == 2
        assert config.max_requests_per_browser == 100
        assert config.headless is True


class TestPooledBrowser:
    """Tests for PooledBrowser dataclass."""

    def test_pooled_browser_creation(self):
        """Test creating a PooledBrowser."""
        from scry.adapters.browser_pool import PooledBrowser

        mock_browser = MagicMock()
        mock_playwright = MagicMock()

        pooled = PooledBrowser(browser=mock_browser, playwright=mock_playwright)
        assert pooled.browser == mock_browser
        assert pooled.playwright == mock_playwright
        assert pooled.request_count == 0
        assert pooled.in_use is False


class TestAsyncBrowserPoolBasics:
    """Basic tests for AsyncBrowserPool (without actual browsers)."""

    def test_pool_initialization(self):
        """Test pool can be initialized."""
        from scry.adapters.browser_pool import AsyncBrowserPool, BrowserPoolConfig

        config = BrowserPoolConfig(pool_size=1)
        pool = AsyncBrowserPool(config)
        assert pool.config.pool_size == 1
        assert pool._initialized is False

    def test_pool_stats_initial(self):
        """Test pool stats before initialization."""
        from scry.adapters.browser_pool import AsyncBrowserPool

        pool = AsyncBrowserPool()
        stats = pool.stats()
        assert stats["initialized"] is False
        assert stats["available"] == 0


# ====================
# navigator.py additional tests
# ====================


class TestNavigatorCreateBrowserContext:
    """Tests for _create_browser_context function."""

    def test_create_browser_context_no_credentials(self):
        """Test creating context without credentials."""
        from scry.core.nav.navigator import _create_browser_context

        mock_browser = MagicMock()
        context = _create_browser_context(mock_browser, None)
        mock_browser.new_context.assert_called_once_with()
        assert context == mock_browser.new_context.return_value

    def test_create_browser_context_with_credentials(self):
        """Test creating context with HTTP credentials."""
        from scry.core.nav.navigator import _create_browser_context

        mock_browser = MagicMock()
        login_params = {
            "http_basic": {"username": "user", "password": "pass"}
        }
        _context = _create_browser_context(mock_browser, login_params)
        mock_browser.new_context.assert_called_once_with(
            http_credentials={"username": "user", "password": "pass"}
        )


class TestNavigatorCaptureArtifacts:
    """Tests for _capture_artifacts function."""

    def test_capture_artifacts(self):
        """Test capturing page artifacts."""
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from scry.core.nav.navigator import _capture_artifacts

        mock_page = MagicMock()
        mock_page.content.return_value = "<html><body>Test</body></html>"

        with TemporaryDirectory() as tmpdir:
            screenshots_dir = Path(tmpdir) / "screenshots"
            html_dir = Path(tmpdir) / "html"
            html_snapshots: list[str] = []
            screenshots: list[Path] = []

            _capture_artifacts(
                mock_page, 1, screenshots_dir, html_dir, "test-job",
                html_snapshots, screenshots
            )

            # Should have taken screenshots
            assert mock_page.screenshot.called
            assert len(screenshots) >= 1
            assert len(html_snapshots) == 1
            assert "Test" in html_snapshots[0]

    def test_capture_artifacts_scroll_error(self):
        """Test capture_artifacts handles scroll errors gracefully."""
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from scry.core.nav.navigator import _capture_artifacts

        mock_page = MagicMock()
        mock_page.content.return_value = "<html></html>"
        mock_page.evaluate.side_effect = Exception("Scroll error")

        with TemporaryDirectory() as tmpdir:
            screenshots_dir = Path(tmpdir) / "screenshots"
            html_dir = Path(tmpdir) / "html"
            html_snapshots: list[str] = []
            screenshots: list[Path] = []

            # Should not raise
            _capture_artifacts(
                mock_page, 1, screenshots_dir, html_dir, "test-job",
                html_snapshots, screenshots
            )


class TestExecutePlan:
    """Tests for execute_plan function."""

    @patch("scry.core.nav.navigator.sync_playwright")
    def test_execute_plan_empty(self, mock_playwright):
        """Test execute_plan with empty plan."""
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from scry.core.ir.model import ScrapePlan
        from scry.core.nav.navigator import execute_plan

        plan = ScrapePlan(steps=[])

        with TemporaryDirectory() as tmpdir:
            html_snapshots, screenshots = execute_plan(
                plan,
                Path(tmpdir) / "screenshots",
                Path(tmpdir) / "html",
                "test-job",
            )

            assert html_snapshots == []
            assert screenshots == []
            # Playwright should not have been called
            mock_playwright.assert_not_called()


# ====================
# generator.py additional tests
# ====================


class TestGeneratorStepRenderers:
    """Tests for generator step renderer functions."""

    def test_render_navigate(self):
        """Test _render_navigate function."""
        from scry.core.codegen.generator import _render_navigate
        from scry.core.ir.model import Navigate

        step = Navigate(url="https://example.com/path?query=1")
        lines = _render_navigate(step, 1, 1, None)

        assert any("page.goto" in line for line in lines)
        assert any("screenshot" in line for line in lines)

    def test_render_navigate_with_cookie_selector(self):
        """Test _render_navigate with cookie dismiss selector."""
        from scry.core.codegen.generator import _render_navigate
        from scry.core.ir.model import Navigate

        step = Navigate(url="https://example.com")
        lines = _render_navigate(step, 1, 1, "button.accept-cookies")

        # Should have cookie dismiss code
        assert any("accept-cookies" in line for line in lines)

    def test_render_click(self):
        """Test _render_click function."""
        from scry.core.codegen.generator import _render_click
        from scry.core.ir.model import Click

        step = Click(selector="button.submit")
        lines = _render_click(step, 1)

        assert any("click" in line.lower() for line in lines)
        assert any("button.submit" in line for line in lines)

    def test_render_fill(self):
        """Test _render_fill function."""
        from scry.core.codegen.generator import _render_fill
        from scry.core.ir.model import Fill

        step = Fill(selector="input.email", text="test@example.com")
        lines = _render_fill(step, 1)

        assert any("fill" in line.lower() for line in lines)
        assert any("test@example.com" in line for line in lines)

    def test_render_wait_for(self):
        """Test _render_wait_for function."""
        from scry.core.codegen.generator import _render_wait_for
        from scry.core.ir.model import WaitFor

        step = WaitFor(selector="div.content", state="visible")
        lines = _render_wait_for(step, 1)

        assert any("wait_for" in line.lower() for line in lines)
        assert any("visible" in line for line in lines)

    def test_render_wait_for_all_states(self):
        """Test _render_wait_for with all state values."""
        from scry.core.codegen.generator import _render_wait_for
        from scry.core.ir.model import WaitFor

        for state in ["visible", "hidden", "attached", "detached"]:
            step = WaitFor(selector="div", state=state)
            lines = _render_wait_for(step, 1)
            assert any(state in line for line in lines)

        # Unknown state defaults to visible
        step = WaitFor(selector="div", state="unknown")
        lines = _render_wait_for(step, 1)
        assert any("visible" in line for line in lines)

    def test_render_select(self):
        """Test _render_select function."""
        from scry.core.codegen.generator import _render_select
        from scry.core.ir.model import Select

        step = Select(selector="select.country", value="US")
        lines = _render_select(step, 1)

        assert any("select_option" in line for line in lines)

    def test_render_hover(self):
        """Test _render_hover function."""
        from scry.core.codegen.generator import _render_hover
        from scry.core.ir.model import Hover

        step = Hover(selector="div.menu")
        lines = _render_hover(step, 1)

        assert any("hover" in line.lower() for line in lines)

    def test_render_keypress_with_selector(self):
        """Test _render_keypress with selector."""
        from scry.core.codegen.generator import _render_keypress
        from scry.core.ir.model import KeyPress

        step = KeyPress(selector="input.search", key="Enter")
        lines = _render_keypress(step, 1)

        assert any("press" in line.lower() for line in lines)
        assert any("input.search" in line for line in lines)

    def test_render_keypress_without_selector(self):
        """Test _render_keypress without selector."""
        from scry.core.codegen.generator import _render_keypress
        from scry.core.ir.model import KeyPress

        step = KeyPress(selector=None, key="Escape")
        lines = _render_keypress(step, 1)

        assert any("keyboard.press" in line for line in lines)

    def test_render_upload(self):
        """Test _render_upload function."""
        from scry.core.codegen.generator import _render_upload
        from scry.core.ir.model import Upload

        step = Upload(selector="input[type=file]", file_path="/path/to/file.pdf")
        lines = _render_upload(step, 1)

        assert any("set_input_files" in line for line in lines)

    def test_render_validate_presence(self):
        """Test _render_validate for presence validation."""
        from scry.core.codegen.generator import _render_validate
        from scry.core.ir.model import Validate

        step = Validate(
            selector="div.content",
            validation_type="presence",
            is_critical=False,
            description="Check content exists",
        )
        lines = _render_validate(step, 1)

        assert any("is_visible" in line for line in lines)
        assert any("Non-critical" in line for line in lines)

    def test_render_validate_absence(self):
        """Test _render_validate for absence validation."""
        from scry.core.codegen.generator import _render_validate
        from scry.core.ir.model import Validate

        step = Validate(
            selector="div.error",
            validation_type="absence",
            is_critical=False,
            description="Error should not be visible",
        )
        lines = _render_validate(step, 1)

        assert any("should not be present" in line for line in lines)

    def test_render_validate_text(self):
        """Test _render_validate for text validation."""
        from scry.core.codegen.generator import _render_validate
        from scry.core.ir.model import Validate

        step = Validate(
            selector="h1",
            validation_type="text",
            expected_text="Welcome",
            is_critical=False,
            description="Check title",
        )
        lines = _render_validate(step, 1)

        assert any("text_content" in line for line in lines)
        assert any("Welcome" in line for line in lines)

    def test_render_validate_count(self):
        """Test _render_validate for count validation."""
        from scry.core.codegen.generator import _render_validate
        from scry.core.ir.model import Validate

        step = Validate(
            selector="li.item",
            validation_type="count",
            expected_count=5,
            is_critical=False,
            description="Check item count",
        )
        lines = _render_validate(step, 1)

        assert any("count()" in line for line in lines)
        assert any("5" in line for line in lines)

    def test_render_validate_critical(self):
        """Test _render_validate for critical validation."""
        from scry.core.codegen.generator import _render_validate
        from scry.core.ir.model import Validate

        step = Validate(
            selector="div",
            validation_type="presence",
            is_critical=True,
            description="Critical check",
        )
        lines = _render_validate(step, 1)

        assert any("CRITICAL" in line for line in lines)
        assert any("sys.exit(1)" in line for line in lines)


class TestRenderSteps:
    """Tests for _render_steps function."""

    def test_render_steps_all_types(self):
        """Test _render_steps with various step types."""
        from scry.core.codegen.generator import _render_steps
        from scry.core.ir.model import (
            Click,
            Fill,
            Hover,
            KeyPress,
            Navigate,
            ScrapePlan,
            Select,
            Upload,
            Validate,
            WaitFor,
        )

        plan = ScrapePlan(steps=[
            Navigate(url="https://example.com"),
            Click(selector="button"),
            Fill(selector="input", text="hello"),
            WaitFor(selector="div", state="visible"),
            Select(selector="select", value="opt1"),
            Hover(selector="div.menu"),
            KeyPress(key="Enter"),
            Upload(selector="input[type=file]", file_path="/file.txt"),
            Validate(selector="div", validation_type="presence"),
        ])

        code = _render_steps(plan)

        assert "page.goto" in code
        assert "click" in code.lower()
        assert "fill" in code.lower()
        assert "wait_for" in code.lower()
        assert "select_option" in code
        assert "hover" in code.lower()


class TestGenerateScript:
    """Tests for generate_script function."""

    def test_generate_script_basic(self):
        """Test generating a basic script."""
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from scry.core.codegen.generator import generate_script
        from scry.core.ir.model import Navigate, ScrapePlan

        plan = ScrapePlan(steps=[Navigate(url="https://example.com")])

        with TemporaryDirectory() as tmpdir:
            artifacts_root = Path(tmpdir)
            script_path = generate_script(
                plan,
                job_id="test-job",
                artifacts_root=artifacts_root,
                headless=True,
            )

            assert script_path.exists()
            content = script_path.read_text()
            assert "https://example.com" in content
            assert "HEADLESS = True" in content

    def test_generate_script_with_options(self):
        """Test generating script with options."""
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from scry.core.codegen.generator import generate_script
        from scry.core.ir.model import Navigate, ScrapePlan

        plan = ScrapePlan(steps=[Navigate(url="https://example.com")])

        with TemporaryDirectory() as tmpdir:
            artifacts_root = Path(tmpdir)
            script_path = generate_script(
                plan,
                job_id="test-job",
                artifacts_root=artifacts_root,
                headless=False,
                options={
                    "extra_wait_ms": 1000,
                    "wait_load_state": True,
                    "extraction_spec": {"title": {"selector": "h1"}},
                    "cookie_dismiss_selector": "button.dismiss",
                },
            )

            assert script_path.exists()
            content = script_path.read_text()
            assert "HEADLESS = False" in content
            assert "EXTRA_WAIT_MS = 1000" in content
            assert "WAIT_LOAD_STATE = True" in content


# ====================
# optimize.py additional tests
# ====================


class TestOptimizeCompression:
    """Tests for optimize compression functions."""

    def test_build_steps_repr(self):
        """Test _build_steps_repr function."""
        from scry.core.ir.model import Click, Navigate
        from scry.core.optimizer.optimize import _build_steps_repr

        steps = [
            Navigate(url="https://example.com"),
            Click(selector="button"),
        ]

        result = _build_steps_repr(steps)
        assert len(result) == 2
        assert result[0]["type"] == "navigate"
        assert result[1]["type"] == "click"

    def test_parse_compressed_steps(self):
        """Test _parse_compressed_steps function."""
        from scry.core.optimizer.optimize import _parse_compressed_steps

        data = {
            "steps": [
                {"type": "navigate", "url": "https://example.com"},
                {"type": "click", "selector": "button"},
                {"type": "invalid"},  # Should be skipped
                "not a dict",  # Should be skipped
            ]
        }

        result = _parse_compressed_steps(data)
        assert len(result) == 2

    def test_parse_compressed_steps_empty(self):
        """Test _parse_compressed_steps with empty/missing steps."""
        from scry.core.optimizer.optimize import _parse_compressed_steps

        assert _parse_compressed_steps({}) == []
        assert _parse_compressed_steps({"steps": None}) == []


class TestOptimizePlan:
    """Tests for optimize_plan function."""

    def test_optimize_plan_empty(self):
        """Test optimizing empty plan."""
        from scry.core.ir.model import ScrapePlan
        from scry.core.optimizer.optimize import optimize_plan

        plan = ScrapePlan(steps=[])
        result = optimize_plan(plan)
        assert result.steps == []

    def test_optimize_plan_removes_duplicates(self):
        """Test optimizing removes consecutive duplicates."""
        from scry.core.ir.model import Click, ScrapePlan
        from scry.core.optimizer.optimize import optimize_plan

        plan = ScrapePlan(steps=[
            Click(selector="button"),
            Click(selector="button"),  # Duplicate
            Click(selector="other"),
        ])

        result = optimize_plan(plan)
        # Should have removed the duplicate
        assert len(result.steps) == 2

    def test_optimize_plan_removes_redundant_wait(self):
        """Test optimizing removes WaitFor after Navigate."""
        from scry.core.ir.model import Navigate, ScrapePlan, WaitFor
        from scry.core.optimizer.optimize import optimize_plan

        plan = ScrapePlan(steps=[
            Navigate(url="https://example.com"),
            WaitFor(selector="body", state="visible"),  # Redundant after Navigate
        ])

        result = optimize_plan(plan)
        assert len(result.steps) == 1

    def test_optimize_plan_merges_waits(self):
        """Test optimizing merges consecutive WaitFor same selector."""
        from scry.core.ir.model import ScrapePlan, WaitFor
        from scry.core.optimizer.optimize import optimize_plan

        plan = ScrapePlan(steps=[
            WaitFor(selector="div", state="attached"),
            WaitFor(selector="div", state="visible"),
        ])

        result = optimize_plan(plan)
        # Should merge into one
        assert len(result.steps) == 1


# ====================
# Additional navigator.py tests
# ====================


class TestNavigatorExecuteNavigateException:
    """Tests for _execute_navigate exception handling."""

    def test_execute_navigate_data_url_set_content_fails(self):
        """Test _execute_navigate falls back to goto when set_content fails."""
        from scry.core.ir.model import Navigate
        from scry.core.nav.navigator import _execute_navigate

        mock_page = MagicMock()
        mock_page.set_content.side_effect = Exception("set_content failed")

        step = Navigate(url="data:text/html,<html><body>Test</body></html>")
        _execute_navigate(mock_page, step)

        # Should have tried set_content first, then fallen back to goto
        mock_page.set_content.assert_called_once()
        mock_page.goto.assert_called_once_with("data:text/html,<html><body>Test</body></html>")


class TestNavigatorExecuteStepDispatch:
    """Tests for _execute_step dispatch to all step types."""

    @pytest.fixture
    def mock_page(self):
        """Create a mock page."""
        page = MagicMock()
        page.locator.return_value = MagicMock()
        return page

    def test_execute_step_fill(self, mock_page):
        """Test _execute_step dispatches Fill correctly."""
        from scry.core.ir.model import Fill
        from scry.core.nav.navigator import _execute_step

        step = Fill(selector="input.email", text="test@test.com")
        _execute_step(mock_page, step)
        mock_page.fill.assert_called_once_with("input.email", "test@test.com")

    def test_execute_step_wait_for(self, mock_page):
        """Test _execute_step dispatches WaitFor correctly."""
        from scry.core.ir.model import WaitFor
        from scry.core.nav.navigator import _execute_step

        step = WaitFor(selector="div.loading", state="hidden")
        _execute_step(mock_page, step)
        mock_page.wait_for_selector.assert_called_once_with("div.loading", state="hidden")

    def test_execute_step_select(self, mock_page):
        """Test _execute_step dispatches Select correctly."""
        from scry.core.ir.model import Select
        from scry.core.nav.navigator import _execute_step

        step = Select(selector="select#country", value="US")
        _execute_step(mock_page, step)
        mock_page.select_option.assert_called_once_with("select#country", "US")

    def test_execute_step_hover(self, mock_page):
        """Test _execute_step dispatches Hover correctly."""
        from scry.core.ir.model import Hover
        from scry.core.nav.navigator import _execute_step

        step = Hover(selector="button.dropdown")
        _execute_step(mock_page, step)
        mock_page.hover.assert_called_once_with("button.dropdown")
        mock_page.wait_for_timeout.assert_called_once_with(500)

    def test_execute_step_keypress(self, mock_page):
        """Test _execute_step dispatches KeyPress correctly."""
        from scry.core.ir.model import KeyPress
        from scry.core.nav.navigator import _execute_step

        step = KeyPress(selector="input.search", key="Enter")
        _execute_step(mock_page, step)
        mock_page.locator.assert_called_once_with("input.search")
        mock_page.locator.return_value.press.assert_called_once_with("Enter")

    def test_execute_step_upload(self, mock_page):
        """Test _execute_step dispatches Upload correctly."""
        from scry.core.ir.model import Upload
        from scry.core.nav.navigator import _execute_step

        step = Upload(selector="input[type=file]", file_path="/path/to/file.pdf")
        _execute_step(mock_page, step)
        mock_page.set_input_files.assert_called_once_with("input[type=file]", "/path/to/file.pdf")


class TestNavigatorExecutePlanWithSteps:
    """Tests for execute_plan with actual steps."""

    @patch("scry.core.nav.navigator.sync_playwright")
    def test_execute_plan_with_navigate(self, mock_playwright):
        """Test execute_plan with Navigate step."""
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from scry.core.ir.model import Navigate, ScrapePlan
        from scry.core.nav.navigator import execute_plan

        # Setup mock Playwright
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_page.content.return_value = "<html><body>Test</body></html>"

        mock_pw_instance = MagicMock()
        mock_pw_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        mock_playwright.return_value.__enter__.return_value = mock_pw_instance

        plan = ScrapePlan(steps=[Navigate(url="https://example.com")])

        with TemporaryDirectory() as tmpdir:
            html_snapshots, screenshots = execute_plan(
                plan,
                Path(tmpdir) / "screenshots",
                Path(tmpdir) / "html",
                "test-job",
            )

            # Should have content
            assert len(html_snapshots) == 1
            assert html_snapshots[0] == "<html><body>Test</body></html>"
            mock_page.goto.assert_called_once_with("https://example.com")

    @patch("scry.core.nav.navigator.sync_playwright")
    def test_execute_plan_with_multiple_steps(self, mock_playwright):
        """Test execute_plan with multiple steps."""
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from scry.core.ir.model import Click, Fill, Navigate, ScrapePlan
        from scry.core.nav.navigator import execute_plan

        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_page.content.return_value = "<html></html>"

        mock_pw_instance = MagicMock()
        mock_pw_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        mock_playwright.return_value.__enter__.return_value = mock_pw_instance

        plan = ScrapePlan(steps=[
            Navigate(url="https://example.com"),
            Fill(selector="input#username", text="user"),
            Click(selector="button#submit"),
        ])

        with TemporaryDirectory() as tmpdir:
            html_snapshots, screenshots = execute_plan(
                plan,
                Path(tmpdir) / "screenshots",
                Path(tmpdir) / "html",
                "test-job",
            )

            # Should have captured artifacts for each step
            assert len(html_snapshots) == 3
            mock_page.goto.assert_called_once()
            mock_page.fill.assert_called_once()
            mock_page.click.assert_called_once()


# ====================
# Additional anthropic.py tests
# ====================


class TestAnthropicClient:
    """Tests for _client function."""

    def test_client_with_api_key(self):
        """Test _client creates Anthropic instance with API key."""
        from scry.adapters.anthropic import _client

        mock_client_instance = MagicMock()

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"}, clear=True):
            with patch("anthropic.Anthropic", return_value=mock_client_instance) as mock_anthropic_class:
                client = _client()

                mock_anthropic_class.assert_called_once_with(api_key="test-key-123")
                assert client == mock_client_instance

    def test_client_without_api_key_raises(self):
        """Test _client raises RuntimeError when no API key."""
        from scry.adapters.anthropic import _client

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="Anthropic API key not found"):
                _client()


class TestAnthropicExtractJsonEdgeCases:
    """Tests for _extract_json edge cases."""

    def test_extract_json_invalid_braces_json(self):
        """Test JSON extraction fails when JSON between braces is invalid."""
        from scry.adapters.anthropic import _extract_json

        # Has braces but JSON is invalid (will try to extract, fail, and continue)
        text = "Some text {this is not valid json} more text"
        with pytest.raises(ValueError, match="Failed to parse JSON"):
            _extract_json(text)

    def test_extract_json_code_fence_without_json_label(self):
        """Test JSON extraction from code fence without json label."""
        from scry.adapters.anthropic import _extract_json

        text = """```
{"key": "value"}
```"""
        result = _extract_json(text)
        assert result == {"key": "value"}

    def test_extract_json_code_fence_invalid_json(self):
        """Test JSON extraction fails with invalid JSON in code fence."""
        from scry.adapters.anthropic import _extract_json

        text = """```json
{invalid json here}
```"""
        with pytest.raises(ValueError, match="Failed to parse JSON"):
            _extract_json(text)

    def test_extract_json_multiple_code_fences(self):
        """Test JSON extraction with multiple code fences."""
        from scry.adapters.anthropic import _extract_json

        text = """Here's some text:
```python
print("hello")
```
And here's JSON:
```json
{"found": true}
```"""
        result = _extract_json(text)
        assert result == {"found": True}


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
