# Refactoring Plan — Single Streamlit Application

This plan simplifies the prototype into a single Streamlit application while preserving modularity and separation of concerns. We keep the existing domain services (transcript processing and intelligence orchestration) and remove the FastAPI + task cache layers, replacing HTTP polling with direct function calls and UI progress callbacks.


## Goals

- One-process Streamlit app (no separate FastAPI or HTTP polling).
- Keep domain logic modular (SRP) and testable: parsing, cleaning, review, intelligence.
- Minimize cognitive load (KISS/YAGNI) while honoring SOLID/DRY.
- Retain export options and structured outputs.


## Non-Goals

- Public API for external clients (can be reintroduced later if needed).
- Distributed task orchestration or persistence beyond Streamlit sessions.
- Multi-instance shared task registry.


## Target Architecture

- UI: Streamlit pages orchestrate user actions and display progress.
- Controller: Thin functions that call domain services with progress callbacks.
- Domain: Existing modules under `backend/transcript/*`, `backend/intelligence/*`, and `backend/utils/*` unchanged.
- Settings: Continue to use `backend/config.py` (dotenv + pydantic-settings); load in Streamlit.
- Logging: Configure structlog at app start.


## Task Breakdown

Each task includes objective, what to change, and implementation notes. Suggested order matches dependencies.


**1) Create a Thin Controller Layer for Pipelines**
- Objective: Encapsulate orchestration so Streamlit pages remain thin and focused on UI.
- Changes:
  - Add `frontend/services/pipeline.py` with two functions:
    - `run_transcript_pipeline(content_str: str, on_progress: Callable[[float, str], None]) -> dict`
      - Steps: VTT parse → chunk → `await TranscriptService.clean_transcript(..., progress_callback=...)`
      - Return transcript dict containing entries, chunks, cleaned_chunks, review_results, final_transcript, processing_stats.
    - `run_intelligence_pipeline(chunks: list[VTTChunk], on_progress: Callable[[float, str], None]) -> MeetingIntelligence`
      - Steps: `await IntelligenceOrchestrator.process_meeting(chunks, progress_callback=...)`
      - Return `MeetingIntelligence` model or a serializable dict via `.model_dump()`.
  - Add `frontend/services/runtime.py` with a safe async runner:
    - `run_async(coro)` that uses `asyncio.run` or an event loop policy; keep it simple (no threads) unless needed.
- Notes:
  - Import services from `backend.transcript.services.transcript_service`, `backend.intelligence.intelligence_orchestrator`.
  - Inject a small adapter so `on_progress(pct, msg)` updates Streamlit widgets.


**2) Wire Upload & Process Page to Controller**
- Objective: Remove HTTP upload and task polling; call the pipeline directly.
- Changes (file: `frontend/pages/1_📤_Upload_Process.py`):
  - Remove use of `BackendService`, `TaskService`, and `ProgressTracker` for API polling.
  - On button click: read uploaded bytes, decode UTF-8, then call `run_transcript_pipeline` via `run_async(...)`.
  - Create UI containers for progress: `status = st.empty()`, `bar = st.progress(0)`; pass a callback that updates `bar.progress(progress)` and `status.text(message)`.
  - Store result in `st.session_state` under `STATE_KEYS.TRANSCRIPT_DATA` and show metrics, same as now.
- Notes:
  - Keep file validation (`utils/helpers.validate_file`).
  - Keep export rendering and metrics components; they’re format-agnostic.


**3) Wire Intelligence Page to Controller**
- Objective: Replace HTTP start/poll with direct function call.
- Changes (file: `frontend/pages/3_🧠_Intelligence.py`):
  - Remove use of `BackendService`, `TaskService`, and URL task resume.
  - Find transcript data in session; extract the list of `chunks` (reconstruct `VTTChunk` if needed; else pass formatted text per chunk to orchestrator if you prefer not to rehydrate dataclasses).
  - On button click: call `run_intelligence_pipeline(chunks, on_progress)` using `run_async(...)`.
  - Persist results into `STATE_KEYS.INTELLIGENCE_DATA` (store `.model_dump()` if Pydantic model) and display tabs as today.
- Notes:
  - If rehydrating dataclasses, mirror the existing background task’s rehydration (as in `backend/api/v1/background_tasks.py`).


