import { describe, expect, it } from "vitest";

import type { EvaluateAssemblyResult } from "../api/assemblies";
import { assemblyReadout, EM_DASH } from "./readout";

/**
 * FINDINGS burn-down 2026-07-25 #7: the assembly title block used to hardcode
 * mm³/mm²/mm while the part title block already honoured the document unit —
 * the same solid read `31,391.38 mm³` in the assembly and `1.9156 in³` in the
 * part. One product, one convention: these assert the assembly panel converts
 * at the display boundary exactly like the part panel.
 */
function evaluation(): EvaluateAssemblyResult {
  return {
    assembly_id: "a1",
    version: 1,
    status: "well_constrained",
    instances: [],
    properties: {
      volume: 31391.38,
      surface_area: 6451.6,
      centroid: { x: 25.4, y: 50.8, z: 0 },
      bounding_box: {
        min: { x: 0, y: 0, z: 0 },
        max: { x: 25.4, y: 50.8, z: 76.2 },
      },
      topology: { faces: 6, edges: 12, shells: 1 },
    },
    bounding_box: {
      min: { x: 0, y: 0, z: 0 },
      max: { x: 25.4, y: 50.8, z: 76.2 },
    },
  };
}

describe("assemblyReadout", () => {
  it("prints millimetres unchanged in an mm assembly", () => {
    const out = assemblyReadout(evaluation(), "mm");
    expect(out).toMatchObject({
      volume: "31,391.38",
      volumeUnit: "mm³",
      area: "6,451.6",
      areaUnit: "mm²",
      centroid: "25.4, 50.8, 0",
      extents: "25.4 × 50.8 × 76.2",
      lengthUnit: "mm",
    });
  });

  it("converts every cell to the document unit in an inch assembly", () => {
    const out = assemblyReadout(evaluation(), "in");
    expect(out).toMatchObject({
      volume: "1.9156",
      volumeUnit: "in³",
      area: "10",
      areaUnit: "in²",
      centroid: "1, 2, 0",
      extents: "1 × 2 × 3",
      lengthUnit: "in",
    });
  });

  it("shows placeholders (with the right unit labels) before a solve", () => {
    const out = assemblyReadout(undefined, "in");
    expect(out).toMatchObject({
      volume: EM_DASH,
      area: EM_DASH,
      centroid: EM_DASH,
      extents: EM_DASH,
      volumeUnit: "in³",
      areaUnit: "in²",
      lengthUnit: "in",
    });
  });

  it("shows a placeholder for a solve that produced no bounding box", () => {
    const partial: EvaluateAssemblyResult = {
      ...evaluation(),
      bounding_box: null,
      properties: null,
    };
    expect(assemblyReadout(partial, "mm").extents).toBe(EM_DASH);
    expect(assemblyReadout(partial, "mm").volume).toBe(EM_DASH);
  });
});
