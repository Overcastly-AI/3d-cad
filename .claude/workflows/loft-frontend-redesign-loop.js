export const meta = {
  name: 'loft-frontend-redesign-loop',
  description:
    'Redesign the front end around what the work COSTS, not around what exists. Cost -> direction -> build in disjoint web subtrees -> design review -> QA -> re-measure.',
  whenToUse:
    'Frontend redesign and flow work: the capability is already there and reaching it costs too much, or the surface does not feel like a modeling tool. Runs ONE wave and returns.',
  phases: [
    { title: 'Cost', detail: 'measure what journeys cost and pick the wave from the standing audits' },
    { title: 'Direction', detail: 'ONE agent fixes the interaction and visual decisions for the whole wave' },
    { title: 'System', detail: 'the design-system change lands FIRST and alone, if the wave needs one' },
    { title: 'Build', detail: 'one builder per disjoint apps/web subtree, against the fixed direction' },
    { title: 'Review', detail: 'code-reviewer reads the diff — correctness, hooks, DRY' },
    { title: 'Design', detail: 'frontend-qa against the direction and the mandate' },
    { title: 'QA', detail: 'qa-tester drives the real browser; hooks and muscle memory survive' },
    { title: 'Evidence', detail: 're-measure the cost and hand the founder the before/after' },
  ],
}

// ---------------------------------------------------------------------------
// WHY THIS EXISTS, separately from loft-frontend-loop.
//
// Founder, 2026-09-11: "The front end must be improved for user experience. The
// flow of creating a part should be seamless. I want to give full freedom of
// improving the UI design and flow. Changes are encouraged to feel more like
// Fusion 360 or Plasticity."
//
// `loft-frontend-loop` asks CAN THE USER REACH THIS. That was the right question
// on 2026-08-26, when 39 of 120 contract capabilities were unreachable. It is
// the wrong question now, and `check-ui-parity.py` says so in its own docstring:
// it measures REACHABILITY, NOT DISCOVERABILITY, and a batch that closes real
// flow gaps leaves its number unmoved. **A capability that takes eleven gestures
// is AUTHORABLE.** Every FB-1..FB-19 founder report was a flow failure on a
// capability that was already present, already reachable, already covered by a
// green spec. A loop built on parity is structurally blind to all of them.
//
// So this loop is driven by a different measurement — `check-flow-cost.py`,
// which reads `apps/web/e2e/` as what it actually is: a transcript of ~2500 real
// gestures on this product. The canonical register -> part -> sketch -> extrude
// -> edit -> export journey costs **30 gestures**, driven entirely through the
// UI. That is the number this loop exists to move, with every caveat in that
// script's docstring attached — above all that a drop is a QUESTION, never an
// achievement, because it is trivially gamed by editing the spec instead of the
// app.
//
// FOUR THINGS THIS LOOP DOES DIFFERENTLY, each one earned:
//
// 1. A DIRECTION PHASE SITS UPSTREAM OF THE BUILDERS, AND IT IS THE WHOLE
//    DIFFERENCE. Parallel builders in a parity batch are safe because each adds
//    a separate affordance; parallel builders in a REDESIGN batch each make
//    aesthetic and interaction decisions, and three agents deciding
//    independently produce three dialects. That failure is invisible per item —
//    every one passes its own design review, because each is internally
//    coherent — and it only shows up as the thing the founder already rejected
//    once: a UI that reads as templated and unintentional. So one agent fixes
//    the decisions for the wave (the gesture grammar, the token moves, the
//    signature element, what a handle looks like everywhere) and the builders
//    implement against them. Note this BUYS freedom rather than spending it: the
//    founder asked for bold, and bold survives being made once and applied three
//    times, where it does not survive being averaged across three authors.
//
// 2. THE DESIGN SYSTEM IS THE HOT FILE IN A REDESIGN, WHICH IT NEVER IS IN A
//    PARITY BATCH. `packages/design` is where the mandate says to fix things
//    ("fix the primitive, never the instance"), so a redesign wave pulls three
//    builders into ONE package at once — the overwrite class this org has
//    already paid for twice. Worse, the cheap way out of that collision is for
//    each builder to patch its own instance instead, which is the exact DRY
//    violation review rejects, arrived at by following the parallelism rule. So
//    a wave needing a primitive change lands that change FIRST, ALONE, and the
//    builders start from its SHA.
//
// 3. THE HOOKS ARE PART OF THE PRODUCT. A redesign rewrites the DOM, and
//    `data-testid`, roles and accessible names go with it unless someone is
//    watching: a parts-register redesign dropped `part-health` on 2026-08-26 and
//    turned the whole suite red. Every builder brief in this loop carries the
//    inventory rule, and QA checks it as a first-class item rather than noticing
//    it when specs fail.
//
// 4. IT RE-MEASURES, AND REPORTS THE DELTA WITH THE DIFF. A wave that shortens
//    nothing is a legitimate outcome (a wave can buy legibility or atmosphere
//    instead) and must be SAID rather than hidden, because the alternative is
//    the number quietly becoming the goal. See the Evidence phase.
// ---------------------------------------------------------------------------

