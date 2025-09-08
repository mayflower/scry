Below is a **code‑free** blueprint of the Python module layout and Docker structure, followed by a **runnable, incremental implementation plan** with **6 versions** to avoid big‑bang development. This stays within your constraints: **no logging**, **no video recording**, **no sandbox** (Docker is fine), and **no domain specialization**.

---

## 1) Python Module Structure (no code)

> Goal: clean separation of concerns, event‑driven orchestration, and artifacts limited to **screenshots** and **generated Playwright Python**.

```
repo-root/
├─ src/
│  └─ universal_scraper/
│     ├─ api/                         # REST surfaces (FR-6)
│     │  ├─ __init__.py
│     │  ├─ routes.py                 # Defines endpoints only (no logging)
│     │  └─ dto.py                    # Request/response dataclasses & validation
│     │
│     ├─ core/                        # Core orchestration & domain-agnostic logic
│     │  ├─ __init__.py
│     │  ├─ ir/                       # ScrapePlan IR definitions (schema-aligned)
│     │  │  ├─ __init__.py
│     │  │  └─ model.py
│     │  ├─ planner/                  # NL → IR using Anthropic Claude
│     │  │  ├─ __init__.py
│     │  │  └─ plan_builder.py
│     │  ├─ nav/                      # AI-assisted navigation directives (generic)
│     │  │  ├─ __init__.py
│     │  │  └─ navigator.py
│     │  ├─ extractor/                # Generic DOM/structured-data extraction
│     │  │  ├─ __init__.py
│     │  │  └─ extract.py
│     │  ├─ optimizer/                # Path compression & selector stabilization
│     │  │  ├─ __init__.py
│     │  │  └─ optimize.py
│     │  ├─ codegen/                  # Playwright Python generation (no AI at runtime)
│     │  │  ├─ __init__.py
│     │  │  └─ generator.py
│     │  ├─ executor/                 # Runs generated code; captures screenshots only
│     │  │  ├─ __init__.py
│     │  │  └─ runner.py
│     │  ├─ validator/                # JSON Schema validation & normalization
│     │  │  ├─ __init__.py
│     │  │  └─ validate.py
│     │  └─ self_heal/                # Incremental repair loop (screenshots + HTML)
│     │     ├─ __init__.py
│     │     ├─ diagnose.py
│     │     └─ patch.py
│     │
│     ├─ adapters/                    # External adapters (FOSS/Anthropic)
│     │  ├─ __init__.py
│     │  ├─ browser_use.py            # Primary control (Browser-Use over Playwright)
│     │  ├─ playwright.py             # Low-level Playwright helpers
│     │  └─ anthropic.py              # Claude client wrapper
│     │
│     ├─ runtime/                     # Event-driven plumbing & artifact IO
│     │  ├─ __init__.py
│     │  ├─ events.py                 # In-memory or Redis-backed event bus (no logs)
│     │  └─ storage.py                # Read/write artifacts (screenshots, code, IR)
│     │
│     └─ config/                      # Configuration parsing only (no observability)
│        ├─ __init__.py
│        └─ settings.py
│
├─ artifacts/                         # Generated at runtime (mounted volume)
│  ├─ screenshots/                    # Per job_id/
│  ├─ generated_code/                 # job_id.py (Playwright automation)
│  └─ html/                           # DOM snapshots if needed by self-heal
│
├─ docker/                            # Docker structure (no code content)
│  ├─ base/
│  │  └─ Dockerfile                   # Python + Playwright + Chromium
│  ├─ api/
│  │  └─ Dockerfile                   # Adds src/, exposes API port
│  ├─ worker/
│  │  └─ Dockerfile                   # Adds src/, runs worker entrypoint
│  └─ compose/
│     └─ docker-compose.yml           # api, worker, (redis introduced later)
│
├─ pyproject.toml                     # Build metadata (no code shown)
└─ README.md                          # How to run (conceptual, no code snippets)
```

**Environment variables (names only):**

* `CLAUDE_API_KEY` – Anthropic Claude access.
* `MAX_REPAIR_ATTEMPTS` – default **20**.
* `HEADLESS` – default **true**.
* `SCREENSHOT_DIR` – default `artifacts/screenshots`.
* `GENERATED_CODE_DIR` – default `artifacts/generated_code`.
* `HTML_SNAPSHOTS_DIR` – default `artifacts/html`.
* `EVENT_BACKEND` – `inmemory` (early) or `redis` (later).
* `REDIS_URL` – only when `EVENT_BACKEND=redis`.
* `WORKER_CONCURRENCY` – optional tuning.

> Notes:
>
> * No video, HAR, or trace artifacts are produced—**screenshots only**.
> * No logging systems are included; any “execution\_log” returned by the API is a **transient status list** required by your response schema, not persisted.

---

## 2) Docker Structure (no code)

**Images**

* `docker/base/Dockerfile`: Python + Playwright + headless Chrome/Chromium installed; common system deps.
* `docker/api/Dockerfile`: based on `base`, adds `src/` and starts the API service.
* `docker/worker/Dockerfile`: based on `base`, adds `src/` and starts the worker process.

**Compose Topology**

* `api` service: exposes the REST API; mounts `./artifacts:/app/artifacts`.
* `worker` service: runs jobs; mounts the same `artifacts` volume.
* `redis` service: **introduced in a later version** to fulfill event‑driven decoupling (TC‑2.1). Not used in the earliest versions.
* Shared bridge network for internal communication.

> The **final state** uses two application containers (api, worker) plus optional Redis when event decoupling is activated. No sandbox container; **Docker is the only isolation** layer.

---

## 3) Incremental Implementation Plan (6 runnable versions)

Each version produces a **running system** that can be exercised with your existing API input specification and yields a compliant response. No logging is added at any stage.

