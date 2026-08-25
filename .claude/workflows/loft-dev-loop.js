export const meta = {
  name: 'loft-dev-loop',
  description:
    'Audit -> groom -> build/review/verify N disjoint items in worktrees. The org loop, not the orchestrator doing it by hand.',
  whenToUse:
    'The standard loop. Runs ONE batch and returns. Chain batches on completion; there is no cron.',
  phases: [
    { title: 'Discover' },
    { title: 'Audit' },
    { title: 'Groom' },
    { title: 'Build' },
    { title: 'Review' },
    { title: 'Verify' },
    { title: 'DocSync' },
    { title: 'Integrate' },
  ],
}

// ---------------------------------------------------------------------------
// WHY THIS EXISTS, stated bluntly because the previous version got it wrong.
//
// Founder, 2026-08-14: "none of the agents are being used in the project. You
// are constantly over writing files and then wasting tokens trying to fix and
// racing before the next cron job kicks off."
//
// Checked, and true. Of the fourteen agents in .claude/agents/, EIGHT had never
// been invoked: backlog-groomer, product-auditor, engineering-auditor,
// vision-steward, doc-syncer, oss-curator, platform-builder, geometry-qa.
// The orchestrator had been writing docs/BACKLOG.md ITSELF — "file QA7-1",
// "file REV-1..REV-5", "file CI-4" are all orchestrator commits. That is the
// backlog-groomer's whole job, performed in the most expensive context in the
// system. Overwrites, wasted tokens and racing all follow from that one
// substitution.
//
// TWO CHANGES ON 2026-08-14, both from measurement, both load-bearing:
//
// 1. REVIEW AND VERIFY ARE IN THE LOOP. They were not, and the engineering
//    audit's K8 measured the consequence: three of the last five commits landed
//    with no code review and no QA pass, disclosed only in the commit message —
//    not in ROADMAP or BACKLOG, where the groomer reads. A build-only loop
//    cannot produce reviewed work no matter how good the builders are.
//    Structured as a PIPELINE, not barriered stages: item A's review starts the
//    moment A's build lands, while B is still building.
//
// 2. BUILDERS COMMIT CODE ONLY. The previous version told every builder to tick
//    docs/ROADMAP.md and docs/BACKLOG.md as its last act — which puts every
//    worktree back in contention over exactly the two files the whole collision
//    protocol exists for, undoing the isolation this script just bought. The
//    same-commit rule is still kept: the orchestrator folds the tick in at
//    integration (cherry-pick -> write the tick -> commit --amend --no-edit).
//    Measured working on SKETCH-1 (30a9f3f) and VP-1 (43c703c).
// ---------------------------------------------------------------------------

const READY = {
  type: 'object',
  additionalProperties: false,
  properties: {
    items: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        properties: {
          id: { type: 'string' },
          title: { type: 'string' },
          ticket: { type: 'string' },
          agentType: {
            type: 'string',
            enum: ['kernel-architect', 'backend-builder', 'frontend-builder', 'platform-builder'],
          },
          territory: { type: 'string' },
          kind: {
            type: 'string',
            enum: ['defect', 'capability'],
            description:
              'defect = something is broken. capability = the product cannot do it at all. ' +
              'Forced so a batch cannot be silently all-defect: the loop shipped 4 feat ' +
              'commits in 45 and every one was a defect repair before anyone noticed.',
          },
        },
        required: ['id', 'title', 'ticket', 'agentType', 'territory', 'kind'],
      },
    },
    ratio: {
      type: 'string',
      description:
        'MEASURED feat/fix split of the last 30 commits, plus the defect/capability split ' +
        'of the batch you are returning. The script cannot run git; you can. This is the ' +
        'instrument that makes convergence-on-repair visible every batch.',
    },
  },
  required: ['items', 'ratio'],
}

const BUILT = {
  type: 'object',
  additionalProperties: false,
  required: ['id', 'shipped', 'branch', 'shas', 'summary', 'gates', 'mutation', 'notDone'],
  properties: {
    id: { type: 'string' },
    shipped: { type: 'boolean' },
    branch: { type: 'string' },
    shas: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
    gates: { type: 'string' },
    mutation: { type: 'string' },
    notDone: { type: 'string' },
  },
}