// Keep this list COMPLETE — cross-check against `ls apps/web/src` when adding a
// top-level directory. A subtree missing from it is not merely unavailable, it
// is invisible: the planner can only assign work to a listed subtree, so an
// omission silently makes every item living there unschedulable with no error
// anywhere. `apps/web/src/components/**` was missing from the first version of
// the sibling loop and EXPORT-3 could not have been picked up by any batch.
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
]

// FOUNDATIONS — claimable, but only ever by ONE item, which then runs first and
// alone while everyone else starts from its commit.
//
// The first version of this file listed only `packages/design/**` here and left
// `store/` and `lib/` out of the loop entirely, on the reasoning that a
// cross-cutting change "is an escalation to the orchestrator, not a wave item".
// That reasoning is sound and the conclusion was wrong, which the craft audit
// exposed within the hour: its single most important item — persistent geometry
// selection, the one the mandate's whole "next step visible from the current
// state" rule depends on — lives in `apps/web/src/store/**`. So the loop's most
// valuable possible work was UNSCHEDULABLE, silently, with no error anywhere.
// That is precisely the failure the SUBTREES list above carries a warning about,
// committed by the person who wrote the warning.
//
// The fix is the mechanism that already existed for `packages/design`: a
// foundation item is not un-buildable, it is un-PARALLELISABLE. Give it the wave
// to itself, land it first, hand its SHA to the rest. A second foundation item
// in the same wave is deferred rather than raced.
const FOUNDATION_SUBTREES = [
  'packages/design/**',
  'apps/web/src/store/**',
  'apps/web/src/lib/**',
]
const SYSTEM_SUBTREE = FOUNDATION_SUBTREES[0]

// Still NOT claimable at all: `test/` and the loose files at the root of
// `apps/web/src` (`router.tsx`, `main.tsx`, `index.css`). Unlike store and lib,
// these have no plausible single owner for a wave — a router change serves
// whatever surfaces the wave happens to touch, so it belongs inside those items
// rather than being one.

const batchSize = (args && args.batchSize) || 3
const branch = (args && args.branch) || 'claude/frontend-workflow-redesign-8ae3su'
const occupied = (args && args.occupiedSubtrees) || []
const seedItems = (args && Array.isArray(args.items) && args.items) || []
const skipCost = !!(args && args.skipCost)
const skipDirection = !!(args && args.skipDirection)
//: Which roadmap wave to draw from, e.g. 'W1'. Omit to let the planner choose.
const wave = (args && args.wave) || null

const available = SUBTREES.filter((t) => !occupied.includes(t))

const ROADMAP_DOC = 'docs/design/REDESIGN-ROADMAP.md'
const AUDITS = ['docs/design/AUDIT-FLOW-2026-09.md', 'docs/design/AUDIT-CRAFT-2026-09.md']

const PLAN = {
  type: 'object',
  required: ['items'],
  properties: {
    waveGoal: {
      type: 'string',
      description:
        'the ONE sentence a user would say about this wave if it works. Not a list.',
    },
    items: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'title', 'subtree', 'costNow', 'costAfter', 'surface', 'acceptance'],
        properties: {
          id: { type: 'string' },
          title: { type: 'string' },
          subtree: { type: 'string', enum: [...SUBTREES, ...FOUNDATION_SUBTREES] },
          costNow: {
            type: 'string',
            description:
              'what the journey costs TODAY, in gestures, and how you measured it. "feels slow" is a FAILING answer.',
          },
          costAfter: {
            type: 'string',
            description:
              'what it should cost after, and what the user does INSTEAD of the gestures removed. If the answer is "the same", say why the item is still worth it — legibility and atmosphere are legitimate wins.',
          },
          surface: {
            type: 'string',
            description: 'where the user meets it — the panel, the toolbar group, the gesture',
          },
          acceptance: {
            type: 'string',
            description:
              'the e2e assertion proving a user can do it the NEW way, driven through the real UI',
          },
          needsPrimitive: {
            type: 'boolean',
            description:
              'true if this requires a new or changed primitive in packages/design, or a change to the shared store or lib. Be honest: a "just this once" local style is the DRY violation review rejects, and a quietly-widened store is the overwrite class.',
          },
          primitive: {
            type: 'string',
            description: 'which primitive / store slice, if needsPrimitive',
          },
        },
      },
    },
    deferred: {
      type: 'array',
      items: { type: 'string' },
      description:
        'roadmap items NOT in this wave, each with the one-line reason. A high-value item with no clean subtree belongs here and leads the next wave.',
    },
  },
}

