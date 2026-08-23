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
BASE_URL="http://$AIFS_BACKEND_HOST:$AIFS_BACKEND_PORT"

command -v curl >/dev/null 2>&1 || { echo "需要 curl" >&2; exit 2; }
command -v python >/dev/null 2>&1 || { echo "需要 python" >&2; exit 2; }

curl -fsS "$BASE_URL/health" | python -c '
import json, sys
data = json.load(sys.stdin)
assert data == {"status": "ok", "service": "aifs-api", "version": "0.1.0"}, data
'

GENERATED="$(curl -fsS -X POST "$BASE_URL/v1/rest-inputs" \
  -H 'content-type: application/json' \
  --data-raw '{"system_name":"water","position":"O 0 0 0\nH 0 1 0\nH 0 -1 0","job_type":"energy","xc":"PBE0","charge":0,"spin":1}')"

REST_INPUT="$(python -c 'import json,sys; d=json.loads(sys.argv[1]); assert d["rest_input"]; print(d["rest_input"], end="")' "$GENERATED")"
VALIDATION_PAYLOAD="$(python -c 'import json,sys; print(json.dumps({"rest_input": sys.argv[1]}))' "$REST_INPUT")"
curl -fsS -X POST "$BASE_URL/v1/rest-inputs/validate" \
  -H 'content-type: application/json' \
  --data-raw "$VALIDATION_PAYLOAD" | python -c '
import json, sys
data = json.load(sys.stdin)
assert data["valid"] is True, data
'

echo "AIFS local backend smoke check passed"
