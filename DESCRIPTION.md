# Meeting Transcript Cleaner — Architecture and Code Guide

This repository turns raw WebVTT meeting transcripts into:
- Cleaned, readable transcripts with speaker attribution
- Quality-reviewed output
- Comprehensive meeting intelligence (summary and action items)

Current prototype mode: single Streamlit app that calls the domain services directly (no FastAPI backend or HTTP polling). The domain layers and agents remain the same. The previous two‑service architecture and task cache are retained in the repo as historical context.


## High‑Level Architecture

- Frontend: Streamlit multi‑page app for a 3‑step UX (Upload → Review → Intelligence)
  - Calls domain services directly via a small pipeline layer
  - Shows inline progress via callbacks (no HTTP polling)
- Legacy backend (not used in prototype): FastAPI app with background tasks and routers
  - Kept in the repo as reference; safe to ignore for the prototype
- Domain services
  - Transcript domain: VTT parsing, chunking, AI cleaning, review
  - Intelligence domain: semantic chunking (LangChain), insight extraction, synthesis
- (Historical) Task cache: Previously used with the FastAPI backend for async polling
- Agents: Stateless Pydantic AI agents that call OpenAI models (default: `o3-mini`)

Typical flow (prototype)
1) Upload .vtt → Parse and chunk in-process → Clean + Review chunks concurrently (inline progress)
2) Review cleaned transcript and export
3) Extract intelligence → Semantic chunking → Per‑chunk insights → Direct synthesis → Show/export results


## Repository Layout (key paths)

- `backend/`
  - `config.py`: Settings and logging (dotenv + pydantic‑settings; structlog config)
  - `transcript/`
    - `services/vtt_processor.py`: Parse VTT → `VTTEntry` list, create token‑based `VTTChunk`s
    - `services/cleaning_service.py`: Clean chunk text via Pydantic AI agent
    - `services/review_service.py`: Review cleaned chunk for quality via agent
    - `services/transcript_service.py`: Orchestrate parse → clean → review; export helpers
    - `models.py`: Dataclasses (`VTTEntry`, `VTTChunk`), Pydantic (`CleaningResult`, `ReviewResult`)
    - `agents/cleaner.py`, `agents/reviewer.py`: Stateless agent definitions
  - `intelligence/`
    - `intelligence_orchestrator.py`: Semantic chunking → insights extraction → synthesis
    - `models.py`: Pydantic outputs (`ChunkInsights`, `MeetingIntelligence`, `ActionItem`)
    - `agents/insights.py`, `agents/direct.py`: Stateless agents for extraction/synthesis
  - `utils/semantic_chunker.py`: LangChain `RecursiveCharacterTextSplitter` wrapper
- `frontend/`
  - `main.py`: Streamlit entry, navigation to 3 pages
  - `pages/1_📤_Upload_Process.py`: Upload VTT, start processing; inline progress via callbacks
  - `pages/2_👀_Review.py`: Review chunk‑level results and full transcript; export
  - `pages/3_🧠_Intelligence.py`: Extract intelligence; inline progress; export
  - `services/pipeline.py`: Thin controller for transcript + intelligence pipelines
  - `services/runtime.py`: Minimal async runner
  - `services/state_service.py`: Session and URL param utilities
  - `components/*`: Exports, metrics, error helpers
  - `utils/*`: Constants, file helpers
- `tests/`: Unit tests (domain focus)
- `docker-compose.yml`, `frontend/Dockerfile`: Containerized dev/deploy (single app)
- `justfile`: Dev shortcuts (install, run app, test, lint, docker)


## Configuration and Logging

`backend/config.py` centralizes settings and logging:
- Loads `.env` (dotenv) and exposes model names and limits (concurrency/rate)
- Provides a simple structlog setup used by the domain services


## Transcript Domain

VTT parsing and chunking (`backend/transcript/services/vtt_processor.py`)
- Parses VTT into `VTTEntry` objects (regex for timestamps; `<v Speaker>..</v>` then `Speaker:` fallback)
- Creates `VTTChunk`s based on token estimate (~ chars / 4) with target size (default 500 tokens)
- Emits analytics (speakers, durations, chunk distribution) via structlog

Cleaning (`backend/transcript/services/cleaning_service.py`)
- Preps a prompt including short previous‑chunk context (flow preservation)
- Calls stateless `cleaning_agent` (Pydantic AI) returning `CleaningResult`
- Logs timing and quality metrics

Review (`backend/transcript/services/review_service.py`)
- Compares original chunk vs cleaned text
- Calls stateless `review_agent` returning `ReviewResult` (score/issues/accept)

Transcript orchestration (`backend/transcript/services/transcript_service.py`)
- `process_vtt(content)`: parse → chunk + compute analytics
- `clean_transcript(transcript)`: bounded concurrency via `asyncio.Semaphore` and provider rate limiting via `asyncio_throttle.Throttler`; updates progress through a callback; aggregates cleaned text and review results + stats
- `export(transcript, format)`: vtt/txt/json output helpers
- `extract_intelligence(transcript)`: convenience to run the `IntelligenceOrchestrator` on available chunks

Data models (`backend/transcript/models.py`)
- Dataclasses: `VTTEntry`, `VTTChunk` (with `to_transcript_text()`)
- Pydantic: `CleaningResult`, `ReviewResult`

Agents (`backend/transcript/agents/*.py`)
- Stateless Pydantic AI agents using the configured OpenAI model names from settings
- Cleaner exposes a small tool to provide a context window from previous text


## Intelligence Domain

Semantic chunking (`backend/utils/semantic_chunker.py`)
- Combines cleaned VTT chunks into a single transcript then splits semantically with LangChain’s `RecursiveCharacterTextSplitter`
- Token‑ish params mapped to chars (≈ 4 chars/token); default chunk size 1500 tokens with 200 overlap