// --- The shared standard ----------------------------------------------------
const STANDARD = `
HOW THIS REPO JUDGES FRONTEND WORK:
* ALWAYS invoke the \`frontend-design\` skill before writing UI. The bar is
  Fusion 360 / Plasticity, not "premium dashboard" — judge your result against a
  reference side by side before calling it done, and say plainly if you had no
  reference image and were judging against a written description instead.
* Fix the PRIMITIVE in \`packages/design\`, never the instance. The viewport reads
  the SAME tokens as the DOM; no hex literal is duplicated between them.
* PRESERVE EVERY TEST HOOK. Before you change a surface, inventory its
  \`data-testid\`s, roles and accessible names; after, prove the same set is
  present (a redesign that dropped \`part-health\` turned the whole suite red).
  A hook you believe is obsolete is a conversation, not a deletion.
* An assertion never SEEN to fail is not a gate. Run the mutation, quote the red
  output, revert, confirm green. FIVE gates that could not fail have shipped
  here, and the fifth was found only because its author ran the mutation and it
  PASSED — so ask "could this fixture have reddened at all", not "did I run it".
* Direct manipulation is the goal, and it is what this loop is FOR: a handle
  first, the numeric field as the precision fallback. A new modal form where a
  drag would do is a finding against you, not a feature.
* Quality floor: WCAG-AA contrast, visible focus, prefers-reduced-motion,
  self-hosted fonts, responsive to 1280x800.

ENVIRONMENT, each line having cost a whole agent run:
* FIRST ACTION: \`git rev-list --count HEAD..origin/${branch}\`. Nonzero means
  your worktree was seeded stale — reset before reading anything. This has been
  ~100% of worktrees, not an occasional accident; budget for the reset.
* \`git push -u origin <branch>\` FROM A WORKTREE PUSHES NOTHING and prints
  "Everything up-to-date". Use \`git push origin HEAD:${branch}\`, then verify BY
  VALUE with \`git ls-remote origin ${branch}\`. Exit status proves nothing.
* A new worktree is not ready until \`pnpm install --frozen-lockfile\` has run.
  Before that, prettier/tsc fail on files you never touched — in someone else's
  territory, which reads as their regression. It is your environment.
* A Tailwind preset or token change is a BUILD-CONFIG change: RESTART VITE, or
  your classes will not exist and the component renders wrong with no build
  error. A <canvas> reporting 300x150 is the fingerprint of un-styled.
* Editing a \`packages/design\` primitive under a running Vite can serve a STALE
  transform, so a mutation check passes when it must have failed. Restart Vite
  between mutation legs and verify the SERVED bytes.
* \`pnpm run <script> -- <args>\` DROPS the \`--\` in pnpm 10. Never write it.
  Confirm the port Vite printed; kill ONLY your own Vite, resolved by port with
  \`lsof -ti\` (\`ss\` resolves nothing here, and a process-name grep kills every
  sibling agent's stack).
* Never \`git stash\` — the stash list is SHARED across worktrees and popping
  hands you whoever stashed last. Use a patch file under your own scratchpad dir.
* The container is reclaimed without warning. Push the MOMENT a slice is green.
* You CANNOT read CI — api.github.com is denied to subagents. Push and stop; the
  orchestrator reads the run and relays failures back.
* Do NOT touch docs/ROADMAP.md or docs/BACKLOG.md — the groomer owns the board.
  **But you MUST end your commit message with the line \`Doc-tick: groomer\`.**
  This is not ceremony: CI runs a DOCTICK gate that fails any commit landing
  product code with neither a board tick nor that trailer, and it has no
  \`continue-on-error\`. Wave 0 shipped two P0 fixes that were both red on it,
  because the brief told builders to skip the board AND to push straight to the
  shared branch — and the orchestrator protocol's answer (fold the tick in at
  integration with \`cherry-pick\` + \`--amend\`) presumes builders land on their
  OWN branches, so the amend window never existed. The trailer is the gate's own
  sanctioned hatch, it needs no doc edit, and two parallel builders cannot
  collide on it.
`

