#!/usr/bin/env bash
# dist-leg.sh — the BUILT-BUNDLE browser leg: Playwright against `vite build`
# output, served through the REAL production nginx config.
#
#   just dist-leg                       # build, serve, run the leg
#   DIST_SKIP_BUILD=1 scripts/dist-leg.sh
#   scripts/dist-leg.sh -- --grep CSP   # extra playwright args
#
# WHY IT EXISTS. Every other spec in this repo drives the Vite DEV server, so
# two things that only ship to users had never been exercised at all:
#
#   * the Content-Security-Policy in deploy/docker/web/nginx.conf, which the dev
#     server does not emit. A CSP that blocks a worker, a blob: URL or an
#     inlined font is a TOTAL failure that ships green — the page still renders.
#     Measured on this leg's first run: the policy that file's own comment
#     proposed blocked eight of the app's fonts.
#   * rollup's module graph, which is not vite's dev graph. `three@0.185.1`
#     ships a dual ESM/CJS build, so `instanceof PerspectiveCamera` is false for
#     a real camera whenever both records reach one graph — already true under
#     vitest. Nothing could say what the SHIPPED bundle does until something
#     loaded it.
#
# HOW FAITHFUL IT IS, STATED PLAINLY. The bundle is the real one and the config
# is the real one (scripts/render-web-nginx.py rewrites exactly four
# container-specific directives — listen, root, resolver, upstream — and REFUSES
# if it has to touch an add_header line). What it is NOT is the real IMAGE: the
# Docker registry is policy-denied in the dev container, so nothing here can
# build it. That half is gated where it IS observable — scripts/web-smoke.sh
# asserts the SERVED policy on the real container in deploy-path's
# compose-smoke, on all three nginx locations.
#
# The backend is scripts/e2e.sh's native boot (uvicorn + per-service SQLite),
# for the same reason the e2e workflow uses it: Postgres-specific behaviour is
# deploy-path's job, and this leg is about the front-end artifact.

set -euo pipefail
cd "$(dirname "$0")/.."

WEB_PORT="${DIST_WEB_PORT:-5290}"
GATEWAY_PORT="${GATEWAY_PORT:-8000}"
HOST=127.0.0.1
DIST_DIR="$(pwd)/apps/web/dist"
RUN_DIR="$(mktemp -d -t loft-dist-leg.XXXXXX)"
NGINX_PID=""

# nginx is not a build dependency of anything else here, so say WHICH binary is
# missing rather than letting `nginx: command not found` stand in for a design
# decision. On a GitHub runner the e2e workflow installs nginx-light; locally
# `sudo apt-get install -y --no-install-recommends nginx-light` is enough.
NGINX_BIN="${NGINX_BIN:-}"
if [[ -z "$NGINX_BIN" ]]; then
  NGINX_BIN="$(command -v nginx || true)"
  [[ -n "$NGINX_BIN" ]] || NGINX_BIN="$( [[ -x /usr/sbin/nginx ]] && echo /usr/sbin/nginx || true)"
fi
if [[ -z "$NGINX_BIN" ]]; then
  echo "dist-leg: no nginx binary found." >&2
  echo "dist-leg: this leg serves the bundle through the REAL production config," >&2
  echo "dist-leg: which is the only way the CSP gets exercised at all — serving it" >&2
  echo "dist-leg: with \`vite preview\` would leave that half untested." >&2
  echo "dist-leg: install it (apt-get install -y --no-install-recommends nginx-light)" >&2
  echo "dist-leg: or point NGINX_BIN at one." >&2
  exit 1
fi

cleanup() {
  # SCOPED TO THE PID WE STARTED. Never a pattern kill: several agents run
  # stacks in this container at once, and `pkill -f nginx` is friendly fire that
  # reads exactly like a clean teardown.
  if [[ -n "$NGINX_PID" ]] && kill -0 "$NGINX_PID" 2>/dev/null; then
    kill "$NGINX_PID" 2>/dev/null || true
    wait "$NGINX_PID" 2>/dev/null || true
  fi
  if [[ "${DIST_KEEP_RUNDIR:-0}" == "1" ]]; then
    echo "dist-leg: run dir kept at $RUN_DIR"
  else
    rm -rf "$RUN_DIR"
  fi
}
trap cleanup EXIT

