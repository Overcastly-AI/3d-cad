#!/usr/bin/env bash
# compose-build-retry.sh — `docker compose build`, retried ONCE, and only on
# BuildKit's "error reading from server: EOF" (never on a failed build).
#
#   scripts/compose-build-retry.sh gateway documents geometry
#   scripts/compose-build-retry.sh --self-test
#
# WHY. deploy-path's backup-restore-drill went red once on e3bd6aa at step 1:
#
#   target documents: failed to receive status: rpc error: code = Unavailable
#   desc = error reading from server: EOF
#
# That is the client losing its gRPC stream to the runner's BuildKit daemon,
# not a defect in any Dockerfile; later runs of identical trees went green.
# A red that says nothing about the commit costs a ~20-minute re-run and, worse,
# teaches people that this job's reds are noise. The cause is on the runner,
# not in this repo, so one retry is the fix available here.
#
# WHAT IS RETRIED, and why it is so narrow. Exactly one retry, and only when
# the output carries that exact line (EOF_SIGNATURE, matched as a fixed string)
# AND no sign that a build step itself failed (STEP_FAILURE_RE). Everything
# else fails IMMEDIATELY with its original exit code: a Dockerfile error, a COPY
# of a missing file, a RUN that exits non-zero, a RUN whose own download was
# reset, and every OTHER gRPC or socket error ("connection reset by peer", a
# refused connection, a different `Unavailable` desc). None of those has a known
# runner-side cause here, and a retry widened by guesswork turns real failures
# into slow greens. A second EOF fails too: two in a row is a sick runner, and
# hiding that behind a loop would turn a loud red into a slow one.
#
# The retry is announced on stderr (and as a GitHub warning annotation on a
# runner), so a green that needed it is visible rather than silent.

set -euo pipefail

# The observed failure, verbatim after its `target <service>: ` prefix. A
# fixed string, never a bare "EOF": that also appears inside failing RUN steps.
EOF_SIGNATURE='failed to receive status: rpc error: code = Unavailable desc = error reading from server: EOF'
# A build step (or the Dockerfile) failed. Present => never retried, even if
# the EOF line appears beside it.
STEP_FAILURE_RE='did not complete successfully|failed to compute cache key|dockerfile parse error|failed to read dockerfile|unknown instruction'

log() { echo "compose-build-retry: $*" >&2; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/compose-build-retry.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

# is_eof_drop LOGFILE — true iff LOGFILE carries the EOF signature and no build
# failure. Separate function so the self-test grades the exact predicate used.
is_eof_drop() {
  grep -Fq -- "$EOF_SIGNATURE" "$1" && ! grep -Eq -- "$STEP_FAILURE_RE" "$1"
}

# Give a restarting daemon up to ~30 s before the one retry; never fatal (the
# retry's own failure is the verdict).
wait_for_daemon() {
  local i
  for i in 1 2 3 4 5 6; do
    if docker info >/dev/null 2>&1; then return 0; fi
    log "daemon not answering yet (probe $i/6); waiting 5 s"
    sleep "${COMPOSE_BUILD_RETRY_WAIT:-5}"
  done
  return 0
}

build_with_retry() {
  local log_file rc attempt
  for attempt in 1 2; do
    log_file="$WORK/attempt-$attempt.log"
    rc=0
    # pipefail: the pipeline's status is docker's, not tee's.
    docker compose build "$@" 2>&1 | tee "$log_file" || rc=$?
    if ((rc == 0)); then
      if ((attempt == 2)); then
        log "attempt 2 succeeded after the BuildKit EOF on attempt 1"
      fi
      return 0
    fi
    if ((attempt == 2)); then
      log "attempt 2 ALSO failed (exit $rc) — not retrying again; a second" \
        "failure in a row is a sick runner or a real defect, not a blip"
      return "$rc"
    fi
    if ! is_eof_drop "$log_file"; then
      log "build failed (exit $rc) and it is NOT the BuildKit EOF —" \
        "failing immediately, no retry"
      return "$rc"
    fi
    log "build failed (exit $rc) with the BuildKit EOF, not a build error —" \
      "retrying ONCE. Matched:"
    { grep -F -- "$EOF_SIGNATURE" "$log_file" || true; } | head -3 | sed 's/^/    /' >&2
    if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
      echo "::warning::docker compose build hit the BuildKit 'error reading from server: EOF' (runner-side daemon drop); retried once"
    fi
    wait_for_daemon
  done
}

# --self-test: a fake `docker` on PATH that replays canned outputs, one case
# per path through the policy. Every case asserts BOTH the exit code and the
# number of build attempts, so "retried when it must not" and "gave up when it
# should have retried" are each a failure.
self_test() {
  local root="$WORK" script fails=0
  script="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
  mkdir -p "$root/bin"
  cat >"$root/bin/docker" <<'FAKE'
#!/usr/bin/env bash
# Fake docker: `docker info` succeeds; `docker compose build` replays the
# outcome listed for this attempt in $FAKE_PLAN (space-separated).
if [[ "$1" == "info" ]]; then exit 0; fi
n=$(( $(cat "$FAKE_COUNT" 2>/dev/null || echo 0) + 1 ))
echo "$n" >"$FAKE_COUNT"
read -r -a plan <<<"$FAKE_PLAN"
outcome="${plan[$((n - 1))]:-ok}"
case "$outcome" in
  ok) echo " Image loft-gateway Built"; exit 0 ;;
  eof)
    # Verbatim from e3bd6aa's backup-restore-drill log.
    echo "#12 [documents 4/9] COPY packages/py-kit /app/packages/py-kit"
    echo "target documents: failed to receive status: rpc error: code = Unavailable desc = error reading from server: EOF"
    exit 1 ;;
  reset)
    echo "target documents: failed to receive status: rpc error: code = Unavailable desc = error reading from server: read unix @->/run/docker.sock: read: connection reset by peer"
    exit 17 ;;
  refused)
    echo "failed to receive status: rpc error: code = Unavailable desc = connection error: desc = \"transport: Error while dialing: dial unix /run/buildkit/buildkitd.sock: connect: connection refused\""
    exit 19 ;;
  dockerfile)
    echo 'failed to solve: failed to compute cache key: failed to calculate checksum of ref x::y: "/nope": not found'
    exit 23 ;;
  runeof)
    echo "#9 12.3 pip: ConnectionResetError: [Errno 104] connection reset by peer"
    echo "failed to receive status: rpc error: code = Unavailable desc = error reading from server: EOF"
    echo 'failed to solve: process "/bin/sh -c uv sync" did not complete successfully: exit code: 2'
    exit 2 ;;
