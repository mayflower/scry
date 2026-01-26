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
    for sel in selectors:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            return el.get_text(strip=True)
    return None


def _meta_content(soup: BeautifulSoup, name: str) -> str | None:
    el = soup.find("meta", attrs={"name": name})
    if isinstance(el, Tag):
        content = el.get("content")
        if content and isinstance(content, str):
            return content.strip()
    return None


def extract_data(
    schema: dict[str, Any], html_pages: list[str], base_url: str | None = None
) -> dict[str, Any]:
    if not html_pages:
        return {}

    html = html_pages[0]
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, Any] = {}

    schema_type = schema.get("type")
    if schema_type == "object":
        props = schema.get("properties", {}) or {}
        for key, prop in props.items():
            key_l = key.lower()
            prop_type = prop.get("type")

            # Title-like fields - check field name to determine extraction strategy
            if prop_type == "string" and "title" in key_l:
                # For "title" specifically, prefer <title> tag
                val = (
                    soup.title.string.strip()
                    if soup.title and soup.title.string
                    else _first_text(soup, ["h1", "h2", "header h1"])
                )
                if val:
                    out[key] = val
                continue

            # Heading fields - prefer h1/h2 tags
            if prop_type == "string" and "heading" in key_l:
                val = _first_text(soup, ["h1", "h2", "h3", "header h1"])
                if val:
                    out[key] = val
                continue

            # Name fields
            if prop_type == "string" and "name" in key_l:
                val = _first_text(soup, ["h1", "h2", "h3", ".name", "[class*='name']"])
                if val:
                    out[key] = val
                continue

            # Description-like
            if prop_type == "string" and any(
                k in key_l for k in ["description", "summary", "overview"]
            ):
                val = _meta_content(soup, "description") or _first_text(
                    soup, [".description", "p.description", "p", "article p"]
                )
                if val:
                    out[key] = val
                continue

            # Price fields
            if prop_type == "string" and "price" in key_l:
                val = _first_text(
                    soup,
                    [
                        f".{key}",
                        f"[class*='{key}']",
                        ".price",
                        "[class*='price']",
                        "span:has-text('$')",
                    ],
                )
                if val:
                    out[key] = val
                continue

            # Generic string fields - try class/id matching
            if prop_type == "string":
                val = _first_text(
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
                if val:
                    out[key] = val
                continue

            # Number fields
            if prop_type in ["number", "integer"]:
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
                if val:
                    # Try to extract number from text
                    num_match = re.search(r"[\d,]+\.?\d*", val.replace(",", ""))
                    if num_match:
                        try:
                            num_val = float(num_match.group())
                            if prop_type == "integer":
                                out[key] = int(num_val)
                            else:
                                out[key] = num_val
                        except (ValueError, TypeError):
                            pass
                continue

            # Array fields - generic extraction
            if prop_type == "array" and "feature" not in key_l and "tag" not in key_l:
                items_type = prop.get("items", {}).get("type")
                if items_type == "string":
                    # Try to find lists by class name
                    arr_items: list[str] = []
                    # Try ul/ol lists first
                    list_elem = soup.find(class_=key) or soup.find(class_=f"{key}s")
                    if isinstance(list_elem, Tag):
                        for li in list_elem.find_all("li"):
                            text = li.get_text(strip=True)
                            if text:
                                arr_items.append(text)
                    # Try spans/divs
                    if not arr_items:
                        for elem in soup.find_all(class_=re.compile(key)):
                            text = elem.get_text(strip=True)
                            if text:
                                arr_items.append(text)
                                if len(arr_items) >= 10:
                                    break
                    if arr_items:
                        out[key] = arr_items
                continue

            # Features array
            if prop_type == "array" and "feature" in key_l:
                items_type = prop.get("items", {}).get("type")
                if items_type == "string":
                    features: list[str] = []
                    # Look for ul with class containing "feature"
                    for ul in soup.find_all(["ul", "ol"]):
                        if isinstance(ul, Tag):
                            ul_class = ul.get("class")
                            if isinstance(ul_class, list) and any(
                                "feature" in str(c).lower() for c in ul_class
                            ):
                                for li in ul.find_all("li"):
                                    text = li.get_text(strip=True)
                                    if text:
                                        features.append(text)
                    if features:
                        out[key] = features
                continue

            # Tags array
            if prop_type == "array" and "tag" in key_l:
                items_type = prop.get("items", {}).get("type")
                if items_type == "string":
                    tags: list[str] = []
                    # Look for elements with class containing "tag"
                    tag_container = soup.find(class_=re.compile("tag", re.IGNORECASE))
                    if isinstance(tag_container, Tag):
                        for elem in tag_container.find_all(["span", "a", "div"]):
                            text = elem.get_text(strip=True)
                            if text:
                                tags.append(text)
                    if tags:
                        out[key] = tags
                continue

            # Links
            if (
                prop_type == "array"
                and (prop.get("items", {}).get("type") in ("string", "object"))
                and ("link" in key_l or "url" in key_l)
            ):
                links: list[Any] = []
                items = prop.get("items", {})
                for a in soup.find_all("a"):
                    if not isinstance(a, Tag):
                        continue
                    href = a.get("href")
                    if not href or not isinstance(href, str):
                        continue
                    if base_url:
                        href = urljoin(base_url, href)
                    if items.get("type") == "string":
                        links.append(href)
                    else:
                        links.append({"text": a.get_text(strip=True), "href": href})
                    if len(links) >= 20:
                        break
                if links:
                    out[key] = links
                continue

            # Images
            if (
                prop_type == "array"
                and prop.get("items", {}).get("type") == "string"
                and ("image" in key_l or "img" in key_l)
            ):
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
                if imgs:
                    out[key] = imgs

    # If schema is not object or nothing matched, return best-effort minimal data
    return normalize_against_schema(schema, out)
