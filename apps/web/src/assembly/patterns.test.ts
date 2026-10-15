import { describe, expect, it } from "vitest";

import type {
  AssemblyGraphResponse,
  EvaluateAssemblyResult,
  InstanceResponse,
  Placement,
} from "../api/assemblies";
import type { EdgeSignature } from "../api/parts";
import type { PatternResponse } from "../api/patterns";
import { EMPTY_VISIBILITY } from "../viewport/instanceVisibility";
import { buildEvaluateAssemblyRequest } from "./evaluateRequest";
import {
  buildPattern,
  formFromPattern,
  newPatternForm,
  patternTitle,
  samePartInstances,
} from "./patterns";
import { buildSceneInstances } from "./sceneInstances";
import { nestedParts } from "./subAssemblies";

const IDENTITY: Placement = {
  position: { x: 0, y: 0, z: 0 },
  orientation: { x: 0, y: 0, z: 0, w: 1 },
};

const RIM: EdgeSignature = {
  subshape_type: "edge",
  curve: "circle",
  end_a: { x: 3, y: 0, z: 0 },
  end_b: { x: 3, y: 0, z: 0 },
  midpoint: { x: -3, y: 0, z: 0 },
  length_mm: 18.85,
};

function instance(over: Partial<InstanceResponse>): InstanceResponse {
  return {
    id: "i1",
    assembly_id: "stage",
    name: "Rail <1>",
    ref_document_id: "rail",
    ref_document_kind: "part",
    ref_pinned_version: null,
    grounded: true,
    order_index: 0,
    placement: IDENTITY,
    created_at: "2026-10-15T00:00:00Z",
    updated_at: "2026-10-15T00:00:00Z",
    ...over,
  };
}

const RAIL_1 = instance({ id: "r1" });
const RAIL_2 = instance({ id: "r2", name: "Rail <2>", order_index: 1 });
const SCREW = instance({
  id: "s1",
  name: "M3x8 <1>",
  ref_document_id: "screw",
  grounded: false,
  order_index: 2,
});

function pattern(over: Partial<PatternResponse>): PatternResponse {
  return {
    id: "p1",
    assembly_id: "stage",
    order_index: 0,
    pattern: {
      type: "hole",
      seed_instance_ids: ["s1"],
      seed_hole: { instance_id: "r1", signature: RIM },
      also_on: ["r2"],
    },
    ...over,
  };
}

describe("the pattern form", () => {
  it("reads typed expressions into numbers and keeps the text", () => {
    const form = {
      ...newPatternForm(["s1"]),
      count: "12 / 2 + 1",
      spacing: "1 in",
    };
    const built = buildPattern(form);
    if (!("pattern" in built)) throw new Error(built.error);
    expect(built.pattern).toMatchObject({
      type: "linear",
      count: 7,
      spacing_mm: 25.4,
      count_expr: "12 / 2 + 1",
      spacing_expr: "1 in",
      direction: { kind: "origin_axis", axis: "x" },
    });
  });

  it("names what is missing or wrong", () => {
    expect(buildPattern(newPatternForm([]))).toEqual({
      error: "Choose a component to repeat",
    });
    expect(buildPattern({ ...newPatternForm(["s1"]), count: "2 mm" })).toEqual({
      error: expect.stringMatching(/^Count: /) as unknown as string,
    });
    expect(buildPattern({ ...newPatternForm(["s1"]), axis: "edge" })).toEqual({
      error: "Pick an edge for the direction",
    });
    expect(buildPattern({ ...newPatternForm(["s1"]), kind: "hole" })).toEqual({
      error: "Pick the hole the seed sits in",
    });
    expect(
      buildPattern({
        ...newPatternForm(["s1"]),
        kind: "circular",
        angle: "400 deg",
      }),
    ).toEqual({ error: "Angle: more than 0 and at most 360°" });
  });

  it("round-trips a stored circular pattern about a picked edge", () => {
    const stored = pattern({
      pattern: {
        type: "circular",
        seed_instance_ids: ["s1"],
        axis: { kind: "edge", instance_id: "r1", signature: RIM },
        flip: true,
        count: 32,
        angle_deg: 360,
        count_expr: "32",
        angle_expr: "360 deg",
      },
    });
    const form = formFromPattern(stored.pattern);
    expect(form).toMatchObject({ kind: "circular", axis: "edge", flip: true });
    const built = buildPattern(form);
    if (!("pattern" in built)) throw new Error(built.error);
    expect(built.pattern).toEqual(stored.pattern);
  });

  it("titles patterns by kind and offers the same part's other instances", () => {
    const linear = pattern({
      id: "p2",
      pattern: {
        type: "linear",
        seed_instance_ids: ["s1"],
        direction: { kind: "origin_axis", axis: "y" },
        flip: false,
        count: 3,
        spacing_mm: 5,
      },
    });
    const all = [pattern({}), linear, pattern({ id: "p3" })];
    expect(all.map((p) => patternTitle(all, p))).toEqual([
      "Hole pattern 1",
      "Linear pattern 1",
      "Hole pattern 2",
    ]);
    expect(
      samePartInstances([RAIL_1, RAIL_2, SCREW], "r1").map((i) => i.id),
    ).toEqual(["r2"]);
  });
});

