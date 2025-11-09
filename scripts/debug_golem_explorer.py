#!/usr/bin/env python3
"""Debug script to see what the explorer sees on golem.de"""

from playwright.sync_api import sync_playwright


def get_page_state(page):
    """Extract page state same as explorer does."""
    try:
        title = page.title()
        url = page.url

        # Extract interactive elements (same as explorer)
        elements = page.evaluate("""() => {
            const getSelector = (el) => {
                if (el.id) return '#' + el.id;
                if (el.className && typeof el.className === 'string') {
                    const classes = el.className.trim().split(/\\s+/).slice(0, 2).join('.');
                    if (classes) return el.tagName.toLowerCase() + '.' + classes;
                }
                return el.tagName.toLowerCase();
            };

            const elements = [];
            // Get clickable elements
            document.querySelectorAll('a, button, [role="button"], [onclick]').forEach((el, idx) => {
                if (idx < 50 && el.offsetParent !== null) {  // Visible elements only, limit to 50
                    elements.push({
                        type: 'clickable',
                        selector: getSelector(el),
                        text: el.textContent?.trim().substring(0, 100) || '',
                        tag: el.tagName.toLowerCase()
                    });
                }
            });

            // Get input fields
            document.querySelectorAll('input, textarea, select').forEach((el, idx) => {
                if (idx < 20 && el.offsetParent !== null) {  // Limit to 20
                    elements.push({
                        type: 'input',
                        selector: getSelector(el),
                        placeholder: el.placeholder || '',
                        inputType: el.type || 'text'
                    });
                }
            });

            return elements;
        }""")

        # Get visible text content
        text_content = page.evaluate("() => document.body.innerText")
        if isinstance(text_content, str):
            text_content = text_content[:3000]

        return {"title": title, "url": url, "elements": elements, "text": text_content}
    except Exception as e:
        return {
            "title": "",
            "url": page.url,
            "elements": [],
            "text": "",
            "error": str(e),
        }


def main():
    print("Debugging golem.de explorer page state extraction")
    print("=" * 70)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        page = context.new_page()
        page.set_default_timeout(30000)

        print("\nNavigating to golem.de...")
        page.goto("https://www.golem.de/", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)  # Wait for JS to load

        state = get_page_state(page)

        print(f"\nPage title: {state['title']}")
        print(f"Page URL: {state['url']}")
        print(f"\nExtracted {len(state['elements'])} interactive elements:")
        print("-" * 70)

        # Show cookie-related elements
        cookie_elements = [
            el
            for el in state["elements"]
            if any(
                word in el.get("text", "").lower()
                for word in ["cookie", "consent", "zustimm", "accept", "ablehnen"]
            )
        ]

        if cookie_elements:
            print("\n🍪 COOKIE-RELATED ELEMENTS:")
            for i, el in enumerate(cookie_elements, 1):
                print(f"\n  {i}. Type: {el['type']}")
                print(f"     Selector: {el['selector']}")
                print(f"     Text: {el.get('text', '')[:100]}")
                print(f"     Tag: {el['tag']}")
        else:
            print("\n⚠️  NO COOKIE-RELATED ELEMENTS FOUND!")

        print("\n" + "-" * 70)
        print("\nAll clickable elements:")
        for i, el in enumerate(state["elements"][:20], 1):  # First 20
            if el["type"] == "clickable":
                print(f"\n  {i}. [{el['tag']}] {el['selector']}")
                print(f"     Text: {el.get('text', '')[:80]}")

        print("\n" + "-" * 70)
        print("\nPage text excerpt (first 500 chars):")
        print(state["text"][:500])

        browser.close()


if __name__ == "__main__":
    main()
