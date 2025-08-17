# Meeting Transcript Cleaner - Decoupled Architecture
# Task runner using just (https://github.com/casey/just)

# Show available recipes
default:
    @just --list

# Installation
[group('setup')]
install:
    uv sync --no-dev

[group('setup')]
install-dev:
    uv sync

# Testing
[group('test')]
test:
    uv run pytest tests/ -v

[group('test')]
test-unit:
    uv run pytest tests/ -v -m "not integration"

[group('test')]
test-integration:
    uv run pytest tests/integration/ -v

[group('test')]
test-backend:
    uv run pytest tests/backend/ -v

[group('test')]
test-frontend:
    uv run pytest tests/frontend/ -v

[group('test')]
test-watch:
    uv run pytest tests/ -v --looponfail

# Code quality
[group('quality')]
lint:
    uv run ruff check .
    uv run black --check .
    uv run isort --check-only .

[group('quality')]
format:
    uv run black .
    uv run isort .
    uv run ruff check --fix .

[group('quality')]
type-check:
    uv run mypy .
    uv run pyright

[group('quality')]
check: lint type-check test

# Cleanup
[group('maintenance')]
clean:
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
    find . -name "*.pyc" -delete
    find . -name "*.pyo" -delete
    find . -name "*~" -delete

# Local development
[group('dev')]
run-backend:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "🚀 Starting backend service on http://localhost:8000"
    cd backend_service && uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

[group('dev')]
run-frontend:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "🚀 Starting frontend service on http://localhost:8501"
    export BACKEND_URL=http://localhost:8000
    cd frontend && uv run streamlit run main.py --server.port 8501 --server.address 0.0.0.0

[group('dev')]
dev:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "🚀 Starting both services in parallel..."
    echo "Backend: http://localhost:8000"
    echo "Frontend: http://localhost:8501"
    echo "Press Ctrl+C to stop both services"

    # Start backend in background
    (cd backend_service && uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000) &
    BACKEND_PID=$!

    # Wait a moment for backend to start
    sleep 2

    # Start frontend in background
    (export BACKEND_URL=http://localhost:8000 && cd frontend && uv run streamlit run main.py --server.port 8501 --server.address 0.0.0.0) &
    FRONTEND_PID=$!

    # Function to cleanup on exit
    cleanup() {
        echo "🛑 Stopping services..."
        kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
        wait $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
        echo "✅ Services stopped"
    }

    # Set trap to cleanup on script exit
    trap cleanup EXIT INT TERM

    # Wait for user to stop
    wait

# Docker operations
[group('docker')]
docker-build:
    docker-compose build

[group('docker')]
docker-run:
    docker-compose up -d

[group('docker')]
docker-stop:
    docker-compose down

[group('docker')]
docker-logs service="":
    #!/usr/bin/env bash
    if [ "{{ service }}" = "" ]; then
        docker-compose logs -f
    else
        docker-compose logs -f {{ service }}
    fi

[group('docker')]
docker-shell service:
    docker-compose exec {{ service }} /bin/bash

# Health and monitoring
[group('monitor')]
health:
    curl -f http://localhost:8000/health || echo "❌ Backend service is not healthy"

[group('monitor')]
status:
    #!/usr/bin/env bash
    echo "🔍 Checking service status..."
    echo ""
    echo "Backend (http://localhost:8000):"
    curl -s http://localhost:8000/health | jq '.' 2>/dev/null || echo "❌ Backend not responding"
    echo ""
    echo "Frontend (http://localhost:8501):"
    curl -s http://localhost:8501/_stcore/health >/dev/null && echo "✅ Frontend healthy" || echo "❌ Frontend not responding"
