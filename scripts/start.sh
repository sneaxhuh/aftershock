#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
docker compose up --build -d
printf '\nAFTERSHOCK is starting at http://localhost:8000\n'
printf 'Live agents require GEMINI_API_KEY in .env. See README.md.\n'
