#!/usr/bin/env bash
# Loop driver: a `Stop` hook that hands the orchestrator its next instruction
# instead of letting the session go idle.
#
# WHY THIS SHAPE. `exit 2` on a Stop hook prevents Claude from stopping and
# feeds stderr back as the next instruction (see docs/LOOP-MECHANISMS.md). The
# existing ~/.claude/stop-hook-git-check.sh already uses that mechanism — it was
# waking the orchestrator all along, it just said "commit your changes". This
# adds the half that was missing: when the tree IS clean and there is nothing to
# push, say what to do next rather than nothing.
#
# HONEST LIMIT, so nobody expects perpetual motion: the harness sets
# `stop_hook_active` on the Stop event that follows a block, and this script
# exits 0 when it sees it. So it buys ONE extra turn per stop, not an infinite
# loop. That is deliberate — an unbounded self-continue burns the budget with no
# natural stop. The durable driver is the hourly Routine
# (trig_01NpYREN1tnixA2VTsb4qDFM); this is the nudge that stops a session
# sitting idle in between.
#
# It is also careful to do NOTHING while work is in flight. A hook that
# dispatches on top of live agents is how the previous 15-minute cron came to be
# "racing before the next cron job kicks off".

set -uo pipefail

# The in-flight probe, in one place so the guard and its control cannot drift.
# DEPTH-AGNOSTIC ON PURPOSE. The first version globbed `/tmp/claude-0/*/tasks`,
# one directory too shallow — the harness writes
# `/tmp/claude-0/<project-slug>/<session-uuid>/tasks/` — so the guard could never
# fire, and `2>/dev/null` swallowed the `No such file or directory` that would
# have said so. Found by the engineering auditor (AUDIT-ENGINEERING K7),
# reproduced here before fixing. The test that "passed" did so because its
# fixture was created at the depth the code expected: a fixture you build to
# match your code only proves your code matches your fixture.
#
# AND NO PIPE. `find … | grep -q .` is wrong under `pipefail`, which this script
# sets: grep exits at the FIRST match, find takes SIGPIPE, and the pipeline
# reports failure — so the guard says "nothing in flight" precisely when MANY
# outputs are fresh, i.e. when a batch is at its busiest. One match survives it
# (find finishes first), which is why it looked fine. `-print -quit` stops at the
# first hit with no second process to race. Found by the negative control below,
# not by reading.
TASK_ROOT=${TASK_ROOT:-/tmp/claude-0}
tasks_in_flight() {
  [[ -n "$(find "${1:-$TASK_ROOT}" -path '*/tasks/*.output' -mmin -30 \
             -print -quit 2>/dev/null)" ]]
}

# --self-test: does guard 2 fire against an output file the HARNESS produced?
# That is the control the original lacked. It REFUSES (exit 2) rather than
# passing when there is no harness output to test against, because a vacuous
# pass is the failure mode this whole finding is about.
#
# The window control needs its own root — ageing the real probe proves nothing
# while OTHER tasks are live, and this session had two. So it replays the real
# probe's path SHAPE, measured relative to the task root, under a temp dir. The
# depth is copied from the harness rather than typed in, which is the whole
# point: a fixture you author to match your code proves only that.
if [[ "${1:-}" == "--self-test" ]]; then
  probe=$(find "$TASK_ROOT" -path '*/tasks/*.output' 2>/dev/null | head -1)
  if [[ -z "$probe" ]]; then
    echo "self-test REFUSED: no harness-produced */tasks/*.output anywhere under" \
         "$TASK_ROOT, so the guard cannot be exercised. Re-run with a" \
         "background task live." >&2
    exit 2
  fi
  echo "probe: $probe"
  touch -h "$probe"
  if tasks_in_flight; then
    echo "PASS: guard 2 fires on a harness-produced task output"
  else
    echo "FAIL: guard 2 did NOT fire on $probe — the glob is wrong again" >&2
    exit 1
  fi

  fake_root=$(mktemp -d)
  trap 'rm -rf "$fake_root"' EXIT
  rel=${probe#"$TASK_ROOT"/}
  mkdir -p "$fake_root/$(dirname -- "$rel")"
  # MANY of them, not one. A single match cannot expose the SIGPIPE/pipefail
  # defect described above — the reader has nothing to race — and neither can a
  # handful, because a few short paths fit in the 64 KiB pipe buffer and `find`
  # finishes writing before the reader exits. Measured: 3 files let the piped
  # form pass; 2000 overflow the buffer and it fails deterministically.
  fake_dir="$fake_root/$(dirname -- "$rel")"
  seq 1 2000 | sed "s#^#$fake_dir/probe#; s#\$#.output#" | xargs -r touch
  if ! tasks_in_flight "$fake_root"; then
    echo "FAIL: guard 2 missed 2000 fresh outputs at the harness's own depth ($rel)" >&2
    exit 1
  fi
  touch -d '90 minutes ago' "$fake_dir"/probe*.output
  if tasks_in_flight "$fake_root"; then
    echo "FAIL: guard 2 fired on a 90-minute-old output — the window is not applied" >&2
    exit 1
  fi
  echo "PASS: guard 2 stays quiet for a 90-minute-old output"
  exit 0
fi

input=$(cat)

# 1. Already blocking. Let the stop happen; never block twice.
if [[ "$(printf '%s' "$input" | jq -r '.stop_hook_active // false')" == "true" ]]; then
  exit 0
fi

cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')
[[ -n "$cwd" && -d "$cwd" ]] && cd "$cwd" || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0

# 2. Work in flight? Say nothing. The agents will wake the orchestrator when
#    they finish, and the Routine covers the case where they never do.
#    Verify with `scripts/loop-continue.sh --self-test` while a task is live.
if tasks_in_flight; then
  exit 0
fi

# 3. Dirty tree or unpushed commits are the git hook's job, not ours — leaving
#    them to it avoids two hooks shouting different instructions at once.
if ! git diff --quiet || ! git diff --cached --quiet; then exit 0; fi
if [[ -n "$(git log --oneline @{upstream}..HEAD 2>/dev/null)" ]]; then exit 0; fi

# 4. Anything left to build? The Ready queue is the board's, not ours to guess.
ready=$(awk '/^## Ready \(top of queue\)/{f=1;next} /^## /{f=0} f && /^- \[ \]/{c++} END{print c+0}' \
  docs/BACKLOG.md 2>/dev/null)
[[ "${ready:-0}" -gt 0 ]] || exit 0

cat >&2 <<EOF
LOOP: idle, tree clean, everything pushed, and ${ready} unchecked item(s) in the
Ready queue. Do not stop — take the next step yourself.

Follow .claude/ORCHESTRATOR.md. In short:
  1. Read CI for any pushed SHA without a verdict; fix red before new work.
  2. Dispatch ONE batch: the backlog-groomer owns docs/BACKLOG.md and returns
     the batch; each builder gets isolation: 'worktree' and a disjoint
     territory; Review and Verify are not optional.
  3. You do NOT write the board, run the audits, or build. If you are editing
     docs/BACKLOG.md, stop — that is the groomer's file.

If the founder has asked you to stop, or the remaining items genuinely need a
decision only they can make, say which item and why in one line and stop.
EOF
exit 2