Extraction + synthesis (`backend/intelligence/*`)
- `agents/insights.py`: `chunk_extraction_agent` extracts concise insights/themes/actions per semantic chunk (stateless)
- `agents/direct.py`: `direct_synthesis_agent` builds the final `MeetingIntelligence` (summary + action items)
- `intelligence_orchestrator.py`:
  - Phase 1: semantic chunking (no API calls)
  - Phase 2: concurrent per‑chunk extraction with semaphore + throttler; errors are surfaced
  - Phase 3: direct synthesis from filtered insights; returns `MeetingIntelligence` plus rich `processing_stats`

Output models (`backend/intelligence/models.py`)
- `ChunkInsights`: insights, importance, themes, actions (minimal validators; retries via `ModelRetry`)
- `MeetingIntelligence`: markdown summary, list of `ActionItem`s, and `processing_stats`


## Frontend Design

Entry and navigation (`frontend/main.py`)
- Streamlit app configured for wide layout; simple summary on landing
- Navigation to three pages

Pages
- Upload & Process (`frontend/pages/1_📤_Upload_Process.py`)
  - Validates file, runs transcript pipeline directly, shows inline progress
  - On success, stores result in session state and shows metrics
- Review (`frontend/pages/2_👀_Review.py`)
  - Shows per‑chunk original vs cleaned text with quality metrics (if present)
  - Provides export in TXT/MD/VTT via `ExportHandler`
- Intelligence (`frontend/pages/3_🧠_Intelligence.py`)
  - Runs intelligence pipeline directly; displays summary and action items with small metrics
  - Export summary/action items in TXT/MD

Services and components
- `services/pipeline.py`: Controller to run domain services with UI progress
- `services/runtime.py`: Async runner helper
- `services/state_service.py`: Session keys and URL param helpers
- `components/export_handlers.py`: Download helpers for transcript/intelligence
- `components/metrics_display.py`: Quality and transcript metrics widgets


## API Surface

Prototype mode does not expose HTTP endpoints. All orchestration is in‑process via Streamlit.


## Concurrency, Rate Limits, and Progress

- Bounded concurrency for OpenAI calls using `asyncio.Semaphore`
- Provider rate limiting via `asyncio_throttle.Throttler(rate_limit=50/min)`
- Background tasks update `TaskEntry.progress` and `message`; UI polls with 2s interval by default


## Configuration and Operations

- Env and .env
  - App reads `backend/.env` via dotenv/pydantic‑settings
  - Required: `OPENAI_API_KEY`
  - Tunables: `max_concurrent_tasks`, `rate_limit_per_minute`
  - Model names: `cleaning_model`, `review_model`, `insights_model`, `synthesis_model`
- Local dev with `just`
  - `just run-app` → http://localhost:8501
  - `just test`, `just lint`, `just format`
- Docker
  - `docker-compose up -d` starts single Streamlit app


## Error Handling and Observability

- Extensive structured logging via structlog throughout parsing, chunking, extraction, and synthesis
- Background task error paths set task status to FAILED, capture `error`/`error_code`, and return explanatory `message`
- Health endpoint surfaces dependency status (OpenAI key presence, cache health) and model configuration


## Data and Serialization Notes

- Domain results include Python dataclasses (`VTTEntry`, `VTTChunk`) and Pydantic models; background tasks convert results to pure JSON‑serializable dicts before caching
- Frontend expects task results with:
  - Transcript: `entries`, `chunks`, `final_transcript?`, `cleaned_chunks?`, `review_results?`, `processing_stats?`
  - Intelligence: `summary`, `action_items[]`, `processing_stats`


## Known Gaps / Notes for Future Work

- Task cache duplication: There are two task cache implementations: `backend/tasks/cache.py` (used by routers/background tasks) and `backend/core/task_cache.py` (referenced by some tests). Favor `backend/tasks/cache.py` for runtime. Consider consolidating to a single canonical module and aligning tests.
- Legacy tests and client: Some tests reference modules like `backend.api.v1.endpoints` or a `frontend/api_client.py` that do not exist in the current layout. If you rely on the test suite, update or remove outdated tests to reflect the present API and client (`frontend/services/backend_service.py`).
- Persistence: The in‑memory cache is ephemeral by design. For production persistence or horizontal scaling, replace it with an external store (e.g., Redis) and implement distributed locking.
- Export fidelity: `export('vtt')` currently reconstructs using original cues; mapping cleaned text back to exact time spans is non‑trivial and could be improved.
- Security: Add authN/Z for API endpoints if exposing publicly; currently none is enforced.


## Extension Points

- Swap or configure OpenAI models via `.env` without code changes
- Adjust concurrency and rate limits in settings for your quota/tier
- Replace the cache with a distributed store by implementing the same interface
- Extend agents/prompts or add post‑processing to summaries and action items
- Add additional endpoints (e.g., batch upload) or storage for transcripts


## Quick Pointers (files worth skimming)

- VTT parsing and chunking: `backend/transcript/services/vtt_processor.py`
- Transcript orchestration: `backend/transcript/services/transcript_service.py`
- Intelligence orchestration: `backend/intelligence/intelligence_orchestrator.py`
- Agents: `backend/transcript/agents/*.py`, `backend/intelligence/agents/*.py`
- Pipeline/controller: `frontend/services/pipeline.py`, `frontend/services/runtime.py`
- Streamlit pages: `frontend/pages/*.py`

This document should equip you to navigate and modify the codebase without reading every file. For deeper behavior, search logs emitted by structlog and follow the referenced modules above.