const REVIEWED = {
  type: 'object',
  additionalProperties: false,
  required: ['blocking', 'findings'],
  properties: {
    blocking: { type: 'boolean' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['severity', 'file', 'summary'],
        properties: {
          severity: { type: 'string', enum: ['red', 'amber', 'green'] },
          file: { type: 'string' },
          line: { type: 'integer' },
          summary: { type: 'string' },
          evidence: { type: 'string' },
        },
      },
    },
  },
}

const VERIFIED = {
  type: 'object',
  additionalProperties: false,
  required: ['passed', 'evidence', 'failures'],
  properties: {
    passed: { type: 'boolean' },
    evidence: { type: 'string' },
    failures: { type: 'array', items: { type: 'string' } },
  },
}

const batchSize = (args && args.batchSize) || 3
const skipAudit = !!(args && args.skipAudit)
const skipDiscover = !!(args && args.skipDiscover)
const skipCurate = !!(args && args.skipCurate)

// BUILD SITS BEHIND FOUR OF THE MOST EXPENSIVE AGENTS IN THE SYSTEM, AND THAT
// IS WHY THE LOOP KEPT PRODUCING NO CODE (measured 2026-08-24, three runs).
//
// The founder said "make sure to follow the workflow", twice. I started it three
// times and got zero builders out of it, and misdiagnosed the Build phase as
// broken. Build is fine. It is simply never REACHED: Discover -> Audit ->
// Curate -> Groom are four sequential `await` barriers ahead of it — a
// vision-steward, two deep auditors and an oss-curator, each a multi-hundred-
// thousand-token run — and this container is reclaimed without warning. The
// journals say it plainly:
//   wf_5d45a0e8-a15: vision-steward result, product-auditor result,
//                    engineering-auditor STARTED WITH NO RESULT -> the
//                    `parallel()` barrier never resolved, run over.
//   wf_595d52cf-5e0: oss-curator started, no result, run over.
// Neither run ever evaluated a line of the Build phase.
//
// Two things follow, and the second is the one that generalises.
//
// (a) `seedItems` lets the orchestrator hand the batch straight in. `items`
//     used to come ONLY from the groomer's return value, so a groomer that died
//     — or was skipped — produced an empty batch and the early return below,
//     which reads in the log exactly like "the board is empty" rather than "the
//     agent that reads the board never came back". Same words, opposite cause.
//
// (b) A LONG PREFIX OF OPTIONAL EXPENSIVE WORK IN FRONT OF THE ONLY PHASE THAT
//     SHIPS is a design defect, not a scheduling detail. Every phase ahead of
//     Build must be individually skippable, and the caller that wants code this
//     hour must be able to say so. The direction layer is not optional in
//     GENERAL — it is the whole point of this file — but it is optional in any
//     GIVEN batch, and conflating those two costs a batch each time.
//
// Note the front half was not idle while it died: passes 4 and 5 of
// docs/AUDIT-PRODUCT.md and the engineering pass came out of these runs and had
// to be rescued by hand from the working tree. Write-early earned its keep
// again. But an audit nobody builds against is a report, not a loop.
const skipGroom = !!(args && args.skipGroom)
const seedItems = (args && Array.isArray(args.items) && args.items) || []

// Which verifier an item gets. `geometry-qa` owns golden models, STEP
// round-trips, solver determinism and benchmarks; CLAUDE.md says it runs
// "whenever kernel-adjacent code changes", and it had NEVER been spawned in 108
// subagent spawns — while GEOM-2 shipped a whole new face-matching tier and
// GEOM-3 rewrote the persisted face-signature contract. The kernel-architect was
// writing its own goldens, which is the QA'd-by-the-author arrangement this loop
// exists to end. Routing is by TERRITORY so nobody has to remember.
const KERNEL_PATHS = ['services/geometry', 'packages/py-kit', 'goldens', 'kernel']
const isKernelAdjacent = (it) =>
  KERNEL_PATHS.some((k) => String((it && it.territory) || '').includes(k))
const occupied = (args && args.occupiedTerritories) || []
const branch = (args && args.branch) || 'claude/branch-review-development-hkbbnb'

