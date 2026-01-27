"""Integration tests for event bus (InMemory and Redis)."""

from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from scry.runtime.events import InMemoryBus, RedisBus, get_bus


class TestInMemoryBus:
    """Integration tests for InMemoryBus."""

    def test_enqueue_and_dequeue(self):
        """Test basic enqueue and dequeue operations."""
        bus = InMemoryBus()

        # Test enqueue
        payload = {"job_id": "test-123", "data": "test data"}
        bus.enqueue(payload)

        # Test dequeue
        result = bus.dequeue(timeout=1)
        assert result is not None
        assert result["job_id"] == "test-123"
        assert result["data"] == "test data"

        # Test timeout when queue is empty
        result = bus.dequeue(timeout=0.1)
        assert result is None

    def test_multiple_messages(self):
        """Test queueing multiple messages."""
        bus = InMemoryBus()

        # Enqueue multiple messages
        for i in range(5):
            bus.enqueue({"id": i, "message": f"msg_{i}"})

        # Dequeue all messages
        messages = []
        for _ in range(5):
            msg = bus.dequeue(timeout=0.1)
            if msg:
                messages.append(msg)

        assert len(messages) == 5
        # Check FIFO order
        for i, msg in enumerate(messages):
            assert msg["id"] == i
            assert msg["message"] == f"msg_{i}"

    def test_result_storage_and_retrieval(self):
        """Test storing and retrieving job results."""
        bus = InMemoryBus()

        # Store results
        job1_result = {"status": "completed", "data": {"value": 1}}
        job2_result = {"status": "failed", "error": "Test error"}

        bus.set_result("job1", job1_result)
        bus.set_result("job2", job2_result)

        # Retrieve results
        assert bus.get_result("job1") == job1_result
        assert bus.get_result("job2") == job2_result

        # Non-existent job
        assert bus.get_result("non-existent") is None

    def test_thread_safety(self):
        """Test thread safety of InMemoryBus."""
        bus = InMemoryBus()
        results = []

        def producer(start, count):
            """Producer thread that enqueues messages."""
            for i in range(start, start + count):
                bus.enqueue({"id": i})
                time.sleep(0.001)  # Small delay to simulate work

        def consumer():
            """Consumer thread that dequeues messages."""
            while True:
                msg = bus.dequeue(timeout=0.1)
                if msg is None:
                    break
                results.append(msg["id"])

        # Start multiple producers
        with ThreadPoolExecutor(max_workers=5) as executor:
            # 3 producers, each adding 10 messages
            futures = []
            futures.append(executor.submit(producer, 0, 10))
            futures.append(executor.submit(producer, 10, 10))
            futures.append(executor.submit(producer, 20, 10))

            # Wait a bit for producers to start
            time.sleep(0.05)

            # 2 consumers
            futures.append(executor.submit(consumer))
            futures.append(executor.submit(consumer))

            # Wait for all to complete
            for future in futures:
                future.result()

        # Should have all 30 messages
        assert len(results) == 30
        assert set(results) == set(range(30))

    def test_concurrent_result_access(self):
        """Test concurrent access to results."""
        bus = InMemoryBus()

        def set_results():
            """Thread that sets results."""
            for i in range(100):
                bus.set_result(f"job_{i}", {"value": i})
                time.sleep(0.0001)

        def get_results(output_list):
            """Thread that gets results."""
            for i in range(100):
                result = bus.get_result(f"job_{i}")
                if result:
                    output_list.append(result["value"])
                time.sleep(0.0001)

        list1 = []
        list2 = []

        # Run setter and getters concurrently
        threads = [
            threading.Thread(target=set_results),
            threading.Thread(target=get_results, args=(list1,)),
            threading.Thread(target=get_results, args=(list2,)),
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # Both getters should see some results
        assert len(list1) > 0
        assert len(list2) > 0

    def test_complex_payloads(self):
        """Test with complex nested payloads."""
        bus = InMemoryBus()

        complex_payload = {
            "job_id": "complex-123",
            "request": {
                "nl_request": "Extract data",
                "schema": {
                    "type": "object",
                    "properties": {
                        "nested": {
                            "type": "object",
                            "properties": {"deep": {"type": "array", "items": {"type": "string"}}},
                        }
                    },
                },
                "target_urls": ["https://example.com", "https://test.com"],
            },
            "metadata": {
                "timestamp": "2024-01-01T00:00:00Z",
                "user_id": 12345,
                "tags": ["test", "complex", "nested"],
            },
        }

        bus.enqueue(complex_payload)
        result = bus.dequeue(timeout=1)

        # Should preserve complex structure
        assert result == complex_payload
        assert result["request"]["schema"]["properties"]["nested"]["type"] == "object"
        assert len(result["metadata"]["tags"]) == 3


class TestRedisBus:
    """Integration tests for RedisBus (requires Redis)."""

    @pytest.fixture
    def redis_available(self):
        """Check if Redis is available."""
        try:
            import redis

            r = redis.Redis.from_url("redis://localhost:6379", socket_connect_timeout=1)
            r.ping()
            return True
        except Exception:
            return False

    @pytest.mark.skipif(
        not os.getenv("REDIS_URL"),
        reason="Redis not configured (set REDIS_URL to test)",
    )
    def test_redis_basic_operations(self, redis_available):
        """Test basic Redis bus operations."""
        if not redis_available:
            pytest.skip("Redis not available")

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        bus = RedisBus(redis_url)

        # Clear any existing messages
        try:
            while bus.dequeue(timeout=0.1):
                pass
        except Exception:
            pass

        # Test enqueue and dequeue
        payload = {"job_id": "redis-test", "data": "test"}
        bus.enqueue(payload)

        result = bus.dequeue(timeout=2)
        assert result is not None
        assert result["job_id"] == "redis-test"

    @pytest.mark.skipif(
        not os.getenv("REDIS_URL"),
        reason="Redis not configured",
    )
    def test_redis_result_storage(self, redis_available):
        """Test Redis result storage."""
        if not redis_available:
            pytest.skip("Redis not available")

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        bus = RedisBus(redis_url)

        # Store and retrieve result
        job_result = {"status": "completed", "data": {"test": True}}
        bus.set_result("redis-job-1", job_result)

        retrieved = bus.get_result("redis-job-1")
        assert retrieved == job_result


class TestGetBus:
    """Test the get_bus factory function."""

    def test_get_inmemory_bus(self):
        """Test getting InMemory bus."""
        with patch.dict("os.environ", {"EVENT_BACKEND": "inmemory"}):
            bus = get_bus()
            assert isinstance(bus, InMemoryBus)

    def test_get_redis_bus(self):
        """Test getting Redis bus."""
        with patch.dict(
            "os.environ",
            {"EVENT_BACKEND": "redis", "REDIS_URL": "redis://localhost:6379"},
        ):
            try:
                bus = get_bus()
                assert isinstance(bus, RedisBus)
            except ImportError:
                # Redis library not installed
                pass

    def test_default_bus(self):
        """Test default bus selection."""
        with patch.dict("os.environ", {}, clear=True):
            bus = get_bus()
            # Should default to InMemory
            assert isinstance(bus, InMemoryBus)

    def test_singleton_behavior(self):
        """Test that get_bus returns the same instance."""
        with patch.dict("os.environ", {"EVENT_BACKEND": "inmemory"}):
            bus1 = get_bus()
            bus2 = get_bus()
            assert bus1 is bus2  # Same instance


class TestEndToEndFlow:
    """Test complete flow with event bus."""

    def test_job_submission_and_retrieval(self):
        """Test submitting a job and retrieving results."""
        bus = InMemoryBus()

        # Simulate API submitting a job
        job_request = {
            "job_id": "e2e-test",
            "request": {
                "nl_request": "Extract title",
                "output_schema": {"type": "object"},
                "target_urls": ["https://example.com"],
            },
        }
        bus.enqueue(job_request)

        # Simulate worker processing
        job = bus.dequeue(timeout=1)
        assert job is not None
        assert job["job_id"] == "e2e-test"

        # Worker sets result
        job_result = {
            "job_id": "e2e-test",
            "status": "completed",
            "data": {"title": "Example Page"},
            "execution_log": ["received", "processed", "done"],
        }
        bus.set_result(job["job_id"], job_result)

        # API retrieves result
        result = bus.get_result("e2e-test")
        assert result is not None
        assert result["status"] == "completed"
        assert result["data"]["title"] == "Example Page"

    def test_multiple_concurrent_jobs(self):
        """Test handling multiple jobs concurrently."""
        bus = InMemoryBus()
        job_count = 10

        # Submit multiple jobs
        for i in range(job_count):
            bus.enqueue(
                {
                    "job_id": f"concurrent-{i}",
                    "request": {"data": i},
                }
            )

        # Process all jobs
        processed = []
        while True:
            job = bus.dequeue(timeout=0.1)
            if not job:
                break

            # "Process" the job
            result = {
                "job_id": job["job_id"],
                "result": job["request"]["data"] * 2,
            }
            bus.set_result(job["job_id"], result)
            processed.append(job["job_id"])

        assert len(processed) == job_count

        # Verify all results
        for i in range(job_count):
            result = bus.get_result(f"concurrent-{i}")
            assert result is not None
            assert result["result"] == i * 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
