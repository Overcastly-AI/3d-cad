#!/usr/bin/env bash
# Boot / tear down an ISOLATED native stack for the concurrency load harness.
#
# Why this exists: docs/PERF.md's numbers are all single-user and in-process, so
# nothing in the repo could answer "can four people use this at once?".
# `scripts/concurrency-load.py` answers it over the real HTTP path, and it needs
# a stack that (a) does not collide with the shared dev ports (:8000-8002,
# :5173) or a running `just e2e`, and (b) can run N geometry workers so the
# worker-vs-cache tradeoff in docs/OPERATIONS.md §6 can be MEASURED rather than
# reasoned about.
#
# Ports: gateway 8510, documents 8511, geometry 8512, 8513, ... (one per worker).
# State: fresh SQLite files under $LOAD_STATE_DIR (default: a mktemp dir).
#
# N geometry PROCESSES on separate ports, not `--workers N`: the in-process mesh
# store refuses WEB_CONCURRENCY > 1 without S3 (geometry.mesh_store
# .assert_single_worker_mesh_store), and the compose topology the ops doc talks
# about (`--scale geometry=N`) is N processes behind a round-robin anyway. The
# harness does the round-robin the way compose DNS would.
#
#   scripts/load-stack.sh up 2      # gateway + documents + 2 geometry workers
#   scripts/load-stack.sh down
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="${LOAD_STATE_DIR:-/tmp/loft-load-stack}"
PIDFILE="$STATE/pids"
GATEWAY_PORT=8510
DOCUMENTS_PORT=8511
GEOMETRY_PORT_BASE=8512

wait_healthy() {
  local port="$1" name="$2" tries=0
  # OCP's cold import is ~20 s on this container, so the geometry budget is
  # generous on purpose; a real failure shows up in the log we tail below.
  until curl -fsS -m 2 "http://127.0.0.1:${port}/readyz" >/dev/null 2>&1; do
    tries=$((tries + 1))
    if [ "$tries" -gt 120 ]; then
      echo "FATAL: ${name} on :${port} never became ready" >&2
      tail -30 "$STATE/${name}.log" >&2 || true
      exit 1
    fi
    sleep 1
  done
  echo "ready: ${name} :${port}"
}

cmd_up() {
  local workers="${1:-1}"
  cmd_down >/dev/null 2>&1 || true
  mkdir -p "$STATE"
  # create_all does NOT migrate, so a db left by an earlier run would be reused
  # at ITS old schema (CLAUDE.md environment recipe). Always start from nothing.
  rm -f "$STATE"/*.db "$PIDFILE"
  local doc_dsn="sqlite+aiosqlite:///$STATE/documents.db"
  local gw_dsn="sqlite+aiosqlite:///$STATE/gateway.db"
  (cd "$ROOT" && uv run python - "$doc_dsn" "$gw_dsn" <<'PY'
import asyncio
import sys

from documents.db import Base as DocumentsBase
from gateway.db import Base as GatewayBase
from py_kit.db import async_dsn
from sqlalchemy.ext.asyncio import create_async_engine


async def main() -> None:
    for url, base in ((sys.argv[1], DocumentsBase), (sys.argv[2], GatewayBase)):
        engine = create_async_engine(async_dsn(url))
        async with engine.begin() as conn:
            await conn.run_sync(base.metadata.create_all)
        await engine.dispose()


asyncio.run(main())
PY
  )

  local geometry_urls=()
  for i in $(seq 0 $((workers - 1))); do
    local port=$((GEOMETRY_PORT_BASE + i))
    # LOFT_ENV=dev opens /metrics without a token, which is how the harness
    # scrapes loft_rebuild_cache_{hits,misses}_total per worker.
    (cd "$ROOT" && LOFT_ENV=dev nohup uv run uvicorn geometry.main:app \
      --host 127.0.0.1 --port "$port" --workers 1 \
      >"$STATE/geometry-$port.log" 2>&1 & echo $! >>"$PIDFILE")
    geometry_urls+=("http://127.0.0.1:$port")
  done

  (cd "$ROOT" && LOFT_ENV=dev POSTGRES_URL="$doc_dsn" nohup uv run uvicorn documents.main:app \
    --host 127.0.0.1 --port "$DOCUMENTS_PORT" \
    >"$STATE/documents.log" 2>&1 & echo $! >>"$PIDFILE")

  # The gateway points at the FIRST geometry worker; the harness talks to the
  # others directly. Fan-out at the gateway would need a load balancer the
  # shipped stack does not have (that absence is itself a finding).
  # REDIS_URL is inherited from the caller's environment when set (the gateway
  # rate limiter is a no-op without it — fail-open by absence), so exporting is
  # the whole wiring. An inline `${REDIS_URL:+VAR=...}` would be parsed as a
  # COMMAND here, not an assignment, and fails with "No such file or directory".
  (cd "$ROOT" && LOFT_ENV=dev POSTGRES_URL="$gw_dsn" \
    GEOMETRY_URL="${geometry_urls[0]}" \
    DOCUMENTS_URL="http://127.0.0.1:$DOCUMENTS_PORT" \
    nohup uv run uvicorn gateway.main:app \
    --host 127.0.0.1 --port "$GATEWAY_PORT" \
    >"$STATE/gateway.log" 2>&1 & echo $! >>"$PIDFILE")

  wait_healthy "$DOCUMENTS_PORT" documents
  wait_healthy "$GATEWAY_PORT" gateway
  for i in $(seq 0 $((workers - 1))); do
    wait_healthy $((GEOMETRY_PORT_BASE + i)) "geometry-$((GEOMETRY_PORT_BASE + i))"
  done
  echo "geometry workers: ${geometry_urls[*]}"
}

cmd_down() {
  # Kill by recorded PID and by the isolated ports, never by a bare `pkill -f
  # "port 85"` — that pattern matches the invoking shell's own command line.
  if [ -f "$PIDFILE" ]; then
    while read -r pid; do
      [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
    done <"$PIDFILE"
    rm -f "$PIDFILE"
  fi
  local pids
  pids="$(ps -eo pid,args | awk '/uvicorn (geometry|gateway|documents)\.main:app/ && /--port 85[0-9][0-9]/ {print $1}')"
  for pid in $pids; do kill "$pid" 2>/dev/null || true; done
  sleep 1
  for pid in $pids; do kill -9 "$pid" 2>/dev/null || true; done
  echo "down"
}

case "${1:-}" in
up) shift; cmd_up "$@" ;;
down) cmd_down ;;
*)
  echo "usage: $0 {up [geometry-workers] | down}" >&2
  exit 2
  ;;
esac
