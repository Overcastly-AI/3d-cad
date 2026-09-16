#!/usr/bin/env bash
# compose-verdict.sh — the last thing a compose-driving job says, and the only
# thing a reader of its CI log can afford to read.
#
# SOURCED, never executed:  . "$(dirname "$0")/compose-verdict.sh"
#
# WHY THIS EXISTS. The job log is the ONLY channel out of CI here — the
# artifact download is policy-denied (`CONNECT tunnel failed, 403`) — so what a
# job writes LAST is a first-class interface. Earned on 2026-09-15, when the
# web container exited 1 on boot and reading that out of `deploy-path` took
# THREE escalating log pulls: `tail 40` returned pure teardown chatter, `tail
# 115` returned service logs, and only `tail 175` reached the single `[emerg]`
# line that mattered. Both callers dump ~150 lines of every service's log on
# failure and the runner appends its own trailer, so an escalating tail is a
# losing strategy against an unknown amount of trailing noise. A short verdict
# emitted after the dump is not. `.github/workflows/e2e.yml` learned the same
# lesson in 2874f0a; this is that fix applied to `deploy-path`.
#
# It lives in one file because BOTH deploy-path jobs need it and a copy-paste
# pair is exactly how the two would drift (CLAUDE.md, DRY — NON-NEGOTIABLE).
#
# Contract for the caller:
#   SERVICES=(…)     the compose services this proof considers load-bearing
#   CURRENT_STEP     updated by the caller's step(); named on failure
#   VERDICT_LABEL    what to call this proof in the banner
#   VERDICT_FILE     optional path; the workflow re-prints it after its own
#                    trailing steps, since a script cannot be the last thing a
#                    JOB runs
#
# MUST be called while the containers still EXIST — `docker compose down`
# removes the very things `docker inspect` is asked about, so a verdict built
# after teardown could only ever report "nothing here".

