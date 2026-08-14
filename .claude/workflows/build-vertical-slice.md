# Workflow: build-vertical-slice

Take ONE handed-in ticket from implementation → review → verification. Run with
the Claude Code `Workflow` tool.

## Inputs — the orchestrator supplies these; there is no Pick and no Plan

```
args = {
  id, title,
  ticket,      // mechanism + fix + acceptance criteria, verbatim from the board
  agentType,   // kernel-architect | backend-builder | frontend-builder | platform-builder
  territory,   // explicit file globs this agent may write
}
```

**Pick and Plan were removed 2026-08-14.** Measured over two runs of the
7-phase predecessor: SEL-6 took 7 agents / 536 tool calls / 1.18M subagent
tokens / 3h19m, and SEL-7 took 7 agents / 506 calls / 1.12M tokens / 3h33m —
for one item each. A single targeted builder sent at SEL-7's blocking review
finding cost 62 calls / 132k tokens / 17 minutes and returned a *better* fix
than its brief asked for.

Pick re-read the backlog to choose the top unchecked item — a `grep` answers
that — and died twice on the harness's parameter-stripping fault, burning ~132k
tokens for nothing. Plan restated acceptance criteria the board entry already
carried, against this repo's own rule that briefs should *point at* criteria
rather than restate them.

The better reason is collision: when the orchestrator hands out the ticket it
also hands out the **territory**, so two live agents cannot be aimed at the same
files. Pick chose its own item and therefore its own files.

## Phases

1. **Build** — the specialist named in `agentType`, in its **own worktree**
   (`isolation: 'worktree'`). Implements, reviews its own diff, and QAs against
   the real running stack. Commits only if green; leaves the work on its branch.
2. **Review** — `code-reviewer` reads the pushed SHAs. Correctness first, then
   DRY, service boundaries, typing, licence hygiene. **It re-runs the builder's
   mutation evidence itself** on anything load-bearing, and checks every factual
   claim the diff adds to the record.
3. **Verify** — `qa-tester` (plus `geometry-qa` when kernel-adjacent) exercises
   the real artifact and asks the question the builder's own gate structurally
   cannot. Mutation-verifies every assertion it adds.

Review and Verify are **not optional** and were deliberately kept when Pick and
Plan went. They are the phases that have caught real defects here: a reticle
dimmed to 2.98:1 (below the WCAG 1.4.11 floor); a unit test that tested its own
helper, proved by deleting the app code and watching all 1584 tests stay green;
and a farthest-hit mutation that left every measured fraction unchanged,
catchable only by an occluded-share control.

## Standard the builder is held to

- **An assertion never seen to fail is not a gate.** Build the mutation, run it,
  quote the red output, revert, confirm green.
- **A claim that is not true is a defect**, including in a comment. Every number
  must be measured; an inherited claim must be re-derived before it is repeated.
- **Doc edits are the LAST step**, then staged and committed in the same turn.

## Done when

`just lint` + typecheck + unit green, geometry gates green when kernel-adjacent,
e2e green when user-facing, ROADMAP/BACKLOG ticked in the same commit, branch
integrated, and CI green on the pushed commit.
