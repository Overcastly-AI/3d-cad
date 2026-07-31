/**
 * What the assembly panel may claim about mass.
 *
 * The defect being fenced: a section titled "Combined mass" that reported no
 * mass (materials.md §6.1, the part inspector's defect at a second address),
 * and — once mass existed — the two ways a total can be absent, which must not
 * look alike. The roll-up nulls its total unless EVERY contributor has a
 * material, so absence is normal and it always has a NAME behind it.
 */
import { describe, expect, it } from "vitest";

import type {
  EvaluateAssemblyResult,
  InstanceResponse,
} from "../api/assemblies";
import type { ShapeProperties } from "../api/tessellate";
import { assemblyMassState, combinedEyebrow } from "./mass";

function props(massG: number | null): ShapeProperties {
  return {
    volume: 1000,
    surface_area: 600,
    centroid: { x: 0, y: 0, z: 0 },
    mass_g: massG,
    bounding_box: { min: { x: 0, y: 0, z: 0 }, max: { x: 10, y: 10, z: 10 } },
    topology: { faces: 6, edges: 12, shells: 1 },
  };
}

function instance(id: string, name: string): InstanceResponse {
  return {
    id,
    assembly_id: "a1",
    name,
    ref_document_id: "p1",
    ref_document_kind: "part",
    ref_pinned_version: null,
    order_index: 0,
    grounded: false,
    placement: {
      position: { x: 0, y: 0, z: 0 },
      orientation: { x: 0, y: 0, z: 0, w: 1 },
    },
    created_at: "2026-07-30T09:00:00Z",
    updated_at: "2026-07-30T09:00:00Z",
  };
}

function evaluation(
  total: number | null,
  per: readonly (number | null | "no-body")[],
): EvaluateAssemblyResult {
  return {
    assembly_id: "a1",
    version: 1,
    status: "well_constrained",
    properties: props(total),
    instances: per.map((mass, i) => ({
      instance_id: `i${i + 1}`,
      part_mesh_glb_id: mass === "no-body" ? null : "sha256:abc",
      placement: {
        position: { x: 0, y: 0, z: 0 },
        orientation: { x: 0, y: 0, z: 0, w: 1 },
      },
      properties: mass === "no-body" ? null : props(mass),
    })),
  };
}

const graph = [
  instance("i1", "Housing"),
  instance("i2", "Pin"),
  instance("i3", "Cover"),
];

describe("assemblyMassState", () => {
  it("says nothing at all before the first solve", () => {
    expect(assemblyMassState(undefined, graph)).toEqual({ kind: "unsolved" });
    expect(
      assemblyMassState({ ...evaluation(null, []), properties: null }, graph),
    ).toEqual({ kind: "unsolved" });
  });

  it("reports the total when every component is weighed", () => {
    expect(assemblyMassState(evaluation(84.56, [27, 57.56]), graph)).toEqual({
      kind: "known",
      massG: 84.56,
    });
  });

  it("names the component that has no material", () => {
    const state = assemblyMassState(evaluation(null, [27, null]), graph);
    expect(state).toEqual({ kind: "partial", missing: ["Pin"] });
  });

  it("does not blame an instance that produced no body", () => {
    // `properties: null` is "no body", not "no material" — it never enters the
    // roll-up, so it can never be the reason the total went null.
    const state = assemblyMassState(
      evaluation(null, [27, "no-body", null]),
      graph,
    );
    expect(state).toEqual({ kind: "partial", missing: ["Cover"] });
  });

  it("distinguishes 'nobody has one' from 'this one is missing'", () => {
    expect(assemblyMassState(evaluation(null, [null, null]), graph)).toEqual({
      kind: "unassigned",
    });
  });

  it("survives a graph it has no names for", () => {
    const state = assemblyMassState(evaluation(null, [27, null]), []);
    expect(state).toEqual({ kind: "partial", missing: ["An instance"] });
  });
});

describe("combinedEyebrow", () => {
  it("promises mass only when there is one", () => {
    expect(combinedEyebrow({ kind: "known", massG: 12 })).toBe("Combined mass");
    for (const state of [
      { kind: "unsolved" } as const,
      { kind: "unassigned" } as const,
      { kind: "partial", missing: ["Pin"] } as const,
    ]) {
      expect(combinedEyebrow(state)).not.toMatch(/mass/i);
    }
  });
});
