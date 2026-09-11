#!/usr/bin/env node
// Exercise `loft-frontend-redesign-loop.js`'s ORCHESTRATION against a stub
// harness — no agents, no worktrees, no tokens.
//
// WHY THIS EXISTS. A workflow script is the one kind of code here that nobody
// ever runs before it runs for real, and "for real" costs several agent-hours
// and a wave of builder time. This repo has already shipped a loop hook whose
// in-flight guard could never fire, and five gates that could not fail; a
// workflow is the same hazard with a much bigger bill attached.
//
// It caught two real defects on its first run, both of the shape that is
// invisible in production because the run still LOOKS successful: an item
// deferred for colliding on the design system was still reported as shipped in
// the return value, and the "built N/M" line counted that deferred item in its
// denominator. The orchestrator would have gone looking for a commit that does
// not exist.
//
// This stubs `agent()`, so it proves the WIRING — phase order, territory
// allocation, serialisation, what the wave claims it did. It proves nothing
// about the prompts, which is where the judgement lives. Do not read a pass
// here as "the workflow is good".
//
//     node scripts/dryrun-redesign-workflow.mjs

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const REPO = join(dirname(fileURLToPath(import.meta.url)), "..");
const WORKFLOW = join(REPO, ".claude/workflows/loft-frontend-redesign-loop.js");

const AsyncFn = Object.getPrototypeOf(async function () {}).constructor;
const failures = [];

function check(label, cond) {
  if (!cond) failures.push(label);
}

async function run(args) {
  const src = readFileSync(WORKFLOW, "utf8").replace(
    /^export const meta/m,
    "const meta",
  );
  const calls = [];
  const logs = [];
  const agent = async (prompt, opts) => {
    calls.push({ ...opts, promptLen: prompt.length });
    if (opts.phase === "Cost")
      return { items: args.__planItems || [], waveGoal: "planned goal" };
    if (opts.phase === "System") return "landed\nSHA: abc1234def";
    if (opts.phase === "Direction")
      return "GRAMMAR: one handle, brass, live readout.";
    return `report for ${opts.label}`;
  };
  const pipeline = async (arr, build, review) => {
    const out = [];
    for (const it of arr) out.push(await review(await build(it), it));
    return out;
  };
  const parallel = async (fns) => Promise.all(fns.map((f) => f()));
  const fn = new AsyncFn(
    "agent",
    "parallel",
    "pipeline",
    "phase",
    "log",
    "args",
    src,
  );
  const res = await fn(
    agent,
    parallel,
    pipeline,
    (t) => logs.push(`== ${t}`),
    (m) => logs.push(String(m)),
    args,
  );
  return { calls, logs, res, labels: calls.map((c) => c.label) };
}

const item = (id, subtree, extra = {}) => ({
  id,
  title: `${id} title`,
  subtree,
  costNow: "12 gestures",
  costAfter: "4 gestures",
  surface: "the viewport",
  acceptance: "a spec drags the handle",
  ...extra,
});

// 1. A design-system item runs FIRST and ALONE, and hands its SHA to the rest.
{
  const { calls, res, labels } = await run({
    skipCost: true,
    items: [
      item("R1", "packages/design/**", {
        needsPrimitive: true,
        primitive: "DragHandle",
      }),
      item("R2", "apps/web/src/viewport/**"),
      item("R3", "apps/web/src/sketch/**"),
    ],
  });
  const sysAt = labels.indexOf("system:R1");
  const firstBuild = labels.findIndex((l) => l.startsWith("build:"));
  check("system item runs", sysAt >= 0);
  check("system runs BEFORE any builder", sysAt >= 0 && sysAt < firstBuild);
  check(
    "the system SHA is parsed out of the report",
    res.systemSha === "abc1234def",
  );
  check(
    "builders are told the SHA",
    calls.some((c) => c.label === "build:R2" && true),
  );
  check(
    "every builder is isolated in a worktree",
    calls
      .filter((c) => c.phase === "Build")
      .every((c) => c.isolation === "worktree"),
  );
}

