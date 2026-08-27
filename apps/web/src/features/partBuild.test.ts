/**
 * The part workspace's build facts — the derivation three surfaces now share.
 *
 * The bug being fenced (AUDIT-ENGINEERING J2): with one broken feature the same
 * screen read "Failed" (Solve), "Up to date" (Status) and "Ready" (Export), and
 * that last one is a wrong FILE, not a wrong label — the strict-prefix rule
 * returns a mesh for the last-good prefix, so a user could download a STEP that
 * silently omitted every feature from the failure onward. All four existing
 * `body-status` assertions were happy-path, which is exactly why it shipped.
 *
 * So the tests here are the NON-happy paths, and the last block asserts the
 * invariant that made the defect possible in the first place: the three cells
 * must not be able to disagree.
 */
import { describe, expect, it } from "vitest";

import {
  bodyStatusReadout,
  excludedNote,
  exportGate,
  isStaleForTree,
  partialBodySentence,
  registerHealthReadout,
  skippedReason,
  solveSummary,
} from "./partBuild";
import {
  brokenFillet,
  cleanCube,
  justWritten,
  makeBuild,
  makeEvaluation,
  makePart,
  makeTree,
  midWrite,
  rolledBack,
  strandedDownstream,
  unverified,
} from "../test/partBuildFixture";

describe("isStaleForTree", () => {
  it("is fresh only when the versions match", () => {
    expect(isStaleForTree({ builtFromTreeVersion: 7, treeVersion: 7 })).toBe(
      false,
    );
    expect(isStaleForTree({ builtFromTreeVersion: 6, treeVersion: 7 })).toBe(
      true,
    );
  });

  it("calls a FUTURE version stale too — undo/redo also bumps the counter", () => {
    // py_kit's `is_stale_for_tree` compares by INEQUALITY for this reason: a
    // body stamped with a version the part never reached is as unusable as an
    // old one. A `<` here would silently trust it.
    expect(isStaleForTree({ builtFromTreeVersion: 9, treeVersion: 7 })).toBe(
      true,
    );
  });
});

