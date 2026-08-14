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
if find /tmp/claude-0/*/tasks -name '*.output' -mmin -30 2>/dev/null | grep -q .; then
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
