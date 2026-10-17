import { describe, expect, it } from "vitest";

import type {
  AssemblyGraphResponse,
  EvaluateAssemblyResult,
  InstanceResponse,
  Placement,
} from "../api/assemblies";
import type { MirrorResponse } from "../api/mirrors";
import type { PlanarFaceSignature } from "../api/partTypes";
import { EMPTY_VISIBILITY } from "../viewport/instanceVisibility";
import { buildEvaluateAssemblyRequest } from "./evaluateRequest";
import {
  buildMirror,
  canBeOppositeHand,
  formFromMirror,
  mirrorSeedNames,
  mirrorTitle,
  mirrorWarning,
  newMirrorForm,
} from "./mirrors";
import { usePatternPickStore } from "./patternStore";
import { buildSceneInstances } from "./sceneInstances";
import { nestedParts } from "./subAssemblies";

const IDENTITY: Placement = {
  position: { x: 0, y: 0, z: 0 },
  orientation: { x: 0, y: 0, z: 0, w: 1 },
};

const END_FACE: PlanarFaceSignature = {
  subshape_type: "face",
  surface: "plane",
  normal: { x: 1, y: 0, z: 0 },
  centroid: { x: 60, y: 5, z: 5 },
  area_mm2: 100,
};

function instance(over: Partial<InstanceResponse>): InstanceResponse {
  return {
    id: "a1",
    assembly_id: "crankset",
    name: "Crank arm <1>",
    ref_document_id: "arm",
    ref_document_kind: "part",
    ref_pinned_version: null,
    grounded: true,
    order_index: 0,
    placement: IDENTITY,
    created_at: "2026-10-17T00:00:00Z",
    updated_at: "2026-10-17T00:00:00Z",
    ...over,
  };
}

const ARM = instance({});
const SPINDLE = instance({
  id: "s1",
  name: "Spindle <1>",
  ref_document_id: "spindle",
  order_index: 1,
});
const PEDALS = instance({
  id: "p1",
  name: "Pedal set <1>",
  ref_document_id: "pedals",
  ref_document_kind: "assembly",
  order_index: 2,
});

function mirror(over: Partial<MirrorResponse["mirror"]>): MirrorResponse {
  return {
    id: "m1",
    assembly_id: "crankset",
    order_index: 0,
    mirror: {
      seed_instance_ids: ["a1"],
      plane: { kind: "origin_plane", plane: "yz", offset_mm: 0 },
      opposite_hand_instance_ids: [],
      ...over,
    },
  };
}

function graph(mirrors: MirrorResponse[]): AssemblyGraphResponse {
  return {
    assembly: {
      id: "crankset",
      name: "Crankset",
      owner_id: "u",
      folder_id: null,
      length_unit: "mm",
      doc_version: 3,
      created_at: "2026-10-17T00:00:00Z",
      updated_at: "2026-10-17T00:00:00Z",
    },
    doc_version: 3,
    instances: [ARM, SPINDLE, PEDALS],
    mates: [],
    mirrors,
    can_undo: false,
    can_redo: false,
  };
}

describe("the mirror form", () => {
  it("builds an origin-plane mirror with a typed offset", () => {
    const form = { ...newMirrorForm(["a1"]), plane: "xy" as const };
    form.offset = "2 * 10 mm";
    form.opposite = ["a1"];
    expect(buildMirror(form)).toEqual({
      mirror: {
        seed_instance_ids: ["a1"],
        plane: { kind: "origin_plane", plane: "xy", offset_mm: 20 },
        opposite_hand_instance_ids: ["a1"],
      },
    });
  });

  it("says what is missing, and drops an opposite hand that is not a seed", () => {
    expect(buildMirror(newMirrorForm([]))).toEqual({
      error: "Choose a component to mirror",
    });
    const face = { ...newMirrorForm(["a1"]), plane: "face" as const };
    expect(buildMirror(face)).toEqual({
      error: "Pick the face to mirror about",
    });
    const bad = { ...newMirrorForm(["a1"]), offset: "3 deg" };
    expect("error" in buildMirror(bad)).toBe(true);
    const stale = { ...newMirrorForm(["a1"]), opposite: ["s1"] };
    const built = buildMirror(stale);
    expect(
      "mirror" in built && built.mirror.opposite_hand_instance_ids,
    ).toEqual([]);
  });

  it("round-trips a stored face-plane mirror through the form", () => {
    const stored = mirror({
      seed_instance_ids: ["a1", "s1"],
      opposite_hand_instance_ids: ["a1"],
      plane: { kind: "face", instance_id: "s1", signature: END_FACE },
    });
    const form = formFromMirror(stored.mirror);
    expect(form).toMatchObject({
      seeds: ["a1", "s1"],
      opposite: ["a1"],
      plane: "face",
      face: { instanceId: "s1", signature: END_FACE },
    });
    expect(buildMirror(form)).toEqual({ mirror: stored.mirror });
    expect(formFromMirror(mirror({}).mirror)).toMatchObject({
      plane: "yz",
      offset: "0 mm",
    });
  });

  it("offers an opposite hand on parts only", () => {
    expect(canBeOppositeHand(ARM)).toBe(true);
    expect(canBeOppositeHand(PEDALS)).toBe(false);
  });
});

