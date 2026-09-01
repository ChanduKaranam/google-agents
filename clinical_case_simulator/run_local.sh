#!/usr/bin/env bash
# Start the ADK dev UI at http://localhost:8000 and pick "clinical_simulator".
set -euo pipefail
cd "$(dirname "$0")"
[[ -f .env ]] || { echo "Create .env first: cp .env.example .env, then add your key."; exit 1; }
exec .venv/bin/adk web . "$@"
