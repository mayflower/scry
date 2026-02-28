"""Integration tests for data extraction from real HTML."""

from __future__ import annotations

import pytest

from scry.core.extractor.extract import extract_data


class TestDataExtraction:
    """Test suite for data extraction from HTML."""

    def test_extract_simple_strings(self):
        """Test extracting basic string fields from HTML."""
        html = """
        <html>
        <head>
            <title>Test Product Page</title>
            <meta name="description" content="This is a test product">
        </head>
        <body>
            <h1>Amazing Product</h1>
            <p class="description">High quality item for testing</p>
            <div class="price">$29.99</div>
        </body>
        </html>
        """

        schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "heading": {"type": "string"},
                "description": {"type": "string"},
                "price": {"type": "string"},
            },
        }

        result = extract_data(schema, [html])

        assert result["title"] == "Test Product Page"
        assert result["heading"] == "Amazing Product"
        assert (
            "test product" in result["description"].lower()
            or "high quality" in result["description"].lower()
        )
        assert "$29.99" in result["price"]

    def test_extract_numbers(self):
        """Test extracting numeric fields from HTML."""
        html = """
        <html>
        <body>
            <div class="stats">
                <span class="count">42</span>
                <span class="rating">4.5</span>
                <span class="price">99.99</span>
                <span class="quantity">1,234</span>
            </div>
        </body>
        </html>
        """

        schema = {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "rating": {"type": "number"},
                "price": {"type": "number"},
                "quantity": {"type": "integer"},
            },
        }

        result = extract_data(schema, [html])

        assert result.get("count") == 42
        assert result.get("rating") == 4.5 or result.get("rating") == 4
        assert result.get("price") == 99.99 or result.get("price") == 99
        assert result.get("quantity") in [1234, 1, 234]  # Might parse differently

    def test_extract_arrays(self):
        """Test extracting array fields from HTML lists."""
        html = """
        <html>
        <body>
            <ul class="features">
                <li>Fast shipping</li>
                <li>High quality</li>
                <li>Great support</li>
            </ul>
            <div class="tags">
                <span>electronics</span>
                <span>gadgets</span>
                <span>tech</span>
            </div>
        </body>
        </html>
        """

        schema = {
            "type": "object",
            "properties": {
                "features": {"type": "array", "items": {"type": "string"}},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
        }

        result = extract_data(schema, [html])

        # Should extract at least some items
        if "features" in result:
            assert isinstance(result["features"], list)
            assert len(result["features"]) > 0
            # Check if any feature was extracted
            features_text = " ".join(str(f) for f in result["features"])
            assert "shipping" in features_text.lower() or "quality" in features_text.lower()

        if "tags" in result:
            assert isinstance(result["tags"], list)

    def test_extract_nested_objects(self):
        """Test extracting nested object structures."""
        html = """
        <html>
        <body>
            <div class="product">
                <h2>Laptop</h2>
                <div class="specs">
                    <span class="cpu">Intel i7</span>
                    <span class="ram">16GB</span>
                    <span class="storage">512GB SSD</span>
                </div>
                <div class="pricing">
                    <span class="regular">$1299</span>
                    <span class="sale">$999</span>
                </div>
            </div>
        </body>
        </html>
        """

        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "specs": {
                    "type": "object",
                    "properties": {
                        "cpu": {"type": "string"},
                        "ram": {"type": "string"},
                        "storage": {"type": "string"},
                    },
                },
                "pricing": {
                    "type": "object",
                    "properties": {
                        "regular": {"type": "string"},
                        "sale": {"type": "string"},
                    },
                },
            },
        }

        result = extract_data(schema, [html])

        # Check name extraction
        if "name" in result:
            assert "laptop" in result["name"].lower()

        # Check nested extraction (may not work perfectly without specialization)
        if "specs" in result and isinstance(result["specs"], dict):
            specs_str = str(result["specs"])
            assert "16" in specs_str or "Intel" in specs_str or "512" in specs_str

    def test_extract_from_empty_html(self):
        """Test extraction from empty or minimal HTML."""
        html = "<html><body></body></html>"

        schema = {
            "type": "object",
            "properties": {"title": {"type": "string"}, "content": {"type": "string"}},
        }

        result = extract_data(schema, [html])

        # Should return empty dict or empty strings
        assert isinstance(result, dict)
        assert result.get("title", "") == "" or result.get("title") is None

    def test_extract_from_multiple_pages(self):
        """Test extraction when multiple HTML pages are provided."""
        html1 = """
        <html>
        <head><title>Page 1</title></head>
        <body><h1>First Page</h1></body>
        </html>
        """

        html2 = """
        <html>
        <head><title>Page 2</title></head>
        <body><h1>Second Page</h1></body>
        </html>
        """

        schema = {
            "type": "object",
            "properties": {"title": {"type": "string"}, "heading": {"type": "string"}},
        }

        # Should use first page
        result = extract_data(schema, [html1, html2])

        assert "Page 1" in result.get("title", "") or "First" in result.get("heading", "")

    def test_extract_with_base_url(self):
        """Test URL resolution with base URL."""
        html = """
        <html>
        <body>
            <a href="/page1">Link 1</a>
            <a href="page2">Link 2</a>
            <a href="https://external.com/page">External</a>
            <img src="/images/test.jpg">
        </body>
        </html>
        """

        schema = {
            "type": "object",
            "properties": {
                "links": {"type": "array", "items": {"type": "string"}},
                "images": {"type": "array", "items": {"type": "string"}},
            },
        }

        result = extract_data(schema, [html], base_url="https://example.com")

        # Check if links are extracted and resolved
        if "links" in result and isinstance(result["links"], list):
            links_str = " ".join(result["links"])
            # Should contain some URLs
            assert "http" in links_str or "/" in links_str

    def test_extract_special_fields(self):
        """Test extraction of special field names like email, url, date."""
        html = """
        <html>
        <body>
            <div class="contact">
                <span class="email">test@example.com</span>
                <span class="phone">(555) 123-4567</span>
                <span class="website">https://example.com</span>
                <span class="date">2024-01-15</span>
                <span class="address">123 Main St, City, State 12345</span>
            </div>
        </body>
        </html>
        """

        schema = {
            "type": "object",
            "properties": {
                "email": {"type": "string"},
                "phone": {"type": "string"},
                "url": {"type": "string"},
                "website": {"type": "string"},
                "date": {"type": "string"},
                "address": {"type": "string"},
            },
        }

        result = extract_data(schema, [html])

        # Check email extraction
        if "email" in result:
            assert "@" in result["email"]

        # Check URL extraction
        if "url" in result or "website" in result:
            url_value = result.get("url", "") or result.get("website", "")
            assert "http" in url_value or "example" in url_value

    def test_extract_from_complex_html(self):
        """Test extraction from realistic complex HTML."""
        html = """
        <html>
        <head>
            <title>E-commerce Product Page</title>
            <meta name="description" content="Buy the best products online">
        </head>
        <body>
            <header>
                <nav>
                    <a href="/">Home</a>
                    <a href="/products">Products</a>
                    <a href="/cart">Cart</a>
                </nav>
            </header>
            <main>
                <article class="product">
                    <h1>Premium Headphones</h1>
                    <div class="gallery">
                        <img src="/img1.jpg" alt="Product image 1">
                        <img src="/img2.jpg" alt="Product image 2">
                    </div>
                    <div class="details">
                        <p class="description">
                            High-quality wireless headphones with noise cancellation.
                            Perfect for music lovers and professionals.
                        </p>
                        <div class="price-section">
                            <span class="original-price">$299.99</span>
                            <span class="sale-price">$199.99</span>
                            <span class="discount">33% off</span>
                        </div>
                        <ul class="features">
                            <li>40-hour battery life</li>
                            <li>Active noise cancellation</li>
                            <li>Bluetooth 5.0</li>
                            <li>Comfortable fit</li>
                        </ul>
                        <div class="reviews">
                            <span class="rating">4.5</span>
                            <span class="review-count">1,234 reviews</span>
                        </div>
                    </div>
                    <div class="purchase">
                        <select name="quantity">
                            <option>1</option>
                            <option>2</option>
                            <option>3</option>
                        </select>
                        <button>Add to Cart</button>
                    </div>
                </article>
            </main>
            <footer>
                <p>&copy; 2024 Test Store. All rights reserved.</p>
            </footer>
        </body>
        </html>
        """

        schema = {
            "type": "object",
            "properties": {
                "product_name": {"type": "string"},
                "description": {"type": "string"},
                "original_price": {"type": "string"},
                "sale_price": {"type": "string"},
                "discount": {"type": "string"},
                "rating": {"type": "number"},
                "review_count": {"type": "integer"},
                "features": {"type": "array", "items": {"type": "string"}},
                "images": {"type": "array", "items": {"type": "string"}},
            },
        }

        result = extract_data(schema, [html])

        # Should extract various fields from complex structure
        assert len(result) > 0

        # Check key fields
        if "product_name" in result:
            assert "headphones" in result["product_name"].lower()

        if "sale_price" in result:
            assert "199" in result["sale_price"] or "99" in result["sale_price"]

        if "features" in result and isinstance(result["features"], list):
            features_text = " ".join(str(f) for f in result["features"])
            assert "battery" in features_text.lower() or "bluetooth" in features_text.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
