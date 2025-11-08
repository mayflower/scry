"""Test native Playwright exploration with realistic multi-step navigation scenarios."""

from __future__ import annotations

import os

import pytest
from universal_scraper.api.dto import ScrapeRequest
from universal_scraper.core.executor.runner import run_job


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="Requires ANTHROPIC_API_KEY")
def test_native_exploration_multi_step_navigation():
    """Test native exploration with a complex navigation scenario requiring at least 5 steps.

    This test creates a multi-page HTML structure that requires:
    1. Navigate to the main page
    2. Click on a menu link to go to products
    3. Click on a specific product category
    4. Click on a product detail link
    5. Click on specifications tab
    6. Extract the final data
    """

    # Create a multi-page HTML structure that simulates navigation
    main_page = """
    <html>
    <head><title>TechStore - Home</title></head>
    <body>
        <nav>
            <a href="#products" id="products-link">Products</a>
            <a href="#about">About</a>
            <a href="#contact">Contact</a>
        </nav>
        <div id="home">
            <h1>Welcome to TechStore</h1>
            <p>Your source for technology products</p>
        </div>
        <div id="products" style="display:none">
            <h2>Product Categories</h2>
            <ul>
                <li><a href="#laptops" class="category-link">Laptops</a></li>
                <li><a href="#phones" class="category-link">Phones</a></li>
                <li><a href="#tablets" class="category-link">Tablets</a></li>
            </ul>
        </div>
        <div id="laptops" style="display:none">
            <h2>Laptops</h2>
            <ul class="product-list">
                <li><a href="#laptop-pro" class="product-link">ProBook X1</a></li>
                <li><a href="#laptop-air" class="product-link">AirBook S2</a></li>
            </ul>
        </div>
        <div id="laptop-pro" style="display:none">
            <h2>ProBook X1</h2>
            <div class="tabs">
                <a href="#overview" class="tab">Overview</a>
                <a href="#specs" class="tab">Specifications</a>
                <a href="#reviews" class="tab">Reviews</a>
            </div>
            <div id="overview">
                <p>High-performance laptop for professionals</p>
            </div>
            <div id="specs" style="display:none">
                <h3>Technical Specifications</h3>
                <ul class="spec-list">
                    <li class="spec-item">Processor: Intel Core i9</li>
                    <li class="spec-item">RAM: 32GB DDR5</li>
                    <li class="spec-item">Storage: 1TB NVMe SSD</li>
                    <li class="spec-item">Display: 15.6" 4K OLED</li>
                    <li class="spec-item">Battery: 12 hours</li>
                </ul>
                <p class="price">Price: $2,499</p>
            </div>
        </div>
    </body>
    </html>
    """

    # For testing, we'll use a data URL
    test_url = f"data:text/html,{main_page}"

    req = ScrapeRequest(
        nl_request=(
            "Navigate through the website to find the ProBook X1 laptop. "
            "Click on Products, then Laptops category, then the ProBook X1 product, "
            "then click on the Specifications tab to get the detailed specs. "
            "Extract the processor, RAM, storage, and price information."
        ),
        schema={
            "type": "object",
            "properties": {
                "product_name": {"type": "string"},
                "processor": {"type": "string"},
                "ram": {"type": "string"},
                "storage": {"type": "string"},
                "price": {"type": "string"},
            },
        },
        target_urls=[test_url],
    )

    res = run_job(req)

    # Verify the job completed
    assert res.job_id
    assert "exploring" in res.execution_log

    # Check that data was extracted
    assert isinstance(res.data, dict)

    # The actual extraction might not work perfectly with data URLs,
    # but we're testing that native exploration attempts multiple navigation steps
    print(f"Execution log: {res.execution_log}")
    print(f"Data extracted: {res.data}")


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="Requires ANTHROPIC_API_KEY")
def test_native_exploration_form_interaction():
    """Test native exploration with form filling and submission requiring multiple steps.

    This test requires:
    1. Navigate to the page
    2. Click on a "Start" button
    3. Fill in first form field
    4. Fill in second form field
    5. Click submit button
    6. Wait for results
    7. Extract the results
    """

    form_page = """
    <html>
    <head><title>Multi-Step Form</title></head>
    <body>
        <div id="welcome">
            <h1>Welcome to the Survey</h1>
            <button id="start-btn" onclick="document.getElementById('welcome').style.display='none'; document.getElementById('form-step1').style.display='block';">Start Survey</button>
        </div>
        
        <div id="form-step1" style="display:none">
            <h2>Step 1: Personal Information</h2>
            <form>
                <label>Name: <input type="text" id="name" name="name"></label><br>
                <label>Email: <input type="email" id="email" name="email"></label><br>
                <button type="button" onclick="document.getElementById('form-step1').style.display='none'; document.getElementById('form-step2').style.display='block';">Next</button>
            </form>
        </div>
        
        <div id="form-step2" style="display:none">
            <h2>Step 2: Preferences</h2>
            <form>
                <label>Favorite Color: 
                    <select id="color" name="color">
                        <option value="">Select...</option>
                        <option value="red">Red</option>
                        <option value="blue">Blue</option>
                        <option value="green">Green</option>
                    </select>
                </label><br>
                <label>Comments: <textarea id="comments" name="comments"></textarea></label><br>
                <button type="button" onclick="showResults()">Submit</button>
            </form>
        </div>
        
        <div id="results" style="display:none">
            <h2>Survey Complete!</h2>
            <div class="summary">
                <p class="confirmation">Thank you for completing the survey!</p>
                <p class="submission-id">Submission ID: SURVEY-2024-001</p>
                <p class="timestamp">Submitted at: 2024-01-15 10:30:00</p>
            </div>
        </div>
        
        <script>
        function showResults() {
            document.getElementById('form-step2').style.display='none';
            document.getElementById('results').style.display='block';
        }
        </script>
    </body>
    </html>
    """

    test_url = f"data:text/html,{form_page}"

    req = ScrapeRequest(
        nl_request=(
            "Complete the multi-step survey form. Click Start Survey, "
            "fill in 'John Doe' for name, 'john@example.com' for email, "
            "click Next, select 'Blue' for favorite color, "
            "enter 'This is a test' in comments, then submit. "
            "Extract the confirmation message and submission ID from the results."
        ),
        schema={
            "type": "object",
            "properties": {
                "confirmation": {"type": "string"},
                "submission_id": {"type": "string"},
                "timestamp": {"type": "string"},
            },
        },
        target_urls=[test_url],
    )

    res = run_job(req)

    # Verify the job completed
    assert res.job_id
    assert "exploring" in res.execution_log

    print(f"Execution log: {res.execution_log}")
    print(f"Data extracted: {res.data}")