// --- Cost -------------------------------------------------------------------
let plan = null
if (!skipCost) {
  phase('Cost')
  log(`subtrees available this wave: ${available.join(', ') || 'NONE'}`)

  plan = await agent(
    `Plan ONE WAVE of the frontend redesign. The founder's standard is that
creating a part should feel SEAMLESS, and that the app should feel like Fusion
360 or Plasticity rather than a web form with a 3D view in it.

START FROM THE MEASUREMENT, NOT FROM AN IMPRESSION.

Run \`python3 scripts/check-flow-cost.py\` (and \`--json\`). It reads the e2e suite
as a transcript of real gestures and reports what each journey costs the hand.
Read its docstring before you read its output — it states three limits that
matter more than any row: it measures the path THE SPEC took (so it models an
expert who already knows every verb), it is blind to hesitation and ambiguity
(FB-13, the worst defect on the founder's list, costs ZERO gestures), and it is
gamed by editing the spec instead of the app. A high count is very often a
MEASUREMENT PROBE rather than an expensive journey. Open the spec before you
believe a row, and say which ones you opened.

THEN READ THE STANDING DESIGN WORK, which is where the judgement lives:
  - ${ROADMAP_DOC} — the sequenced redesign roadmap. If it exists, THIS IS YOUR
    SOURCE and your job is to select the next wave from it, not to re-derive it.
${AUDITS.map((a) => `  - ${a} — the independent audit it was built from.`).join('\n')}
${wave ? `\nThe orchestrator has named wave **${wave}**. Draw from it.` : ''}

If the roadmap does not exist yet, say so plainly and plan from the audits plus
your own measured walk of the app — but do NOT write the roadmap yourself. A
plan derived in passing is not the same artefact as a roadmap two independent
auditors converged on, and quietly substituting one for the other is how the
direction layer went dead here before.

FOR EACH ITEM, the plan must answer WHAT IT COSTS NOW AND WHAT IT COSTS AFTER:
  - \`costNow\`: gestures today, measured, with the journey you measured it on.
  - \`costAfter\`: gestures after, and what the user does INSTEAD. If the honest
    answer is "the same", the item can still be right — atmosphere, legibility
    and a readable next step are real wins the gesture count cannot see — but
    then SAY that is the win, so nobody later reports a flat number as failure.
  - \`acceptance\`: the e2e assertion that proves a user can do it the new way,
    through the real UI. Seeding over the API proves nothing about the path.
  - \`needsPrimitive\`: whether it needs a new or changed \`packages/design\`
    primitive. Be honest — a "just this once" local style is the DRY violation
    review rejects, and this flag is how the wave avoids three builders
    colliding in one package.

TERRITORY IS A HARD CONSTRAINT. Assign each item exactly one \`subtree\`, and NO
TWO ITEMS MAY SHARE ONE:
${available.map((t) => `  - ${t}`).join('\n')}
${occupied.length ? `\nOCCUPIED by builders live right now, unavailable this wave:\n${occupied.map((t) => `  - ${t}`).join('\n')}` : ''}
At most ONE item in the wave may claim a FOUNDATION — \`${FOUNDATION_SUBTREES.join('`, `')}\` —
and it will be built FIRST and ALONE, with the others starting from its commit.
A foundation item is not too big for the loop, it is merely un-parallelisable;
if the most valuable thing you can see lives in one, pick it and let it have the
wave. A SECOND foundation item in the same wave is deferred, not raced.
Return AT MOST ${Math.min(batchSize, available.length)} items. If a high-value
item cannot get a clean subtree, put it in \`deferred\` with its reason — it
leads the next wave rather than racing this one.

Give the wave a \`waveGoal\`: the ONE sentence a user would say about it if it
works. If you cannot write that sentence, the wave is a list of repairs rather
than a redesign, and you should re-pick.

You are read-only on app code. Do not implement anything, and do not touch
docs/BACKLOG.md or docs/ROADMAP.md.`,
    { label: 'cost', phase: 'Cost', agentType: 'frontend-qa', schema: PLAN },
  )
}

const items = (seedItems.length ? seedItems : (plan && plan.items) || []).slice(0, batchSize)

if (items.length === 0) {
  log(
    skipCost
      ? 'skipCost was set and no seedItems were passed — nothing to build. Pass args.items.'
      : plan
        ? 'The planner returned no items. That is a real result only if `deferred` explains it.'
        : 'The planner produced NO RESULT (died, or was skipped). This is not an empty roadmap.',
  )
  return { built: [], note: 'no wave to build' }
}

// One item per subtree. Serialising a clash is NOT handled here — the wave is
// trimmed instead, deliberately, because two builders in one subtree is the
// overwrite class this org has already paid for.
const byTree = new Map()
for (const it of items) if (!byTree.has(it.subtree)) byTree.set(it.subtree, it)
const batch = [...byTree.values()]
if (batch.length < items.length) {
  log(`::warning:: ${items.length - batch.length} item(s) shared a subtree and were trimmed.`)
}

const goal = (plan && plan.waveGoal) || (args && args.waveGoal) || '(no wave goal stated)'
log(`wave goal: ${goal}`)
log(`wave: ${batch.map((i) => `${i.id}[${i.subtree}]`).join(', ')}`)