describe("derivePartBuild — provenance", () => {
  it("is not stale while the part row merely LAGS the tree it just wrote", () => {
    // Every local mutation refetches the tree and re-evaluates; the part row is
    // refreshed on focus, so it trails by design. Comparing against the newest
    // version anyone reported is what keeps that from reading as staleness.
    const build = makeBuild({
      tree: makeTree(["Sketch1", "Extrude1"], { treeVersion: 8 }),
      part: makePart(3),
      evaluation: makeEvaluation(["ok", "ok"], { treeVersion: 8 }),
    });
    expect(build.stale).toBe(false);
    expect(build.currentTreeVersion).toBe(8);
    expect(bodyStatusReadout(build).status).toBe("up-to-date");
  });

  it("learns the tree moved from the part row alone (the concurrent edit)", () => {
    const build = unverified();
    expect(build.builtFromTreeVersion).toBe(3);
    expect(build.currentTreeVersion).toBe(4);
    expect(build.stale).toBe(true);
    expect(build.unverified).toBe(true);
    expect(bodyStatusReadout(build).status).toBe("unverified");
  });

  it("says Solving… rather than Unverified while the answer is on its way", () => {
    const solving = makeBuild({
      tree: makeTree(["Sketch1", "Extrude1"], { treeVersion: 4 }),
      part: makePart(4),
      evaluation: makeEvaluation(["ok", "ok"], { treeVersion: 3 }),
      evaluating: true,
    });
    expect(solving.stale).toBe(true);
    expect(solving.unverified).toBe(false);
    expect(bodyStatusReadout(solving).label).toBe("Solving…");

    const refetchingTree = makeBuild({
      tree: makeTree(["Sketch1", "Extrude1"], { treeVersion: 4 }),
      part: makePart(4),
      evaluation: makeEvaluation(["ok", "ok"], { treeVersion: 3 }),
      treeFetching: true,
    });
    expect(refetchingTree.unverified).toBe(false);
  });

  it("stops claiming to be current the moment a write is issued (QA-R4)", () => {
    // The measured defect: part, tree and evaluation all read version 7 while
    // the app holds a write it KNOWS supersedes the body, so every readout said
    // "up to date" about the previous part's mass for ~600-840 ms.
    const build = midWrite();
    expect(build.builtFromTreeVersion).toBe(7);
    expect(build.currentTreeVersion).toBe(7);
    // No cache has moved, so the version comparison alone cannot see this.
    expect(build.stale).toBe(false);
    expect(build.activity).toBe("solving");
    expect(bodyStatusReadout(build).status).not.toBe("up-to-date");
    expect(bodyStatusReadout(build).label).toBe("Solving…");
    expect(solveSummary(build)).toBe("Solving…");
  });

  it("takes the denominator from the write's own reply, ahead of both caches", () => {
    // The provenance half, standing alone: the reply said 8, the caches still
    // say 7, and nothing is in flight to explain it away.
    const build = justWritten();
    expect(build.currentTreeVersion).toBe(8);
    expect(build.stale).toBe(true);
    expect(build.unverified).toBe(true);
    expect(bodyStatusReadout(build).status).toBe("unverified");
    expect(exportGate(build).state).toBe("unverified");
  });

  it("keeps the highest version anyone reported, whichever source it was", () => {
    // A write reply cannot pull the denominator BACKWARDS past a cache that has
    // already learned about a later edit — `newestTreeVersion` is a max.
    const build = makeBuild({
      tree: makeTree(["Sketch1", "Extrude1"], { treeVersion: 9 }),
      part: makePart(9),
      evaluation: makeEvaluation(["ok", "ok"], { treeVersion: 9 }),
      writtenTreeVersion: 8,
    });
    expect(build.currentTreeVersion).toBe(9);
    expect(build.stale).toBe(false);
  });

  it("claims nothing before an evaluation has landed", () => {
    const build = makeBuild({ tree: makeTree(["Sketch1"]), part: makePart(3) });
    expect(build.stale).toBe(false);
    expect(build.solve).toBe("unknown");
    expect(solveSummary(build)).toBe("—");
    expect(build.scope).toBe("none");
  });
});

describe("derivePartBuild — a broken feature", () => {
  it("names the failure and the state actually on screen", () => {
    const build = brokenFillet();
    expect(build.failed).toBe(true);
    expect(build.failure?.name).toBe("Fillet1");
    expect(build.failure?.ordinal).toBe(3);
    expect(build.lastGood?.name).toBe("Extrude1");
    // The finding in one assertion: a body EXISTS, and it is not the part.
    expect(build.hasBody).toBe(true);
    expect(build.scope).toBe("partial");
  });

  it("lists the features the strict-prefix rule stranded (N3)", () => {
    const build = strandedDownstream();
    expect(build.failure?.name).toBe("Hole 1");
    expect(build.excluded.map((f) => f.name)).toEqual([
      "Mirror plane x=45",
      "Dowel hole",
      "Corner fillets R8",
    ]);
    expect(skippedReason(build)).toBe("not attempted — Hole 1 failed first");
    expect(excludedNote(build)).toBe(
      "Not attempted: the 3 features below. The build stops at the first failure, even for a feature that does not depend on Hole 1.",
    );
    expect(partialBodySentence(build)).toBe(
      "Showing the last good state — built to Base extrude. Hole 1 failed, so 3 features are excluded from it onward. Export is blocked until it builds.",
    );
  });

  it("does not count a SUPPRESSED feature as a casualty of the failure", () => {
    // Suppression is the user's own decision and the row already says so; only
    // `skipped` is the prefix rule's collateral.
    const build = makeBuild({
      tree: makeTree(["Sketch1", "Extrude1", "Fillet1", "Chamfer1"]),
      part: makePart(3),
      evaluation: makeEvaluation(["ok", "suppressed", "error", "skipped"], {
        lastGoodFeatureId: "f1",
      }),
    });
    expect(build.excluded.map((f) => f.name)).toEqual(["Chamfer1"]);
  });

  it("still reports the failure when the tree has not loaded yet", () => {
    const build = makeBuild({
      evaluation: makeEvaluation(["ok", "error"]),
    });
    expect(build.failed).toBe(true);
    expect(build.failure).toBeNull();
    expect(solveSummary(build)).toBe("Failed");
    expect(exportGate(build).blockedReason).toBe("Feature error");
  });
});