const STANDARD = `
HOW THIS REPO JUDGES WORK:
* An assertion never SEEN to fail is not a gate. For any gate you add or change,
  build the mutation that should redden it, RUN it, quote the red output, revert,
  confirm green. Four gates that could not fail have shipped here: a CI grep
  matching its own prose, a unit test whose helper did the cleanup it asserted,
  a self_test returning 0 with zero checks because all([]) is True, and a loop
  guard tested against a fixture built at the depth its own code expected.
* The NEGATIVE control is where the second bug lives, and it has to be sized to
  the failure — three fixture files let a broken probe pass where two thousand
  failed it every time.
* A claim that is not true is a defect, including in a comment. Every number you
  write must be one you measured, and an inherited claim must be re-derived
  before you repeat it.
* Flow is the product: judge by what the user does NEXT.

ENVIRONMENT: Docker's registry is blocked (403), so \`just dev\`/compose cannot
run — boot natively per CLAUDE.md (uvicorn + SQLite via metadata.create_all,
never alembic). Prefix your SQLite files per-ticket and rm -f only your own.
Never write \`pnpm run <script> -- <args>\` — pnpm 10 drops the \`--\` and Vite
silently takes :5173, which poisons every later e2e run. Kill everything you
start, INCLUDING Vite. \`just lint\` is the gate, not \`ruff check\`; use
\`uv run ruff\`, never a bare PATH ruff.
You CANNOT read CI (api.github.com is policy-denied for subagents) — commit,
stop, and the orchestrator relays failures back.
`

// --- Discover ---------------------------------------------------------------
// THIS PHASE DID NOT EXIST, AND WITHOUT IT THE LOOP COULD NOT SHIP A FEATURE.
// Measured 2026-08-16 after the founder asked "is our idea agent finding new
// ideas from plasticity and fusion? We are not progressing new features":
// across ~45 commits the split was 22 docs / 9 fix / 8 test / 4 feat / 2 ci, and
// all four feats were repairs of founder-reported defects. Every Ready item was
// a defect. VISION.md and COMPETITIVE.md had been untouched for 16 days, and
// `vision-steward` had NEVER been spawned — 38 spawns, zero of it.
//
// The cause is the loop's SHAPE: the auditors find what is BROKEN, the groomer
// curates from the auditors, the builders build the board. Nothing looked for
// what is ABSENT. A defect-repair machine converges on a well-repaired version
// of what it already is, and every individual batch looks productive while it
// happens. So this runs FIRST, ahead of the auditors, and its output is an
// input to the groom.
if (!skipDiscover) {
  phase('Discover')
  await agent(
    `Competitive discovery against **Fusion 360 and Plasticity** — the two the
founder named. You own \`docs/VISION.md\` and \`docs/COMPETITIVE.md\`; you have
WebFetch and WebSearch and you are the one role allowed to look outside the repo.

FIRST, re-ground the daily-driver scorecard. It directs prioritisation, so a
stale row is worse than no row. Read \`git log\` since the last VISION edit and
re-derive every row you touch against the CODE or a running app — never flip a
row because a commit message says so.

THEN find capability gaps a working engineer would actually hit. Not a feature
checklist: the useful finding is where "could I model a real part in this today?"
is NO and the user would not know why. Plasticity's strength is direct/sub-d
modelling feel and viewport quality; Fusion's is the parametric timeline, sketch
inference, assemblies and drawings. We already have a timeline, a sketcher,
extrude/revolve/fillet/chamfer/shell/draft/hole, assemblies with mates, drawings
and STEP/STL export.

Weigh three things this project learned the hard way. (1) Every founder complaint
on 2026-08-01 was a FLOW failure, not a missing verb — the capability was there
and unreachable, so do not assume the next win is a new verb. (2) A snap copies
the coordinate but infers no CONSTRAINT (SNAP-2): Fusion and SolidWorks create an
inferred coincident so the corner stays attached when the profile is later
dimensioned. That is a capability gap wearing a bug's clothing, and it is exactly
what you should find BEFORE the founder does. (3) Mirroring about a datum axis is
impossible; the axes only just became selectable.

END with a prioritised candidate list the backlog-groomer can turn into Ready
items — each with the gap, why an engineer hits it, what Fusion or Plasticity
does instead, and a rough size. Rank by the daily-driver question, not by how
impressive the feature sounds. **If your honest conclusion is that defect repair
should still outrank new capability right now, say so plainly with reasoning** —
that is a more useful answer than a list generated to satisfy the request.

You write direction docs ONLY, never app code, and NEVER \`docs/BACKLOG.md\` —
that belongs to the backlog-groomer. Commit your doc changes as the last thing
you do, staged and committed in the same turn. Every claim must be sourced or
measured; an inherited claim must be re-derived before you repeat it.`,
    { label: 'discover:competitive', phase: 'Discover', agentType: 'vision-steward' },
  )
}

