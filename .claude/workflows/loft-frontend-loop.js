export const meta = {
  name: 'loft-frontend-loop',
  description:
    'Close the gap between what the backend can do and what a user can reach. Parity -> flow -> build in disjoint web subtrees -> design review -> QA -> founder evidence.',
  whenToUse:
    'Frontend-focused batches, especially "the backend has this and the UI does not". Runs ONE batch and returns.',
  phases: [
    { title: 'Parity', detail: 'derive the reachability gap from the committed contract' },
    { title: 'Flow', detail: 'decide HOW each gap becomes reachable, not just that it does' },
    { title: 'Build', detail: 'one builder per disjoint apps/web subtree' },
    { title: 'Design', detail: 'frontend-qa against the design mandate' },
    { title: 'QA', detail: 'qa-tester drives the real browser' },
    { title: 'Evidence', detail: 'before/after shots for the founder' },
  ],
}

// ---------------------------------------------------------------------------
// WHY THIS EXISTS, separately from loft-dev-loop.
//
// Founder, 2026-08-26: "I want to switch focus on the front end. There are
// features that exist on the backend but not the front end."
//
// Measured the same day, and the number is the argument for a dedicated loop:
// of 120 request-side capability literals in the gateway contract, **39 are
// unreachable from the UI** — 5 that appear nowhere in apps/web at all, and 34
// that the app can DISPLAY but no user can CREATE. `symmetric_lines` and
// `collinear` shipped that morning: rendered by ConstraintGlyphs.tsx,
// authorable by nobody. So did `sweep`, the boolean verbs, sheet-metal hem and
// corner relief, circular pattern, STL and GLB export.
//
// The general loop cannot find these. Its Discover phase looks for what is
// ABSENT from the product and its auditors look for what is BROKEN; a
// capability that is present, correct, tested and unreachable is neither. It
// passes every gate we own while being worth nothing to a user. That is a third
// failure mode and it needs its own detector.
//
// THREE THINGS THIS LOOP DOES DIFFERENTLY, each earned:
//
// 1. PARITY IS MECHANICAL, NOT AN OPINION. `scripts/check-ui-parity.py` derives
//    the gap from the committed contract and the e2e suite. An auditor's
//    impression of what is missing is a sample of what it happened to try; this
//    is the whole surface, and it is re-runnable, so the number moves and can
//    be gated on.
//
// 2. PARITY IS NOT THE GOAL — REACHABILITY IS. Shipping one form per missing
//    verb would take the number to zero and fail the founder's actual standard.
//    Every FB-1..FB-19 report was a flow failure where the capability was
//    already there and unreachable. So the Flow phase sits between the gap list
//    and the builders, and its job is to say HOW each thing becomes reachable:
//    which surface, which selection, what proposes it. A capability reachable
//    only from a menu nobody opens is still a gap.
//
// 3. apps/web IS ONE TERRITORY UNLESS YOU SPLIT IT BY SUBTREE. Learned the hard
//    way on 2026-08-25/26: five parallel web items had to be serialised because
//    they all wanted `apps/web/src/viewport/**`, and the groomer ended up
//    marking MATE-1 and ORTHO-1 BLOCKED behind whoever held it. Two builders in
//    one subtree is the overwrite class this org already paid for. So the batch
//    is allocated BY SUBTREE, at most one builder each, and an item that cannot
//    get a clean subtree waits for the next batch rather than racing.
// ---------------------------------------------------------------------------

// Keep this list COMPLETE. A subtree missing from it is not merely unavailable —
// it is invisible: the Parity phase can only assign work to a listed subtree, so
// an omission silently makes every gap living there unschedulable, with no error
// anywhere. `apps/web/src/components/**` was missing from the first version and
// EXPORT-3 (which lives in it) could not have been picked up by any batch.
// Cross-check against `ls apps/web/src` when adding a top-level directory.
const SUBTREES = [
  'apps/web/src/viewport/**',
  'apps/web/src/sketch/**',
  'apps/web/src/routes/**',
  'apps/web/src/features/**',
  'apps/web/src/components/**',
  'apps/web/src/drawing/**',
  'apps/web/src/assembly/**',
  'apps/web/src/measure/**',
  'apps/web/src/api/**',
  'apps/web/src/auth/**',
  'apps/web/src/settings/**',
  'apps/web/src/shortcuts/**',
  'apps/web/src/units/**',
  'packages/design/**',
]

