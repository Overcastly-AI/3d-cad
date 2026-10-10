/**
 * QA 2026-10-10: an assembly whose joints stopped resolving exported as
 * "Ready". The gate reads the claimable solve facts and must say "Partial",
 * naming the count and the kind, for every way a mate can fail to be honoured.
 */
import { describe, expect, it } from "vitest";

import type { MateResponse } from "../api/assemblies";
import {
  assemblyExporter,
  assemblyExportGate,
  assemblyFaultSummary,
  assemblySolveFaults,
  type AssemblySolveFacts,
} from "./assemblyExport";

const JOINT_A = "00000000-0000-0000-0000-00000000000a";
const JOINT_B = "00000000-0000-0000-0000-00000000000b";
const MATE_C = "00000000-0000-0000-0000-00000000000c";

const mates = [
  { id: JOINT_A, mate: { type: "joint" } },
  { id: JOINT_B, mate: { type: "joint" } },
  { id: MATE_C, mate: { type: "coincident" } },
] as unknown as Pick<MateResponse, "id" | "mate">[];

const unresolved = (id: string) => ({
  mate_id: id,
  error: { code: "subshape_unresolved", message: "gone" },
});

function facts(over: Partial<AssemblySolveFacts> = {}): AssemblySolveFacts {
  return {
    status: "well_constrained",
    diagnosis: null,
    mateErrors: [],
    ...over,
  };
}

describe("assemblyExportGate", () => {
  it("is Ready for a clean solve, and leaves the filename alone", async () => {
    const gate = assemblyExportGate(facts(), mates);
    expect(gate.state).toBe("ready");
    expect(gate.statusLabel).toBeUndefined();
    expect(gate.confirmReason).toBeNull();
    const raw = async () => ({ blob: new Blob([]), filename: "hinge.step" });
    expect(assemblyExporter(raw, gate.partial)).toBe(raw);
  });

  it("is Ready for an under-constrained solve with nothing dropped", () => {
    expect(
      assemblyExportGate(facts({ status: "under_constrained" }), mates).state,
    ).toBe("ready");
  });

  it("names unresolved joints by count and kind", async () => {
    const gate = assemblyExportGate(
      facts({
        status: "under_constrained",
        mateErrors: [unresolved(JOINT_A), unresolved(JOINT_B)],
      }),
      mates,
    );
    expect(gate.state).toBe("partial");
    expect(gate.statusLabel).toBe("Partial · 2 joints unresolved");
    expect(gate.notice).toMatch(
      /^2 joints unresolved, so the file would hold the parts at their last solved or initial positions/,
    );
    expect(gate.confirmReason).toBe("2 joints unresolved.");
    const raw = async () => ({ blob: new Blob([]), filename: "hinge.step" });
    const file = await assemblyExporter(raw, gate.partial)("step");
    expect(file.filename).toBe("hinge-partial.step");
  });

  it("splits joints from mates, and unresolved wins over conflict", () => {
    const faults = assemblySolveFaults(
      facts({
        status: "conflicting",
        mateErrors: [unresolved(JOINT_A)],
        diagnosis: {
          classification: "conflicting",
          remaining_dof: 0,
          removable: false,
          conflicting_mates: [JOINT_A, MATE_C],
          redundant_mates: [],
          message: "conflict",
        },
      }),
      mates,
    );
    expect(assemblyFaultSummary(faults)).toBe(
      "1 joint unresolved, 1 mate conflicting",
    );
  });

  it("flags a solve that gave up without naming a mate", () => {
    expect(
      assemblyExportGate(facts({ status: "not_converged" }), mates).statusLabel,
    ).toBe("Partial · solve did not converge");
  });

  it("does not count redundant mates: the assembly still solves", () => {
    const gate = assemblyExportGate(
      facts({
        status: "over_constrained",
        diagnosis: {
          classification: "redundant",
          remaining_dof: 0,
          removable: true,
          conflicting_mates: [],
          redundant_mates: [MATE_C],
          message: "redundant",
        },
      }),
      mates,
    );
    expect(gate.state).toBe("ready");
  });
});