// --- Audit -----------------------------------------------------------------
// Independent and parallel, and they must NOT see each other's output first.
// Write-early is mandated so a late crash does not lose the pass — it worked:
// both 2026-08-14 reports survived their agents' deaths intact.
if (!skipAudit) {
  phase('Audit')
  await parallel([
    () =>
      agent(
        `Deep PRODUCT audit of Loft from a working engineer's perspective —
daily-driver readiness and workflow friction against Fusion 360 / Plasticity /
SolidWorks / Onshape. APPEND your findings to docs/AUDIT-PRODUCT.md as you go
(write-early: append incrementally, do not hold everything to the end — agents
here have died mid-run and lost whole passes). Rate each finding and end with a
prioritised recommendation list the groomer can turn into Ready items. You are
READ-ONLY on app code. Do NOT coordinate with the engineering auditor; the
independence is the point.`,
        { label: 'audit:product', phase: 'Audit', agentType: 'product-auditor' },
      ),
    () =>
      agent(
        `Deep ENGINEERING audit of Loft — correctness risks, security, DRY and
service-boundary violations, test-coverage gaps, geometry-QA coverage,
performance, dependency and licence hygiene. APPEND to
docs/AUDIT-ENGINEERING.md as you go (write-early). Rate each finding and end
with a prioritised recommendation list. READ-ONLY on app code. Do NOT
coordinate with the product auditor.

Two live threads worth your attention: docs/RETRO.md §4 records that this
project keeps shipping gates that cannot fail and claims nobody measured — the
last pass found one in the loop's own Stop hook, so look for more. And
CI-4/QA7-1 in docs/BACKLOG.md: the e2e suite is not yet trustworthy per-commit.`,
        { label: 'audit:engineering', phase: 'Audit', agentType: 'engineering-auditor' },
      ),
  ])
}

// --- Curate ------------------------------------------------------------------
// `oss-curator` owns the FIRST-IMPRESSION surface of an MIT open-source project
// — README, CONTRIBUTING, SECURITY, issue/PR templates, badges, screenshots. It
// had never been spawned either, and the product audit's top finding (M1) is
// exactly its territory: a stranger who clones this repo lands on a sign-in card
// pinned to the bottom-right corner with ~86 % empty grid and no "MIT /
// self-hosted / your data" framing anywhere. Same cadence as the audits.
if (!skipCurate) {
  phase('Audit')
  await agent(
    `Audit and repair the first-impression surface of this repo as an MIT,
self-hostable, open-source CAD project: README, CONTRIBUTING, SECURITY,
CODE_OF_CONDUCT, issue/PR templates, badges, and the screenshots the README
leans on.

TRUTH ONLY — this is the rule that matters most for your role. Do not claim a
capability the product does not have, and re-derive anything already written
before you repeat it: this project has shipped several confident claims that
were never measured, and a README is the highest-visibility place for one.
Check what actually shipped in \`git log\` and \`docs/ROADMAP.md\` rather than
trusting existing prose.

Relevant, and it is your territory rather than the frontend's: the product audit
recorded that the landing screen is a sign-in card at the bottom-right of an
otherwise empty frame, with no product framing at all — no MIT/self-hosted line,
no version, no link to docs — on the one screen every self-hoster sees first.
Judge whether the README compensates or compounds that.

Meta and docs only, never app code. Commit as the last thing you do, staged and
committed in the same turn. Do NOT touch \`docs/BACKLOG.md\` or
\`docs/ROADMAP.md\`.`,
    { label: 'curate:oss', phase: 'Audit', agentType: 'oss-curator' },
  )
}

// --- Groom -----------------------------------------------------------------
// THE GROOMER OWNS THE BOARD. The orchestrator does not write it. This is the
// single change that removes the overwrite class: one writer for BACKLOG.
phase('Groom')
const occupiedNote = occupied.length
  ? `\nTERRITORIES ALREADY OCCUPIED by builders live right now — items touching
these CANNOT be in this batch, so skip them however high they rank and say so:
${occupied.map((t) => `  - ${t}`).join('\n')}\n`
  : ''

