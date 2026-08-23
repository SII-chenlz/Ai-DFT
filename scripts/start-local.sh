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

: "${DEEPSEEK_HARNESS_DIR:=$ROOT_DIR/../deepseek-harness}"
: "${DSH_HOME:=$ROOT_DIR/.dsh-home}"
: "${AIFS_BACKEND_HOST:=127.0.0.1}"
: "${AIFS_BACKEND_PORT:=8000}"
: "${AIFS_BASIS_SET_POOL:=$ROOT_DIR/.local/basis_set_pool}"
export DEEPSEEK_HARNESS_DIR DSH_HOME AIFS_BACKEND_HOST AIFS_BACKEND_PORT AIFS_BASIS_SET_POOL

if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
  echo "未设置 DEEPSEEK_API_KEY；请在 .env.local 中填写后再启动" >&2
  exit 2
fi

"$ROOT_DIR/scripts/install-plugin-local.sh"

BACKEND_LOG="${AIFS_BACKEND_LOG:-$ROOT_DIR/.local/aifs-backend.log}"
mkdir -p "$(dirname "$BACKEND_LOG")"
"$ROOT_DIR/scripts/start-backend.sh" >"$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

cleanup() {
  kill "$BACKEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

for _ in {1..30}; do
  if curl -fsS "http://$AIFS_BACKEND_HOST:$AIFS_BACKEND_PORT/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -fsS "http://$AIFS_BACKEND_HOST:$AIFS_BACKEND_PORT/health" >/dev/null 2>&1; then
  echo "AIFS FastAPI 启动失败，日志：$BACKEND_LOG" >&2
  exit 1
fi

cd "$DEEPSEEK_HARNESS_DIR"
pnpm dsh web "$@"