describe("derivePartBuild — the travel stop", () => {
  it("counts what the stop holds back and calls the body a prefix", () => {
    const build = rolledBack();
    expect(build.failed).toBe(false);
    expect(build.rolledBack.map((f) => f.name)).toEqual(["Fillet1"]);
    expect(build.scope).toBe("partial");
    expect(bodyStatusReadout(build).status).toBe("rolled-back");
  });

  it("does not treat the tip as a rollback", () => {
    expect(cleanCube().rolledBack).toEqual([]);
    expect(cleanCube().scope).toBe("whole");
  });
});

describe("the export gate", () => {
  it("REFUSES over a broken tree and names the feature to fix", () => {
    const gate = exportGate(brokenFillet());
    expect(gate.state).toBe("feature-error");
    expect(gate.blockedReason).toBe("Fillet1 failed");
    expect(gate.partial).toBe(false);
    // No notice band: the status cell and both format cells already say
    // "Fillet1 failed", and the viewport notice carries the consequence.
    expect(gate.notice).toBeNull();
  });

  it("REFUSES while provenance is unverified — the server exports the CURRENT tree", () => {
    const gate = exportGate(unverified());
    expect(gate.state).toBe("unverified");
    expect(gate.blockedReason).toBe("Unverified");
  });

  it("ALLOWS a deliberate rollback, marked partial in cell AND filename", () => {
    const gate = exportGate(rolledBack());
    expect(gate.blockedReason).toBeUndefined();
    expect(gate.partial).toBe(true);
    expect(gate.notice).toContain("partial");
  });

  it("blames the TRAVEL STOP, not a missing body, when the stop is the cause", () => {
    // UI-REVIEW P3: rolling the stop behind the first body-making feature left
    // the cell saying "No body" — true of a sketch-only part, misleading here,
    // where the user has a body and has parked a control in front of it.
    const behindTheBody = makeBuild({
      tree: makeTree(["Sketch1", "Extrude1"], {
        treeVersion: 5,
        rollbackFeatureId: "f1",
      }),
      part: makePart(5),
      evaluation: makeEvaluation(["ok"], {
        treeVersion: 5,
        meshGlbId: null,
        properties: null,
      }),
    });
    const gate = exportGate(behindTheBody);
    expect(gate.state).toBe("no-body");
    expect(gate.blockedReason).toBe("Rolled back");
    expect(gate.notice).toContain("travel stop");
  });

  it("keeps the two honest states it already had", () => {
    expect(exportGate(cleanCube())).toEqual({
      state: "ready",
      partial: false,
      notice: null,
    });
    const sketchOnly = makeBuild({
      tree: makeTree(["Sketch1"]),
      part: makePart(3),
      evaluation: makeEvaluation(["ok"], {
        meshGlbId: null,
        properties: null,
      }),
    });
    expect(exportGate(sketchOnly).blockedReason).toBe("No body");
  });
});

