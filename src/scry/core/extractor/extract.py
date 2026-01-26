"""Generic DOM/structured-data extraction (V2).

Heuristic mapping from common schema fields to page content.
No domain specialization; best-effort extraction.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from ..validator.validate import normalize_against_schema


def _first_text(soup: BeautifulSoup, selectors: list[str]) -> str | None:
    """Find first matching element and return its text content."""
    for sel in selectors:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            return el.get_text(strip=True)
    return None


def _meta_content(soup: BeautifulSoup, name: str) -> str | None:
    """Extract content from a meta tag by name."""
    el = soup.find("meta", attrs={"name": name})
    if isinstance(el, Tag):
        content = el.get("content")
        if content and isinstance(content, str):
            return content.strip()
    return None


# --- Field Extractors ---
# Each extractor handles a specific field type pattern


def _extract_title(soup: BeautifulSoup, key: str) -> str | None:
    """Extract title-like fields from <title> or headings."""
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return _first_text(soup, ["h1", "h2", "header h1"])


def _extract_heading(soup: BeautifulSoup, key: str) -> str | None:
    """Extract heading fields from h1/h2/h3 tags."""
    return _first_text(soup, ["h1", "h2", "h3", "header h1"])


def _extract_name(soup: BeautifulSoup, key: str) -> str | None:
    """Extract name fields from headings or .name classes."""
    return _first_text(soup, ["h1", "h2", "h3", ".name", "[class*='name']"])


def _extract_description(soup: BeautifulSoup, key: str) -> str | None:
    """Extract description from meta tag or paragraph elements."""
    return _meta_content(soup, "description") or _first_text(
        soup, [".description", "p.description", "p", "article p"]
    )


def _extract_price(soup: BeautifulSoup, key: str) -> str | None:
    """Extract price fields using price-related selectors."""
    return _first_text(
        soup,
        [
            f".{key}",
            f"[class*='{key}']",
            ".price",
            "[class*='price']",
            "span:has-text('$')",
        ],
    )


def _extract_generic_string(soup: BeautifulSoup, key: str) -> str | None:
    """Extract generic string fields by class/id matching."""
    return _first_text(
        soup,
        [
            f".{key}",
            f"#{key}",
            f"[class*='{key}']",
            f"[id*='{key}']",
            f"span.{key}",
            f"div.{key}",
        ],
    )


def _extract_number(soup: BeautifulSoup, key: str, prop_type: str) -> int | float | None:
    """Extract numeric fields and convert to int/float."""
    val = _first_text(
        soup,
        [
            f".{key}",
            f"#{key}",
            f"[class*='{key}']",
            f"span.{key}",
            f"div.{key}",
        ],
    )
    if not val:
        return None

    num_match = re.search(r"[\d,]+\.?\d*", val.replace(",", ""))
    if not num_match:
        return None

    try:
        num_val = float(num_match.group())
        return int(num_val) if prop_type == "integer" else num_val
    except (ValueError, TypeError):
        return None


def _extract_generic_array(soup: BeautifulSoup, key: str) -> list[str]:
    """Extract generic array of strings from lists or class-matched elements."""
    arr_items: list[str] = []

    # Try ul/ol lists first
    list_elem = soup.find(class_=key) or soup.find(class_=f"{key}s")
    if isinstance(list_elem, Tag):
        for li in list_elem.find_all("li"):
            text = li.get_text(strip=True)
            if text:
                arr_items.append(text)

    # Try spans/divs if no list items found
    if not arr_items:
        for elem in soup.find_all(class_=re.compile(key)):
            text = elem.get_text(strip=True)
            if text:
                arr_items.append(text)
                if len(arr_items) >= 10:
                    break

    return arr_items


def _extract_features(soup: BeautifulSoup, key: str) -> list[str]:
    """Extract features array from lists with 'feature' in class name."""
    features: list[str] = []

    for ul in soup.find_all(["ul", "ol"]):
        if not isinstance(ul, Tag):
            continue
        ul_class = ul.get("class")
        if not isinstance(ul_class, list):
            continue
        if not any("feature" in str(c).lower() for c in ul_class):
            continue
        for li in ul.find_all("li"):
            text = li.get_text(strip=True)
            if text:
                features.append(text)

    return features


def _extract_tags(soup: BeautifulSoup, key: str) -> list[str]:
    """Extract tags array from elements with 'tag' in class name."""
    tags: list[str] = []

    tag_container = soup.find(class_=re.compile("tag", re.IGNORECASE))
    if isinstance(tag_container, Tag):
        for elem in tag_container.find_all(["span", "a", "div"]):
            text = elem.get_text(strip=True)
            if text:
                tags.append(text)

    return tags


def _extract_links(
    soup: BeautifulSoup, key: str, base_url: str | None, items_type: str
) -> list[Any]:
    """Extract links from anchor tags."""
    links: list[Any] = []

    for a in soup.find_all("a"):
        if not isinstance(a, Tag):
            continue
        href = a.get("href")
        if not href or not isinstance(href, str):
            continue
        if base_url:
            href = urljoin(base_url, href)
        if items_type == "string":
            links.append(href)
        else:
            links.append({"text": a.get_text(strip=True), "href": href})
        if len(links) >= 20:
            break

    return links


def _extract_images(soup: BeautifulSoup, key: str, base_url: str | None) -> list[str]:
    """Extract image URLs from img tags."""
    imgs: list[str] = []

    for img in soup.find_all("img"):
        if not isinstance(img, Tag):
            continue
        src = img.get("src")
        if not src or not isinstance(src, str):
            continue
        if base_url:
            src = urljoin(base_url, src)
        imgs.append(src)
        if len(imgs) >= 20:
            break

    return imgs


# --- Field Pattern Matchers ---


def _matches_string_pattern(key_l: str, pattern: str) -> bool:
    """Check if lowercase key matches a pattern."""
    return pattern in key_l


def _matches_description_pattern(key_l: str) -> bool:
    """Check if key matches description-like patterns."""
    return any(k in key_l for k in ["description", "summary", "overview"])


# --- Main Dispatcher ---


def _extract_string_field(soup: BeautifulSoup, key: str, key_l: str) -> tuple[str | None, bool]:
    """
    Extract a string field based on key pattern.

    Returns:
        Tuple of (extracted_value, was_handled).
        was_handled is True if a specific pattern matched.
    """
    # Check patterns in priority order
    if "title" in key_l:
        return _extract_title(soup, key), True

    if "heading" in key_l:
        return _extract_heading(soup, key), True

    if "name" in key_l:
        return _extract_name(soup, key), True

    if _matches_description_pattern(key_l):
        return _extract_description(soup, key), True

    if "price" in key_l:
        return _extract_price(soup, key), True

    # Fallback to generic string extraction
    return _extract_generic_string(soup, key), True


def _extract_array_field(
    soup: BeautifulSoup,
    key: str,
    key_l: str,
    prop: dict[str, Any],
    base_url: str | None,
) -> tuple[list[Any] | None, bool]:
    """
    Extract an array field based on key pattern.

    Returns:
        Tuple of (extracted_value, was_handled).
    """
    items = prop.get("items", {})
    items_type = items.get("type")

    # Features array
    if "feature" in key_l and items_type == "string":
        result = _extract_features(soup, key)
        return result if result else None, True

    # Tags array
    if "tag" in key_l and items_type == "string":
        result = _extract_tags(soup, key)
        return result if result else None, True

    # Links array
    if ("link" in key_l or "url" in key_l) and items_type in ("string", "object"):
        result = _extract_links(soup, key, base_url, items_type)
        return result if result else None, True

    # Images array
    if ("image" in key_l or "img" in key_l) and items_type == "string":
        result = _extract_images(soup, key, base_url)
        return result if result else None, True

    # Generic array (only for string items, excluding feature/tag)
    if items_type == "string":
        result = _extract_generic_array(soup, key)
        return result if result else None, True

    return None, False


def _extract_field(
    soup: BeautifulSoup,
    key: str,
    prop: dict[str, Any],
    base_url: str | None,
) -> Any:
    """
    Extract a single field from the soup based on its schema property.

    Returns:
        The extracted value, or None if nothing found.
    """
    key_l = key.lower()
    prop_type = prop.get("type")

    if prop_type == "string":
        str_value, _ = _extract_string_field(soup, key, key_l)
        return str_value

    if prop_type in ("number", "integer"):
        return _extract_number(soup, key, prop_type)

    if prop_type == "array":
        arr_value, _ = _extract_array_field(soup, key, key_l, prop, base_url)
        return arr_value

    return None


def extract_data(
    schema: dict[str, Any], html_pages: list[str], base_url: str | None = None
) -> dict[str, Any]:
    """
    Extract data from HTML pages based on a JSON schema.

    Args:
        schema: JSON schema defining expected fields
        html_pages: List of HTML content strings
        base_url: Optional base URL for resolving relative links

    Returns:
        Dictionary of extracted field values
    """
    if not html_pages:
        return {}

    html = html_pages[0]
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, Any] = {}

    schema_type = schema.get("type")
    if schema_type != "object":
        return normalize_against_schema(schema, out)

    props = schema.get("properties", {}) or {}
    for key, prop in props.items():
        value = _extract_field(soup, key, prop, base_url)
        if value is not None:
            out[key] = value

    return normalize_against_schema(schema, out)
