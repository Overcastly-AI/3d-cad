#!/usr/bin/env bash
# e2e.sh — the `just e2e` gate: geometry gates, then the Playwright suite.
#
# Leg 1: geometry golden models + STEP round-trip (docs/GEOMETRY-QA.md).
# Leg 2: Playwright e2e for @loft/web against the real stack. The specs need
#         the geometry service (:8002) and gateway (:8000); this script boots
#         them as background uvicorn processes (PIDs saved, cleaned up on
#         exit — never killed by pattern) or reuses already-healthy ones, so
#         it composes with a running `just dev` loop. Playwright's webServer
#         config starts/reuses the Vite dev server (:5173) itself.
#
# Env:    GATEWAY_PORT / GEOMETRY_PORT   override ports (default 8000/8002)
#         PLAYWRIGHT_BROWSERS_PATH       honored if set; else /opt/pw-browsers
#                                        when that directory exists
#
# Idempotent and safe to re-run; exits non-zero on any failing leg.

set -euo pipefail
cd "$(dirname "$0")/.."

HOST=127.0.0.1
GATEWAY_PORT="${GATEWAY_PORT:-8000}"
GEOMETRY_PORT="${GEOMETRY_PORT:-8002}"
RUN_DIR="$(mktemp -d -t loft-e2e.XXXXXX)"
STARTED_PIDS=()

cleanup() {
  local pid
  for pid in "${STARTED_PIDS[@]-}"; do
    [[ -n "$pid" ]] || continue
    kill "$pid" 2>/dev/null || true
  done
  for pid in "${STARTED_PIDS[@]-}"; do
    [[ -n "$pid" ]] || continue
    wait "$pid" 2>/dev/null || true
  done
  rm -rf "$RUN_DIR"
}
trap cleanup EXIT

# HTTP code for a URL ("000" = no connection), never fails the script.
# NB: curl -w prints "000" itself on connection failure (and exits non-zero),
# so swallow the exit code and only default when the output is empty.
probe() {
  local code
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 2 "$1" 2>/dev/null || true)"
  echo "${code:-000}"
}

# start_service NAME APP_MODULE PORT — reuse a healthy listener or boot
# uvicorn in the background (PID recorded for cleanup) and wait for /readyz.
start_service() {
  local name="$1" app="$2" port="$3" code attempt pid
  code="$(probe "http://${HOST}:${port}/readyz")"
  if [[ "$code" == "200" ]]; then
    echo "e2e: reusing healthy ${name} on :${port}"
    return 0
  fi
  if [[ "$code" != "000" ]]; then
    echo "e2e: :${port} is occupied but /readyz returned ${code} — not a healthy ${name}." >&2
    echo "e2e: free the port (or set ${name^^}_PORT) and re-run." >&2
    return 1
  fi
  echo "e2e: starting ${name} on :${port} (log: ${RUN_DIR}/${name}.log)"
  uv run uvicorn "${app}" --host "$HOST" --port "$port" \
    >"${RUN_DIR}/${name}.log" 2>&1 &
  pid=$!
  STARTED_PIDS+=("$pid")
  for ((attempt = 1; attempt <= 30; attempt++)); do
    [[ "$(probe "http://${HOST}:${port}/readyz")" == "200" ]] && return 0
    if ! kill -0 "$pid" 2>/dev/null; then break; fi
    sleep 1
  done
  echo "e2e: ${name} failed to become ready on :${port} — log tail:" >&2
  tail -n 40 "${RUN_DIR}/${name}.log" >&2 || true
  return 1
}

echo "== e2e leg 1/2: geometry gates (goldens + STEP round-trip) =="
uv run pytest \
  services/geometry/tests/test_goldens.py \
  services/geometry/tests/test_step_roundtrip.py

echo
echo "== e2e leg 2/2: Playwright suite (@loft/web) =="
start_service geometry geometry.main:app "$GEOMETRY_PORT"
export GEOMETRY_URL="${GEOMETRY_URL:-http://${HOST}:${GEOMETRY_PORT}}"

# Gateway DB plumbing: the auth e2e needs a user store. Without a Postgres
# daemon (this sandbox), default POSTGRES_URL to the same file-backed
# aiosqlite database the gateway's own unit suite uses, and apply the
# migration-equivalent (ORM metadata create) the way its tests do.
if [[ -z "${POSTGRES_URL:-}" ]]; then
  export POSTGRES_URL="sqlite+aiosqlite:///${RUN_DIR}/gateway-e2e.db"
  echo "e2e: POSTGRES_URL unset — using ${POSTGRES_URL}"
  uv run python - <<'PY'
import asyncio
import os

from sqlalchemy.ext.asyncio import create_async_engine

from gateway.db import Base
from py_kit.db import async_dsn


async def main() -> None:
    engine = create_async_engine(async_dsn(os.environ["POSTGRES_URL"]))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


asyncio.run(main())
PY
fi

# Explicit dev posture: unset LOFT_ENV fails closed on the gateway (JWT
# secret required outside dev), so this local gate declares itself dev.
export LOFT_ENV="${LOFT_ENV:-dev}"
start_service gateway gateway.main:app "$GATEWAY_PORT"

if [[ -z "${PLAYWRIGHT_BROWSERS_PATH:-}" && -d /opt/pw-browsers ]]; then
  export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
fi
pnpm --filter @loft/web e2e

echo
echo "e2e: all legs green."