// --- Direction --------------------------------------------------------------
// The phase that makes this a redesign loop rather than a repair loop. See note
// 1 in the header: N builders each deciding independently produce N dialects,
// and that failure passes every per-item review because each dialect is
// internally coherent.
//
// It does NOT barrier the wave. "Never barrier shipping on planning" is a
// standing rule here, earned; if this agent dies, the builders fall back to the
// roadmap and the mandate, which is worse but not stopped.
let direction = null
if (!skipDirection) {
  phase('Direction')
  direction = await agent(
    `Fix the DESIGN DECISIONS for this redesign wave, before any builder starts.

Wave goal: **${goal}**

Items, each going to a different builder working in parallel:
${batch.map((i) => `  - ${i.id} — ${i.title}\n      subtree: ${i.subtree}\n      surface: ${i.surface}\n      cost now: ${i.costNow}\n      cost after: ${i.costAfter}`).join('\n')}

WHY YOU EXIST. Those builders are about to make aesthetic and interaction
decisions independently. Each will produce something internally coherent, each
will pass its own design review, and together they will produce three dialects
of this product — which is precisely the "templated, unintentional" result the
founder has already rejected once. Your job is to make the decisions ONCE so
they can be applied three times. You are buying boldness, not rationing it: a
strong choice survives being implemented by three hands, and does not survive
being averaged across three authors.

Invoke the \`frontend-design\` skill first — this is exactly the brief it is for.
Then read ${ROADMAP_DOC} and the audits behind it if they exist, and go LOOK at
the running app; decide against what is there, not against what you imagine.

DECIDE, concretely enough that a builder cannot reasonably diverge:
  1. **The gesture grammar.** What does a drag handle look like in this product
     — shape, colour, hover state, what it does on grab, what the readout says
     while dragging, where the numeric fallback lives, what Esc does mid-drag.
     Decide it ONCE. This is the mandate's single biggest named gap and the
     wave will introduce several handles at once; they must be the same object.
  2. **The token moves.** Any palette / type / spacing / elevation change the
     wave needs, named as tokens in \`packages/design\`, with the old value and
     the new one. If the wave needs no token change, say so — that is a
     legitimate and cheap answer.
  3. **The signature element.** The mandate says spend boldness in ONE place and
     keep the rest disciplined. Say where it is spent in this wave, and — just
     as important — where it is deliberately NOT.
  4. **What proposes the next step.** For each item, what makes the affordance
     appear at the moment it is useful. "The user opens a menu and finds it" is
     a FAILING answer.
  5. **THE FILE EVERY ITEM NEEDS AND NO ITEM OWNS.** Find it before the builders
     do. A redesign wave lands on several surfaces that are wired together
     somewhere — a page component, a router, a layout — and that seam belongs to
     no subtree, so the territory rule tells EVERY builder to stop and report
     rather than reach across. Three builders each correctly refusing to proceed
     is a deadlocked wave, and the failure looks like three well-behaved agents.
     So: name the file, allocate it BY EXACT LINE ANCHOR per item, and say which
     item commits FIRST so the others build against a landed seam rather than a
     promised one. If two items genuinely need the same hunk, they are one item
     and you should say so.
     Watch for the other half of that shape too — a CONTRACT SPLIT ACROSS TWO
     BUILDERS where each half is inert alone and the pair is silently wrong if
     either is missed. Write it into both briefs in the same words, and say what
     the broken state looks like, because "looks almost right" is what makes it
     survive review.
  6. **What must NOT change.** Name the muscle memory this wave is forbidden to
     break: existing hotkeys, the meaning of Esc and Enter, the position of
     anything a user's hand already goes to without looking. A redesign that
     costs an existing user their reflexes has lost more than it won.

Deliver it as a short, decisive brief a builder can implement from — not an
essay, not options. Where you genuinely cannot decide without seeing it built,
say which ONE thing that is and what the builder should try first.

You are read-only on app code. Write your brief to
\`docs/design/DIRECTION-${(goal || 'wave').slice(0, 24).replace(/[^a-zA-Z0-9]+/g, '-').toLowerCase()}.md\`
as you go, so it survives if you are cut off, and return it.`,
    { label: 'direction', phase: 'Direction', agentType: 'frontend-qa' },
  )
}

const DIRECTION_BLOCK = direction
  ? `\nTHE WAVE'S DESIGN DIRECTION — decided for you, implement against it:\n${String(direction).slice(0, 6000)}\n`
  : `\nNO DIRECTION BRIEF WAS PRODUCED (the agent died or was skipped). Fall back to
${ROADMAP_DOC} and the design mandate, and say in your report that you were
deciding without one — a wave built this way is at risk of diverging from its
siblings, and the orchestrator needs to know to look for that.\n`

// --- System -----------------------------------------------------------------
// If the wave needs a primitive, it lands FIRST and ALONE. See note 2: three
// builders in `packages/design` at once is the overwrite class, and the cheap
// escape from it (each patching its own instance) is the DRY violation review
// rejects. Serialising one item is much cheaper than either.
const needsSystem = batch.filter(
  (i) => FOUNDATION_SUBTREES.includes(i.subtree) || i.needsPrimitive,
)
const systemItem = needsSystem[0] || null

