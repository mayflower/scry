"""Generic DOM/structured-data extraction (V2).

Heuristic mapping from common schema fields to page content.
No domain specialization; best-effort extraction.
"""

from __future__ import annotations

from bs4 import BeautifulSoup
from typing import Any, Dict, List
from ..validator.validate import normalize_against_schema
from urllib.parse import urljoin


def _first_text(soup: BeautifulSoup, selectors: List[str]) -> str | None:
    for sel in selectors:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            return el.get_text(strip=True)
    return None


def _meta_content(soup: BeautifulSoup, name: str) -> str | None:
    el = soup.find("meta", attrs={"name": name})
    if el and el.get("content"):
        return el["content"].strip()
    return None


def extract_data(
    schema: Dict[str, Any], html_pages: List[str], base_url: str | None = None
) -> Dict[str, Any]:
    if not html_pages:
        return {}

    html = html_pages[0]
    soup = BeautifulSoup(html, "html.parser")
    out: Dict[str, Any] = {}

    schema_type = schema.get("type")
    if schema_type == "object":
        props = schema.get("properties", {}) or {}
        for key, prop in props.items():
            key_l = key.lower()
            prop_type = prop.get("type")

            # Title-like
            if prop_type == "string" and any(
                k in key_l for k in ["title", "name", "heading"]
            ):
                val = _first_text(soup, ["title", "h1", "h2", "header h1"]) or (
                    soup.title.string.strip()
                    if soup.title and soup.title.string
                    else None
                )
                if val:
                    out[key] = val
                continue

            # Description-like
            if prop_type == "string" and any(
                k in key_l for k in ["description", "summary", "overview"]
            ):
                val = _meta_content(soup, "description") or _first_text(
                    soup, ["p", "article p"]
                )
                if val:
                    out[key] = val
                continue

            # Links
            if (
                prop_type == "array"
                and (prop.get("items", {}).get("type") in ("string", "object"))
                and ("link" in key_l or "url" in key_l)
            ):
                links: List[Any] = []
                items = prop.get("items", {})
                for a in soup.find_all("a"):
                    href = a.get("href")
                    if not href:
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
                and items.get("type") == "string"
                and ("image" in key_l or "img" in key_l)
            ):
                imgs: List[str] = []
                for img in soup.find_all("img"):
                    src = img.get("src")
                    if not src:
                        continue
                    if base_url:
                        src = urljoin(base_url, src)
                    imgs.append(src)
                    if len(imgs) >= 20:
                        break
                if imgs:
                    out[key] = imgs
                continue

    # If schema is not object or nothing matched, return best-effort minimal data
    return normalize_against_schema(schema, out)