const ready = skipGroom
  ? null
  : await agent(
  `You own docs/BACKLOG.md. Reconcile it against git history, docs/ROADMAP.md,
both audit docs, **docs/COMPETITIVE.md and docs/VISION.md's daily-driver
scorecard**, docs/UI-REVIEW.md and docs/GEOMETRY-QA.md: dedupe, reprioritise,
tick what has actually shipped, and refresh the Ready queue.

**MEASURE THE RATIO AND RETURN IT — this is not optional and it is why the
schema demands it.** Run \`git log --pretty=format:'%s' -30 | cut -d: -f1 | sort |
uniq -c\` (or better) and report the feat/fix split of the last 30 commits, plus
the defect/capability split of the batch you are handing back. The workflow
script cannot run git; you can, and the loop went 4-feat-in-45 with every Ready
item a defect before a human noticed. You are the instrument that makes that
visible EVERY batch instead of every fortnight.

**Tag every returned item \`kind\`: 'defect' (something is broken) or
'capability' (the product cannot do it at all).** If the whole batch is
\`defect\`, that may well be correct — say so and why in \`ratio\`. What is not
acceptable is it happening silently.

Then RETURN the top ${batchSize} Ready items that are DISJOINT — no two may touch
the same files, because each will be built concurrently in its own worktree.
Serialising same-file items is your call to make; prefer fewer items to a
collision.
${occupiedNote}
For each returned item give: id, title, the ticket text (mechanism + fix +
acceptance criteria, enough that a builder needs no other context), the
agentType that owns that code, and an explicit territory as file globs.

Two things to know. (1) The orchestrator has been filing items by hand — CI-2,
CI-3, CI-4, REV-1..REV-5, QA7-1, FB-20, SEL-6..SEL-8, SPEC-3/4. That was a
mistake and it stops now; the board is yours. Reconcile anything it got wrong.
(2) Founder reports outrank everything. Four sketcher complaints are in flight —
dimensions not assigning, snap points not working, no orbit while sketching, and
no Fusion-style hover-a-face-to-sketch. VP-1 shipped orbit on the MIDDLE button
and the founder is on a TRACKPAD, so that complaint is NOT closed; there should
be a VP-1a for a trackpad-reachable gesture if one is not already filed. "Snap
points do not work" has never been reproduced by anyone and has no ticket.

Commit your board changes yourself, as the LAST thing you do, staged and
committed in the same turn — never leave shared-doc edits unstaged across other
tool calls. You are the only writer on those files this batch: builders are
explicitly told not to touch them.`,
  { label: 'groom', phase: 'Groom', agentType: 'backlog-groomer', schema: READY },
)

// Seeded items WIN over the groomer's: a caller that passed a batch in has
// already decided, and silently preferring a groom result over an explicit
// argument is the kind of surprise that costs a batch to notice.
const items = (seedItems.length ? seedItems : (ready && ready.items) || []).slice(
  0,
  batchSize,
)
if (items.length === 0) {
  // Say WHICH emptiness this is. "Nothing to build" reads as "the board is
  // clear" — a satisfying, wrong conclusion when the truth is that the agent
  // which reads the board never came back.
  log(
    skipGroom
      ? 'skipGroom was set and no seedItems were passed — nothing to build. Pass args.items.'
      : ready
        ? 'Groomer returned an empty Ready queue — nothing to build this batch.'
        : 'Groomer produced NO RESULT (died, or was skipped). This is not an empty board.',
  )
  return { built: [], greenBranches: [], note: 'Ready queue empty' }
}
log(`batch: ${items.map((i) => `${i.id}(${i.agentType}/${i.kind || '?'})`).join(', ')}`)
const capability = items.filter((i) => i.kind === 'capability').length
log(`composition: ${capability} capability / ${items.length - capability} defect`)
if (ready && ready.ratio) log(`groomer's measured ratio: ${ready.ratio}`)
if (capability === 0 && !skipDiscover) {
  log(
    'NOTE: an all-defect batch immediately after a Discover pass. Legitimate if the ' +
      "groomer's ratio says so — but this is the exact shape that went unnoticed for 45 " +
      'commits, so read its reasoning rather than skimming past it.',
  )
}

