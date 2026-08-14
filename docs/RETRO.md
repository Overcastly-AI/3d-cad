# Retro — the loop on itself

The doc `docs/AUTONOMOUS-LOOP.md` §1.1 says this project should have, and did
not until 2026-08-14: an honest retro on the LOOP, owned by the orchestrator,
kept **in the repo**.

That last part is the reason this file exists at all. The orchestrator had been
keeping a detailed running log — 19 iterations, ~59 KB — in the session
scratchpad under `/tmp`. The scratchpad does not survive a container restart,
and the container was reclaimed **twice in three days** (a 16 h 45 m gap on
08-12, a ~30 h gap on 08-13). Every measured cause below would have been lost
and re-learned. Loop memory belongs in git.

Read this before trying to make the loop run unattended. It is a list of things
that have actually broken, with the measurement that identified each.

---

## 1. What actually stops the loop

Ranked by how much time each has cost.

### 1.1 The scheduler is session-only, and it has died SEVEN times

`CronCreate` jobs are in-memory and per-session. They are lost on container
restart and have also vanished mid-session. Each loss stops the loop dead until
a human says something.

Mitigation in place: the cron's FIRST instruction is to run `CronList` and
re-create itself if the list is empty. That covers mid-session loss. It cannot
cover container restart, because nothing is left running to notice.

**The real fix is a durable server-side Routine (`create_trigger`), and it has
been DENIED four times with `MCP tool call requires approval`.** It needs one
interactive approval from the founder. Until then the loop survives idling but
not reclamation, and "loop all night" will keep under-delivering. This is the
single highest-value unblock available.

### 1.2 Container reclamation kills in-flight agents mid-run

Observed twice. Symptom on resume: the last commit is many hours old and the
tree is dirty with a dead agent's work. The tell is `date -u` versus
`git log -1 --format=%ci` — **not** the process table, which looks healthy
because everything restarted.

Protocol when you find it: you are the relauncher. **Judge** the uncommitted
work, run the gates yourself, and commit it with honest provenance stating
whether Review and Verify ran. Never revert it. Done successfully on 08-12
(`0983935`), where the dead agent's work turned out to be sound and was verified
with 11 runs plus a mutation before being committed.

### 1.3 An intermittent harness fault strips tool parameters

Surfaces as `TelemetrySafeError: agent({schema}): StructuredOutput retry cap (5)
exceeded`, which names the symptom and hides the cause. The real error is in the
agent transcript:

> The permission handler returned updatedInput for Read that failed schema
> validation … **The tool input from the model was valid.**

Every tool call in the affected agent session is rejected before execution;
eventually it hits `StructuredOutput` too, which is why the workflow reports a
schema problem about a payload that visibly contains the required fields.

Diagnosis: grep the transcript for `permission handler returned updatedInput`.
If present, **do not touch the schema and do not resume** (the cached failure
replays) — relaunch a FRESH run. It is intermittent, hits every tool uniformly
inside an affected session, and leaves the orchestrator untouched.

Cautionary note on the diagnosis itself: seeing an `Agent`-spawned probe pass
while two `Workflow`-spawned agents failed, the orchestrator concluded the split
was Workflow-versus-Agent. It was not — a Workflow-spawned review was running
clean at the same moment. That was one data point on each side of an invented
axis. The probe had simply run in a healthy window.

### 1.4 Missing, versus the blueprint's survival layer (§1.4)

| Blueprint requirement | Status |
|---|---|
| Watchdog cron, idempotent | Present, but see §1.1 — not durable |
| Never barrier shipping on planning | Met, and improved 08-14 by deleting Pick/Plan |
| **Retry-once-then-skip** | **MISSING.** Dead agents are relaunched by hand |
| **Write-early** (append findings incrementally) | **PARTIAL.** Agents that die before reporting lose everything |
| **Always arm the next iteration** | **PARTIAL.** Cron is the only re-arm, and it dies |
| Liveness check on wakeup | Met — in the cron's step 2 |

---

## 2. The collision tax, and the structural fix we have not taken

`docs/AUTONOMOUS-LOOP.md` §1.3 says the blueprint runs each slice **in its own
git worktree with per-instance DB/ports**, and `.claude/workflows/autonomous-dev-loop.md`
repeats it. We do not do this. Every agent shares one checkout.

The cost of that choice is most of `CLAUDE.md`'s multi-agent section, and it is
not theoretical:

* `scripts/stage-doc-hunks.py` (905 lines) — the tool that exists solely to
  stop agents overwriting each other in the two shared docs — has now failed
  **three times in production, silently each time**: a whole-hunk matcher that swept a
  colleague's entry; a mis-derived line number that relocated the author's own
  entry to the end of the file; and a one-directional cross-check that let a
  bold-lead continuation truncate an entry to 7 lines of 31 while reporting
  "left 0 hunk(s) unstaged".
