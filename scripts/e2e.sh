#!/usr/bin/env bash
# e2e.sh — the `just e2e` gate: geometry gates, then the Playwright suite.
#
# Leg 1: geometry golden models + STEP round-trip (docs/GEOMETRY-QA.md).
# Leg 2: Playwright e2e for @loft/web against the real stack. The specs need
#         the geometry service (:8002), documents service (:8001), and
#         gateway (:8000); this script boots them as background uvicorn
#         processes (PIDs saved, cleaned up on exit — never killed by
#         pattern) or reuses already-healthy ones, so it composes with a
#         running `just dev` loop. Playwright's webServer config
#         starts/reuses the Vite dev server (:5173) itself.
#
# Usage:  scripts/e2e.sh [--geometry-only|--web-only] [-- <playwright args>...]
#
#         --web-only     skip leg 1. CI's e2e workflow uses this: ci.yml's
#                        `python` job already runs whole-repo pytest, so
#                        re-running the 2.4k geometry tests per shard would
#                        pay ~12 min four times over for zero new coverage.
#         --geometry-only  leg 1 only (no stack, no browser).
#         trailing args  forwarded verbatim to `playwright test`, which is how
#                        CI passes --shard=i/N. Sharding is why the per-push
#                        browser gate is affordable, and it is DERIVED from the
#                        filesystem: every spec lands in exactly one shard with
#                        no list to maintain, so a new spec cannot be born
#                        outside the gate (the failure mode that has bitten
#                        this repo four times — see docs/BACKLOG.md GATE-1).
#
# Env:    GATEWAY_PORT / DOCUMENTS_PORT / GEOMETRY_PORT
#                                        override ports (default 8000/8001/8002)
#         PLAYWRIGHT_BROWSERS_PATH       honored if set; else /opt/pw-browsers
#                                        when that directory exists
#         E2E_JSON_REPORT                write Playwright's JSON report here
#                                        (CI reconciles the executed test count
#                                        against the discovered one, so a shard
#                                        that silently ran nothing cannot pass)
#         CI                             when set, NEVER reuse a listener: every
#                                        port must be free and this script must
#                                        boot the stack itself. Reuse exists so
#                                        the gate composes with a local
#                                        `just dev`; in CI an occupied port can
#                                        only mean a stale/foreign process, and
#                                        reusing one is how a green run gets
#                                        served an app that isn't this commit.
#
# Idempotent and safe to re-run; exits non-zero on any failing leg.

set -euo pipefail
cd "$(dirname "$0")/.."

RUN_GEOMETRY=1
RUN_WEB=1
case "${1:-}" in
  --geometry-only)
    RUN_WEB=0
    shift
    ;;
  --web-only)
    RUN_GEOMETRY=0
    shift
    ;;
esac
if [[ "${1:-}" == "--" ]]; then
  shift
fi
PLAYWRIGHT_ARGS=("$@")

HOST=127.0.0.1
GATEWAY_PORT="${GATEWAY_PORT:-8000}"
DOCUMENTS_PORT="${DOCUMENTS_PORT:-8001}"
GEOMETRY_PORT="${GEOMETRY_PORT:-8002}"
VITE_PORT=5173
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
    if [[ -n "${CI:-}" ]]; then
      echo "e2e: :${port} already serves a healthy ${name}, but CI is set." >&2
      echo "e2e: refusing to reuse it — a CI run must exercise THIS commit's code." >&2
      return 1
    fi
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

# The WHOLE geometry suite, by directory — deliberately not a file list.
#
# This was a hand-written two-file allowlist (test_goldens.py +
# test_step_roundtrip.py) until 2026-07-30. Engineering audit J8 measured what
# that actually covered: 228 of 2118 geometry tests, and it EXCLUDED the
# 309-test composition matrix — the suite built specifically to catch silent
# wrong geometry, which had already found four real defects including two P0s.
# So "geometry gates green" in our Definition of Done certified ~11% of the
# suite while skipping the part that finds the P0s, and every new test file
# landed outside the gate by default.
#
# Same defect as the matrix's own hand-listed predecessor axis and G3's
# hand-listed service names: an enumerated gate cannot fail when the thing it
# enumerates grows, it just quietly stops covering. A directory can.
#
# Note ci.yml's `python` job already runs `uv run pytest` over the whole repo,
# so CI was never blind here — the gap was in the LOCAL gate an agent runs
# before committing, which is where a false "geometry verified" is most
# expensive because it is what the commit message then claims.
if [[ "$RUN_GEOMETRY" == 1 ]]; then
  echo "== e2e leg 1/2: geometry gates (full geometry suite) =="
  uv run pytest services/geometry/tests
fi

