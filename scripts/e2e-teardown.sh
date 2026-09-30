#!/usr/bin/env bash
# e2e-teardown.sh — BOUNDED teardown for the processes the browser legs start.
#
# SOURCED by scripts/e2e.sh and scripts/dist-leg.sh:
#     source scripts/e2e-teardown.sh
#     setsid <command> ... &        # its own process group; $! is the PGID
#     td_stop 10000 5000 "gateway=$!" ...
# EXECUTED only as `scripts/e2e-teardown.sh --self-test` (`just lint`, ~1.5 s).
#
# WHY (CI-VERDICT-HANG-1). e2e.sh's exit trap used to SIGTERM each pid and then
# `wait` on it, and `wait` is UNBOUNDED: one process that ignores or outlives
# SIGTERM holds the CI step until its 40-minute timeout. Run 34041681272 shard
# 2/4 did exactly that — playwright exited 0, the verdict printed GREEN, and
# the step then hung 18m35s inside the trap until the timeout killed it.
#
# The contract, all of it checked by the self-test below:
#   * every process is its OWN process group (`setsid`), so a signal reaches
#     the wrapper (`uv run`, `pnpm exec`) AND what it spawned. Signalling only
#     `uv` would orphan the uvicorn that actually holds the port.
#   * SIGTERM every group; poll until each group is empty or GRACE_MS passes;
#     SIGKILL the groups still alive; poll KILL_MS more. Worst case is
#     GRACE_MS + KILL_MS + one 100 ms poll. Nothing here ever `wait`s on a
#     live process: `wait` is used only to reap a leader that is already dead.
#   * every escalation is ONE log line naming the process, as a `::warning::`
#     (SIGKILL needed) or `::error::` (survived SIGKILL) so it also lands in
#     the run's annotations.
#   * the return code says what happened (0 clean, 1 SIGKILL was needed, 2
#     something survived SIGKILL) and the callers deliberately do NOT fold it
#     into their exit status: teardown runs after the verdict is decided, so it
#     can make a run slower to finish by at most the bound, never greener or
#     redder.
#
# `setsid` puts the child in a new group WITHOUT forking only when the caller
# is not itself a group leader. A background job of a non-interactive bash
# never is (no job control), so `$!` is the PGID; the self-test asserts that
# rather than assuming it.
#
# bash >= 5 ($EPOCHREALTIME). e2e.sh already needs bash 4+ (mapfile, ${x^^}).

# Milliseconds since the epoch, without forking `date` in a 100 ms poll loop.
# EPOCHREALTIME's separator follows LC_NUMERIC, so strip either.
_td_now_ms() {
  local t="${EPOCHREALTIME/[.,]/}"
  echo $((t / 1000))
}

# td_group_alive PGID — true while any NON-zombie process is in the group. A
# zombie leader is dead for every purpose that matters here (it holds no port
# and no pipe), and `kill -0` would report it alive until it is reaped.
td_group_alive() {
  ps -e -o pgid= -o stat= |
    awk -v g="$1" '$1 == g && $2 !~ /^Z/ { found = 1 } END { exit !found }'
}