* A commit through an isolated index reverted a sibling's work because
  `git read-tree HEAD` had snapshotted a stale HEAD.
* A source file (`features.py`) was swept into an unrelated commit because
  `git add <one file>` is exactly as wholesale as `git add <one doc>`.

None of these can happen between worktrees. **The Agent and Workflow tools both
support `isolation: "worktree"` and we are not using it.** Adopting it would
retire a large class of defect that discipline has repeatedly failed to prevent.
Recorded here as the loop's biggest open structural improvement.

**ADOPTED AND MEASURED, 2026-08-14.** The first batch dispatched with
`isolation: 'worktree'` produced two live worktrees under `.claude/worktrees/`,
both at `5aa981a`. Two builders worked simultaneously in
`apps/web/src/sketch/**` and `apps/web/src/viewport/**` with **zero** contact:
no shared index, no `stage-doc-hunks.py`, no `GIT_INDEX_FILE` dance, nothing to
reconcile. The whole collision protocol was simply not needed.

**CORRECTION, same day, and it is the retro's own §4 class.** I wrote above that
the worktrees were "cut from the branch tip rather than from `origin/main` — the
base ref was the specific thing worth checking, and it was right." The check was
right; the conclusion was not. `5aa981a` happened to be BOTH at that moment, so
the observation could not distinguish the two hypotheses and I asserted the
flattering one. Measured properly a few hours later, across two different
dispatch mechanisms and after `main` had moved on to `5cd7216`: **every** live
worktree — the Agent-tool ones and the Workflow ones alike — still sits at
`5aa981a`. The base is the session's initial ref, PINNED. It is not the branch
tip and it is not current `main`.

Consequence, found by the VP-1a agent rather than by me: its worktree was five
commits behind and **did not contain VP-1**, the very commit it was extending —
`apps/web/e2e/sketch-orbit.spec.ts` did not exist in it. It noticed, reset its
branch to the dev tip, and said so in its report. An agent that did not notice
would have built against stale code, gated against stale code, and produced a
commit whose parent silently reverts its predecessors.

**So every worktree brief must now say: your first act is
`git fetch origin <dev branch> && git reset --hard origin/<dev branch>`, then
state in your report which SHA you actually built on.** That is cheap, and it is
the only thing standing between worktree isolation and a silent revert. The
general lesson is the one this file keeps writing down: a single observation
consistent with two explanations is not evidence for either.

One residual seam, and its fix: the same-commit rule requires every commit to
tick `docs/ROADMAP.md` + `docs/BACKLOG.md`, which would put every worktree back
in contention over exactly the two files the protocol was written for. So
**builders now commit CODE ONLY**, and the orchestrator folds the tick in at
integration (`cherry-pick` -> write the tick -> `commit --amend --no-edit`).
The rule is kept and the contention is gone. Written into
`.claude/ORCHESTRATOR.md` §2.

---

## 3. Process change, 2026-08-14: the orchestrator hands out tickets

`build-vertical-slice` (Pick → Plan → Kernel → Backend → Frontend → Review →
Verify) is retired in favour of `ticket-slice` (Build → Review → Verify) with
`{id, title, ticket, agentType, territory}` supplied by the orchestrator.

Measured justification, from this repo:

| | agents | tool calls | subagent tokens | wall clock |
|---|---|---|---|---|
| SEL-6, full slice | 7 | 536 | 1.18 M | 3 h 19 m |
| SEL-7, full slice | 7 | 506 | 1.12 M | 3 h 33 m |
| One targeted builder on SEL-7's review finding | 1 | 62 | 132 k | 17 m |

The targeted builder returned a **better** fix than its brief asked for. Pick
re-read the backlog to choose the top unchecked item — a `grep` answers that —
and died twice on §1.3's fault, burning ~132 k tokens for nothing. Plan restated
acceptance criteria the backlog entry already carried, against this repo's own
rule that briefs should *point at* criteria rather than restate them.

**Review and Verify were kept untouched**, because they are the two phases that
have caught real defects:

* SEL-1: a reticle dimmed to 2.98:1, below the WCAG 1.4.11 non-text floor.
* SEL-7: a unit test that tested **its own helper** — proved by deleting the app
  code and watching all 1584 tests stay green.
* SEL-6: a farthest-hit mutation that left **every** measured fraction unchanged
  (96.7 / 94.8 / 99.2), catchable only by an occluded-share control.

The founder's stated reason for the change is the better one: when the
orchestrator hands out the ticket it also hands out the **territory**, so two
live agents cannot be pointed at the same files. Pick chose its own item and
therefore its own files, which is how two agents end up in one file.

---

## 4. The defect class this project keeps producing

