"""Element reference management for Browser Tools API.

Provides stable ref_X identifiers for DOM elements that persist across
page interactions until navigation occurs. This is more robust than CSS
selectors which can break when page structure changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ElementReference:
    """Represents a stable reference to a DOM element.

    Element references are created from the accessibility tree and provide
    fallback selectors for element recovery if the element is temporarily
    detached from the DOM.
    """

    ref_id: str  # e.g., "ref_0", "ref_1"
    selector: str  # Fallback CSS selector for element recovery
    role: str  # ARIA role (e.g., "button", "link", "textbox")
    name: str  # Element name/label (truncated to 100 chars)
    attributes: dict[str, str] = field(default_factory=dict)  # href, type, id, etc.


class ElementReferenceManager:
    """Manages element references for a browser session.

    Creates and tracks stable ref_X identifiers that map to DOM elements.
    References are reset on page navigation to ensure consistency.
    """

    def __init__(self):
        self._refs: dict[str, ElementReference] = {}
        self._counter: int = 0
        self._page_url: str | None = None

    def reset(self):
        """Resets all references (called on navigation)."""
        self._refs.clear()
        self._counter = 0

    def on_navigation(self, new_url: str):
        """Called when page navigates to reset references if URL changed."""
        if self._page_url != new_url:
            self.reset()
            self._page_url = new_url

    def create_ref(
        self,
        selector: str,
        role: str,
        name: str,
        attributes: dict[str, str] | None = None,
    ) -> str:
        """Creates a new element reference.

        Args:
            selector: CSS selector for finding the element
            role: ARIA role (button, link, textbox, etc.)
            name: Element name/label (will be truncated to 100 chars)
            attributes: Optional dict of element attributes (href, type, id, etc.)

        Returns:
            Reference ID in format "ref_N"
        """
        ref_id = f"ref_{self._counter}"
        self._counter += 1

        # Truncate name to 100 chars to avoid bloat
        truncated_name = name[:100] if name else ""

        self._refs[ref_id] = ElementReference(
            ref_id=ref_id,
            selector=selector,
            role=role,
            name=truncated_name,
            attributes=attributes or {},
        )

        return ref_id

    def get_ref(self, ref_id: str) -> ElementReference | None:
        """Gets an element reference by ID.

        Args:
            ref_id: Reference ID (e.g., "ref_0")

        Returns:
            ElementReference if found, None otherwise
        """
        return self._refs.get(ref_id)

    def has_ref(self, ref_id: str) -> bool:
        """Checks if a reference exists.

        Args:
            ref_id: Reference ID to check

        Returns:
            True if reference exists
        """
        return ref_id in self._refs

    def get_all_refs(self) -> dict[str, ElementReference]:
        """Returns all current references.

        Returns:
            Dictionary mapping ref_id to ElementReference
        """
        return self._refs.copy()
