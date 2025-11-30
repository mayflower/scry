from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

from ...api.dto import ScrapeRequest, ScrapeResponse
from ...config.settings import settings
from ...runtime.storage import data_artifact_path, job_artifact_paths
from ..codegen.generator import generate_script
from ..extractor.extract import extract_data
from ..self_heal.diagnose import propose_patch
from ..self_heal.patch import merge_codegen_options


async def run_job_with_id(  # noqa: PLR0912, PLR0915
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

    # Perform agentic exploration to discover the scraping path
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

    # Emit progress for post-exploration phases
    if progress_callback:
        try:
            progress_callback(
                {
                    "step": max_exploration_steps,
                    "max_steps": max_exploration_steps + 5,  # Add phases for codegen/execution
                    "action": "exploration_complete",
                    "url": start_url,
                    "status": "optimizing",
                }
            )
        except Exception:
            pass

    # Store exploration data for validation
    exploration_data = res.data if hasattr(res, "data") else None

    # Optimize exploration path into IR for code generation
    if res.steps:
        from ..optimizer.optimize import compress_min_path_with_anthropic

        execution_log.append("optimizing")
        opt = compress_min_path_with_anthropic(res, req.nl_request, req.output_schema)
        execution_log.append("path_compressed")
    else:
        # If no steps from exploration, create minimal IR
        from ..ir.model import Navigate, ScrapePlan

        opt = ScrapePlan(steps=[Navigate(url=start_url)], notes="minimal plan")

    # Synthesize extraction selectors from exploration BEFORE generating script
    extraction_spec: dict[str, Any] = {}
    if res.html_pages and len(res.html_pages) > 0:
        from ..extractor.selector_plan import synthesize_selectors

        execution_log.append("synthesizing_selectors")
        extraction_spec = synthesize_selectors(
            req.nl_request,
            req.parameters,
            req.output_schema,
            res.html_pages[0],  # Use HTML from exploration
            url=start_url,
        )
        if extraction_spec:
            execution_log.append("selectors_ready")

    # Generate and execute code with self-healing loop
    options: dict[str, Any] = {"extraction_spec": extraction_spec}
    last_stderr = None

    for attempt in range(max(1, settings.max_repair_attempts)):
        if attempt == 0:
            execution_log.append("codegen")
        else:
            execution_log.append(f"repair_attempt_{attempt}")

        script_path = generate_script(
            opt, job_id, artifacts_root, settings.headless, options=options
        )

        execution_log.append("executing_script")
        try:
            script_result = subprocess.run(
                ["python", str(script_path)],
                check=False,  # Don't raise on non-zero exit
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Check if validation failed (exit code 1 from critical validation)
            if script_result.returncode == 1:
                execution_log.append("validation_failed")
                # Extract validation failure from stderr/stdout
                validation_error = None
                if script_result.stderr and "CRITICAL validation failed:" in script_result.stderr:
                    validation_error = script_result.stderr
                elif script_result.stdout and "CRITICAL validation failed:" in script_result.stdout:
                    validation_error = script_result.stdout

                # Treat validation failure like any other error for self-healing
                if attempt + 1 < settings.max_repair_attempts:
                    last_stderr = (
                        validation_error or script_result.stderr or "Validation checkpoint failed"
                    )
                    patch = propose_patch(attempt + 1, last_stderr, None)
                    options = merge_codegen_options(options, patch)
                    continue
                execution_log.append("validation_repair_exhausted")
                break
            if script_result.returncode != 0:
                # Other non-validation errors
                raise subprocess.CalledProcessError(
                    script_result.returncode,
                    script_result.args,
                    script_result.stdout,
                    script_result.stderr,
                )

            execution_log.append("script_done")
            break
        except subprocess.CalledProcessError as e:
            last_stderr = e.stderr
            # Propose patch and continue if attempts remain
            if attempt + 1 >= settings.max_repair_attempts:
                execution_log.append("script_failed")
                break
            patch = propose_patch(attempt + 1, last_stderr, None)
            options = merge_codegen_options(options, patch)
            continue

    # Extract data from artifacts
    execution_log.append("extracting")
    data_file = data_artifact_path(artifacts_root, job_id)
    if data_file.exists():
        try:
            import json

            data = json.loads(data_file.read_text(encoding="utf-8"))
        except Exception:
            data = _finalize_from_artifacts(job_id, req)
    else:
        data = _finalize_from_artifacts(job_id, req)

    # If generated script extracted nothing but exploration got data, use exploration data
    # Check if the primary schema fields are empty (especially arrays)
    schema_empty = False
    if data and req.output_schema:
        # Check if array fields in schema are empty
        props = req.output_schema.get("properties", {})
        for key, spec in props.items():
            if spec.get("type") == "array":
                # For array fields, check if empty or missing
                value = data.get(key)
                if not value or (isinstance(value, list) and len(value) == 0):
                    schema_empty = True
                    break
                if isinstance(value, str) and not value.strip():
                    # Empty string instead of array
                    schema_empty = True
                    break

    if (not data or data == {} or schema_empty) and exploration_data:
        execution_log.append("using_exploration_data")
        data = exploration_data

    # Validate against exploration data
    try:
        if isinstance(exploration_data, dict) and exploration_data:

            def _norm(v):
                if isinstance(v, str):
                    return v.strip()
                return v

            mismatch = False
            for k, v in (data or {}).items():
                ev = (exploration_data or {}).get(k)
                if ev is None:
                    continue
                if isinstance(v, (int, float)) and isinstance(ev, (int, float)):
                    if v != ev:
                        mismatch = True
                        break
                elif _norm(v) != _norm(ev):
                    mismatch = True
                    break
            execution_log.append("validation_ok" if not mismatch else "validation_mismatch")
    except Exception:
        pass

    execution_log.append("done")
    return ScrapeResponse(job_id=job_id, execution_log=execution_log, data=data)


async def run_job(req: ScrapeRequest) -> ScrapeResponse:
    """Main entry point for scraping jobs."""
    return await run_job_with_id(str(uuid.uuid4()), req)


def _finalize_from_artifacts(job_id: str, req: ScrapeRequest) -> dict[str, Any]:
    _, _, html_dir = job_artifact_paths(Path(settings.artifacts_root), job_id)
    html_file = html_dir / f"{job_id}-page-1.html"
    html_pages = []
    if html_file.exists():
        html_pages.append(html_file.read_text(encoding="utf-8"))
    base_url = req.target_urls[0] if (req.target_urls and len(req.target_urls) > 0) else None
    return extract_data(req.output_schema, html_pages, base_url=base_url)