function graph(patterns: PatternResponse[]): AssemblyGraphResponse {
  return {
    assembly: {
      id: "stage",
      name: "Stage",
      owner_id: "u",
      folder_id: null,
      length_unit: "mm",
      doc_version: 3,
      created_at: "2026-10-15T00:00:00Z",
      updated_at: "2026-10-15T00:00:00Z",
    },
    doc_version: 3,
    instances: [RAIL_1, RAIL_2, SCREW],
    mates: [],
    patterns,
    can_undo: false,
    can_redo: false,
  };
}

describe("patterns in the request and the scene", () => {
  it("rides the evaluation request only when there are any", () => {
    const request = buildEvaluateAssemblyRequest(
      graph([pattern({})]),
      new Map(),
    );
    expect(request.patterns).toEqual([
      { pattern_id: "p1", order_index: 0, pattern: pattern({}).pattern },
    ]);
    expect(
      "patterns" in buildEvaluateAssemblyRequest(graph([]), new Map()),
    ).toBe(false);
  });

  it("draws each copy like its seed, selecting the seed", () => {
    const moved: Placement = { ...IDENTITY, position: { x: 25, y: 0, z: 8 } };
    const evaluation = {
      assembly_id: "stage",
      version: 3,
      status: "well_constrained",
      instances: [
        { instance_id: "s1", part_mesh_glb_id: null, placement: IDENTITY },
        {
          instance_id: "copy-1",
          part_mesh_glb_id: null,
          placement: moved,
          pattern: { pattern_id: "p1", seed_instance_id: "s1", index: 1 },
        },
      ],
      mate_errors: [],
    } as unknown as EvaluateAssemblyResult;
    const scene = buildSceneInstances({
      instances: [RAIL_1, RAIL_2, SCREW],
      evaluation,
      nested: nestedParts(evaluation, { instances: [] }),
      subPoses: new Map(),
      componentOverride: () => null,
      preview: () => null,
      byMeshId: new Map(),
      visibility: EMPTY_VISIBILITY,
    });
    const copy = scene.find((s) => s.id === "copy-1");
    expect(copy).toMatchObject({
      name: "M3x8 <1> (2)",
      balloon: 3,
      groupId: "s1",
    });
    expect(scene).toHaveLength(4);
  });

  it("names a copy inside a sub-assembly after the part sharing its mesh", () => {
    const evaluation = {
      instances: [
        {
          instance_id: "w/spoke",
          part_mesh_glb_id: "sha256:spoke",
          placement: IDENTITY,
          path: ["w", "spoke"],
        },
        {
          instance_id: "w/copy",
          part_mesh_glb_id: "sha256:spoke",
          placement: IDENTITY,
          path: ["w", "copy"],
        },
      ],
    } as unknown as EvaluateAssemblyResult;
    const request = {
      instances: [
        {
          instance_id: "w",
          part_key: "wheel@tip",
          features: [],
          sub_assembly: {
            assembly_id: "wheel",
            version: 1,
            instances: [
              {
                instance_id: "spoke",
                name: "Spoke <1>",
                part_key: "spoke-doc@tip",
                features: [],
              },
            ],
          },
        },
      ],
    } as unknown as Parameters<typeof nestedParts>[1];
    const nested = nestedParts(evaluation, request);
    expect(nested.get("w/copy")).toMatchObject({
      groupId: "w",
      name: "Spoke <1>",
      partDocumentId: "spoke-doc",
    });
  });
});