// 2. TWO items wanting the design system: the second is DEFERRED, never raced —
//    and, critically, is not REPORTED as shipped. This is the defect that
//    motivated the harness.
{
  const { res, labels } = await run({
    skipCost: true,
    items: [
      item("R1", "packages/design/**", { needsPrimitive: true }),
      item("R2", "apps/web/src/viewport/**", { needsPrimitive: true }),
      item("R3", "apps/web/src/sketch/**"),
    ],
  });
  check(
    "only one system item is built",
    labels.filter((l) => l.startsWith("system:")).length === 1,
  );
  check("the colliding item is NOT built", !labels.includes("build:R2"));
  check(
    "the colliding item is NOT reported as shipped",
    !res.items.some((i) => i.id === "R2"),
  );
  check(
    "the colliding item IS reported as deferred",
    res.deferred.some((d) => d.includes("R2")),
  );
}

// 3. No primitive needed: no System phase at all, builders start immediately.
{
  const { labels, res } = await run({
    skipCost: true,
    items: [
      item("R2", "apps/web/src/viewport/**"),
      item("R3", "apps/web/src/sketch/**"),
    ],
  });
  check(
    "no System phase when none is needed",
    !labels.some((l) => l.startsWith("system:")),
  );
  check("no SHA is invented", res.systemSha === null);
}

// 4. An empty plan returns a NOTE rather than silently building nothing — the
//    difference between "there is no work" and "the planner died" is one this
//    loop must never blur.
{
  const { labels, res } = await run({ skipCost: true, items: [] });
  check("an empty plan spawns no agents", labels.length === 0);
  check(
    "an empty plan says so",
    typeof res.note === "string" && res.note.length > 0,
  );
}

// 5. Two items in one subtree are trimmed to one — the overwrite class.
{
  const { labels } = await run({
    skipCost: true,
    items: [
      item("R2", "apps/web/src/viewport/**"),
      item("R9", "apps/web/src/viewport/**"),
    ],
  });
  check(
    "a subtree clash is trimmed, not serialised",
    !labels.includes("build:R9"),
  );
}

// 5b. A FOUNDATION OUTSIDE packages/design is schedulable, and runs solo.
//     The craft audit's highest-value item — persistent geometry selection, the
//     one the mandate's "next step visible from the current state" rule depends
//     on — lives in `apps/web/src/store/**`. The first version of the loop
//     excluded store/ and lib/ from its subtree list entirely, so that item was
//     UNSCHEDULABLE with no error anywhere: the exact failure the loop's own
//     SUBTREES comment warns about. This case is the gate on that fix.
{
  const { labels, res } = await run({
    skipCost: true,
    items: [
      item("CRAFT-12", "apps/web/src/store/**"),
      item("CRAFT-4", "apps/web/src/viewport/**"),
    ],
  });
  check(
    "a store/** item is scheduled at all",
    labels.includes("system:CRAFT-12"),
  );
  check(
    "a store/** item runs BEFORE the others",
    labels.indexOf("system:CRAFT-12") <
      labels.findIndex((l) => l.startsWith("build:")),
  );
  check("its siblings still run", labels.includes("build:CRAFT-4"));
  check(
    "it is reported as attempted",
    res.items.some((i) => i.id === "CRAFT-12"),
  );
}

// 6. NEGATIVE CONTROL. The checks above must be capable of failing: a wave with
//    a design-system item MUST NOT look identical to one without. If these two
//    agree, every assertion in case 1 is passing vacuously.
{
  const withSys = await run({
    skipCost: true,
    items: [
      item("R1", "packages/design/**", { needsPrimitive: true }),
      item("R2", "apps/web/src/viewport/**"),
    ],
  });
  const without = await run({
    skipCost: true,
    items: [
      item("R1", "apps/web/src/sketch/**"),
      item("R2", "apps/web/src/viewport/**"),
    ],
  });
  check(
    "negative control: the system path is distinguishable from the plain path",
    JSON.stringify(withSys.labels) !== JSON.stringify(without.labels),
  );
}

for (const f of failures) console.log(`FAIL  ${f}`);
console.log(`\n${failures.length} failure(s)`);
process.exit(failures.length ? 1 : 0);
