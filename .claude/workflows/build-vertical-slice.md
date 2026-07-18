# Workflow: build-vertical-slice

Take one backlog item from contract → services → UI → verification in
coordinated phases. Run with the Claude Code `Workflow` tool.

## Inputs
`args = { item: "<backlog item title + acceptance criteria>", notes?: "<constraints>" }`

## Phases

1. **Plan** — one agent reads `docs/ROADMAP.md`, `docs/RESEARCH.md`,
   `docs/ARCHITECTURE.md`, and the relevant service code; produces a concrete
   slice plan: DTO/contract changes, which services move, kernel work y/n,
   UI surfaces, acceptance checks. Schema-validated output.
2. **Kernel** — `kernel-architect` implements geometry-service work (skipped
   when the item isn't kernel-adjacent). Must pass geometry gates.
3. **Backend** — `backend-builder` implements gateway/documents/py-kit work;
   regenerates contracts + ts-client (`just gen`). Must pass `just lint` +
   unit tests.
4. **Frontend** — `frontend-builder` implements the UI against the fresh
   ts-client. Must typecheck and build.
5. **Review** — `code-reviewer` reviews the full diff; 🔴/🟡 findings go back
   to the owning builder and are fixed before proceeding.
6. **Verify** — `qa-tester` drives the real stack (desktop + touch) against
   the acceptance checks; `geometry-qa` runs golden/round-trip gates when
   phase 2 ran. Fail → back to the owning builder, max two loops, then stop
   and surface.

## Done when

Both sides build, all gates green, flow proven in a running stack,
ROADMAP + BACKLOG ticked, committed with a conventional message (files staged
explicitly), pushed.

## Script outline

```js
export const meta = {
  name: 'build-vertical-slice',
  description: 'Implement one Loft backlog item end-to-end',
  phases: [{title:'Plan'},{title:'Kernel'},{title:'Backend'},{title:'Frontend'},{title:'Review'},{title:'Verify'}],
}
phase('Plan')
const plan = await agent(`Plan the slice for: ${args.item}. ${args.notes ?? ''}`, {schema: PLAN_SCHEMA})
phase('Kernel')
if (plan.kernel) await agent(`Implement geometry-service work: ${JSON.stringify(plan.kernel)}`, {agentType:'kernel-architect'})
phase('Backend')
if (plan.backend) await agent(`Implement backend + regen contracts: ${JSON.stringify(plan.backend)}`, {agentType:'backend-builder'})
phase('Frontend')
if (plan.frontend) await agent(`Implement UI: ${JSON.stringify(plan.frontend)}`, {agentType:'frontend-builder'})
phase('Review')
const review = await agent('Review the current diff.', {agentType:'code-reviewer', schema: REVIEW_SCHEMA})
// route 🔴/🟡 fixes to the owning builder, then:
phase('Verify')
await agent(`QA against acceptance criteria: ${args.item}`, {agentType:'qa-tester'})
if (plan.kernel) await agent('Run golden-model + round-trip gates on the touched capabilities.', {agentType:'geometry-qa'})
```
