#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM_DIR="${DEEPSEEK_HARNESS_DIR:-$ROOT_DIR/../deepseek-harness}"
ENV_FILE="${AIFS_ENV_FILE:-$ROOT_DIR/.env.local}"
REQUIRE_INSTALLED=0
if [[ "${1:-}" == "--require-installed" ]]; then
  REQUIRE_INSTALLED=1
fi

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi
: "${DSH_HOME:=$ROOT_DIR/.dsh-home}"
export DSH_HOME

PLUGIN_DIR="$ROOT_DIR/dsh-plugin-aifs"
PACKAGE_JSON="$PLUGIN_DIR/package.json"
PATCH_FILE="$PLUGIN_DIR/cordis.patch.yml"

python - "$PACKAGE_JSON" "$PATCH_FILE" <<'PY'
import json
import pathlib
import sys

package_path = pathlib.Path(sys.argv[1])
patch_path = pathlib.Path(sys.argv[2])
manifest = json.loads(package_path.read_text())
assert manifest["dsh"]["bundle"]["patch"] == "./cordis.patch.yml"
patch = patch_path.read_text()
assert "id: aifs" in patch
assert "@aifs/dsh-plugin-aifs" in patch
PY

PROFILE_DIR="$DSH_HOME/profiles/web"
PROFILE_PACKAGE="$PROFILE_DIR/package.json"
if [[ ! -f "$PROFILE_PACKAGE" ]]; then
  if (( REQUIRE_INSTALLED )); then
    echo "Web profile 尚未创建：$PROFILE_PACKAGE" >&2
    exit 1
  fi
  echo "AIFS bundle 源文件检查通过；Web profile 尚未安装。运行 scripts/install-plugin-local.sh。"
  exit 0
fi

python - "$PROFILE_PACKAGE" <<'PY'
import json
import sys

manifest = json.load(open(sys.argv[1]))
dependencies = manifest.get("dependencies", {})
assert "@aifs/dsh-plugin-aifs" in dependencies, dependencies
PY

if (( REQUIRE_INSTALLED )); then
  PROFILE_MANIFEST="$PROFILE_DIR/dsh.profile"
  if [[ ! -f "$PROFILE_MANIFEST" ]]; then
    echo "profile manifest 不存在：$PROFILE_MANIFEST" >&2
    exit 1
  fi
  grep -q "@aifs/dsh-plugin-aifs" "$PROFILE_MANIFEST"
fi

echo "AIFS Harness bundle 已安装到：$PROFILE_DIR"