**4) Replace ProgressTracker with Direct UI Updates**
- Objective: Remove polling abstraction.
- Changes:
  - Update `frontend/components/progress_tracker.py` to a minimal helper or deprecate it.
  - Create a small helper in `frontend/services/pipeline.py`:
    - `make_st_progress_callback(status_placeholder, bar_placeholder)` returns `(pct, msg)` updater.
- Notes:
  - Keep the component if you want consistent UI, but switch it to accept a callback API rather than polling a task id.


**5) Remove HTTP Client and Health Checks**
- Objective: Eliminate backend dependency.
- Changes:
  - Delete or archive: `frontend/services/backend_service.py`, `frontend/services/task_service.py`, `frontend/components/health_check.py`.
  - Update imports across pages to remove references.
  - Remove API endpoint constants and polling config from `frontend/utils/constants.py` that are no longer used.
- Notes:
  - Keep general constants and session state keys.


**6) Configure Settings & Logging in Streamlit**
- Objective: Ensure models and rate limits are honored; logs are consistent.
- Changes:
  - In `frontend/main.py` startup, call `dotenv.load_dotenv()` and import `backend.config.settings`.
  - Optionally call `backend.config.configure_structlog()` once; avoid double configuration.
  - If needed, expose a quick status banner showing selected model names and environment (`settings.environment`).
- Notes:
  - The services already consume `settings`; no code changes in domain are required.


**7) Decommission FastAPI and Task Cache (Code Hygiene)**
- Objective: Reduce dead code; keep domain only.
- Changes:
  - Mark as deprecated or remove: `backend/api/v1/*`, `backend/tasks/cache.py`, and `backend/core/task_cache.py` (duplicate).
  - Keep `backend/transcript/*`, `backend/intelligence/*`, `backend/utils/*`, `backend/config.py`.
- Notes:
  - If you want to keep the API for later, leave it in repo but remove from Docker/Just flows and README.


**8) Update Docker and Justfile**
- Objective: Single service container.
- Changes:
  - `docker-compose.yml`: Remove `backend` service; keep only `frontend` renamed to `app` (optional). Remove `depends_on` and `BACKEND_URL` env since it’s unused.
  - `frontend/Dockerfile`: Ensure it installs all project dependencies (domain + Streamlit). The `pyproject.toml` already includes FastAPI; it can remain.
  - `justfile`: Remove `run-backend`, adjust `run-frontend` to `run-app`, and update combined `dev` target accordingly.
- Notes:
  - Keep `uv sync` based workflows intact.


**9) Tests: Remove API/Client Tests; Keep/Refactor Domain Tests**
- Objective: Align tests to new runtime.
- Changes:
  - Remove or archive tests under `tests/backend/` that target HTTP routes and `tests/frontend/test_api_client.py` referencing non-existent `api_client.py`.
  - Keep domain unit tests (e.g., `backend/tests/test_task_cache.py` can be removed if cache is deleted; keep VTT parsing and orchestrator tests if present or add minimal tests).
  - Add small tests for `pipeline.run_transcript_pipeline` and `pipeline.run_intelligence_pipeline` (mock agents to avoid real API calls).
- Notes:
  - If retaining some API tests for documentation, mark them skipped with a clear reason.


**10) Documentation Updates**
- Objective: Ensure docs match architecture.
- Changes:
  - Update `README.md` quickstart and architecture sections to reflect single Streamlit app.
  - Update `DESCRIPTION.md` “System Architecture” and “Data flow” to remove FastAPI, background tasks, and task cache; show inline callbacks.
  - Document environment variables (OPENAI_API_KEY, model names) and how progress appears in UI.


**11) Optional: Non-Blocking Execution**
- Objective: Keep UI responsive during long operations if needed.
- Changes (only if required):
  - Add a simple `ThreadPoolExecutor` wrapper in `runtime.py` for CPU-bound VTT parsing or to run `asyncio` in a thread.
  - Start with synchronous calls first (KISS); only add threading if the main thread being busy is a real issue.


**12) Cleanup and Dead Code Removal**
- Objective: Reduce cognitive load.
- Changes:
  - Remove unused imports across pages and components.
  - Delete no-longer-used constants and helpers.
  - Ensure `pyproject.toml` remains consistent; keep FastAPI dependency optional (not harmful).


## Implementation Notes and Tips

