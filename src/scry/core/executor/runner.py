"""Job execution with exploration, code generation, and self-healing."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ...api.dto import ScrapeRequest, ScrapeResponse
from ...config.settings import settings
from ...runtime.storage import data_artifact_path, job_artifact_paths
from ..codegen.generator import generate_script
from ..extractor.extract import extract_data
from ..self_heal.diagnose import propose_patch
from ..self_heal.patch import merge_codegen_options

if TYPE_CHECKING:
    from ...adapters.playwright_explorer import ExplorationResult
    from ..ir.model import ScrapePlan

logger = logging.getLogger(__name__)

# --- Helper Functions ---


def _emit_exploration_progress(
    progress_callback: Any | None,
    max_exploration_steps: int,
    start_url: str,
) -> None:
    """Emit progress notification for post-exploration phase."""
    if not progress_callback:
        return
    try:
        progress_callback(
            {
                "step": max_exploration_steps,
                "max_steps": max_exploration_steps + 5,
                "action": "exploration_complete",
                "url": start_url,
                "status": "optimizing",
            }
        )
    except Exception:
        logger.debug("Progress callback failed, continuing execution")


def _optimize_exploration_path(
    res: ExplorationResult,
    start_url: str,
    nl_request: str,
    output_schema: dict[str, Any],
    execution_log: list[str],
) -> ScrapePlan:
    """Optimize exploration results into an IR ScrapePlan."""
    if res.steps:
        from ..optimizer.optimize import compress_min_path_with_anthropic

        execution_log.append("optimizing")
        opt = compress_min_path_with_anthropic(res, nl_request, output_schema)
        execution_log.append("path_compressed")
        return opt

    # If no steps from exploration, create minimal IR
    from ..ir.model import Navigate, ScrapePlan

    return ScrapePlan(steps=[Navigate(url=start_url)], notes="minimal plan")


def _synthesize_extraction_selectors(
    res: ExplorationResult,
    nl_request: str,
    parameters: dict[str, Any] | None,
    output_schema: dict[str, Any],
    start_url: str,
    execution_log: list[str],
) -> dict[str, Any]:
    """Synthesize extraction selectors from exploration HTML."""
    if not res.html_pages or len(res.html_pages) == 0:
        return {}

    from ..extractor.selector_plan import synthesize_selectors

    execution_log.append("synthesizing_selectors")
    extraction_spec = synthesize_selectors(
        nl_request,
        parameters,
        output_schema,
        res.html_pages[0],
        url=start_url,
    )
    if extraction_spec:
        execution_log.append("selectors_ready")
    return extraction_spec


def _run_script_once(script_path: Path) -> subprocess.CompletedProcess[str]:
    """Execute generated script and return result."""
    return subprocess.run(
        [sys.executable, str(script_path)],
        check=False,
        capture_output=True,
        text=True,
    )


def _handle_validation_failure(
    script_result: subprocess.CompletedProcess[str],
) -> str | None:
    """Extract validation error from script output."""
    if script_result.stderr and "CRITICAL validation failed:" in script_result.stderr:
        return script_result.stderr
    if script_result.stdout and "CRITICAL validation failed:" in script_result.stdout:
        return script_result.stdout
    return None


def _should_retry_validation(
    script_result: subprocess.CompletedProcess[str],
    attempt: int,
    execution_log: list[str],
) -> tuple[bool, str | None]:
    """Check if validation failure should trigger retry.

    Returns:
        Tuple of (should_retry, error_message).
    """
    execution_log.append("validation_failed")
    validation_error = _handle_validation_failure(script_result)

    if attempt + 1 < settings.max_repair_attempts:
        error_msg = validation_error or script_result.stderr or "Validation checkpoint failed"
        return True, error_msg

    execution_log.append("validation_repair_exhausted")
    return False, None


def _handle_script_error(
    error: subprocess.CalledProcessError,
    attempt: int,
    execution_log: list[str],
) -> tuple[bool, str | None]:
    """Handle script execution error and determine if retry is needed.

    Returns:
        Tuple of (should_retry, error_message).
    """
    if attempt + 1 >= settings.max_repair_attempts:
        execution_log.append("script_failed")
        return False, None
    return True, error.stderr


def _handle_script_result(
    script_result: subprocess.CompletedProcess[str],
    attempt: int,
    execution_log: list[str],
) -> tuple[bool, str | None]:
    """Handle script execution result.

    Returns:
        Tuple of (should_continue_loop, error_for_patch).
        should_continue_loop=True means retry, False means exit loop.
    """
    # Handle validation failure (exit code 1)
    if script_result.returncode == 1:
        should_retry, error_msg = _should_retry_validation(script_result, attempt, execution_log)
        if should_retry and error_msg:
            return True, error_msg
        return False, None

    # Handle other non-zero exit codes
    if script_result.returncode != 0:
        raise subprocess.CalledProcessError(
            script_result.returncode,
            script_result.args,
            script_result.stdout,
            script_result.stderr,
        )

    # Success
    execution_log.append("script_done")
    return False, None


def _execute_with_self_healing(
    opt: ScrapePlan,
    job_id: str,
    artifacts_root: Path,
    extraction_spec: dict[str, Any],
    execution_log: list[str],
    progress_callback: Any | None = None,
    max_exploration_steps: int = 20,
) -> None:
    """Execute generated script with self-healing retry loop."""
    options: dict[str, Any] = {"extraction_spec": extraction_spec}

    for attempt in range(max(1, settings.max_repair_attempts)):
        execution_log.append("codegen" if attempt == 0 else f"repair_attempt_{attempt}")

        if progress_callback:
            try:
                progress_callback({
                    "step": max_exploration_steps + attempt + 1,
                    "max_steps": max_exploration_steps + 5,
                    "action": "codegen" if attempt == 0 else f"repair_attempt_{attempt}",
                    "status": "executing",
                })
            except Exception:
                logger.debug("Progress callback failed during codegen attempt %d", attempt)

        script_path = generate_script(
            opt, job_id, artifacts_root, settings.headless, options=options
        )
        execution_log.append("executing_script")

        try:
            script_result = _run_script_once(script_path)
            should_continue, error_msg = _handle_script_result(
                script_result, attempt, execution_log
            )
        except subprocess.CalledProcessError as e:
            should_continue, error_msg = _handle_script_error(e, attempt, execution_log)

        if should_continue and error_msg:
            patch = propose_patch(attempt + 1, error_msg, None)
            options = merge_codegen_options(options, patch)
            continue
        break


def _load_extracted_data(artifacts_root: Path, job_id: str, req: ScrapeRequest) -> dict[str, Any]:
    """Load extracted data from artifacts."""
    data_file = data_artifact_path(artifacts_root, job_id)
    if data_file.exists():
        try:
            import json

            return json.loads(data_file.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: S110 - fallback to artifact extraction
            print(f"[Runner] Warning: Failed to load {data_file}, falling back to extraction: {e}")
    return _finalize_from_artifacts(job_id, req)


def _check_schema_empty(data: dict[str, Any], output_schema: dict[str, Any]) -> bool:
    """Check if primary schema array fields are empty."""
    if not data or not output_schema:
        return False

    props = output_schema.get("properties", {})
    for key, spec in props.items():
        if spec.get("type") != "array":
            continue
        value = data.get(key)
        if not value:
            return True
        if isinstance(value, list) and len(value) == 0:
            return True
        if isinstance(value, str) and not value.strip():
            return True
    return False


def _normalize_value(v: Any) -> Any:
    """Normalize value for comparison."""
    if isinstance(v, str):
        return v.strip()
    return v


def _validate_against_exploration(
    data: dict[str, Any] | None,
    exploration_data: dict[str, Any] | None,
    execution_log: list[str],
) -> None:
    """Validate extracted data against exploration data."""
    if not isinstance(exploration_data, dict) or not exploration_data:
        return

    try:
        mismatch = False
        for k, v in (data or {}).items():
            ev = exploration_data.get(k)
            if ev is None:
                continue
            if isinstance(v, (int, float)) and isinstance(ev, (int, float)):
                if v != ev:
                    mismatch = True
                    break
            elif _normalize_value(v) != _normalize_value(ev):
                mismatch = True
                break
        execution_log.append("validation_ok" if not mismatch else "validation_mismatch")
    except Exception:
        logger.debug("Validation comparison failed, skipping validation check")


# --- Main Entry Points ---


async def run_job_with_id(
    job_id: str,
    req: ScrapeRequest,
    progress_callback: Any | None = None,
) -> ScrapeResponse:
    """Unified implementation with exploration, code generation, and self-healing.

    Combines the best of all versions:
    - Agentic exploration from V2 (now async)
    - Code generation from V3/V4
    - Self-healing loop from V4
    """
    from ...adapters.playwright_explorer import explore_with_playwright

    execution_log: list[str] = ["received"]
    artifacts_root = Path(settings.artifacts_root)
    screenshots_dir, _, html_dir = job_artifact_paths(artifacts_root, job_id)

    # Get start URL
    start_url = req.target_urls[0] if req.target_urls else None
    if not start_url:
        execution_log.append("no_target_url")
        execution_log.append("done")
        return ScrapeResponse(job_id=job_id, execution_log=execution_log, data={})

    # Perform agentic exploration
    execution_log.append("exploring")
    max_exploration_steps = int(os.getenv("MAX_EXPLORATION_STEPS", "20"))
    res = await explore_with_playwright(
        start_url=start_url,
        nl_request=req.nl_request,
        schema=req.output_schema,
        screenshots_dir=screenshots_dir,
        html_dir=html_dir,
        job_id=job_id,
        max_steps=max_exploration_steps,
        headless=settings.headless,
        login_params=req.login_params,
        progress_callback=progress_callback,
    )
    execution_log.append("exploration_complete")

    # Emit progress notification
    _emit_exploration_progress(progress_callback, max_exploration_steps, start_url)

    # Store exploration data
    exploration_data = res.data if hasattr(res, "data") else None

    # Optimize path into IR
    opt = _optimize_exploration_path(
        res, start_url, req.nl_request, req.output_schema, execution_log
    )

    # Synthesize extraction selectors
    extraction_spec = _synthesize_extraction_selectors(
        res, req.nl_request, req.parameters, req.output_schema, start_url, execution_log
    )

    # Execute with self-healing
    _execute_with_self_healing(
        opt, job_id, artifacts_root, extraction_spec, execution_log,
        progress_callback=progress_callback,
        max_exploration_steps=max_exploration_steps,
    )

    # Extract final data
    if progress_callback:
        try:
            progress_callback({
                "step": max_exploration_steps + 4,
                "max_steps": max_exploration_steps + 5,
                "action": "extracting_data",
                "status": "extracting",
            })
        except Exception:
            logger.debug("Progress callback failed during extraction")

    execution_log.append("extracting")
    data = _load_extracted_data(artifacts_root, job_id, req)

    # Use exploration data if extraction is empty
    schema_empty = _check_schema_empty(data, req.output_schema)
    if (not data or data == {} or schema_empty) and exploration_data:
        execution_log.append("using_exploration_data")
        data = exploration_data

    # Validate against exploration
    _validate_against_exploration(data, exploration_data, execution_log)

    execution_log.append("done")
    return ScrapeResponse(job_id=job_id, execution_log=execution_log, data=data)


async def run_job(req: ScrapeRequest) -> ScrapeResponse:
    """Main entry point for scraping jobs."""
    return await run_job_with_id(str(uuid.uuid4()), req)


def _finalize_from_artifacts(job_id: str, req: ScrapeRequest) -> dict[str, Any]:
    """Extract data from HTML artifacts when JSON data file is missing."""
    _, _, html_dir = job_artifact_paths(Path(settings.artifacts_root), job_id)
    html_file = html_dir / f"{job_id}-page-1.html"
    html_pages = []
    if html_file.exists():
        html_pages.append(html_file.read_text(encoding="utf-8"))
    base_url = req.target_urls[0] if (req.target_urls and len(req.target_urls) > 0) else None
    return extract_data(req.output_schema, html_pages, base_url=base_url)
