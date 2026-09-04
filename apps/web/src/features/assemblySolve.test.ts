import { describe, expect, it } from "vitest";

import type { EvaluateAssemblyResult } from "../api/assemblies";
import {
  assemblySolveLabel,
  assemblySolveTone,
  deriveAssemblySolve,
  type AssemblySolveInput,
} from "./assemblySolve";

/** The answer the kernel gives for the MATED fixture (remaining_dof 3). */
const mated = {
  status: "under_constrained",
  diagnosis: {
    status: "under_constrained",
    remaining_dof: 3,
    conflicting_mates: [],
    message: "Three degrees of freedom remain.",
    suggested_fix: null,
  },
  instances: [],
  mate_errors: [],
  properties: null,
} as unknown as EvaluateAssemblyResult;

/** The mate id the PREVIOUS solve badged as unresolved (MATE-OBS-2). */
const STALE_MATE = "9d3d1cf2-0f6a-4c1a-9c50-1f8f7c1d0001";

/**
 * The answer the kernel gives for the SAME fixture with `mates=[]`
 * (remaining_dof 6) — the previous solve, and the reading the UI reported.
 *
 * The two carry the SAME `status`, which is the whole reason this module never
 * looks at the solve's content: `test_status_alone_cannot_distinguish_the_two`
 * (services/geometry) proves a status-keyed staleness test passes in a world
 * where mates do nothing.
 */
const preMate = {
  ...mated,
  diagnosis: {
    ...mated.diagnosis,
    remaining_dof: 6,
    conflicting_mates: [STALE_MATE],
  },
  // The EIGHTH CONSUMER's input (MATE-OBS-2): `AssemblyTreePanel` badged its
  // rows from these two fields directly, so a retained solve put a `conflict` /
  // `unresolved` stamp on a row for the length of every write. Both are
  // populated here so a matrix row that leaked either one has something to leak.
  mate_errors: [
    { mate_id: STALE_MATE, error: { code: "mate_unresolved", message: "x" } },
  ],
} as unknown as EvaluateAssemblyResult;

/** Settled: the evaluation on screen was solved from the key in force. */
function settled(over: Partial<AssemblySolveInput> = {}): AssemblySolveInput {
  return {
    writing: false,
    loading: false,
    evaluating: false,
    solvable: true,
    placeholder: false,
    failed: false,
    evaluation: mated,
    ...over,
  };
}

describe("deriveAssemblySolve — a settled solve", () => {
  it("spends the verdict the solver returned", () => {
    const solve = deriveAssemblySolve(settled());
    expect(solve.stale).toBe(false);
    expect(solve.activity).toBe("idle");
    expect(solve.status).toBe("under_constrained");
    expect(solve.diagnosis?.remaining_dof).toBe(3);
    expect(solve.mateErrors).toEqual([]);
    expect(assemblySolveLabel(solve)).toBe("Under constrained");
  });

  it("hands the tree panel the error set it is entitled to badge", () => {
    // The EIGHTH CONSUMER, settled: `preMate` is only "previous" when
    // something supersedes it, so at rest its error set is the current one and
    // the badge must be drawn. The gate must not be a mute button.
    const solve = deriveAssemblySolve(settled({ evaluation: preMate }));
    expect(solve.stale).toBe(false);
    expect(solve.mateErrors.map((e) => e.mate_id)).toEqual([STALE_MATE]);
    expect(solve.diagnosis?.conflicting_mates).toEqual([STALE_MATE]);
  });

  it("says nothing when there is nothing solved yet", () => {
    const solve = deriveAssemblySolve(settled({ evaluation: undefined }));
    expect(solve.status).toBeNull();
    expect(assemblySolveLabel(solve)).toBe("—");
    expect(assemblySolveTone(solve)).toBe("text-gauge");
  });
});

