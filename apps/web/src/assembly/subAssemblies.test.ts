import { describe, expect, it } from "vitest";

import type {
  AssemblyGraphResponse,
  EvaluateAssemblyRequest,
  EvaluateAssemblyResult,
  InstanceResponse,
  Placement,
} from "../api/assemblies";
import { buildEvaluateAssemblyRequest } from "./evaluateRequest";
import { buildSceneInstances } from "./sceneInstances";
import {
  componentClashIds,
  componentName,
  componentOf,
  composePlacement,
  invertPlacement,
  nestedParts,
  nestedPlacement,
  subAssemblyStamp,
  uniqueSubAssemblyIds,
} from "./subAssemblies";

const S = Math.SQRT1_2;
const IDENTITY: Placement = {
  position: { x: 0, y: 0, z: 0 },
  orientation: { x: 0, y: 0, z: 0, w: 1 },
};
const TURN_Z: Placement = {
  position: { x: 100, y: 50, z: 0 },
  orientation: { x: 0, y: 0, z: S, w: S },
};

function instance(over: Partial<InstanceResponse>): InstanceResponse {
  return {
    id: "i1",
    assembly_id: "bike",
    name: "Frame <1>",
    ref_document_id: "frame",
    ref_document_kind: "part",
    ref_pinned_version: null,
    grounded: false,
    order_index: 0,
    placement: IDENTITY,
    created_at: "2026-10-15T00:00:00Z",
    updated_at: "2026-10-15T00:00:00Z",
    ...over,
  };
}

const WHEEL = instance({
  id: "w1",
  name: "Wheel <1>",
  ref_document_id: "wheel",
  ref_document_kind: "assembly",
  grounded: true,
});
const FRAME = instance({ id: "f1", order_index: 1 });

const WHEEL_REQUEST: EvaluateAssemblyRequest = {
  assembly_id: "wheel",
  version: 4,
  linear_deflection: 0.1,
  instances: [
    {
      instance_id: "rim",
      name: "Rim <1>",
      part_key: "rim-doc@tip",
      grounded: true,
      placement: IDENTITY,
      features: [],
      materials: null,
    },
  ],
};

function graph(): AssemblyGraphResponse {
  return {
    assembly: {
      id: "bike",
      name: "Bike",
      owner_id: "u",
      folder_id: null,
      length_unit: "mm",
      doc_version: 2,
      created_at: "2026-10-15T00:00:00Z",
      updated_at: "2026-10-15T00:00:00Z",
    },
    doc_version: 2,
    instances: [WHEEL, FRAME],
    mates: [],
    can_undo: false,
    can_redo: false,
  };
}

const RIM_POSE: Placement = {
  position: { x: 3, y: 0, z: 10 },
  orientation: { x: 0, y: 0, z: 0, w: 1 },
};

function evaluation(): EvaluateAssemblyResult {
  return {
    assembly_id: "bike",
    version: 2,
    status: "well_constrained",
    instances: [
      {
        instance_id: "occ-rim",
        part_mesh_glb_id: "sha256:rim",
        placement: RIM_POSE,
        path: ["w1", "rim"],
      },
      {
        instance_id: "f1",
        part_mesh_glb_id: "sha256:frame",
        placement: IDENTITY,
      },
    ],
    sub_assemblies: [{ instance_id: "w1", placement: IDENTITY }],
  } as EvaluateAssemblyResult;
}

describe("embedding sub-assemblies in the request", () => {
  it("lists each referenced sub-assembly once", () => {
    expect(uniqueSubAssemblyIds(graph())).toEqual(["wheel"]);
  });

  it("carries the sub-assembly's own request and no features of its own", () => {
    const request = buildEvaluateAssemblyRequest(
      graph(),
      new Map(),
      new Map(),
      new Map([["wheel", WHEEL_REQUEST]]),
    );
    const [wheel, frame] = request.instances;
    expect(wheel?.sub_assembly).toBe(WHEEL_REQUEST);
    expect(wheel?.features).toEqual([]);
    expect(wheel?.part_key).toBe("wheel@tip");
    expect(frame?.sub_assembly).toBeUndefined();
  });

  it("changes its stamp when a nested request changes", () => {
    const before = subAssemblyStamp(new Map([["wheel", WHEEL_REQUEST]]));
    const edited = { ...WHEEL_REQUEST, version: 5 };
    expect(subAssemblyStamp(new Map([["wheel", edited]]))).not.toBe(before);
  });
});

describe("nested parts", () => {
  const request = buildEvaluateAssemblyRequest(
    graph(),
    new Map(),
    new Map(),
    new Map([["wheel", WHEEL_REQUEST]]),
  );

  it("reads each nested part off its result path", () => {
    const nested = nestedParts(evaluation(), request);
    expect([...nested.values()]).toEqual([
      {
        id: "occ-rim",
        groupId: "w1",
        name: "Rim <1>",
        partDocumentId: "rim-doc",
        features: [],
      },
    ]);
    expect(componentOf(nested, "occ-rim")).toBe("w1");
    expect(componentOf(nested, "f1")).toBe("f1");
    expect(componentName([WHEEL, FRAME], nested, "occ-rim")).toBe(
      "Wheel <1> / Rim <1>",
    );
    expect(componentName([WHEEL, FRAME], nested, "f1")).toBe("Frame <1>");
    const lifted = componentClashIds(
      { measured: new Set(["occ-rim", "f1"]), unverifiedOnly: new Set() },
      nested,
    );
    expect([...lifted.measured].sort()).toEqual(["f1", "w1"]);
  });

  it("draws the parts of a sub-assembly as the component's scene instances", () => {
    const nested = nestedParts(evaluation(), request);
    const scene = buildSceneInstances({
      instances: [WHEEL, FRAME],
      evaluation: evaluation(),
      nested,
      subPoses: new Map([["w1", IDENTITY]]),
      componentOverride: (id) => (id === "w1" ? TURN_Z : null),
      preview: () => null,
      byMeshId: new Map(),
      visibility: {},
    });
    expect(scene.map((s) => [s.id, s.groupId, s.balloon, s.grounded])).toEqual([
      ["occ-rim", "w1", 1, true],
      ["f1", undefined, 2, false],
    ]);
    expect(scene[0]?.name).toBe("Wheel <1> / Rim <1>");
    // Moving the wheel to TURN_Z carries the rim: (3, 0, 10) turned 90° about
    // Z is (0, 3, 10), then shifted by (100, 50, 0). Scene is Y-up.
    const [x, y, z] = scene[0]?.transform.position ?? [];
    expect(x).toBeCloseTo(100);
    expect(y).toBeCloseTo(10);
    expect(z).toBeCloseTo(-53);
  });
});

describe("pose algebra", () => {
  it("carries a part with its component", () => {
    const moved = nestedPlacement(TURN_Z, IDENTITY, RIM_POSE);
    expect(moved.position.x).toBeCloseTo(100);
    expect(moved.position.y).toBeCloseTo(53);
    expect(moved.position.z).toBeCloseTo(10);
    expect(moved.orientation.z).toBeCloseTo(S);
  });

  it("inverts a rigid transform", () => {
    const round = composePlacement(TURN_Z, invertPlacement(TURN_Z));
    expect(round.position.x).toBeCloseTo(0);
    expect(round.position.y).toBeCloseTo(0);
    expect(Math.abs(round.orientation.w)).toBeCloseTo(1);
  });
});