describe("mirrors in the tree", () => {
  it("names a mirror and what it reflects", () => {
    const stored = [
      mirror({}),
      { ...mirror({ opposite_hand_instance_ids: ["a1"] }), id: "m2" },
    ];
    expect(mirrorTitle(stored, stored[1] as MirrorResponse)).toBe("Mirror 2");
    expect(mirrorSeedNames([ARM], (stored[1] as MirrorResponse).mirror)).toBe(
      "Crank arm <1> (opposite hand)",
    );
  });

  it("warns for a copy that is not a mirror image, and for a failure", () => {
    expect(
      mirrorWarning([ARM], { mirror_id: "m1", placed: 1, asymmetric: [] }),
    ).toBeNull();
    expect(
      mirrorWarning([ARM], { mirror_id: "m1", placed: 1, asymmetric: ["a1"] }),
    ).toMatch(/^Crank arm <1>: not symmetric.*opposite hand$/);
    expect(
      mirrorWarning([ARM], {
        mirror_id: "m1",
        placed: 0,
        error_code: "subshape_unresolved",
        error_message: "mirror plane: no face",
      }),
    ).toBe("mirror plane: no face");
  });
});

describe("mirrors in the request and the scene", () => {
  it("rides the evaluation request only when there are any", () => {
    const request = buildEvaluateAssemblyRequest(
      graph([mirror({})]),
      new Map(),
    );
    expect(request.mirrors).toEqual([
      { mirror_id: "m1", order_index: 0, mirror: mirror({}).mirror },
    ]);
    expect(
      "mirrors" in buildEvaluateAssemblyRequest(graph([]), new Map()),
    ).toBe(false);
  });

  it("draws each twin with its own mesh, selecting the seed", () => {
    const twin: Placement = { ...IDENTITY, position: { x: -70, y: 0, z: 0 } };
    const evaluation = {
      instances: [
        {
          instance_id: "a1",
          part_mesh_glb_id: "sha256:arm",
          placement: IDENTITY,
        },
        {
          instance_id: "twin",
          part_mesh_glb_id: "sha256:arm-opposite",
          placement: twin,
          mirror: {
            mirror_id: "m1",
            seed_instance_id: "a1",
            opposite_hand: true,
          },
        },
        {
          instance_id: "copy",
          part_mesh_glb_id: "sha256:arm",
          placement: twin,
          mirror: { mirror_id: "m2", seed_instance_id: "a1" },
        },
      ],
    } as unknown as EvaluateAssemblyResult;
    const opposite = { surface: "opposite" } as never;
    const scene = buildSceneInstances({
      instances: [ARM],
      evaluation,
      nested: nestedParts(evaluation, { instances: [] }),
      subPoses: new Map(),
      componentOverride: () => null,
      preview: () => null,
      byMeshId: new Map([["sha256:arm-opposite", opposite]]),
      visibility: EMPTY_VISIBILITY,
    });
    expect(scene.find((s) => s.id === "twin")).toMatchObject({
      name: "Crank arm <1> (opposite hand)",
      groupId: "a1",
      patternCopy: true,
      geometry: opposite,
    });
    expect(scene.find((s) => s.id === "copy")?.name).toBe(
      "Crank arm <1> (mirror)",
    );
  });
});

describe("the mirror plane pick", () => {
  it("takes a face only while a plane pick is armed", () => {
    const store = usePatternPickStore.getState();
    store.pickFace("a1", END_FACE);
    expect(usePatternPickStore.getState().pickedFace).toBeNull();
    store.arm("plane");
    usePatternPickStore.getState().pickEdge("a1", {
      subshape_type: "edge",
      curve: "line",
      end_a: { x: 0, y: 0, z: 0 },
      end_b: { x: 1, y: 0, z: 0 },
      midpoint: { x: 0.5, y: 0, z: 0 },
      length_mm: 1,
    });
    expect(usePatternPickStore.getState().picked).toBeNull();
    usePatternPickStore.getState().pickFace("a1", END_FACE);
    expect(usePatternPickStore.getState()).toMatchObject({
      picking: null,
      pickedFace: { instanceId: "a1", signature: END_FACE },
    });
    usePatternPickStore.getState().clear();
  });
});
