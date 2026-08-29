import { describe, expect, it } from "vitest";

import type { AssemblySolveDiagnosis } from "../api/assemblies";
import { assemblyDiagnosisReadout } from "./diagnosis";
import { mateNamesById, type MateIdentity } from "./mates";

/**
 * The two ids from the AUDIT-PRODUCT S-18 report, and the panel names the
 * defect said did not exist.
 */
const ID_A = "4ae95465-6f0e-4a2f-9a95-1c9e2b1e0001";
const ID_B = "b78a814e-7c3d-4e1b-9c4d-2f8a3c5d0002";

const names = mateNamesById([
  { id: ID_A, mate: { type: "lock", a_instance_id: "a", b_instance_id: "b" } },
  {
    id: ID_B,
    mate: {
      type: "coincident",
      flush: true,
      a: { kind: "face", instance_id: "a", signature: {} },
      b: { kind: "face", instance_id: "b", signature: {} },
      // The signature shape is irrelevant to naming; the cast keeps this
      // fixture from carrying a whole PlanarFaceSignature for a label test.
    },
  },
] as Parameters<typeof mateNamesById>[0]);

function diagnosis(
  over: Partial<AssemblySolveDiagnosis>,
): AssemblySolveDiagnosis {
  return {
    remaining_dof: 0,
    removable: false,
    // The server's own prose, carried verbatim from `_diagnose` — including
    // the Python list repr. Present in every fixture ON PURPOSE: the readout
    // must never reach for it.
    message: `mates ['${ID_A}', '${ID_B}'] are mutually unsatisfiable`,
    suggested_fix: `Remove or relax mate ${ID_A}`,
    ...over,
  };
}

/** The whole message a user reads, message + every action label. */
function everything(
  d: AssemblySolveDiagnosis,
  map: ReadonlyMap<string, MateIdentity> = names,
): string {
  const readout = assemblyDiagnosisReadout(d, map);
  if (readout === null) throw new Error("expected a readout");
  return [readout.text, ...readout.subjects.map((s) => s.name)].join(" | ");
}

