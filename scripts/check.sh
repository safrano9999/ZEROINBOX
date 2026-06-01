#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

node --check "$PLUGIN_ROOT/index.js"
PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/zeroinbox-pycache" python3 -m py_compile \
  "$PLUGIN_ROOT/zeroinbox/__init__.py" \
  "$PLUGIN_ROOT/zeroinbox/classifier.py" \
  "$PLUGIN_ROOT/zeroinbox/cli.py" \
  "$PLUGIN_ROOT/zeroinbox/config.py" \
  "$PLUGIN_ROOT/zeroinbox/imap_backend.py" \
  "$PLUGIN_ROOT/zeroinbox/models.py" \
  "$PLUGIN_ROOT/zeroinbox/report.py" \
  "$PLUGIN_ROOT/zeroinbox/sorter.py" \
  "$PLUGIN_ROOT/ZEROINBOX_init.sh" \
  "$PLUGIN_ROOT/scripts/gmail-init-labels"
