"""Async Browser Pool for Scry.

Maintains a pool of pre-launched Playwright browser instances to eliminate
cold-start latency. Uses async Playwright API which is the recommended approach
for applications running in async contexts (like FastAPI/MCP servers).

Performance improvement:
- Without pool: ~3-5 seconds browser launch per request
- With pool: ~50ms context creation (browser already running)

Why async Playwright:
- Sync Playwright has thread affinity (operations must happen in creating thread)
- Async Playwright has no thread affinity - browsers can be used from any coroutine
- This is the recommended approach from Playwright maintainers

See: https://github.com/microsoft/playwright-python/issues/462
"""

from __future__ import annotations

import asyncio
import atexit
import os
import time
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from playwright.async_api import Browser, Playwright, async_playwright

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@dataclass
class PooledBrowser:
    """A browser instance managed by the pool."""

    browser: Browser
    playwright: Playwright
    created_at: float = field(default_factory=time.time)
    request_count: int = 0
    in_use: bool = False


@dataclass
class BrowserPoolConfig:
    """Configuration for the browser pool."""

    pool_size: int = int(os.getenv("BROWSER_POOL_SIZE", "2"))
    max_requests_per_browser: int = int(os.getenv("BROWSER_MAX_REQUESTS", "100"))
    browser_max_age_seconds: int = int(os.getenv("BROWSER_MAX_AGE", "3600"))  # 1 hour
    headless: bool = os.getenv("HEADLESS", "true").lower() in {"true", "1", "yes"}
    health_check_interval: int = int(os.getenv("BROWSER_HEALTH_CHECK_INTERVAL", "60"))


