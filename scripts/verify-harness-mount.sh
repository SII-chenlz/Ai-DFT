#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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

python - "$PROFILE_PACKAGE" "$PLUGIN_DIR" "$DSH_HOME/skills/aifs-molecular-planning" "$ROOT_DIR/skills/aifs-molecular-planning" <<'PY'
import json
from pathlib import Path
import sys

manifest = json.loads(Path(sys.argv[1]).read_text())
dependencies = manifest.get("dependencies", {})
assert dependencies.get("@aifs/dsh-plugin-aifs") == f"link:{sys.argv[2]}"
assert "@aifs/dsh-plugin-aifs" in manifest["dsh"]["profile"]["bundles"]
installed = Path(sys.argv[1]).parent / "node_modules/@aifs/dsh-plugin-aifs"
assert installed.is_symlink() and installed.resolve() == Path(sys.argv[2]).resolve()
skill_link = Path(sys.argv[3])
assert skill_link.is_symlink() and skill_link.resolve() == Path(sys.argv[4]).resolve()
PY

echo "AIFS 插件和规划 Skill 已安装到：$DSH_HOME"