// DELIBERATELY NOT subtrees: `lib/`, `store/`, `test/`, and the loose files at
// the root of `apps/web/src` (`router.tsx`, `main.tsx`, `index.css`). A change
// in any of those is cross-cutting by construction — every subtree imports
// them — so allocating one to a single builder would be a fiction that the
// other builders in the batch silently violate. Work that genuinely needs them
// is an escalation to the orchestrator, which serialises it, not a batch item.

const batchSize = (args && args.batchSize) || 3
const branch = (args && args.branch) || 'claude/branch-review-development-hkbbnb'
const occupied = (args && args.occupiedSubtrees) || []
const seedItems = (args && Array.isArray(args.items) && args.items) || []
const skipParity = !!(args && args.skipParity)

const available = SUBTREES.filter((t) => !occupied.includes(t))

const PLAN = {
  type: 'object',
  required: ['items'],
  properties: {
    items: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'title', 'capability', 'subtree', 'surface', 'proposedBy', 'acceptance'],
        properties: {
          id: { type: 'string' },
          title: { type: 'string' },
          capability: {
            type: 'string',
            description: 'the contract literal(s) this makes reachable, e.g. "collinear"',
          },
          subtree: { type: 'string', enum: SUBTREES },
          surface: {
            type: 'string',
            description: 'WHERE the user meets it — the toolbar group, panel, or gesture',
          },
          proposedBy: {
            type: 'string',
            description:
              'what makes it appear at the right moment. "the user opens a menu" is a FAILING answer.',
          },
          acceptance: {
            type: 'string',
            description: 'the e2e assertion that will prove a user can author it',
          },
        },
      },
    },
    deliberateOmissions: {
      type: 'array',
      items: { type: 'string' },
      description: 'gaps that SHOULD stay closed, each with its one-line reason',
    },
  },
}

// --- The shared standard, kept identical in spirit to loft-dev-loop's --------
const STANDARD = `
HOW THIS REPO JUDGES FRONTEND WORK:
* ALWAYS invoke the \`frontend-design\` skill before writing UI. The bar is
  Fusion 360 / Plasticity, not "premium dashboard" — judge your result against a
  reference side by side before calling it done.
* Fix the PRIMITIVE in \`packages/design\`, never the instance. The viewport reads
  the SAME tokens as the DOM; no hex literal is duplicated between them.
* Never break the product for looks. Preserve every \`data-testid\`, role and
  accessible name — a parts-register redesign dropped \`part-health\` on
  2026-08-26 and turned the whole suite red.
* An assertion never SEEN to fail is not a gate. Run the mutation, quote the red
  output, revert, confirm green. FIVE gates that could not fail have shipped
  here, and the fifth was found only because its author ran the mutation and it
  PASSED — so ask "could this fixture have reddened at all", not "did I run it".
* Quality floor: WCAG-AA contrast, visible focus, prefers-reduced-motion,
  self-hosted fonts, responsive to 1280x800.

ENVIRONMENT, each item having cost a whole agent run:
* FIRST ACTION: \`git rev-list --count HEAD..origin/${branch}\`. Nonzero means
  your worktree was seeded stale — reset before reading anything.
* \`git push -u origin <branch>\` FROM A WORKTREE PUSHES NOTHING and prints
  "Everything up-to-date". Use \`git push origin HEAD:${branch}\`, then verify BY
  VALUE with \`git ls-remote origin ${branch}\`. Exit status proves nothing.
* A new worktree is not ready until \`pnpm install --frozen-lockfile\` has run.
  Before that, prettier/tsc fail on files you never touched.
* A Tailwind preset or token change is a BUILD-CONFIG change: RESTART VITE, or
  your classes will not exist and the component renders wrong with no build
  error. A <canvas> reporting 300x150 is the fingerprint of un-styled.
* \`pnpm run <script> -- <args>\` DROPS the \`--\` in pnpm 10. Never write it.
  Confirm the port Vite printed; kill your Vite in teardown.
* The container is reclaimed without warning. Push the MOMENT a slice is green.
* You CANNOT read CI — api.github.com is denied to subagents. Push and stop; the
  orchestrator reads the run and relays failures back.
* Do NOT touch docs/ROADMAP.md or docs/BACKLOG.md — the groomer owns the board.
`