describe("the three cells cannot disagree", () => {
  // The J2 invariant, asserted directly rather than left to three components:
  // for any build, a failure is a failure in ALL of Solve / Status / Export.
  const scenarios = [
    { name: "clean", build: cleanCube(), agrees: false },
    { name: "broken fillet", build: brokenFillet(), agrees: true },
    { name: "stranded downstream", build: strandedDownstream(), agrees: true },
  ];

  scenarios.forEach(({ name, build, agrees }) => {
    it(`${name}: Solve, Status and Export tell the same story`, () => {
      const solve = solveSummary(build);
      const status = bodyStatusReadout(build).status;
      const gate = exportGate(build);
      if (agrees) {
        expect(solve).toBe("Failed");
        expect(status).toBe("partial");
        expect(gate.blockedReason).toBeDefined();
      } else {
        expect(solve).toBe("Solved");
        expect(status).toBe("up-to-date");
        expect(gate.state).toBe("ready");
      }
    });
  });

  it("never spends 'Up to date' on a body that is a prefix", () => {
    [
      brokenFillet(),
      strandedDownstream(),
      rolledBack(),
      unverified(),
      midWrite(),
      justWritten(),
    ].forEach((build) => {
      expect(bodyStatusReadout(build).label).not.toBe("Up to date");
    });
  });

  /**
   * QA-R4's invariant, asserted over the whole transient space rather than the
   * one path that was measured: STALE MUST NEVER READ AS UP TO DATE. The window
   * that shipped came from a second route into the all-clear branch (stale, but
   * `treeFetching` cancelling the "Unverified" verdict without cancelling this
   * one) — the kind of gap a scenario-by-scenario test does not find.
   */
  it("never says 'Up to date' about a stale body, in any request state", () => {
    const flags = ["evaluating", "treeFetching", "regenerating", "writing"];
    for (let bits = 0; bits < 1 << flags.length; bits += 1) {
      const state = Object.fromEntries(
        flags.map((flag, index) => [flag, (bits & (1 << index)) !== 0]),
      );
      const build = makeBuild({
        tree: makeTree(["Sketch1", "Extrude1"], { treeVersion: 4 }),
        part: makePart(4),
        evaluation: makeEvaluation(["ok", "ok"], { treeVersion: 3 }),
        ...state,
      });
      expect(build.stale, JSON.stringify(state)).toBe(true);
      expect(bodyStatusReadout(build).status, JSON.stringify(state)).not.toBe(
        "up-to-date",
      );
    }
  });

  /**
   * The second inconsistency QA-R4 recorded: at t+2288 ms STATUS read
   * "Regenerating…" while SOLVE still read "Solved" — one cell reporting a
   * rebuild the other denied, because `solve` tested `evaluating` alone.
   */
  it("SOLVE and STATUS agree about whether a rebuild is under way", () => {
    const settled = {
      tree: makeTree(["Sketch1", "Extrude1"]),
      part: makePart(3),
      evaluation: makeEvaluation(["ok", "ok"], { lastGoodFeatureId: "f2" }),
    };
    (["evaluating", "regenerating", "meshPending", "writing"] as const).forEach(
      (flag) => {
        const build = makeBuild({ ...settled, [flag]: true });
        expect(bodyStatusReadout(build).status, flag).not.toBe("up-to-date");
        expect(build.solve, flag).toBe("solving");
        expect(solveSummary(build), flag).toBe("Solving…");
      },
    );
    // `mesh-error` is the deliberate exception: the evaluation DID return a
    // verdict and only the mesh is unservable, which STATUS says in its own
    // words — claiming "Solving…" there would invent a rebuild nobody started.
    const meshError = makeBuild({ ...settled, regenFailed: true });
    expect(bodyStatusReadout(meshError).status).toBe("error");
    expect(solveSummary(meshError)).toBe("Solved");
  });
});

describe("transient request state stays in its own lane", () => {
  it("reports the mesh states without touching the model claim", () => {
    const base = {
      tree: makeTree(["Sketch1", "Extrude1"]),
      part: makePart(3),
      evaluation: makeEvaluation(["ok", "ok"], { lastGoodFeatureId: "f2" }),
    };
    expect(
      bodyStatusReadout(makeBuild({ ...base, regenerating: true })).label,
    ).toBe("Regenerating…");
    expect(
      bodyStatusReadout(makeBuild({ ...base, meshPending: true })).label,
    ).toBe("Regenerating…");
    const failedMesh = bodyStatusReadout(
      makeBuild({ ...base, regenFailed: true }),
    );
    expect(failedMesh.status).toBe("error");
    expect(failedMesh.tone).toBe("flag");
  });

  it("prefers the model's own bad news over an in-flight mesh fetch", () => {
    // A regenerating mesh is worth saying; a BROKEN TREE is worth saying more,
    // and `regenFailed` is only ever a `mesh_not_found` retry flag — it could
    // never carry feature health (PartPage.tsx:506/513).
    const build = makeBuild({
      tree: makeTree(["Sketch1", "Extrude1", "Fillet1"]),
      part: makePart(3),
      evaluation: makeEvaluation(["ok", "ok", "error"], {
        lastGoodFeatureId: "f2",
      }),
    });
    expect(build.activity).toBe("idle");
    expect(bodyStatusReadout(build).status).toBe("partial");
  });
});

