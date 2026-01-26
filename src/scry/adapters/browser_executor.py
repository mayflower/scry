"""Browser executor for Browser Tools API.

Executes browser actions requested by Claude through tool_use blocks.
Manages browser lifecycle, element interactions, and provides structured
tool_result responses.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any

from .dom_tree import DOMTreeGenerator
from .element_refs import ElementReferenceManager

if TYPE_CHECKING:
    from collections.abc import Sequence

    from playwright.sync_api import Browser, BrowserContext, ElementHandle, Page, Playwright

# Error message constants to avoid duplication
_ERR_REF_OR_COORD_REQUIRED = "Either ref or coordinate is required"
_ERR_COORD_FORMAT = "coordinate must be [x, y]"
_ERR_START_COORD_FORMAT = "start_coordinate must be [x, y]"


class BrowserExecutor:
    """Executes browser actions and manages browser state.

    This class encapsulates all Playwright interactions and provides
    a unified interface for the agent loop to execute browser actions.
    """

    def __init__(
        self,
        viewport_width: int = 1024,
        viewport_height: int = 768,
        headless: bool = True,
        slow_mo: int = 0,
    ):
        """Initialize browser executor.

        Args:
            viewport_width: Browser viewport width in pixels
            viewport_height: Browser viewport height in pixels
            headless: Whether to run browser in headless mode
            slow_mo: Milliseconds to slow down Playwright operations (for debugging)
        """
        self.viewport = {"width": viewport_width, "height": viewport_height}
        self.headless = headless
        self.slow_mo = slow_mo

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

        self.ref_manager = ElementReferenceManager()
        self.dom_generator: DOMTreeGenerator | None = None

    def start(self):
        """Start the browser (synchronous version)."""
        from playwright.sync_api import sync_playwright

        print("[BrowserExecutor] Starting browser...")

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless, slow_mo=self.slow_mo
        )
        self._context = self._browser.new_context(
            viewport={"width": self.viewport["width"], "height": self.viewport["height"]}  # type: ignore[arg-type]
        )
        self._page = self._context.new_page()

        # Initialize DOM generator
        self.dom_generator = DOMTreeGenerator(self._page, self.ref_manager)

        # Event listener for navigation
        self._page.on("load", lambda _: self._on_page_load())

        print(f"[BrowserExecutor] Browser started (viewport: {self.viewport})")

    def stop(self):
        """Stop the browser."""
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

        self._browser = None
        self._context = None
        self._page = None
        self._playwright = None

        print("[BrowserExecutor] Browser stopped")

    def _on_page_load(self):
        """Callback when page loads (for reference reset)."""
        if self._page:
            url = self._page.url
            self.ref_manager.on_navigation(url)
            print(f"[BrowserExecutor] Page loaded: {url}")

    @property
    def page(self) -> Page:
        """Get current page (raises if browser not started)."""
        if not self._page:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    def execute(self, tool_use_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Execute a browser action and return tool_result.

        Args:
            tool_use_id: ID from tool_use block
            input_data: Action parameters from Claude

        Returns:
            tool_result dictionary
        """
        action = input_data.get("action", "")

        # Map action names to handlers
        handlers = {
            "navigate": self._handle_navigate,
            "screenshot": self._handle_screenshot,
            "read_page": self._handle_read_page,
            "get_page_text": self._handle_get_page_text,
            "find": self._handle_find,
            "zoom": self._handle_zoom,
            "left_click": self._handle_left_click,
            "right_click": self._handle_right_click,
            "middle_click": self._handle_middle_click,
            "double_click": self._handle_double_click,
            "triple_click": self._handle_triple_click,
            "left_click_drag": self._handle_drag,
            "left_mouse_down": self._handle_mouse_down,
            "left_mouse_up": self._handle_mouse_up,
            "type": self._handle_type,
            "key": self._handle_key,
            "hold_key": self._handle_hold_key,
            "scroll": self._handle_scroll,
            "scroll_to": self._handle_scroll_to,
            "form_input": self._handle_form_input,
            "wait": self._handle_wait,
        }

        handler = handlers.get(action)
        if not handler:
            return self._error_result(tool_use_id, f"Unknown action: {action}")

        try:
            return handler(tool_use_id, input_data)
        except Exception as e:
            print(f"[BrowserExecutor] Error in action {action}: {e}")
            return self._error_result(tool_use_id, str(e))

    # === Helper methods ===

    def _success_result(self, tool_use_id: str, content: list[dict[str, Any]]) -> dict[str, Any]:
        """Create successful tool_result response."""
        return {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}

    def _error_result(self, tool_use_id: str, message: str) -> dict[str, Any]:
        """Create error tool_result response."""
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "is_error": True,
            "content": [{"type": "text", "text": f"Error: {message}"}],
        }

    def _take_screenshot(self) -> dict[str, Any]:
        """Take screenshot and return as base64 content block."""
        png_bytes = self.page.screenshot(type="png")
        b64_data = base64.b64encode(png_bytes).decode("utf-8")

        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": b64_data,
            },
        }

    def _get_element_by_ref(self, ref: str) -> ElementHandle | None:
        """Find element by reference ID.

        Args:
            ref: Reference ID (e.g., "ref_0")

        Returns:
            ElementHandle if found, None otherwise
        """
        ref_data = self.ref_manager.get_ref(ref)
        if not ref_data:
            return None

        # Try to find by selector - silent failure is intentional, we return None
        try:
            element = self.page.query_selector(ref_data.selector)
            if element:
                return element
        except Exception:  # noqa: S110
            pass

        return None

    def _scroll_element_into_view(self, element: ElementHandle):
        """Scroll element into view if needed."""
        element.scroll_into_view_if_needed()
        # Brief wait for smooth scrolling
        self.page.wait_for_timeout(100)

    def _click_element(
        self,
        element: ElementHandle,
        button: str = "left",
        click_count: int = 1,
        modifiers: list[str] | None = None,
    ):
        """Click an element with specified button and modifiers."""
        from typing import Literal, cast

        self._scroll_element_into_view(element)

        # Type-safe button parameter
        button_typed = cast(
            "Literal['left', 'middle', 'right']",
            button if button in ("left", "middle", "right") else "left",
        )

        # Type-safe modifiers parameter
        modifiers_typed: (
            Sequence[Literal["Alt", "Control", "ControlOrMeta", "Meta", "Shift"]] | None
        ) = None
        if modifiers:
            valid_modifiers: list[Literal["Alt", "Control", "ControlOrMeta", "Meta", "Shift"]] = []
            for mod in modifiers:
                if mod in ("Alt", "Control", "ControlOrMeta", "Meta", "Shift"):
                    valid_modifiers.append(
                        cast(
                            "Literal['Alt', 'Control', 'ControlOrMeta', 'Meta', 'Shift']",
                            mod,
                        )
                    )  # type: ignore[arg-type]
            modifiers_typed = valid_modifiers if valid_modifiers else None

        element.click(button=button_typed, click_count=click_count, modifiers=modifiers_typed)

    # === Action handlers ===

    def _handle_navigate(self, tool_use_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Navigate to URL or through history."""
        url = input_data.get("text", "")

        if not url:
            return self._error_result(tool_use_id, "URL is required for navigate action")

        if url == "back":
            self.page.go_back(wait_until="domcontentloaded")
        elif url == "forward":
            self.page.go_forward(wait_until="domcontentloaded")
        else:
            # Add https:// if no protocol specified
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"

            self.page.goto(url, wait_until="domcontentloaded")

        # Reset references after navigation
        self.ref_manager.reset()

        screenshot = self._take_screenshot()
        return self._success_result(
            tool_use_id, [{"type": "text", "text": f"Navigated to {url}"}, screenshot]
        )

    def _handle_screenshot(self, tool_use_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Take screenshot of viewport."""
        screenshot = self._take_screenshot()
        return self._success_result(tool_use_id, [screenshot])

    def _handle_read_page(self, tool_use_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Generate DOM tree with element references."""
        filter_type = input_data.get("text", "")

        if not self.dom_generator:
            return self._error_result(tool_use_id, "DOM generator not initialized")

        tree = self.dom_generator.generate(filter_type)

        return self._success_result(tool_use_id, [{"type": "text", "text": tree}])

    def _handle_get_page_text(self, tool_use_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Extract text content from page."""
        title = self.page.title()
        url = self.page.url

        # Try to find main content
        content_selectors = [
            "article",
            "main",
            '[role="main"]',
            ".article-body",
            ".post-content",
            ".entry-content",
            "body",
        ]

        text = ""
        for selector in content_selectors:
            try:
                element = self.page.query_selector(selector)
                if element:
                    text = element.inner_text()
                    if text:
                        break
            except Exception:  # noqa: S112 - trying multiple selectors
                continue

        # Normalize whitespace
        text = " ".join(text.split())
        # Limit length
        text = text[:5000]

        output = f"Title: {title}\nURL: {url}\n---\n{text}"

        return self._success_result(tool_use_id, [{"type": "text", "text": output}])

    def _handle_find(self, tool_use_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Find elements by semantic query."""
        query = input_data.get("text", "")

        if not query:
            return self._error_result(tool_use_id, "Search query is required for find action")

        # For now, return a message that find is not fully implemented
        # In production, this would search through element refs by name/role
        all_refs = self.ref_manager.get_all_refs()
        matches = []

        query_lower = query.lower()
        for ref_id, ref_data in all_refs.items():
            # Simple matching by name or role
            if query_lower in ref_data.name.lower() or query_lower in ref_data.role.lower():
                matches.append(f"- {ref_id}: {ref_data.role} {ref_data.name[:50]}")

        if matches:
            result_text = f"Found {len(matches)} matching elements\n\n" + "\n".join(
                matches[:10]
            )  # Limit to 10
        else:
            result_text = "No matching elements found"

        return self._success_result(tool_use_id, [{"type": "text", "text": result_text}])

    def _handle_zoom(self, tool_use_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Take screenshot of specific region."""
        region = input_data.get("region")

        if not region or len(region) != 4:
            return self._error_result(tool_use_id, "Region must be [x, y, width, height]")

        x, y, width, height = region
        png_bytes = self.page.screenshot(
            type="png", clip={"x": x, "y": y, "width": width, "height": height}
        )
        b64_data = base64.b64encode(png_bytes).decode("utf-8")

        screenshot = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": b64_data,
            },
        }

        return self._success_result(tool_use_id, [screenshot])

    def _handle_left_click(self, tool_use_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Handle left click (with ref or coordinate)."""
        ref = input_data.get("ref")
        coordinate = input_data.get("coordinate")
        modifier = input_data.get("text", "")  # Modifier key (ctrl, shift, etc.)

        modifiers = [modifier] if modifier else []

        if ref:
            element = self._get_element_by_ref(ref)
            if not element:
                return self._error_result(tool_use_id, f"Element not found: {ref}")
            self._click_element(element, button="left", click_count=1, modifiers=modifiers)
            return self._success_result(tool_use_id, [{"type": "text", "text": f"Clicked {ref}"}])
        if coordinate and len(coordinate) == 2:
            x, y = coordinate
            self.page.mouse.click(x, y, button="left")
            return self._success_result(
                tool_use_id, [{"type": "text", "text": f"Clicked at ({x}, {y})"}]
            )
        return self._error_result(tool_use_id, _ERR_REF_OR_COORD_REQUIRED)

    def _handle_right_click(self, tool_use_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Handle right click."""
        ref = input_data.get("ref")
        coordinate = input_data.get("coordinate")

        if ref:
            element = self._get_element_by_ref(ref)
            if not element:
                return self._error_result(tool_use_id, f"Element not found: {ref}")
            self._click_element(element, button="right")
            return self._success_result(
                tool_use_id, [{"type": "text", "text": f"Right-clicked {ref}"}]
            )
        if coordinate and len(coordinate) == 2:
            x, y = coordinate
            self.page.mouse.click(x, y, button="right")
            return self._success_result(
                tool_use_id, [{"type": "text", "text": f"Right-clicked at ({x}, {y})"}]
            )
        return self._error_result(tool_use_id, _ERR_REF_OR_COORD_REQUIRED)

    def _handle_middle_click(self, tool_use_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Handle middle click."""
        ref = input_data.get("ref")
        coordinate = input_data.get("coordinate")

        if ref:
            element = self._get_element_by_ref(ref)
            if not element:
                return self._error_result(tool_use_id, f"Element not found: {ref}")
            self._click_element(element, button="middle")
            return self._success_result(
                tool_use_id, [{"type": "text", "text": f"Middle-clicked {ref}"}]
            )
        if coordinate and len(coordinate) == 2:
            x, y = coordinate
            self.page.mouse.click(x, y, button="middle")
            return self._success_result(
                tool_use_id, [{"type": "text", "text": f"Middle-clicked at ({x}, {y})"}]
            )
        return self._error_result(tool_use_id, _ERR_REF_OR_COORD_REQUIRED)

    def _handle_double_click(self, tool_use_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Handle double click."""
        ref = input_data.get("ref")
        coordinate = input_data.get("coordinate")

        if ref:
            element = self._get_element_by_ref(ref)
            if not element:
                return self._error_result(tool_use_id, f"Element not found: {ref}")
            self._click_element(element, click_count=2)
            return self._success_result(
                tool_use_id, [{"type": "text", "text": f"Double-clicked {ref}"}]
            )
        if coordinate and len(coordinate) == 2:
            x, y = coordinate
            self.page.mouse.dblclick(x, y)
            return self._success_result(
                tool_use_id, [{"type": "text", "text": f"Double-clicked at ({x}, {y})"}]
            )
        return self._error_result(tool_use_id, _ERR_REF_OR_COORD_REQUIRED)

    def _handle_triple_click(self, tool_use_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Handle triple click."""
        ref = input_data.get("ref")
        coordinate = input_data.get("coordinate")

        if ref:
            element = self._get_element_by_ref(ref)
            if not element:
                return self._error_result(tool_use_id, f"Element not found: {ref}")
            self._click_element(element, click_count=3)
            return self._success_result(
                tool_use_id, [{"type": "text", "text": f"Triple-clicked {ref}"}]
            )
        if coordinate and len(coordinate) == 2:
            x, y = coordinate
            self.page.mouse.click(x, y, click_count=3)
            return self._success_result(
                tool_use_id, [{"type": "text", "text": f"Triple-clicked at ({x}, {y})"}]
            )
        return self._error_result(tool_use_id, _ERR_REF_OR_COORD_REQUIRED)

    def _handle_drag(self, tool_use_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Handle drag from start to end coordinate."""
        start_coord = input_data.get("start_coordinate")
        end_coord = input_data.get("coordinate")

        if not start_coord or len(start_coord) != 2:
            return self._error_result(tool_use_id, _ERR_START_COORD_FORMAT)
        if not end_coord or len(end_coord) != 2:
            return self._error_result(tool_use_id, _ERR_COORD_FORMAT)

        start_x, start_y = start_coord
        end_x, end_y = end_coord

        self.page.mouse.move(start_x, start_y)
        self.page.mouse.down()
        self.page.mouse.move(end_x, end_y)
        self.page.mouse.up()

        return self._success_result(
            tool_use_id,
            [
                {
                    "type": "text",
                    "text": f"Dragged from ({start_x}, {start_y}) to ({end_x}, {end_y})",
                }
            ],
        )

    def _handle_mouse_down(self, tool_use_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Handle mouse down at coordinate."""
        coordinate = input_data.get("coordinate")

        if not coordinate or len(coordinate) != 2:
            return self._error_result(tool_use_id, _ERR_COORD_FORMAT)

        x, y = coordinate
        self.page.mouse.move(x, y)
        self.page.mouse.down()

        return self._success_result(
            tool_use_id, [{"type": "text", "text": f"Mouse down at ({x}, {y})"}]
        )

    def _handle_mouse_up(self, tool_use_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Handle mouse up at coordinate."""
        coordinate = input_data.get("coordinate")

        if not coordinate or len(coordinate) != 2:
            return self._error_result(tool_use_id, _ERR_COORD_FORMAT)

        x, y = coordinate
        self.page.mouse.move(x, y)
        self.page.mouse.up()

        return self._success_result(
            tool_use_id, [{"type": "text", "text": f"Mouse up at ({x}, {y})"}]
        )

    def _handle_type(self, tool_use_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Type text into focused element."""
        text = input_data.get("text", "")

        if not text:
            return self._error_result(tool_use_id, "Text is required for type action")

        self.page.keyboard.type(text)

        return self._success_result(tool_use_id, [{"type": "text", "text": f"Typed: {text[:50]}"}])

    def _handle_key(self, tool_use_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Press key or key combination."""
        key_text = input_data.get("text", "")

        if not key_text:
            return self._error_result(tool_use_id, "Key is required for key action")

        # Handle key combinations (ctrl+a, cmd+v, etc.)
        if "+" in key_text:
            # Split into modifiers + key
            parts = key_text.lower().split("+")
            modifiers = parts[:-1]
            key = parts[-1]

            # Press modifiers
            for mod in modifiers:
                if mod in ("ctrl", "control"):
                    self.page.keyboard.down("Control")
                elif mod in ("cmd", "meta"):
                    self.page.keyboard.down("Meta")
                elif mod == "shift":
                    self.page.keyboard.down("Shift")
                elif mod == "alt":
                    self.page.keyboard.down("Alt")

            # Press key
            self.page.keyboard.press(key.capitalize())

            # Release modifiers
            for mod in modifiers:
                if mod in ("ctrl", "control"):
                    self.page.keyboard.up("Control")
                elif mod in ("cmd", "meta"):
                    self.page.keyboard.up("Meta")
                elif mod == "shift":
                    self.page.keyboard.up("Shift")
                elif mod == "alt":
                    self.page.keyboard.up("Alt")
        else:
            # Single key
            self.page.keyboard.press(key_text.capitalize())

        return self._success_result(
            tool_use_id, [{"type": "text", "text": f"Pressed key: {key_text}"}]
        )

    def _handle_hold_key(self, tool_use_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Hold key for duration."""
        key = input_data.get("text", "")
        duration = input_data.get("duration", 1.0)

        if not key:
            return self._error_result(tool_use_id, "Key is required for hold_key action")

        self.page.keyboard.down(key.capitalize())
        self.page.wait_for_timeout(int(duration * 1000))
        self.page.keyboard.up(key.capitalize())

        return self._success_result(
            tool_use_id, [{"type": "text", "text": f"Held key {key} for {duration}s"}]
        )

    def _handle_scroll(self, tool_use_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Scroll in direction by amount."""
        direction = input_data.get("scroll_direction", "")
        amount = input_data.get("scroll_amount", 1)
        coordinate = input_data.get("coordinate")

        if not direction:
            return self._error_result(
                tool_use_id, "scroll_direction is required (up, down, left, right)"
            )

        # Scroll amount in pixels (amount * 100)
        pixels = amount * 100

        # Determine delta
        delta_x = 0
        delta_y = 0

        if direction == "down":
            delta_y = pixels
        elif direction == "up":
            delta_y = -pixels
        elif direction == "right":
            delta_x = pixels
        elif direction == "left":
            delta_x = -pixels
        else:
            return self._error_result(tool_use_id, f"Invalid scroll direction: {direction}")

        # Scroll using mouse wheel
        if coordinate and len(coordinate) == 2:
            x, y = coordinate
            self.page.mouse.move(x, y)

        self.page.mouse.wheel(delta_x, delta_y)

        return self._success_result(
            tool_use_id, [{"type": "text", "text": f"Scrolled {direction} by {amount}"}]
        )

    def _handle_scroll_to(self, tool_use_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Scroll element into view."""
        ref = input_data.get("ref")

        if not ref:
            return self._error_result(tool_use_id, "ref is required for scroll_to action")

        element = self._get_element_by_ref(ref)
        if not element:
            return self._error_result(tool_use_id, f"Element not found: {ref}")

        self._scroll_element_into_view(element)

        return self._success_result(tool_use_id, [{"type": "text", "text": f"Scrolled to {ref}"}])

    def _handle_form_input(self, tool_use_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Set form input value programmatically."""
        ref = input_data.get("ref")
        value = input_data.get("value")

        if not ref:
            return self._error_result(tool_use_id, "ref is required for form_input action")

        element = self._get_element_by_ref(ref)
        if not element:
            return self._error_result(tool_use_id, f"Element not found: {ref}")

        # Fill the element with value
        try:
            if isinstance(value, bool):
                # Checkbox or radio
                if value:
                    element.check()
                else:
                    element.uncheck()
            else:
                # Text input, select, textarea
                element.fill(str(value))
        except Exception as e:
            return self._error_result(tool_use_id, f"Failed to set value: {e}")

        return self._success_result(
            tool_use_id, [{"type": "text", "text": f"Set {ref} to {value}"}]
        )

    def _handle_wait(self, tool_use_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Wait for specified duration."""
        duration = input_data.get("duration", 1.0)

        # Limit to 100 seconds max
        duration = min(duration, 100.0)

        self.page.wait_for_timeout(int(duration * 1000))

        return self._success_result(tool_use_id, [{"type": "text", "text": f"Waited {duration}s"}])
