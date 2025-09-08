from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

from ...adapters.browser_use import (
    explore_with_browser_use,  # type: ignore[attr-defined]
    is_browser_use_available,
)
from ...adapters.playwright import take_screenshot
from ...api.dto import ScrapeRequest, ScrapeResponse
from ...config.settings import settings
from ...runtime.storage import data_artifact_path, job_artifact_paths
from ..codegen.generator import generate_script
from ..extractor.extract import extract_data
from ..nav.navigator import execute_plan
from ..optimizer.optimize import optimize_plan
from ..planner.plan_builder import build_plan
from ..self_heal.diagnose import propose_patch
from ..self_heal.patch import merge_codegen_options


def run_minimal_job(req: ScrapeRequest) -> ScrapeResponse:
    job_id = str(uuid.uuid4())
    screenshots_dir, _, _ = job_artifact_paths(Path(settings.artifacts_root), job_id)

    execution_log: list[str] = [
        "received",
    ]

    url = None
    if req.target_urls and len(req.target_urls) > 0:
        url = req.target_urls[0]

    if url:
        execution_log.append("navigating")
        out_png = screenshots_dir / "step-1.png"
        take_screenshot(url, out_png, headless=settings.headless)
        execution_log.append("screenshot_captured")
    else:
        execution_log.append("no_target_url")

    execution_log.append("done")

    # Return an empty but schema-conformant container.
    # Without domain specialization, we use an empty dict.
    data: dict[str, Any] = {}

    return ScrapeResponse(job_id=job_id, execution_log=execution_log, data=data)


def run_v2_job(req: ScrapeRequest) -> ScrapeResponse:
    job_id = str(uuid.uuid4())
    screenshots_dir, _, html_dir = job_artifact_paths(
        Path(settings.artifacts_root), job_id
    )

    execution_log: list[str] = ["received", "planning"]
    plan = build_plan(req)

    execution_log.append("navigating")
    html_pages, shots = execute_plan(
        plan,
        screenshots_dir,
        html_dir,
        job_id,
        headless=settings.headless,
        login_params=req.login_params,
    )
    execution_log.append("screenshots_captured" if shots else "no_screenshots")

    # Persist first HTML snapshot for future self-heal
    if html_pages:
        html_out = html_dir / f"{job_id}-page-1.html"
        html_out.write_text(html_pages[0], encoding="utf-8")

    execution_log.append("extracting")
    # Best-effort extraction using schema
    base_url = (
        req.target_urls[0] if (req.target_urls and len(req.target_urls) > 0) else None
    )
    data = extract_data(req.output_schema, html_pages, base_url=base_url)

    execution_log.append("done")
    return ScrapeResponse(job_id=job_id, execution_log=execution_log, data=data)


def _finalize_from_artifacts(job_id: str, req: ScrapeRequest) -> dict[str, Any]:
    _, _, html_dir = job_artifact_paths(Path(settings.artifacts_root), job_id)
    html_file = html_dir / f"{job_id}-page-1.html"
    html_pages = []
    if html_file.exists():
        html_pages.append(html_file.read_text(encoding="utf-8"))
    base_url = (
        req.target_urls[0] if (req.target_urls and len(req.target_urls) > 0) else None
    )
    return extract_data(req.output_schema, html_pages, base_url=base_url)