// --- Build -> Review -> Verify ---------------------------------------------
// A PIPELINE, deliberately: item A's review starts the moment A's build lands,
// rather than waiting for the slowest build in the batch. Nothing in review or
// QA needs cross-item context, so a barrier here would only buy idle time.
const slices = await pipeline(
  items,

  // 1 — Build, in its own worktree.
  (it) =>
    agent(
      `Own ticket ${it.id} end to end, in your own isolated git worktree.

FIRST ACT, BEFORE READING ANYTHING ELSE. Your worktree is seeded from this
session's INITIAL ref, not from the branch tip — measured 2026-08-14 across two
dispatch mechanisms hours apart: every worktree sat at the same stale commit
even after main had moved on. One agent's worktree was five commits behind and
did not contain the very commit it was extending; the spec file its ticket named
did not exist. So run:
    git fetch origin ${branch} && git reset --hard origin/${branch}
and STATE IN YOUR REPORT which SHA you actually built on. Skipping this means
gating against stale code and producing a commit whose parent silently reverts
its predecessors.

TICKET ${it.id} — ${it.title}

${it.ticket}

TERRITORY (yours alone; siblings are building other items in their own
worktrees):
${it.territory}

Implement it, review your own diff hard, and QA it against the real running
stack before committing. Commit ONLY if your gates are green. Leave the work on
YOUR worktree's branch and do NOT push — the orchestrator integrates green
branches and verifies the merged tree.

Ports and DB files are the only things still shared: pick ports off the
defaults and prefix your SQLite files with \`${it.id.toLowerCase()}-\`.

COMMIT CODE AND TESTS ONLY. Do NOT edit docs/ROADMAP.md or docs/BACKLOG.md —
several agents ticking those two files in several worktrees is a guaranteed
conflict, and the backlog-groomer is the only writer on them this batch. The
orchestrator folds your board tick into your commit at integration. Everything
a reader needs in order to write that tick must therefore be in your commit
message and your report.

${STANDARD}

REPORT: your branch name, the commit SHAs, what shipped, gate tails, mutation
evidence verbatim, and what you did NOT do and why.`,
      {
        label: `build:${it.id}`,
        phase: 'Build',
        agentType: it.agentType,
        isolation: 'worktree',
        schema: BUILT,
      },
    ),

  // 2 — Independent review of what actually landed.
  async (build, it) => {
    if (!build || !build.shipped) return { item: it, build, review: null, verify: null }
    const range = (build.shas || []).join(' ') || `branch ${build.branch}`
    const review = await agent(
      `Independent code review of ticket ${it.id} — ${it.title}.

The work is committed on the worktree branch \`${build.branch}\`, commits:
${range}
Read them with \`git show <sha>\` from the main checkout — a worktree branch is
an ordinary ref in this repo, so the commits are visible to you. Review the
COMMITTED state; if the working tree is dirty, those files belong to live
siblings and are not yours to judge.

THE BUILDER'S OWN ACCOUNT (treat as a claim to check, not as evidence):
  summary:  ${build.summary}
  gates:    ${build.gates}
  mutation: ${build.mutation}
  not done: ${build.notDone}

THE TICKET IT WAS MEANT TO SATISFY:
${it.ticket}

Review for correctness first, then for what this repo rejects in review: DRY (a
hand-written duplicate of a generated API type; copied cross-service boilerplate
that belongs in py-kit), service boundaries (only services/geometry imports
OCP/build123d; services/geometry never touches Postgres; apps/web talks only to
the gateway), strict typing with no unjustified \`any\`, no GPL/AGPL dependency,
and apps/web composing packages/design primitives rather than restyling raw
elements.

THEN THE TWO THAT MATTER MOST HERE:
1. VERIFY THE MUTATION EVIDENCE YOURSELF on anything load-bearing. Re-run it.
   This project has shipped four gates that could not fail, and a builder
   reporting "mutation-verified" is exactly the claim worth spot-checking.
   Revert anything you change.
2. CHECK EVERY FACTUAL CLAIM the diff adds to the durable record. A wrong number
   in a comment is a defect; the last two reviews found four between them.

Mark \`blocking: true\` ONLY for something that must change before more work
lands. You are read-only on app code — report, do not fix.`,
      { label: `review:${it.id}`, phase: 'Review', agentType: 'code-reviewer', schema: REVIEWED },
    )
    return { item: it, build, review, verify: null }
  },

  // 3 — Independent QA against the real running stack.
  async (slice) => {
    if (!slice || !slice.build || !slice.build.shipped) return slice
    const { item, build, review } = slice
    const flagged = review
      ? (review.findings || [])
          .filter((f) => f.severity !== 'green')
          .map((f) => `  [${f.severity}] ${f.file}${f.line ? ':' + f.line : ''} — ${f.summary}`)
          .join('\n') || '  (none)'
      : '  (the reviewer died; assume nothing was checked)'

    const kernel = isKernelAdjacent(item)
    const verifier = kernel ? 'geometry-qa' : 'qa-tester'
    const verify = await agent(
      `Independent QA of ticket ${item.id} — ${item.title}, against the REAL
running stack in a real browser. You did not write this code and you are not
here to confirm it.

Committed on worktree branch \`${build.branch}\`: ${(build.shas || []).join(' ')}
Check it out or read it with \`git show\`; do NOT modify the builder's worktree.

THE ACCEPTANCE CRITERIA THIS MUST MEET:
${item.ticket}

WHAT THE REVIEWER FLAGGED (context, not your worklist):
${flagged}

${
        kernel
          ? `THIS IS KERNEL-ADJACENT, SO YOU ARE THE GEOMETRIC-CORRECTNESS GATE, NOT A
WEB QA. A green unit suite with a wrong volume is a failure. Exercise the golden
suite, STEP round-trip fidelity, solver determinism across interpreter restarts,
and the performance budget. Hand-derive expected values in closed form at
documented per-model tolerances — never an ad-hoc epsilon, and never the
builder's own numbers re-run. If the change touches a PERSISTED signature or
contract, prove a selector authored BEFORE the change still resolves after it.
Write your findings to docs/GEOMETRY-QA.md.

`
          : ''
      }YOUR JOB IS THE CHECK THE BUILDER'S OWN GATE STRUCTURALLY CANNOT MAKE. That
phrasing is deliberate: on recent tickets the useful QA finding was never "the
feature is broken", it was that the shipped gate asked a question too coarse to
see the defect — a boolean where the interesting fact was WHICH entity answered,
or a pass rate a wrong-but-plausible implementation also achieves. Find that
question and ask it.

* Exercise the real artifact, desktop AND touch where the change is user-facing.
* MUTATION-VERIFY every assertion you add: prove it reddens against the
  pre-change behaviour, then restore.
* Watch for gates that pass for FREE — a refusal check that would score zero on
  a healthy scene, a census over a region where nothing is ever drawn. Under
  mutation those look identical to success.
* If you find the feature correct but the evidence weak, say exactly that.

${STANDARD}

REPORT: verdict PASS or FAIL, your measurements, your mutation evidence
verbatim, and anything you found that this ticket did NOT close — including
defects outside its scope, which get filed rather than fixed.`,
      { label: `verify:${item.id}`, phase: 'Verify', agentType: verifier, schema: VERIFIED },
    )
    return { ...slice, verify }
  },
)

