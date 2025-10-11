# Meeting Transcript Cleaner (Streamlit Prototype)

This prototype turns raw WebVTT meeting transcripts into:

- Cleaned, readable transcripts with speaker attribution
- Quality-reviewed output
- Comprehensive meeting intelligence (summary and action items)

The app is a single Streamlit service that calls the domain services directly (no separate FastAPI backend or HTTP polling). Intelligence extraction always uses a single high-quality flow—no “detail levels” or conditional prompts.

---

## Key Features

- Single Streamlit app (3-step UX: Upload → Review → Intelligence)
- Pydantic AI agents for:
  - Cleaning speech-to-text artifacts
  - Reviewing quality
  - Extracting insights and synthesizing the summary
- Inline progress updates using callbacks (no task polling)
- Dockerized app and Justfile dev workflows

---

## Architecture (Now Simplified)

- UI (Streamlit): Orchestrates the flow and shows progress
- Transcript Domain: VTT parsing and chunking; AI cleaning and review
- Intelligence Domain: Semantic chunking (LangChain) → per-chunk insight extraction → direct synthesis
- Settings & Logging: `backend/config.py` provides environment, model names, concurrency limits, and structlog setup

Data Flow
1) Upload .vtt → parse + chunk → async clean + review (progress shown inline)
2) Review cleaned transcript → export TXT/MD/VTT
3) Extract intelligence → insights + summary/action items (progress shown inline)

---

## Prerequisites

- Python 3.11+
- OpenAI API access (`OPENAI_API_KEY`)
- macOS/Linux (Windows should work but not actively tested)
- Docker (optional)
- just (optional, for local dev convenience)

---

## Configuration

Environment variables are read via dotenv at app start (see `backend/.env`).

Example `backend/.env`:

```
OPENAI_API_KEY=sk-xxx
environment=development
log_level=INFO

# Optional tuning
max_concurrent_tasks=50
rate_limit_per_minute=50

# Model names (default to o3-mini everywhere)
cleaning_model=o3-mini
review_model=o3-mini
insights_model=o3-mini
synthesis_model=o3-mini
```

---

## Local Development (with just)

Install dependencies (uses uv):

```
just install
# or, with dev deps:
just install-dev
```

Run the app:

```
just run-app
# Streamlit on http://localhost:8501
```

Run tests and linters:

```
just test
just lint
just format
```

Cleanup:

```
just clean
```

---

## Docker

Build and run with docker-compose (single service):

```
just docker-build
just docker-run
```

App is available at http://localhost:8501

To check health quickly:

```
just status
```

---

## Using the App

1. Upload a WebVTT file in “Upload & Process”
2. Watch inline progress; review metrics and participants
3. See detailed review by chunk or full cleaned transcript; export TXT/MD/VTT
4. Go to “Intelligence” and extract a summary + action items; export TXT/MD

Sample VTT: `test_meeting.vtt`

---

## Notes and Limitations

- There is no public API layer in this prototype. The UI calls the domain services directly.
- State is session-scoped; results can be exported for persistence.
- Concurrency and rate limits are enforced inside the services.


---

## Notes and Limitations

- Task state is stored in memory and expires automatically (TTL). This is perfect for local and container scenarios but not durable. Use the task ID immediately after submission to poll results.
- OpenAPI docs are only available in non-production environments at /docs.
- Model names default to o3-mini across the system; override via backend/.env if needed.
