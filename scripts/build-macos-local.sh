#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_PYTHON="${AIFS_PYTHON:-python3}"
VENV_DIR="$ROOT_DIR/.local/desktop-build-venv"
node "$ROOT_DIR/scripts/release.mjs" --installed
if [[ "$(uname -m)" != arm64 || "$(uname -s)" != Darwin ]]; then
  echo "首版调试包只支持 macOS arm64" >&2
  exit 2
fi
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$BUILD_PYTHON" -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/python" -c 'import sys, platform; assert sys.version_info[:2] == (3, 11) and platform.machine() == "arm64", "Build requires native arm64 Python 3.11"'
"$VENV_DIR/bin/python" -m pip install -r "$ROOT_DIR/packaging/requirements-desktop.lock"
"$VENV_DIR/bin/python" "$ROOT_DIR/scripts/build-desktop-backend.py"
node "$ROOT_DIR/scripts/build-desktop-plugin.mjs"
