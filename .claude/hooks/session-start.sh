#!/bin/bash
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

pip install ruff --quiet

echo "--- ruff check server.py ---"
ruff check server.py
