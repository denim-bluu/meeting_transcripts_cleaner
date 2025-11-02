# Meeting Transcript Cleaner - Reflex Application
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
run-app:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "🚀 Starting Reflex app..."
    reflex run

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
docker-clean:
    docker-compose down -v --rmi all
    docker image prune -f

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
status:
    #!/usr/bin/env bash
    echo "🔍 Checking Reflex app status..."
    curl -s http://localhost:3000 >/dev/null && echo "✅ App healthy" || echo "❌ App not responding"
