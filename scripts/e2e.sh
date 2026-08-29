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
#         trailing args  forwarded verbatim to `playwright test`, with ONE
#                        substitution: `--balanced-shard=i/N` is expanded by
#                        scripts/e2e-shard-plan.py into the file patterns for
#                        that shard. That is how CI shards, and
#                        `scripts/e2e.sh --web-only -- --balanced-shard=3/4`
#                        reproduces a CI shard locally with one command.
#
#                        Sharding stays DERIVED from the filesystem: the
#                        planner partitions the set `playwright test --list`
#                        returns, so every spec lands in exactly one shard with
#                        no list to maintain and a new spec cannot be born
#                        outside the gate (the failure mode that has bitten
#                        this repo four times — see docs/BACKLOG.md GATE-1).
#                        What the committed duration manifest changes is only
#                        WHICH shard, never WHETHER; see e2e-shard-plan.py.
#                        Playwright's own `--shard=i/N` still works and is
#                        still count-based — it is what CI used until CI-BAL
#                        measured shard 3/4 at 1.58x the median.
#
# Env:    GATEWAY_PORT / DOCUMENTS_PORT / GEOMETRY_PORT
#                                        override ports (default 8000/8001/8002)
#         PLAYWRIGHT_BROWSERS_PATH       honored if set; else /opt/pw-browsers
#                                        when that directory exists
#         E2E_JSON_REPORT                write Playwright's JSON report here
#                                        (CI reconciles the executed test count
#                                        against the discovered one, so a shard
#                                        that silently ran nothing cannot pass).
#                                        Unset -> one is still written, into the
#                                        log dir, because the verdict block this
#                                        script ends with is derived from it.
#         E2E_LOG_DIR                    write the three service logs HERE and
#                                        do NOT delete them on exit. Without it
#                                        the logs live in a mktemp dir the exit
#                                        trap removes, which is why a red CI
#                                        shard could report a gateway 502 with
#                                        no gateway log to read (docs/BACKLOG.md
#                                        CI-3/CI-4) — the evidence was destroyed
#                                        seconds before the upload step ran.
#         E2E_METRICS_DIR                sample host load + per-process RSS/CPU
#                                        into resources.csv here for the whole
#                                        browser leg (scripts/e2e-sample-
#                                        resources.sh). Joins to per-test timing
#                                        by timestamp — see `e2e-shard-audit.py
#                                        --timeline`.
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
# Service logs go to E2E_LOG_DIR when it is set, and that directory SURVIVES the
# run; RUN_DIR (sqlite stores, preflight scratch) is still removed. Splitting
# them is the whole point: the trap below used to delete the service logs on
# EXIT, so a shard that died on a gateway 502 uploaded traces and screenshots
# showing the browser's side of a failure whose cause was in a log that no
# longer existed.
LOG_DIR="${E2E_LOG_DIR:-$RUN_DIR}"
mkdir -p "$LOG_DIR"
SERVICES=(geometry documents gateway)
STARTED_PIDS=()
SAMPLER_PID=""
# Set once the browser leg is configured; print_verdict reads them.
E2E_REPORT=""
PLAYWRIGHT_LOG="${LOG_DIR}/playwright-output.log"
SHARD_LABEL=""

