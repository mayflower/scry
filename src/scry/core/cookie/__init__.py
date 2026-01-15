"""Cookie banner detection module.

This module provides LLM-based detection of cookie consent banners
that does not rely on string matching or ID patterns.
"""

from __future__ import annotations

from .detector import BannerHints, CookieBannerResult, detect_cookie_banner

__all__ = ["BannerHints", "CookieBannerResult", "detect_cookie_banner"]
