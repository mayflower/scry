"""FastMCP 2.0 server for Scry browser agent.

Exposes the full browser automation capability as an MCP tool with real-time
progress streaming via ctx.report_progress(). Includes:
- LLM-driven exploration
- Path optimization
- Code generation
- Self-healing execution loop
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import TYPE_CHECKING, Any

from fastmcp import Context, FastMCP
from starlette.responses import JSONResponse

from .api.dto import ScrapeRequest
from .core.executor.runner import run_job_with_id

if TYPE_CHECKING:
    from starlette.requests import Request

# Configure logging to show INFO level (required for telemetry messages)
logging.basicConfig(level=logging.INFO)

mcp = FastMCP(name="scry-browser")


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:  # noqa: ARG001
    """Health check endpoint for Kubernetes probes."""
    return JSONResponse({"status": "healthy", "service": "scry-mcp"})


def _build_login_params(username: str | None, password: str | None) -> dict[str, str] | None:
    """Build login params dict if credentials are provided."""
    if username and password:
        return {"username": username, "password": password}
    return None


def _build_result_text_parts(result: Any) -> list[str]:
    """Build text content parts from scrape result."""
    parts = [
        f"Browser task completed (job: {result.job_id}, status: {result.status})",
        f"Execution: {' → '.join(result.execution_log)}",
    ]
    if result.data:
        parts.append(f"\nExtracted data:\n```json\n{json.dumps(result.data, indent=2)}\n```")
    return parts


@mcp.tool
async def browser(
    url: str,
    task: str,
    output_schema: dict[str, Any],
    ctx: Context,
    login_username: str | None = None,
    login_password: str | None = None,
    max_steps: int = 20,
):
    """Automate browser tasks using LLM-driven exploration and code generation.

    Use this tool for web scraping, form filling, and browser automation tasks.
    The agent will:
    1. Explore the page using screenshots and LLM decisions
    2. Optimize the discovered navigation path
    3. Generate executable Playwright code
    4. Execute with self-healing on failures

    Progress updates including screenshots are streamed in real-time.

    Args:
        url: The starting URL to navigate to
        task: Natural language description of what to accomplish
        output_schema: JSON schema describing expected output data structure
        ctx: FastMCP context for progress reporting (automatically provided)
        login_username: Optional username for form-based login
        login_password: Optional password for form-based login
        max_steps: Maximum exploration steps (default 20)

    Returns:
        dict containing extracted data, execution log, and job metadata
    """
    job_id = str(uuid.uuid4())

    # Set MAX_EXPLORATION_STEPS env var for the runner
    os.environ["MAX_EXPLORATION_STEPS"] = str(max_steps)

    # Build the ScrapeRequest (using alias 'schema' for output_schema field)
    request = ScrapeRequest(
        nl_request=task,
        schema=output_schema,
        example=None,
        login_params=_build_login_params(login_username, login_password),
        parameters=None,
        target_urls=[url],
    )

    # Track progress steps and latest screenshot for the callback
    callback_state: dict[str, int | str | None] = {"step": -1, "last_screenshot_b64": None}

    def progress_callback(data: dict[str, Any]) -> None:
        """Sync callback that schedules async progress reporting and captures screenshots.

        Embeds screenshot data as JSON in the progress notification's message field.
        This approach works because:
        - Progress callbacks are request-scoped (tied to call_tool())
        - The message field is a string that can contain arbitrary JSON
        - Client parses JSON to extract screenshot, step, action, status
        """
        step = data.get("step", 0)

        # Capture the latest screenshot (always update, even on duplicate steps)
        screenshot = data.get("screenshot_b64")
        print(
            f"[MCP] progress_callback called: step={step}, has_screenshot={bool(screenshot)}, screenshot_len={len(screenshot) if screenshot else 0}"
        )
        if screenshot:
            callback_state["last_screenshot_b64"] = screenshot
            print(f"[MCP] Screenshot captured in callback_state: {len(screenshot)} bytes")

        # Avoid duplicate progress reports
        if step <= callback_state["step"]:
            return
        callback_state["step"] = step

        status = data.get("status", "working")
        action = data.get("action", "processing")

        # Build JSON payload with all progress data including screenshot
        progress_payload = {
            "step": step,
            "action": action,
            "status": status,
            "screenshot": screenshot or "",  # Empty string if no screenshot
        }

        # Schedule progress report on the event loop (fire-and-forget)
        try:
            loop = asyncio.get_running_loop()

            # Report progress with JSON payload in message field
            loop.create_task(  # noqa: RUF006
                ctx.report_progress(
                    progress=step,
                    total=data.get("max_steps", max_steps + 5),
                    message=json.dumps(progress_payload),
                )
            )

            if screenshot:
                print(
                    f"[MCP] Sending progress with screenshot: step={step}, "
                    f"screenshot_len={len(screenshot)}"
                )
        except Exception as e:
            print(f"[MCP] Progress report failed: {e}")

    # Run the full pipeline directly (async Playwright, no thread pool needed)
    result = await run_job_with_id(
        job_id,
        request,
        progress_callback,
    )

    # Report completion
    await ctx.report_progress(
        progress=max_steps + 5,
        total=max_steps + 5,
        message="completed",
    )

    final_screenshot = callback_state["last_screenshot_b64"]
    screenshot_len = len(str(final_screenshot)) if final_screenshot else 0
    print(f"[MCP] Returning result with screenshot: {bool(final_screenshot)}, len={screenshot_len}")

    # Import here to avoid linter removing "unused" imports at module level
    from fastmcp.tools.tool import ToolResult  # noqa: PLC0415
    from mcp.types import ImageContent, TextContent  # noqa: PLC0415

    # Build content blocks for the response
    text_parts = _build_result_text_parts(result)
    content_blocks: list[TextContent | ImageContent] = [
        TextContent(
            type="text",
            text="\n".join(text_parts),
        )
    ]

    # Add screenshot as ImageContent if available
    if final_screenshot:
        content_blocks.append(
            ImageContent(
                type="image",
                data=str(final_screenshot),
                mimeType="image/png",
            )
        )

    # Return ToolResult with both content blocks and structured data
    return ToolResult(
        content=content_blocks,
        structured_content={
            "job_id": result.job_id,
            "data": result.data if result.data else {},
            "execution_log": result.execution_log,
            "status": result.status,
        },
    )


def main() -> None:
    """Run the MCP server with streamable-http transport."""
    # Initialize OpenTelemetry tracing (if enabled)
    from .telemetry import init_telemetry

    init_telemetry()

    port = int(os.getenv("MCP_PORT", "8085"))
    host = os.getenv("MCP_HOST", "0.0.0.0")  # nosec B104 - Docker container binding

    print(f"[Scry MCP] Starting server on {host}:{port}/mcp")
    mcp.run(transport="streamable-http", host=host, port=port, path="/mcp")


if __name__ == "__main__":
    main()