/**
 * The DRAWER-level verdict (audit J3b). The wire carries two orthogonal axes
 * and the register used to read only the first, so a part rolled back to
 * feature 2 of 9 read "Clean" — a verdict on a prefix printed as a verdict on
 * the part. Both traps are fenced here: null must not become `whole`, and
 * `whole` must not be hedged.
 */
describe("registerHealthReadout", () => {
  const base = { lastStatus: "ok" as const, age: ", 20 min ago" };

  it("says Clean only when the whole tree ran", () => {
    const whole = registerHealthReadout({
      ...base,
      state: "ok",
      scope: "whole",
    });
    expect(whole.label).toBe("Clean");
    expect(whole.tone).toBe("quiet");
  });

  it("refuses the word Clean for a verdict that covers a prefix", () => {
    const prefix = registerHealthReadout({
      ...base,
      state: "ok",
      scope: "rolled_back",
    });
    expect(prefix.label).not.toBe("Clean");
    expect(prefix.label).toBe("Clean to stop");
    // Not established — the dashed phantom stamp, never the quiet all-clear.
    expect(prefix.tone).toBe("indeterminate");
    expect(prefix.title).toMatch(/travel stop/);
    expect(prefix.title).toMatch(/never attempted/);
    expect(prefix.srSuffix).toMatch(/untried/);
  });

  it("renders an unqualified ok exactly as before — null is not 'whole'", () => {
    const nulled = registerHealthReadout({ ...base, state: "ok", scope: null });
    expect(nulled.label).toBe("Clean");
    expect(nulled.tone).toBe("quiet");
    expect(nulled.title).toMatch(/not a claim that it has a body/);
    // ...and identical to a row that predates the field entirely.
    expect(
      registerHealthReadout({ ...base, state: "ok", scope: undefined }),
    ).toEqual(nulled);
  });

  it("keeps Broken for a failure inside a prefix, and says where the stop is", () => {
    const failedPrefix = registerHealthReadout({
      ...base,
      state: "failed",
      lastStatus: "failed",
      scope: "rolled_back",
    });
    expect(failedPrefix.label).toBe("Broken");
    expect(failedPrefix.tone).toBe("flag");
    expect(failedPrefix.title).toMatch(/before the travel stop/);

    const failedWhole = registerHealthReadout({
      ...base,
      state: "failed",
      lastStatus: "failed",
      scope: "whole",
    });
    expect(failedWhole.label).toBe("Broken");
    expect(failedWhole.title).not.toMatch(/travel stop/);
  });

  it("keeps the stale record past-tense and drops any scope beside it", () => {
    const stale = registerHealthReadout({
      ...base,
      state: "stale",
      lastStatus: "failed",
      scope: "rolled_back",
    });
    expect(stale.label).toBe("Was broken");
    expect(stale.tone).toBe("indeterminate");
    // There is no live verdict for a scope to qualify.
    expect(stale.scope).toBeNull();
  });

  it("says nothing at all about a part that was never evaluated", () => {
    const never = registerHealthReadout({
      ...base,
      state: undefined,
      lastStatus: null,
      scope: null,
    });
    expect(never.label).toBe("Not evaluated");
    expect(never.tone).toBe("quiet");
    expect(
      registerHealthReadout({ ...base, state: "never", scope: null }).label,
    ).toBe("Not evaluated");
  });

  it("spends the age clause it was handed, and survives not having one", () => {
    expect(
      registerHealthReadout({ ...base, state: "ok", scope: "whole" }).title,
    ).toMatch(/20 min ago/);
    expect(
      registerHealthReadout({ ...base, age: "", state: "ok", scope: "whole" })
        .title,
    ).toMatch(/rebuilt\. That is not a claim/);
  });
});
