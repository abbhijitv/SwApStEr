#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python || ! -d frontend/node_modules ]]; then
  echo 'Install dependencies first; see README.md.'
  exit 1
fi
.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
backend_pid=$!
cleanup() { kill "$backend_pid" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
npm run dev --prefix frontend
