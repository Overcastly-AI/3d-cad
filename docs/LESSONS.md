# Lessons — the history behind the rules

**This file is NOT auto-loaded, and it is not a rulebook.** The current rules
live in three places, each stated once:

- [`CLAUDE.md`](../CLAUDE.md) — the reference manual every agent loads;
- [`.claude/PROTOCOL.md`](../.claude/PROTOCOL.md) — what every agent does at
  start, commit, push, stack and evidence time;
- [`.claude/ORCHESTRATOR.md`](../.claude/ORCHESTRATOR.md) — the orchestrator's
  procedure.

This file holds the **why**: incident write-ups, measurements, and every
superseded version of a rule. Rules in those files end with
`(why: docs/LESSONS.md#<anchor>)`; the anchors below are stable, so link to
them rather than to headings.

**Read every entry as history.** The entries were moved here VERBATIM, so many
of them contain statements that were later corrected, sometimes further down
the same entry, and some read in the imperative ("do X") about an X that is no
longer the rule. **Where an entry here disagrees with CLAUDE.md, PROTOCOL.md or
ORCHESTRATOR.md, the rule file wins.** Conflicts found during the move, and how
each was decided, are under *Conflicts found during the move* below.

**How to add to it:** when a rule changes, REPLACE it in the rule file and
append the old version plus the story here, under a new `<a id>` anchor in the
right topic. Never layer a correction on top of a rule in the rule file.
(why: [pruning-2026-09-23](#pruning-2026-09-23))

---

<a id="pruning-2026-09-23"></a>

## Why this file exists (2026-09-23)

`CLAUDE.md` had grown to 165 KB / 2,281 lines, about 40k tokens loaded into
every agent's context, and most of it was dated incident write-ups with
corrections layered IN PLACE. The CI-reading recipe had about six superseding
layers, the extrude-handle mandate paragraph had two, and the port-teardown
recipe had three wrong versions. Agents read the stale layers as current. The
file had already made the point itself twice, on the same sentence: *a
correction is also a claim, and it decays exactly like the claim it replaced*
([extrude-handle-claims](#extrude-handle-claims)). Layering was the mechanism
that kept stale claims in front of every agent.

So the rule files were rewritten to hold only the current state, and
everything else moved here verbatim. The move was checked by the repo's own
rare-token conservation method ([rare-token-conservation](#rare-token-conservation)):
every backtick token and every word occurring at most twice in the ORIGINAL
`CLAUDE.md` + `ORCHESTRATOR.md` must still occur somewhere in the union of the
new `CLAUDE.md` + `ORCHESTRATOR.md` + `PROTOCOL.md` + this file.

<a id="open-conflicts"></a>

## Conflicts found during the move — all RESOLVED 2026-09-23

The move turned up two places where the layers disagreed and nothing in the
source said which one won. The orchestrator decided both on 2026-09-23. No
conflicts are open.

1. **Who writes the board tick. RESOLVED 2026-09-23: the trailer rule wins,
   and the orchestrator-writes-the-tick recipe is RETIRED.**
   `.claude/ORCHESTRATOR.md` §2 (verified 2026-08-14 on SKETCH-1 and VP-1)
   said builders commit code only and the ORCHESTRATOR writes the
   ROADMAP/BACKLOG tick at integration (`git cherry-pick`, edit both docs,
   `git commit --amend --no-edit`); see [board-tick-conflict](#board-tick-conflict).
   `CLAUDE.md`'s amended doc-sync rule (2026-09-14, [doc-tick](#doc-tick)) says
   builders use a `Doc-tick: groomer` trailer and the orchestrator dispatches
   the `backlog-groomer` before the batch closes. **Retired because the recipe
   is the orchestrator doing the groomer's job, which orchestrator rule 1
   forbids.** It also contradicted ORCHESTRATOR.md §0 ("If you find yourself
   editing `docs/BACKLOG.md`, stop") and PROTOCOL.md §2. It has been removed
   from the rule files. Do not revive it.
2. **How to pull a red job's log. RESOLVED 2026-09-23: both are right, for
   different jobs.** `CLAUDE.md` (2026-08-28, after `2874f0a` added the
   `== e2e verdict ==` block) said `tail_lines: 45`; see
   [ci-reading-procedure](#ci-reading-procedure). `.claude/ORCHESTRATOR.md` §6
   (undated) said `tail_lines=900`, which overflows the tool limit and spills
   to a file at zero context cost, then parse that file; see
   [orch-traps](#orch-traps). **The rule, now stated once in ORCHESTRATOR.md
   §0c, depends on the job:**
   - a job that ends with an `== e2e verdict ==` block (the e2e shards) gets
     `tail_lines: 45`;
   - a job with no verdict block (the `ci` jobs, `deploy-path`) gets
     `tail_lines: 900`, spilled to a file, then grep or parse the file.

## Correction chains collapsed to their last state

Each chain below was stated in place as several layers. The rule files now
carry only the last layer; the full chain is in the linked entry.

| Topic | Superseded layers | Current (last) state |
|---|---|---|
| Reading CI ([ci-reading-procedure](#ci-reading-procedure)) | spill + parse ids only; `get_job_logs` per run; `conclusion` missing (08-28); `status: "completed"` empty listing (09-11); `status: "in_progress"` filter (09-11/13) | `status` and `per_page` are IGNORED (09-16); one `list_workflow_runs` call, parse the spill for `head_sha` + `status` + `conclusion`; `get_job_logs` `failed_only` for a verdict; on a red job, `tail_lines: 45` (verdict block) or `tail_lines: 900` spilled to a file (no verdict block) |
| e2e job count ([ci-reading-procedure](#ci-reading-procedure)) | 5 jobs | 6 (`dist-bundle` added in `ed8c3d7`, 2026-09-23) |
| Concurrency ([ci-concurrency](#ci-concurrency)) | blanket `cancel-in-progress`; PR-only cancel | per-SHA push groups; ref-keyed PR groups |
| Workflow-context failures ([ci-workflow-refused](#ci-workflow-refused)) | "local gates cannot catch this" | `scripts/check-workflow-contexts.py` grades `env:` only |
| MinIO smoke ([ci-minio-withdrawn](#ci-minio-withdrawn)) | "rate limit or distribution change, not ours"; repointed to `quay.io` (`bd58416`) | withdrawn from quay.io too (2026-09-24); built from pinned source via the Go module proxy (`deploy/docker/minio.Dockerfile`) |
| Extrude handle ([extrude-handle-claims](#extrude-handle-claims)) | "a form with no handle" (FALSE since T-23); "drawn but unreachable" (09-13) | 2026-09-16 at `93733b2`: extrude, fillet, shell, datum and both pattern gauges drag; no touch pass; hole has no gauge (CRAFT-9c) |
| Doc ticks ([doc-tick](#doc-tick)) | ROADMAP + BACKLOG in the same commit | same commit OR `Doc-tick: groomer`, which is a debt the groomer clears before the batch closes |
| Port teardown ([stale-vite-teardown](#stale-vite-teardown)) | process-name grep; `ss -lptn`; `lsof -ti :PORT \| head -1` | `lsof -ti tcp:<port> -sTCP:LISTEN`, for uvicorns as well as Vite |
| Worktree seed ([worktree-seed](#worktree-seed)) | "check `git log -1`"; watch for a named SHA; audit after a batch | reset to `origin/<branch>` first, every time; the SHA moves with `main` |
| stage-doc-hunks failures ([staging-protocol](#staging-protocol)) | "failed silently three times" | five silent failures; never use it in a worktree |
| Push command ([worktree-push](#worktree-push)) | `git push -u origin <branch>` | `git push origin HEAD:<branch>`, then `git ls-remote` |
| `git add -p` ([staging-protocol](#staging-protocol)) | suggested as a fallback | unavailable (no interactive git in this container) |
| Board tick ([board-tick-conflict](#board-tick-conflict)) | orchestrator cherry-picks, edits both docs and amends at integration | RETIRED 2026-09-23; builders use `Doc-tick: groomer` and the groomer reconciles before the batch closes |
| Red job log ([open-conflicts](#open-conflicts)) | `tail_lines: 45` vs `tail_lines=900` | 45 for jobs with an `== e2e verdict ==` block; 900 spilled to a file for jobs without one |
| Where the CI procedure lives | CLAUDE.md (loaded by every agent) | `.claude/ORCHESTRATOR.md` §0c; CLAUDE.md keeps a one-line pointer (2026-09-23) |
| Wave size ([orch-red-gate](#orch-red-gate)) | N≈2–4 builders | about 3 heavy agents live; loops cap a wave at 3 builders |
| StructuredOutput fault ([orch-traps](#orch-traps)) | relaunch fresh; one canary | after two `Workflow` failures, fall back to `Agent` dispatches and run the phases by hand |

## Index

- **Orchestration and process:** [orchestrator-first](#orchestrator-first), [dispatch-not-do](#dispatch-not-do), [stop-hook](#stop-hook), [orch-why](#orch-why), [orch-three-workflows](#orch-three-workflows), [orch-send-screenshots](#orch-send-screenshots), [orch-relaunch](#orch-relaunch), [orch-red-gate](#orch-red-gate), [orch-dead-agent](#orch-dead-agent), [orch-discover](#orch-discover), [orch-worktree-seed](#orch-worktree-seed), [orch-review-verify](#orch-review-verify), [board-tick-conflict](#board-tick-conflict), [orch-no-cron](#orch-no-cron), [orch-hand-dispatch](#orch-hand-dispatch), [orch-control-run](#orch-control-run), [orch-anti-patterns](#orch-anti-patterns), [orch-traps](#orch-traps)
- **Design mandate:** [flow-directive](#flow-directive), [extrude-handle-claims](#extrude-handle-claims), [screenshot-gate](#screenshot-gate)
- **Docs in sync:** [doc-tick](#doc-tick)
- **CI:** [ci-local-gates](#ci-local-gates), [ci-access](#ci-access), [ci-reading-procedure](#ci-reading-procedure), [ci-concurrency](#ci-concurrency), [ci-unbuilt-commits](#ci-unbuilt-commits), [ci-cancelled-two-causes](#ci-cancelled-two-causes), [ci-minio-withdrawn](#ci-minio-withdrawn), [ci-workflow-refused](#ci-workflow-refused), [ci-fast-green](#ci-fast-green)
- **Git, staging and worktrees:** [staging-protocol](#staging-protocol), [update-ref](#update-ref), [marker-ids](#marker-ids), [sweep-source-files](#sweep-source-files), [worktree-push](#worktree-push), [worktree-pnpm-install](#worktree-pnpm-install), [worktree-seed](#worktree-seed), [git-stash](#git-stash), [add-and-commit](#add-and-commit)
- **Tests, gates and evidence:** [sharded-bisect](#sharded-bisect), [force-true-zero-area](#force-true-zero-area), [instanceof-dual-builds](#instanceof-dual-builds), [count-floor](#count-floor), [absent-set](#absent-set), [before-after-subtraction](#before-after-subtraction), [census-call](#census-call), [assembled-ids](#assembled-ids), [params-extra-ignore](#params-extra-ignore), [rare-token-conservation](#rare-token-conservation), [fixture-rejected](#fixture-rejected), [negative-control-downstream](#negative-control-downstream), [audit-by-question](#audit-by-question), [fastapi-routes](#fastapi-routes), [screen-position-gate](#screen-position-gate), [camera-rest](#camera-rest), [playwright-cache](#playwright-cache), [accidental-settle](#accidental-settle), [quiet-window](#quiet-window), [bisect-green-end](#bisect-green-end), [founder-screenshots](#founder-screenshots)
- **Environment:** [env-intro](#env-intro), [runpath-swap](#runpath-swap), [python-and-just](#python-and-just), [ipv6-loopback](#ipv6-loopback), [egress-map](#egress-map), [build-context-gate](#build-context-gate), [nginx-pid](#nginx-pid), [native-boot](#native-boot), [no-background-stack](#no-background-stack), [readonly-sqlite](#readonly-sqlite), [pytest-verdict-last](#pytest-verdict-last), [pytest-qq](#pytest-qq), [conftest-env-leak](#conftest-env-leak), [stale-uvicorns](#stale-uvicorns), [pnpm-dashdash](#pnpm-dashdash), [scratchpad-inspect](#scratchpad-inspect), [test-results-wiped](#test-results-wiped), [stale-vite-teardown](#stale-vite-teardown), [vite-stale-transform](#vite-stale-transform), [tailwind-preset-restart](#tailwind-preset-restart), [lint-gate](#lint-gate), [gen-verify](#gen-verify), [scoped-gate](#scoped-gate), [tailwind-probe](#tailwind-probe)
- **Prior wording of rules reworded in place:** [prior-design-standing-rules](#prior-design-standing-rules), [prior-service-boundaries](#prior-service-boundaries), [prior-commands-note](#prior-commands-note), [prior-definition-of-done](#prior-definition-of-done), [prior-dev-team](#prior-dev-team), [prior-territories](#prior-territories), [prior-token-economy](#prior-token-economy), [prior-session-start](#prior-session-start), [prior-loop-phases](#prior-loop-phases), [prior-integrate](#prior-integrate), [prior-rules-that-survive](#prior-rules-that-survive)

---

## Orchestration and process

<a id="orchestrator-first"></a>

### Why the orchestrator pointer sits at the top of CLAUDE.md

*Moved verbatim from `CLAUDE.md` lines 9–33 on 2026-09-23. Current rule: CLAUDE.md → Start here.*

**If you are the ORCHESTRATOR, open
[`.claude/ORCHESTRATOR.md`](./.claude/ORCHESTRATOR.md) now and follow it.**
It is short. This file is the reference manual; that one is the procedure.

It is placed here, at line 1, because the previous pointer to it sat at line
338 of a 1017-line file and the process it describes was consequently not
followed. The founder's summary of what that cost: *"none of the agents are
being used in the project. You are constantly over writing files and then
wasting tokens trying to fix and racing before the next cron job kicks off."*

The four rules, so they are in your context even if you read nothing else:

1. **You dispatch and integrate. You do not do the org's job.** The
   `backlog-groomer` owns `docs/BACKLOG.md`. The auditors own the audit docs.
   Builders write code; reviewers review; QA exercises the real app. **If you
   are editing the backlog yourself, you have already gone wrong.**
2. **Use the agents.** There are fourteen in `.claude/agents/`. On 2026-08-14
   an audit found eight had never been invoked — the entire direction layer was
   dead and the orchestrator was doing it by hand, in the most expensive context
   in the system.
3. **Builders get their own worktree** (`isolation: 'worktree'`). A shared
   checkout is the root of every overwrite, and of the staging tool that has
   failed silently three times.
4. **Reading CI is yours alone** — `api.github.com` is denied to every
   subagent. Agents push and stop; you read the run and relay failures back.

<a id="dispatch-not-do"></a>

### The orchestrator does not do the org's job; worktrees; doc edits last

*Moved verbatim from `CLAUDE.md` lines 777–810 on 2026-09-23. Current rule: CLAUDE.md → Orchestration rules.*

**READ THIS FIRST — most of the rules below exist because we were not doing the
two things at the top of this list, and they become far less load-bearing once
we are.**

- **THE ORCHESTRATOR DISPATCHES AND INTEGRATES. IT DOES NOT DO THE ORG'S JOB.**
  Audited 2026-08-14 after the founder said "none of the agents are being used":
  eight of the fourteen agents in `.claude/agents/` had never been invoked, and
  the orchestrator had been writing `docs/BACKLOG.md` ITSELF — `file CI-4`,
  `file REV-1..REV-5`, `file QA7-1` are all orchestrator commits. That is the
  `backlog-groomer`'s entire job, performed in the most expensive context in the
  system. Every symptom followed from it: two classes of writer on the shared
  docs (hence overwrites, hence the staging tool below), audits done by hand
  instead of by `product-auditor`/`engineering-auditor`, and a cron racing its
  own slices. **The groomer owns the board. The auditors own the audit docs. The
  builders own their code. The orchestrator hands out tickets, integrates green
  branches, and reads CI — which is the one thing no subagent can do.**
- **BUILD IN WORKTREES.** Give every parallel builder `isolation: 'worktree'`.
  We documented this at `.claude/workflows/autonomous-dev-loop.md` for weeks and
  never did it, and the cost is most of this section: a shared index is the only
  reason `git add` can sweep a colleague, the only reason a stale `read-tree`
  can revert one, and the only reason `stage-doc-hunks.py` exists. Next-Lane
  runs the same loop with worktrees and has no equivalent script at all.
- **DOC EDITS ARE THE LAST STEP, STAGED AND COMMITTED IN THE SAME TURN.** This
  is Next-Lane's actual mitigation for the shared-doc race, and it is cheaper
  and more reliable than ours. Never leave `docs/ROADMAP.md` / `docs/BACKLOG.md`
  edits unstaged across other tool calls — that window is the whole hazard. When
  several agents must touch the same docs, serialize the doc-writers or give one
  a worktree. `scripts/stage-doc-hunks.py` is now a FALLBACK for the
  unavoidable shared-tree case, not the default path: it is 905 lines, it has
  failed silently three times in production (swept a colleague's entry;
  relocated the author's own entry to the end of the file; truncated an entry to
  7 lines of 31 while reporting "left 0 hunk(s) unstaged"), and every one of
  those failures was a cost of sharing a tree rather than a reason to trust the
  tool. Read `git diff --cached` in full before every commit regardless.

<a id="stop-hook"></a>

### The stop-hook false positive; liveness; verify before trusting

*Moved verbatim from `CLAUDE.md` lines 1038–1061 on 2026-09-23. Current rule: CLAUDE.md → Orchestration rules.*

- **The stop-hook "there are uncommitted changes, please commit and push" is a
  FALSE POSITIVE whenever agents are in flight, and obeying it literally is the
  sweeping defect above at its worst.** The hook cannot tell your work from four
  colleagues' half-finished work; during a parallel batch the tree is *supposed*
  to be dirty, and "commit and push these changes" would produce one commit
  containing four agents' unfinished slices under a message describing none of
  them. Seen repeatedly on 2026-07-31 with four agents live. The correct response
  is to VERIFY, not to comply: `git diff --cached --name-only` empty (nothing of
  yours staged) and `git log --oneline origin/<branch>..HEAD` empty (nothing of
  yours unpushed) means you are clean and the dirt is theirs. Map the dirty paths
  to territories and say so; do not commit, do not stash, do not revert. Only if
  one of those two checks is non-empty do you actually owe a commit.
- **Liveness (orchestrator duty).** On every wakeup, check in-flight agents'
  output mtimes; >30 min stale without a known long gate = investigate, reap,
  relaunch. A dead agent's uncommitted work is preserved and reconciled by
  its relauncher, never reverted.
- **Verify before trusting.** The orchestrator re-runs a targeted slice of a
  completed agent's gates before reporting its work done.
- **Run gates in the foreground** — never end a turn waiting on your own
  backgrounded build/test.
- **Founder updates are results-first:** what shipped + evidence
  (numbers, screenshots), then what's running, then what's next — proactively
  at milestones.

<a id="orch-why"></a>

### Why the orchestrator playbook exists

*Moved verbatim from `.claude/ORCHESTRATOR.md` lines 5–7 on 2026-09-23. Current rule: ORCHESTRATOR.md.*

You are the orchestrator. This file is what you follow. It exists because the
loop was rebuilt on 2026-08-14 after the founder pointed out that the agents
were not being used and the orchestrator was doing their work by hand.

<a id="orch-three-workflows"></a>

### Reading CI means all three workflows

*Moved verbatim from `.claude/ORCHESTRATOR.md` lines 29–39 on 2026-09-23. Current rule: ORCHESTRATOR.md §0.*

1. **Reading CI.** `api.github.com` is policy-denied for every subagent. You are
   the only one who can see a run, so you read it and relay failures back.
   **THERE ARE THREE WORKFLOWS AND `ci` IS ONLY ONE OF THEM** — `ci.yml`,
   `e2e.yml`, `deploy-path.yml`. Reading `ci` alone and saying "CI is green" is
   a false statement about the build, and I made it repeatedly on 2026-08-14
   while `e2e` had been RED for **ten consecutive commits** (last green
   `a34382b`; red from `221a7ca` onward, which is a DOCS-ONLY commit, so the
   red was never in anyone's diff). Nobody caught it because the sentence
   "green on ci" is true and reads like the whole answer. Check all three, name
   which one you checked, and treat "green" as a claim that needs the same
   measurement discipline as any other.

<a id="orch-send-screenshots"></a>

### Sending every screenshot a commit adds

*Moved verbatim from `.claude/ORCHESTRATOR.md` lines 42–53 on 2026-09-23. Current rule: ORCHESTRATOR.md §0.*

**AND SENDING ANY SCREENSHOTS THE COMMIT ADDS, IN THE SAME TURN.** CLAUDE.md's
design mandate says "surfaced" means the orchestrator SENDS them with the
file-send tool — a PNG the founder never sees does not count. Make it
mechanical, because judgement fails here: after every cherry-pick, run
`git show --name-only <sha> -- docs/screenshots/` and send whatever it lists.
Measured 2026-08-15 when the founder had to ask: 17 shots were added across
the session and I sent 12. The five I sat on were the two that most directly
showed his own reported bugs — `dimension-pick-before-desktop.png`, which has
the whole "cannot assign a dimension" defect in one frame, and the SKETCH-1
re-open pair. I sent the shots for the two tickets whose agents happened to
mention screenshots in their reports, and missed the ones whose agents merely
committed them. Do not rely on the report; read the diff.

<a id="orch-relaunch"></a>

### Relaunching a dead agent: assume the tree is booby-trapped

*Moved verbatim from `.claude/ORCHESTRATOR.md` lines 54–64 on 2026-09-23. Current rule: ORCHESTRATOR.md §0.*

4. **Relaunching dead agents** and reconciling their preserved work. **Run the
   gates that agent's work was ABOUT, not the gates that are cheap** — and read
   `git diff --cached` in full, every hunk, before committing it. On 2026-08-15 a
   reconciliation of mine (`0580f7d`) shipped a stopped agent's
   `// MUTANT: always 0` constant as product code: I ran lint and the unit suite,
   both structurally incapable of seeing an e2e-diagnostics change, and the one
   gate that could see it was the one I skipped. It then failed on every commit
   for the next ten. Mutation testing is MANDATORY here, so an agent killed
   mid-mutation leaves sabotage that is by construction invisible to every gate
   except the one it was aimed at. Assume the tree is booby-trapped, not merely
   unfinished.

<a id="orch-red-gate"></a>

### A red gate stops the line; fan-out does not beat the session limit (2026-09-23)

*Moved verbatim from `.claude/ORCHESTRATOR.md` lines 74–124 on 2026-09-23. Current rule: ORCHESTRATOR.md §0b.*

**Added 2026-09-23 after the founder said "Something is failing. We have tons of
agents. Something needs to be fixed!" — and was right.** `e2e` stayed red for
~15 consecutive commits while up to seven agents did other work. Three
mechanisms, all orchestrator decisions:

1. **Fan-out died to the session limit — twice — and stranded finished work.**
   Five or six Opus agents at 250–480K tokens each exhausted the session
   together; every one was killed mid-flight. Result: a complete QA commit
   (`54462f6`) and a complete 1,661-line touch spec sat UNPUSHED in worktrees,
   and ~2,600 lines of fixes sat uncommitted. Motion without convergence.
2. **Nobody owned "make e2e green".** The fixing agent died with everyone else;
   the survivors each owned a feature, so the red belonged to no one.
3. **I gave two agents overlapping territory** (the re-fit agent and the
   pick-proxy agent both edited four overlay files). The "disjoint territories"
   rule only works if the brief is actually disjoint — check the file lists
   against each other before dispatch, not after.

**Rules:**
- **When `e2e` (or any of the three workflows) is red on the tip, ONE agent owns
  greening it end-to-end, and new feature work waits.** A red tip is the
  batch's only priority. Name the owner in the brief.
- **Keep ~3 heavy agents live, not 6.** Past that, the session limit kills the
  whole wave and the work is stranded. A cheap `sonnet` groomer does not count
  against the three.
- **Briefs say "push after each gated fix, not at the end."** A fix in a
  worktree when the limit hits is worth nothing.
- **After any limit hit, first salvage: `git -C <worktree> status` +
  `log origin/<branch>..HEAD` for every worktree, patch everything to the
  scratchpad, then RESUME the agents (SendMessage keeps their context) rather
  than dispatching fresh.**
- **Pull every failing shard's verdict, not one.** I read shard 3, fixed it,
  and left shards 2 and 4 unread for days; 7 of the 9 remaining failures were
  there.
- **Lean briefs — the protocol now lives in `.claude/PROTOCOL.md`, and every
  agent definition tells the agent to read it first.** Restating ~40 lines of
  environment rules per brief cost more context than the task, six times a wave.
  A brief is now exactly:
  ```
  TASK       what, why, the measured evidence, what "done" means
  TERRITORY  the exact paths this agent may EDIT (it may RUN anything)
  PORTS      gateway/documents/geometry + Vite, unique to this agent
  BRANCH     claude/<session-branch>
  ```
  If you find yourself writing a rule into a brief, it belongs in PROTOCOL.md.
- **Check territories AGAINST EACH OTHER before dispatch, not after.** List every
  live agent's EDIT paths and intersect them pairwise; a non-empty intersection
  means serialise or re-cut. On 2026-09-18 two briefs each looked disjoint on
  their own, and both agents edited the same four overlay files.
- **Run the loops with `args.branch` set** — they now refuse to start without it,
  and cap a wave at 3 builders however large `batchSize` is.

<a id="orch-dead-agent"></a>

### Detecting a dead agent under worktrees

*Moved verbatim from `.claude/ORCHESTRATOR.md` lines 130–138 on 2026-09-23. Current rule: ORCHESTRATOR.md §1.*

3. **Check for a dead agent.** The old tell was "last commit is old AND the
   tree is dirty" — that breaks under worktrees, because the main tree stays
   clean and the work sits in `.claude/worktrees/*` (now gitignored, so it does
   not even show as untracked). Check all three: `git worktree list`, then
   `git -C <each worktree> status --short`, then in-flight agents' output
   mtimes. Anything stale beyond ~30 min with no known long gate is a death.
   You are its relauncher: judge the work, run the gates yourself, and commit it
   with honest provenance stating whether Review and Verify ran.
   **Never revert or discard it** — including the worktree.

<a id="orch-discover"></a>

### Why the Discover phase exists

*Moved verbatim from `.claude/ORCHESTRATOR.md` lines 152–165 on 2026-09-23. Current rule: ORCHESTRATOR.md §2.*

- **Discover** — `vision-steward`, competitive gaps against Fusion 360 and
  Plasticity, owning `docs/VISION.md` + `docs/COMPETITIVE.md`. **THIS PHASE DID
  NOT EXIST AND THE LOOP WAS STRUCTURALLY INCAPABLE OF SHIPPING A NEW FEATURE
  WITHOUT IT.** Measured 2026-08-16 after the founder asked "is our idea agent
  finding new ideas — we are not progressing new features": across ~45 commits,
  22 docs / 9 fix / 8 test / **4 feat** / 2 ci, and all four feats were repairs
  of founder-reported defects. Every one of the seven Ready items was a defect.
  `VISION.md` and `COMPETITIVE.md` had been untouched for 16 days, and
  `vision-steward` had **never been spawned** — 38 subagent spawns, zero of it.
  The cause is structural, not lazy dispatch: the auditors find what is BROKEN
  and the groomer curates from the auditors, so **nothing in the loop was
  looking for what is ABSENT**. A defect-repair machine converges on a
  well-repaired version of what it already is. Run it on the same cadence as the
  audits, and feed its candidates to the groomer — it does NOT write the board.

<a id="orch-worktree-seed"></a>

### Worktree seeding, as first measured by the orchestrator (2026-08-14)

*Moved verbatim from `.claude/ORCHESTRATOR.md` lines 176–185 on 2026-09-23. Current rule: PROTOCOL.md §1.*

**A WORKTREE IS SEEDED FROM THE SESSION'S INITIAL REF, NOT THE BRANCH TIP —
put the reset in every brief.** Measured 2026-08-14 across both dispatch
mechanisms, hours apart, and after `main` had moved: every worktree sat at
`5aa981a`. The VP-1a agent's worktree was five commits behind and did not
contain VP-1, the commit it was extending — the spec file it was told to edit
did not exist. It noticed and reset; an agent that did not would have gated
against stale code and produced a commit whose parent reverts its
predecessors. Brief line: *"your first act is `git fetch origin <branch> &&
git reset --hard origin/<branch>`; state in your report which SHA you built
on."*

<a id="orch-review-verify"></a>

### Why Review and Verify are phases

*Moved verbatim from `.claude/ORCHESTRATOR.md` lines 186–191 on 2026-09-23. Current rule: ORCHESTRATOR.md §2.*

- **Review, then Verify** — `code-reviewer` then `qa-tester`, per item,
  pipelined so an item's review starts the moment its build lands. **These were
  missing from the loop until 2026-08-14**, when the engineering audit (K8)
  measured the consequence: three of the last five commits landed with no review
  and no QA. A build-only loop cannot produce reviewed work however good the
  builders are. The reviewer re-runs the builder's mutation evidence itself.

<a id="board-tick-conflict"></a>

### RETIRED 2026-09-23 — the orchestrator writing the board tick at integration (2026-08-14)

*Moved verbatim from `.claude/ORCHESTRATOR.md` lines 195–208 on 2026-09-23. Current rule: RETIRED; builders use Doc-tick: groomer (see Conflicts found during the move).*

**Builders commit CODE ONLY. The board tick is yours, folded in at
integration.** The same-commit rule for `docs/ROADMAP.md` + `docs/BACKLOG.md`
still holds — but three worktrees each editing those two files is a guaranteed
conflict, and resolving it by hand re-creates the sweeping this loop exists to
end. So say in every brief: *"commit code and tests only; do NOT touch
docs/BACKLOG.md or docs/ROADMAP.md."* Then at integration, per item:
`git cherry-pick <sha>`, write the tick, `git add` the two docs,
`git commit --amend --no-edit`. The rule is kept (every commit carries its tick)
and no two agents ever hold the same file. Verified working 2026-08-14 on
SKETCH-1 (`30a9f3f`) and VP-1 (`43c703c`).

**Push each cherry-pick separately.** GitHub fires one run per push *event*, so
a batched push leaves the earlier commits with no run at all — not a cancelled
one, none. Five separate pushes on 2026-08-14 produced five separate runs.

<a id="orch-no-cron"></a>

### Why there is no cron

*Moved verbatim from `.claude/ORCHESTRATOR.md` lines 219–240 on 2026-09-23. Current rule: ORCHESTRATOR.md §3.*

Removed by founder directive, 2026-08-14. We had made a 15-minute cron the
*pacer* against slices lasting three and a half hours — it woke roughly fourteen
times per slice and each wake did more hand-work. That was the "racing".

The loop chains on completion, which covers everything *inside* a session.

**It does not cover the case that has actually cost us most.** An earlier
version of this file said "it cannot go idle if every batch launches the next
one" — that is false here. In-session chaining dies with the session, and the
container has been reclaimed twice (16 h 45 m and ~30 h gaps). Removing cron
fixed the racing and left **zero** recovery paths where there had been one
flawed one.

What actually wakes this loop, and what each mechanism survives, is in
`docs/LOOP-MECHANISMS.md`. Short version: the `Stop` hook already continues the
session (it is the "Stop hook feedback" you keep seeing); only a GitHub Actions
schedule, a Routine, or a PR webhook survives the container dying, and none is
currently armed.

If a timer is ever reinstated it must be **stall recovery, never the pacer** —
its first action is a liveness check that returns immediately if any in-flight
agent's output mtime is under 30 minutes.

<a id="orch-hand-dispatch"></a>

### Hand-dispatch silently drops the loop's phases

*Moved verbatim from `.claude/ORCHESTRATOR.md` lines 246–272 on 2026-09-23. Current rule: ORCHESTRATOR.md §4.*

- **IF YOU DISPATCH BY HAND, YOU OWN THE LOOP'S PHASES BY HAND. Measured twice
  in one session, both times by me.** The loops in `.claude/workflows/` encode
  Review and QA as phases. Dispatching builders directly with the `Agent` tool
  is often the right call — it is cheaper, it survives a dead planner, and it
  lets you shape a brief around what the last wave just taught you — but it
  silently drops every phase the script would have run, and the drop is
  invisible because the builders all come back green.
  Wave 0: two builders dispatched by hand, integrated from their reports. No
  code review, no cross-item QA. A retrospective review then found a BLOCKING
  defect — the two fixes were each correct and wrong together, Enter on the new
  modal applied the sketch dimension instead of pressing the focused button —
  and it was visible in the very screenshot committed as proof the feature
  worked. Neither builder could have caught it: one predated the other's
  surface, and the unit test that asserts the opposite contract renders its
  component in ISOLATION.
  Wave 2: I had just ADDED the code-review phase to the loop, in a commit whose
  message explains why it matters — and then hand-dispatched three builders and
  skipped it again. Four commits, ~2900 lines, reviewed by nobody until
  afterwards.
  So the rule is not "use the workflow". It is: **when you hand-dispatch, run
  the phases yourself, in order, and say which you ran.** Build -> code-review
  -> cross-item QA -> integrate. The cross-item pass is the one that keeps
  getting skipped and it is the one that catches what per-item review cannot by
  construction: two affordances that are each correct and interfere.
  The tell that you are about to do it again: you have just finished writing a
  brief, the builders are live, and integrating feels like the next step. It is
  not. Reviewing is.

<a id="orch-control-run"></a>

### A control run under the same load is not a control

*Moved verbatim from `.claude/ORCHESTRATOR.md` lines 287–304 on 2026-09-23. Current rule: ORCHESTRATOR.md §4.*

- **A CONTROL RUN UNDER THE SAME LOAD IS NOT A CONTROL.** The standard move when
  a spec goes red is to revert your change and re-run: if it still fails it is
  pre-existing, not yours. That reasoning is only valid if the *other* variable
  is held still, and on this box it usually is not. Measured 2026-08-17/18: TWO
  agents in a row ran that control at load ~3-9 on 4 cores, got a failure in
  both arms, and correctly-by-their-evidence reported "pre-existing, not mine".
  Both were wrong — `qa-sketch-frame:991` passes 4/4 on a quiet machine. A
  contaminant that affects both arms cancels out of the comparison and leaves
  you certain of the wrong thing. It is the same shape as the bisect that
  reproduced a failure at a commit believed green (RETRO §4c): the shared cause
  sat underneath every point sampled.
  So the control has THREE arms, not two: your change under load, your change
  QUIET, and reverted quiet. `scripts/e2e.sh` now prints the 1-minute load
  average before the browser suite and warns when a red will be untrustworthy —
  read that line before you read the failures. And when briefing a builder, say
  this explicitly: *if you find a red spec, establish a pass rate on a QUIET
  machine before you run the revert control, because a control under load proves
  nothing.*

<a id="orch-anti-patterns"></a>

### Anti-patterns, with the evidence that earned them

*Moved verbatim from `.claude/ORCHESTRATOR.md` lines 310–342 on 2026-09-23. Current rule: ORCHESTRATOR.md §5.*

- **Doing the groomer's job.** `file CI-4`, `file REV-1..REV-5`, `file QA7-1`
  are all orchestrator commits. Eight of fourteen agents had never run.
- **Sharing one checkout across builders.** The entire collision protocol, and
  `scripts/stage-doc-hunks.py` — 905 lines that failed silently three times —
  are the cost. Worktrees make them unnecessary.
- **Trusting a gate nobody has seen fail.** Three shipped in one day: a CI grep
  matching its own prose, a unit test whose helper did the cleanup it asserted,
  and a `self_test` returning 0 with zero checks because `all([])` is `True`.
  **Standing review question: "can this gate fail? show it failing."**
- **Testing a probe against a fixture you built to match it.** The loop hook's
  own in-flight guard globbed `/tmp/claude-0/*/tasks` — one directory shallower
  than the harness's real path — and its test passed because the fixture was
  created at the depth the code expected. It could never fire, so the hook was
  free to dispatch on top of live agents: the exact racing it was written to
  prevent, shipped 59 minutes after `docs/RETRO.md`. Found by
  `engineering-auditor` (K7), fixed in `29387da`. **When a probe reads something
  the environment produces, the positive control must use the environment's own
  artefact, and the test must REFUSE rather than pass when none exists.**
  Corollary, earned the same hour: writing the *negative* controls found a
  second defect the audit had not — `find … | grep -q .` is wrong under
  `pipefail` (grep exits first, find takes SIGPIPE), so the guard read "nothing
  in flight" precisely when many outputs were fresh. **The negative control is
  where the second bug lives.** And size it: 3 fixture files let the broken form
  pass, 2000 failed it deterministically.
- **Repeating an inherited claim.** Three false claims reached the record, one
  written *while correcting somebody else's wrong number*. Every number you
  write must be one you measured.
- **Concluding from a command you did not check.** A `comm` reported "zero
  overlapping files" only because one input was silently empty. Re-run with
  stderr visible before believing a suspiciously clean answer.
- **Diagnosing from one data point per side.** The harness's
  parameter-stripping fault was misattributed to a Workflow-vs-Agent split on
  exactly that evidence. It was intermittent all along.

<a id="orch-traps"></a>

### Orchestrator environment traps, incl. the StructuredOutput fault

*Moved verbatim from `.claude/ORCHESTRATOR.md` lines 350–390 on 2026-09-23. Current rule: ORCHESTRATOR.md §6.*

- **Docker's registry is blocked (403).** `just dev`/compose cannot run; boot
  natively (uvicorn + SQLite via `metadata.create_all`, never alembic).
- **Cheap CI logs:** ask `get_job_logs` for `tail_lines=900`. It overflows the
  tool limit and spills to a file at **zero context cost** — parse that file and
  print only failure lines. `get_workflow_run` is *not* cheap; it returns the
  full repository object twice. `list_workflow_runs` ignores `per_page`.
- **`StructuredOutput retry cap exceeded`** usually is not a schema problem.
  Grep the agent transcript for `permission handler returned updatedInput`; if
  present it is an intermittent harness fault — relaunch fresh, do not resume
  (the cached failure replays) and do not touch the schema.
  **REFINEMENT, 2026-08-15: count the faults per agent before relaunching, and
  send ONE canary rather than the whole batch.** A three-agent workflow lost all
  three in five minutes — 10, 11 and 24 occurrences respectively; both auditors
  returned EMPTY having written nothing despite write-early, and the groomer hit
  the cap. When the fault is hitting EVERY agent, "relaunch fresh" re-buys the
  same failure at full batch cost. Instead dispatch one agent on a real ticket
  and let it double as the probe — tell it the fault exists, that it is not its
  mistake, to retry once or twice and then stop and report rather than working
  around it. Count the occurrences with
  `grep -c 'permission handler returned updatedInput' <transcript>.jsonl`; a
  clean canary means the batch is safe to send.
  **AND THAT REFINEMENT WAS ITSELF WRONG WITHIN ONE CYCLE — the canary was not a
  valid control.** I sent one `Agent`-tool dispatch, it saw ZERO faults across
  ~45 calls and finished a full ticket, and I concluded "the fault has passed"
  and relaunched the workflow. It died identically: 12, 21 and 10 occurrences,
  both auditors EMPTY again. The canary differed from the batch in THREE ways at
  once — dispatch mechanism (`Agent` vs `Workflow`), concurrency (one agent vs
  two auditors in parallel), and schema (none vs `StructuredOutput`) — so a clean
  result could not isolate anything. That is the third time in one day I reasoned
  from one data point per side, having written the rule down twice. **A control
  that varies more than one thing is not a control, it is an anecdote.**
  What IS measured: two `Workflow` runs failed heavily (10/11/24 and 12/21/10),
  one `Agent` run was clean, and the stripped calls span `Bash` (19), `Glob` (6),
  `Grep` (4), `Read` (9) and `Write` (3) — so it is not Bash-specific and not
  schema-specific either (the auditors carry no schema and still returned empty).
  Practical rule until someone isolates it properly: **when `Workflow` fails this
  way twice, fall back to `Agent` dispatches and run the loop's phases by hand.**
  That is a workaround chosen on evidence, not a diagnosis — do not write it up
  as one.
- **Playwright's `actionTimeout` is unset**, meaning *no* timeout. A `.catch()`
  cannot save you from a promise that never settles; pass explicit timeouts.

---

## Design mandate

<a id="flow-directive"></a>

### Flow is the first rule — the founder's reasoning

*Moved verbatim from `CLAUDE.md` lines 79–87 on 2026-09-23. Current rule: CLAUDE.md → Design mandate.*

**FLOW IS THE FIRST RULE (founder directive 2026-08-01: "Flow is critical for
users. Think about it as you build. How should we direct the user? Hopefully in
a way to leave fusion and go OS").** Judge every surface by what the user does
NEXT, not by whether the current screen is correct in isolation. The strategic
reasoning, because it changes priorities: people leave Fusion for licensing,
cost and cloud lock-in — that gets them to TRY us. They only STAY if modelling
does not cost them time. Nobody trades muscle memory for a philosophy. So flow
is the RETENTION mechanic, and feature parity without it produces a tool people
admire and do not use. Four concrete tests, each one a defect when it fails:

<a id="extrude-handle-claims"></a>

### The direct-manipulation sentence and its two corrections

*Moved verbatim from `CLAUDE.md` lines 92–141 on 2026-09-23. Current rule: CLAUDE.md → Design mandate.*

- **Direct manipulation beats forms.** Fusion's extrude is a draggable arrow;
  the numeric field is the precision fallback. This is the single biggest
  "does not feel like a modeling tool" gap we have, bigger than any missing
  feature.
  **CORRECTED 2026-09-13 — "ours is a form with no handle at all" was TRUE when
  written and has been FALSE since T-23, and three briefs quoted it as fact.**
  Extrude HAS a drag handle. It is drawn, it works, and it is unreachable:
  `document.elementFromPoint` down the gauge's own projected axis resolves to
  the handle at **2 of 16 sample points** — a 24x24 grip at the arrow's apex and
  nothing else — and a real `page.mouse.down/move/up` from the shaft midpoint
  left `extrude-distance` unchanged at 40. The shaft, cone and snap ladder are
  WebGL with no raycast target, so **the affordance and the hit target are
  anticorrelated**: the one place you can grab is a 12 px collar on the POINT of
  an arrow drawn at 0.92 opacity, ~90 px from where the arrow tells you to aim.
  That is the zero-area family's fourth costume — **drawn in GL, targeted in the
  DOM, and only one of the two is a control** — after the SVG stroke with no
  height, the `sr-only` element clipped out of frame, and the Tailwind utility
  that was never generated.
  The correction makes the gap WORSE, not smaller, and it changes what the fix
  is: the wave is not "build direct manipulation", it is "make the thing we
  already drew grabbable, and then give the other six verbs one at all"
  (fillet/chamfer/shell/revolve/pattern/hole return `handles: []` today).
  **CORRECTED AGAIN 2026-09-16 — the paragraph above is now itself STALE, and
  this is the SECOND time this one sentence has gone out of date while briefs
  quoted it.** Wave 3 (CRAFT-7 through CRAFT-11) did the work the correction
  asked for. Measured against the running app at `93733b2`: a real
  `page.mouse.down` / 12 moves / `up` from the extrude handle's centre drove
  `extrude-distance` **10 -> 65 mm** with the readout tracking, and **26 of 143**
  grid samples now resolve to `extrude-depth-handle` / `-sleeve` — against 2 of
  16 and a drag that moved nothing. The same holds for fillet (10 -> 20), shell,
  datum, and both pattern gauges; `handles: []` is no longer true of six verbs.
  So do NOT brief "the extrude handle is unreachable" or "no verb has a handle" —
  both were true, both are false, and a brief that quotes either sends an agent
  to rebuild something that works.
  What is still open is narrower and worth stating so the pendulum does not swing
  too far: the gauges have had NO touch pass (every reach number above, old and
  new, came from a mouse at 1280x800), and hole has no gauge yet (CRAFT-9c).
  **The durable lesson is now stronger than the one below it, because the file
  has demonstrated it twice on the same sentence: a correction is also a claim,
  and it decays exactly like the claim it replaced.** Dating a correction does
  not preserve it. The only thing that works is re-measuring before you quote it,
  including when what you are quoting is itself labelled a correction.
  **The general lesson, and the reason this correction is here rather than only
  in the roadmap: a mandate sentence is a CLAIM ABOUT THE PRODUCT, and product
  claims go stale silently.** This one survived a rewrite of the surface it
  describes, and every brief that quoted it inherited the error at no cost to
  itself. Before quoting a line of this file as evidence for what to build,
  check it against the running app the way you would check a test — and when it
  is wrong, correct it HERE, not just in the document you happened to be
  writing.

<a id="screenshot-gate"></a>

### Screenshots: surfaced means sent, and the capture is a gate

*Moved verbatim from `CLAUDE.md` lines 178–203 on 2026-09-23. Current rule: CLAUDE.md → Design mandate.*

4. **Show, don't tell.** UI changes ship with before/after screenshots
   (desktop + small-laptop widths) surfaced to the founder at milestones.
   **"Surfaced" means the orchestrator SENDS the screenshots to the founder
   (the file-send tool), not merely generates them into `docs/screenshots/`.**
   Every UI change → pass the before/after shots to the founder in chat;
   generating a PNG the founder never sees does not count (founder directive
   2026-07-23).
   **AND THE CAPTURE IS A GATE, NOT ONLY A COURTESY — it has now caught a
   defect every test passed.** Measured 2026-09-14 on CRAFT-7's follow-up: the
   snap-ladder floor change was correct in arithmetic, unit-tested, e2e-green,
   and it **ERASED THE LADDER** — 5 legible graduation crosses before, **0**
   after. Both rung classes were bounded by the PITCH, which was harmless while
   every ladder was 5 mm and fatal at 2 mm, because a 0.8 mm arm drawn across a
   0.97 mm rod is a mark inside the thing it graduates. Nothing in the suite
   could see it: the marks were present in the scene graph, correctly sized by
   their own rule, and invisible. The builder found it only because the mandate
   made it capture the before/after pair it would otherwise have had no reason
   to look at.
   The general point, and the reason this rule earns its place twice over: a
   screenshot is the only check we own that asks **"is the thing legible?"**
   rather than "is the thing present and correctly computed". Every other gate
   in this repo — DOM probes, pixel censuses, unit assertions — tests a property
   somebody thought to name. So when a change alters DRAWN GEOMETRY, capture the
   pair *before* believing the suite, and look at it; the shot you take for the
   founder is the same shot that tells you whether you shipped a ruler or a
   blank rod.

---

## Docs in sync

<a id="doc-tick"></a>

### Same-commit doc ticks vs the `Doc-tick: groomer` trailer (amended 2026-09-14)

*Moved verbatim from `CLAUDE.md` lines 294–326 on 2026-09-23. Current rule: CLAUDE.md → Docs in sync.*

- **Every commit that lands a feature/fix MUST, in the same commit, update
  `docs/ROADMAP.md` and `docs/BACKLOG.md`.** A commit that ships work but
  leaves the roadmap stale is incomplete.
  **AMENDED 2026-09-14 — this rule and the `Doc-tick: groomer` convention could
  not both be true, and the convention had quietly won: 28 of the last 30
  commits on the working branch touched NEITHER file, every one of them
  carrying the trailer.** A non-negotiable contradicted by 93 % of its own
  history is not a rule, it is noise — and noise in this file is worse than
  silence, because every brief quotes it.
  Both halves of the tension are real. The rule exists because stale docs are a
  defect. The convention exists because `docs/ROADMAP.md` and `docs/BACKLOG.md`
  are the two files EVERY agent is required to touch, which makes them the
  highest-contention paths in the repo — they are the reason
  `stage-doc-hunks.py` exists, the reason it has failed silently five times,
  and the reason a commit can sweep a colleague's entry. Under parallel
  builders the same-commit rule manufactures the exact collision the territory
  rule is trying to prevent.
  **So the rule now reads: every commit that lands a feature/fix MUST carry its
  doc tick EITHER in the same commit OR as a `Doc-tick: groomer` trailer, and
  the trailer is a DEBT the orchestrator owes before the batch closes.** It is
  a deferral, not an exemption. Concretely:
  · a builder in a worktree uses the trailer — it must not race for the board;
  · a lone committer touching no shared doc may still tick in place;
  · **the orchestrator dispatches the `backlog-groomer` before the batch ends**,
    and a batch is not done while any trailer is unreconciled;
  · `docs/ROADMAP.md`'s "Current focus" line must be true at every batch
    boundary, which is the property the original rule was really protecting.
  The failure mode to watch is the one that produced this amendment: the
  trailer is cheap to write and the groom pass is easy to skip, so the debt
  accrues invisibly and the board goes stale while every commit message claims
  otherwise. A review caught it here by counting, which is the check — if you
  want to know whether the convention is working, count the commits since the
  last `docs(board)` commit, do not read the trailers.

---

## CI

<a id="ci-local-gates"></a>

### Local gates are not the CI gate

*Moved verbatim from `CLAUDE.md` lines 336–355 on 2026-09-23. Current rule: CLAUDE.md → Definition of done.*

- **LOCAL GATES ARE NOT THE CI GATE — check GitHub Actions after every push
  (orchestrator duty).** Learned the hard way 2026-07-25: the founder had to
  tell us "none of the CI tests are passing" after CI had been red for
  **days** while every batch was being certified green locally. Two
  independent causes, both invisible to `just lint && just test && just e2e`:
  (a) `geometry-minio-smoke` had been failing since the job landed —
  `docker compose up -d --wait minio minio-init` names a ONE-SHOT in a
  `--wait` list, and `--wait` waits for running|healthy and treats a
  container that EXITS as a failure, so the step returned 1 the instant the
  bucket bootstrap *succeeded*; and the Docker registry is blocked in this
  container, so no local run could ever have exercised it. (b) A required
  DTO field (`ViewCreate.auto_place`) landed in one agent's commit while the
  web callers were fixed in a different agent's later commit, so the
  intermediate commit was typecheck-red in CI even though the tip was green.
  Rules: after pushing, **read the run for that SHA** (GitHub MCP:
  `actions_list` → `list_workflow_runs` filtered by branch, then
  `get_job_logs` with `failed_only: true`); treat `cancelled` as "superseded,
  look at the newer run," not as pass; and **every commit must be green on
  its own**, so a required-field change and its callers belong in ONE commit
  even when that crosses agent territories.

<a id="ci-access"></a>

### Only the orchestrator can read CI

*Moved verbatim from `CLAUDE.md` lines 356–365 on 2026-09-23. Current rule: ORCHESTRATOR.md §0c (Reading CI).*

- **Only the ORCHESTRATOR can read CI — subagents cannot. Budget the relay
  into the brief.** A subagent has no `gh`, no GitHub MCP in its toolset, and
  `api.github.com` is policy-denied for its session (`403 GitHub access is
  not enabled for this session`) — same policy-denial class as the blocked
  docker registry, so there is nothing to route around. A brief that ends
  "push and then read the run" therefore dead-ends *after* the agent has done
  the work. Either (a) tell the agent to push and stop, and the orchestrator
  reads the run and relays `get_job_logs` output back via SendMessage so the
  agent can iterate, or (b) keep CI-verified work in the orchestrator's own
  hands. Do NOT write briefs that assume a subagent can self-verify CI.

<a id="ci-reading-procedure"></a>

### Reading CI cheaply: the layered recipe and every correction to it

*Moved verbatim from `CLAUDE.md` lines 366–544 on 2026-09-23. Current rule: ORCHESTRATOR.md §0c (Reading CI).*

- **CI can ONLY be read through the GitHub MCP tools — never a bash poll, not
  even in the orchestrator's own session.** `api.github.com` is policy-denied
  from `Bash` here for the orchestrator too (the bullet above is about
  subagents, but the block is not subagent-specific), so the natural instinct
  — arm a `Monitor` that curls the runs endpoint until the conclusion lands —
  **cannot work**: the monitor fires once with the poll error and exits, which
  reads like "still running" if you aren't watching for it. Same for
  `Bash(run_in_background)`. Consequence: **waiting on CI is turn-based.** Push,
  then read the run with `actions_list` → `list_workflow_runs` (filter by
  branch) or `actions_get` → `get_workflow_run` on a known run id, and re-read
  it on a later turn; there is no way to be woken by a CI transition. Two
  practical notes: (a) `list_workflow_runs` returns ~430 KB and blows the tool
  limit — it gets spilled to a file, so parse that file with `python3 -c` and
  print only `head_sha`/`status`/`conclusion` rather than trying to read it.
  **`per_page` is IGNORED** — asking for 1 still returns 30 runs and the same
  ~430 KB, so do not bother trying to trim the payload that way; the spill +
  parse is the only cheap path;
  (b) `get_workflow_run` on ONE id is small-ISH but carries the entire commit
  message, which in this repo runs to thousands of tokens per call — three
  commits' verdicts cost more context than the whole rest of an integration
  pass.
  **THE CHEAPEST VERDICT READ IS `get_job_logs` WITH `failed_only: true` AND
  `return_content: false`** — measured 2026-08-27, it returns one line
  (`{"failed_jobs":0,"message":"No failed jobs found","total_jobs":7}`) and it
  answers the question you actually have. Green is `failed_jobs: 0`; red names
  the failing jobs, and you then re-call the same tool with `return_content:
  true` and a `tail_lines` on the ONE job you care about. Reserve
  `get_workflow_run` for when you need the commit message or the run's own
  `conclusion` string (e.g. telling `cancelled` from `failure`). The ids still
  come from the spilled `list_workflow_runs` parse, which is unavoidable.
  **CORRECTION 2026-08-28: `list_workflow_runs` NO LONGER RETURNS `conclusion`
  AT ALL, so the parse above cannot give you a verdict — only ids.** Measured:
  the run objects in the spill carry `status` (`completed`/`in_progress`) and
  fourteen other keys, and `conclusion` is not among them; a `KeyError` is what
  told me. So a completed run in that listing is a run that FINISHED, which is
  not a run that PASSED, and any reasoning that treats the spill as a board is
  reading a field that is not there. Use the spill for `head_sha` → `id` only,
  then take the verdict from `get_job_logs` as above.
  **RE-MEASURED 2026-09-11: `conclusion` IS BACK IN `list_workflow_runs`, so the
  2026-08-28 correction above is now itself stale — and believing it costs a
  whole extra call per run.** Read across 23 run objects spanning all three
  workflows: every one carried `conclusion` (`success`) beside `status`. So the
  documented dance — spill the listing, parse it for ids only, then `get_job_logs`
  per run to learn the verdict — buys nothing that one call does not already
  give you. **The cheapest COMPLETE verdict read is now
  `list_workflow_runs` with `status: "completed"` plus the branch filter: one
  call returns `head_sha` + `conclusion` for every finished run.** Keep
  `get_job_logs` for the case it is still best at — a RED run, where
  `failed_only: true` names the failing jobs. Do not delete the 08-28 correction:
  the field has now disappeared and come back once, so the durable lesson is to
  CHECK for it rather than to assume either way, and a `KeyError` is the tell in
  both directions.
  **And the cheap completion check has a cheaper form than the empty listing:
  filter by `status: "in_progress"`.** Empty means nothing is still running, at a
  cost of about ten tokens, and it does not grow as runs accumulate the way the
  completed listing does (each completed row carries the entire commit message,
  which in this repo is thousands of tokens — nine of them cost ~13 k).
  **CAVEAT 2026-09-13: that "ten tokens" holds ONLY when the answer is "nothing
  running".** An in_progress row carries the whole commit message exactly like a
  completed one, so the call costs the same per-row price whenever runs ARE live
  — measured ~5 k to learn "not done yet" with four runs in flight, and it is
  most expensive precisely when you are most tempted to poll it. It is a cheap
  ANSWER, not a cheap QUESTION. Ask it once per integration pass rather than on
  every wake, and remember there is no way to be woken by a CI transition, so
  the alternative to patience is spending context on impatience.
  **SUPERSEDED 2026-09-16 — THE `status` PARAMETER IS IGNORED, EXACTLY LIKE
  `per_page`, SO THE "FILTER BY `in_progress`" RECIPE ABOVE IS DEAD.** Measured
  with a control, because a claim about a tool needs one: two calls differing
  ONLY in `status` (`"in_progress"` then `"completed"`), same branch, same
  minute, returned **byte-identical 126 225-byte spills** (`cmp -s` clean), both
  carrying the same 30 rows, every one of them `completed`. A filter that
  returns rows it was asked to exclude is not filtering.
  Know which direction this fails in, because it is not the harmless one. The
  old recipe reads an EMPTY listing as "nothing is running". The filter being
  inert means the listing is **never** empty, so that question can no longer be
  asked at all — and the rows you get back are COMPLETED runs wearing the label
  you requested, so a reader following the old recipe would treat finished runs
  as in-flight, or worse, poll forever waiting for a list that cannot empty.
  **What to do instead, and it is no more expensive than the thing it replaces:
  ONE `list_workflow_runs` call with the branch filter, let it spill, and parse
  the spill for `head_sha` + `status` + `conclusion` together.** All three
  fields are present (re-confirmed today), so a single call gives the whole
  board, and the spill means the 126 KB never enters context — the cost is the
  error message plus your own `python3` print, which is a few hundred tokens for
  thirty runs. Completion is then `status == "completed"` read off the row you
  already have, rather than a second call that does not work.
  The durable half is the same lesson the `conclusion`-disappeared-and-came-back
  entry above teaches, now with a second instance: **the parameters this tool
  documents are not all honoured, and a silently-ignored filter is
  success-shaped.** `per_page` was the first, `status` is the second. Before
  believing any new filter argument, run it twice with two values that MUST
  disagree and compare the bytes; if they match, the argument did nothing.
  **A FAST GREEN IS TOLD FROM AN ALL-SKIPPED GREEN BY STEP DURATION, and
  `deploy-path` is routinely fast for real.** Its nine runs today finished in
  under three minutes each, which looks exactly like the every-job-skipped shape
  that also reports `success`. It was genuine: `list_workflow_jobs` showed
  "Compose stack end-to-end (build, boot, migrate, round-trip)" consuming
  **2 m 09 s** and the backup/restore drill **2 m 25 s**. A skipped job's steps
  are absent or instant, so read the MAIN step's duration, not the run's.
  **AND `e2e` LEGITIMATELY HAS NO RUN ON A DOCS-ONLY COMMIT** — it carries
  `paths-ignore: docs/**, **/*.md`, so four of nine commits today have no e2e row
  by design. That is NOT the unbuilt-commit hole described further down; it is a
  deliberate skip. Tell them apart by the diff: if every changed path matches the
  ignore list, the absence is correct. `deploy-path` has no such filter and runs
  on everything, so it is the one whose missing row is always a real anomaly.
  **CORRECTION 2026-09-11: THE `total_jobs` DISCRIMINATOR WORKS FOR `e2e` AND
  DOES NOT WORK FOR `ci` — THE TWO WORKFLOWS DIFFER IN A WAY THE RULE BELOW DOES
  NOT ACCOUNT FOR.** I read `{"failed_jobs":0,"total_jobs":7}` on a `ci` run and
  called the commit green, correctly by the rule as written. It was not green; it
  was **queued**, and `list_workflow_jobs` a few minutes later showed six jobs
  finished and `python` still inside Pytest. The mechanism: `ci`'s seven jobs are
  all independent, so GitHub creates all seven the instant the run is queued and
  `total_jobs` reads 7 from the very first second. `e2e`'s fifth job (`e2e
  complete`) *depends on* the four shards, so it does not exist until they
  finish — which is the only reason 4-vs-5 discriminates there. **A count that
  is complete at t=0 cannot tell you the run is complete.** So for `ci`,
  `failed_jobs: 0` means "nothing has failed yet" and nothing more, at every
  moment of the run.
  **The cheap completion check that DOES work, and it is nearly free: ask
  `list_workflow_runs` with `status: "completed"` and the branch filter.** An
  unfinished run yields `{"total_count":0,"workflow_runs":[]}` — a few tokens —
  and the moment it finishes the run appears, at which point `get_job_logs` with
  `failed_only` gives the verdict as usual. Two calls, both cheap, and neither
  can report a queued run as a pass. Do NOT reach for `list_workflow_jobs` to
  settle this: it returns every step of every job with timestamps and cost ~8 k
  tokens to learn one job was still running, which is most of an integration
  pass spent on a question the empty listing answers for free.
  **AND `failed_jobs: 0` ON AN UNFINISHED RUN IS NOT A PASS — READ `total_jobs`
  IN THE SAME REPLY.** It means "nothing has failed YET", which is true of every
  run that has barely started, and it reads exactly like green. Caught twice on
  2026-08-28, the second time only because the number looked odd. The free
  discriminator is already in the cheap call: `get_job_logs` reports
  `total_jobs`, and a COMPLETE run has a known job count — **6 for `e2e`
  (4 shards + `e2e complete` + `dist-bundle`), 7 for `ci`**. (It was 5 until
  `ed8c3d7` added `dist-bundle` on 2026-09-23 — a count that is part of a
  procedure goes stale when the workflow grows, so re-derive it from `e2e.yml`
  rather than trusting this number. Note `dist-bundle` has no `needs`, so it
  exists from t=0 and does not by itself make `total_jobs` a completion
  signal; `e2e complete` still appears only after the four shards finish.) So `total_jobs: 4` on an e2e run is
  an UNFINISHED run, not a four-job one, and the `failed_jobs: 0` beside it says
  nothing at all. Confirming it any other way is expensive: `list_workflow_jobs`
  on a single run returns every step of every job with timestamps and cost ~8 k
  tokens to learn that two shards were still running. Read the PAIR, not the
  zero.
  **AND WHEN A JOB IS RED, `tail_lines` MAY NEVER REACH THE FAILURE — budget for
  a fixed tail, not an escalating one.** Cost most of an integration pass on
  2026-08-28: I pulled 60, then 190, then 255 lines of a red `playwright (shard
  3/4)` job and got three service logs and `upload-artifact` chatter every time,
  because `scripts/e2e.sh` dumped 180 lines of `INFO: 127.0.0.1 … 200 OK` AFTER
  Playwright's summary and the runner appended ~120 more. Each pull cost
  thousands of tokens to learn nothing, and the artifact that holds the answer
  is unreachable — `curl` of the Azure blob URL `download_workflow_run_artifact`
  hands back is `CONNECT tunnel failed, response 403`, same policy-denial class
  as the docker registry. **The job log is the ONLY channel, so what a job
  writes LAST is a first-class interface, not cosmetics.** Fixed in `2874f0a`:
  every shard now ends with an `== e2e verdict ==` block naming each failed
  test, emitted by a final `if: always()` workflow step (the script cannot be
  last — the upload steps run after it exits). Measured after: ONE
  `tail_lines: 45` call returned the complete verdict where three escalating
  pulls had returned nothing. Two things generalise. (a) When you own the thing
  producing the log, put the verdict last and keep it short; a diagnostic dump
  that outweighs the diagnosis is worse than no dump. (b) An escalating tail is
  a losing strategy against an unknown amount of trailing noise — measure the
  trailer once, fix it, and then a fixed small tail always works.
  **AND THE VERDICT MUST NOT COUNT AN EXPECTED FAILURE AS A FAILURE.** On its
  first live run the new block reported `2 failed` on a shard that had one, the
  extra being a `test.fail()`-annotated case that documents a known gap and is
  SUPPOSED to fail: Playwright reconciles that into `tests[].status: "expected"`,
  while the raw `tests[].results[].status` reads `failed`, and a summariser that
  walks results rather than statuses inverts the annotation's whole meaning.
  Note the inverse is a REAL failure and needs saying by name — a `test.fail()`
  case that PASSES means the gap has closed and the annotation is now a lie.
  What saved this was the block's own cross-check against the report's `stats`,
  which printed "this summary disagrees with the report's own stats (expected:
  walked 165, stats say 166; unexpected: walked 2, stats say 1) — trust neither
  until checked" instead of confidently reporting a phantom. **A second,
  independently-derived count is what turns a wrong summary into a legible one**
  — the same lesson `stage-doc-hunks.py` paid for three times, and the reason a
  guard should refuse rather than guess when its two readings disagree.

<a id="ci-concurrency"></a>

### cancel-in-progress, then per-SHA concurrency groups

*Moved verbatim from `CLAUDE.md` lines 545–582 on 2026-09-23. Current rule: ORCHESTRATOR.md §0c (Reading CI).*

- **FIXED 2026-07-30 — `cancel-in-progress` is now PR-only, so a branch run
  that has STARTED is no longer killed by the next push. MEASURED, with one
  caveat below.** History, because the reasoning matters: the
  concurrency group is keyed on the ref, and with blanket cancellation pushing
  commit B ~3 min after A left A's run `cancelled` — which by the rule above is
  NOT a pass, so A shipped CI-unverified with nothing wrong with it. It hit
  three commits in a row (`6c9c432`, `8f387fc`, nearly `fe2e5cb`), including
  the commit that first *documented* the trap, and the exposure scales with the
  number of agents pushing in parallel — precisely when per-commit signal
  matters most. Blanket cancellation and "every commit green on its own" cannot
  both hold, so cancellation now applies only to `pull_request` (where just the
  head matters for merge). Two things follow: (a) don't "fix" a red-looking
  board by re-enabling it; (b) a `cancelled` run on a branch push is now a real
  anomaly worth investigating, not the routine noise it used to be.
  NB a descendant's green run does verify the *tree* of its ancestors, so a
  cancelled ancestor whose child is green is not an unknown build — it is an
  unverified *commit*. Say which of the two you mean.
  **SUPERSEDED 2026-07-30 by a per-SHA group — read this caveat as the reason
  why.** The PR-only `cancel-in-progress` alone did NOT save a run that had not
  STARTED yet. Evidence: with the fix live, `5de225c`'s run stayed
  `in_progress` across a later push (the old config would have killed it
  instantly) — but `60ac962` and `cb0dcd0`, also pushed with the fix in their own
  trees, still came back `cancelled`. The difference is that those two were
  superseded before getting a runner slot: a concurrency group admits one running
  plus one *pending* run, and a newer arrival evicts the pending one regardless of
  `cancel-in-progress`, which only governs runs already holding a slot. So under
  runner contention — which is exactly when several agents are pushing — rapid
  back-to-back pushes can still cost the middle commit its run. Practical rule:
  the fix removed the routine case but not the mechanism. Under four agents
  pushing it became the NORM, not an edge: **5 of 8 consecutive runs came back
  `cancelled`**, including `5794b48` — the fix for the very lint failure an audit
  had just flagged — so the rule was unenforceable exactly when parallelism made
  it most valuable. Real fix: the push group is now keyed on `github.sha`
  (`format('ci-sha-{0}', github.sha)`), giving every commit its own group that
  nothing can evict; PRs keep a ref-keyed group so a superseded PR push still
  cancels. It costs runner minutes, which is the price of the rule. Consequence:
  a `cancelled` run on a branch push is now genuinely anomalous — investigate it
  rather than shrugging.

<a id="ci-unbuilt-commits"></a>

### A commit in the middle of a multi-commit push gets no run

*Moved verbatim from `CLAUDE.md` lines 583–599 on 2026-09-23. Current rule: ORCHESTRATOR.md §0c (Reading CI).*

- **A COMMIT PUSHED IN THE MIDDLE OF A MULTI-COMMIT PUSH GETS NO RUN AT ALL —
  not a cancelled one, NOTHING — so "every commit green on its own" has a hole
  the per-SHA concurrency fix does not touch.** GitHub fires ONE workflow run per
  push *event*, keyed to the push's head commit; every commit between the old tip
  and the new one is simply never built. This is invisible in a way eviction is
  not: a `cancelled` run is at least a row you can see and question, whereas an
  unbuilt commit leaves no row, so the board looks complete. Measured 2026-08-01:
  `3065813` and `3cf6650` were committed 69 s apart and pushed together, and
  `3065813` has ZERO runs across all three workflows while `3cf6650` has three —
  and `3065813` touched `apps/web/e2e/**`, so it was not a paths-ignore skip.
  Two consequences. (a) **Push each commit separately** when you want per-commit
  evidence — the per-SHA group means back-to-back pushes no longer cost each
  other their runs, so the reason to batch is gone. (b) When auditing, do not
  reason from the runs list alone: it enumerates PUSHES, not commits. Cross-check
  against `git log` and treat a commit with no row as UNVERIFIED, exactly like a
  cancelled one. (Its descendant's green run still verifies the *tree*, never the
  intermediate *commit* — the same distinction the bullet above insists on.)

<a id="ci-cancelled-two-causes"></a>

### `cancelled` has two causes

*Moved verbatim from `CLAUDE.md` lines 600–612 on 2026-09-23. Current rule: ORCHESTRATOR.md §0c (Reading CI).*

- **`cancelled` HAS TWO CAUSES AND GITHUB USES THE SAME WORD FOR BOTH** — a
  concurrency eviction, and a job hitting `timeout-minutes`. Discriminate by
  DURATION and by the sibling jobs. Seen 2026-07-30: three runs read `cancelled`
  *after* the per-SHA fix and I nearly concluded the fix had failed; in fact the
  `python` job's Pytest step ran **14m31s** and the job was killed at **15m16s**
  against a 15-minute ceiling, while the other four jobs all passed. An eviction
  kills a run EARLY and takes ALL its jobs with it; a timeout kills ONE job at
  almost exactly the configured limit and leaves its siblings green. So read
  `list_workflow_jobs` for the run and look at per-job conclusions and step
  durations before naming a cause — the run-level `conclusion` alone cannot tell
  you which happened. (The python job is now 30 minutes. The suite is ~2958 tests
  dominated by OCCT geometry and grows with every verb and golden, so expect to
  revisit it; sharding is the next lever if 30 gets tight.)

<a id="ci-minio-withdrawn"></a>

### geometry-minio-smoke: the MinIO images were withdrawn

*Moved verbatim from `CLAUDE.md` lines 613–675 on 2026-09-23. Current rule: ORCHESTRATOR.md §0c (Reading CI).*

- **`geometry-minio-smoke` STARTED FAILING ON THE RUNNER 2026-09-12 FOR A REASON
  THAT IS NOT IN THIS REPO — do not go looking for it in a diff.** The job dies
  in its first pull: `minio Error pull access denied for minio/minio, repository
  does not exist or may require 'docker login'`. That is the RUNNER being refused
  by Docker Hub, not the `--wait`-on-a-one-shot defect this file documents above,
  and the two read nothing alike — that one failed AFTER the bucket bootstrap
  succeeded, this one never pulls an image at all.
  The evidence that it is not ours, gathered because "not in my diff" is not the
  same claim as "not ours": the `minio/minio` pin last changed on **2026-07-31**
  (`2fba93e`) and has passed ever since; the eleven commits merged from the dev
  branch touched no compose file and no workflow; the job was **green on this
  same branch at `2e77533`** earlier the same day; and it then failed on
  `702c07e`, a MERGE commit carrying no application change, which is the cleanest
  possible negative control — a failure on a commit that changed nothing relevant
  cannot have been caused by a commit.
  Two plausible causes and I am not asserting either: Docker Hub's anonymous
  pull limit (GitHub-hosted runners share IP pools and hit it in bursts), or a
  change in how that image is distributed. **Do not "fix" it by deleting or
  disabling the job** — it is the only cross-process mesh-store check we have,
  and the same registry-denial class already makes image builds untestable
  locally. The real fixes are authenticating the pull or mirroring the image,
  both platform-builder decisions that need a secret, so flag it rather than
  routing around it. Until then expect every commit on every branch to carry
  this one red job, and say so explicitly when reporting a run rather than
  letting "CI is red" imply the diff did it.
  **RESOLVED 2026-09-13 in `bd58416`, and BOTH causes guessed above were wrong —
  the repositories were WITHDRAWN.** By then it had spread from one job to three
  (`ci/geometry-minio-smoke`, `deploy-path/compose-stack-e2e`,
  `deploy-path/backup-restore-drill`), all dying in the same pull, on every
  commit including docs-only ones. MinIO Inc. stopped publishing community
  images altogether: `GET hub.docker.com/v2/repositories/minio/{minio,mc}/`
  both return `{"message":"object not found"}`, and the `minio/minio` GitHub
  README now reads "THIS REPOSITORY IS NO LONGER MAINTAINED" / "distributed as
  source code only". Fixed by repointing both pins to MinIO's own other
  registry, `quay.io`, at the tags their own official Helm chart still ships.
  **The general lesson is the diagnostic, not the incident. "The registry is
  blocked here" made this look unmeasurable, and it was not.** The blob CDN is
  policy-denied, but `registry-1.docker.io` answers (`/v2/` returns 401, which
  is its auth challenge, not a denial), so an anonymous pull token from
  `auth.docker.io/token?service=registry.docker.io&scope=repository:<repo>:pull`
  plus a manifest GET measures any Docker Hub image from this container without
  a daemon. That turned a shrug into an answer in two minutes:

  | image | manifest API |
  |---|---|
  | `minio/minio` (pinned tag AND `latest`) | **401** |
  | `library/postgres:16`, `library/redis:7` | 200 |

  Read the STATUS, because the three causes are different words: **429**
  (`toomanyrequests`) is the anonymous rate limit, **401** on one repo while
  others return 200 is that repo being gone or gated, and a rate limit would
  have hit postgres and redis too. Always probe a CONTROL image in the same
  breath — a bare "minio 401" is consistent with the network being broken, and
  `library/postgres: 200` beside it is what makes it evidence. The same reading
  also refutes the runner-IP-pool theory for free: an identical result from a
  completely different network cannot be about the runner's IP.
  Green afterwards, and verified as REAL rather than skipped-green by step
  duration: compose-stack-e2e's main step ran 1m58s and the backup/restore
  drill 2m21s, matching their historical timings.
  Do NOT delete this entry now that it is fixed: the durable half is that an
  upstream can WITHDRAW an image, which no amount of pinning survives, and the
  next occurrence will wear the same "pull access denied" costume as a login
  problem.
  **IT RECURRED 2026-09-24, ELEVEN DAYS LATER, ON QUAY.IO — and the fix is now
  to stop pulling MinIO at all.** `deploy-path` (both jobs) died on `cd6baed`
  and `fc5e840` with `minio Error unauthorized: access to the requested
  resource is not authorized`, ten minutes after the SAME pins pulled green on
  `639f21c`; neither commit touched compose. That sentence is quay's anonymous
  answer for a repository that is gone or private (Docker Hub's is "pull access
  denied"), so the costume changed with the registry. quay.io itself is
  `CONNECT 403` from this container (000), so it could not be probed directly;
  the evidence gathered instead: Docker Hub `minio/{minio,mc}` still **401** /
  `object not found`, beside controls `library/redis:7` **200** and
  `library/postgres:16` **429** (the anonymous rate limit, a different word);
  `ghcr.io/minio/minio` has no public repo (token 403) while
  `ghcr.io/versity/versitygw` answers 200; and upstream's own history shows
  why: `minio/minio` `05e5699` (2025-10-19) moved community publishing off
  quay to `registry.min.dev/community/minio`, a registry MinIO controls and
  that is also 403 here. **A third vendor registry would be the same bet a
  third time.** Fixed by building the SAME two releases from source:
  `go install github.com/minio/{minio,mc}@<pseudo-version>` resolves through
  `proxy.golang.org` (reachable here, and it keeps every version it has ever
  served), the pseudo-versions are the exact commits the RELEASE tags point at
  (proxy `.info` `Origin.Hash`), and the `h1:` sums are pinned in the
  Dockerfile and recorded in `sum.golang.org`. Proven locally without docker:
  the Dockerfile's own RUN bodies, replayed, built both binaries in 274 s cold
  on 4 cores, `minio --version` names the release, `mc ready local` + `mc mb`
  work, and `services/geometry/tests/test_s3_store.py` with
  `LOFT_MINIO_SMOKE=1` ran **18 passed** against it (**1 failed** with a wrong
  secret, the negative control; a corrupted pinned sum makes the build
  REFUSE). The lesson that generalises: **when an upstream has withdrawn a
  distribution channel once, treat every channel it controls as withdrawable
  and build from a content-addressed source you do not have to trust it for.**

<a id="ci-workflow-refused"></a>

### `failure` with zero jobs: GitHub refused the workflow file

*Moved verbatim from `CLAUDE.md` lines 676–734 on 2026-09-23. Current rule: ORCHESTRATOR.md §0c (Reading CI).*

- **`conclusion: failure` WITH `total_jobs: 0` IS NOT A TEST FAILURE — IT IS
  GITHUB REFUSING THE WORKFLOW FILE, AND NOTHING WE RUN LOCALLY CAN SEE IT.**
  Measured 2026-09-15. `deploy-path` reported `failure` on a commit whose diff
  was a container fix, and the natural read is that the fix did not work. It had
  never been tested: **no job was ever created.** Three tells, all in the cheap
  calls you already make:
  · `created_at == run_started_at == updated_at` — a run that concluded in
    **zero seconds** did not run;
  · `get_job_logs` with `failed_only` returns `{"failed_jobs":0,"total_jobs":0}`
    — and note `failed_jobs: 0` here means "no jobs exist", the opposite of the
    green it looks like;
  · the run's `name` is the **file path** (`.github/workflows/deploy-path.yml`)
    rather than the workflow's `name:`, because GitHub never got far enough to
    read it.
  The cause was `${{ runner.temp }}` in a **job-level** `env:`. The `runner`
  context is only available at STEP level; job-level `env` allows `github`,
  `needs`, `strategy`, `matrix`, `vars`, `secrets` and `inputs`. An invalid
  context reference is a schema rejection, not a runtime error.
  **The local gates cannot catch this and it is worth knowing which ones give
  false comfort:** the file parses as YAML, has no duplicate keys, has a correct
  `jobs`/`steps`/`env` structure, and `docker compose config -q` is irrelevant
  to it. `python -c "yaml.safe_load(...)"` passing means the file is *YAML*, not
  that it is a *workflow*. So treat any workflow edit as unverifiable until the
  run, and read the zero-second/zero-job shape before hunting in the diff.
  **And the irony is the durable half: this was a VERDICT BLOCK — a diagnostic
  added to make failures legible — and it made the workflow unrunnable, which
  is the least legible failure available.** That is the second guard in one day
  to manufacture the outcome it was added to prevent (the other: a build-time
  `nginx -t` creating the root-owned pid file that then blocked the non-root
  runtime). When you add a guard, ask what it does when IT is wrong, not only
  what it catches when the subject is.
  **AMENDED the same day — "the local gates cannot catch this" and "treat any
  workflow edit as unverifiable until the run" were both TRUE when written and
  are now PARTLY FALSE, which is exactly the kind of stale claim this file warns
  about.** `scripts/check-workflow-contexts.py` (in `just lint` and CI) grades
  every `${{ }}` expression in an `env:` mapping against the contexts allowed at
  that level, and it catches THIS defect: run against the real broken bytes
  (`git show 981a8d0:.github/workflows/*.yml`) it names both offending keys and
  exits 1. The allowed sets are transcribed from GitHub's own workflow-parser
  schema — `actions/languageservices`, `workflow-parser/src/workflow-v1.0.json`,
  reachable via `raw.githubusercontent.com` — whose `job-env` / `step-env` /
  `workflow-env` definitions each carry a `context` array; `--show-table` prints
  what the gate believes so it can be diffed against that file rather than
  trusted. Read it rather than guessing: the three sets really do nest,
  `workflow-env` {github, inputs, vars, secrets} < `job-env` {+needs, strategy,
  matrix} < `step-env` {+steps, job, **runner**, env, hashFiles}.
  **What is still unverifiable, stated honestly so the amendment does not
  overclaim:** the gate covers `env:` mappings only. Expressions in `if:`,
  `with:` and `run:` are counted and REPORTED as not graded, and nothing here
  validates the rest of the Actions schema. So the original advice still holds
  for everything except this one class — which, being the one that silently
  takes down a whole file, was the one worth buying.
  Two practical rules that outlive the specific gate. **Prefer `$RUNNER_TEMP` to
  `${{ runner.temp }}` inside any `run:` block** — in the shell it is an ordinary
  environment variable, needs no expression, and cannot fail this way at all.
  And **when an idiom fails, grep the repo for a WORKING instance before
  inventing a fix**: `e2e.yml` uses `runner.temp` eight times and is green, every
  one at step level, so the difference between the working and broken code was
  one nesting level and was sitting in the tree the whole time.

<a id="ci-fast-green"></a>

### A suspiciously fast green

*Moved verbatim from `CLAUDE.md` lines 735–741 on 2026-09-23. Current rule: ORCHESTRATOR.md §0c (Reading CI).*

- **A suspiciously FAST green deserves the same scrutiny as a red.** The
  usual cause is a job that skipped its work, and `conclusion: success` is
  emitted when every job is skipped. Discriminate by reading the log for
  evidence the work actually happened (2026-07-25: the first-ever deploy-path
  run passed in 86s where ~20 min was expected — real, and the proof was the
  teardown naming six actual containers; a no-op job has nothing to remove).
  Prefer asserting on a side effect only real execution produces.

---

## Git, staging and worktrees

<a id="staging-protocol"></a>

### Staging shared docs: stage-doc-hunks.py and the isolated index

*Moved verbatim from `CLAUDE.md` lines 815–958 on 2026-09-23. Current rule: CLAUDE.md → Orchestration rules.*

- **Commit protocol:** stage your own files explicitly — never `git add -A`.
  **And for the HIGH-TRAFFIC SHARED DOCS (`docs/ROADMAP.md`, `docs/BACKLOG.md`),
  `git add <file>` is not "explicit" enough — stage HUNKS.** Every agent is
  required to tick both in the same commit, so they are nearly always dirty with
  somebody else's in-flight text; `git add docs/BACKLOG.md` then silently
  captures it. Seen 2026-07-30: an orchestrator commit about an unrelated test
  gate (`33b1b5a`) carried three P3 items another agent had just filed, so the
  commit message described none of its own contents and the authorship in history
  is wrong. Nothing was lost, which is exactly why it is easy to miss. Use a
  filtered `git apply --cached` (or `git add -p`) for these two files, and if you
  find you have already swept foreign text, annotate the record rather than
  rewriting shared history that other agents have already rebased onto.
  **IN A WORKTREE, DO NOT USE `stage-doc-hunks.py` AT ALL — stage the file whole
  after reading `git diff` in full.** Established 2026-08-29, and it is a
  simplification that has been available ever since worktree isolation became
  mandatory for builders. A worktree has its OWN index and working tree, so the
  only uncommitted text in it is YOURS; there is no colleague's entry to sweep,
  which is the single hazard the tool exists to prevent. Against that zero
  benefit, the measured cost is five silent failures — it has swept a
  neighbour's entry, relocated the author's own entry to the end of the file,
  truncated a 31-line entry to 7, truncated one to its heading, and staged 1 of
  3 entries — every one of them reporting `left 0 hunk(s) unstaged` while doing
  it, and every one caught only by a `git show :<file>` byte comparison. A tool
  whose failures are success-shaped, run where it can protect nothing, is pure
  downside. **The check that actually works is the cheap one and it still
  applies: read `git diff --cached` IN FULL immediately before committing.**
  The tool remains correct for the SHARED checkout (the orchestrator's own tree,
  or any agent not in a worktree) — that is the case it was written for and the
  only one where a foreign hunk can be present.
  **In the shared checkout, use `python3 scripts/stage-doc-hunks.py <file>
  "<marker>"`**, where the marker is a phrase from your entry's first line that
  fits entirely on ONE line — it matches line by line, so a marker spanning a
  line break matches nothing and then silently drops your whole entry (48 lines,
  measured 2026-08-28). It stages only
  hunks that ADD a line containing your marker and leaves the rest unstaged for
  their author. It exists because this rule was broken TWICE in one day, the
  second time by the person who wrote it: the correct path was fiddly and
  `git add <file>` is four words, and under load the cheap path wins. A rule that
  loses to convenience is not a control; make the correct path the easy one.
  **It filters at LINE granularity, and it has to.** The first version matched
  whole hunks, which silently swept a colleague's entry whenever theirs sat
  beside yours — git merges changes within its context window into ONE hunk, and
  a blank line between two appended entries is NOT enough to separate them
  (measured). It reported "left 1 hunk(s) unstaged for their author" while doing
  it, which is worse than failing. Note `git add -p` is NOT a fallback here:
  interactive git is unavailable in this container.
  **And that line-granularity filtering then MIS-PLACED the author's own entry —
  the failure nobody was watching for, because everyone was watching the
  colleague's text.** Fixed 2026-08-01, found by the dogfooding pass, reproduced
  deterministically. The tool emits `--unidiff-zero` sub-hunks and DROPS the
  colleague's added lines from the patch, but it was numbering the new side by
  walking the full working-tree diff — which counts those dropped lines. So every
  sub-hunk after a colleague's entry carried a `+b` too large by exactly the
  number of lines dropped, and `git apply` inserted the text somewhere else: in
  the measured case `@@ -5,0 +9,3` where `+6` was right, landing the author's
  entry at the END of the file, after an unrelated item, blank-line separator
  gone — while printing "staged 1 hunk(s) … left 0 hunk(s) unstaged". The
  colleague's text was untouched, which is why the existing guard (does it sweep
  a neighbour?) sailed past it. `+b` is now DERIVED as
  `run_old_anchor + 1 + emitted`, a function of what the patch actually contains,
  so it cannot drift from it. Two general lessons: **a tool that guards commits
  needs its own guard** — `python3 scripts/stage-doc-hunks.py --self-test` builds
  a throwaway repo with a colleague's entry directly above yours and compares
  `git show :FILE` BYTE-FOR-BYTE, because asserting the exit code would have
  passed all along; and **check the staged tree, not the staging report** —
  `git show :<file>` after staging a shared doc, not just `git diff --cached`.
  **AND THE SELF-TEST I ADDED THAT MORNING PASSED WHILE THE TOOL SWEPT A
  COLLEAGUE'S ROADMAP ENTRY THAT AFTERNOON — a fixture in the wrong FORMAT is a
  gate that cannot fail for the reason you care about.** `ENTRY_START` knew list
  items and headings, so it found boundaries in `docs/BACKLOG.md` (`- [ ] …`) and
  none at all in `docs/ROADMAP.md`, whose entries are bold-lead PARAGRAPHS
  (`**QA3-1 CLOSED (…) — …**`). Two adjacent ROADMAP entries therefore read as ONE
  run of added lines, the marker made the whole run "mine", and it staged 31 lines
  where 16 were mine — printing "left 0 hunk(s) unstaged for their author" as it
  did. My self-test used the BACKLOG shape only, so it sailed through. Caught by
  the kernel agent reading `git diff --cached` in full; nothing was lost. Three
  changes, and the second is the one that generalises: (a) `ENTRY_START` learned
  bold-lead paragraphs; (b) a SECOND, independently-derived entry count (added
  lines separated by an added blank line) now cross-checks it, and the tool
  REFUSES when the two disagree rather than guessing — so the next format nobody
  taught it fails loudly instead of eating a neighbour; (c) `--self-test` carries
  BOTH doc shapes, and the negative control is that reverting the regex makes the
  ROADMAP case refuse. Note a post-condition that compares the staged tree
  against what attribution CLAIMED does NOT catch this: a wrong claim verifies
  happily against itself. That is the `gen-check`-measuring-the-wrong-input trap
  wearing different clothes, and the fix is the same — get a second opinion from
  a different derivation, not a louder assertion of the first.
  **AND THE CROSS-CHECK THAT WAS ADDED TO CATCH ALL THIS WAS ONE-DIRECTIONAL, SO
  IT SAT OUT THE NEXT FAILURE.** Fixed 2026-08-11, found by the SEL-6 QA agent.
  The bold-lead alternative from the fix above matched `**` ANYWHERE, so a
  CONTINUATION line opening with a bold run — `**94.8 %**, every answer naming
  the near face`, i.e. how anyone writes a measured result — read as a new entry.
  The marker matched only the text above it, everything below was attributed to a
  colleague who does not exist, and `mine_only_subhunks` dropped it: **7 lines
  staged of a 31-line ROADMAP entry**, reported as `left 0 hunk(s) unstaged for
  their author`. Caught only by reading `git diff --cached` in full. This is the
  MIRROR of the previous defect — that one MISSED a boundary and swept a
  neighbour, this one INVENTED a boundary and truncated the author's own entry —
  and the guard added for the first was written as `blanks > seen`, which is
  blind to `seen > blanks`. It was `seen=2, blanks=1`; `1 > 2` is false; nothing
  fired. Two changes: a bold lead now opens an entry only where an entry CAN
  begin (top of the run, or after a blank line — both docs separate entries that
  way), and the cross-check refuses on ANY disagreement, either direction. The
  general lesson is narrower and sharper than "add a cross-check": **a guard
  written against one failure tends to encode that failure's DIRECTION.** Ask
  what the symmetric mistake looks like and make sure the guard fires on it too.
  Note also that the exit code was 0 throughout — `--self-test` now carries a
  third fixture (`bold-continuation`) and its negative control reproduces the
  defect exactly: exit 0, colleague untouched, tree wrong. Only the byte-for-byte
  `git show :FILE` comparison catches it.
  **When you are ready to commit and ANOTHER agent already has files staged, do
  not touch their index — build your commit against an isolated one.** The
  staging protocol above assumes the index is yours to arrange, and under four
  parallel agents it frequently is not: a `git reset` to clear someone else's
  staged work, or a commit that sweeps it in, are both the same defect (a commit
  whose message describes none of its own contents). `GIT_INDEX_FILE` gives you a
  private index for the duration:
  ```bash
  export GIT_INDEX_FILE=$(mktemp -u /tmp/idx.XXXX)
  git read-tree HEAD                     # start from HEAD, not from their index
  git add <your files only>              # stage-doc-hunks.py still applies to ROADMAP/BACKLOG
  git commit -m "…"                      # commits YOUR tree; their index is untouched
  unset GIT_INDEX_FILE
  ```
  Used first on 2026-07-31 by the perf agent, which found ~40 of a sibling's
  files staged when its own work was ready; nothing of theirs was swept and their
  commit landed as its parent. Verify afterwards with `git show --stat HEAD` that
  the commit contains only your paths — the isolated index protects their work,
  not you from your own `git add`.
  **AND `git read-tree HEAD` SNAPSHOTS HEAD AT THAT MOMENT — if a sibling commits
  before you do, your commit REVERTS THEIRS.** This is the recipe's own trap and
  it bit within hours of the recipe landing: the ops agent read-tree'd, worked,
  and committed; a sibling had committed in between, so its tree carried the
  PRE-sibling content and its commit silently deleted `CLAUDE.md`'s and
  `docs/ARCHITECTURE.md`'s changes plus three screenshots. It was caught only
  because the agent ran `git show --stat HEAD` before pushing and saw deletions
  it never made. Nothing reached the remote, which is the good outcome and also
  why this is easy to miss — a `git commit` that reverts a colleague reports
  nothing unusual. Two rules: pin the base explicitly rather than by name
  (`base=$(git rev-parse HEAD); git read-tree "$base"`), and immediately before
  committing re-check that `git rev-parse HEAD` still equals `$base` — if it
  moved, re-read-tree from the new HEAD and re-add your paths. Then `git show
  --stat HEAD` and read it for paths you did NOT touch; that check is not
  optional, it is the only thing that catches this.

<a id="update-ref"></a>

### `git update-ref` on a checked-out branch

*Moved verbatim from `CLAUDE.md` lines 959–982 on 2026-09-23. Current rule: CLAUDE.md → Orchestration rules.*

- **`git update-ref` ON THE BRANCH YOU HAVE CHECKED OUT MAKES OTHER AGENTS'
  LANDED COMMITS LOOK LIKE YOUR STAGED CHANGES — same family as the stale
  `read-tree`, different door.** Done by the ORCHESTRATOR 2026-09-16. Having
  pushed a commit from a throwaway worktree (the correct move when the shared
  tree is dirty with a colleague's in-flight file and you therefore cannot
  rebase), I tried to realign the local branch. `git branch -f` REFUSES for a
  branch in use — that refusal is the guard — and `git update-ref` does the same
  thing with no such check: it moves the ref and touches neither the index nor
  the working tree. `git status` then reported **eight files as staged** that I
  had never touched; they were four colleagues' landed commits, and a `git
  commit` at that moment would have REVERTED all four under a message about a
  docs edit.
  The tell is that the "staged" paths are ones your task never mentions. The fix
  is `git checkout HEAD -- <exactly those paths>`, which brings index and worktree
  up for them and leaves a genuinely-dirty foreign file alone — never `git reset
  --hard` (it destroys the colleague's uncommitted work) and never a bare `git
  reset` (it unstages theirs).
  Two rules. **Do not realign a local branch ref while its worktree is dirty with
  someone else's work — just leave it behind and `git pull` when the tree is
  yours again**; a local ref pointing at an older commit is harmless, a
  desynchronised index is not. And **when git refuses an operation, read the
  refusal before reaching for the command that does not check** — `git branch -f`
  declined for exactly this reason and I routed around the safety rather than the
  problem.

<a id="marker-ids"></a>

### A bare item id is not a safe marker

*Moved verbatim from `CLAUDE.md` lines 983–990 on 2026-09-23. Current rule: CLAUDE.md → Orchestration rules.*

- **`stage-doc-hunks.py`: a bare item id is NOT a safe marker, because siblings
  cross-reference ids.** Seen 2026-07-31: `stage-doc-hunks.py docs/BACKLOG.md
  "OPS-1"` swept another agent's OBS-1 entry, because THEIR text contained the
  phrase "the same shape as OPS-1". The tool did exactly what it was told; the
  marker was the defect. Use a phrase from your own entry's FIRST line — e.g.
  `"OPS-1 — there was no backup"` rather than `"OPS-1"` — so the match cannot
  land inside somebody else's prose. The tool now prints the entry-start line of
  everything it stages; read that output rather than trusting the count.

<a id="sweep-source-files"></a>

### The sweep happens in source files too; resyncing the default index

*Moved verbatim from `CLAUDE.md` lines 991–1037 on 2026-09-23. Current rule: CLAUDE.md → Orchestration rules.*

- **THE SWEEP IS NOT A DOCS PROBLEM — it happens in SOURCE files too, and there
  the hunk tooling does not apply.** The staging rule names `docs/ROADMAP.md` and
  `docs/BACKLOG.md` because those are the two files every agent is REQUIRED to
  touch. That framing is too narrow: any file two agents happen to edit at once
  has the same hazard, and `git add <one source file>` is just as wholesale as
  `git add <one doc>`. Seen 2026-08-01: the folders agent staged
  `packages/py-kit/src/py_kit/schemas/features.py` while the prefetch agent had
  four uncommitted DTOs in it, so `17404ab` (a folders commit) shipped
  `WarmTreeRequest`/`WarmTreeResult`/`WarmCancelRequest`/`PrefetchRequest`, and
  the prefetch commit that followed contains no py-kit hunk at all. Nothing was
  lost and BOTH commits are green on their own — the models were unreachable from
  any route in the folders tree, so its OpenAPI was unchanged, which is precisely
  why no gate objected. The universal check is cheap and needs no tool:
  **`git diff --cached` and READ IT before every commit.** Not `--name-only` —
  the names looked right here; the hunks were the problem. If a hunk is not
  yours, unstage that path (`git reset -q HEAD -- <path>`), re-add only your own
  changes, and tell the other agent. Annotate rather than rewrite once siblings
  have rebased onto it.
  **AND THEN RESYNC THE DEFAULT INDEX, or your own commit reads as uncommitted.**
  `.git/index` never learns about a commit made through another index, so it keeps
  the PRE-commit blob for every path you just committed and `git status` reports
  them as dirty (`MM <file>`) forever. Caught within minutes of writing this
  recipe: a stop-hook git check flagged an orchestrator commit as unpushed work
  when it was already on the remote. The tell is `git diff HEAD -- <path>` coming
  back EMPTY while `git status` calls the path modified — worktree matches HEAD,
  so the index is the stale party. Fix per path you committed:
  ```bash
  git reset -q HEAD -- <the paths you just committed>   # NOT a bare `git reset`
  ```
  Name the paths. A bare `git reset` would unstage a colleague's work, which is
  the defect this whole technique exists to avoid.
  **AND THE RESYNC ITSELF CAN UNSTAGE A COLLEAGUE — naming the paths is not
  enough when the paths are SHARED.** `git reset -q HEAD -- <paths>` mutates the
  DEFAULT index, and every agent is required to touch `docs/ROADMAP.md` and
  `docs/BACKLOG.md`, so those two paths are almost always in somebody else's
  staging area at the same moment. Seen 2026-08-01: an agent staged its doc hunks,
  a sibling committed through an isolated index and resynced those same two paths,
  and the first agent's hunks were silently unstaged — its commit would have
  landed without its ROADMAP/BACKLOG tick, which is the one thing every commit is
  required to carry. Nothing warns you. That is now THREE distinct ways this
  recipe bites (a stale `read-tree` base reverting a sibling, a marker matching a
  sibling's prose, and this), and the SAME cheap check caught all three:
  **re-read `git diff --cached` immediately before `git commit`, not when you
  staged.** Treat staging as perishable — stage and commit in one tight window
  rather than staging early and doing more work.
  Push with `git push -u origin <branch>`; on rejection `git pull --rebase`
  and retry. Commit only when your gates are green.

<a id="worktree-push"></a>

### `git push -u origin <branch>` from a worktree pushes nothing

*Moved verbatim from `CLAUDE.md` lines 1095–1122 on 2026-09-23. Current rule: PROTOCOL.md §4.*

- **`git push -u origin <branch>` FROM A WORKTREE PUSHES NOTHING AND SAYS
  "Everything up-to-date" — and worktree isolation is MANDATORY for builders, so
  the standing push instruction is wrong for every builder we run.** Found
  2026-08-16 by the backlog-groomer, which noticed its own commit had not landed
  and re-pushed by hand; reproduced deterministically before writing this down.
  Mechanism: a worktree is on its OWN branch (`worktree-agent-<id>`), while the
  shared checkout holds `claude/<name>`. `git push origin <branch>` expands to
  the refspec `<branch>:<branch>`, and the LEFT side is resolved as a local ref —
  so git pushes the MAIN checkout's branch, which is already at the remote tip,
  and truthfully reports it is up to date. Your commit is never mentioned.
  Measured, with a scratch commit in the worktree so HEAD and the ref differed:
  ```
  HEAD                                    ebbaa18
  ref claude/branch-review-development-…  5c7fb48   (the OTHER worktree's branch)
  git push --dry-run -u origin claude/…   -> "Everything up-to-date"
  git push --dry-run origin HEAD:claude/… -> "5c7fb48..ebbaa18  HEAD -> claude/…"
  ```
  Use `git push origin HEAD:<branch>` — pushing the commit you are ON, by value,
  rather than a name that resolves somewhere else — and then VERIFY with
  `git ls-remote origin <branch>` that the remote tip equals `git rev-parse HEAD`.
  Two things generalise. (a) **This failure is silent and success-shaped**: exit
  code 0, a reassuring sentence, and a whole agent run left on the floor; the
  push-succeeded belief is only falsifiable against `ls-remote`, so verify by
  VALUE, never by exit status. It is the zero-byte-200 trap in different clothes.
  (b) A `-u` flag is not a safety net — here it cheerfully offered to set the
  upstream of a branch the agent was not on. Auditing for this is cheap and worth
  doing after any batch: `git rev-list --count origin/<branch>..<worktree-branch>`
  should be 0 for every worktree branch.

<a id="worktree-pnpm-install"></a>

### A fresh worktree gives false lint/typecheck failures

*Moved verbatim from `CLAUDE.md` lines 1123–1136 on 2026-09-23. Current rule: PROTOCOL.md §1.*

- **A freshly-created WORKTREE gives FALSE `prettier --check` and `tsc` failures
  on files you never touched — and they name a COLLEAGUE'S territory, so the
  natural read is "someone pushed a red build".** Found 2026-08-15 by the CI-2
  agent, which nearly reported the branch tip as lint-red in frontend territory
  before catching itself. Before `pnpm install --frozen-lockfile`, `just lint`
  failed on 6 unmodified `apps/web/src/**` files and `pnpm -r typecheck` failed
  with `Cannot find module 'openapi-fetch'`. The proof it was the environment and
  not the tree: it extracted `apps/web/src/api/drawings.ts` from the committed
  blob at the tip, prettier failed those exact bytes, and the identical bytes
  passed after the install. Rule: **a new worktree is not ready until
  `pnpm install --frozen-lockfile` has run in it**, and a lint failure in a file
  outside your diff is a claim about YOUR environment until you have proved
  otherwise on committed bytes. Do not report it as a colleague's regression —
  that costs two agents' time and starts a hunt for a defect that does not exist.

<a id="worktree-seed"></a>

### Worktrees are seeded at the last merge into main

*Moved verbatim from `CLAUDE.md` lines 1137–1198 on 2026-09-23. Current rule: PROTOCOL.md §1.*

- **A WORKTREE IS NOT NECESSARILY SEEDED FROM THE BRANCH TIP — check `git log -1`
  before you trust anything you read in it.** Found 2026-08-25 by the PICK-1
  agent, which was handed a worktree checked out at `3b0b29e` — a merge into
  `main`, **76 commits behind** `claude/branch-review-development-hkbbnb`. It
  noticed only because the spec its brief named (`apps/web/e2e/pick-anchor.spec.ts`)
  did not exist at all, reset to the remote tip, and went on to finish the job.
  **That detection was luck, and the luck does not generalise**: a MISSING file is
  loud, but a file that merely predates the branch by 76 commits reads as
  perfectly ordinary source, and an agent would then diagnose a bug that was
  fixed weeks ago, or build against an API that has since changed, and its
  eventual rebase would look like an unrelated conflict. The rule: **the first
  action in any worktree is `git rev-list --count HEAD..origin/<branch>`** —
  nonzero means reset before reading anything. Put it in every builder brief;
  that is the only mitigation that has actually worked (three for three — the
  PICK-1 agent at 76 commits behind, the REACH-2 agent at 120, the QA-R4 agent at
  123, all three seeded at `3b0b29e`). **Three occurrences of the SAME commit is
  not bad luck, and the "detect at creation" fix below has not been built** —
  worktree creation belongs to the harness, not to anything in this repo, so
  there is no hook here to put a check in. Until that changes the brief line IS
  the control, so it goes in every builder brief, every time. Do not let the fact
  that agents keep catching it become a reason to stop telling them to look.
  **UPDATE 2026-08-28: it is NINE IN A ROW now, and the seed has merely moved on
  to `03d2eca` — also a merge into `main`, 22 to 31 commits behind depending on
  when the worktree was made.** All nine caught it because the brief carried the
  check; without it the day's dispatches would have built against a tree up to a
  month old, and the tell would have been a rebase conflict that reads as a
  colleague's fault rather than a stale base. Two things this run settles. (a)
  The rate is ~100%, not occasional — treat the reset as the FIRST step of every
  brief and budget for it, rather than filing it as a precaution. (b) The seed is
  always a MERGE INTO `main`, never an arbitrary point on the working branch,
  which is the signature to detect on if a creation hook ever becomes available:
  a HEAD that is not an ancestor of the branch. Until then the brief line is
  still the whole control.
  **MECHANISM FOUND 2026-08-29, and it makes the SHA in this entry a moving
  target — do not memorise it.** A container restart landed mid-turn and the
  session's own checkout came back at `03d2eca` with the local branch ref stale,
  while the remote was 70 commits ahead. **The container's default clone is
  seeded at the last merge into `main`, and worktrees inherit that starting
  point** — which is why every one of the nine arrived at the same commit rather
  than at a random old one. It was never bad luck or a harness bug; it is the
  clone's origin showing through. Two consequences. (a) **The specific SHA will
  change every time `main` advances** — this entry named `3b0b29e`, then
  `03d2eca`, and `main` is now `d4552e3`, so a brief that greps for a literal
  commit will stop working the next time we merge. State the rule as "reset to
  `origin/<branch>` first", never as "watch for commit X". (b) The same restart
  leaves the ORCHESTRATOR's checkout stale in exactly the same way, and its
  local branch ref can point at a commit the remote passed long ago — so after
  any restart, `git fetch && git reset --hard origin/<branch>` before reading or
  reasoning about anything, and check `git ls-remote` rather than the local ref
  when you need to know where the branch actually is.
  **AND THE "AUDIT IT AFTER A BATCH" ADVICE THIS ENTRY ORIGINALLY GAVE DOES NOT
  WORK — measured 2026-08-27, do not retry it.** A behind-count over every
  worktree returned 47 "STALE" rows and not one was the fault: a worktree seeded
  correctly at the tip *naturally* falls behind as the branch advances, so
  trailing and mis-seeded are indistinguishable by that measure, and an audit
  that flags everything flags nothing. Worse, it cannot work even in principle:
  an agent that follows the rule RESETS, so by the time you look, the evidence of
  the bad seed is gone — the only worktrees that could still show it are ones
  where nobody noticed, which is exactly the case you are trying to find. Detect
  it at CREATION, not after. The signature is a HEAD that is not an ancestor of
  the branch (both occurrences were seeded at `3b0b29e`, a merge into `main`),
  not a HEAD that is merely behind.

<a id="git-stash"></a>

### `git stash` is shared across worktrees

*Moved verbatim from `CLAUDE.md` lines 1478–1501 on 2026-09-23. Current rule: PROTOCOL.md §3.*

- **`git stash` IS NOT ISOLATED BY A WORKTREE — THE STASH LIST IS SHARED, AND
  POPPING HANDS YOU WHOEVER STASHED LAST.** Found 2026-08-28 by the hover-to-
  sketch agent, which caused the incident and recovered it. Worktrees give every
  builder its own branch, index and working tree, so the reasonable assumption is
  that `git stash` is private too. It is not: `refs/stash` lives in the SHARED
  `.git`, so a `stash push` → `reset --hard` → `stash pop` cycle in one worktree
  raced a sibling's stash and popped **the sibling's payload into this agent's
  tree** while its own went to them. The failure is silent and success-shaped —
  `git stash pop` reported `Dropped refs/stash@{0}` and exited 0, which is the
  same shape as the worktree-push trap and the zero-byte-200: a reassuring
  sentence over the wrong bytes. It is also worse than the `git add` sweep,
  because a sweep leaves the work in a commit somebody can read, whereas a lost
  pop leaves it nowhere either agent is looking.
  **Use a patch file, never `git stash`:** `git diff > $SCRATCHPAD/<slug>.patch`
  (add `--cached` for staged work, or `git diff HEAD` for both), then
  `git apply` it back. A path you named yourself cannot be taken by a sibling.
  If you have already popped somebody else's work: do NOT drop it. Revert their
  files out of your tree, save their diff to a patch file, and put it back with
  `git stash create` + `git stash store -m "RECOVERED <whose> work — <why>"` so
  the list entry says what it is; then tell the orchestrator. That is exactly
  what happened here and nothing was lost. Before dropping such an entry, prove
  containment rather than assuming it — compare `git show 'stash@{0}:<file>'`
  against `git show HEAD:<file>` per file and read the diffs, because "their work
  landed" is a claim about every file in the stash, not about the branch.

<a id="add-and-commit"></a>

### `git add && git commit` in one command is the sweep

*Moved verbatim from `CLAUDE.md` lines 1502–1524 on 2026-09-23. Current rule: PROTOCOL.md §3.*

- **`git add <my file> && git commit` IN ONE COMMAND IS THE SWEEP, and chaining
  them is what defeats the protocol's own check.** Done by the ORCHESTRATOR on
  2026-08-27, hours after quoting the rule at three separate agents: `4e41eb4`
  says "fix(workflow): a subtree missing from the list is invisible" and carries
  **1,538 lines of a live qa-tester's work** — its 14-case spec, its QA-REVIEW
  entry, and three board items — because `git add` writes to the SHARED index and
  `git commit` commits THE WHOLE INDEX, not the paths you just added. The QA agent
  had staged its files minutes earlier. Nothing was lost; it annotated the record
  in `b253980` rather than rewriting pushed history, which is the right call.
  The existing recipe says to read `git diff --cached` immediately before
  committing, and that WOULD have caught this — but chaining `add && commit` in a
  single shell line leaves no moment to read anything, which is precisely why the
  cheap path keeps winning. **So the rule is not "check the index", it is "never
  put `git add` and `git commit` in the same command while other agents are
  live."** Two separate calls, with the diff read in between.
  And note the NEW half the victim found, which the recipe did not cover: it
  documents the hazard from the COMMITTER's side, so its mitigation is a check the
  committer runs. From the STAGER's side there is no check at all — the QA agent
  staged correctly, ran its own `git diff --cached`, and was swept anyway by
  somebody else's commit landing in between. Its tell is `git commit` replying
  "nothing to commit, working tree clean" when you know you staged three files.
  The only real protection for a stager is to not be one for long: stage and
  commit in one tight window, or build against an isolated `GIT_INDEX_FILE`.

---

## Tests, gates and evidence

<a id="sharded-bisect"></a>

### A new test in a sharded spec can redden an untouched case

*Moved verbatim from `CLAUDE.md` lines 1199–1213 on 2026-09-23. Current rule: CLAUDE.md → Gates and evidence.*

- **ADDING A TEST TO A SHARDED SPEC FILE CAN TURN A LATENT RACE RED IN A CASE
  NOBODY TOUCHED — and the bisect will point straight at the innocent commit.**
  Measured 2026-08-27. `fca2e42` added a case to `qa-reach-batch.spec.ts` and a
  reference-angle case in the same file went red; CI said green at `0cee656` and
  red at `fca2e42`, which is a clean bisect and a wrong conclusion. The decisive
  check was **comparing the failing case and its helpers byte-for-byte across the
  two commits** — identical, 5198 bytes — and then running each in isolation
  against the same app source: HEAD's spec 2/3, `0cee656`'s spec 3/3. Same code,
  different outcome. The e2e suite is sharded 4 ways by filesystem order, so a new
  case reshuffles which cases share a worker and a race that had always been there
  started losing. Rule: when a bisect lands on a commit whose diff cannot plausibly
  reach the failure, **diff the failing test itself across the two commits before
  believing the bisect**; if it is unchanged, the commit changed the SCHEDULE, not
  the behaviour, and the defect is older than both. Corollary: "green at N, red at
  N+1" proves the failure became OBSERVABLE at N+1, never that N+1 caused it.

<a id="force-true-zero-area"></a>

### `force: true`, zero-area targets, and assertions that cannot observe failure

*Moved verbatim from `CLAUDE.md` lines 1214–1295 on 2026-09-23. Current rule: PROTOCOL.md §8.*

- **`click({ force: true })` DISABLES THE ONLY CHECK THAT ASKS WHETHER A USER
  COULD HAVE CLICKED IT — so a target no real mouse can hit passes a 4/4-green
  spec.** Found 2026-08-27 by the frontend-qa pass on REACH-3.
  `dimension-placement.spec.ts` picked its edge with `force: true`; scanning 18
  points along the same 40 mm edge with `elementFromPoint` found **11 of 18
  clickable**, and the central run — exactly where a user aims — returns the
  `drawing-view` polyline, because **the view's own drawn outline sits above its
  own pick target**. A real `page.mouse.click` at the midpoint does nothing,
  silently, and every spec stayed green. There are **26 such calls across 8 spec
  files**; treat each as an unproven pick until checked.
  `force` is legitimate for a target deliberately covered (a modal scrim you mean
  to click through) — it is a lie when used to make a flaky pick stop failing,
  which is the usual reason it gets added.
  **ROOT CAUSE FOUND 2026-08-27, and it is better than "someone was papering over
  a flake": THE PICK TARGET HAD ZERO AREA.** Chrome's `getBoundingClientRect` on
  an SVG `<line>` **ignores stroke width**, so a 2.6 mm-stroked pick line measured
  **118.1 x 0.0 px**. A zero-height box is unhittable by construction — invisible
  to Playwright's actionability check, to assistive tech, and to any touch-target
  audit — so `force: true` was the only way any spec could ever have picked it,
  and every one of those 26 calls was hiding this. Fixed by making the hit region
  a rotated `<rect>` of the same band; the edge went from 9/18 reachable points to
  14/18 and a real `page.mouse.click` at the midpoint went from doing *nothing* to
  opening the author menu. Two lessons: **`force: true` is evidence of a defect,
  not a workaround for one** — when you find one, delete it and see what breaks;
  and **an SVG stroke is not a hit box**, so any pick affordance drawn as a bare
  stroked `line`/`path` needs an explicit filled hit region or it does not exist
  as a control at all.
  **AUDITED 2026-08-27 — the answer is ONE of 22, so this was one bad affordance
  and NOT a systemic pattern.** 18 were cargo (removing the flag changed nothing;
  the targets measured 39×39 px at 18/18 reachable points, and a 40 mm line
  156.2×10.2 at 14/18 with its centre resolving to itself), 3 were legitimate
  (`aria-disabled` controls a spec deliberately clicks through), and 1 was
  vacuous. `force: true` now appears once in `apps/web/e2e/`, inside a
  `clickRefusedControl` helper that asserts area and `elementFromPoint`
  reachability BEFORE forcing.
  **The vacuous one is worth its own rule: `sr-only` IS VISIBLE to every
  visibility API.** `nav-chrome.spec.ts` claimed "a stray click on the locked
  Extrude is inert". While a command is open the whole tool band is `sr-only` —
  measured `1×1 @ (-1,43)`, `clip: rect(0,0,0,0)`, `overflow:hidden`. Not
  zero-area: *clipped out of the frame*. **`checkVisibility()` and Playwright's
  `isVisible()` both return TRUE for it**, so the visibility check the spec was
  leaning on could never fire, and `force` sent the synthetic click to whatever
  was topmost — measured, `header[topbar]`. The Extrude handler was never
  invoked, so all three assertions would have passed identically had the handler
  discarded every pick. A test asserting something is INERT must prove the
  handler ran and did nothing, not that a click went somewhere.
  **A THIRD ZERO-AREA MECHANISM, 2026-08-27: A TAILWIND UTILITY THAT DOES NOT
  EXIST IS SILENT.** `w-32` was written on a progress bed; this theme's spacing
  scale is **closed at 12**, so the class produced no rule at all and the element
  resolved to **zero width** — the DOM looked perfect, every attribute was right,
  and Playwright called the `role="progressbar"` *hidden*. Tailwind does not warn
  on an unknown utility; it simply emits nothing. So the three zero-area defects
  this week each had a different cause — an SVG stroke that `getBoundingClientRect`
  ignores, an `sr-only` element clipped out of frame, and a utility class that was
  never generated — and all three presented identically as "the control is there
  and cannot be touched". When an element measures 0 in either axis, suspect the
  STYLE was never applied before you suspect the layout.
  **This is the THIRD member of one family and the family is the lesson:** an
  assertion that cannot observe the failure mode. `toBeVisible()` is a box
  property, so it passed a SAVE control shoved outside the frame; `toHaveText
  ("Solved")` after a submit was already true, so it read the pre-edit body; and
  `force: true` skips actionability, so it hit an occluded target. In every case
  the suite was green, the product was broken, and the gap was invisible until
  someone measured the thing the assertion was standing in for. When a spec
  proves a USER can do something, assert with the user's own mechanism — a real
  `page.mouse.click` at the control's centre, or `elementFromPoint` resolving to
  the control — never a proxy that skips the step you are claiming works.
  **AND A UNIT ASSERTION CANNOT SEE WHAT ELSE IS ON THE SURFACE — a string can
  satisfy every property you check about it and still be wrong because something
  ELSE already says it.** Measured 2026-08-29 on REASON-GATE-1. The corner
  relief's new blocker read `"Pick two different edge flanges."`, which is
  verbatim the opening of that card's own inline field error — so the card
  rendered the same sentence twice and a `getByText` resolved to two nodes.
  Every unit assertion passed: non-empty, ≤48 characters, names the fix. They
  had to, because **a unit test holds the string in isolation and isolation is
  exactly the property that was violated.** Only the real browser could see it.
  The general form: when a check validates a part, ask what the part is
  ADJACENT to in the assembled thing, and put at least one assertion where the
  adjacency exists. This is the same shape as the golden-suite blind spot (a
  fixture that never reaches the path) and the downstream negative control (a
  probe injected past the guard) — a correct check pointed somewhere the defect
  is not.

<a id="instanceof-dual-builds"></a>

### `instanceof` against a dual ESM/CJS library

*Moved verbatim from `CLAUDE.md` lines 1296–1350 on 2026-09-23. Current rule: CLAUDE.md → Environment recipes.*

- **`instanceof` AGAINST A LIBRARY CLASS IS FALSE FOR A PERFECTLY GOOD OBJECT WHEN
  THE LIBRARY SHIPS DUAL ESM/CJS BUILDS — AND IT FAILS SILENTLY, IN THE DIRECTION
  THAT LOOKS LIKE NOTHING HAPPENING.** Found 2026-09-16 by the pick-mark portal
  agent, in its own code: `camera instanceof PerspectiveCamera` decided whether a
  mark got a depth-sorted `z-index`. `three@0.185.1`'s exports map is
  `{".": {"import": "./build/three.module.js", "require": "./build/three.cjs"}}` —
  ONE version, TWO builds, so `PerspectiveCamera` resolved through `require` is a
  DIFFERENT class object from the one resolved through `import`, and an instance
  of either fails `instanceof` against the other. There is no version conflict to
  find and no lockfile to fix; a single pinned version is enough to produce it.
  The failure has no symptom at the failure site. The test is simply false, the
  `if` does not run, and every mark silently keeps whatever `z-index` it had —
  restacking an overlay against the HUD with no error, no warning and no visibly
  wrong value. That is what puts it in the "assertion that cannot observe its
  failure mode" family rather than in the ordinary-bug pile.
  **Use the library's own duck-typed flag**: three sets `isPerspectiveCamera` /
  `isOrthographicCamera` / `isMesh` on the prototypes precisely because its
  maintainers know this, and a flag is true across every copy. Same reasoning for
  any library that ships both builds. The test that proves you fixed it is a
  stand-in object carrying the FLAG that fails `toBeInstanceOf` — if your test
  uses a real instance from the same import as the code, it cannot fail either way.
  **The census is the part worth copying, because the first fix was one site of
  fifteen.** `grep -rn 'instanceof '` over `apps/web/src` + `packages/design/src`
  finds 15 three-class sites — 12 in `Viewport.tsx` alone, plus `SketchScene.tsx`,
  `BenchBackdrop.tsx` and an `instanceof Mesh` in `glbGeometry.ts` — every one
  carrying the same latent defect. Grep the CALL (`instanceof `), never a
  particular class name. Note `instanceof` against a **browser/JS builtin**
  (`HTMLElement`, `Error`, `Uint32Array`, `DOMException`) is FINE here: one realm,
  one class object, no duality — so this is not a blanket ban on the operator, and
  a sweep that treats it as one will churn 20 innocent sites.
  **CORRECTED within the hour by the agent that found it, because my first version
  said "unknown in production" and that was a failure to measure, not a real
  unknown — and it would have sent someone to sweep 15 sites at a priority they
  do not deserve.** Measured: exactly ONE `three` is installed
  (`node_modules/.pnpm/three@0.185.1`) and only `apps/web` depends on it, so the
  Vite app bundle has a single module graph and **`instanceof` against a three
  class is CORRECT in the shipped app today.** Those 15 sites are LATENT, not
  broken.
  Where it actually bites is **vitest**, where `@react-three/fiber` resolves to
  its CJS dev build and pulls a second module record of the SAME package. Probed
  against a real r3f root: `isPerspectiveCamera: true`, **`instanceof
  PerspectiveCamera: false`**, `constructor === PerspectiveCamera: false`,
  `constructor.name: "PerspectiveCamera"` — a genuine camera failing the check,
  silently.
  **So the durable rule is narrower and sharper than "instanceof is unsafe": a
  dual ESM/CJS pair of the SAME package produces two classes of the same name, and
  no version pin fixes it because there is no version skew to fix.** Two
  consequences, and the second is the one that will actually save somebody a day:
  (a) use the duck-typed flags in any code that must survive both module graphs,
  which is what three does internally; (b) **the moment anyone writes a unit test
  for `Viewport.tsx`'s camera logic, all 13 of its sites will start failing
  inexplicably** — the app is fine, the test environment is not, and the natural
  diagnosis ("my mock is wrong") is wrong. That is why this entry says the app is
  FINE and why a new test breaks anyway; a rule that only said "instanceof is
  dangerous" would have left the next agent debugging the wrong thing.

<a id="count-floor"></a>

### A count floor cannot catch a shrink

*Moved verbatim from `CLAUDE.md` lines 1352–1368 on 2026-09-23. Current rule: CLAUDE.md → Gates and evidence.*

- **A COUNT FLOOR IS A COLLAPSE DETECTOR. IT CANNOT CATCH A SHRINK, AND A
  REFACTOR PRODUCES SHRINKS.** Measured 2026-09-15, and it corrects the advice
  the orchestrator gave. Splitting 15 modules out of `packages/py-kit` into a
  new distribution took `check-air-gap.py`'s python census from **147 walked to
  132** — still above its floor of 100, so **the gate passed while the entire
  new package was scanned by nothing.** I told the fixing agent to "add the root
  and re-derive the floor"; it pointed out that re-deriving the floor does not
  fix the defect class, and proved it on a fixture with one root emptied: with a
  per-root census the gate reports `vacuous=True, empty_roots=[...]`; **with the
  floor alone it reports `walked 3 >= floor, ok` and the defect is invisible.**
  No floor low enough to survive normal churn can detect a corpus that merely
  got smaller. **Census each declared ROOT and refuse when any one contributes
  zero**; keep the global floor for what it is actually good at — total
  collapse — and write that division of labour down beside it.
  Same pass, same file, the reason it happened: the roots were **an inline tuple
  written out twice**, in two different checks. That is precisely how a new
  package gets added to neither. One named constant.

<a id="absent-set"></a>

### A gate that walks what is present cannot see what is absent

*Moved verbatim from `CLAUDE.md` lines 1369–1385 on 2026-09-23. Current rule: CLAUDE.md → Gates and evidence.*

- **A GATE THAT WALKS WHAT IS PRESENT CANNOT SEE WHAT IS ABSENT — derive the
  EXPECTED set independently, or it only ever grades work somebody remembered to
  do.** Same day: `packages/loft-wire` became a dependency of `loft-py-kit`, and
  `deploy/docker/service.Dockerfile` never copied it, so all three service
  images failed at layer 2. `check-build-context.py` could not have caught it,
  and the reason is structural rather than an oversight: that check grades **the
  COPY lines that exist** — does each source resolve, does it survive
  `.dockerignore`. **This was a COPY line nobody wrote.**
  The fix is a second, independently-derived question rather than a better walk:
  for each service, compute which uv workspace members are in its dependency
  closure (from `[tool.uv.workspace] members` plus each member's `[project]
  dependencies`) and assert every one is copied. Note the first probe anyone
  reaches for says nothing: layer 1 (`--no-install-workspace`) resolves
  **happily** with the member absent and exits 0; only layer 2 fails.
  Generalises to every allow-list, manifest and registration table in this repo:
  if the check reads the same list the code reads, it can only tell you the list
  is self-consistent. Ask what SHOULD be in it, from somewhere else.

<a id="before-after-subtraction"></a>

### Before/after subtraction blames the code for drift

*Moved verbatim from `CLAUDE.md` lines 1386–1419 on 2026-09-23. Current rule: PROTOCOL.md §8.*

- **A BEFORE/AFTER SUBTRACTION ATTRIBUTES TO YOUR CHANGE EVERYTHING THAT DRIFTED
  ON SOMEBODY ELSE'S CLOCK — and it does so in the direction that blames the
  code.** Measured 2026-09-15. `fillet-chamfer-gauge.spec.ts` asserted "the gauge
  covers ONLY the mark it stands on" by censusing reachable edge marks before and
  after the gauge mounts and subtracting. It went red in CI naming two extra
  marks, and the orchestrator's brief said the near-certain cause was the commit
  that had just changed the hit sleeve. **That commit was innocent**, proved
  geometrically: the band measured 223x24 at (279,514) and the accused mark sits
  at (628,653), and the element on top of that mark is the viewport `<canvas>`
  carrying `data-buried="true"` in BOTH readings — its edge is behind the body,
  so it was never a pointer target at all.
  The real cause: burial is decided by a **rotating per-frame budget** whose
  convergence is 16-21 s quiet and **up to 31 s under load**. A helper for it
  already existed, `expectSeatsSettled`, with that cost measured and written into
  a named constant — **and the spec that needed it most never called it.** So
  BEFORE was taken half-drained while AFTER, seconds later and through a pick,
  could not be, and every mark the pass buried in between was scored as theft by
  the gauge. On the slowest shard, in the direction that indicts the diff.
  **The rule: when a check takes a BEFORE/AFTER pair, the two readings must be
  taken in the SAME STATE, and the only way to know they were is to NAME THE
  SETTLE OUT LOUD.** An unstated settle is not a wait, it is a coincidence of
  timing that your next optimisation, new mount, or shard partner will delete.
  And prefer **attribution to subtraction** where you can get it: the fixed
  assertion reads each unreachable mark WITH its occluder and checks the
  guarantee against the after-set by `data-gauge` ownership, keeping the delta
  only as a second, independently-derived opinion that must AGREE — refusing
  when the two disagree rather than guessing, because disagreement means one
  reading is measuring something nobody named. That is strictly MORE sensitive,
  not merely more stable: the negative control caught a mark being stolen that
  was **already buried**, which the old subtraction scored as zero.
  Third member this week of "a correct check pointed where the defect is not",
  and the one with the sharpest tell: **a gate that names an innocent commit is
  still a broken gate.** Before believing a bisect or a brief that fingers a
  diff, check whether the measurement could have moved on its own.

<a id="census-call"></a>

### Census the call, not the argument

*Moved verbatim from `CLAUDE.md` lines 1420–1441 on 2026-09-23. Current rule: PROTOCOL.md §8.*

- **A CENSUS THAT GREPS THE ARGUMENT MISSES EVERY CALL THAT PASSES OPTIONS — AND
  THOSE ARE SYSTEMATICALLY THE INTERESTING ONES.** Measured 2026-09-14, by the
  orchestrator, in a brief. A red shard named `full-flow.spec.ts` with
  `toHaveCount — Expected: 0, Received: 1`; I grepped `toHaveCount(0)`, found
  **two** candidate sites, and briefed QA that there were two. There are
  **six** `toHaveCount(` sites in that file, and the one that actually failed
  was none of the two: `toHaveCount(0, { timeout: 30_000 })`, where the option
  object puts a comma exactly where the literal grep expects a paren.
  The bias is not random and that is the whole point. **A call site passes
  options precisely when it is doing something unusual** — a longer timeout
  marks the assertions gating the SLOWEST flows, which are the ones that fail
  in CI and the ones whose failures are hardest to reproduce. So the naive grep
  is blind in the direction of the defects you are hunting. Same shape for any
  argument-matching census: `toHaveText("x")` misses `toHaveText("x", {…})`,
  `waitFor({state:"visible"})` misses a `timeout` sibling, `click()` misses
  `click({ position })`.
  Grep the CALL, not the argument — `toHaveCount(` — and then read the hits.
  And when a brief hands a subagent an enumeration ("there are exactly two
  candidates"), that enumeration is a MEASUREMENT the brief is asserting, so it
  can be wrong in the way any measurement can; say how it was derived, so the
  agent can check it rather than inherit it. This one was caught only because
  the QA agent re-derived the census instead of trusting the brief.

<a id="assembled-ids"></a>

### Test ids are assembled; a literal grep cannot prove absence

*Moved verbatim from `CLAUDE.md` lines 1442–1477 on 2026-09-23. Current rule: PROTOCOL.md §8.*

- **AND I THEN COMMITTED A SECOND INSTANCE OF THAT SAME BLINDNESS IN THE SAME
  COMMIT — `grep '<literal test id>'` CANNOT SUPPORT THE CONCLUSION "THIS ID
  EXISTS NOWHERE", BECAUSE IDS ARE ASSEMBLED.** The bullet above originally
  continued by reporting `part-export-error` as a phantom test id making two
  `toHaveCount(0)` assertions vacuously true. **That was wrong.** The id is real
  and is built by template at `apps/web/src/components/ExportRow.tsx:164` —
  `` data-testid={`${testIdPrefix}-error`} `` — so no literal grep can ever see
  it. I wrote the rule about argument-grep blindness and fell into the
  identifier-grep version of it in the same breath, then stated the false
  conclusion to the founder and wrote it here. Caught by the builder I had
  briefed with it.
  **The near-miss is the part worth keeping.** Acting on the wrong diagnosis
  meant repointing both specs at `part-export-notice`, and that would have been
  an ACTIVE REGRESSION: `-notice` is the partial-body advisory, which renders on
  a healthy page, so `toHaveCount(0)` would have begun failing for being
  correct. A confident wrong diagnosis of a "dead" assertion is more dangerous
  than the dead assertion, because the fix is a code change and the symptom is a
  green test.
  Practical rules. (a) To decide whether a test id exists, grep the **suffix**
  (`-error`), or the template variable, or search the rendered DOM — never the
  full literal. Any id, class or route built by interpolation is invisible to
  the obvious search, and interpolation is the normal way to write a reusable
  component. (b) **"This locator never resolves" is a claim about the running
  app, so prove it in the running app** — render the state and count the nodes —
  rather than inferring it from source.
  The underlying defect class is still real and still worth the guard: an
  assertion whose locator can never resolve is the cheapest member of the
  "cannot observe its failure mode" family (with the `sr-only` control, the
  zero-area SVG stroke, the ungenerated Tailwind utility and `force: true`).
  So: **a `toHaveCount(0)` / `not.toBeVisible()` guard needs a companion proving
  the locator CAN resolve**, and an assertion you have never seen fail is not
  yet a gate — mutate the app until it reddens, once. The genuine defect here
  was narrower than I claimed and that guard would have found it:
  `export-formats.spec.ts` drives the export BAND (`part-export-band-*`) while
  watching the PANEL's alert, a node that spec never touches, so a band failure
  would have rendered `part-export-band-error` and the assertion still read 0.

<a id="params-extra-ignore"></a>

### Params models are `extra="ignore"`

*Moved verbatim from `CLAUDE.md` lines 1525–1540 on 2026-09-23. Current rule: PROTOCOL.md §8.*

- **PARAMS MODELS ARE PYDANTIC-DEFAULT `extra="ignore"`, so a payload that
  MISSPELLS a field validates, evaluates, and silently gives the OLD reading —
  and every gate agrees with it.** Found 2026-08-26 by the PATTERN-1 agent, in
  its own first draft: spelling the new selection `params.features` instead of
  `params.scope` returned 2xx, evaluated happily, and produced the legacy
  whole-body behaviour, with **seven tests passing against the wrong scope**.
  There is no server-side guard and there cannot easily be one — `extra="ignore"`
  is what makes the DTOs forward-compatible. Two consequences. (a) A contract
  test for a new param MUST assert on the RESULT (the geometry, the row, the
  bytes), never on the status code; a 2xx proves the request parsed, not that it
  meant anything. (b) When you add a field to a params model, the UI-side test
  that exercises it is the only thing standing between a typo and a silently
  ignored feature — write it in the same commit as the DTO, not with the UI.
  This is the `gen-check`-measuring-the-wrong-input trap in a third costume: the
  pipeline was healthy, the input was wrong, and everything downstream
  self-consistently confirmed it.

<a id="rare-token-conservation"></a>

### Verify a bulk deletion by conservation of rare tokens

*Moved verbatim from `CLAUDE.md` lines 1543–1561 on 2026-09-23. Current rule: CLAUDE.md → Gates and evidence.*

- **VERIFY A BULK DELETION BY CONSERVATION OF RARE TOKENS, NOT BY READING THE
  DIFF.** Measured 2026-09-14 pruning `docs/ROADMAP.md` from 3 915 lines to 445
  (284K -> 44K) by collapsing closed items into `docs/CHANGELOG.md`. A diff that
  size cannot be read for what LEFT — which is the only direction that matters
  in a prune, and the direction a normal review is worst at, because a reviewer's
  attention goes to the lines that arrived. The check that works: take every
  backtick-quoted token and every word occurring <= 2 times in the ORIGINAL, and
  assert each still appears somewhere in the union of the rewritten files. Rare
  tokens are where the irreplaceable content is — an id, a SHA, a measured
  number, the one sentence naming a decision — and common words are noise that
  survives any edit, so filtering on rarity is what makes the check sensitive.
  It earned its keep immediately: it caught "SSO/OIDC for teams" silently lost
  from Phase 5 to a Read-tool TRUNCATION, i.e. a loss with no deliberate act
  behind it, which no amount of careful editing would have prevented and no
  reviewer would have missed the absence of.
  Generalises past docs: any mechanical bulk rewrite (a codemod, a mass rename,
  a generated-file regeneration) can be checked the same way — conserve the rare
  strings, ignore the common ones. And prefer it to a line-count or byte-count
  assertion, which passes happily while the wrong half survives.

<a id="fixture-rejected"></a>

### A new fixture rejected by existing gates proves they were blind

*Moved verbatim from `CLAUDE.md` lines 1680–1694 on 2026-09-23. Current rule: CLAUDE.md → Gates and evidence.*

- **WHEN A NEW FIXTURE IS REJECTED BY EXISTING GATES, THAT REJECTION IS THE PROOF
  THEY WERE BLIND — do not "fix" the fixture.** Measured 2026-08-29 on STEPDET-1.
  A determinism hole survived because both assembly goldens were single-`Solid`
  parts, so the gate could not fail for its own reason; adding a multi-body
  golden was the durable half of the fix. That golden was then REJECTED by two
  NEIGHBOURING gates — the round-trip oracle matched solids per **instance**, and
  the instancing gate asserted one B-rep per **part**. Both assertions are true
  only while a part is one solid, i.e. both had the same blindness as the gate
  under repair, and both had been passing for years. The tempting read is "my
  fixture is wrong"; the correct one is "three gates shared an assumption nobody
  had written down". Both are now per-BODY, with instance identity moved to the
  NAMED occurrences (OCCT adds an unnamed one per body). **A fixture built to
  reach an uncovered path is a probe of every gate it passes through, not only of
  the one you are fixing** — when it comes back rejected, read the rejection
  before believing it.

<a id="negative-control-downstream"></a>

### A negative control downstream of the guard measures nothing

*Moved verbatim from `CLAUDE.md` lines 1695–1706 on 2026-09-23. Current rule: CLAUDE.md → Gates and evidence.*

- **A NEGATIVE CONTROL AIMED DOWNSTREAM OF THE GUARD IT TESTS MEASURES NOTHING —
  and it reports a WORKING fix as broken.** Measured 2026-08-29 on GATE-FLOOR.
  The agent's probe emptied a gate's check list just before the `if all(...)`,
  which was correct until the fix added a count floor EARLIER in the same block;
  the clear then ran *after* the floor, so the first "after" reading said both
  gates still exited 0 and the fix had failed. It had not. **When you add a
  guard earlier in a function, every existing probe that injects its mutation
  further down silently stops testing anything** — and the failure direction
  here is the nasty one, because "my fix does not work" is a conclusion people
  act on by rewriting working code. A lost `append` is missing for the WHOLE
  verdict, so the injection belongs at the START of the verdict block. Same
  family as the gates themselves: a check that cannot observe its subject.

<a id="audit-by-question"></a>

### Audit a defect class by its question, not its shape

*Moved verbatim from `CLAUDE.md` lines 1707–1720 on 2026-09-23. Current rule: CLAUDE.md → Gates and evidence.*

- **AN AUDIT THAT PATTERN-MATCHES AN IDIOM MISSES EVERY INSTANCE WEARING A
  DIFFERENT SHAPE — ask the question the idiom stands for.** Same pass: the
  audit table marked `check-build-context.py` *"n/a (straight-line, not
  list-driven)"*, which was true of its self-test and blind to its MAIN path —
  the path CI runs — which printed `0 COPY source(s) reach the build context`
  and **exited 0**. That is the gate standing in for the `docker build` the
  403-blocked registry makes unreachable here, silently disarmed. It was found
  only because the brief said to check the others too. `check-tailwind-scale.py`
  was not in the audit's table at all and had the same hole, saved only by
  `max()` raising on an empty sequence — an accidental floor one `default=0`
  away from a silent pass. **The brief said "check the other three"; the answer
  was eleven checked and four holed.** When a defect class has recurred, audit
  the whole class by its QUESTION ("what does this gate do when it examines
  nothing?"), never by grepping the shape the last instance happened to have.

<a id="fastapi-routes"></a>

### Walking FastAPI routes: use `iter_route_contexts`

*Moved verbatim from `CLAUDE.md` lines 1837–1859 on 2026-09-23. Current rule: CLAUDE.md → Environment recipes.*

- **WALKING FastAPI's RAW ROUTES REPORTS A CORRECTLY-AUTHENTICATED ROUTER AS
  WIDE OPEN — use `fastapi.routing.iter_route_contexts`, not
  `_IncludedRouter.original_router.routes`.** Measured 2026-08-29 while building
  the K2 auth gate, and it is a correction to the advice this file and the
  BACKLOG entry both previously gave. Recursing the raw included routers gets
  the right route COUNT and two things wrong: (a) a router included into another
  router keeps only its own prefix, so a route served at `/outer/inner/leaf`
  reports as `/inner/leaf`; and (b) — the dangerous one —
  `include_router(r, dependencies=[Depends(auth)])` records the dependency on the
  INCLUSION, so the raw route's `dependant` is **empty** and a gate reading it
  calls a properly-authenticated router unauthenticated. **That is a false
  positive on a security gate, and a gate that cries wolf gets muted, which is
  how it stops protecting anything.** Neither defect fires today (no service uses
  nested inclusion or include-level auth), so the raw walk gives the right answer
  now and a silently wrong one the first time someone reaches for a normal
  FastAPI idiom. `iter_route_contexts` is the flattener FastAPI's own OpenAPI
  generator uses: it composes prefixes and merges inclusion-level dependencies.
  **The honest caveat that comes with it:** once the walk uses FastAPI's own
  flattener, an OpenAPI cross-check is a CONSISTENCY check, not an independent
  oracle — which is exactly why the count floor carries the weight. The general
  lesson is the one this repo keeps paying for: **a walk that finds nothing makes
  every "all of them are fine" assertion vacuously true**, so assert the count
  you expect to walk, not only the property you expect to hold.

<a id="screen-position-gate"></a>

### A screen-position gate cannot tell the thing moved from the camera moved

*Moved verbatim from `CLAUDE.md` lines 2027–2057 on 2026-09-23. Current rule: PROTOCOL.md §8.*

- **A GATE THAT ASSERTS A SCREEN POSITION CANNOT TELL "THE THING MOVED" FROM
  "THE CAMERA MOVED" — and for six commits ours reported a defect that was not in
  its contract.** Measured 2026-09-18. `fillet-chamfer-gauge.spec.ts`'s *contract
  beta* ("releasing the pointer must leave the instrument where the drag put it")
  went red at `Expected: <= 6 | Received: 52.83`, which reads unambiguously as the
  gauge springing back to its opening length. **The instrument never moved.**
  Sampling the grip's own `data-value` across the release: 10.5 before `mouse.up`
  and 10.5 at +0, +50, +150, +400, +1000 and +3000 ms, `aria-valuenow` and the
  editor field agreeing throughout, the drawn arrow unchanged, the 24x24 box
  byte-identical. What moved was the CAMERA — view-matrix translation
  `(-8.07,-8.68,-81.32)` -> `(-6.84,-8.55,-85.43)`, a 5 % dolly that slid a
  stationary instrument 52.7 px. The spec compared the grip's PAGE POSITION, a
  proxy a legitimate camera move invalidates, and `handUnderway()` falling to zero
  IS the re-fit's trigger, so the camera moves on exactly the frame the assertion
  sampled.
  **Assert the property, not a stand-in for it**: the fixed version watches
  `data-value` vs the editor field on every animation frame via a sampler
  installed IN THE PAGE and stamped by a `pointerup` listener, plus the
  `gauge-<id>-spine` WORLD length — both camera-invariant, and strictly stronger
  than what it replaced. Note the first rewrite read only the SETTLED state and
  the mutant SURVIVED; it took the per-frame sampler to make the gate able to
  redden (`+24.9ms rod=8 field=10.5`, 51 of 52 frames). Same family as the
  `sr-only` control and the zero-area stroke: a check that cannot observe its
  subject.
  **And the wrong-gate hid a REAL defect it was not built to see.** The camera
  move is itself a bug — releasing a gauge lurches the view when nothing is out of
  frame — because `readProposal` unions the whole `command-layer` group, resting
  sketch ink included. So the red was simultaneously a false accusation of the
  gauge and a true signal about the camera, which is why "the assertion is wrong"
  and "nothing is wrong" are different conclusions: fix the assertion, then go and
  look at what it was accidentally detecting.

<a id="camera-rest"></a>

### `waitForCameraRest` is blind to a re-frame

*Moved verbatim from `CLAUDE.md` lines 2058–2076 on 2026-09-23. Current rule: PROTOCOL.md §8.*

- **`waitForCameraRest` COMPARES VIEW DIRECTION ONLY, so it is blind to every
  re-frame — and a spec that samples a screen point after a preview changes may be
  passing on round-trip latency.** Same pass. The CRAFT-12 re-fit is a pure
  standoff/target ease ("re-frame, never re-orient"), so direction never changes
  and the helper returns on its first sample MID-SLIDE. That is not a bug in it;
  it is the wrong instrument. The revolve case reproduced 3/3 by adding what CI
  has for free — latency, as four idle `page.evaluate` round trips between
  sampling the projected track and hit-testing the pixel: camera dead still at
  `157.14,128.99,178.98` through track/idle/hover, then `160.68,130.78,180.18` at
  the read, `held=null`. **Hovering a sleeve builds the snap ladder, the ladder
  draws inside `command-layer`, and that group's world box is what the re-fit
  watches — so ARMING the instrument fires a second re-fit.**
  Use a POSITION settle (`waitForCameraStill`: position, 0.02 mm over 4 frames),
  name it at EVERY place the camera can move (after each value change AND after
  the arming hover), and re-sample the track after arming rather than before.
  Verify against the REPRODUCTION, not against quiet: green 3/3 with eight idle
  round trips, double what reddened it. **There are likely more specs with this
  latent hazard than the two that failed** — the ones green today may be green on
  timing, exactly as this one was.

<a id="playwright-cache"></a>

### A stale Playwright transform cache

*Moved verbatim from `CLAUDE.md` lines 2077–2083 on 2026-09-23. Current rule: PROTOCOL.md §7.*

- **A STALE PLAYWRIGHT TRANSFORM CACHE REPORTS WRONG TEST LINE NUMBERS AND MAY RUN
  STALE BYTES.** Same pass: a combined run reported tests at lines 488/572/699
  when the file on disk had them at 598/684/833. `rm -rf
  /tmp/playwright-transform-cache-0` fixed it, and everything was re-run cold.
  Same family as the stale-Vite transform: it corrupts your EVIDENCE rather than
  your run, and the tell is cheap — if a reported line number does not match the
  file, stop and clear the cache before believing anything else the run said.

<a id="accidental-settle"></a>

### Making a spec faster can delete an accidental settle

*Moved verbatim from `CLAUDE.md` lines 2084–2110 on 2026-09-23. Current rule: CLAUDE.md → Gates and evidence.*

- **MAKING A SPEC FASTER CAN DELETE AN ACCIDENTAL SETTLE — an implicit wait
  nobody wrote down, which the slow version was providing for free.** Found
  2026-08-29 while closing QA-CI4-HEADROOM-1. A ring scan did 1068 full-frame
  canvas readbacks to read nine pixels each; batching them 356:1 was obviously
  correct and immediately produced a new failure ("the origin ring must be
  visible ink"). The caller waits on the selection readout, which is **DOM**,
  while the ring it then measures is **canvas on a demand-rendered scene** — and
  the 356 sequential awaits had been letting the renderer win that race, with
  nothing in the code saying so. The fix is to STATE the wait (`waitForFrames`),
  never to un-batch: **an accidental settle is a latent flake whether or not
  anyone has tripped it yet**, and the optimisation only revealed it. Whenever a
  spec mixes a DOM wait with a canvas assertion, the synchronisation between them
  must be written down, because the thing that has been supplying it is
  incidental timing.
  **And in the same pass, TWO COST MODELS WERE WRONG BEFORE INSTRUMENTATION
  SETTLED IT.** The orchestrator guessed the perf ceiling was too tight (it was
  the most machine-independent assertion on the shard: 1.15-1.22 against a 2.00
  ceiling while absolute cost moved 66%); the agent then guessed the readbacks
  were the cost, batched them 356:1, and **the wall clock did not move**
  (45.9/47.5/timeout → 49.3/46.3/44.7). Only a per-phase timer found it: the zoom
  loop was **47% of the wall** (15.8 s of 33.2 s) and the scan it had just
  optimised was **0.6%** (190 ms). The loop re-parked the pointer before each of
  48 wheel notches with the cursor already there — 46 of 48 round trips moved it
  nowhere, and the cost was sequential CDP latency, not pixels. **Instrument
  before optimising a slow spec; the obvious expensive-looking operation is
  routinely not the cost**, and in a browser-driven test the cost is usually the
  number of round trips, not the work in any one of them.

<a id="quiet-window"></a>

### Run the batch-end e2e in a quiet window

*Moved verbatim from `CLAUDE.md` lines 2111–2130 on 2026-09-23. Current rule: CLAUDE.md → Environment recipes.*

- **Run the batch-end `just e2e` in a QUIET window — never concurrent with
  heavy agents — and treat a red sweep run under CPU load as UNCONFIRMED.**
  Seen 2026-07-23: a batch-end sweep kicked off while 2-3 kernel agents were
  running geometry pytest + booting isolated stacks came back 2 failed / 188
  passed; both failures were 5s-timeout UI-state waits in the heaviest specs
  (`full-flow.spec.ts` register→sketch→extrude→export, `sketch-on-face.spec.ts`)
  — `new-extrude` "solve a sketch first" still disabled, `sketch-strip`
  toHaveCount(0) got 1. The discriminator that proves FLAKE not regression: the
  failure POINT MOVED between runs (extrude-enable one run, sketch-strip-dismiss
  the next) — a real code regression fails identically every time; a
  contention flake wanders to whichever 5s-gated step loses the CPU race that
  run. The diff under test (`beb3a21`, drawings-only) didn't touch the
  sketch/extrude path, and 188 specs passed. Procedure: (a) don't overlap the
  gate with agent load; (b) if it happens, reconfirm the specific failures by
  an isolated rerun in a QUIET window before concluding regression — but a
  moving failure point is already a flake tell; (c) the heavy founder-flow
  specs' intermediate waits use the default 5s (the `eval-status` wait already
  uses 30s) — bump the solve/UI-state-gated ones to a generous timeout so the
  gate is contention-robust (filed as a spec-hardening item, same class as the
  raster tolerance fix).

<a id="bisect-green-end"></a>

### A bisect's green end must be a commit seen to pass

*Moved verbatim from `CLAUDE.md` lines 2131–2153 on 2026-09-23. Current rule: CLAUDE.md → Gates and evidence.*

- **A bisect that reproduces a failure at an "earlier green" commit proves the
  failure is NOT in the diff under test — but it does NOT prove "environment."
  Confirm the actual assertion before naming a cause.** Cautionary tale
  (2026-07-22): a batch-end `just e2e` failed 6 specs; a four-point bisect (HEAD
  → `0c10265` → `47c88f4` → `24b1c53`) reproduced them all at a commit believed
  green, and the orchestrator concluded "container-restart raster drift" and
  filed it as such. A qa-tester then read the specs and found the real cause: 5
  of the 6 (the measure specs) asserted the STALE pre-units-convention readout
  string `"37.42"`, but the units change (`70ce39d`, 2026-07-17) switched the
  readout to `formatLength` → `"37.4166 mm"` — and that commit is an ANCESTOR of
  all three bisect points, so they were deterministically red there too, for a
  code/assertion reason, not the environment. The `toHaveText("37.42")` timeout
  was misread as "the readout never appears" when it appears with the correct
  value in a new format. Only the undo-redo 1280 band-fit (`≤0px` → `Received:
  1`) was genuine sub-pixel raster drift (fixed with a documented ≤2px
  tolerance). Lessons: (a) the "green" end of a bisect must be a commit you have
  actually seen pass, not one assumed to; a shared ancestor bug hides from every
  bisect point below it. (b) Before concluding "environment," open the spec and
  read the EXACT expected-vs-received — a stale golden/format string and a raster
  miss look identical through a `toHaveText` timeout. (c) DOM-overlay picks
  (`getByTestId("measure-vertex-N")`) are already raster-independent, so "pick
  coords drifted" was never even applicable to those specs. Measure/undo-redo
  specs are container-robust as of `1e1395d`.

<a id="founder-screenshots"></a>

### Founder screenshots are refresh-on-demand

*Moved verbatim from `CLAUDE.md` lines 2154–2173 on 2026-09-23. Current rule: CLAUDE.md → Environment recipes.*

- **Founder screenshots are refresh-on-demand, not a per-run output.** `just
  e2e` used to rewrite ~90 PNGs under `docs/screenshots/` every run, forcing a
  noise commit. Two churn sources: (1) the per-run random session email in the
  header (`uniqueEmail()`), and (2) Chromium's screenshot pixels are **not**
  byte-identical across a full run even with software GL — sub-pixel raster/
  camera state flips a few AA pixels (thousands over a dense sketch grid) purely
  from browser-process state; it's byte-stable in isolation but not under load,
  so pure determinism can't win. Fix (all in `apps/web`, one seam in
  `e2e/fixtures.ts`): the shared `test` fixture wraps `page.screenshot` to
  normalise the header email, freeze animations/caret, wait for `document.fonts.
  ready`, and **skip the file write for `docs/screenshots/**` unless
  `UPDATE_SCREENSHOTS=1`**. Routine e2e captures (still exercising the render)
  but never overwrites the committed PNGs → tree stays clean. To refresh the
  founder shots deliberately: `UPDATE_SCREENSHOTS=1 pnpm --filter @loft/web e2e`
  (config forces portable software-GL rendering so any contributor regenerates
  near-identical baselines). Specs import `test`/`expect` from `./fixtures`, not
  `@playwright/test`. NB: `reducedMotion` is NOT a top-level Playwright `use`
  option in 1.56 (`use.contextOptions.reducedMotion`), and enabling it snaps the
  r3f camera, which shifts face-pick screen coords and flakes the pick specs —
  left off deliberately.

---

## Environment

<a id="env-intro"></a>

### The environment-recipes section, as originally introduced

*Moved verbatim from `CLAUDE.md` lines 1089–1094 on 2026-09-23. Current rule: CLAUDE.md → Environment recipes.*

Next-Lane's equivalent section was earned through painful debugging; ours
starts small. **When you burn >15 minutes on an environment quirk, append the
recipe here in the same commit as the fix.**

- Working branch: develop on the current `claude/*` branch; never push to
  `main` without explicit permission.

<a id="runpath-swap"></a>

### Swapping an auditwheel-vendored library without touching `.venv`

*Moved verbatim from `CLAUDE.md` lines 1562–1570 on 2026-09-23. Current rule: CLAUDE.md → Environment recipes.*

- **To test swapping an auditwheel-vendored library WITHOUT touching the shared
  `.venv`, check for `RUNPATH` (not `RPATH`) with `readelf -d`.** `LD_LIBRARY_PATH`
  takes precedence over `RUNPATH` but is beaten by `RPATH`, so when the consumer
  uses `RUNPATH` you can drop a replacement in a scratch dir, point
  `LD_LIBRARY_PATH` at it, and the real library is never mapped — prove which one
  loaded by grepping `/proc/self/maps` after the import. That is how the P0
  licence fix (a GPL-free `libjbig` stub) was validated against the full 2385-test
  geometry suite on 2026-07-31 with zero risk to a concurrent agent's environment.
  Mutating the shared `.venv` to test a swap would have broken every sibling.

<a id="python-and-just"></a>

### Python interpreters and `just` in this container

*Moved verbatim from `CLAUDE.md` lines 1571–1577 on 2026-09-23. Current rule: CLAUDE.md → Environment recipes.*

- In this container, `uv python install 3.12` fails (403: the egress proxy
  blocks github.com release downloads of python-build-standalone — a policy
  denial, don't retry/route around). Not needed: system interpreters exist at
  `/usr/bin/python3.10`–`3.13`; with `.python-version` = 3.12, `uv sync`
  picks up `/usr/bin/python3.12` automatically. PyPI + npm registries are
  direct (proxy no-proxy list), so `uv sync` / `pnpm install` just work.
- `just` is not preinstalled: `uv tool install rust-just` → `~/.local/bin/just`.

<a id="ipv6-loopback"></a>

### No IPv6 loopback here; CI is dual-stack

*Moved verbatim from `CLAUDE.md` lines 1578–1596 on 2026-09-23. Current rule: CLAUDE.md → Environment recipes.*

- **This container has NO IPv6 loopback, so `localhost` here can only ever mean
  `127.0.0.1` — and every CI runner is dual-stack.** Anything that BINDS or
  PROBES a loopback address is therefore untestable locally in a way that *looks*
  tested: it passes here for the wrong reason. Cost a full round trip on
  2026-08-01, when the new e2e workflow's first three runs were ALL red —
  including the two that should have been green, which made the negative control
  worthless because it died in setup like the others. Cause: Vite forces
  `dns.setDefaultResultOrder("verbatim")`, so its default `localhost` host bound
  `::1` while `baseURL`/`webServer.url` asked for `127.0.0.1`; the process stayed
  alive and never answered. **The tell is the wording** — Playwright says
  "Timed out waiting Nms from config.webServer" for a live-but-silent server and
  "exited early" for a crash, and they are different bugs. Two rules: bind the
  LITERAL address (`--host 127.0.0.1`) rather than trusting name resolution, and
  **when a diagnosis cannot be reproduced locally, ship the PROBE with the fix** —
  `scripts/e2e.sh`'s CI preflight prints `127.0.0.1 -> 200, [::1] -> 000`, so a
  wrong diagnosis costs one log line instead of another round trip. Note the
  first instinct here (raise the 60 s timeout) was ruled out by measurement: with
  `apps/web/node_modules/.vite` deleted, Vite served in 1.3 s. A timeout is
  headroom, never a fix.

<a id="egress-map"></a>

### Egress: what is reachable and what is denied

*Moved verbatim from `CLAUDE.md` lines 1597–1625 on 2026-09-23. Current rule: CLAUDE.md → Environment recipes.*

- **"github.com is blocked" is TOO COARSE: release-asset downloads are 403, but
  `git clone` over HTTPS WORKS — and so do `archive.ubuntu.com` and
  `files.pythonhosted.org`.** Measured 2026-08-01 while mirroring
  corresponding source (LIC-2): `curl -L
  https://github.com/Open-Cascade-SAS/OCCT/archive/refs/tags/V7_9_3.tar.gz` →
  **403**, same policy-denial class as the python-build-standalone block, while
  `git clone --depth 1 --branch V7_9_3 https://github.com/...` → **succeeds**
  (36 119 files). The brief for that task reasonably assumed the whole host was
  denied and pre-authorised a documented-only outcome; taking that at face value
  would have shipped an unverified recipe when the work could be — and was —
  fully executed and checksummed here. Rule: when you need bytes from a denied
  host, check whether a DIFFERENT protocol or a different upstream serves the
  same artefact before concluding it is unfetchable. Corollary in the same
  session: the legacy PyPI path
  `files.pythonhosted.org/packages/source/<l>/<name>/<file>` returned a
  **zero-byte body with a SUCCESS status**, while the hashed
  `/packages/<a>/<b>/<sha>/<file>` URL from the JSON index returned the real
  file. A zero-byte 200 is the worst failure shape there is — every digest check
  downstream agrees with itself — so assert on size, and prefer the URL the
  index gives you over a path you constructed.
  **Measured egress map, extended 2026-08-01 (LIC-4).** REACHABLE: `git clone`
  over HTTPS, `raw.githubusercontent.com`, `archive.ubuntu.com`,
  `files.pythonhosted.org`, `conda.anaconda.org`. DENIED (`CONNECT 403`): every
  distro source host probed — nine of them, incl. the CentOS/AlmaLinux vaults —
  and github.com *release assets*. The practical consequence is that
  distro-built binaries cannot have their SRPMs mirrored from here, so a task
  needing corresponding source for one of them must either derive the answer
  from artefacts already on disk or write down why it does not need the source
  at all. Full table with the probe list: `docs/LICENSING.md` §7.5.

<a id="build-context-gate"></a>

### The image build is untestable here: the build-context gate

*Moved verbatim from `CLAUDE.md` lines 1626–1648 on 2026-09-23. Current rule: CLAUDE.md → Environment recipes.*

- **The blocked registry means NOTHING about the image build is locally
  testable, so anything the build depends on needs a gate that does not build.**
  `.dockerignore` excludes `scripts`, `deploy` and `docs` wholesale and then
  re-includes named files with `!` negations; a `COPY` whose source is not
  negated resolves to NOTHING and fails the build. That failure is unreachable
  here by construction — no `just` target can produce it — so its first and only
  signal is the `deploy-path` workflow, the slowest one we run. It cost two red
  commits on 2026-08-01: LIC-2 added `scripts/corresponding_source.py` to the
  runtime COPY (check-licences.py imports it) with no negation, and all three
  service images failed while `ci` and `e2e` stayed green, because neither
  builds an image. Second time the list had lost an entry, which is the tell
  that the *allow-list* is the defect. Fix: `scripts/check-build-context.py`
  re-implements moby's `MatchesOrParentMatches` and asserts every Dockerfile
  COPY source exists and survives `.dockerignore` — stdlib, no daemon, ~10 ms,
  wired into `just lint` and CI's `compose` job. Two things generalise. (a) When
  a whole class of failure is unreachable locally, re-implement just enough of
  the absent tool to gate it, and CROSS-CHECK the re-implementation against a
  real one rather than trusting it (this matcher was diffed against the docker
  SDK's own context walk over all 445 included entries — zero disagreements; a
  naive comparison against the SDK's `matches()` shows 190 false differences,
  because that method is the depth-limited variant and directory pruning happens
  in `walk()`). (b) Ship the gate with a `--self-test` that reproduces the
  defect and demands a failure, exactly as `just licence-selftest` does.

<a id="nginx-pid"></a>

### `nginx -t` creates the pid file

*Moved verbatim from `CLAUDE.md` lines 1649–1679 on 2026-09-23. Current rule: CLAUDE.md → Environment recipes.*

- **`nginx -t` CREATES THE PID FILE. A BUILD-TIME CHECK RUN AS ROOT THEREFORE
  MANUFACTURED THE RUNTIME CRASH IT WAS ADDED TO PREVENT.** Measured 2026-09-15;
  the web container had exited 1 on boot on every commit since it landed —
  `[emerg] 1#1: open() "/tmp/nginx.pid" failed (13: Permission denied)` — while
  every other service came up healthy. "`nginx -t` only validates syntax" is
  FALSE and is the belief that shipped this: `ngx_init_cycle()` runs almost the
  whole startup under `-t`, creating the pid file (ngx_cycle.c ~322), creating
  the cache/temp paths (~356) and opening the log files (~365); only the listen
  sockets (~636) are skipped. `ngx_create_pidfile()` opens with
  `NGX_FILE_CREATE_OR_OPEN` at 0644 under `-t`, and test mode returns from
  `main()` **without** calling `ngx_delete_pidfile()`. So a root `nginx -t` in
  the Dockerfile baked `-rw-r--r-- root:root /tmp/nginx.pid` into the image, and
  the non-root master's `O_TRUNC` open of that existing file got EACCES.
  **/tmp being 1777 is a red herring** — the sticky bit governs unlink and
  rename, never writing to a file you do not own. Proved with three `open(2)`
  calls from uid 100 under `setpriv`, which is how to settle this class without
  a daemon: root-owned 0644 file in a 1777 dir → `(13: Permission denied)`;
  same dir, file ABSENT → OK (so /tmp was innocent); dir owned by the runtime
  user → OK, and OK again on re-open. Fix: a pid directory the image owns
  (`/var/run/nginx`, chowned) plus the validation moved AFTER `USER nginx`, so
  the check runs as the user that has to live with its artifacts.
  Three things generalise beyond nginx. (a) **A build-time check that runs as a
  different user than the runtime is not a check of the runtime** — it can pass
  for reasons the container will never enjoy, and here it actively created the
  fault. Put the gate after `USER`. (b) **A tool that VALIDATES may also WRITE**;
  before trusting "it only inspects", read what it does, and delete or chown
  what it leaves. (c) Reopening a fd through `/proc/self/fd/N` needs permission
  on the underlying object, and **a root-owned pipe denies a non-root reopen
  with the same errno 13** — which is why the build-time `nginx -t` now sends
  its output to a regular file: `/var/log/nginx/error.log` is a symlink to
  `/dev/stderr`, and BuildKit's stdio is not the container's.

<a id="native-boot"></a>

### The native, container-free boot

*Moved verbatim from `CLAUDE.md` lines 1721–1782 on 2026-09-23. Current rule: CLAUDE.md → Environment recipes.*

- **The Docker *registry* is blocked here, but the stack does NOT need Docker —
  a native, container-free boot works and CAN drive `just e2e` + founder
  screenshots.** `docker pull` of `postgres:16` / `redis:7` / `minio/minio:*`
  fails mid-blob with **403 Forbidden** from
  `production.cloudfront.docker.com/...blobs...` (same policy-denial class as
  the github python-build block above; don't retry/route around), so the
  *compose* stack can't build. But every external is OPTIONAL and the services
  run natively via uvicorn, so the whole app boots with no containers:
  - **documents / gateway → SQLite.** Each needs a schema. Do NOT run alembic
    against SQLite: the migrations render Postgres DDL verbatim (e.g.
    `created_at DATETIME DEFAULT (now())`) and SQLite has no `now()` →
    `OperationalError` at insert time. Instead create the schema with
    SQLAlchemy `metadata.create_all` (renders dialect-correct DDL —
    `CURRENT_TIMESTAMP` on SQLite), exactly as `scripts/e2e.sh` and the unit
    suites do:
    ```python
    from sqlalchemy.ext.asyncio import create_async_engine
    from documents.db import Base as D; from gateway.db import Base as G
    from py_kit.db import async_dsn
    for url, base in ((doc_dsn, D), (gw_dsn, G)):
        e = create_async_engine(async_dsn(url))
        async with e.begin() as c: await c.run_sync(base.metadata.create_all)
        await e.dispose()
    ```
    DSNs are file URLs: `sqlite+aiosqlite:////abs/path/documents.db` (the env
    var is `POSTGRES_URL`; `py_kit.db.async_dsn` normalizes `sqlite://` →
    `sqlite+aiosqlite://`).
    **Always `rm -f` the SQLite files first — `create_all` does NOT migrate.**
    `metadata.create_all` is a no-op on a table that already exists, so a
    scratchpad `documents.db` left by an earlier session is silently reused at
    ITS old schema. Seen 2026-07-25: a db from 07-23 made every e2e spec fail
    at `new-sketch` with gateway 500s — `no such column: features.suppressed`,
    a column added after that file was written. The failure looks like a code
    regression and is not one, and it gets worse the longer a container lives
    (the schema drifts further each day). Start every native boot from fresh
    files.
  - **geometry → in-process LRU mesh store** when `S3_URL` is unset. Keep
    `--workers 1` (the LRU is per-process; multi-worker would split it). No MinIO.
  - **gateway → fail-open rate limiter** when `REDIS_URL` is unset (no-op
    dependency). WS fan-out + mate authoring are plain REST/in-proc — no Redis. 
  Boot (ports gateway :8000, documents :8001, geometry :8002 — the smoke/e2e
  defaults), after the create_all above:
  ```bash
  uv run uvicorn geometry.main:app  --host 127.0.0.1 --port 8002 --workers 1 &
  POSTGRES_URL="$DOC_DSN" uv run uvicorn documents.main:app --host 127.0.0.1 --port 8001 &
  LOFT_ENV=dev POSTGRES_URL="$GW_DSN" GEOMETRY_URL=http://127.0.0.1:8002 \
    DOCUMENTS_URL=http://127.0.0.1:8001 \
    uv run uvicorn gateway.main:app --host 127.0.0.1 --port 8000 &
  scripts/smoke-healthz.sh 8000   # all three /healthz+/readyz → 200
  ```
  `LOFT_ENV=dev` is required (the gateway fail-closes on JWT posture otherwise).
  Then Vite: Playwright's `webServer` boots it itself (`reuseExistingServer`),
  so just run the specs — the Vite `/api` proxy defaults to `:8000`; set
  `GATEWAY_ORIGIN=http://127.0.0.1:8000` explicitly to be safe. Founder
  screenshots: `UPDATE_SCREENSHOTS=1 PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
  pnpm --filter @loft/web exec playwright test e2e/<spec>.ts`. This is how the
  UR3 / units / mate / drawings founder shots under `docs/screenshots/` were
  captured natively (2026-07-18) — **e2e + screenshots are NOT CI-only.**
  Runnable gates here therefore include the full Playwright e2e, not just
  `pnpm --filter @loft/web {typecheck,test}` + `just lint` + geometry `pytest`.
  (Only `just dev` / `docker compose` proper — which build the container images —
  still can't run; use the native boot above instead of the compose stack.)

<a id="no-background-stack"></a>

### Never boot the stack with `Bash(run_in_background)`

*Moved verbatim from `CLAUDE.md` lines 1783–1794 on 2026-09-23. Current rule: PROTOCOL.md §7.*

- **DO NOT BOOT THE NATIVE STACK WITH `Bash(run_in_background)` — it dies, and it
  dies wearing the readonly-SQLite mask.** Found 2026-08-28 by the ORTHO-1 agent.
  `uv run uvicorn` produces a second bind attempt that exits 3; the harness reads
  that as the task failing, and reaps the **surviving** listener along with it. The
  symptom is all three services answering 200 one minute and **000** the next,
  which is exactly what the stale-handle fault above looks like — so you will
  "fix" it by restarting, get another ten minutes, and lose the same time again.
  Use `setsid nohup … < /dev/null &` from a script, with a health-poll loop; that
  survives across tool calls. This is now the FOURTH distinct fault presenting as
  "my stack was up and now it is not" (stale handle, a sibling's `rm -f`, a
  sibling's un-scoped teardown, and this), so when a healthy stack goes silent,
  identify WHICH before acting — they have four different fixes.

<a id="readonly-sqlite"></a>

### `attempt to write a readonly database`: stale handle or deleted file

*Moved verbatim from `CLAUDE.md` lines 1795–1815 on 2026-09-23. Current rule: PROTOCOL.md §7.*

- **A long-running native uvicorn on a scratchpad SQLite file starts returning
  `attempt to write a readonly database` after ~10 minutes, and it reads exactly
  like a code regression.** Symptom: register -> 500, every spec dies at
  `seedSession`, while a FRESH process writes the same file fine. Nothing in the
  app changed; the long-lived connection's handle goes bad. Restarting the three
  services clears it, so bounce them before each e2e leg rather than debugging the
  500 — an agent lost time to this on 2026-07-30 chasing a phantom regression.
  **AND THE SAME 500 HAS A SECOND CAUSE UNDER PARALLELISM: a sibling deleted your
  database. PREFIX SCRATCHPAD DB FILENAMES PER AGENT.** The session scratchpad is
  SHARED, so `$SP/documents.db` / `$SP/gateway.db` are the obvious names for
  everyone — and the boot recipe says to `rm -f` them first, because `create_all`
  does not migrate. So agent B's perfectly correct "start from fresh files" step
  unlinks the file agent A's live uvicorns are holding open, and A's gateway
  returns `attempt to write a readonly database` from then on (deleted inode,
  still-open handle). Measured 2026-08-02 with four agents live: isolating the
  PORTS is not enough, the DATABASE PATH has to be isolated too. Use
  `$SP/<slug>-documents.db` / `$SP/<slug>-gateway.db` and `rm -f` ONLY your own
  prefix — never an unprefixed file, which may be someone's live stack. Note the
  symptom is identical to the stale-handle case above and to the stale-Vite case,
  so before diagnosing a 500 at register, restart YOUR stack on YOUR own files and
  re-run; three separate environment faults wear the same mask.

<a id="pytest-verdict-last"></a>

### Put the pytest verdict in `pytest_unconfigure`

*Moved verbatim from `CLAUDE.md` lines 1816–1831 on 2026-09-23. Current rule: CLAUDE.md → Environment recipes.*

- **`pytest_terminal_summary` RUNS BEFORE THE SHORT TEST SUMMARY, so a verdict
  written there lands in the MIDDLE of the log — use `pytest_unconfigure`.**
  Measured 2026-08-28 by the PGTEST-GATE agent, and it is the THIRD instance of
  one pattern this week: **whatever a job writes LAST is its only interface,
  because the log tail is the only channel** (the e2e shard verdict, the pytest
  verdict, and `scripts/e2e.sh`'s service dump are all the same lesson). The
  mechanism here has a second half worth knowing: when a SESSION-SCOPED FIXTURE
  fails, pytest repeats its reason once per dependent test, so a 4-line failure
  reason across 172 tests produced a **1563-line log with the verdict at line
  870** — no fixed `tail_lines` could reach it. Fixed by making the reason ONE
  line and moving the verdict to `pytest_unconfigure`, which runs after the
  reporter's final stats line: **532 lines, verdict last, `tail -6` gets the
  whole answer.** Related, same measurement: a `pytest_report_header` in a
  SUBDIRECTORY conftest never fires on a whole-repo run — it is not an initial
  conftest — while `pytest_unconfigure` and `pytest_terminal_summary` both do,
  because the conftest is registered by collection time.

<a id="pytest-qq"></a>

### `-q` twice deletes the summary line

*Moved verbatim from `CLAUDE.md` lines 1832–1836 on 2026-09-23. Current rule: CLAUDE.md → Environment recipes.*

- **`pytest -q` ON THE CLI PLUS `-q` IN `addopts` MAKES `-qq`, WHICH SILENTLY
  DELETES THE PASS/FAIL SUMMARY LINE.** The dot-line still prints, so the run
  looks complete and the count is simply gone — a green-shaped output with no
  number in it. Same family as the zero-byte 200: the shape of success survives
  while the content that makes it checkable does not.

<a id="conftest-env-leak"></a>

### A conftest env var leaks across services

*Moved verbatim from `CLAUDE.md` lines 1860–1871 on 2026-09-23. Current rule: CLAUDE.md → Environment recipes.*

- **A `conftest.py` env var leaks ACROSS services, because pytest collects every
  conftest before running any test.** `services/gateway/tests/conftest.py` does
  `os.environ.setdefault("LOFT_ENV", "dev")` so the gateway suite can build
  settings; in a whole-repo `uv run pytest` that dev posture is therefore already
  in `os.environ` when the documents and geometry suites run. The failure mode is
  the nasty direction: a test asserting a NON-dev behaviour (e.g. that the
  datastore-credential guard refuses to boot) passes when its file is run alone
  and fails in the full sweep — or worse, a test asserting the dev-allow path
  passes in the sweep for the wrong reason. Any test whose subject depends on
  `LOFT_ENV` (or any other conftest-seeded variable) must `monkeypatch.delenv`
  / `monkeypatch.setenv` EXPLICITLY rather than inherit, and should assert the
  non-dev case by name. Found 2026-07-30 while landing the fail-closed guard.

<a id="stale-uvicorns"></a>

### Stale dev uvicorns poison `just e2e` (original grep recipe)

*Moved verbatim from `CLAUDE.md` lines 1872–1882 on 2026-09-23. Current rule: CLAUDE.md → Environment recipes.*

- **Stale dev uvicorns poison `just e2e`.** Long-lived service uvicorns (from a
  prior `just dev` or an agent that booted the stack) run **without**
  `--reload`, so after any backend commit their served OpenAPI/routes go stale.
  `just e2e` (and `just smoke`) **reuse healthy listeners** on :8000/:8001/:8002
  rather than rebooting, so a batch-end e2e will 404 on newly-added routes and
  fail specs that are actually green against HEAD. Before a batch-end `just
  e2e`, kill lingering `*.main:app` uvicorns:
  `ps -eo pid,args | grep -E '(gateway|geometry|documents)\.main:app' | grep -v grep`
  then `kill` those pids (parents + children) so the suite reboots from current
  code. Agents that need a stack mid-run should boot **isolated** ports (e.g.
  :8010/:8012) and tear them down, leaving the shared stack untouched.

<a id="pnpm-dashdash"></a>

### `pnpm run <script> -- <args>` drops the `--`

*Moved verbatim from `CLAUDE.md` lines 1883–1896 on 2026-09-23. Current rule: PROTOCOL.md §7.*

- **`pnpm run <script> -- <args>` DROPS the `--` in pnpm 10, so the args never
  reach the script — and this is the GENERATOR of the stale-Vite trap below.**
  Measured on pnpm 10.33.0: `pnpm --filter @loft/web dev -- --port 5199` starts
  Vite on **5173** with no error, while `dev --port 5199` and `exec vite --port
  5199` both bind correctly. The `--` separator is npm-idiomatic, so the failure
  is produced by CORRECT muscle memory and reported by nothing. The invocation an
  agent reaches for to boot an ISOLATED frontend is therefore the one that
  silently takes the SHARED port; `reuseExistingServer: true` then hands that
  stray 5173 to the next `just e2e`, whose specs all 500 at `seedSession` against
  a torn-down gateway and read as a code regression. Never write `--`; always
  confirm the port Vite actually printed. Half of this is now closed in code:
  `apps/web/vite.config.ts` sets `server.strictPort`, so a Vite that cannot take
  the port it was given FAILS instead of falling back to 5173. The swallowed
  argument is still silent — that part only discipline fixes.

<a id="scratchpad-inspect"></a>

### The shared scratchpad holds a stdlib-shadowing `inspect.py`

*Moved verbatim from `CLAUDE.md` lines 1897–1910 on 2026-09-23. Current rule: PROTOCOL.md §1.*

- **THE SESSION SCRATCHPAD IS SHARED, AND IT CONTAINS A STDLIB-SHADOWING
  `inspect.py` — running `python <scratchpad>/x.py` breaks every import and reads
  like a broken venv.** Reported 2026-08-29 by the STEPDET-1 agent and verified
  by me: the file is really there. Python puts the SCRIPT'S OWN DIRECTORY on
  `sys.path[0]`, so a throwaway script run from the scratchpad root shadows the
  stdlib `inspect` for everything it imports, and the failure surfaces far from
  the cause — `module 'inspect' has no attribute 'signature'` out of some
  unrelated library's import. The natural diagnosis is "the shared `.venv` is
  broken", which is expensive and wrong, and the natural next step (rebuilding
  it) would break every sibling agent. **Work in a per-agent subdirectory**
  (`$SCRATCHPAD/<slug>/`), which you should be doing anyway — the scratchpad is
  shared, so an unprefixed filename is a collision waiting to happen, exactly as
  it is for the SQLite DB files. Any stdlib name is a hazard here, not just this
  one; `inspect.py` is simply the one somebody has already left behind.

<a id="test-results-wiped"></a>

### Playwright wipes `apps/web/test-results/`

*Moved verbatim from `CLAUDE.md` lines 1911–1926 on 2026-09-23. Current rule: CLAUDE.md → Environment recipes.*

- **`apps/web/test-results/` LOOKS like the ideal scratch directory and Playwright
  WIPES IT at the start of every run — including your live SQLite files.** It is
  gitignored AND prettier-ignored AND inside the linted tree, which is exactly the
  combination an agent needing a throwaway config hunts for, so this is a trap
  correct reasoning walks into. Cost a restart on 2026-08-15: an isolated
  Playwright config and two SQLite DBs were placed there, the first run deleted
  them mid-flight, and the unlinked-inode DBs produced precisely the
  `attempt to write a readonly database` / "500 at create-part" mask the recipes
  above describe — i.e. it wears the same costume as three other faults. Two more
  traps in the same corner, both measured: **Node refuses to type-strip a `.ts`
  Playwright config located under `node_modules/`**, so an isolated config there
  must be `.mjs`; and **`apps/web/playwright.config.ts` hardcodes
  `baseURL: 5173` with no env override**, so running against an isolated Vite port
  needs a whole separate config file, not a flag. The working recipe, which
  survives all three: `apps/web/node_modules/.vp1a/<name>.config.mjs` — gitignored
  via `node_modules`, eslint-ignored via `**/node_modules/**`, and not wiped.

<a id="stale-vite-teardown"></a>

### A stale Vite on :5173, and the three wrong teardown recipes

*Moved verbatim from `CLAUDE.md` lines 1927–1986 on 2026-09-23. Current rule: PROTOCOL.md §7.*

- **A stale Vite on :5173 poisons `just e2e` worse than a stale uvicorn — every
  spec 500s at register.** `apps/web/playwright.config.ts` sets
  `reuseExistingServer: true` (so e2e composes with a running `just dev`), and
  the Vite `/api` proxy targets `GATEWAY_ORIGIN ?? http://127.0.0.1:8000`
  (`apps/web/vite.config.ts`). An agent that booted an **isolated** frontend
  (its own Vite on :5173 with `GATEWAY_ORIGIN=http://127.0.0.1:8010`) and tore
  down its :8010 gateway but **left the Vite process running** leaves a
  :5173 whose proxy now points at a DEAD gateway. A later shared `just e2e`
  *reuses that stale Vite* → `/api/v1/auth/register` proxies to nothing →
  **500**, and since every spec's `seedSession` registers first, the WHOLE
  suite fails ("e2e register failed: 500", ~157 failed / 2 passed) while
  leg-1 geometry gates pass and a direct curl to the real :8000 gateway
  returns 201. Symptom ≠ code regression. **Before a batch-end `just e2e`,
  also kill a stale Vite — but SCOPE THE KILL TO PORT 5173.** Resolve the pid
  from the listener, never from a process-name grep:
  ```bash
  pid=$(lsof -ti tcp:5173 -sTCP:LISTEN 2>/dev/null)
  [ -n "$pid" ] && kill $pid        # ONLY the process LISTENING on :5173
  ```
  **CORRECTED 2026-09-23 — the version above this said `lsof -ti :5173 | head -1`,
  and that kills the wrong process.** `lsof -ti :PORT` returns every process
  with a socket on the port, CLIENTS included. Measured with a control: a
  listener and a separate client connected to it, `lsof -ti :PORT` -> both pids,
  `lsof -ti tcp:PORT -sTCP:LISTEN` -> the listener only. With `head -1` the one
  you kill depends on ordering — and our gateway holds sockets to documents, so
  tearing down documents' port could kill the GATEWAY and leave documents
  running on a deleted database file, which surfaces as `attempt to write a
  readonly database`: the same mask as three other faults in this file. Found by
  the hole-editor agent, which hit it.
  **This is the THIRD wrong version of this one recipe** — a process-name grep
  (killed every agent's Vite), then `ss` (silently killed nothing), then this
  (can kill a neighbour). Each was plausible and none was tested against the
  case that breaks it. A teardown recipe needs a control that includes a
  process it must NOT kill, not only one it must.
  **USE `lsof -ti`, NOT `ss`. `ss -lptn` RESOLVES NOTHING IN THIS CONTAINER** — it
  prints no row at all for a listener the calling shell owns, so a teardown built
  on it **silently no-ops** and reads exactly like a clean teardown while every
  service is still running. Found 2026-08-27 by the REACH-ORDER agent, and it is
  my error twice over on the same recipe: the first version was a process-name
  grep that killed every agent's Vite, and the "fix" was this inert one. Measured
  against a real listener on :5399 — `ss -lptn` → nothing, `ss -ltn` → nothing,
  `lsof -ti` → the pid, `fuser <port>/tcp` → the pid. A `/proc/net/tcp` inode scan
  also works if neither binary is present. **The general rule: a teardown recipe
  is a claim about this container, so verify it against a real listener before
  writing it down.** Both of my versions were plausible and neither was tested;
  one over-killed and one under-killed, and the silent one is worse, because
  friendly fire at least announces itself.
  **THE EARLIER VERSION OF THIS RECIPE SAID `ps -eo pid,args | grep -E
  'vite/bin/vite'`, WHICH IS NOT PORT-SCOPED AND KILLS EVERY AGENT'S VITE.**
  Measured 2026-08-27 by the QA-R4 agent: every e2e leg it ran over ~10 minutes
  collapsed mid-run, twice with the signature of a murdered process rather than a
  crash — `ECONNREFUSED 127.0.0.1:5194` while its gateway still answered 200 (its
  Vite killed), then `gw=000` on a stack that had booted healthy minutes earlier
  (its uvicorns killed). Memory was fine throughout (12 GB free), so not OOM. The
  most likely cause is a sibling faithfully following this very recipe. A cleanup
  step that reaches outside its own ports is not cleanup, it is friendly fire, and
  it gets worse the more agents run — which is exactly when long legs matter most.
  Same rule for uvicorns: match on the port you booted, not on `*.main:app`.
  Agents booting an isolated frontend MUST kill their Vite in teardown, not just
  their uvicorns — and MUST kill only their own.

<a id="vite-stale-transform"></a>

### Vite can serve a stale transform of a workspace package

*Moved verbatim from `CLAUDE.md` lines 1987–2005 on 2026-09-23. Current rule: PROTOCOL.md §7.*

- **VITE CAN SERVE A STALE TRANSFORM OF A WORKSPACE PACKAGE, WHICH MAKES A
  MUTATION CHECK PASS WHEN IT MUST HAVE FAILED — the worst failure in this whole
  family, because it corrupts the EVIDENCE rather than the run.** Found
  2026-08-28 by the A11Y-TOOLBTN-1 agent. It edited
  `packages/design/src/primitives/ToolButton.tsx` under a running Vite,
  reintroduced the original defect to prove its new e2e case could see it, and
  the case went **GREEN** — the fix appeared to be unnecessary. `curl` of the
  served module showed the OLD condition while disk had the new one; only
  bouncing Vite made served bytes match disk, and the case then reddened as it
  should. **Every other trap in this file costs you a run; this one costs you a
  wrong conclusion, and the conclusion is "my test is fine" or "this fix does
  nothing".** Note this is the QUIET half of the stale-Vite entry below: that one
  is a stale PROXY TARGET and it is loud (every spec 500s at register), whereas
  this is a stale TRANSFORM of a linked workspace package and everything looks
  normal. Rule: **when mutation-testing a `packages/**` primitive through the
  browser, restart Vite between legs and verify the SERVED bytes**, e.g.
  `curl -s http://127.0.0.1:<port>/@fs<abs path> | grep <the line you changed>`.
  A mutation that does not redden is a claim about the served bundle until you
  have checked which bytes it was.

<a id="tailwind-preset-restart"></a>

### A Tailwind preset change needs a Vite restart

*Moved verbatim from `CLAUDE.md` lines 2006–2026 on 2026-09-23. Current rule: PROTOCOL.md §7.*

- **A TAILWIND PRESET CHANGE IS A BUILD-CONFIG CHANGE, NOT A SOURCE CHANGE — a
  running Vite will not pick it up, and the symptom is "your new feature is
  broken", never a build error.** Measured 2026-08-17 recovering VIEWCUBE-1.
  `packages/design/src/tailwind-preset.ts` gained `h-view-cube` /
  `bottom-view-cube` utilities in the same change that used them. Against a Vite
  started BEFORE the patch, those classes did not exist, so the host `div` had
  no width, height or seat — and its child `<canvas>` fell back to the HTML
  DEFAULT of **300x150 at the top-left**. The e2e probe therefore reported a
  cube of the wrong size in the wrong corner, which reads exactly like a
  half-finished component. I was one step from rewriting work that was already
  correct; after killing Vite the same bytes measured **108x108 at (1130, 602)**
  on a 1280x800 frame with every facet click steering the camera.
  Two things generalise. (a) **`300x150` is a fingerprint, not a measurement** —
  it is the intrinsic size of a `<canvas>` with no CSS size, so any element
  reporting it is un-styled rather than mis-styled, and the question is why the
  CSS is missing, not what the component did wrong. (b) The stale-Vite entry
  above is about a stale PROXY TARGET (every spec 500s at register, loud and
  obvious). This is the quieter half: a stale *config* yields a page that loads,
  renders and lies. **Restart Vite after touching `tailwind-preset.ts`,
  `tokens.ts`, `vite.config.ts`, or anything else Vite reads once at boot** —
  the same reflex as regenerating contracts after a pydantic change.

<a id="lint-gate"></a>

### `just lint` is the lint gate

*Moved verbatim from `CLAUDE.md` lines 2174–2190 on 2026-09-23. Current rule: PROTOCOL.md §6.*

- **`ruff check` + `pyright` is NOT the lint gate — `just lint` is.** CI
  (`.github/workflows/ci.yml`) runs `uv run ruff format --check .` AND
  `prettier --check .` (via `just lint`), and `ruff` is lock-pinned (uv.lock →
  0.15.20; `pyproject` floor `>=0.12` is a red herring — `uv run ruff` uses the
  locked version, the same one CI's `uv sync --locked` installs, so a local
  `ruff format --check` failure is NEVER "version skew," it's a real red build).
  A per-slice gate of only `ruff check`/`pyright`/`gen-check`/`web typecheck`
  passes while `ruff format`- and prettier-dirty files accumulate — then the
  batch-boundary `just lint` goes red (seen 2026-07-19: 4 `ruff format`-dirty
  py files + **12 prettier-dirty `goldens-sheet-metal/*.json`** slipped through
  ~10 green-looking slice commits). **Two rules: (1) every slice agent runs the
  full `just lint` before committing, not just `ruff check`; (2) newly-committed
  golden JSON (and any JSON/MD/YAML) must pass `prettier --check` — the test
  harness parses goldens as JSON (whitespace-insensitive) so a stored content
  hash is a string field unaffected by formatting, i.e. `prettier --write` on a
  golden is behaviour-neutral and safe.** Always run the full `just lint` at the
  batch boundary regardless.

<a id="gen-verify"></a>

### `just gen` reads the working tree; untracked files fail prettier; bare ruff

*Moved verbatim from `CLAUDE.md` lines 2191–2245 on 2026-09-23. Current rule: PROTOCOL.md §6.*

- **`just gen` reads the WORKING TREE, so in a shared tree it silently bakes
  another agent's uncommitted schema into YOUR commit — and `gen-check` cannot
  see it, by construction.** `scripts/gen-contracts.py` imports the live source,
  so the generator's input is whatever is on disk. `gen-check` then regenerates
  *the same way* and diffs against the committed JSON, i.e. it asks "do the
  committed contracts match the working tree?" when the standing rule needs "do
  they match the committed SOURCE?" Those coincide for a single developer and
  come apart exactly when several agents are editing schemas at once. Seen
  2026-07-31: an agent's `just gen` captured a sibling's uncommitted gateway
  duplicate-route work, so its commit carried `gateway.openapi.json` +
  `gateway/schema.ts` describing routes with no committed source — gen-check-RED
  in CI on that commit, while passing locally. It was caught by hand and
  force-pushed over. The tempdir in `gen-check.sh` protects the tree from being
  DIRTIED; it never made the INPUT clean, which is the property that matters.
  **Fix, shipped the same day: `just gen-verify` (`scripts/gen-check.sh
  --from-index`)** materialises the git INDEX — the tree `git commit` would
  write — into a throwaway worktree and generates there, so it answers "will CI
  be green on my commit". Verified against the real defect rather than asserted:
  with a schema change present only in the working tree and only the generated
  output staged, the default mode exits **0** (blessing a commit CI rejects) and
  `--from-index` exits **1** naming the leaked field. Run `just gen-verify`, not
  `just gen-check`, before committing anything that touches a pydantic model
  while other agents are live. CI itself is unaffected — it checks out a clean
  tree, so there index == HEAD == worktree and the default mode is already right.
  The general lesson is the one this repo keeps relearning: **a gate is only as
  honest as its INPUT, and "it passed" tells you nothing until you know what it
  measured.** **(2b) `prettier --check .` walks the FILESYSTEM,
  not the index, so an UNTRACKED scratch file fails lint for every agent at
  once** — and `.prettierignore` covers `docs/`, `.claude/`, generated dirs and
  build output, but NOT the repo root. Seen 2026-07-30: an agent left a
  180-byte `eval1.json` (an evaluate-response dump) at the root; it never would
  have been committed, and it would still have turned the batch-end `just lint`
  red for everyone, looking like someone else's regression. Payload dumps,
  curl output and one-off fixtures go in the session scratchpad, never the repo
  root. When you find one that is another agent's, tell that agent — do not
  delete it; it may be in active use. **(2c) Some temp files CANNOT go in the
  scratchpad — those must be `prettier --write`-clean before you walk away from
  them.** `apps/web/playwright.config.ts` sets `testDir: "./e2e"`, so a throwaway
  spec has to live inside `apps/web/e2e/` to be discovered at all; the scratchpad
  is not an option, and `.prettierignore` does not cover that directory. Seen
  2026-07-31: the orchestrator wrote a temporary founder-capture spec there,
  deleted it minutes later, and in the window between, a concurrent agent's
  `pnpm run lint` went red on formatting alone — a failure in nobody's diff, in a
  file that no longer exists by the time anyone looks. Rule: anything you must
  place inside a linted tree gets formatted the moment it is written, not when it
  is committed (it never will be), and gets deleted in the same turn.
  **(3) Lint with `uv run ruff …`, NEVER a
  bare PATH `ruff`.** Seen 2026-07-23 (interference slice `e46db16`): the agent ran a PATH
  `ruff check` that predated the `RUF002` confusable rule and reported "0 errors,"
  but the locked `uv run ruff check` (0.15.20) flagged 8× `RUF002` (a test file
  using U+00D7 `×`/U+2212 `−` glyphs — every other file uses ASCII `x`/`-`) + 1×
  `SIM300`, so HEAD shipped lint-red under a false "lint clean" claim (geometry-QA
  caught it). A bare `ruff` resolves to whatever's on PATH, which can be older than
  the lockfile; `uv run ruff` always uses the pinned 0.15.20 CI installs. Prefer
  ASCII in code/tests (`x`, `-`, `<=`) — reserve `×`/`−`/`≤` for docs/markdown.

<a id="scoped-gate"></a>

### Scope a gate to your whole diff

*Moved verbatim from `CLAUDE.md` lines 2246–2259 on 2026-09-23. Current rule: PROTOCOL.md §6.*

- **When a concurrent agent's unfinished work blocks a clean full `just lint`,
  scope your gate to your ENTIRE diff — every file you touched — not just the
  primary source file.** Cautionary tale (2026-07-23, overnight loop): a
  first-angle-projection slice (`822b3a9`) changed `bounds_aware_layout`'s
  signature in `compose.py` AND the call sites in `test_drawings_compose.py`,
  but — unable to run repo-wide `just lint` because a concurrent frontend agent
  had unfinished `apps/web` work — ran only scoped `pyright compose.py`. That
  passed; the signature change left 7 `pyright` errors in the TEST file
  (`dict[str, ViewBounds]` vs the new `dict[ViewProjection, ViewBounds | None]`),
  so HEAD shipped lint-red and a sibling agent caught it. A scoped gate is fine
  when the tree is dirty with foreign work, but scope it to `git diff --name-only`
  (your whole change), e.g. `uv run pyright <each changed .py>` + `ruff` on all
  of them — never just the one file you were "mainly" editing. A signature change
  breaks its callers and tests, which single-file scoping can't see.

<a id="tailwind-probe"></a>

### Compiling the real Tailwind against our preset from a scratch script

*Moved verbatim from `CLAUDE.md` lines 2260–2281 on 2026-09-23. Current rule: CLAUDE.md → Environment recipes.*

- **TO COMPILE THE REAL TAILWIND AGAINST OUR PRESET FROM A SCRATCH SCRIPT, the
  script must sit OUTSIDE `node_modules` with a `node_modules` SYMLINK beside
  it** — three separate resolution traps stack up and each one looks like the
  last. Measured 2026-08-28 while cross-checking `scripts/check-tailwind-scale.py`
  against the compiler. (a) `postcss` is not a dependency of `packages/design`
  and pnpm's strict layout means there is no root `node_modules/postcss` either;
  only `apps/web` has both `postcss` and `tailwindcss`. (b) `tailwindcss@3.4` has
  **no `exports` map**, so Node ESM cannot resolve the bare `tailwindcss/plugin`
  our preset imports — it needs the literal `tailwindcss/plugin.js`. (c) Node
  refuses to type-strip a `.ts` file under `node_modules/`
  (`ERR_UNSUPPORTED_NODE_MODULES_TYPE_STRIPPING`), so the obvious hiding place
  for a throwaway probe — the one the `apps/web/node_modules/.vp1a/` recipe above
  endorses for Playwright configs — cannot import the preset at all. What works:
  put the probe in the session scratchpad, `ln -s <repo>/apps/web/node_modules`
  next to it so bare specifiers resolve, and import the preset through a copy
  whose two specifiers are rewritten (`tailwindcss/plugin.js`, plus an absolute
  path to the REAL `tokens.ts` so the scale under test is the committed one).
  Node 22.22 then type-strips both `.ts` files and `postcss([tailwind({...})])`
  runs. Worth the setup: it turns "I think this family reads `spacing`" into a
  measurement — 2664 family x value pairs, 0 disagreements — and it is what
  removed `leading-` (reads `lineHeight`) and `z-` (extended, not replaced) from
  that gate's coverage before they could cry wolf.

---

## Prior wording of rules reworded in place

<a id="prior-design-standing-rules"></a>

### Design mandate standing rules 1–3a, original wording

*Moved verbatim from `CLAUDE.md` lines 152–177 on 2026-09-23. Current rule: CLAUDE.md → Design mandate.*

Standing rules:

1. **Always use the `frontend-design` skill** (`.claude/skills/frontend-design/`,
   vendored Anthropic skill). ANY UI work — new surface, component, or
   redesign — invokes it first: establish/extend the token system (palette /
   type / layout / **one signature element**), avoid the AI-default looks it
   names, spend boldness in one place, keep the rest disciplined.
2. **Design system first.** `packages/design` (tokens + primitives + fonts)
   is the single source of truth; screens compose primitives. Fix the
   primitive, never the instance (this is the DRY rule applied to design).
   Both renderers draw from it: Tailwind preset for the DOM, TS token
   constants for the WebGL viewport — one palette, two renderers.
3. **The viewport is the hero.** Chrome recedes; the model gets the pixels.
   Panels, trees, and toolbars are quiet precision instruments — dense,
   legible, keyboard-first — not marketing surfaces.
3a. **Tool-grade viewport, benchmarked against Fusion 360 / Plasticity**
   (founder recalibration 2026-07-16 — "premium dashboard" is NOT the bar;
   *feels like a modeling tool* is). Concretely: (a) the 3D scene fills the
   frame with depth — grid reads to the horizon (no mid-frame fade into flat
   void), background has atmosphere (gradient/fog/vignette), bodies get
   studio-quality shading (matcap/env — Plasticity's look), never debug-gray;
   (b) persistent view navigation: a ViewCube/gizmo + home/iso/ortho snaps
   is table stakes, not a feature; (c) **every chrome element is functional**
   — a tile/readout that only decorates is a defect; wire it or delete it;
   (d) judge screenshots side-by-side against a Fusion/Plasticity reference
   before calling UI work done.

<a id="prior-service-boundaries"></a>

### Service boundaries, original wording

*Moved verbatim from `CLAUDE.md` lines 252–258 on 2026-09-23. Current rule: CLAUDE.md → Service boundaries.*

**Service boundaries (enforced in review)**

- Only `services/geometry` imports OCP/build123d. No kernel types cross a
  service boundary — meshes/exports go to object storage, references by ID.
- `services/geometry` never touches Postgres; `services/documents` never
  imports the kernel; `apps/web` talks only to the gateway.
- **No GPL/AGPL dependencies** (MIT app; LGPL-dynamic ok — RESEARCH §8).

<a id="prior-commands-note"></a>

### Commands section note, original wording

*Moved verbatim from `CLAUDE.md` lines 277–277 on 2026-09-23. Current rule: CLAUDE.md → Commands.*

(Targets land with the monorepo scaffold; keep this section true as they do.)

<a id="prior-definition-of-done"></a>

### Definition of done, original wording

*Moved verbatim from `CLAUDE.md` lines 330–335 on 2026-09-23. Current rule: CLAUDE.md → Definition of done.*

- **Definition of done for ANY change** = builds + lint/typecheck + unit
  tests green + geometry gates green (when kernel-adjacent) + e2e green (when
  user-facing) + ROADMAP/BACKLOG ticked + committed & pushed + **CI green on
  the pushed commit**. For new capabilities: scripting/MCP exposure where
  sensible (or an explicit "not agent-appropriate" note) once Phase 5 lands
  the surface.

<a id="prior-dev-team"></a>

### Work as a dev team, original wording

*Moved verbatim from `CLAUDE.md` lines 743–776 on 2026-09-23. Current rule: CLAUDE.md → Work as a dev team.*

**Work as a dev team**

**ORCHESTRATOR: READ [`.claude/ORCHESTRATOR.md`](./.claude/ORCHESTRATOR.md)
FIRST, EVERY SESSION.** It is the playbook you follow — what is yours, what
belongs to an agent, the audit -> groom -> build -> integrate loop, and the
anti-patterns with the evidence that earned them. The short version: you
dispatch and integrate; you do not write the board, run the audits, or build.

Built by a **team of specialized AI agents**, not one generalist. Default to
delegating. The tooling lives in [`.claude/`](./.claude/README.md).

**Builders:** `kernel-architect` (geometry service, kernel layer, solver),
`backend-builder` (gateway/documents, py-kit), `frontend-builder` (web app,
viewport), `platform-builder` (Docker/compose/CI/Helm, contract pipeline).

**Quality (independent of whoever wrote the code):** `code-reviewer`,
`qa-tester` (Playwright, real stack, desktop + touch), `geometry-qa` (golden
models, round-trips, benchmarks → `docs/GEOMETRY-QA.md`), `frontend-qa`
(design/a11y/consistency → `docs/UI-REVIEW.md`).

**Direction (read-only on app code):** `product-auditor` +
`engineering-auditor` (independent, don't coordinate), `backlog-groomer`,
`vision-steward`, `doc-syncer` (cheap-model doc reconciler, every iteration),
`oss-curator` (README/community surface, truth-only).

**The loop for every feature:** plan → implement (specialist) → review
(`code-reviewer`) → QA (`qa-tester`; `geometry-qa` when kernel-adjacent;
`frontend-qa` spot-check) → tick ROADMAP/BACKLOG → commit. Workflows in
`.claude/workflows/` orchestrate this; `autonomous-dev-loop` chains batches
on completion. There is no cron and no watchdog — see `docs/LOOP-MECHANISMS.md`
for what wakes the loop and what each mechanism survives.

**Multi-agent orchestration protocol**

<a id="prior-territories"></a>

### File territories, original wording

*Moved verbatim from `CLAUDE.md` lines 811–814 on 2026-09-23. Current rule: CLAUDE.md → Orchestration rules.*

- **File territories.** Parallel agents get explicitly disjoint territories in
  their briefs (e.g. one holds `services/geometry/**`, another `apps/web/**`).
  Never edit, revert, or commit another agent's in-flight files. Foreign
  uncommitted work in shared files: build alongside, stage only your hunks.

<a id="prior-token-economy"></a>

### Token economy, original wording

*Moved verbatim from `CLAUDE.md` lines 1062–1085 on 2026-09-23. Current rule: CLAUDE.md → Token economy.*

**Token economy (founder priority 2026-07-10 — quality-neutral savings only)**

Usage-limit interruptions cost more than they save; spend tokens where
quality lives (builders, reviewers, geometry QA) and trim everywhere else:

- **Model tiers:** direction/docs roles (groomer, vision-steward,
  oss-curator: `model: sonnet`; doc-syncer: `haiku`) — builders, reviewers,
  and QA stay on the strong default. Never downgrade a role whose output
  gates correctness or security.
- **Lean briefs:** orchestrator briefs point at the BACKLOG item's acceptance
  criteria instead of restating them; only deltas, environment facts, and
  territory go in the brief.
- **Scoped reading:** agents read the doc *sections* they need (e.g.
  RESEARCH §N named in the brief), not every direction doc end-to-end.
- **Targeted verification:** the orchestrator re-runs a *targeted slice* of a
  completed agent's gates (the protocol's wording — not the full suite);
  the full sweep (`just lint && just test && just e2e`) runs once per batch
  end, not per item.
- **Lean shared docs:** files every agent reads must stay small. BACKLOG
  changelog entries ≤3 lines; groomer prunes older entries into CHANGELOG.md
  each pass; Done archives get collapsed to one line per item after a phase
  closes.
- **Right-size reports:** agent return reports carry evidence tails and
  decisions, not narration. Screenshots > prose for UI evidence.

<a id="prior-session-start"></a>

### Orchestrator session start, original wording

*Moved verbatim from `.claude/ORCHESTRATOR.md` lines 125–140 on 2026-09-23. Current rule: ORCHESTRATOR.md §1.*

**1. Session start**

1. `date -u`, `git log -1 --format=%ci`, `git status --short`, `git log --oneline -5`.
2. Read `docs/RETRO.md` — the loop's own memory, including every way it has
   broken. Then this file's §5.
3. **Check for a dead agent.** The old tell was "last commit is old AND the
   tree is dirty" — that breaks under worktrees, because the main tree stays
   clean and the work sits in `.claude/worktrees/*` (now gitignored, so it does
   not even show as untracked). Check all three: `git worktree list`, then
   `git -C <each worktree> status --short`, then in-flight agents' output
   mtimes. Anything stale beyond ~30 min with no known long gate is a death.
   You are its relauncher: judge the work, run the gates yourself, and commit it
   with honest provenance stating whether Review and Verify ran.
   **Never revert or discard it** — including the worktree.
4. Read CI for any pushed SHA without a verdict. Fix red before starting new work.

<a id="prior-loop-phases"></a>

### Audit / Groom / Build phases, original wording

*Moved verbatim from `.claude/ORCHESTRATOR.md` lines 166–175 on 2026-09-23. Current rule: ORCHESTRATOR.md §2.*

- **Audit** — `product-auditor` + `engineering-auditor` in parallel, independent,
  appending to their own docs as they go (write-early: we have lost two agents'
  entire reports to session limits). Roughly every third batch; the board does
  not need refreshing every time.
- **Groom** — `backlog-groomer` refreshes the Ready queue and returns the top
  N **disjoint** items, each with `{id, title, ticket, agentType, territory}`.
- **Build** — one agent per item, each with **`isolation: 'worktree'`**, owning
  the slice end to end: implement, self-review, QA, commit-if-green, leave it on
  its branch. N≈2–4.

<a id="prior-integrate"></a>

### Integrate phase, original wording

*Moved verbatim from `.claude/ORCHESTRATOR.md` lines 192–194 on 2026-09-23. Current rule: ORCHESTRATOR.md §2.*

- **Integrate** — yours. Merge each green branch, verify the merged tree
  (typecheck + unit + targeted gates), push, read CI, then launch the next batch.

<a id="prior-rules-that-survive"></a>

### Short rules that survive contact, original wording

*Moved verbatim from `.claude/ORCHESTRATOR.md` lines 274–286 on 2026-09-23. Current rule: ORCHESTRATOR.md §4.*

- **Never push a red build.** Verify before pushing, not after.
- **Push each commit separately** — GitHub fires one run per push *event*, so
  commits batched into one push get no individual CI run.
- **Doc edits are the LAST step**, staged and committed in the same turn. Never
  leave `ROADMAP`/`BACKLOG` edits unstaged across other tool calls.
- **Read `git diff --cached` in full** before every commit. Not `--name-only`.
- **A dead agent's work is preserved and reconciled, never reverted.**
- **Verify before trusting**: re-run a targeted slice of a completed agent's
  gates before reporting its work done.
- **Kill what you start.** Stray uvicorns and a stray Vite on :5173 silently
  poison every later e2e run and read exactly like a code regression.
- **Founder updates are results-first**: what shipped with evidence, then what is
  running, then what is next.