- Progress Callbacks: Both transcript cleaning and intelligence orchestration already support progress callbacks; adapt them to update Streamlit placeholders.
- Dataclass Rehydration: If working with dicts from session, rehydrate `VTTEntry`/`VTTChunk` as needed (see pattern in `backend/api/v1/background_tasks.py`).
- Error Handling: Surface exceptions via `st.error()` and include short guidance; continue logging via structlog.
- Settings: Prefer `.env` in repo root or `backend/.env`; ensure Streamlit loads it once at startup.
- Rate Limits: The throttler and semaphore in services already cap concurrency and rate.


## Suggested PR Sequence

1) Add controller (`pipeline.py`, `runtime.py`) and wire Upload page to direct calls; keep backend as-is.
2) Wire Intelligence page; remove polling & HTTP client usage.
3) Delete HTTP client/services and unused components; simplify constants.
4) Update docs; update justfile; update Docker compose to single service.
5) Remove/deprecate FastAPI routes and task cache; trim tests; add pipeline tests.


## Acceptance Criteria

- Running `uv run streamlit run frontend/main.py`:
  - Upload a .vtt, see in-UI progress (bar + status), and a completed transcript with metrics and exports.
  - Trigger intelligence extraction from the Review/Intelligence page, see progress, summary, and action items.
  - No HTTP calls to a backend; no `BACKEND_URL` required.
  - Errors are shown in the UI and logs without crashing the session.


## Risks & Mitigations

- Long-running tasks can block UI: Start synchronous; add `runtime.run_async` or thread executor only if necessary.
- Multi-user contention: Streamlit sessions are separate; model rate limit is enforced by existing throttler.
- Regression on exports: Ensure export components still receive the expected dict structure; adjust only if fields moved.


## Estimated Effort

- Controller + Upload wiring: 0.5–1 day
- Intelligence wiring: 0.5 day
- Cleanup (remove HTTP, docs, Docker/Just updates): 0.5 day
- Tests adjustments: 0.5 day

Total: ~2–3 dev-days for a clean, minimal prototype.

---

## Implementation Blueprints (Lightweight)

These are intentionally minimal to guide implementation without over-prescription.

1) frontend/services/pipeline.py (new)

```
from collections.abc import Callable
from backend.transcript.services.transcript_service import TranscriptService
from backend.intelligence.intelligence_orchestrator import IntelligenceOrchestrator

def make_progress_callback(update):
    # update(progress: float, message: str) -> None
    def cb(pct: float, msg: str):
        try:
            update(pct, msg)
        except Exception:
            pass
    return cb

def run_transcript_pipeline(content_str: str, on_progress: Callable[[float, str], None]) -> dict:
    service = TranscriptService(api_key="unused-here")  # settings handles API key
    transcript = service.process_vtt(content_str)

    def progress_sync(pct, msg):
        on_progress(max(0.0, min(1.0, pct)), msg)

    # Run async cleaning in a sync context via runtime.run_async
    from .runtime import run_async
    result = run_async(service.clean_transcript(transcript, progress_callback=progress_sync))
    return result

def run_intelligence_pipeline(chunks: list, on_progress: Callable[[float, str], None]):
    orchestrator = IntelligenceOrchestrator()

    from .runtime import run_async
    def progress_sync(pct, msg):
        on_progress(max(0.0, min(1.0, pct)), msg)

    intel = run_async(orchestrator.process_meeting(chunks, progress_callback=progress_sync))
    return intel
```

2) frontend/services/runtime.py (new)

```
import asyncio

def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # In Streamlit, avoid nested loops; run in a new task and wait
        return asyncio.run(coro)  # If this raises, fallback to to_thread
    return asyncio.run(coro)
```

3) Upload page wiring (excerpt)

```
from services.pipeline import run_transcript_pipeline

status = st.empty()
bar = st.progress(0)

def ui_update(pct, msg):
    bar.progress(pct)
    status.text(f"{int(pct*100)}% • {msg}")

if st.button("Process VTT"):
    content_str = uploaded_file.getvalue().decode("utf-8")
    data = run_transcript_pipeline(content_str, ui_update)
    st.session_state[STATE_KEYS.TRANSCRIPT_DATA] = data
```

4) Intelligence page wiring (excerpt)

