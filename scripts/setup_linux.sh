#!/usr/bin/env bash
# One-time setup from source on Linux/macOS (Python 3.12+, Node.js 20.19+).
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
(cd frontend && npm ci && npm run build)
echo "Done. Run: cd backend && ../.venv/bin/python -m app.serve"