cleanup() {
  local pid
  if [[ -n "$SAMPLER_PID" ]]; then
    kill "$SAMPLER_PID" 2>/dev/null || true
    wait "$SAMPLER_PID" 2>/dev/null || true
  fi
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

# Tail every service log to the job output. Called when the browser leg fails,
# because an artifact nobody downloads is not evidence anybody reads — and here
# that is literal, not rhetorical: artifact download is POLICY-DENIED from the
# dev container (curl of the Azure blob URL the GitHub MCP hands back ->
# `CONNECT tunnel failed, 403`), so "it is in E2E_LOG_DIR" does not mean anybody
# can read it. The job log is the only channel. That is why this stays inline
# even though the directory now survives the run: preserved-for-download and
# readable-in-the-log are different requirements and only the second is met.
#
# What DID change (2026-08-28): it no longer prints 180 lines. On a red shard
# these logs are overwhelmingly `INFO: 127.0.0.1:53312 - "POST /api/v1/parts/…
# HTTP/1.1" 200 OK` — routine successes, which by construction are not the
# reason anything failed, and which were most of the ~300 lines that buried the
# failure list. They are dropped and COUNTED; every other line (4xx, 5xx,
# tracebacks, warnings, startup errors) is kept verbatim. The unfiltered log is
# in E2E_LOG_DIR.
dump_service_logs() {
  local name log kept dropped
  local routine='"[A-Z]+ [^"]*" (2[0-9]{2}|3[0-9]{2}) '
  for name in "${SERVICES[@]}"; do
    log="${LOG_DIR}/${name}.log"
    [[ -f "$log" ]] || continue
    kept="$(grep -vE "$routine" "$log" | tail -n 30 || true)"
    dropped="$(grep -cE "$routine" "$log" || true)"
    echo >&2
    echo "e2e: ──── ${name}.log (last 30 lines that are not routine 2xx/3xx" \
      "access logs; ${dropped:-0} of those omitted) ────" >&2
    if [[ -n "$kept" ]]; then
      printf '%s\n' "$kept" >&2
    else
      echo "(nothing but routine access logs — this service reported no error)" >&2
    fi
  done
  echo >&2
}

# THE LAST THING THIS SCRIPT PRINTS, on every path. See scripts/e2e-verdict.py
# for why it has to be last: the orchestrator's only channel into a red CI shard
# is `get_job_logs`, which returns the TAIL of the job log, and on 2026-08-28
# tails of 60/190/255 lines all failed to reach the failure list of run
# 33139349952's shard 3/4. A summary that is not last is a summary nobody can
# read.
print_verdict() {
  local status="$1"
  local args=(--status "$status" --out "${LOG_DIR}/verdict.txt")
  [[ -n "$E2E_REPORT" ]] && args+=(--report "$E2E_REPORT")
  [[ -f "$PLAYWRIGHT_LOG" ]] && args+=(--fallback-log "$PLAYWRIGHT_LOG")
  [[ -n "$SHARD_LABEL" ]] && args+=(--label "$SHARD_LABEL")
  python3 scripts/e2e-verdict.py "${args[@]}"
}

# HTTP code for a URL ("000" = no connection), never fails the script.
# NB: curl -w prints "000" itself on connection failure (and exits non-zero),
# so swallow the exit code and only default when the output is empty.
probe() {
  local code
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time "${2:-2}" "$1" 2>/dev/null || true)"
  echo "${code:-000}"
}

