"""DOM tree generation for Browser Tools API.

Generates YAML-like DOM tree representation from Playwright's accessibility API.
This provides Claude with a semantic understanding of the page structure using
element references (ref_X) instead of fragile CSS selectors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from .element_refs import ElementReferenceManager


class DOMTreeGenerator:
    """Generates DOM tree representation for Claude using accessibility API.

    The output format is a YAML-like tree structure with element references:
    - role "name" [ref=ref_X] attr1="value1" attr2="value2"
      - child_role "child_name" [ref=ref_Y]
    """

    # Roles considered interactive (for filtering)
    INTERACTIVE_ROLES = {
        "button",
        "link",
        "textbox",
        "checkbox",
        "radio",
        "combobox",
        "listbox",
        "menuitem",
        "menuitemcheckbox",
        "menuitemradio",
        "option",
        "searchbox",
        "slider",
        "spinbutton",
        "switch",
        "tab",
        "treeitem",
    }

    # Roles to ignore (presentational)
    IGNORED_ROLES = {"none", "presentation"}

    def __init__(self, page: Page, ref_manager: ElementReferenceManager):
        """Initialize DOM tree generator.

        Args:
            page: Playwright page instance
            ref_manager: Element reference manager for creating ref_X identifiers
        """
        self.page = page
        self.ref_manager = ref_manager

    def generate(self, filter_type: str = "") -> str:
        """Generates DOM tree as YAML-like string.

        Args:
            filter_type: "" for all elements, "interactive" for only interactive elements

        Returns:
            YAML-like tree structure with element references
        """
        # Get accessibility snapshot from Playwright
        snapshot = self.page.accessibility.snapshot()  # type: ignore[attr-defined]

        if not snapshot:
            return "No accessibility tree available"

        lines: list[str] = []
        self._traverse_node(
            node=snapshot,
            indent=0,
            lines=lines,
            filter_type=filter_type,
            max_depth=15,
        )

        return "\n".join(lines)

    def _traverse_node(
        self,
        node: dict[str, Any],
        indent: int,
        lines: list[str],
        filter_type: str,
        max_depth: int = 15,
    ) -> None:
        """Recursively traverse accessibility tree nodes.

        Args:
            node: Accessibility tree node from Playwright
            indent: Current indentation level
            lines: List to append formatted lines to
            filter_type: Filter mode ("" or "interactive")
            max_depth: Maximum tree depth to prevent infinite recursion
        """
        if not node or indent > max_depth:
            return

        role = node.get("role", "generic")
        name = node.get("name", "")

        # Skip ignored roles but process their children
        if role in self.IGNORED_ROLES:
            for child in node.get("children", []):
                self._traverse_node(child, indent, lines, filter_type, max_depth)
            return

        # Filter: only interactive elements
        if filter_type == "interactive" and role not in self.INTERACTIVE_ROLES:
            # Not interactive, but check children
            for child in node.get("children", []):
                self._traverse_node(child, indent, lines, filter_type, max_depth)
            return

        # Build selector for this element (fallback for element recovery)
        selector = self._build_selector(node)
        attributes = self._extract_attributes(node)

        # Create element reference
        ref_id = self.ref_manager.create_ref(
            selector=selector,
            role=role,
            name=name[:100] if name else "",  # Truncate to 100 chars
            attributes=attributes,
        )

        # Format and add line
        line = self._format_line(role, name, ref_id, attributes, indent)
        lines.append(line)

        # Process children with increased indent
        for child in node.get("children", []):
            self._traverse_node(child, indent + 1, lines, filter_type, max_depth)

    def _format_line(
        self,
        role: str,
        name: str,
        ref_id: str,
        attributes: dict[str, str],
        indent: int,
    ) -> str:
        """Format a single line in YAML-like format.

        Args:
            role: Element role (button, link, etc.)
            name: Element name/label
            ref_id: Reference ID (ref_X)
            attributes: Element attributes (href, type, etc.)
            indent: Indentation level

        Returns:
            Formatted line: "- role "name" [ref=ref_X] attr1="value1"
        """
        prefix = "  " * indent

        # Clean and truncate name
        clean_name = self._clean_name(name)
        name_part = f' "{clean_name}"' if clean_name else ""

        # Format attributes (only show relevant ones)
        attr_parts = []
        relevant_attrs = ("href", "type", "id", "placeholder", "value")
        for key, value in attributes.items():
            if key in relevant_attrs:
                # Truncate long values
                short_value = value[:50] + "..." if len(value) > 50 else value
                # Escape quotes in value
                escaped_value = short_value.replace('"', '\\"')
                attr_parts.append(f'{key}="{escaped_value}"')

        attr_str = " ".join(attr_parts)
        if attr_str:
            attr_str = " " + attr_str

        return f"{prefix}- {role}{name_part} [ref={ref_id}]{attr_str}"

    def _clean_name(self, name: str) -> str:
        """Clean element name for display.

        Args:
            name: Raw element name

        Returns:
            Cleaned and truncated name
        """
        if not name:
            return ""

        # Normalize whitespace
        clean = " ".join(name.split())

        # Truncate to 100 chars
        if len(clean) > 100:
            clean = clean[:97] + "..."

        # Escape quotes
        clean = clean.replace('"', '\\"')

        return clean

    def _build_selector(self, node: dict[str, Any]) -> str:
        """Build CSS selector from accessibility node.

        This is a fallback selector for element recovery if the element
        is temporarily detached from the DOM. In production, more robust
        selectors would be generated.

        Args:
            node: Accessibility tree node

        Returns:
            CSS selector string
        """
        role = node.get("role", "")
        name = node.get("name", "")

        # Simple selector strategies based on role
        if role == "link" and "value" in node:
            # Link with href
            href = node.get("value", "")
            if href:
                # Escape special chars in href for CSS selector
                escaped_href = href.replace('"', '\\"')
                return f'a[href="{escaped_href}"]'
        elif role == "button":
            if name:
                # Button with text - use Playwright's has-text selector
                return f'button:has-text("{name[:50]}")'
            return "button"
        elif role == "textbox":
            return 'input[type="text"], input:not([type]), textarea'
        elif role == "searchbox":
            return 'input[type="search"]'
        elif role == "checkbox":
            return 'input[type="checkbox"]'
        elif role == "radio":
            return 'input[type="radio"]'
        elif role == "combobox":
            return "select"

        # Fallback: role attribute
        return f'[role="{role}"]' if role else "*"

    def _extract_attributes(self, node: dict[str, Any]) -> dict[str, str]:
        """Extract relevant attributes from accessibility node.

        Args:
            node: Accessibility tree node

        Returns:
            Dictionary of relevant attributes
        """
        attrs = {}

        # Known attributes to extract
        attr_names = (
            "href",
            "type",
            "id",
            "placeholder",
            "value",
            "checked",
            "disabled",
            "name",
        )

        for key in attr_names:
            if key in node:
                # Convert to string
                value = node[key]
                if isinstance(value, bool):
                    attrs[key] = "true" if value else "false"
                else:
                    attrs[key] = str(value)

        return attrs
