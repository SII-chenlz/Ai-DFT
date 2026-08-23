#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${AIFS_ENV_FILE:-$ROOT_DIR/.env.local}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

: "${AIFS_BACKEND_HOST:=127.0.0.1}"
: "${AIFS_BACKEND_PORT:=8000}"
: "${AIFS_BASIS_SET_POOL:=$ROOT_DIR/.local/basis_set_pool}"
export AIFS_BASIS_SET_POOL
mkdir -p "$AIFS_BASIS_SET_POOL"

exec python -m uvicorn aifs.api:app \
  --app-dir "$ROOT_DIR/backend/src" \
  --host "$AIFS_BACKEND_HOST" \
  --port "$AIFS_BACKEND_PORT"