if [[ "$RUN_WEB" == 0 ]]; then
  echo
  echo "e2e: geometry leg green (--geometry-only)."
  exit 0
fi

echo
echo "== e2e leg 2/2: Playwright suite (@loft/web) =="
# Playwright's webServer sets reuseExistingServer, which is correct locally
# (compose with a running `just dev`) and a trap in CI: a stray Vite proxies
# /api at whatever gateway IT was told about, and every spec then 500s at
# register — or worse, passes against a stale bundle. On a fresh runner nothing
# should be listening, so say so loudly rather than discovering it as a spec
# failure 10 minutes later.
if [[ -n "${CI:-}" && "$(probe "http://${HOST}:${VITE_PORT}/")" != "000" ]]; then
  echo "e2e: something is already listening on :${VITE_PORT} in CI." >&2
  echo "e2e: Playwright would REUSE it (reuseExistingServer) and test the wrong app." >&2
  exit 1
fi

start_service geometry geometry.main:app "$GEOMETRY_PORT"
export GEOMETRY_URL="${GEOMETRY_URL:-http://${HOST}:${GEOMETRY_PORT}}"

# DB plumbing: the auth e2e needs a user store (gateway) and the sketcher
# e2e needs parts + features (documents). Without a Postgres daemon (this
# sandbox), each service gets its OWN file-backed aiosqlite database with
# the migration-equivalent (ORM metadata create), the way the services' own
# unit suites do. With POSTGRES_URL preset (a real dev stack), both use it.
if [[ -z "${POSTGRES_URL:-}" ]]; then
  DOCUMENTS_DB="sqlite+aiosqlite:///${RUN_DIR}/documents-e2e.db"
  GATEWAY_DB="sqlite+aiosqlite:///${RUN_DIR}/gateway-e2e.db"
  echo "e2e: POSTGRES_URL unset — using per-service sqlite stores in ${RUN_DIR}"
  uv run python - "$DOCUMENTS_DB" "$GATEWAY_DB" <<'PY'
import asyncio
import sys

from sqlalchemy.ext.asyncio import create_async_engine

from documents.db import Base as DocumentsBase
from gateway.db import Base as GatewayBase
from py_kit.db import async_dsn


async def main() -> None:
    for url, base in ((sys.argv[1], DocumentsBase), (sys.argv[2], GatewayBase)):
        engine = create_async_engine(async_dsn(url))
        async with engine.begin() as connection:
            await connection.run_sync(base.metadata.create_all)
        await engine.dispose()


asyncio.run(main())
PY
  POSTGRES_URL="$DOCUMENTS_DB" start_service documents documents.main:app "$DOCUMENTS_PORT"
  export POSTGRES_URL="$GATEWAY_DB"
else
  start_service documents documents.main:app "$DOCUMENTS_PORT"
fi
export DOCUMENTS_URL="${DOCUMENTS_URL:-http://${HOST}:${DOCUMENTS_PORT}}"

# Explicit dev posture: unset LOFT_ENV fails closed on the gateway (JWT
# secret required outside dev), so this local gate declares itself dev.
export LOFT_ENV="${LOFT_ENV:-dev}"
start_service gateway gateway.main:app "$GATEWAY_PORT"

if [[ -z "${PLAYWRIGHT_BROWSERS_PATH:-}" && -d /opt/pw-browsers ]]; then
  export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
fi

# `pnpm run <script> -- <args>` DROPS the separator in pnpm 10 and the args
# never reach the script (CLAUDE.md recipe), so invoke the binary directly —
# --shard has to arrive intact or a shard silently runs the WHOLE suite.
if [[ -n "${E2E_JSON_REPORT:-}" ]]; then
  export PLAYWRIGHT_JSON_OUTPUT_NAME="$E2E_JSON_REPORT"
  PLAYWRIGHT_ARGS+=(--reporter=list,json)
fi
# NB `"${ARR[@]-}"` on an EMPTY array expands to one empty word, not zero
# (measured, bash 5.2), and playwright would read that empty string as a
# match-everything file filter. Branch on the length instead.
if ((${#PLAYWRIGHT_ARGS[@]} > 0)); then
  pnpm --filter @loft/web exec playwright test "${PLAYWRIGHT_ARGS[@]}"
else
  pnpm --filter @loft/web exec playwright test
fi

echo
if [[ "$RUN_GEOMETRY" == 1 ]]; then
  echo "e2e: all legs green."
else
  # Not "all legs green" — leg 1 did not run, and a gate that overstates what
  # it checked is how "geometry verified" ends up in a commit message that
  # never ran a golden.
  echo "e2e: browser leg green (--web-only; the geometry leg did NOT run)."
fi
