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
  skippedReason,
  solveSummary,
} from "./partBuild";
import {
  brokenFillet,
  cleanCube,
  makeBuild,
  makeEvaluation,
  makePart,
  makeTree,
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
    [brokenFillet(), strandedDownstream(), rolledBack(), unverified()].forEach(
      (build) => {
        expect(bodyStatusReadout(build).label).not.toBe("Up to date");
      },
    );
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