// MORE THAN ONE item wanting the design system is the collision this phase
// exists to prevent, arriving one level up: serialising the first and letting
// the rest run would put them straight back into `packages/design` together,
// which is the overwrite class. Defer them — a wave is cheaper than an overwrite.
const collide = needsSystem.slice(1)
if (collide.length) {
  log(
    `::warning:: ${collide.length} further item(s) also need the design system ` +
      `(${collide.map((i) => i.id).join(', ')}). Serialising only the first would put ` +
      'the rest back into packages/design together. They are DEFERRED to the next ' +
      'wave — re-plan them against the primitive this one lands.',
  )
}
const rest = batch.filter((i) => i !== systemItem && !collide.includes(i))
let systemSha = null

if (systemItem) {
  phase('System')
  // The foundation the item claims, if it named one; otherwise the design system,
  // which is what `needsPrimitive` without a foundation subtree means.
  const foundation = FOUNDATION_SUBTREES.includes(systemItem.subtree)
    ? systemItem.subtree
    : SYSTEM_SUBTREE
  log(`foundation change lands first and alone: ${systemItem.id} in ${foundation} (${systemItem.primitive || 'unnamed'})`)
  const built = await agent(
    `Land the FOUNDATION half of this redesign wave, alone, before the others start.

Item: **${systemItem.title}** (${systemItem.id})
Foundation: \`${foundation}\` — ${systemItem.primitive || '(the plan did not name the primitive or store slice — name it in your report)'}
Cost now: ${systemItem.costNow}
Cost after: ${systemItem.costAfter}
Acceptance: ${systemItem.acceptance}
${DIRECTION_BLOCK}
YOUR TERRITORY IS \`${foundation}\` plus the surfaces that consume what you
change, and nothing else. You have the wave to yourself precisely BECAUSE this
work cannot be fenced into one subtree — that is what makes it a foundation, not
what makes it too big.

You are going FIRST and ALONE on purpose. ${rest.length} builder(s) start from
your commit the moment you push, so two things matter more than usual:
  - **Push the moment you are green.** Siblings are blocked on your SHA. A
    perfect commit you are still polishing is worse for this wave than a good
    one they can build on.
  - **Prefer an ADDITIVE change.** Every call site you touch is a file a sibling
    may also hold, and a breaking change is a cost you are choosing on their
    behalf. A new primitive beside the old one, or a new store slice rather than
    a changed signature, costs you a follow-up and costs them nothing. List every
    file you touched outside your own subtree so the orchestrator can warn
    whoever owns it.
  - **Restart Vite before you believe any mutation test.** Editing a
    \`packages/design\` primitive under a running Vite can serve a STALE
    transform, so the mutation passes when it must have failed — that is a wrong
    CONCLUSION, not a wrong run, and it is the one trap that costs you the fix
    rather than the time.

Your report MUST end with the pushed SHA on its own line, as \`SHA: <sha>\`.
${STANDARD}
Report: the primitive's API, the diff stat, the mutation evidence, any call site
you touched outside the package, and a screenshot at 1280x800.`,
    {
      label: `system:${systemItem.id}`,
      phase: 'System',
      agentType: 'frontend-builder',
      isolation: 'worktree',
    },
  )
  const m = String(built || '').match(/SHA:\s*([0-9a-f]{7,40})/i)
  systemSha = m ? m[1] : null
  log(
    systemSha
      ? `design system landed at ${systemSha}; builders will start from it`
      : '::warning:: the system item reported NO SHA. Builders will start from the branch tip,' +
          ' which may not carry the primitive — treat a builder complaint about a missing' +
          ' component as THIS, not as their mistake.',
  )
}