class AsyncBrowserPool:
    """Async pool of pre-launched Playwright browser instances.

    Usage:
        pool = await AsyncBrowserPool.get_instance()
        async with pool.acquire() as (browser, playwright):
            context = await browser.new_context()
            page = await context.new_page()
            # ... do work ...
            await context.close()
    """

    _instance: AsyncBrowserPool | None = None
    _lock: asyncio.Lock | None = None

    def __init__(self, config: BrowserPoolConfig | None = None) -> None:
        self.config = config or BrowserPoolConfig()
        self._pool: asyncio.Queue[PooledBrowser] = asyncio.Queue()
        self._all_browsers: list[PooledBrowser] = []
        self._pool_lock = asyncio.Lock()
        self._initialized = False
        self._shutting_down = False
        self._health_task: asyncio.Task | None = None

    @classmethod
    async def get_instance(cls, config: BrowserPoolConfig | None = None) -> AsyncBrowserPool:
        """Get or create the singleton browser pool instance."""
        if cls._lock is None:
            cls._lock = asyncio.Lock()

        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = AsyncBrowserPool(config)
                    await cls._instance.initialize()
        return cls._instance

    async def initialize(self) -> None:
        """Initialize the browser pool with pre-launched browsers."""
        if self._initialized:
            return

        async with self._pool_lock:
            if self._initialized:
                return

            print(f"[BrowserPool] Initializing async pool with {self.config.pool_size} browsers")
            start = time.perf_counter()

            # Create browsers concurrently for faster initialization
            tasks = [self._create_browser() for _ in range(self.config.pool_size)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(results):
                if isinstance(result, BaseException):
                    print(f"[BrowserPool] Failed to create browser {i + 1}: {result}")
                else:
                    self._all_browsers.append(result)
                    await self._pool.put(result)
                    print(f"[BrowserPool] Browser {i + 1}/{self.config.pool_size} ready")

            elapsed = time.perf_counter() - start
            print(
                f"[BrowserPool] Pool initialized in {elapsed:.2f}s with {self._pool.qsize()} browsers"
            )

            self._initialized = True

            # Start health check task
            self._health_task = asyncio.create_task(self._health_check_loop())

            # Register cleanup on exit (sync wrapper for async shutdown)
            def sync_shutdown():
                try:
                    loop = asyncio.get_running_loop()
                    asyncio.run_coroutine_threadsafe(self.shutdown(), loop)
                except RuntimeError:
                    # No running loop, can't do async cleanup
                    pass

            atexit.register(sync_shutdown)

    async def _create_browser(self) -> PooledBrowser:
        """Create a new browser instance using async Playwright API."""
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=self.config.headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-extensions",
            ],
        )
        return PooledBrowser(browser=browser, playwright=playwright)

    def _is_browser_healthy(self, pooled: PooledBrowser) -> bool:
        """Check if a browser instance is still healthy."""
        try:
            # Check age
            age = time.time() - pooled.created_at
            if age > self.config.browser_max_age_seconds:
                print(f"[BrowserPool] Browser exceeded max age ({age:.0f}s)")
                return False

            # Check request count
            if pooled.request_count >= self.config.max_requests_per_browser:
                print(f"[BrowserPool] Browser exceeded max requests ({pooled.request_count})")
                return False

            # Check if browser is connected
            if not pooled.browser.is_connected():
                print("[BrowserPool] Browser disconnected")
                return False

            return True
        except Exception as e:
            print(f"[BrowserPool] Health check error: {e}")
            return False

    async def _close_browser(self, pooled: PooledBrowser) -> None:
        """Safely close a browser instance."""
        with suppress(Exception):
            await pooled.browser.close()
        with suppress(Exception):
            await pooled.playwright.stop()

    async def _health_check_loop(self) -> None:
        """Background task that checks browser health."""
        while not self._shutting_down:
            await asyncio.sleep(self.config.health_check_interval)
            if self._shutting_down:
                break
            await self._check_and_replace_unhealthy()

    async def _check_and_replace_unhealthy(self) -> None:
        """Check pool browsers and replace unhealthy ones."""
        async with self._pool_lock:
            # Collect browsers that need replacement
            healthy_browsers: list[PooledBrowser] = []
            unhealthy_browsers: list[PooledBrowser] = []

            # Drain the queue to check all browsers
            while not self._pool.empty():
                try:
                    pooled = self._pool.get_nowait()
                    if self._is_browser_healthy(pooled):
                        healthy_browsers.append(pooled)
                    else:
                        unhealthy_browsers.append(pooled)
                except asyncio.QueueEmpty:
                    break

            # Close unhealthy browsers
            for pooled in unhealthy_browsers:
                await self._close_browser(pooled)
                if pooled in self._all_browsers:
                    self._all_browsers.remove(pooled)

            # Put healthy browsers back
            for pooled in healthy_browsers:
                await self._pool.put(pooled)

            # Create replacements for unhealthy browsers
            replacements_needed = self.config.pool_size - len(healthy_browsers)
            for _ in range(replacements_needed):
                try:
                    pooled = await self._create_browser()
                    self._all_browsers.append(pooled)
                    await self._pool.put(pooled)
                    print("[BrowserPool] Replaced unhealthy browser")
                except Exception as e:
                    print(f"[BrowserPool] Failed to create replacement browser: {e}")

    @asynccontextmanager
    async def acquire(
        self, timeout: float = 30.0
    ) -> AsyncGenerator[tuple[Browser, Playwright], None]:
        """Acquire a browser from the pool.

        Args:
            timeout: Maximum time to wait for a browser (seconds)

        Yields:
            Tuple of (Browser, Playwright) instances

        Raises:
            TimeoutError: If no browser available within timeout
        """
        if not self._initialized:
            await self.initialize()

        pooled: PooledBrowser | None = None
        try:
            # Get a browser from the pool
            try:
                pooled = await asyncio.wait_for(self._pool.get(), timeout=timeout)
            except TimeoutError:
                raise TimeoutError(f"No browser available within {timeout}s") from None

            # Mark as in use
            pooled.in_use = True
            pooled.request_count += 1

            # Check health before use
            if not self._is_browser_healthy(pooled):
                print("[BrowserPool] Acquired browser unhealthy, creating replacement")
                await self._close_browser(pooled)
                async with self._pool_lock:
                    if pooled in self._all_browsers:
                        self._all_browsers.remove(pooled)
                pooled = await self._create_browser()
                async with self._pool_lock:
                    self._all_browsers.append(pooled)
                pooled.in_use = True
                pooled.request_count = 1

            yield pooled.browser, pooled.playwright

        finally:
            if pooled is not None:
                pooled.in_use = False
                # Return to pool if still healthy
                if self._is_browser_healthy(pooled):
                    await self._pool.put(pooled)
                else:
                    # Replace unhealthy browser
                    print("[BrowserPool] Releasing unhealthy browser, creating replacement")
                    await self._close_browser(pooled)
                    async with self._pool_lock:
                        if pooled in self._all_browsers:
                            self._all_browsers.remove(pooled)
                    try:
                        new_pooled = await self._create_browser()
                        async with self._pool_lock:
                            self._all_browsers.append(new_pooled)
                        await self._pool.put(new_pooled)
                    except Exception as e:
                        print(f"[BrowserPool] Failed to create replacement: {e}")

    async def shutdown(self) -> None:
        """Shutdown the browser pool and close all browsers."""
        print("[BrowserPool] Shutting down...")
        self._shutting_down = True

        # Cancel health check task
        if self._health_task:
            self._health_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._health_task

        async with self._pool_lock:
            # Drain the queue
            while not self._pool.empty():
                try:
                    self._pool.get_nowait()
                except asyncio.QueueEmpty:
                    break

            # Close all browsers
            for pooled in self._all_browsers:
                await self._close_browser(pooled)

            self._all_browsers.clear()
            self._initialized = False

        print("[BrowserPool] Shutdown complete")

    def stats(self) -> dict:
        """Get pool statistics."""
        return {
            "pool_size": self.config.pool_size,
            "available": self._pool.qsize(),
            "total_browsers": len(self._all_browsers),
            "in_use": sum(1 for b in self._all_browsers if b.in_use),
            "initialized": self._initialized,
        }


async def get_browser_pool() -> AsyncBrowserPool:
    """Get the global browser pool instance."""
    return await AsyncBrowserPool.get_instance()