const done = slices.filter(Boolean)
const died = items.length - done.filter((s) => s.build).length
const green = done.filter(
  (s) => s.build && s.build.shipped && !(s.review && s.review.blocking) && !(s.verify && !s.verify.passed),
)
log(
  `built ${done.filter((s) => s.build && s.build.shipped).length}/${items.length}` +
    (died ? `, ${died} DIED — worktrees preserved, reconcile rather than discard` : '') +
    `; clean through review+QA: ${green.map((s) => s.item.id).join(', ') || 'none'}`,
)

// --- Design ------------------------------------------------------------------
// `frontend-qa` owns design-system adherence, a11y, responsive behaviour and
// viewport UX -> docs/UI-REVIEW.md. It is the LAST agent the loop never pulled
// (AUDIT-ENGINEERING L5, 2026-08-16): one spawn in 108, and it owns the STANDING
// FOUNDER PRIORITY — CLAUDE.md's design mandate, where "flow is the first rule"
// and every founder report on 2026-08-01 was a flow failure rather than a
// missing capability. I wired geometry-qa, oss-curator and doc-syncer and left
// out the one whose subject the founder has complained about most. Runs only
// when the batch actually touched the UI, so it is pulled by the work rather
// than by memory.
const touchedUi = done.some(
  (s2) =>
    s2.build &&
    s2.build.shipped &&
    /apps\/web|packages\/design/.test(String((s2.item && s2.item.territory) || '')),
)
if (touchedUi) {
  phase('Verify')
  await agent(
    `Design and accessibility pass over what this batch changed in the UI:

${done
  .filter((s2) => s2.build && s2.build.shipped)
  .map((s2) => `${s2.item.id}: ${s2.item.title} — ${(s2.build.shas || []).join(' ')}`)
  .join('\n')}

Judge it by CLAUDE.md's design mandate, and lead with FLOW, which is the
founder's standing first rule: what does the user do NEXT from the state this
change leaves them in? Is the next step VISIBLE from the current state? Is there
a direct-manipulation path, or only a form? Are there dead ends or ambiguous
exits — a key that sometimes saves and sometimes discards is the named example.
Every founder report on 2026-08-01 was a flow failure where the capability
existed and was unreachable; that is the class to catch before he does.

Then the floor, which is not negotiable: WCAG-AA contrast, visible focus,
24 px minimum target size, \`prefers-reduced-motion\`, self-hosted fonts, and
responsive to 1280x800 — check BOTH 1600 and 1280, since defects have hidden at
the smaller width before (the origin ring measured 9.37 px at 1600 and 7.17 px
at 1280, on either side of an 8 px pick tolerance).

And design-system adherence: screens compose \`packages/design\` primitives and
never restyle raw elements; the r3f viewport reads the SAME tokens as the DOM.
Fix the primitive, never the instance.

File findings to \`docs/UI-REVIEW.md\`. You are READ-ONLY on app code — report,
do not fix. Capture before/after screenshots at both widths for anything
visual; the orchestrator surfaces them to the founder, and a PNG he never sees
does not count.`,
    { label: 'design:frontend-qa', phase: 'Verify', agentType: 'frontend-qa' },
  )
}