### **V1 — Minimal Vertical Slice (single-container flow)**

**Scope**

* API accepts the full request (NL query, schema, example, login params, optional target URLs).
* In‑process orchestration (no external queue).
* Worker behavior: open the **first** `target_url` (if provided) with Playwright, take a **single screenshot**, and return an **empty but schema‑conformant** `data` structure (e.g., empty arrays/objects as allowed by the schema).
* `execution_log` field returns a small **transient** status sequence (e.g., received → navigating → done).

**Artifacts**

* `artifacts/screenshots/{job_id}/step-1.png`
* `artifacts/generated_code/{job_id}.py` is **not emitted** yet.

**Why this version?**

* Verifies API, job lifecycle, Playwright headless operation, Docker wiring, and artifact write paths—without introducing planning or code generation.

---

### **V2 — Planning + Exploration + Provisional Extraction (still single-container)**

**Scope**

* Introduce **ScrapePlan IR** (generic, schema‑aligned).
* Claude used to convert NL request into IR (actions + generic locators).
* Browser‑Use drives Playwright to follow IR steps; provisional extraction using **generic DOM rules** only (no domain specialization).
* Output `data` **matches the provided schema** with whatever fields can be reliably extracted; missing fields are omitted or null as permitted by the schema.
* Multiple **screenshots** captured at key steps.

**Artifacts**

* `screenshots/{job_id}/step-*.png`
* `html/{job_id}-page-*.html` (if needed by self-heal in later versions)

**Why this version?**

* End‑to‑end agentic navigation and schema‑aligned extraction, still without code generation.

---

### **V3 — Path Optimization + Code Generation + Decoupled Workers**

**Scope**

* Introduce **Path Optimizer**: compress the exploration path into stable steps and resilient selectors.
* **Generate Playwright Python** that reproduces the optimized path **without AI at runtime**.
* Introduce **Redis** and switch `EVENT_BACKEND=redis` to satisfy **event‑driven architecture** (TC‑2.1).
* Execution phase now runs the **generated script** and produces the final `data`.
* Status streaming remains transient; no logs persisted.

**Artifacts**

* `generated_code/{job_id}.py`  (production‑ready Playwright Python)
* `screenshots/{job_id}/...`    (from generated script run)

**Why this version?**

* Guarantees FR‑3.2/FR‑3.3 with a decoupled, event‑driven pipeline matching TC‑2.1.

---

### **V4 — Self‑Healing (Incremental Repair Loop)**

**Scope**

* On runtime failure (timeouts, missing selectors, modal encountered), collect:

  * the **last screenshot** and optionally the **current page HTML**,
* Use Claude to **diagnose** and propose a **minimal patch** (selector change, extra wait, close generic modal).
* Regenerate code with the patch, **re‑execute**, and iterate.
* Stop and set `repair_attempts = 20` with **alert outcome** (e.g., job marked failed) if still unsuccessful.

**Artifacts**

* Updated `generated_code/{job_id}.py` for each accepted patch (only the final one retained).
* Screenshots for each attempt; retained **per your storage policy** (no logs, no video).

**Why this version?**

* Delivers FR‑4.1–FR‑4.5 with strictly **screenshots + HTML** as evidence.

---

### **V5 — Authentication + Multi‑Page Flows + Strict Schema Validation**

**Scope**

* Support **login\_parameters** (username/password/login\_url) in the IR and navigator.
* Handle **multi‑page** extraction (pagination, basic infinite scroll) generically.
* Validate outputs with `jsonschema`; only **schema‑valid** `data` is returned. On validation failure, retry via self‑heal where feasible.
* Ensure `execution_log` (transient status entries) reflects the multi‑stage run.

**Artifacts**

* Screenshots per page/step.
* Final `generated_code/{job_id}.py` implementing authenticated, multi‑page flow.

**Why this version?**

* Completes FR‑2.3/FR‑2.5 and FR‑5.2 while keeping the system universal and domain‑agnostic.

---

### **V6 — Fallbacks + UX Polish (Finalization)**

**Scope**

* **Computer Use** fallback for UIs Browser‑Use struggles with (still generic).
* SSE (Server‑Sent Events) status streaming for FR‑6.3 (optional if you already provide polling).
* Resource limits, timeouts, and backoff tuned for robust operation (without adding logging, video, or sandboxing).
* Hardening of selector strategies and generic modal handling.

**Artifacts**

* Same as previous versions; no new artifact types.

**Why this version?**

* Improves robustness and user experience without expanding scope beyond your catalog.

---

## 4) Run & Test (conceptual, no commands)

For each version:

1. **Build & start containers** using the provided Docker structure.
2. **Submit** a request per your **API Input Specification** (use any target URL(s) you control).
3. **Poll or stream** job status until it reaches `completed` or `failed`.
4. **Inspect** the response fields: `status`, `data` (schema‑valid), `generated_code` presence (V3+), `execution_log` (transient status entries), `repair_attempts`, and `error`.
5. **Check artifacts** in the mounted `artifacts/` directory:

   * Screenshots for each step,
   * Generated Playwright Python (V3+),
   * Optional HTML snapshots used only for self‑healing diagnosis.

> All stages avoid video/trace/HAR capture and any logging system. The system never specializes for any site/domain.

---

### Summary

* The **module layout** cleanly separates API, planning, navigation, code generation, execution, validation, and self‑healing while remaining **universal**.
* The **Docker structure** uses a simple base image, plus `api` and `worker` images, and introduces **Redis** only when event decoupling is needed (V3+).
* The **6‑step plan** yields a running, testable system at each step—culminating in autonomous **Playwright Python** generation, **self‑healing**, and **schema‑valid** JSON output—without logging, video, sandboxing, or domain specialization.

