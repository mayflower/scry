"""LLM-based cookie banner detection.

This module implements semantic analysis of web pages to detect and identify
cookie consent banners without relying on string matching or specific IDs.

Additional heuristics provide context hints to the LLM:
- IAB TCF API detection (window.__tcfapi)
- CSS position/z-index analysis for overlay detection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable


@runtime_checkable
class RefManagerProtocol(Protocol):
    """Protocol for element reference managers.

    Only requires get_ref() method returning something with a selector attribute.
    """

    def get_ref(self, ref_id: str) -> object | None:
        """Get reference data for a ref_id. Returns object with .selector or None."""
        ...


if TYPE_CHECKING:
    pass


@dataclass
class BannerHints:
    """Heuristic hints to provide context to LLM detection.

    These are supplementary signals, not used for string matching.
    """

    has_tcf_api: bool = False  # IAB TCF API (window.__tcfapi) detected
    has_cmp_api: bool = False  # Generic CMP API (window.__cmp) detected
    fixed_elements: list[dict[str, str]] = field(default_factory=list)
    # List of {ref, role, z_index, position} for fixed/sticky high-z elements


@dataclass
class CookieBannerResult:
    """Result of cookie banner detection."""

    has_banner: bool
    dismiss_ref: str | None  # ref_X identifier from DOM tree
    dismiss_selector: str | None  # CSS selector for code generation
    banner_type: str | None  # "modal", "overlay", "bar"
    confidence: float


DETECTION_SYSTEM_PROMPT = """You are a web page analyzer specializing in identifying cookie consent banners.

Your task is to analyze a web page's DOM structure and determine if there is a cookie consent banner present.

IMPORTANT: Do NOT rely on button text like "Accept", "OK", "Agree" for detection.
Instead, analyze:
1. Structural patterns - overlays, modals, fixed/sticky positioned elements
2. Semantic context - elements related to privacy, consent, cookies, GDPR, tracking
3. Interaction blocking - elements that appear to block or overlay main content
4. Visual hierarchy - prominent dismiss buttons, contrasting backgrounds

When identifying the dismiss element:
- Find the PRIMARY action that dismisses/accepts the banner
- This is typically the most prominent button (often larger, colored)
- Avoid secondary actions like "Customize", "Manage preferences", "Reject"
- The goal is to find the quick dismiss option

Respond with a JSON object only, no other text."""


def _create_detection_prompt(dom_tree: str, hints: BannerHints | None = None) -> str:
    """Create the user prompt for cookie banner detection."""
    hints_section = ""
    if hints:
        hints_lines = []
        if hints.has_tcf_api:
            hints_lines.append(
                "- IAB TCF API detected (window.__tcfapi) - confirms consent framework is present"
            )
        if hints.has_cmp_api:
            hints_lines.append(
                "- CMP API detected (window.__cmp) - confirms consent management platform"
            )
        if hints.fixed_elements:
            hints_lines.append(
                f"- {len(hints.fixed_elements)} fixed/sticky elements with high z-index detected:"
            )
            for elem in hints.fixed_elements[:5]:  # Limit to top 5
                hints_lines.append(
                    f"  - {elem.get('ref')}: {elem.get('role')} "
                    f"(z-index: {elem.get('z_index')}, position: {elem.get('position')})"
                )

        if hints_lines:
            hints_section = "\n\nHeuristic signals detected:\n" + "\n".join(hints_lines)

    return f"""Analyze this page DOM structure for cookie consent banners.

DOM Structure (with element references):
```
{dom_tree[:15000]}
```{hints_section}

Based on the structural analysis, determine:
1. Is there a cookie consent banner/dialog present?
2. If yes, what is the element reference (ref_X) of the button that dismisses it?
3. What type of banner is it (modal, overlay, bar)?
4. How confident are you in this detection?

Return ONLY a JSON object:
{{
  "has_banner": true or false,
  "dismiss_ref": "ref_X" or null,
  "banner_type": "modal" or "overlay" or "bar" or null,
  "confidence": 0.0 to 1.0
}}"""


def detect_cookie_banner(
    dom_tree: str,
    ref_manager: RefManagerProtocol | None,
    hints: BannerHints | None = None,
) -> CookieBannerResult:
    """Detect cookie banner using LLM semantic analysis.

    This function analyzes the page's DOM structure to identify cookie consent
    banners without relying on string matching or specific element IDs.

    Args:
        dom_tree: YAML-like DOM tree with element references (ref_X)
        ref_manager: Element reference manager for selector lookup
        hints: Optional heuristic hints (TCF API detection, fixed elements)

    Returns:
        CookieBannerResult with detection results and dismiss element info
    """
    from ...adapters.anthropic import complete_json, has_api_key

    # If no API key, return no banner detected
    if not has_api_key():
        print("[Cookie] No API key available, skipping detection")
        return CookieBannerResult(
            has_banner=False,
            dismiss_ref=None,
            dismiss_selector=None,
            banner_type=None,
            confidence=0.0,
        )

    try:
        # Call Claude for semantic analysis
        result, _ = complete_json(
            system_prompt=DETECTION_SYSTEM_PROMPT,
            user_prompt=_create_detection_prompt(dom_tree, hints),
            model="claude-sonnet-4-20250514",  # Use Sonnet for speed
            max_tokens=500,
            temperature=0.0,
        )

        has_banner = bool(result.get("has_banner", False))
        dismiss_ref = result.get("dismiss_ref")
        banner_type = result.get("banner_type")
        confidence = float(result.get("confidence", 0.0))

        # Look up selector from ref if we have a dismiss ref
        dismiss_selector = None
        if dismiss_ref and ref_manager:
            ref_data = ref_manager.get_ref(dismiss_ref)
            if ref_data and hasattr(ref_data, "selector"):
                dismiss_selector = getattr(ref_data, "selector")

        print(
            f"[Cookie] Detection result: has_banner={has_banner}, "
            f"dismiss_ref={dismiss_ref}, type={banner_type}, confidence={confidence}"
        )

        return CookieBannerResult(
            has_banner=has_banner,
            dismiss_ref=dismiss_ref,
            dismiss_selector=dismiss_selector,
            banner_type=banner_type,
            confidence=confidence,
        )

    except Exception as e:
        print(f"[Cookie] Detection failed: {e}")
        return CookieBannerResult(
            has_banner=False,
            dismiss_ref=None,
            dismiss_selector=None,
            banner_type=None,
            confidence=0.0,
        )