Not sloppy code — **confident claims that were never measured, and gates that
cannot fail.** Three of each were found in a single day (08-11 to 08-13):

Gates that could not fail:
* A CI guard whose `grep -q -- '--fail-on-flaky'` matched **its own prose** —
  seven occurrences in the file, one of them the actual argument, so the guard
  passed with the argument deleted.
* A unit test whose helper performed the cleanup it was asserting.
* `self_test()` returning 0 with zero checks, because `all([])` is `True`.

Claims that were false:
* `measureInkCoverage`'s docstring said off-axis rejection keeps `scribeSolved`
  out of the census. Recomputed: t = 0.81, residual **9.0** against a tolerance
  of 24 — counted. Structural, not tuning: those tokens differ almost purely in
  luminance and luminance *is* the axis. A rectangle drawn entirely in the wrong
  token clears the floor.
* The same docstring predicted a mutant reading of ~0 that the same commit had
  measured at **212.49**, forty lines away.
* Three wrong numbers in a calibration note, written by the orchestrator *while
  correcting somebody else's wrong number*.

A fourth, found 2026-08-14 and worth naming separately because the shape is
different: **a probe tested against a fixture built to match it.** The loop's
own Stop hook guarded against dispatching on top of live agents by globbing
`/tmp/claude-0/*/tasks` — one directory shallower than the path the harness
actually writes. Its test passed because the test created the fixture at the
depth the code expected. So the guard could never fire, and the hook was free to
do the one thing it was written to prevent — shipped 59 minutes after this file
was written. Found by `engineering-auditor` (K7), reproduced and fixed in
`29387da`. **When a probe reads something the environment produces, the positive
control must use the environment's own artefact, and must REFUSE rather than
pass when there is none.**

And the part that generalises furthest: writing the *negative* controls found a
SECOND defect in the same two lines that the audit had not seen — `find … |
grep -q .` is wrong under `pipefail`, because `grep -q` exits at the first match
and `find` takes SIGPIPE, so the guard reported "nothing in flight" precisely
when many outputs were fresh. One match hides it. **The negative control is
where the second bug lives** — and it has to be sized to the failure: three
fixture files let the broken form pass, two thousand failed it every time.

**Standing review question, earned: "can this gate fail? show it failing."**
And: every number written into a comment, commit message, ROADMAP or BACKLOG
entry must be one somebody measured. Inheriting a claim without re-deriving it
is how all three of the above travelled.

Note that a post-condition comparing a result against what the code *claimed*
does not catch this — a wrong claim verifies happily against itself. The fix is
a second opinion from a different derivation.

---

## 5. Environment facts that cost real time

Full detail lives in `CLAUDE.md`'s environment-recipes section; these are the
ones that specifically cost the LOOP time.

* **Reading CI is the orchestrator's job alone.** `api.github.com` is
  policy-denied from Bash and from every subagent. A brief that ends "push and
  read the run" dead-ends. Budget the relay: agents push and stop; the
  orchestrator reads and relays failures back.
* **Cheap CI logs.** Ask `get_job_logs` for a LARGE `tail_lines` (900). It
  overflows the tool limit and spills to a file at **zero context cost**; then
  parse that file with python and print only the failure lines. Guessing a small
  tail and pulling the blob into context was done four times before this was
  noticed. `get_workflow_run` on one id is **not** cheap — it returns the full
  repository object twice.
* **`list_workflow_runs` ignores `per_page`** — always ~430 KB. Spill and parse.
* **A merge can look far more dangerous than it is.** `main` reported 169
  commits ahead; its *tree* was byte-identical to the merge base, so it held no
  content the branch lacked. Check trees, not commit counts. And when a
  comparison returns a suspiciously clean answer, re-run it with stderr visible:
  a `comm` over two lists reported "zero overlapping files" only because one
  list was silently empty.

---

## 6. Open

1. ~~**Durable Routine approval** (§1.1)~~ — DONE. The founder approved it and
   an hourly Routine is armed. Known limitation: the sessions it fires have no
   MCP connectors, so they cannot read CI.
2. ~~**Worktree isolation** (§2)~~ — DONE and measured, 2026-08-14. See §2.
3. **Retry-once-then-skip and write-early** (§1.4) — write-early is now in the
   auditor briefs and worked (both 2026-08-14 audit reports survived the agents'
   deaths); retry-once-then-skip is still not implemented.
4. **CI-4**: the e2e suite is not yet trustworthy per-commit. QA7-1
   (`qa-sel7-verify:555`) has failed on two commits whose diffs cannot reach the
   code under test.
5. Several items are marked `CLOSED-PENDING-QA` — they carry a code review but
   no independent QA pass. The markers are accurate, not decorative; do not
   silently upgrade them.
