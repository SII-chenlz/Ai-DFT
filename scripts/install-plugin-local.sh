#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM_DIR="${DEEPSEEK_HARNESS_DIR:-$ROOT_DIR/../deepseek-harness}"
ENV_FILE="${AIFS_ENV_FILE:-$ROOT_DIR/.env.local}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

: "${DSH_HOME:=$ROOT_DIR/.dsh-home}"
export DSH_HOME

if [[ ! -f "$UPSTREAM_DIR/package.json" ]]; then
  echo "找不到 DeepSeek Harness：$UPSTREAM_DIR" >&2
  exit 2
fi
if ! command -v pnpm >/dev/null 2>&1; then
  echo "未找到 pnpm；请先按 deepseek-harness 文档安装 Node/pnpm 依赖" >&2
  exit 2
fi

cd "$UPSTREAM_DIR"
pnpm dsh plugin --profile web add "$ROOT_DIR/dsh-plugin-aifs"