describe("deriveAssemblySolve — the superseded window", () => {
  /**
   * THE MEASURED DEFECT, as a table. Each row is a distinct way the workspace
   * ends up holding a PREVIOUS solve; the previous solve is `preMate`, whose
   * `status` is identical to the current one's, so a surface reading it cannot
   * tell it is wrong. Every row must refuse to spend a verdict.
   */
  const paths: ReadonlyArray<readonly [string, Partial<AssemblySolveInput>]> = [
    // t+0: the mate POST is out and no cache knows yet. This is the window the
    // kernel investigation sampled — the click, then ~600 ms of confident wrong.
    ["a write the client just issued", { writing: true }],
    // The graph came back with a new doc_version, so the part-docs key moved and
    // the evaluate query is DISABLED. Nothing else reports anything here.
    ["the graph / part rows refetching", { loading: true, solvable: false }],
    ["the evaluate itself in flight", { evaluating: true }],
    // A referenced PART edited elsewhere moves `partStamp` without touching
    // doc_version, so only the key comparison catches it.
    ["a solve retained from another key", { placeholder: true }],
    // Navigating assemblies: the retained solve belongs to another document.
    [
      "a solve retained from another assembly",
      { placeholder: true, solvable: false },
    ],
    // The last instance deleted: disabled for good, retained solve forever.
    ["an assembly with nothing left to solve", { solvable: false }],
    ["an evaluate that failed", { failed: true }],
  ];

  for (const [name, over] of paths) {
    it(`refuses a verdict over ${name}`, () => {
      const solve = deriveAssemblySolve(
        settled({ evaluation: preMate, ...over }),
      );
      expect(solve.stale).toBe(true);
      expect(solve.status).toBeNull();
      expect(solve.diagnosis).toBeNull();
      // The eighth consumer: no badge can be drawn from a superseded solve,
      // because there is no error set to draw one from (MATE-OBS-2).
      expect(solve.mateErrors).toEqual([]);
      expect(assemblySolveLabel(solve)).not.toBe("Under constrained");
    });
  }

  it("holds SOLVING across the whole window, and only drops it at the end", () => {
    // The three in-flight rows read "Solving…" — a transient word, so a barrier
    // waiting for "not Solving" does not release inside the window.
    for (const over of [
      { writing: true },
      { loading: true, solvable: false },
      { evaluating: true },
      { placeholder: true },
    ]) {
      const solve = deriveAssemblySolve(
        settled({ evaluation: preMate, ...over }),
      );
      expect(assemblySolveLabel(solve)).toBe("Solving…");
      expect(solve.activity).toBe("solving");
    }
  });

  it("says — rather than Solving when nothing will resolve it", () => {
    // Deleting the last instance is NOT a rebuild: claiming "Solving…" forever
    // would be a second lie wearing the first one's clothes.
    const solve = deriveAssemblySolve(
      settled({ evaluation: preMate, solvable: false }),
    );
    expect(solve.activity).toBe("idle");
    expect(assemblySolveLabel(solve)).toBe("—");
  });
});

describe("deriveAssemblySolve — the invariant", () => {
  /**
   * `stale` STRUCTURALLY implies there is no verdict. Asserted over the whole
   * 2^6 space of the transient inputs rather than the rows above, because the
   * defect this closes is a combination nobody enumerated: on the part page a
   * second, unmeasured route to the same lie existed for weeks behind the one
   * that was found. A matrix does not care which route you thought of.
   */
  it("holds over every combination of the transient inputs", () => {
    const flags = [
      "writing",
      "loading",
      "evaluating",
      "solvable",
      "placeholder",
      "failed",
    ] as const;
    let stalest = 0;
    let settledCount = 0;
    for (let mask = 0; mask < 1 << flags.length; mask += 1) {
      const over: Partial<AssemblySolveInput> = {};
      flags.forEach((flag, bit) => {
        over[flag] = (mask & (1 << bit)) !== 0;
      });
      const solve = deriveAssemblySolve(
        settled({ evaluation: preMate, ...over }),
      );
      if (solve.stale) {
        stalest += 1;
        expect(solve.status).toBeNull();
        expect(solve.diagnosis).toBeNull();
        expect(solve.mateErrors).toEqual([]);
        expect(["Solving…", "—"]).toContain(assemblySolveLabel(solve));
      } else {
        settledCount += 1;
        // NON-VACUITY for the new field: the one settled combination must
        // actually HAND OVER the error set, or "empty whenever stale" would
        // hold trivially in a build where `mateErrors` is always empty.
        expect(solve.mateErrors).toHaveLength(1);
        expect(solve.diagnosis?.conflicting_mates).toEqual([STALE_MATE]);
        // The ONE settled combination: solvable, nothing in flight, no
        // placeholder, no error.
        expect(over).toMatchObject({
          writing: false,
          loading: false,
          evaluating: false,
          solvable: true,
          placeholder: false,
          failed: false,
        });
      }
    }
    // The counts are the guard on the guard: a matrix that never reached the
    // settled branch would pass this test while asserting nothing about it.
    expect(settledCount).toBe(1);
    expect(stalest).toBe(63);
  });
});
