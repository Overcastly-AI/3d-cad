#!/usr/bin/env bash
# e2e-sample-resources.sh — sample host load and per-process RSS/CPU while the
# Playwright browser leg runs, so a red shard can be read against numbers
# instead of a hypothesis.
#
# WHY (docs/BACKLOG.md CI-4, 2026-08-11): four consecutive e2e runs failed on
# three DIFFERENT single specs — a colour census, a token-pixel census and a
# gateway 502 — never the same one twice, and one of them on a commit whose diff
# cannot reach the app. That pattern points at the substrate rather than at
# three independent spec bugs, and the honest next move is to measure the
# substrate. This is the measurement.
#
# It deliberately depends on NOTHING from Playwright: no reporter, no plugin, no
# API. It writes a timestamped CSV, and the per-test timing needed to join
# against it already exists in the JSON report the workflow uploads
# (`e2e-shard-audit.py --timeline` prints tests in execution order with their
# start offsets). Two independent captures that meet on a clock beat one
# integrated capture that can only be produced in CI.
#
# Usage:  scripts/e2e-sample-resources.sh OUTPUT.csv [INTERVAL_SECONDS]
#
#         scripts/e2e.sh starts (and kills) it for you when E2E_METRICS_DIR is
#         set, which is also how CI runs it:
#             E2E_METRICS_DIR=/tmp/m scripts/e2e.sh --web-only
#         Runs locally exactly as it does on a runner — that is the point, since
#         a CI-only number is one nobody can falsify.
#
# Output: one `#` header line (nproc / MemTotal / kernel / runner label), one CSV
#         column header, then a row every INTERVAL_SECONDS (default 2):
#           epoch_ms, load1, mem_available_kb, swap_free_kb,
#           then rss_kb + cpu_pct for chrome, chrome_crashpad, node, and the
#           geometry/documents/gateway uvicorns. `node` is EVERY node process
#           summed — on a runner that is Vite plus the Playwright runner and
#           nothing else, but on a dev box it will also count your editor, so
#           read the local numbers as a shape rather than as an absolute.
#
#         cpu_pct is a DELTA of utime+stime from /proc between consecutive
#         samples — not `ps pcpu`, which is an average over the process's whole
#         lifetime and would flatten exactly the transient spikes being hunted.
#         The first row's cpu columns are therefore EMPTY, not 0: there is no
#         previous sample to difference against, and a fabricated zero in a file
#         somebody will read as evidence is worse than a blank.
#
# Costs one `ps` and one `sleep` fork per tick; everything else is a bash
# builtin read of /proc, because the sampler must not become part of the load it
# is measuring.

set -uo pipefail

OUT="${1:?usage: e2e-sample-resources.sh OUTPUT.csv [interval-seconds]}"
INTERVAL="${2:-2}"

CLK_TCK="$(getconf CLK_TCK 2>/dev/null || echo 100)"
[[ "$CLK_TCK" =~ ^[0-9]+$ ]] || CLK_TCK=100

# classify ARGV0 FULL_ARGS — the browser and node buckets match the EXECUTABLE,
# never the whole command line, and that distinction is load-bearing: a first
# cut matched `*chromium*` anywhere in argv and attributed 620 MB of RSS to
# "chrome" on a container with no browser running, because an unrelated
# long-lived process happened to mention `/opt/pw-browsers/chromium` in its
# arguments. A sampler that mis-attributes is worse than one that misses.
# The uvicorns are the exception — their executable is python, so they can only
# be told apart by the app module in their arguments.
GRP=""
classify() {
  case "$1" in
  *crashpad*)
    GRP=chrome_crashpad
    return
    ;;
  *chrome-linux/* | *headless_shell* | */chrome)
    GRP=chrome
    return
    ;;
  node | */node | */node[0-9]*)
    GRP=node
    return
    ;;
  esac
  case "$2" in
  *geometry.main:app*) GRP=geometry ;;
  *documents.main:app*) GRP=documents ;;
  *gateway.main:app*) GRP=gateway ;;
  *) GRP="" ;;
  esac
}

# NOT `GROUPS`: that is a bash special variable holding the current user's unix
# groups, and "assignments to GROUPS have no effect" — silently, so the sampler
# happily wrote a file with one column named `0_rss_kb` (root's gid) instead of
# six named ones. Caught by reading the first CSV it produced.
PROC_GROUPS=(chrome chrome_crashpad node geometry documents gateway)