// --- DocSync -----------------------------------------------------------------
// `doc-syncer` is specified to run EVERY iteration, on the doc surfaces the
// same-commit rule does not cover — ARCHITECTURE facts, README claims,
// CHANGELOG, CLAUDE.md's command list. It had never been spawned once, and the
// drift is exactly what you would predict: ROADMAP went 129 commits stale, then
// stale again the same week; VISION and COMPETITIVE sat 16 days. It is on a
// cheap model by design (CLAUDE.md's token-economy section), so there is no
// reason for it to be the phase that gets skipped. Runs last, once the batch's
// commits exist for it to reconcile against.
phase('DocSync')
const shipped = done
  .filter((s2) => s2.build && s2.build.shipped)
  .map((s2) => `${s2.item.id}: ${(s2.build.shas || []).join(' ')}`)
  .join('\n') || '(nothing shipped this batch)'
await agent(
  `Reconcile the doc surfaces the same-commit rule does NOT cover, against what
actually shipped in this batch:

${shipped}

Check and fix drift in: \`docs/ARCHITECTURE.md\` (stated facts vs the code),
\`README.md\` claims, \`docs/CHANGELOG.md\`, and CLAUDE.md's command list versus
the real \`justfile\` targets. Read \`git show\` on the commits above rather than
their messages alone — a commit message is a claim like any other.

Do NOT touch \`docs/BACKLOG.md\` or \`docs/ROADMAP.md\` (the groomer owns both),
and never app code. If you find nothing drifted, say so and change nothing —
an empty pass is a fine outcome and better than invented edits. Commit as the
last thing you do, staged and committed in the same turn.`,
  { label: 'docsync', phase: 'DocSync', agentType: 'doc-syncer' },
)

// --- Integrate --------------------------------------------------------------
// Left to the orchestrator ON PURPOSE. A merge that silently reverts a sibling,
// or lands branches green in isolation but red together, is expensive and hard
// to see — and reading CI is something no subagent can do at all.
phase('Integrate')
return {
  batch: items.map((i) => i.id),
  died,
  slices: done.map((s) => ({
    id: s.item.id,
    branch: s.build ? s.build.branch : null,
    shas: s.build ? s.build.shas : [],
    shipped: !!(s.build && s.build.shipped),
    summary: s.build ? s.build.summary : null,
    notDone: s.build ? s.build.notDone : null,
    reviewBlocking: s.review ? s.review.blocking : null,
    reviewFindings: s.review ? s.review.findings : null,
    qaPassed: s.verify ? s.verify.passed : null,
    qaEvidence: s.verify ? s.verify.evidence : null,
    qaFailures: s.verify ? s.verify.failures : null,
  })),
  next:
    'Orchestrator: cherry-pick each clean branch, write the ROADMAP/BACKLOG tick, ' +
    '`commit --amend --no-edit`, push EACH commit separately, verify the merged tree, ' +
    'read CI, then chain the next batch.',
}