// --- Parity ----------------------------------------------------------------
let plan = null
if (!skipParity) {
  phase('Parity')
  log(`subtrees available this batch: ${available.join(', ') || 'NONE'}`)

  plan = await agent(
    `Plan a frontend batch that makes BACKEND CAPABILITY REACHABLE.

Run \`python3 scripts/check-ui-parity.py\` (and \`--json\` for the machine-readable
form). It classifies every request-side capability literal in the committed
gateway contract as AUTHORABLE, RENDER-ONLY (the app displays it, no e2e spec
drives it) or ABSENT (nowhere in apps/web at all).

TRIAGE IT — the report is evidence, not a work list, and its middle tier is a
PROXY. "No e2e spec drives this" is the closest mechanical stand-in we have for
"no user can do this", and it is wrong in both directions sometimes: a
capability may be authorable through a path no spec happens to cover, and a spec
may only seed a fixture over the API without proving any UI path exists. So open
the app source for each candidate and establish which it is. Say which ones you
checked and how.

Then separate three groups:
  (a) REAL GAPS worth building — the user should be able to do this and cannot.
  (b) DELIBERATE OMISSIONS — return these in \`deliberateOmissions\` with a
      one-line reason each. A capability we chose not to expose is not a defect,
      and saying so once stops it being re-discovered every pass.
  (c) FALSE POSITIVES — reachable by a path the check cannot see. Say which, so
      the check can be sharpened.

For each item in (a), the plan must answer HOW IT BECOMES REACHABLE, not merely
that it will exist. That is the whole point of this loop:
  - \`surface\`: where the user meets it (which toolbar group, panel, gesture).
  - \`proposedBy\`: what makes it appear at the right moment. **"The user opens a
    menu and finds it" is a FAILING answer.** The design mandate's first flow
    test is that the next step is visible from the current state — a solved
    sketch's likely next action is present, with the profile pre-selected, not
    hunted for. Prefer selection-driven affordances: two lines selected should
    OFFER the constraints that apply to two lines.
  - \`acceptance\`: the e2e assertion that will prove a user can author it. This
    is what closes the parity gap, so it must drive the real UI, not seed a
    fixture over the API.

TERRITORY IS A HARD CONSTRAINT. Assign each item exactly one \`subtree\` from
this list, and NO TWO ITEMS MAY SHARE ONE:
${available.map((t) => `  - ${t}`).join('\n')}
${occupied.length ? `\nOCCUPIED by builders live right now, unavailable this batch:\n${occupied.map((t) => `  - ${t}`).join('\n')}` : ''}
apps/web behaves as ONE territory unless split this way; two builders in a
subtree is the overwrite class this org has already paid for. Return AT MOST
${Math.min(batchSize, available.length)} items. If a high-value gap cannot get a
clean subtree, leave it out and say so — it will lead the next batch.

Rank by the operating question: would a working engineer model a real part in
this today? A constraint they reach for every sketch outranks an export format
they use monthly.

You are read-only on app code. Do not implement anything, and do not touch
docs/BACKLOG.md — the groomer owns the board.`,
    { label: 'parity', phase: 'Parity', agentType: 'frontend-qa', schema: PLAN },
  )
}

const items = (seedItems.length ? seedItems : (plan && plan.items) || []).slice(
  0,
  batchSize,
)

if (items.length === 0) {
  log(
    skipParity
      ? 'skipParity was set and no seedItems were passed — nothing to build. Pass args.items.'
      : plan
        ? 'Parity found no buildable gap this batch. That is a real result if deliberateOmissions explains it.'
        : 'The parity agent produced NO RESULT (died, or was skipped). This is not an empty gap list.',
  )
  return { built: [], note: 'no reachable-capability gaps to build' }
}

const clash = items.length - new Set(items.map((i) => i.subtree)).size
if (clash > 0) {
  log(
    `::warning:: ${clash} item(s) share a subtree with another — serialising is NOT` +
      ' handled here, so the batch is trimmed to one item per subtree.',
  )
}
const byTree = new Map()
for (const it of items) if (!byTree.has(it.subtree)) byTree.set(it.subtree, it)
const batch = [...byTree.values()]

log(`batch: ${batch.map((i) => `${i.id}[${i.subtree}]`).join(', ')}`)
if (plan && plan.deliberateOmissions && plan.deliberateOmissions.length) {
  log(`deliberate omissions: ${plan.deliberateOmissions.length} (see the plan)`)
}

