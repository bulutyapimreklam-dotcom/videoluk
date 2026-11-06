#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 -m venv "$PROJECT_DIR/.venv"
"$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/requirements-local.txt"
echo "Videoluk yerel ses motoru hazır."
echo "Başlatmak için: $PROJECT_DIR/.venv/bin/python $PROJECT_DIR/server.py"
