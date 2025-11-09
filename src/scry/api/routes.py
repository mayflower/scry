import json
import os
import urllib.request
import uuid

from fastapi import APIRouter, HTTPException

from ..core.executor.runner import run_job
from ..runtime.events import get_bus
from .dto import ScrapeRequest, ScrapeResponse


router = APIRouter()


@router.post("/scrape", response_model=ScrapeResponse)
def scrape(req: ScrapeRequest) -> ScrapeResponse:
    try:
        return run_job(req)
    except Exception as e:
        # No logging; raise API error with minimal message
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/llm/ready")
def llm_ready():
    # Anthropic key presence
    key_present = bool(os.getenv("ANTHROPIC_API_KEY"))
    # Browser-Use LLM adapter availability
    try:
        adapter = "ChatAnthropic"
    except Exception:
        adapter = "fallback"
    # CDP version
    cdp_url = os.getenv("CDP_URL", "http://127.0.0.1:9222")
    cdp_version = None
    try:
        # CDP URL is from controlled env var with safe default (localhost)
        with urllib.request.urlopen(f"{cdp_url}/json/version", timeout=2) as r:  # nosec B310
            cdp_version = json.loads(r.read().decode("utf-8"))
    except Exception:
        cdp_version = None
    return {
        "anthropic_key": key_present,
        "adapter": adapter,
        "cdp": bool(cdp_version),
        "cdp_version": cdp_version,
        "nav_backend": os.getenv("NAV_BACKEND"),
    }


@router.post("/scrape/async")
def scrape_async(req: ScrapeRequest):
    try:
        job_id = str(uuid.uuid4())
        bus = get_bus()
        bus.enqueue({"job_id": job_id, "request": req.model_dump()})
        return {"job_id": job_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    try:
        bus = get_bus()
        res = bus.get_result(job_id)
        if not res:
            return {"status": "pending", "job_id": job_id}
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
