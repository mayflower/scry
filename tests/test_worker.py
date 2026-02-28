"""Tests for worker and async processing."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from scry.api.dto import ScrapeRequest, ScrapeResponse
from scry.runtime.events import InMemoryBus
from scry.worker import _worker_loop, main


class TestWorker:
    """Test suite for worker functionality."""

    def test_worker_processes_job_successfully(self):
        """Test worker processes a job from queue."""
        bus = InMemoryBus()

        # Add a job to queue
        job_data = {
            "job_id": "test-123",
            "request": {
                "nl_request": "Extract title",
                "output_schema": {"type": "object"},
                "target_urls": ["https://example.com"],
            },
        }
        bus.enqueue(job_data)

        with patch("scry.worker.get_bus", return_value=bus):
            with patch("scry.worker.run_job_with_id") as mock_run:
                mock_run.return_value = ScrapeResponse(
                    job_id="test-123",
                    status="completed",
                    data={"title": "Test"},
                    execution_log=["done"],
                )

                # Run worker loop once
                with patch.object(bus, "dequeue") as mock_dequeue:
                    # First call returns job, then None to continue, then KeyboardInterrupt to exit
                    mock_dequeue.side_effect = [job_data, None, KeyboardInterrupt()]

                    # This should process one job and exit
                    try:
                        _worker_loop()
                    except KeyboardInterrupt:
                        pass

                # Check job was processed
                mock_run.assert_called_once()
                result = bus.get_result("test-123")
                assert result is not None
                assert result["status"] == "completed"

    def test_worker_handles_invalid_job_data(self):
        """Test worker handles malformed job data gracefully."""
        bus = InMemoryBus()

        # Add invalid job data
        invalid_job = {"invalid": "data"}
        bus.enqueue(invalid_job)

        with patch("scry.worker.get_bus", return_value=bus):
            with patch.object(bus, "dequeue") as mock_dequeue:
                mock_dequeue.side_effect = [invalid_job, None, KeyboardInterrupt()]

                # Should not crash, just continue
                try:
                    _worker_loop()
                except KeyboardInterrupt:
                    pass

                # No result should be set for invalid job
                assert bus.get_result("invalid") is None

    def test_worker_handles_execution_error(self):
        """Test worker handles job execution errors."""
        bus = InMemoryBus()

        job_data = {
            "job_id": "error-job",
            "request": {
                "nl_request": "Extract",
                "output_schema": {"type": "object"},
                "target_urls": ["https://example.com"],
            },
        }
        bus.enqueue(job_data)

        with patch("scry.worker.get_bus", return_value=bus):
            with patch("scry.worker.run_job_with_id") as mock_run:
                mock_run.side_effect = Exception("Execution failed")

                with patch.object(bus, "dequeue") as mock_dequeue:
                    mock_dequeue.side_effect = [job_data, None, KeyboardInterrupt()]

                    # Should handle exception and continue
                    try:
                        _worker_loop()
                    except KeyboardInterrupt:
                        pass

                # No result on error (worker swallows exceptions)
                assert bus.get_result("error-job") is None

    def test_worker_timeout_handling(self):
        """Test worker handles queue timeout properly."""
        bus = InMemoryBus()

        with patch("scry.worker.get_bus", return_value=bus):
            call_count = 0

            def dequeue_with_timeout(*_args, **_kwargs):
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    # Simulate timeout (returns None)
                    return
                # Exit after 2 timeouts
                raise KeyboardInterrupt("Test exit")

            with patch.object(bus, "dequeue", side_effect=dequeue_with_timeout):
                try:
                    _worker_loop()
                except KeyboardInterrupt:
                    pass

                # Should have called dequeue multiple times
                assert call_count == 3

    def test_worker_uses_job_id_when_present(self):
        """Test worker uses job_id from message when available."""
        bus = InMemoryBus()

        job_with_id = {
            "job_id": "specific-id",
            "request": {
                "nl_request": "Test",
                "output_schema": {"type": "object"},
                "target_urls": ["https://example.com"],
            },
        }
        bus.enqueue(job_with_id)

        with patch("scry.worker.get_bus", return_value=bus):
            with patch("scry.worker.run_job_with_id") as mock_with_id:
                with patch("scry.worker.run_job") as mock_without_id:
                    mock_with_id.return_value = ScrapeResponse(
                        job_id="specific-id",
                        status="completed",
                        data={},
                        execution_log=["done"],
                    )

                    with patch.object(bus, "dequeue") as mock_dequeue:
                        mock_dequeue.side_effect = [
                            job_with_id,
                            None,
                            KeyboardInterrupt(),
                        ]
                        try:
                            _worker_loop()
                        except KeyboardInterrupt:
                            pass

                    # Should use run_job_with_id when job_id present
                    mock_with_id.assert_called_once_with(
                        "specific-id", ScrapeRequest(**job_with_id["request"])
                    )
                    mock_without_id.assert_not_called()

    def test_worker_without_job_id(self):
        """Test worker uses run_job when no job_id."""
        bus = InMemoryBus()

        job_without_id = {
            "request": {
                "nl_request": "Test",
                "output_schema": {"type": "object"},
                "target_urls": ["https://example.com"],
            },
        }
        bus.enqueue(job_without_id)

        with patch("scry.worker.get_bus", return_value=bus):
            with patch("scry.worker.run_job") as mock_run:
                mock_run.return_value = ScrapeResponse(
                    job_id="auto-generated",
                    status="completed",
                    data={},
                    execution_log=["done"],
                )

                with patch.object(bus, "dequeue") as mock_dequeue:
                    mock_dequeue.side_effect = [
                        job_without_id,
                        None,
                        KeyboardInterrupt(),
                    ]
                    try:
                        _worker_loop()
                    except KeyboardInterrupt:
                        pass

                # Should use run_job when no job_id
                mock_run.assert_called_once()

    def test_main_spawns_worker_threads(self):
        """Test main function spawns correct number of threads - INTEGRATION TEST."""
        with patch.dict("os.environ", {"WORKER_CONCURRENCY": "3"}):
            # Track the number of _worker_loop calls
            call_count = 0

            def mock_worker_loop():
                nonlocal call_count
                call_count += 1
                # Exit immediately
                return

            with patch("scry.worker._worker_loop", side_effect=mock_worker_loop):
                # Start main in a thread
                main_thread = threading.Thread(target=main, daemon=True)
                main_thread.start()

                # Give threads time to start
                time.sleep(0.1)

                # Since _worker_loop exits immediately, threads should finish quickly
                main_thread.join(timeout=1.0)

                # Check that _worker_loop was called 3 times
                assert call_count == 3

    def test_worker_concurrency_default(self):
        """Test worker uses default concurrency when not set."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("threading.Thread") as mock_thread:
                mock_thread_instance = MagicMock()
                mock_thread.return_value = mock_thread_instance
                mock_thread_instance.join.return_value = None

                main_thread = threading.Thread(target=main)
                main_thread.daemon = True
                main_thread.start()
                time.sleep(0.1)

                # Should create 1 thread by default
                assert mock_thread.call_count == 1

    def test_worker_result_serialization(self):
        """Test worker properly serializes results."""
        bus = InMemoryBus()

        job_data = {
            "job_id": "serialize-test",
            "request": {
                "nl_request": "Test",
                "output_schema": {"type": "object"},
                "target_urls": ["https://example.com"],
            },
        }
        bus.enqueue(job_data)

        with patch("scry.worker.get_bus", return_value=bus):
            with patch("scry.worker.run_job_with_id") as mock_run:
                # Return response with complex data
                mock_run.return_value = ScrapeResponse(
                    job_id="serialize-test",
                    status="completed",
                    data={
                        "nested": {"value": 123},
                        "list": [1, 2, 3],
                        "text": "Test string",
                    },
                    execution_log=["step1", "step2", "done"],
                )

                with patch.object(bus, "dequeue") as mock_dequeue:
                    mock_dequeue.side_effect = [job_data, None, KeyboardInterrupt()]
                    try:
                        _worker_loop()
                    except KeyboardInterrupt:
                        pass

                result = bus.get_result("serialize-test")
                assert result is not None

                # Check data is properly serialized
                assert result["data"]["nested"]["value"] == 123
                assert result["data"]["list"] == [1, 2, 3]
                assert len(result["execution_log"]) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