```
from services.pipeline import run_intelligence_pipeline
from backend.transcript.models import VTTChunk, VTTEntry

def to_vtt_chunks(raw_chunks: list[dict]) -> list[VTTChunk]:
    chunks = []
    for ch in raw_chunks:
        entries = [VTTEntry(**e) for e in ch.get("entries", [])]
        chunks.append(VTTChunk(chunk_id=ch["chunk_id"], entries=entries, token_count=ch["token_count"]))
    return chunks

status = st.empty(); bar = st.progress(0)
ui = lambda p,m: (bar.progress(p), status.text(m))

if st.button("Extract Intelligence"):
    chunks = to_vtt_chunks(transcript["chunks"])  # from session
    intel = run_intelligence_pipeline(chunks, ui)
    st.session_state[STATE_KEYS.INTELLIGENCE_DATA] = intel.model_dump()
```

---

## File-by-File Checklist

- Add: `frontend/services/pipeline.py`, `frontend/services/runtime.py`.
- Update: `frontend/pages/1_📤_Upload_Process.py` to call pipeline directly.
- Update: `frontend/pages/3_🧠_Intelligence.py` to call pipeline directly and rehydrate chunks.
- Possibly Update: `frontend/pages/2_👀_Review.py` only to remove backend health gating.
- Remove/Archive: `frontend/services/backend_service.py`, `frontend/services/task_service.py`, `frontend/components/health_check.py`.
- Trim: `frontend/utils/constants.py` (remove API endpoint and polling sections).
- Leave as-is: `backend/transcript/*`, `backend/intelligence/*`, `backend/utils/*`, `backend/config.py`.
- Optional removal: `backend/api/v1/*`, `backend/tasks/cache.py`, `backend/core/task_cache.py`.

---

## Milestones and Validation

Milestone A: Transcript pipeline end-to-end
- Upload a small sample VTT; see progress updates and final transcript metrics.
- Acceptance: `cleaned_chunks` and `review_results` arrays are present; `final_transcript` populated; no HTTP/network to local backend.

Milestone B: Intelligence extraction end-to-end
- With transcript in session, run extraction; see progress and summary/action items.
- Acceptance: `INTELLIGENCE_DATA.summary` non-empty; `action_items` list present; processing_stats has phase timings.

Milestone C: UI stabilization and exports
- TXT/MD/VTT exports work with new data structures (no API result assumptions).
- Acceptance: Files download and contain expected content; VTT retains cue boundaries (as designed today).

Milestone D: Cleanup and docs
- All removed modules no longer imported; justfile/docker reflect single-app flow; README/DESCRIPTION updated.
- Acceptance: `rg -n "api/v1|BackendService|BACKEND_URL"` finds no live references (except historical docs, if retained intentionally).

---

## Docker and Justfile Updates (suggested)

- docker-compose.yml
  - Remove `backend` service.
  - Rename `frontend` → `app` (optional), remove `environment: BACKEND_URL`.
  - Entrypoint runs `streamlit run frontend/main.py --server.port 8501 --server.address 0.0.0.0`.

- justfile
  - Replace `run-frontend` with `run-app`:
    - `cd frontend && uv run streamlit run main.py --server.port 8501 --server.address 0.0.0.0`
  - Remove `run-backend` and `dev` that spawn both.
  - Keep `test`/`format`/`lint` as-is; adjust any backend API tests.

---

## Rollback Strategy

- Keep API code in a `api_legacy/` branch or tag prior to removal.
- Stage the refactor behind a feature branch; release as a minor version bump.
- If regression found, revert the few touched files (pages + services) and restore docker-compose entries.

---

## Risks by Task (and Mitigation)

- Controller calls block UI: Start synchronous; if needed, add a thread-based runner or reduce semaphore concurrency in settings.
- Dataclass rehydration mismatch: Use the exact field names as in `background_tasks.py` rehydration logic.
- Exports assuming old shapes: Validate expected keys exist; add defensive defaults in export handlers.
- Tests failing due to API removal: Mark legacy tests `xfail` or remove; add minimal pipeline unit tests with mocked agents.

---

## Open Questions / Decisions

- Keep FastAPI code in repo (disabled) vs. delete? Default: delete to reduce noise.
- Do we want a minimal local “health” section in UI to show selected model names and rate limits (from `settings`)? Optional.
- Should `SemanticChunker` operate on cleaned transcript or raw chunks? Current orchestrator uses VTT chunks; that’s fine.