TICKS=0
read_ticks() { # utime+stime for a pid, in clock ticks; 0 when it has gone
  local line rest
  TICKS=0
  # REDIRECTION ORDER MATTERS. `read -r line <FILE 2>/dev/null` does NOT silence
  # a missing file: bash's own "No such file or directory" diagnostic is emitted
  # by the redirection itself, before `read` runs, so it escapes the 2>/dev/null
  # attached to the command. Observed in a real shard run —
  # `e2e-sample-resources.sh: line 98: /proc/4604/stat: No such file or
  # directory` interleaved with Playwright output, i.e. noise in exactly the log
  # this sampler exists to make readable. A sampled process exiting mid-sweep is
  # normal, not an error. Putting 2>/dev/null FIRST silences the redirection too.
  read -r line 2>/dev/null <"/proc/$1/stat" || return 0
  # comm (field 2) is parenthesised and may contain spaces, so split after the
  # LAST ')': the remainder starts at field 3, making utime token 12, stime 13.
  rest="${line##*') '}"
  # shellcheck disable=SC2086 # deliberate word splitting of /proc/<pid>/stat
  set -- $rest
  [[ $# -ge 13 ]] || return 0
  TICKS=$((${12} + ${13}))
}

MEM_AVAILABLE=0
SWAP_FREE=0
MEM_TOTAL=0
read_meminfo() {
  local key value _unit
  MEM_AVAILABLE=0
  SWAP_FREE=0
  while read -r key value _unit; do
    case "$key" in
    MemAvailable:) MEM_AVAILABLE="$value" ;;
    SwapFree:) SWAP_FREE="$value" ;;
    MemTotal:) MEM_TOTAL="$value" ;;
    esac
  done <"/proc/meminfo"
}

now_ms() { # bash builtin clock — no `date` fork per tick
  local whole="${EPOCHREALTIME%.*}" frac="${EPOCHREALTIME#*.}"
  printf '%s%s' "$whole" "${frac:0:3}"
}

read_meminfo
header="# e2e-sample-resources"
header+=" nproc=$(nproc 2>/dev/null || echo '?')"
header+=" mem_total_kb=${MEM_TOTAL}"
header+=" kernel=$(uname -r 2>/dev/null || echo '?')"
header+=" runner=${E2E_RUNNER_LABEL:-${RUNNER_NAME:-${RUNNER_OS:-local}}}"
header+=" job=${GITHUB_JOB:-local}"
header+=" interval_s=${INTERVAL} clk_tck=${CLK_TCK}"

exec 3>"$OUT"
printf '%s\n' "$header" >&3
{
  printf 'epoch_ms,load1,mem_available_kb,swap_free_kb'
  for g in "${PROC_GROUPS[@]}"; do printf ',%s_rss_kb,%s_cpu_pct' "$g" "$g"; done
  printf '\n'
} >&3

running=1
trap 'running=0' TERM INT

declare -A PREV_TICKS=()
declare -A RSS=()
declare -A DTICKS=()
declare -A SEEN=()
PREV_MS=0

while ((running)); do
  ms="$(now_ms)"
  read -r load1 _rest </proc/loadavg
  read_meminfo

  for g in "${PROC_GROUPS[@]}"; do
    RSS["$g"]=0
    DTICKS["$g"]=0
  done
  SEEN=()
  while read -r pid rss args; do
    classify "${args%% *}" "$args"
    [[ -n "$GRP" ]] || continue
    RSS["$GRP"]=$((RSS["$GRP"] + rss))
    SEEN["$pid"]=1
    read_ticks "$pid"
    if [[ -n "${PREV_TICKS[$pid]:-}" ]]; then
      delta=$((TICKS - PREV_TICKS[$pid]))
      ((delta > 0)) && DTICKS["$GRP"]=$((DTICKS["$GRP"] + delta))
    fi
    PREV_TICKS["$pid"]=$TICKS
  done < <(ps -eo pid=,rss=,args= 2>/dev/null)
  # Forget dead pids; a 15-minute shard churns thousands of chrome children.
  for pid in "${!PREV_TICKS[@]}"; do
    [[ -n "${SEEN[$pid]:-}" ]] || unset 'PREV_TICKS[$pid]'
  done

  row="${ms},${load1},${MEM_AVAILABLE},${SWAP_FREE}"
  elapsed_ms=$((ms - PREV_MS))
  for g in "${PROC_GROUPS[@]}"; do
    if ((PREV_MS == 0 || elapsed_ms <= 0)); then
      row+=",${RSS[$g]}," # first sample: no delta exists, so no CPU claim
    else
      # ticks/CLK_TCK seconds of CPU over elapsed_ms/1000 seconds, as a percent,
      # in integer arithmetic: 100 * 1000 * ticks / (CLK_TCK * elapsed_ms).
      row+=",${RSS[$g]},$((100000 * DTICKS[$g] / (CLK_TCK * elapsed_ms)))"
    fi
  done
  printf '%s\n' "$row" >&3
  PREV_MS="$ms"

  # `sleep` is a fork, but an interruptible one: without the wait the TERM from
  # e2e.sh's trap would be handled only after the full interval.
  sleep "$INTERVAL" &
  wait $! 2>/dev/null || true
done

exec 3>&-
