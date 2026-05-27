#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

"${ZEROINBOX_BOOTSTRAP_PYTHON:-python3}" -m venv "$PLUGIN_ROOT/.venv"
"$PLUGIN_ROOT/.venv/bin/python" -m pip install -r "$PLUGIN_ROOT/requirements.txt"