# Per-service `docker compose ps --all --quiet` + `docker inspect -f` rather
# than `docker compose ps --format json`, whose output shape has changed across
# compose versions; `inspect -f` has been stable for years.
build_verdict() {
  local status="$1" out="$2"
  local label="${VERDICT_LABEL:-compose}"
  local svc cid state exit_code health bad=() good=()

  # A verdict that aborts halfway is worse than no verdict: it LOOKS complete.
  # This only ever runs from an EXIT trap, so relaxing -e here costs nothing.
  set +e

  # THE WALKS-NOTHING GUARD, in the one file whose entire purpose is
  # legibility. With `SERVICES` empty the loop below walks nothing, `bad` and
  # `good` stay empty, and a passing status prints "PASS — every step of this
  # proof completed." with NO container list under it — a sentence that
  # describes nothing, wearing the shape of a complete proof. It cannot turn a
  # red job green (the job's status comes from an earlier step), which is
  # exactly why it would never be noticed.
  #
  # `declare -p` rather than `${#SERVICES[@]}` because callers run under
  # `set -u`, where expanding an unset array is itself an error — and the
  # caller most likely to have forgotten to set SERVICES is the one whose
  # verdict would then die instead of explaining.
  local count=0
  declare -p SERVICES >/dev/null 2>&1 && count=${#SERVICES[@]}
  if ((count == 0)); then
    {
      echo
      echo "== ${label} verdict =="
      echo "REFUSED — SERVICES is empty, so this verdict inspected no container."
      echo "     The job's own status was: ${status}"
      echo "     A verdict that names nothing cannot be evidence of anything."
      echo "     Set SERVICES=(…) before the EXIT trap fires; see the contract"
      echo "     at the top of scripts/compose-verdict.sh."
      echo "== end ${label} verdict =="
    } >"$out" 2>&1
    return
  fi

  {
    echo
    echo "== ${label} verdict =="
    if [[ "$status" == "0" ]]; then
      echo "PASS — every step of this proof completed."
    else
      echo "FAIL at step: ${CURRENT_STEP:-unknown}"
      echo "     exit status: ${status}"
    fi

    for svc in "${SERVICES[@]}"; do
      cid="$(docker compose ps --all --quiet "$svc" 2>/dev/null | head -1)" || cid=""
      if [[ -z "$cid" ]]; then
        bad+=("$svc: no container")
        continue
      fi
      state="$(docker inspect -f '{{.State.Status}}' "$cid" 2>/dev/null)" || state="unknown"
      exit_code="$(docker inspect -f '{{.State.ExitCode}}' "$cid" 2>/dev/null)" || exit_code="?"
      health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$cid" 2>/dev/null)" || health=""
      if [[ "$state" == "running" && (-z "$health" || "$health" == "healthy") ]]; then
        good+=("$svc")
      else
        bad+=("$svc: ${state}${health:+ (health: $health)} exit=${exit_code}")
      fi
    done

    if ((${#bad[@]} > 0)); then
      echo "  container(s) not healthy: ${#bad[@]} of ${#SERVICES[@]}"
      for svc in "${bad[@]}"; do
        echo "    - $svc"
        # The LAST few lines of that ONE container. A process that dies on boot
        # writes its reason immediately before exiting, so the tail IS the
        # diagnosis — and six lines of the right container beats 200 lines of
        # all of them.
        docker compose logs --no-color --tail 6 "${svc%%:*}" 2>/dev/null |
          sed 's/^/        /' || true
      done
    fi
    if ((${#good[@]} > 0)); then
      echo "  healthy: ${good[*]}"
    fi
    echo "== end ${label} verdict =="
  } >"$out" 2>&1
}

# Print the verdict LAST (after teardown chatter) and hand a copy to the
# workflow. Callers invoke this at the very end of their EXIT trap.
emit_verdict() {
  local verdict="$1"
  cat "$verdict" >&2 || true
  if [[ -n "${VERDICT_FILE:-}" ]]; then
    cp "$verdict" "$VERDICT_FILE" 2>/dev/null || true
  fi
  rm -f "$verdict" || true
}

# ---------------------------------------------------------------------------
# Self-test. This file is SOURCED in production, so being executed directly is
# unambiguous and free to mean "prove you can fail":
#
#     bash scripts/compose-verdict.sh --self-test
#
# It needs no docker daemon — which matters, because the registry is
# policy-denied in the dev container, so the callers of this file cannot be run
# here at all and everything it does would otherwise be unverifiable outside
# CI. `docker` is stubbed on PATH, which is enough to exercise every branch.
# ---------------------------------------------------------------------------
_verdict_self_test() {
  local fails=0 tmp out
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN

  _expect() { # label, file, must-contain, must-NOT-contain
    local label="$1" file="$2" want="$3" deny="$4" ok=1
    grep -q -- "$want" "$file" || ok=0
    [[ -n "$deny" ]] && grep -q -- "$deny" "$file" && ok=0
    if ((ok)); then
      echo "  ok   $label"
    else
      echo "  FAIL $label"
      echo "       wanted: $want${deny:+ / denied: $deny}"
      sed 's/^/       | /' "$file"
      fails=$((fails + 1))
    fi
  }

  # THE GUARD. An empty SERVICES must REFUSE and must NOT print the PASS
  # sentence — asserting only that it says REFUSED would still pass if the
  # walks-nothing PASS line were printed beside it.
  # NB arrays are assigned on their own line, never as a command prefix:
  # `SERVICES=() build_verdict …` does NOT create an empty array, it puts the
  # literal string "()" in the environment, so the loop walks ONE bogus service
  # and the guard never fires. This self-test caught exactly that in its own
  # first draft, which is the argument for having it.
  VERDICT_LABEL=probe
  CURRENT_STEP=boot
  SERVICES=()

  out="$tmp/empty-pass.txt"
  build_verdict 0 "$out"
  _expect "empty SERVICES on a PASSING status REFUSES" "$out" \
    "REFUSED — SERVICES is empty" "every step of this proof completed"

  out="$tmp/empty-fail.txt"
  build_verdict 1 "$out"
  _expect "empty SERVICES on a FAILING status REFUSES too" "$out" \
    "REFUSED — SERVICES is empty" "FAIL at step"

  # An UNSET SERVICES must behave the same, not die: callers run under `set -u`,
  # and the caller most likely to have forgotten it is the one whose verdict
  # would then abort instead of explaining.
  out="$tmp/unset.txt"
  (
    set -u
    unset SERVICES
    VERDICT_LABEL=probe build_verdict 0 "$out"
  )
  _expect "an UNSET SERVICES refuses rather than aborting" "$out" \
    "REFUSED — SERVICES is empty" ""

  # THE MIRROR: with real services the guard must NOT fire, or it would replace
  # every genuine verdict with a refusal. A guard written against one failure
  # tends to encode that failure's direction; this pins the other one.
  mkdir -p "$tmp/bin"
  cat >"$tmp/bin/docker" <<'STUB'
#!/usr/bin/env bash
# Minimal stand-in: `compose ps --quiet <svc>` yields a cid, `inspect -f` answers
# from the template. "web" is deliberately unhealthy so both branches are walked.
if [[ "${1:-}" == "compose" ]]; then
  case "${2:-}" in
    ps) echo "cid-${*: -1}" ;;
    logs) echo "boom: the last line of the dying container" ;;
  esac
  exit 0
fi
if [[ "${1:-}" == "inspect" ]]; then
  cid="${*: -1}"
  case "${3:-}" in
    *State.Status*) [[ "$cid" == *web ]] && echo "exited" || echo "running" ;;
    *ExitCode*)     [[ "$cid" == *web ]] && echo "1" || echo "0" ;;
    *Health*)       echo "" ;;
  esac
  exit 0
fi
exit 0
STUB
  chmod +x "$tmp/bin/docker"

  out="$tmp/real.txt"
  SERVICES=(gateway web)
  PATH="$tmp/bin:$PATH" build_verdict 0 "$out"
  _expect "a populated SERVICES does NOT trip the guard" "$out" \
    "every step of this proof completed" "REFUSED"
  _expect "…and names the unhealthy container" "$out" "web: exited" ""
  _expect "…and names the healthy one" "$out" "healthy: gateway" ""

  if ((fails)); then
    echo "compose-verdict: SELF-TEST FAILED ($fails)" >&2
    return 1
  fi
  echo "compose-verdict: self-test passed — the verdict can refuse."
  return 0
}

# `${BASH_SOURCE[0]} == $0` is false when sourced, which is the production path.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  if [[ "${1:-}" == "--self-test" ]]; then
    _verdict_self_test
    exit $?
  fi
  echo "compose-verdict.sh is meant to be SOURCED, not executed." >&2
  echo "Run its proof with: bash $0 --self-test" >&2
  exit 2
fi
