#!/usr/bin/env bash
# e2e-job-verdict.sh — the LAST step of every job that runs scripts/e2e.sh.
#
#   JOB_STATUS=${{ job.status }} scripts/e2e-job-verdict.sh VERDICT_FILE STEP
#   scripts/e2e-job-verdict.sh --self-test          (`just lint`, ~50 ms)
#
# Re-prints the verdict block scripts/e2e.sh wrote (the upload steps append
# ~120 lines after the script, and a tail of the job log is the only channel
# into a red run from the dev container), then ends with ONE line that states
# the JOB's real result and exits to match it.
#
# WHY (CI-VERDICT-HANG-1). This step used to `cat` the file and `exit 0`. The
# block describes PLAYWRIGHT and is written before anything else can fail the
# job: a step timeout or OOM kill after the tests passed, the dirty-tree check,
# dist-leg.sh's test-count floor. Each of those left a red job whose log ENDED
# in "GREEN" — the job still went red, but anyone tailing the log read the
# opposite. `job.status` is the one fact here that does not come from inside
# the script.
#
# It cannot turn a red job green: it exits 0 ONLY when job.status is exactly
# `success` AND a verdict file exists, and a step's exit 0 never clears an
# earlier failure anyway. Every other combination — failure, cancelled, an
# empty status (the expression stopped resolving), no verdict file — exits 1
# and ends on a line that does not contain the word GREEN. The self-test sweeps
# that whole matrix. `continue-on-error` steps do not move job.status; the jobs
# that call this have none.
set -euo pipefail

verdict_for_job() {
  local file="$1" step="$2" status="${JOB_STATUS-}" have=0
  if [[ -s "$file" ]]; then
    cat "$file"
    have=1
  else
    echo "::error::no verdict file at ${file} — scripts/e2e.sh never reached its" \
      "summary: the job died before or during setup (uv sync / pnpm install /" \
      "browser install / service boot), or '${step}' was killed by its timeout." \
      "The reason is in '${step}' or a step before it."
    ls -la "$(dirname "$file")" 2>&1 || true
  fi
  case "$status" in
    success)
      if ((have)); then
        echo "e2e: job.status=success — this job is GREEN."
        return 0
      fi
      echo "::error::job.status is success but no verdict was written, so no test" \
        "result corroborates it. Treated as FAILED: check that E2E_LOG_DIR in" \
        "'${step}' matches the path this step reads."
      return 1
      ;;
    "")
      echo "::error::job.status did not resolve (empty), so this cross-check is" \
        "broken. Treated as FAILED until the workflow passes it again."
      return 1
      ;;
    *)
      echo "::error::THIS JOB FAILED (job.status=${status}). If the block above" \
        "reports a pass, the failure is outside the tests: '${step}' was killed" \
        "(timeout, OOM) or a later step failed (e.g. the dirty-tree check). Read" \
        "'${step}' from its end, then the steps after it."
      return 1
      ;;
  esac
}

self_test() {
  local dir fails=0 kind status rc out last
  dir="$(mktemp -d -t e2e-job-verdict.XXXXXX)"
  # shellcheck disable=SC2064
  trap "rm -rf '$dir'" EXIT
  printf '== e2e verdict ==\n0 failed, 12 passed of 12 — GREEN (playwright exit 0)\n' >"$dir/green"
  printf '== e2e verdict ==\n1 failed, 11 passed of 12 — RED (playwright exit 1)\n' >"$dir/red"
  check() {
    if [[ "$2" == 1 ]]; then
      echo "  ok   $1"
    else
      echo "  FAIL $1${3:+ — $3}"
      fails=$((fails + 1))
    fi
  }
  run() { # run KIND STATUS -> sets rc, out, last
    rc=0
    out="$(JOB_STATUS="$2" verdict_for_job "$dir/$1" "Playwright shard 1/6" 2>&1)" || rc=$?
    last="$(printf '%s\n' "$out" | tail -n1)"
  }
  echo "e2e-job-verdict self-test"

  # POSITIVE CONTROL. Without it, a script that always exits 1 would pass
  # every check below.
  run green success
  check "green block + job success: exit 0, last line says GREEN" \
    "$([[ $rc == 0 && "$last" == *"job.status=success"*GREEN* ]] && echo 1)" "rc=$rc last=$last"

  # THE DEFECT: a GREEN block over a job that failed after the tests.
  run green failure
  check "green block + job failure: exit 1, the last line is the failure, not GREEN" \
    "$([[ $rc == 1 && "$last" == *"THIS JOB FAILED (job.status=failure)"* && "$last" != *GREEN* ]] && echo 1)" \
    "rc=$rc last=$last"
  check "  ...and the block itself is still printed above it" \
    "$([[ "$out" == *"— GREEN (playwright exit 0)"* ]] && echo 1)"

  # THE PROPERTY: nothing but (success, verdict present) exits 0, and no other
  # combination's last line contains GREEN.
  for kind in green red missing; do
    for status in failure cancelled "" skipped Success garbage; do
      run "$kind" "$status"
      check "${kind} block + job.status='${status}': exit 1, last line not GREEN" \
        "$([[ $rc == 1 && "$last" != *GREEN* ]] && echo 1)" "rc=$rc last=$last"
    done
  done
  run missing success
  check "no verdict file + job success: exit 1 (a pass nothing corroborates)" \
    "$([[ $rc == 1 && "$last" != *GREEN* ]] && echo 1)" "rc=$rc last=$last"
  run missing failure
  check "no verdict file: names the step to read" \
    "$([[ "$out" == *"no verdict file"*"'Playwright shard 1/6'"* ]] && echo 1)" "$out"
  run green ""
  check "an empty job.status says the CHECK is broken, not that the shard failed" \
    "$([[ "$last" == *"did not resolve"* && "$last" != *"THIS JOB FAILED"* ]] && echo 1)" "$last"

  if ((fails > 0)); then
    echo "e2e-job-verdict self-test: ${fails} FAILED"
    return 1
  fi
  echo "e2e-job-verdict self-test: all passed"
}

case "${1:-}" in
  --self-test)
    self_test
    ;;
  "" | -*)
    echo "usage: JOB_STATUS=<job.status> $0 VERDICT_FILE STEP_NAME | $0 --self-test" >&2
    exit 2
    ;;
  *)
    verdict_for_job "$1" "${2:-the e2e step}"
    ;;
esac
