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

## Architecture (Simplified)

- UI (Streamlit): Orchestrates the flow and shows progress
- Transcript Domain: VTT parsing and chunking; AI cleaning and review
- Intelligence Domain: Direct synthesis over the cleaned transcript (no semantic chunking or multi-step extraction)
- Settings & Logging: `backend/config.py` provides environment, model names, concurrency limits, and structlog setup

Data Flow
1) Upload .vtt → parse + chunk → async clean + review (progress shown inline)
2) Review cleaned transcript → export TXT/MD/VTT
3) Extract intelligence → direct synthesis produces summary + action items (progress shown inline)

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
ENVIRONMENT=development
LOG_LEVEL=INFO

# Optional tuning
MAX_CONCURRENT_TASKS=50
RATE_LIMIT_PER_MINUTE=50

# Model names (default to o3-mini everywhere)
CLEANING_MODEL=o3-mini
REVIEW_MODEL=o3-mini
INSIGHTS_MODEL=o3-mini
SYNTHESIS_MODEL=o3-mini
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

- There is no public API layer in this prototype; the UI calls domain services directly.
- State is session-scoped; export results to persist them.
- Concurrency and rate limits are enforced within the services.