probe() {
  local code
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time "${2:-3}" "$1" 2>/dev/null || true)"
  echo "${code:-000}"
}

echo "== dist leg 1/3: build the production bundle =="
if [[ "${DIST_SKIP_BUILD:-0}" == "1" ]]; then
  echo "dist-leg: DIST_SKIP_BUILD=1 — reusing whatever is in apps/web/dist"
else
  pnpm --filter @loft/web build
fi
# The build is the SUBJECT of this leg, so its output is asserted rather than
# assumed: a leg that silently ran against a stale or absent dist would be the
# `gen-check`-measuring-the-wrong-input trap in new clothes.
[[ -f "$DIST_DIR/index.html" ]] ||
  { echo "dist-leg: no $DIST_DIR/index.html — the build produced nothing" >&2; exit 1; }
dist_js_bytes=$(find "$DIST_DIR/assets" -name '*.js' -printf '%s\n' 2>/dev/null | paste -sd+ | bc || echo 0)
if [[ -z "$dist_js_bytes" || "$dist_js_bytes" -lt 1000000 ]]; then
  echo "dist-leg: only ${dist_js_bytes:-0} bytes of JS in $DIST_DIR/assets." >&2
  echo "dist-leg: the app chunk measures ~2.1 MB, so this is not the app." >&2
  exit 1
fi
echo "dist-leg: $DIST_DIR — $dist_js_bytes bytes of JS across" \
  "$(find "$DIST_DIR/assets" -name '*.js' | wc -l) chunk(s)"

echo
echo "== dist leg 2/3: serve it through deploy/docker/web/nginx.conf =="
main_conf="$(python3 scripts/render-web-nginx.py \
  --out "$RUN_DIR/nginx" --port "$WEB_PORT" --root "$DIST_DIR" \
  --gateway "${HOST}:${GATEWAY_PORT}")"
