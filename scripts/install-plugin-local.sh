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

# Reuse the store that owns an existing DSH node_modules tree. A different
# store makes pnpm attempt to replace that tree during a routine launch.
if [[ -z "${npm_config_store_dir:-}" && -f "$UPSTREAM_DIR/node_modules/.modules.yaml" ]]; then
  INSTALLED_STORE="$(sed -nE 's/^[[:space:]]*"storeDir": "([^"]+)"[,]?$/\1/p' "$UPSTREAM_DIR/node_modules/.modules.yaml" | head -n 1)"
  if [[ -n "$INSTALLED_STORE" ]]; then
    export npm_config_store_dir="$INSTALLED_STORE"
  fi
fi

# The Web preset already loads the filesystem Skill provider. Its DSH_HOME
# skill root is stable even though DSH runs from a sibling checkout.
SKILL_ROOT="$DSH_HOME/skills"
SKILL_LINK="$SKILL_ROOT/aifs-molecular-planning"
mkdir -p "$SKILL_ROOT"
if [[ -L "$SKILL_LINK" ]]; then
  if [[ "$(readlink "$SKILL_LINK")" != "$ROOT_DIR/skills/aifs-molecular-planning" ]]; then
    echo "Skill 链接指向其他位置，请手动检查：$SKILL_LINK" >&2
    exit 2
  fi
elif [[ -e "$SKILL_LINK" ]]; then
  echo "Skill 路径已被占用，请手动检查：$SKILL_LINK" >&2
  exit 2
else
  ln -s "$ROOT_DIR/skills/aifs-molecular-planning" "$SKILL_LINK"
fi

# An installed link needs no pnpm operation. Re-adding it on every launch can
# trigger a workspace reinstall and fail when pnpm selects a different store.
PROFILE_DIR="$DSH_HOME/profiles/web"
if [[ -f "$PROFILE_DIR/package.json" && -L "$PROFILE_DIR/node_modules/@aifs/dsh-plugin-aifs" ]]; then
  if node -e '
    const fs = require("node:fs")
    const path = require("node:path")
    const [profileDir, pluginDir] = process.argv.slice(1)
    const manifest = JSON.parse(fs.readFileSync(path.join(profileDir, "package.json"), "utf8"))
    const installed = path.join(profileDir, "node_modules/@aifs/dsh-plugin-aifs")
    const expected = `link:${pluginDir}`
    process.exit(
      manifest.dependencies?.["@aifs/dsh-plugin-aifs"] === expected &&
      manifest.dsh?.profile?.bundles?.includes("@aifs/dsh-plugin-aifs") &&
      fs.realpathSync(installed) === fs.realpathSync(pluginDir) ? 0 : 1
    )
  ' "$PROFILE_DIR" "$ROOT_DIR/dsh-plugin-aifs"; then
    echo "AIFS 插件和 Skill 已安装到 DSH Web profile"
    exit 0
  fi
fi

cd "$UPSTREAM_DIR"
pnpm dsh plugin --profile web add "$ROOT_DIR/dsh-plugin-aifs"
