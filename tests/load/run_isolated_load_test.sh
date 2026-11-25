#!/usr/bin/env bash
# Isolated load test (and optional HTTP evaluation) for OnboardAI - M3.
#
# Creates a throw-away stack that never touches the running Docker stack or its data:
#   * backend image built from the working tree under its own tag (onboardai-backend:m3-isolated)
#   * temporary PostgreSQL 16 seeded ONLY from docker/postgres (synthetic data), no published DB port
#   * migration 005 applied with random role passwords and scope secret (kept in shell variables only)
#   * backend as onboardai_app + onboardai_reader with the signed employee scope on 127.0.0.1:${PORT}
#   * a synthetic EMP001 login with a random password
# Everything is removed on exit (containers, network, image).
#
# Usage (repository root, Git Bash or Linux; Docker and the dev requirements installed):
#   bash tests/load/run_isolated_load_test.sh [output-dir]          # load test only
#   WITH_EVAL=1 bash tests/load/run_isolated_load_test.sh            # + HTTP evaluation (uses the Azure OpenAI settings in .env)
# Tunables: USERS (10), SPAWN_RATE (2), DURATION (60s), PORT (8301), PY (python interpreter),
#           INDEX_SRC (FAISS index folder mounted read-only; default data/index)
set -euo pipefail

OUT=${1:-loadtest-output}
USERS=${USERS:-10}; SPAWN_RATE=${SPAWN_RATE:-2}; DURATION=${DURATION:-60s}; PORT=${PORT:-8301}
if [ -z "${PY:-}" ]; then
  for c in .venv/Scripts/python.exe .venv/bin/python python3 python; do
    if [ -x "$c" ] || command -v "$c" >/dev/null 2>&1; then PY=$c; break; fi
  done
fi
INDEX_SRC=${INDEX_SRC:-data/index}
ID=onboardai-m3-$$; NET=$ID-net; DB=$ID-db; API=$ID-api; IMG=onboardai-backend:m3-isolated
HOSTPWD=$(pwd -W 2>/dev/null || pwd)
gen() { "$PY" -c "import secrets;print(secrets.token_urlsafe(24))"; }
OWNER_PW=$(gen); APP_PW=$(gen); READER_PW=$(gen); SCOPE=$(gen)$(gen)
export LOADTEST_EMAIL=loadtest.emp001@example.com LOADTEST_PASSWORD=$(gen) LOADTEST_EMPLOYEE=EMP001

cleanup() {
  docker rm -f "$API" "$DB" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  docker rmi "$IMG" >/dev/null 2>&1 || true
}
trap cleanup EXIT
mkdir -p "$OUT"

echo "== build $IMG from the working tree"
docker build -q -t "$IMG" . >/dev/null

echo "== temporary PostgreSQL with synthetic seed (docker/postgres)"
docker network create "$NET" >/dev/null
docker run -d --name "$DB" --network "$NET" -e POSTGRES_DB=onboardai -e POSTGRES_USER=onboardai \
  -e POSTGRES_PASSWORD="$OWNER_PW" -v "$HOSTPWD/docker/postgres:/docker-entrypoint-initdb.d:ro" postgres:16-alpine >/dev/null
for i in $(seq 1 60); do
  docker exec "$DB" pg_isready -U onboardai -d onboardai -h 127.0.0.1 >/dev/null 2>&1 && \
  docker exec "$DB" psql -U onboardai -d onboardai -At -c "SELECT count(*) FROM user_accounts" >/dev/null 2>&1 && break
  sleep 1
done

COMMON=(--network "$NET" -e DB_BACKEND=postgresql -e PG_HOST="$DB" -e PG_PORT=5432 -e PG_DATABASE=onboardai -e HF_HUB_OFFLINE=1)
echo "== migration 005 (least-privilege roles, signed scope) on the temporary database"
docker run --rm "${COMMON[@]}" -e PG_USER=onboardai -e PG_PASSWORD="$OWNER_PW" -e ONBOARDAI_APP_DB_PASSWORD="$APP_PW" \
  -e ONBOARDAI_READER_DB_PASSWORD="$READER_PW" -e ONBOARDAI_SCOPE_SECRET="$SCOPE" "$IMG" \
  python backend/migrations/005_least_privilege_roles.py --apply | head -1
docker run --rm "${COMMON[@]}" -e PG_USER=onboardai -e PG_PASSWORD="$OWNER_PW" -e NEWPW="$LOADTEST_PASSWORD" "$IMG" \
  python -m backend.manage_accounts set --email "$LOADTEST_EMAIL" --employee-id EMP001 --password-env NEWPW >/dev/null

echo "== backend as onboardai_app + onboardai_reader on 127.0.0.1:$PORT"
ENVFILE=(); [ "${WITH_EVAL:-0}" = 1 ] && [ -f .env ] && ENVFILE=(--env-file .env)
docker run -d --name "$API" "${ENVFILE[@]}" "${COMMON[@]}" -e PG_USER=onboardai_app -e PG_PASSWORD="$APP_PW" \
  -e PG_READER_USER=onboardai_reader -e PG_READER_PASSWORD="$READER_PW" -e PG_SCOPE_SECRET="$SCOPE" \
  -v "$(cd "$INDEX_SRC" && (pwd -W 2>/dev/null || pwd)):/app/data/index:ro" -p "127.0.0.1:$PORT:8000" "$IMG" >/dev/null
for i in $(seq 1 90); do curl -fs "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break; sleep 1; done
echo "   healthy after ${i}s"
echo "== read-only index mount: an in-container rebuild must fail and leave the active version unchanged"
docker exec "$API" python -c "
from backend.services import ingest
before = ingest.active_version()
try:
    ingest.build_index(); print('   UNEXPECTED: rebuild succeeded on a read-only mount')
except OSError as exc:
    print('   rebuild refused:', type(exc).__name__, '- active version unchanged:', ingest.active_version() == before, '(' + before + ')')
"

if [ "${WITH_EVAL:-0}" = 1 ]; then
  echo "== HTTP evaluation (held-out set) against the isolated backend"
  INDEX_DIR="$INDEX_SRC" "$PY" -m scripts.hybrid_eval --base-url "http://127.0.0.1:$PORT" --email "$LOADTEST_EMAIL" \
    --password-env LOADTEST_PASSWORD --report "$OUT/hybrid_eval_http.md" --json "$OUT/hybrid_eval_http.json" --delay 1.5 \
    | sed -n '/## Summary/,/## Routing by/p'
fi

echo "== locust: $USERS users, spawn rate $SPAWN_RATE/s, $DURATION"
docker stats --no-stream --format '{{.Name}} cpu={{.CPUPerc}} mem={{.MemUsage}}' "$API" "$DB" | sed 's/^/   before: /'
"$PY" -m locust -f tests/load/locustfile.py --headless -u "$USERS" -r "$SPAWN_RATE" -t "$DURATION" \
  --host "http://127.0.0.1:$PORT" --csv "$OUT/loadtest" --only-summary 2>&1 | tail -25
docker stats --no-stream --format '{{.Name}} cpu={{.CPUPerc}} mem={{.MemUsage}}' "$API" "$DB" | sed 's/^/   after: /'
echo "   5xx/tracebacks in backend log: $(docker logs "$API" 2>&1 | grep -c -E ' -> 5[0-9]{2} |Traceback' || true)"
docker logs "$API" 2>&1 | grep -c -E "$APP_PW|$READER_PW|$OWNER_PW|$SCOPE|$LOADTEST_PASSWORD" | sed 's/^/   secrets in backend log: /' || true
echo "== results in $OUT (removing the isolated stack)"