describe("assemblyDiagnosisReadout — no raw identifier ever reaches the user", () => {
  /**
   * Asserted over EVERY branch and over the WHOLE string, not over the two ids
   * this fixture happens to carry: the defect is a class (a typed field
   * stringified into prose), so a future field leaking a repr has to fail here
   * too. `UUID(` is Python's own constructor repr, which is what actually
   * appeared on screen.
   */
  const branches: ReadonlyArray<
    readonly [string, Partial<AssemblySolveDiagnosis>]
  > = [
    [
      "conflicting",
      { classification: "conflicting", conflicting_mates: [ID_A, ID_B] },
    ],
    [
      "conflicting, one offender",
      { classification: "conflicting", conflicting_mates: [ID_A] },
    ],
    [
      "redundant",
      { classification: "redundant", removable: true, redundant_mates: [ID_B] },
    ],
    ["under-constrained", { remaining_dof: 3 }],
    ["under-constrained by one", { remaining_dof: 1 }],
    ["not converged", {}],
  ];

  for (const [name, over] of branches) {
    it(`prints no identifier on the ${name} branch`, () => {
      const text = everything(diagnosis(over));
      expect(text).not.toMatch(/UUID\(/);
      expect(text).not.toMatch(
        /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i,
      );
      // Nor the bracketed list the repr arrives in, nor the raw prose.
      expect(text).not.toContain("[");
      expect(text).not.toContain("mutually unsatisfiable");
    });
  }

  it("names a mate it cannot find by COUNT, never by its id", () => {
    // The graph is not in hand (navigating, or a refetch in flight). The
    // tempting fallback — print the id "just this once" — is the defect.
    const text = everything(
      diagnosis({
        classification: "conflicting",
        conflicting_mates: [ID_A, ID_B],
      }),
      new Map(),
    );
    expect(text).toContain("2 mates cannot all be satisfied at once.");
    expect(text).not.toContain(ID_A);
  });

  it("counts the mates it cannot name beside the ones it can", () => {
    const readout = assemblyDiagnosisReadout(
      diagnosis({
        classification: "conflicting",
        conflicting_mates: [ID_A, ID_B, "00000000-0000-4000-8000-000000000003"],
      }),
      names,
    );
    expect(readout?.text).toContain(
      "M1 Lock and M2 Coincident and 1 further mate",
    );
    expect(readout?.subjects).toHaveLength(2);
  });
});

describe("assemblyDiagnosisReadout — every clause is terminated", () => {
  /**
   * Defect (c): `message` and `suggested_fix` are two sentences and NEITHER
   * ends in a full stop, so the old `{message}{" "}{suggested_fix}` produced
   * "…at their seed placement Add mates to…". The guard is on the shape of the
   * prose, so it fires wherever a clause loses its terminator — not only on
   * the one string the audit happened to screenshot.
   */
  const all: ReadonlyArray<Partial<AssemblySolveDiagnosis>> = [
    { classification: "conflicting", conflicting_mates: [ID_A, ID_B] },
    { classification: "conflicting", conflicting_mates: [ID_A] },
    { classification: "redundant", removable: true, redundant_mates: [ID_B] },
    { remaining_dof: 6 },
    {},
  ];

  for (const over of all) {
    it(`ends every sentence before the next begins: ${JSON.stringify(over)}`, () => {
      const readout = assemblyDiagnosisReadout(diagnosis(over), names);
      const text = readout?.text ?? "";
      expect(text).not.toBe("");
      // Terminated at the end...
      expect(text.endsWith(".")).toBe(true);
      // ...and at every internal boundary: a capital letter may only follow a
      // terminator + one space, never a bare space. (Mate names are the one
      // legitimate mid-sentence capital, so they are masked out first.)
      const masked = text.replace(
        /M\d+ (Coincident|Concentric|Lock|Distance|Angle)/g,
        "x",
      );
      expect(masked).not.toMatch(/[a-z] [A-Z]/);
    });
  }

  it("reads as prose on the under-constrained path", () => {
    expect(
      assemblyDiagnosisReadout(diagnosis({ remaining_dof: 3 }), names),
    ).toEqual({
      text: "3 degrees of freedom remain. The free components sit where they were seeded; add mates to locate them.",
      subjects: [],
    });
  });

  it("agrees with the panel about what a mate is called", () => {
    const readout = assemblyDiagnosisReadout(
      diagnosis({
        classification: "conflicting",
        conflicting_mates: [ID_A, ID_B],
      }),
      names,
    );
    expect(readout?.text).toBe(
      "M1 Lock and M2 Coincident cannot all be satisfied at once. Remove or relax one of them.",
    );
    // The subjects are the removable handles, in the order the text names them.
    expect(readout?.subjects).toEqual([
      { mateId: ID_A, tag: "M1", name: "M1 Lock" },
      { mateId: ID_B, tag: "M2", name: "M2 Coincident" },
    ]);
  });

  it("says nothing when there is no diagnosis", () => {
    expect(assemblyDiagnosisReadout(null, names)).toBeNull();
  });
});

describe("assemblyDiagnosisReadout — singular and plural", () => {
  it("does not offer to remove one of one", () => {
    const readout = assemblyDiagnosisReadout(
      diagnosis({ classification: "conflicting", conflicting_mates: [ID_B] }),
      names,
    );
    expect(readout?.text).toBe(
      "M2 Coincident cannot be satisfied. Remove or relax it.",
    );
  });

  it("names the redundant mate and what removing it costs", () => {
    const readout = assemblyDiagnosisReadout(
      diagnosis({
        classification: "redundant",
        removable: true,
        redundant_mates: [ID_A],
      }),
      names,
    );
    expect(readout?.text).toBe(
      "M1 Lock is redundant — the assembly solves without it. Remove it to simplify the mate set.",
    );
    expect(readout?.subjects).toEqual([
      { mateId: ID_A, tag: "M1", name: "M1 Lock" },
    ]);
  });

  it("counts one degree of freedom in the singular", () => {
    expect(
      assemblyDiagnosisReadout(diagnosis({ remaining_dof: 1 }), names)?.text,
    ).toContain("1 degree of freedom remains.");
  });
});
