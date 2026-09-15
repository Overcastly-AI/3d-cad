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