// --- Build -> Design --------------------------------------------------------
// A PIPELINE: each item's design review starts the moment its build lands,
// rather than waiting for the slowest builder. Nothing downstream needs
// cross-item context — that is what the QA barrier below is for.
const done = await pipeline(
  rest,
  (it) =>
    agent(
      `Redesign this surface: **${it.title}** (${it.id}).

This is a REDESIGN item, not a feature request. The capability very likely
already exists and already works. What is wrong is what it COSTS and how it
FEELS, so "it works now" is not the finish line and a passing spec is not
evidence you succeeded.

  cost now:   ${it.costNow}
  cost after: ${it.costAfter}
  surface:    ${it.surface}
  acceptance: ${it.acceptance}

Wave goal: ${goal}
${DIRECTION_BLOCK}
Treat the direction as decided, and the cost targets as the point. If building
it shows a decision is wrong, say so in your commit message and do the better
thing — you are the one who will see it move under the hand. But do not diverge
QUIETLY: a sibling is implementing the same grammar in another subtree, and an
undocumented improvement in yours becomes an inconsistency in theirs.

**Ship the e2e that drives the NEW path through the real UI in the same commit**,
and where you removed gestures, make the spec take the short route so
\`check-flow-cost.py\` measures the path you actually built. Where you replaced a
form with a handle, keep a spec on the numeric fallback too — the precision path
is not a legacy path, it is half the feature.

YOUR TERRITORY IS \`${it.subtree}\` AND NOTHING ELSE. Other builders are live in
the sibling subtrees this wave. If the work genuinely requires a file outside it,
STOP and report that rather than reaching across — a clean hand-off costs one
wave, an overwrite costs two agents' work.
${systemSha ? `\nSTART FROM \`${systemSha}\` — the wave's design-system change. \`git fetch origin ${branch} && git reset --hard ${systemSha}\`. If the primitive you need is not there, say so and stop; do not reimplement it locally.\n` : ''}${STANDARD}
Report: the mechanism, the diff stat, the e2e driving the new path, the mutation
evidence, the before/after gesture count for your journey, and before/after
screenshots at 1280x800.`,
      {
        label: `build:${it.id}`,
        phase: 'Build',
        agentType: 'frontend-builder',
        isolation: 'worktree',
      },
    ),
  // BOTH reviews, in parallel, on the same build. The design review and the CODE
  // review ask different questions and neither substitutes for the other — a
  // surface can flow beautifully over a race condition, and correct code can be
  // a dialect of its own.
  //
  // The code review was MISSING from this loop as first written, and from its
  // sibling `loft-frontend-loop` too: both went builder -> frontend-qa -> QA, so
  // nobody read the diff for correctness. That is the exact omission the ORG loop
  // already paid for and fixed on 2026-08-14, when an engineering audit measured
  // three of the last five commits landing with no review and no QA — and Wave 0
  // reintroduced it, shipping ~1900 lines of product code past a design review
  // and a functional QA with no code review at all. `frontend-qa` is read-only on
  // app code and judges the SURFACE; it is not a reviewer of diffs and was never
  // meant to be.
  (build, it) =>
    parallel([
      () =>
        agent(
          `Code review of ${it.id} (${it.title}), just landed in \`${it.subtree}\`.

Builder's report:
${String(build || '(no report — the agent may have died; check git log for its commits)').slice(0, 4000)}

Read the DIFF, not the report. The report is the builder's account of what it
meant to do; your job is what it actually did.

This is REDESIGN work, so weight the review accordingly:
  - **A redesign rewrites the DOM, and the test hooks go with it.** Diff the
    \`data-testid\`s, roles and accessible names on every touched surface against
    their previous state and say whether the set is intact. A dropped
    \`part-health\` once turned the whole suite red.
  - **Fix the primitive, never the instance.** A local style or a copied
    component where \`packages/design\` already has one is a DRY defect here, and
    it is the cheap escape a builder reaches for when the design system is held
    by somebody else.
  - **The mutation evidence.** The builder claims a gate that can fail. Re-run it
    yourself: revert the fix, watch the assertion redden, restore. Five gates
    that could not fail have shipped in this repo, and the fifth was found only
    because someone ran the mutation and it PASSED — so ask "could this fixture
    have reddened at all", not "did they say they ran it".
  - Typing discipline, service boundaries, and any \`any\` without justification.

You are read-only on app code. Return blocking issues plainly and separately
from nits, and say explicitly if you found nothing — a review that reports
nothing because it looked at nothing is the failure mode here.`,
          { label: `review:${it.id}`, phase: 'Review', agentType: 'code-reviewer' },
        ),
      () =>
        agent(
          `Design review of ${it.id} (${it.title}), just landed in \`${it.subtree}\`.

Builder's report:
${String(build || '(no report — the agent may have died; check git log for its commits)').slice(0, 4000)}

Walk the flow yourself in the running app. Lead with the two questions this loop
exists for, in this order:

  1. **Does it cost less than it did?** The claim is "${it.costAfter}" against
     "${it.costNow}". Count it yourself. A redesign that moved the pixels and not
     the gesture count has to justify itself on legibility or atmosphere
     explicitly — which is a legitimate win, but it must be CLAIMED, not assumed.
  2. **Is it the same product as its siblings?** ${direction ? 'A direction brief was fixed for this wave — check the build against it, and report any drift by name, including drift the builder improved on without saying so.' : 'NO direction brief was produced this wave, so divergence is likely — compare this surface against the ones its siblings touched and report anything that reads as a different dialect.'}

Then the mandate:
  - Direct manipulation present, with the numeric field as the fallback rather
    than the only route?
  - Does the affordance appear at the moment it is useful, or must it be hunted?
  - Does the surface still read as a quiet precision instrument, or has a control
    been bolted on where there was room rather than where it belongs?
  - **Test hooks: same set as before?** Inventory them, do not eyeball it.
  - Contrast, visible focus, reduced motion, 1280x800?

You are read-only on app code. File what you find to \`docs/UI-REVIEW.md\` and
return the blocking issues plainly. A finding that it works but does not FLOW is
exactly what you are here for.`,
          { label: `design:${it.id}`, phase: 'Design', agentType: 'frontend-qa' },
        ),
    ]),
)