# CI only: prove Vite can serve THIS app on 127.0.0.1 before handing the job to
# Playwright, and say which address answered.
#
# Playwright's webServer failure is a bare "Timed out waiting …ms" that names no
# cause (its stdout is discarded by default), so the first run of the e2e
# workflow reported four identical setup deaths and zero test results — a red
# build with nothing to diagnose from. The suspected cause is that Vite forces
# dns.setDefaultResultOrder("verbatim"), so on a dual-stack host its default
# `localhost` can bind ::1 only while everything here asks for 127.0.0.1. That
# cannot be reproduced in the dev container (no IPv6 loopback), so rather than
# assert the fix works, this probes BOTH families on an isolated port and prints
# the answer. If the config fix is right this is a few quiet seconds; if it is
# wrong, the log says so in one line instead of costing another round trip.
# Side benefit: it warms node_modules/.vite before the timed webServer start.
preflight_vite() {
  local port=5199 log="${LOG_DIR}/vite-preflight.log" pid attempt v4 v6
  echo "e2e: preflight — proving Vite serves the app on ${HOST}"
  pnpm --filter @loft/web exec vite --host "$HOST" --port "$port" --strictPort \
    >"$log" 2>&1 &
  pid=$!
  for ((attempt = 1; attempt <= 120; attempt++)); do
    v4="$(probe "http://${HOST}:${port}/")"
    [[ "$v4" == "200" ]] && break
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
  done
  v4="$(probe "http://${HOST}:${port}/")"
  v6="$(probe "http://[::1]:${port}/")"
  echo "e2e: preflight — 127.0.0.1 -> ${v4}, [::1] -> ${v6}"
  if [[ "$v4" != "200" ]]; then
    echo "e2e: Vite did NOT serve the app on ${HOST}:${port}." >&2
    if [[ "$v6" == "200" ]]; then
      echo "e2e: it IS answering on [::1] — Vite bound IPv6-only, so the" >&2
      echo "e2e: --host flag in apps/web/playwright.config.ts is not taking effect." >&2
    fi
    echo "e2e: vite log:" >&2
    cat "$log" >&2 || true
    kill "$pid" 2>/dev/null || true
    return 1
  fi
  # The entry module is what actually forces dependency pre-bundling; index.html
  # can answer well before the app is servable. Needs a REAL timeout: with the
  # dep cache cold this took 5.5 s locally, and probing it with the default 2 s
  # cap reported a confident "000" for a server that was working — a diagnostic
  # line that lies is worse than no line at all.
  local t0 entry
  t0=$(date +%s%N)
  entry="$(probe "http://${HOST}:${port}/src/main.tsx" 120)"
  echo "e2e: preflight — entry module -> ${entry} in $((($(date +%s%N) - t0) / 1000000)) ms"
  sed -n '1,6p' "$log" | sed 's/^/e2e: vite: /'
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  return 0
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
  echo "e2e: starting ${name} on :${port} (log: ${LOG_DIR}/${name}.log)"
  uv run uvicorn "${app}" --host "$HOST" --port "$port" \
    >"${LOG_DIR}/${name}.log" 2>&1 &
  pid=$!
  STARTED_PIDS+=("$pid")
  for ((attempt = 1; attempt <= 30; attempt++)); do
    [[ "$(probe "http://${HOST}:${port}/readyz")" == "200" ]] && return 0
    if ! kill -0 "$pid" 2>/dev/null; then break; fi
    sleep 1
  done
  echo "e2e: ${name} failed to become ready on :${port} — log tail:" >&2
  tail -n 40 "${LOG_DIR}/${name}.log" >&2 || true
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

# --balanced-shard=i/N -> this shard's file patterns, chosen by measured
# duration rather than by test count. Done HERE, before anything is booted, so
# a planning failure costs a few seconds instead of a stack boot.
#
# It is a hard failure by design: there is no fall-back to `--shard=i/N`. A
# silent downgrade would restore the 1.58x imbalance while every log still said
# "balanced", which is the shape of every gate defect in docs/BACKLOG.md.
BALANCED_SHARD=""
if ((${#PLAYWRIGHT_ARGS[@]} > 0)); then
  for arg in "${PLAYWRIGHT_ARGS[@]}"; do
    [[ "$arg" == --balanced-shard=* ]] && BALANCED_SHARD="${arg#--balanced-shard=}"
  done
fi
if [[ -n "$BALANCED_SHARD" ]]; then
  plan_config=()
  for arg in "${PLAYWRIGHT_ARGS[@]}"; do
    [[ "$arg" == --config=* ]] && plan_config=(--config "${arg#--config=}")
  done
  plan_file="${RUN_DIR}/shard-patterns.txt"
  echo "e2e: planning ${BALANCED_SHARD} by measured duration"
  python3 scripts/e2e-shard-plan.py \
    --shard "$BALANCED_SHARD" --args-out "$plan_file" "${plan_config[@]}"
  mapfile -t plan_patterns <"$plan_file"
  if ((${#plan_patterns[@]} == 0)); then
    echo "e2e: the planner emitted no patterns for ${BALANCED_SHARD}." >&2
    exit 1
  fi
  rebuilt=()
  for arg in "${PLAYWRIGHT_ARGS[@]}"; do
    if [[ "$arg" == --balanced-shard=* ]]; then
      rebuilt+=("${plan_patterns[@]}")
    else
      rebuilt+=("$arg")
    fi
  done
  PLAYWRIGHT_ARGS=("${rebuilt[@]}")
fi

# LOAD PREFLIGHT — say what the machine looked like at the start, and warn when
# a red result will not be trustworthy.
#
# WHY THIS EARNS ITS LINES. The single largest recurring time sink in this repo
# is a contention flake investigated as a regression. On 2026-08-17 alone it
# cost THREE agents a full diagnosis each: every one of them found a red spec,
# reasonably suspected their own diff, baselined it, and every one of those
# failures then passed 2/2 in a quiet window. CLAUDE.md already documents the
# discriminator (a flake's failure point MOVES between runs; a real regression
# fails identically) but that is applied AFTER the twenty minutes are spent.
# This is the same fact, printed BEFORE.
#
# It deliberately does NOT fail the run. A loaded machine still produces a
# trustworthy GREEN — contention causes false failures, not false passes — and
# refusing to run would block the batch-end sweep that CLAUDE.md asks for. The
# only thing at stake is how a RED should be read, so this prints a line and
# gets out of the way. Set LOFT_E2E_LOAD_LIMIT to tune, or 0 to silence.
if [[ -r /proc/loadavg ]]; then
  e2e_load1="$(cut -d' ' -f1 </proc/loadavg)"
  e2e_cpus="$(nproc 2>/dev/null || echo 1)"
  e2e_limit="${LOFT_E2E_LOAD_LIMIT:-$e2e_cpus}"
  echo "e2e: 1-min load ${e2e_load1} on ${e2e_cpus} cpu(s)"
  # awk, not bash — load average is a float and [[ -gt ]] cannot compare those.
  if [[ "$e2e_limit" != "0" ]] &&
    awk -v l="$e2e_load1" -v m="$e2e_limit" 'BEGIN{exit !(l>m)}'; then
    echo "e2e: ::warning:: load ${e2e_load1} exceeds ${e2e_limit} — a FAILURE" \
      "from this run is UNCONFIRMED. Re-run the failing spec alone on a quiet" \
      "machine before diagnosing it; see CLAUDE.md on contention flakes. A" \
      "PASS is still trustworthy." >&2
  fi
fi
# Playwright's webServer sets reuseExistingServer, which is correct locally
# (compose with a running `just dev`) and a trap in CI: a stray Vite proxies
# /api at whatever gateway IT was told about, and every spec then 500s at
# register — or worse, passes against a stale bundle. On a fresh runner nothing
# should be listening, so say so loudly rather than discovering it as a spec
# failure 10 minutes later.
if [[ -n "${CI:-}" ]]; then
  if [[ "$(probe "http://${HOST}:${VITE_PORT}/")" != "000" ]]; then
    echo "e2e: something is already listening on :${VITE_PORT} in CI." >&2
    echo "e2e: Playwright would REUSE it (reuseExistingServer) and test the wrong app." >&2
    exit 1
  fi
  preflight_vite
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
#
# The JSON report is no longer CI-only. The verdict block this script ends with
# is DERIVED from it, and a summariser that only runs in CI is a summariser
# nobody has exercised before the moment somebody needs it — so when
# E2E_JSON_REPORT is unset we write one into the log dir anyway (RUN_DIR by
# default, i.e. removed on exit; E2E_LOG_DIR keeps it). Local and CI then take
# the SAME path, which is what makes `scripts/e2e.sh --web-only -- --shard=3/4`
# a faithful reproduction of a red CI shard.
# Escape hatch: a caller who passes their own --reporter keeps it, and the
# verdict falls back to parsing the captured list-reporter output.
if ! printf '%s\n' "${PLAYWRIGHT_ARGS[@]-}" | grep -q -- '--reporter'; then
  E2E_REPORT="${E2E_JSON_REPORT:-${LOG_DIR}/playwright-report.json}"
  export PLAYWRIGHT_JSON_OUTPUT_NAME="$E2E_REPORT"
  PLAYWRIGHT_ARGS+=(--reporter=list,json)
fi
# Label the verdict with the shard it belongs to — four shard logs otherwise
# produce four indistinguishable verdict blocks.
# --balanced-shard was expanded into file patterns above, so the label has to be
# taken from the value we captured then — otherwise four balanced shards produce
# four indistinguishable verdict blocks, which is the exact defect this label
# was added to fix.
if [[ -n "$BALANCED_SHARD" ]]; then
  SHARD_LABEL="shard ${BALANCED_SHARD}"
fi
for arg in "${PLAYWRIGHT_ARGS[@]-}"; do
  if [[ "$arg" == --shard=* ]]; then
    SHARD_LABEL="shard ${arg#--shard=}"
  fi
done
# Resource sampling covers the browser leg only — the stack is up, so the CSV's
# first row is already the steady state the specs run against, and everything
# after it is attributable to the suite. Killed by the exit trap.
if [[ -n "${E2E_METRICS_DIR:-}" ]]; then
  mkdir -p "$E2E_METRICS_DIR"
  scripts/e2e-sample-resources.sh "${E2E_METRICS_DIR}/resources.csv" \
    "${E2E_METRICS_INTERVAL:-2}" &
  SAMPLER_PID=$!
  echo "e2e: sampling resources every ${E2E_METRICS_INTERVAL:-2}s -> ${E2E_METRICS_DIR}/resources.csv"
fi

# NB `"${ARR[@]-}"` on an EMPTY array expands to one empty word, not zero
# (measured, bash 5.2), and playwright would read that empty string as a
# match-everything file filter. Branch on the length instead.
#
# `set -e` would abort here before the logs are tailed, so take the status by
# hand: a failing browser leg is exactly when the service logs are worth
# printing, and the script used to tail them only when a service failed to
# become READY — i.e. never in the case anybody has actually had to debug.
#
# `| tee` so the list reporter's own output is on disk as a SECOND, independent
# source for the verdict: when the JSON report is absent or malformed — exactly
# the case where a summariser would otherwise have nothing to say, and exactly
# when somebody needs it to — e2e-verdict.py recovers the failing tests from
# these lines instead of exiting quietly. PIPESTATUS[0], not $?, because tee
# always succeeds.
playwright_status=0
set +e
if ((${#PLAYWRIGHT_ARGS[@]} > 0)); then
  pnpm --filter @loft/web exec playwright test "${PLAYWRIGHT_ARGS[@]}" 2>&1 |
    tee "$PLAYWRIGHT_LOG"
else
  pnpm --filter @loft/web exec playwright test 2>&1 | tee "$PLAYWRIGHT_LOG"
fi
playwright_status=${PIPESTATUS[0]}
set -e

if ((playwright_status != 0)); then
  echo >&2
  echo "e2e: playwright exited ${playwright_status} — service logs follow." >&2
  dump_service_logs
  if [[ -n "${E2E_LOG_DIR:-}" ]]; then
    echo "e2e: full service logs kept in ${E2E_LOG_DIR}" >&2
  else
    echo "e2e: set E2E_LOG_DIR to keep the full logs past this run." >&2
  fi
else
  echo
  if [[ "$RUN_GEOMETRY" == 1 ]]; then
    echo "e2e: all legs green."
  else
    # Not "all legs green" — leg 1 did not run, and a gate that overstates what
    # it checked is how "geometry verified" ends up in a commit message that
    # never ran a golden.
    echo "e2e: browser leg green (--web-only; the geometry leg did NOT run)."
  fi
fi

# The verdict goes LAST on both paths, after the service logs and after the
# leg summary, so `tail_lines: 40` on the job log always contains the whole
# thing. It exits 3 when it cannot reconcile itself with playwright's status
# (a non-zero status it cannot explain, or a zero status over a report that
# lists failures) — and that escalates a "green" run to red, because a pass we
# cannot corroborate is not a pass.
verdict_status=0
print_verdict "$playwright_status" || verdict_status=$?
if ((playwright_status != 0)); then
  exit "$playwright_status"
fi
if ((verdict_status != 0)); then
  echo "e2e: playwright exited 0 but the verdict above does not agree with it." >&2
  exit "$verdict_status"
fi
