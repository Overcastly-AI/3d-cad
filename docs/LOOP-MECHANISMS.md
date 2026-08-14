# How the loop runs, and how the agent wakes up

Researched 2026-08-14 after the loop repeatedly went idle overnight. This file
records what mechanisms exist, which we have **selected**, and what each one
does and does not survive. `.claude/ORCHESTRATOR.md` is the procedure; this is
the machinery underneath it.

---

## 1. The finding: the wake mechanism was already installed

`~/.claude/stop-hook-git-check.sh` (registered as a `Stop` hook in
`/root/.claude/launcher-settings.json`) ends with:

```bash
echo "There are uncommitted changes in the repository. …" >&2
exit 2
```

**`exit 2` on a `Stop` hook prevents Claude from stopping and continues the
conversation**, feeding stderr back as the next instruction. Every "Stop hook
feedback" message in this session was that loop firing. It already implements
the `stop_hook_active` recursion guard correctly (exit 0 when re-entered).

So we were never missing a wake mechanism. We were missing a **reason string
that says something useful**. It said "commit your changes" when it could have
said "dispatch the next Ready item".

That is the cheapest available fix and it needs no cron, no scheduler, and no
approval.

---

## 2. The four mechanisms, and what each survives

| Mechanism | Wakes on | Survives session end? | Survives container reclamation? | Status |
|---|---|---|---|---|
| **`Stop` hook, `exit 2`** | every turn end | no | no | **installed, misaimed** |
| **`SessionStart` hook, `resume` matcher** | session start/resume | n/a — it *is* the resume | yes, when a resume happens | installed for `startup`; no `resume` matcher |
| **Background task completion** | an agent/command finishing | no | no | active; this is how agent results reach the orchestrator |
| **`subscribe_pr_activity`** | CI results, review comments | yes (webhook) | yes | **available, never used** — needs an open PR |
| **GitHub Actions `schedule:`** | wall clock | yes | **yes** — runs on GitHub's runners | not set up; needs an API-key secret |
| **Routines / `create_trigger`** | wall clock | yes | yes | **denied 4× pending approval** |
| ~~Session `CronCreate`~~ | wall clock | no | no | **removed** — see §4 |

### The gap that actually cost us

Container reclamation. It happened twice in three days (16 h 45 m and ~30 h
gaps, `docs/RETRO.md` §1.2). **Only the bottom three rows survive it**, and none
of them is currently running. Everything in-session — stop hook, task
completion, chaining — dies with the container by definition.

Worth knowing before spending an approval: **Next Lane has not solved this
either.** Their own agent reports the scheduled self-check-in "needed a
permission approval that errored out", and a grep of their repo finds the
watchdog only in `docs/RETRO.md` as an unchecked `- [ ]`. This is a shared gap,
not a secret we are missing.

---

## 3. The selected workflow

**Layer 1 — in-session continuity: the `Stop` hook.**
Rewrite the reason string so it drives the loop instead of nagging about git.
It must keep the `stop_hook_active` guard, and it must have a real termination
condition — an empty Ready queue or a budget floor — or it will run until the
usage limit. Blocking a stop with nothing left to do is how a loop turns into a
bill.

**Layer 2 — surviving resume: the `SessionStart` hook.**
Add a `resume` matcher. Its stdout is **injected as context Claude sees and acts
on**, which is mechanically stronger than the pointer at line 1 of `CLAUDE.md`:
it does not depend on anyone following a link. It should inject the orchestrator
contract, the current git state, and whether work was in flight.

**Layer 3 — surviving container death: GitHub Actions on a schedule.**
`anthropics/claude-code-action@v1` in headless mode, on a `schedule:` trigger.
It runs on GitHub's infrastructure, so our container's lifetime is irrelevant.
This is the only layer that closes the gap in §2. Requires an `ANTHROPIC_API_KEY`
repository secret — a founder decision, with a cost attached.

**Layer 4 — event-driven CI: `subscribe_pr_activity`.**
Turns "read CI next turn and hope the session survives" into a wake event.
Requires an open PR to watch, which we do not currently keep. Also gets us a
reviewable diff, so it is not pure overhead.

**Ordering.** 1 is free and immediate. 2 is small. 4 is small but changes how we
merge. 3 is the only one that fixes the real gap and the only one that costs
money.

---

## 4. Why session cron was removed, and what would bring it back

Removed 2026-08-14 by founder directive. The defect was not that a timer
existed — it was that a 15-minute cron was made the **pacer** against slices
lasting 3.5 hours. It woke roughly fourteen times per slice and each wake did
more orchestrator hand-work. That was the "racing".

It also died seven times, being session-scoped and in-memory.

If a timer ever returns it must be **stall recovery, never the pacer**: its
first action is a liveness check that returns immediately if any in-flight
agent's output mtime is under 30 minutes. That is the shape Next Lane's retro
specifies and never implemented.

---

## 5. Honest limits

- The Stop hook's block payload is documented two ways — the official reference
  says `exit 2` or `{"continue": true}`; community write-ups say
  `{"decision": "block", "reason": …}`. Ours uses `exit 2` and demonstrably
  works. Do not switch forms without testing.
- A self-continuing Stop hook burns tokens with no natural stop. The
  termination condition is not optional.
- `SessionStart` fires before MCP servers finish connecting, so its script must
  not depend on MCP tools.
- Layers 1, 2 and 4 are all free. Layer 3 is not.

## Sources

- [Claude Code hooks reference](https://code.claude.com/docs/en/hooks)
- [How the agent loop works](https://code.claude.com/docs/en/agent-sdk/agent-loop)
- [Claude Code GitHub Actions](https://code.claude.com/docs/en/github-actions)
- [Loop engineering — autonomous loops with Claude Code](https://dev.classmethod.jp/en/articles/loop-engineering-claude-code-autonomous/)
- [Stop hook: force task completion](https://claudefa.st/blog/tools/hooks/stop-hook-task-enforcement)
- [Autonomous agent loops](https://claudefa.st/blog/guide/mechanics/autonomous-agent-loops)