// --- QA ---------------------------------------------------------------------
// One pass over the whole wave, deliberately. At this point the interesting
// failures are INTERACTIONS between redesigned surfaces, which per-item review
// cannot see by construction. This is the one place a barrier earns its cost.
phase('QA')
const qa = await agent(
  `Independent QA of this frontend REDESIGN wave, in a REAL browser against the REAL stack.

Wave goal: ${goal}
Items: ${batch.map((i) => `${i.id} in ${i.subtree}`).join('; ')}

A redesign wave fails differently from a feature batch, so look in the places
per-item review cannot reach:

  1. **Did anything a user already relied on stop working?** This is the first
     question, not the last. Hotkeys, Esc/Enter meaning, the position of
     controls a hand goes to without looking, every \`data-testid\` and
     accessible name on the touched surfaces. Redesigns break muscle memory and
     test hooks silently — a dropped \`part-health\` turned the whole suite red.
  2. **Do the redesigned surfaces read as ONE product?** Put them side by side.
     Two new handles with different grab affordances, two panels with different
     density, two readouts with different number formatting — each defensible
     alone, together they are the templated look the founder rejected.
  3. **Do the new affordances interfere?** Two modes competing for the same
     selection, a new hotkey shadowing an existing one, the command band
     overflowing at 1280x800 now that it carries more.
  4. **Then model a real part end to end** — plate, two holes, a fillet, edit a
     parameter, export — and say whether it is SEAMLESS. Count the gestures and
     report the number. That is the founder's actual standard.

Boot natively per CLAUDE.md — the Docker registry is 403-blocked — on SQLite
files prefixed with your own agent slug, from fresh files. Kill stray Vite and
stale \`*.main:app\` uvicorns before your run, scoped to YOUR OWN ports via
\`lsof -ti\`: a stale Vite on :5173 makes every spec 500 at register and reads as
a total regression, and a process-name grep kills every sibling's stack.

Run in a QUIET window and report the load average. A red run under load is
UNCONFIRMED, not evidence. The discriminator: a real regression fails
IDENTICALLY every time; a contention flake MOVES. And a control run under the
same load is not a control — establish a pass rate on a quiet machine first.

File defects to the board's usual place. Do not fix app code.`,
  { label: 'qa:wave', phase: 'QA', agentType: 'qa-tester' },
)

// --- Evidence ---------------------------------------------------------------
// The mandate says UI work ships with before/after screenshots SURFACED TO THE
// FOUNDER, and that generating a PNG nobody sees does not count. That kept being
// remembered by hand, so it is a phase.
phase('Evidence')
// Count and report what ACTUALLY ran. The first version of this returned
// `batch` — every item the planner proposed — so a wave that deferred an item
// for colliding on the design system still reported it as shipped, and the
// orchestrator would have gone looking for a commit that does not exist. A
// report that overstates what landed is worse than no report: it is the one
// failure nobody downstream can detect.
const attempted = (systemItem ? [systemItem] : []).concat(rest)
const shipped = done.filter(Boolean).length + (systemItem ? 1 : 0)
log(`built ${shipped}/${attempted.length} attempted (${collide.length} deferred) — ` +
    're-run `python3 scripts/check-flow-cost.py` for the delta')
log(
  'A FLAT OR RISING NUMBER IS NOT AUTOMATICALLY A FAILURE, and a falling one is' +
    ' not automatically a win: the count is gamed by editing the spec instead of' +
    ' the app, and a wave can legitimately buy atmosphere or legibility instead' +
    ' of gestures. Report the delta WITH the diff that caused it, or not at all.',
)

return {
  waveGoal: goal,
  //: What this wave actually attempted — NOT what the planner proposed.
  items: attempted.map((i) => ({
    id: i.id,
    subtree: i.subtree,
    costNow: i.costNow,
    costAfter: i.costAfter,
  })),
  systemSha,
  deferred: [
    ...((plan && plan.deferred) || []),
    ...collide.map(
      (i) => `${i.id} — deferred: a second item needing packages/design would have raced ${systemItem ? systemItem.id : 'the system item'}`,
    ),
  ],
  directionBriefed: !!direction,
  qa,
  // The orchestrator owes the founder these, and all three get forgotten.
  orchestratorTodo: [
    'read CI for each pushed commit (ci.yml, e2e.yml AND deploy-path.yml) and relay failures to the owning agent',
    'SEND the founder the before/after screenshots with the file-send tool — a PNG in docs/screenshots/ that nobody sees does not count',
    're-run scripts/check-flow-cost.py and report the delta NEXT TO the diff that caused it',
    'feed the wave outcome back into docs/design/REDESIGN-ROADMAP.md — the roadmap is the loop\'s memory, and a wave that does not update it makes the next planner re-derive everything',
  ],
}