def run_v3_job_with_id(job_id: str, req: ScrapeRequest) -> ScrapeResponse:
    screenshots_dir, _, _ = job_artifact_paths(Path(settings.artifacts_root), job_id)

    execution_log: list[str] = ["received", "planning"]
    plan = build_plan(req)
    execution_log.append("optimizing")
    opt = optimize_plan(plan)
    execution_log.append("codegen")
    script_path = generate_script(
        opt, job_id, Path(settings.artifacts_root), settings.headless
    )

    execution_log.append("executing_script")
    try:
        subprocess.run(
            ["python", str(script_path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        execution_log.append("script_done")
    except subprocess.CalledProcessError:
        execution_log.append("script_failed")
        # Still attempt extraction if any HTML exists

    execution_log.append("extracting")
    data = _finalize_from_artifacts(job_id, req)
    execution_log.append("done")
    return ScrapeResponse(job_id=job_id, execution_log=execution_log, data=data)


def run_v3_job(req: ScrapeRequest) -> ScrapeResponse:
    return run_v3_job_with_id(str(uuid.uuid4()), req)


def run_v4_job_with_id(job_id: str, req: ScrapeRequest) -> ScrapeResponse:
    execution_log: list[str] = ["received", "planning"]
    plan = build_plan(req)
    execution_log.append("optimizing")
    opt = optimize_plan(plan)

    options: dict[str, Any] = {}
    artifacts_root = Path(settings.artifacts_root)

    last_stderr = None
    # Agentic exploration path: if Anthropic is available, perform exploration to discover steps
    # and then generate deterministic code from the discovered path.
    start_url = None
    if req.target_urls:
        start_url = req.target_urls[0]
    if start_url and os.getenv("EXPLORATION_MODE", "agentic").lower() == "agentic":
        execution_log.append("exploring")
        if settings.nav_backend != "browser_use" or not is_browser_use_available():
            raise RuntimeError(
                "Exploration requires Browser-Use. Set NAV_BACKEND=browser_use and install browser-use."
            )
        screenshots_dir, _, html_dir = job_artifact_paths(
            Path(settings.artifacts_root), job_id
        )
        res = explore_with_browser_use(
            start_url=start_url,
            nl_request=req.nl_request,
            schema=req.output_schema,
            screenshots_dir=screenshots_dir,
            html_dir=html_dir,
            job_id=job_id,
            max_steps=int(os.getenv("BROWSER_USE_MAX_STEPS", "20")),
            headless=settings.headless,
        )
        if res.steps:
            from ..optimizer.optimize import compress_min_path_with_anthropic

            opt = compress_min_path_with_anthropic(
                res, req.nl_request, req.output_schema
            )
            execution_log.append("path_compressed")
        exploration_data = res.data if hasattr(res, "data") else None

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
            res = subprocess.run(
                ["python", str(script_path)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            execution_log.append("script_done")
            # After first success, try building an extraction spec and rerun to produce JSON data
            try:
                from ..extractor.selector_plan import synthesize_selectors

                html_dir = artifacts_root / "html"
                # Prefer the last page snapshot for selector synthesis
                html_files = sorted([p for p in html_dir.glob(f"{job_id}-page-*.html")])
                html_file = html_files[-1] if html_files else None
                if html_file and html_file.exists():
                    html = html_file.read_text(encoding="utf-8")
                    extraction_spec = synthesize_selectors(
                        req.nl_request,
                        req.parameters,
                        req.output_schema,
                        html,
                        url=(req.target_urls or [""])[0],
                    )
                    if extraction_spec:
                        execution_log.append("extraction_codegen")
                        options2 = dict(options)
                        options2["extraction_spec"] = extraction_spec
                        script_path2 = generate_script(
                            opt,
                            job_id,
                            artifacts_root,
                            settings.headless,
                            options=options2,
                        )
                        execution_log.append("executing_script")
                        subprocess.run(
                            ["python", str(script_path2)],
                            check=True,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        execution_log.append("script_done")
            except Exception:
                pass
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

    # Cross-check vs exploration_data if available
    try:
        if "exploration_data" not in locals():
            exploration_data = None
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
                else:
                    if _norm(v) != _norm(ev):
                        mismatch = True
                        break
            execution_log.append(
                "validation_ok" if not mismatch else "validation_mismatch"
            )
    except Exception:
        pass
    execution_log.append("done")
    return ScrapeResponse(job_id=job_id, execution_log=execution_log, data=data)


def run_v4_job(req: ScrapeRequest) -> ScrapeResponse:
    return run_v4_job_with_id(str(uuid.uuid4()), req)