esac
FAKE
  chmod +x "$root/bin/docker"

  # case NAME PLAN WANT_RC WANT_ATTEMPTS
  case_() {
    local name=$1 plan=$2 want_rc=$3 want_attempts=$4 rc=0 attempts
    rm -f "$root/count"
    PATH="$root/bin:$PATH" FAKE_PLAN="$plan" FAKE_COUNT="$root/count" \
      COMPOSE_BUILD_RETRY_WAIT=0 GITHUB_ACTIONS='' \
      "$script" gateway documents geometry >"$root/$name.out" 2>&1 || rc=$?
    attempts="$(cat "$root/count" 2>/dev/null || echo 0)"
    if [[ "$rc" == "$want_rc" && "$attempts" == "$want_attempts" ]]; then
      echo "  ok    $name: exit $rc after $attempts attempt(s)"
    else
      echo "  FAIL  $name: exit $rc after $attempts attempt(s)," \
        "wanted exit $want_rc after $want_attempts"
      sed 's/^/        | /' "$root/$name.out"
      fails=$((fails + 1))
    fi
  }

  echo "compose-build-retry self-test:"
  case_ clean-build "ok" 0 1
  case_ eof-then-ok "eof ok" 0 2
  case_ eof-then-real-failure-keeps-its-code "eof dockerfile" 23 2
  case_ two-eofs-give-up "eof eof" 1 2
  case_ reset-is-not-the-eof-no-retry "reset ok" 17 1
  case_ refused-is-not-the-eof-no-retry "refused ok" 19 1
  case_ dockerfile-error-no-retry "dockerfile ok" 23 1
  case_ run-step-failure-beside-eof-no-retry "runeof ok" 2 1
  # The retry must be ANNOUNCED — a silent green is the thing we refuse.
  if grep -q "retrying ONCE" "$root/eof-then-ok.out"; then
    echo "  ok    the retry is logged"
  else
    echo "  FAIL  the retry happened without a 'retrying ONCE' log line"
    fails=$((fails + 1))
  fi
  if ((fails)); then
    echo "compose-build-retry self-test: $fails case(s) FAILED" >&2
    return 1
  fi
  echo "compose-build-retry self-test: all cases pass"
}

if [[ "${1:-}" == "--self-test" ]]; then
  self_test
  exit $?
fi

build_with_retry "$@"