"$NGINX_BIN" -t -c "$main_conf"
# setsid, never Bash(run_in_background): the harness reaps a backgrounded stack
# together with the bind attempt that exits, and the symptom is a stack that
# answered 200 a minute ago and 000 now.
setsid nohup "$NGINX_BIN" -c "$main_conf" >"$RUN_DIR/nginx.out" 2>&1 </dev/null &
NGINX_PID=$!
for _ in $(seq 1 60); do
  [[ "$(probe "http://${HOST}:${WEB_PORT}/healthz")" == "200" ]] && break
  kill -0 "$NGINX_PID" 2>/dev/null || break
  sleep 0.5
done

# THE LOOPBACK PROBE, SHIPPED WITH THE FIX. This container has no IPv6 loopback
# and every CI runner is dual-stack, so a server that binds the wrong family
# passes here for the wrong reason and hangs there with no cause named. The
# render binds the LITERAL 127.0.0.1, which removes the ambiguity — this line is
# how a future failure costs one log line instead of a round trip.
v4="$(probe "http://${HOST}:${WEB_PORT}/healthz")"
v6="$(probe "http://[::1]:${WEB_PORT}/healthz")"
echo "dist-leg: nginx ${HOST} -> ${v4}, [::1] -> ${v6} (pid ${NGINX_PID})"
if [[ "$v4" != "200" ]]; then
  echo "dist-leg: nginx did not serve /healthz on ${HOST}:${WEB_PORT}." >&2
  [[ "$v6" == "200" ]] &&
    echo "dist-leg: it IS answering on [::1] — the listen rewrite bound the wrong family." >&2
  echo "dist-leg: nginx stdout/stderr:" >&2
  cat "$RUN_DIR/nginx.out" >&2 || true
  echo "dist-leg: nginx error log:" >&2
  tail -n 40 "$RUN_DIR/nginx/error.log" >&2 || true
  exit 1
fi
# Say what the browser will be handed, in the log, so a red run does not need a
# second trip to find out whether the policy was even served.
csp="$(curl -sS -D - -o /dev/null "http://${HOST}:${WEB_PORT}/" |
  tr -d '\r' | sed -n 's/^[Cc]ontent-[Ss]ecurity-[Pp]olicy: //p')"
if [[ -z "$csp" ]]; then
  echo "dist-leg: the entry document carries NO Content-Security-Policy." >&2
  echo "dist-leg: every 'zero violations' assertion below would then be vacuous." >&2
  exit 1
fi
echo "dist-leg: served policy — ${csp}"

echo
echo "== dist leg 3/3: the browser =="
# Delegated to e2e.sh so the backend boot, the service logs, the JSON report and
# the verdict block are the SAME ones every other browser leg uses — one place
# where a gateway 502 gets dumped, one verdict format in the CI log.
export DIST_ROOT="$DIST_DIR"
export DIST_WEB_ORIGIN="http://${HOST}:${WEB_PORT}"
export E2E_NO_VITE=1
# THE COUNT FLOOR. A green run that executed nothing is the failure this repo
# has shipped four times, and it is cheap here: a `--grep` that matches no
# file, a testDir that stops resolving, or a config change that quietly points
# at `e2e/` instead of `e2e-dist/` all produce "0 failed" and exit 0. So the
# report is read back and the number of EXECUTED tests is asserted against a
# floor.
#
# It is a floor, not an equality, so adding a test does not have to touch this
# file — but it is deliberately close to the real count, because a floor far
# below the truth is a collapse detector and nothing more: it cannot see a leg
# that silently SHRANK, which is what a refactor produces. Raise it when you
# add a test.
DIST_LEG_MIN_TESTS="${DIST_LEG_MIN_TESTS:-8}"
export E2E_JSON_REPORT="${E2E_JSON_REPORT:-$RUN_DIR/dist-leg-report.json}"

# NOT `exec`: exec replaces this shell, so the EXIT trap above would never run
# and nginx would outlive the leg — a stray listener on :5290 that the next run
# would then happily REUSE, serving a stale bundle to a green suite. Call it,
# keep the status, let the trap fire.
status=0
scripts/e2e.sh --web-only -- --config=playwright.dist.config.ts "$@" || status=$?

# Only on a GREEN run: on a red one the failures are the story and a floor
# complaint on top of them is noise. A filtered run (`-- --grep ...`) is
# expected to execute fewer, so it says so and does not judge.
if ((status == 0)); then
  if [[ ! -f "$E2E_JSON_REPORT" ]]; then
    echo "dist-leg: playwright exited 0 but wrote no JSON report at" >&2
    echo "dist-leg: $E2E_JSON_REPORT — the executed-test count cannot be" >&2
    echo "dist-leg: checked, so this pass is not corroborated." >&2
    exit 3
  fi
  ran="$(python3 -c '
import json, sys

report = json.load(open(sys.argv[1]))


def walk(suites):
    for suite in suites:
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                yield test
        yield from walk(suite.get("suites", []))


print(sum(1 for _ in walk(report.get("suites", []))))
' "$E2E_JSON_REPORT")"
  if [[ "$*" == *--grep* || "$*" == *.spec.ts* ]]; then
    echo "dist-leg: ${ran} test(s) executed (filtered run — floor not applied)"
  elif ((ran < DIST_LEG_MIN_TESTS)); then
    echo "dist-leg: GREEN over only ${ran} test(s), floor is ${DIST_LEG_MIN_TESTS}." >&2
    echo "dist-leg: a leg that examines less than it is supposed to reports" >&2
    echo "dist-leg: success for the wrong reason. Either apps/web/e2e-dist/ lost" >&2
    echo "dist-leg: specs or the config stopped resolving them." >&2
    exit 3
  else
    echo "dist-leg: ${ran} test(s) executed against the built bundle (floor ${DIST_LEG_MIN_TESTS})"
  fi
fi
exit "$status"