# _td_poll MS ENTRY... — poll until every group is empty or MS elapse. Leaves
# the entries still alive in TD_LEFT; returns 0 when none are.
_td_poll() {
  local deadline entry
  deadline=$(($(_td_now_ms) + $1))
  shift
  while :; do
    TD_LEFT=()
    for entry in "$@"; do
      if td_group_alive "${entry##*=}"; then
        TD_LEFT+=("$entry")
      fi
    done
    ((${#TD_LEFT[@]} == 0)) && return 0
    (($(_td_now_ms) >= deadline)) && return 1
    sleep 0.1
  done
}

# td_stop GRACE_MS KILL_MS NAME=PGID... — see the contract at the top.
td_stop() {
  local grace_ms="$1" kill_ms="$2"
  shift 2
  local prefix="${TD_PREFIX:-teardown}" entry name pgid t0 rc=0
  local targets=() killed=()
  for entry in "$@"; do
    pgid="${entry##*=}"
    [[ "$pgid" =~ ^[0-9]+$ ]] || continue
    targets+=("$entry")
  done
  ((${#targets[@]} > 0)) || return 0
  t0=$(_td_now_ms)
  for entry in "${targets[@]}"; do
    kill -TERM -- "-${entry##*=}" 2>/dev/null || true
  done
  if ! _td_poll "$grace_ms" "${targets[@]}"; then
    rc=1
    killed=("${TD_LEFT[@]}")
    for entry in "${killed[@]}"; do
      name="${entry%=*}"
      pgid="${entry##*=}"
      echo "::warning::${prefix}: ${name} (pgid ${pgid}) still running" \
        "$((grace_ms / 1000)).$((grace_ms % 1000 / 100)) s after SIGTERM — sending SIGKILL"
      kill -KILL -- "-${pgid}" 2>/dev/null || true
    done
    if ! _td_poll "$kill_ms" "${killed[@]}"; then
      rc=2
      for entry in "${TD_LEFT[@]}"; do
        echo "::error::${prefix}: ${entry%=*} (pgid ${entry##*=}) survived SIGKILL" \
          "for $((kill_ms / 1000)).$((kill_ms % 1000 / 100)) s — abandoning it" \
          "(uninterruptible sleep?); the runner's orphan sweep reaps it."
      done
    fi
  fi
  # Reap the leaders that are gone. Only these: `wait` on a live one is the
  # exact defect this file exists to remove.
  for entry in "${targets[@]}"; do
    pgid="${entry##*=}"
    td_group_alive "$pgid" || wait "$pgid" 2>/dev/null || true
  done
  echo "${prefix}: stopped ${#targets[@]} process group(s) in" \
    "$(($(_td_now_ms) - t0)) ms (${targets[*]%=*})"
  return "$rc"
}

# ── self-test ──────────────────────────────────────────────────────────────
_td_self_test() {
  local dir fails=0 pid inner out rc t0 ms
  dir="$(mktemp -d -t td-selftest.XXXXXX)"
  # Fixtures leak nothing even when a check fails half-way. EXIT, not RETURN:
  # this only ever runs as the script's last act.
  # shellcheck disable=SC2064
  trap "pkill -KILL -g \$(paste -sd, '$dir/pgids' 2>/dev/null) 2>/dev/null; rm -rf '$dir'" EXIT
  check() {
    if [[ "$2" == 1 ]]; then
      echo "  ok   $1"
    else
      echo "  FAIL $1${3:+ — $3}"
      fails=$((fails + 1))
    fi
  }
  alive() { kill -0 "$1" 2>/dev/null && [[ "$(ps -o stat= -p "$1")" != Z* ]]; }
  # disown: the "Killed" job notice bash would print is expected noise here.
  started() { echo "$1" >>"$dir/pgids"; disown "$1"; }
  wait_for() { for _ in $(seq 1 50); do [[ -s "$1" ]] && return 0; sleep 0.02; done; return 1; }
  echo "e2e-teardown self-test"

  # 1. THE DEFECT, REPRODUCED — proves the stubborn fixture is honest. The old
  #    `kill; wait` against a process that ignores SIGTERM must hang; if it
  #    returns, checks 2-3 prove nothing about escalation.
  setsid bash -c 'trap "" TERM; while :; do sleep 0.05; done' &
  pid=$!
  started "$pid"
  sleep 0.1
  rc=0
  timeout 0.5 bash -c "kill $pid; while kill -0 $pid 2>/dev/null; do sleep 0.05; done" || rc=$?
  check "old kill-then-wait HANGS on a SIGTERM-ignoring process (fixture is honest)" \
    "$([[ $rc == 124 ]] && echo 1)" "rc=$rc"
  check "setsid made the background job its own group leader (pgid == \$!)" \
    "$([[ "$(ps -o pgid= -p "$pid" | tr -d ' ')" == "$pid" ]] && echo 1)"

  # 2. The new teardown bounds it: SIGKILL after the grace, named in the log.
  t0=$(_td_now_ms)
  rc=0
  out="$(TD_PREFIX=t td_stop 300 1000 "stubborn=$pid")" || rc=$?
  ms=$(($(_td_now_ms) - t0))
  check "td_stop returns within grace+kill (took ${ms} ms, bound 1300)" \
    "$(((ms < 1300)) && echo 1)"
  check "rc 1 = SIGKILL was needed" "$([[ $rc == 1 ]] && echo 1)" "rc=$rc"
  check "the escalation is one ::warning:: line naming the process" \
    "$([[ "$out" == *"::warning::t: stubborn (pgid $pid) still running 0.3 s after SIGTERM — sending SIGKILL"* ]] && echo 1)" "$out"
  check "the stubborn process is gone" "$(alive "$pid" || echo 1)"

  # 3. The wrapper obeys SIGTERM, its CHILD does not — `uv run` forwarding to a
  #    uvicorn that hangs. Signalling only the leader's pid would orphan the
  #    child on its port; the group signal must reach it.
  setsid bash -c "(trap '' TERM; echo \$BASHPID >'$dir/inner'; exec sleep 300) & wait" &
  pid=$!
  started "$pid"
  wait_for "$dir/inner"
  inner="$(cat "$dir/inner")"
  rc=0
  out="$(TD_PREFIX=t td_stop 300 1000 "wrapper=$pid")" || rc=$?
  check "a child that ignores SIGTERM under a dying wrapper is escalated (rc 1)" \
    "$([[ $rc == 1 ]] && echo 1)" "rc=$rc out=$out"
  check "that grandchild is gone, not orphaned" "$(alive "$inner" || echo 1)"

  # 4. NEGATIVE CONTROL — an ordinary process: no escalation, no warning, fast.
  #    Without this, a td_stop that SIGKILLed everything would pass 2-3.
  setsid sleep 300 &
  pid=$!
  started "$pid"
  t0=$(_td_now_ms)
  rc=0
  out="$(TD_PREFIX=t td_stop 5000 1000 "polite=$pid")" || rc=$?
  ms=$(($(_td_now_ms) - t0))
  check "a process that honours SIGTERM: rc 0, no warning, well inside the grace (${ms} ms)" \
    "$([[ $rc == 0 && "$out" != *::warning::* && $ms -lt 2000 ]] && echo 1)" "rc=$rc out=$out"
  check "and it is gone" "$(alive "$pid" || echo 1)"

  # 5. Nothing to stop / already dead / garbage pgid: silent, rc 0, instant.
  rc=0
  out="$(td_stop 300 300 "gone=$pid" "empty=" "junk=abc")" || rc=$?
  check "already-dead and empty entries are a no-op" \
    "$([[ $rc == 0 && "$out" != *::* ]] && echo 1)" "rc=$rc out=$out"

  # 6. e2e.sh must tear down BEFORE it prints the verdict — the other half of
  #    CI-VERDICT-HANG-1. Structural, because running e2e.sh needs a stack.
  local here stop_line verdict_line
  here="$(dirname "${BASH_SOURCE[0]}")"
  stop_line="$(grep -n '^stop_stack$' "$here/e2e.sh" | tail -n1 | cut -d: -f1 || true)"
  verdict_line="$(grep -n '^print_verdict ' "$here/e2e.sh" | tail -n1 | cut -d: -f1 || true)"
  check "e2e.sh calls stop_stack before print_verdict (lines ${stop_line:-?} < ${verdict_line:-?})" \
    "$([[ -n "$stop_line" && -n "$verdict_line" ]] && ((stop_line < verdict_line)) && echo 1)"

  if ((fails > 0)); then
    echo "e2e-teardown self-test: ${fails} FAILED"
    return 1
  fi
  echo "e2e-teardown self-test: all passed"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  set -euo pipefail
  if [[ "${1:-}" == "--self-test" ]]; then
    _td_self_test
  else
    echo "usage: $0 --self-test   (otherwise SOURCE this file)" >&2
    exit 2
  fi
fi