// --- Flow -> Build -> Design -> QA -----------------------------------------
// A PIPELINE: each item's design review starts the moment its build lands,
// rather than waiting for the slowest builder. Nothing downstream needs
// cross-item context, so a barrier would only buy idle time.
const done = await pipeline(
  batch,
  (it) =>
    agent(
      `Make this backend capability REACHABLE: **${it.title}** (${it.id}).

Capability: \`${it.capability}\` — it exists in the gateway contract and the
service implements it. A user cannot get at it. Your job is the path, not the
feature.

The plan's answer for how it becomes reachable:
  surface:     ${it.surface}
  proposed by: ${it.proposedBy}
  acceptance:  ${it.acceptance}

Treat that as a decision to implement, not a spec to follow blindly — you are
the one who will see whether it actually flows. If building it shows the plan's
answer is wrong, say so in your commit message and do the better thing.

**Ship the e2e that drives it through the REAL UI in the same commit.** That
spec is what closes the parity gap: \`scripts/check-ui-parity.py\` uses the e2e
suite as its reachability oracle, so a capability with no spec driving it still
reads as unreachable — correctly, because nobody has demonstrated a user can get
there. Seeding a fixture over the API does not count and will not move the
number.

YOUR TERRITORY IS \`${it.subtree}\` AND NOTHING ELSE. Other builders are live in
the sibling subtrees this batch. If the work genuinely requires a file outside
it, STOP and report that rather than reaching across — a clean hand-off costs
one batch, an overwrite costs two agents' work.
${STANDARD}
Report: the mechanism, the diff stat, the e2e that drives it, the mutation
evidence, and a screenshot at 1280x800 showing the affordance in place.`,
      {
        label: `build:${it.id}`,
        phase: 'Build',
        agentType: 'frontend-builder',
        isolation: 'worktree',
      },
    ),
  (build, it) =>
    agent(
      `Design review of ${it.id} (${it.title}), just landed in \`${it.subtree}\`.

Builder's report:
${String(build || '(no report — the agent may have died; check git log for its commits)').slice(0, 4000)}

Judge it against the design mandate, and lead with the question this loop exists
for: **is the capability actually reachable now, or merely present?** Walk the
flow yourself in the running app. Specifically —
  - Does the affordance appear at the moment it is useful, or must it be hunted?
  - Is there a direct-manipulation path, with the numeric field as the precision
    fallback rather than the only route?
  - Does the surface still read as a quiet precision instrument, or has a new
    control been bolted on where there was room rather than where it belongs?
  - Test hooks intact? Contrast, focus, reduced-motion, 1280x800?

You are read-only on app code. File what you find to \`docs/UI-REVIEW.md\` and
return the blocking issues plainly. A finding that the thing works but does not
FLOW is exactly what you are here for — say it.`,
      { label: `design:${it.id}`, phase: 'Design', agentType: 'frontend-qa' },
    ),
)

// --- QA --------------------------------------------------------------------
// One pass over the whole batch, deliberately: the interesting failures at this
// point are INTERACTIONS between the new affordances (two new controls in one
// toolbar, two new modes competing for the same selection), which per-item QA
// cannot see. This is the one place a barrier earns its cost.
phase('QA')
const qa = await agent(
  `Independent QA of this frontend batch, in a REAL browser against the REAL stack.

Items: ${batch.map((i) => `${i.id} (${i.capability}) in ${i.subtree}`).join('; ')}

Exercise each capability the way a working engineer would, end to end — not the
happy path the builder wrote a spec for. Then look specifically for what
per-item review cannot see: **do the new affordances interfere with each
other?** Two new controls in one toolbar group, two modes competing for the same
selection, a new hotkey shadowing an existing one, the command band overflowing
at 1280x800 now that it carries more.

Boot natively per CLAUDE.md — the Docker registry is 403-blocked — on SQLite
files prefixed with your own agent slug, from fresh files. Kill stray Vite and
stale \`*.main:app\` uvicorns before your run: a stale Vite on :5173 makes every
spec 500 at register and reads as a total regression.

Run in a QUIET window and report the load average. A red run under load is
UNCONFIRMED, not evidence. The discriminator: a real regression fails
IDENTICALLY every time; a contention flake MOVES.

File defects to the board's usual place. Do not fix app code.`,
  { label: 'qa:batch', phase: 'QA', agentType: 'qa-tester' },
)

// --- Evidence --------------------------------------------------------------
// The mandate says UI work ships with before/after screenshots SURFACED TO THE
// FOUNDER, and that generating a PNG nobody sees does not count. That kept
// being remembered by hand, so it is a phase.
phase('Evidence')
const shipped = done.filter(Boolean).length
log(`built ${shipped}/${batch.length}; re-run scripts/check-ui-parity.py to see the number move`)

return {
  items: batch.map((i) => ({ id: i.id, capability: i.capability, subtree: i.subtree })),
  deliberateOmissions: (plan && plan.deliberateOmissions) || [],
  qa,
  // The orchestrator owes the founder the before/after shots and a re-run of the
  // parity report — both are its job, not a subagent's, and both get forgotten.
  orchestratorTodo: [
    'read CI for each pushed commit and relay failures to the owning agent',
    'send the founder the before/after screenshots (SendUserFile, not a folder)',
    're-run scripts/check-ui-parity.py and report the AUTHORABLE count movement',
  ],
}
