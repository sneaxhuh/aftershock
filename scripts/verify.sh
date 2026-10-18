#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
docker compose -f compose.yaml -f compose.dev.yaml up -d falkordb main rollback restart fallback
RUN_INTEGRATION=1 .venv/bin/python -m pytest -q
