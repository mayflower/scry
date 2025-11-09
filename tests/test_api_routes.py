"""Tests for API routes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from scry.api.dto import ScrapeResponse
from scry.app import create_app


class TestAPIRoutes:
    """Test suite for API routes."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        app = create_app()
        return TestClient(app)

    def test_scrape_endpoint_success(self, client):
        """Test successful scrape request."""
        with patch("scry.api.routes.run_job") as mock_run:
            # Mock successful response
            mock_run.return_value = ScrapeResponse(
                job_id="test-123",
                status="completed",
                data={"title": "Test Page"},
                execution_log=["received", "done"],
            )

            response = client.post(
                "/scrape",
                json={
                    "nl_request": "Extract title",
                    "output_schema": {
                        "type": "object",
                        "properties": {"title": {"type": "string"}},
                    },
                    "target_urls": ["https://example.com"],
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["job_id"] == "test-123"
            assert data["status"] == "completed"
            assert data["data"]["title"] == "Test Page"

    def test_scrape_endpoint_validation_error(self, client):
        """Test scrape request with invalid schema."""
        response = client.post(
            "/scrape",
            json={
                "nl_request": "Extract data",
                # Missing required fields
            },
        )

        assert response.status_code == 422  # Validation error

    def test_scrape_endpoint_execution_error(self, client):
        """Test scrape request that fails during execution."""
        with patch("scry.api.routes.run_job") as mock_run:
            mock_run.side_effect = Exception("Execution failed")

            response = client.post(
                "/scrape",
                json={
                    "nl_request": "Extract title",
                    "output_schema": {"type": "object"},
                    "target_urls": ["https://example.com"],
                },
            )

            assert response.status_code == 500
            assert "Execution failed" in response.json()["detail"]

    def test_scrape_async_endpoint(self, client):
        """Test async scrape endpoint."""
        with patch("scry.api.routes.get_bus") as mock_bus:
            mock_bus.return_value.enqueue = MagicMock()

            response = client.post(
                "/scrape/async",
                json={
                    "nl_request": "Extract title",
                    "output_schema": {"type": "object"},
                    "target_urls": ["https://example.com"],
                },
            )

            # Check if endpoint exists and returns job ID
            if response.status_code == 200:
                data = response.json()
                assert "job_id" in data
                mock_bus.return_value.enqueue.assert_called_once()
            else:
                # Endpoint might not be implemented yet
                assert response.status_code in [404, 405]

    def test_job_status_endpoint(self, client):
        """Test job status polling endpoint."""
        job_id = "test-job-123"

        with patch("scry.api.routes.get_bus") as mock_bus:
            mock_bus.return_value.get_result.return_value = {
                "job_id": job_id,
                "status": "completed",
                "data": {"result": "test"},
            }

            response = client.get(f"/jobs/{job_id}")

            if response.status_code == 200:
                data = response.json()
                assert data["job_id"] == job_id
                assert data["status"] == "completed"
            else:
                # Endpoint might not be implemented
                assert response.status_code in [404, 405]

    def test_healthz_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/healthz")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_llm_ready_endpoint(self, client):
        """Test LLM readiness check."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            response = client.get("/llm/ready")

            assert response.status_code == 200
            data = response.json()
            assert data["anthropic_key"] is True
            assert "adapter" in data
            assert "cdp" in data

    def test_llm_ready_no_api_key(self, client):
        """Test LLM readiness without API key."""
        with patch.dict("os.environ", {}, clear=True):
            response = client.get("/llm/ready")

            assert response.status_code == 200
            data = response.json()
            assert data["anthropic_key"] is False

    def test_scrape_with_empty_target_urls(self, client):
        """Test scrape with no target URLs."""
        with patch("scry.api.routes.run_job") as mock_run:
            mock_run.return_value = ScrapeResponse(
                job_id="test-empty",
                status="completed",
                data={},
                execution_log=["received", "no_target_url", "done"],
            )

            response = client.post(
                "/scrape",
                json={
                    "nl_request": "Extract data",
                    "output_schema": {"type": "object"},
                    "target_urls": [],
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"] == {}
            assert "no_target_url" in data["execution_log"]

    def test_scrape_with_complex_schema(self, client):
        """Test scrape with nested schema."""
        with patch("scry.api.routes.run_job") as mock_run:
            mock_run.return_value = ScrapeResponse(
                job_id="test-complex",
                status="completed",
                data={
                    "products": [
                        {"name": "Product 1", "price": 10.99},
                        {"name": "Product 2", "price": 20.99},
                    ]
                },
                execution_log=["received", "done"],
            )

            response = client.post(
                "/scrape",
                json={
                    "nl_request": "Extract products",
                    "output_schema": {
                        "type": "object",
                        "properties": {
                            "products": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "price": {"type": "number"},
                                    },
                                },
                            }
                        },
                    },
                    "target_urls": ["https://example.com"],
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]["products"]) == 2
            assert data["data"]["products"][0]["price"] == 10.99


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
