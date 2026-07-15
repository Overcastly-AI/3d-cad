import { describe, expect, it } from "vitest";

import type {
  AssemblyGraphResponse,
  InstanceResponse,
} from "../api/assemblies";
import type { FeatureTreeResponse } from "../api/parts";
import {
  buildEvaluateAssemblyRequest,
  partKey,
  uniquePartDocumentIds,
} from "./evaluateRequest";

const IDENTITY = {
  orientation: { w: 1, x: 0, y: 0, z: 0 },
  position: { x: 0, y: 0, z: 0 },
};

function instance(over: Partial<InstanceResponse>): InstanceResponse {
  return {
    id: "i1",
    assembly_id: "a1",
    name: "Plate <1>",
    ref_document_id: "part-1",
    ref_document_kind: "part",
    ref_pinned_version: null,
    grounded: false,
    order_index: 0,
    placement: IDENTITY,
    created_at: "2026-07-15T00:00:00Z",
    updated_at: "2026-07-15T00:00:00Z",
    ...over,
  };
}

function tree(partId: string): FeatureTreeResponse {
  return {
    part_id: partId,
    tree_version: 3,
    features: [
      // A minimal sketch + extrude; only id + feature + rolled_back matter here.
      {
        id: "f-sketch",
        name: "Sketch1",
        rolled_back: false,
        feature: {
          type: "sketch",
          version: 1,
          params: {
            plane: { kind: "datum_plane", plane: "XY" },
            entities: [],
            constraints: [],
          },
        },
      },
      {
        id: "f-rolled",
        name: "Extrude2",
        rolled_back: true,
        feature: {
          type: "extrude",
          version: 1,
          params: {
            profile: { kind: "feature", feature_id: "f-sketch" },
            distance_mm: 5,
            operation: "add",
            direction: "normal",
          },
        },
      },
    ],
  } as unknown as FeatureTreeResponse;
}

function graph(
  over: Partial<AssemblyGraphResponse> = {},
): AssemblyGraphResponse {
  return {
    assembly: {
      id: "a1",
      name: "Bolted plates",
      owner_id: "u1",
      doc_version: 7,
      created_at: "2026-07-15T00:00:00Z",
      updated_at: "2026-07-15T00:00:00Z",
    },
    doc_version: 7,
    instances: [
      instance({ id: "i1", ref_document_id: "part-1", grounded: true }),
      instance({ id: "i2", ref_document_id: "part-1", grounded: false }),
    ],
    mates: [
      {
        id: "m1",
        assembly_id: "a1",
        order_index: 0,
        mate: {
          type: "lock",
          a_instance_id: "i1",
          b_instance_id: "i2",
        },
      },
    ],
    ...over,
  };
}

describe("partKey", () => {
  it("keys on ref_document_id @ tip when unpinned (v1)", () => {
    expect(partKey(instance({ ref_document_id: "part-9" }))).toBe("part-9@tip");
  });

  it("keys on the pinned version when set", () => {
    expect(partKey(instance({ ref_pinned_version: 4 }))).toBe("part-1@4");
  });

  it("gives two instances of the same part the SAME key (dedup)", () => {
    const a = partKey(instance({ id: "i1", ref_document_id: "p" }));
    const b = partKey(instance({ id: "i2", ref_document_id: "p" }));
    expect(a).toBe(b);
  });
});

describe("uniquePartDocumentIds", () => {
  it("dedups shared parts to one id", () => {
    expect(uniquePartDocumentIds(graph())).toEqual(["part-1"]);
  });
});

describe("buildEvaluateAssemblyRequest", () => {
  it("carries the graph identity, version, and deflection", () => {
    const req = buildEvaluateAssemblyRequest(
      graph(),
      new Map([["part-1", tree("part-1")]]),
    );
    expect(req.assembly_id).toBe("a1");
    expect(req.version).toBe(7);
    expect(req.linear_deflection).toBeGreaterThan(0);
  });

  it("sends the non-rolled-back feature prefix per instance and preserves grounded + placement", () => {
    const req = buildEvaluateAssemblyRequest(
      graph(),
      new Map([["part-1", tree("part-1")]]),
    );
    expect(req.instances).toHaveLength(2);
    const [i1, i2] = req.instances;
    expect(i1?.grounded).toBe(true);
    expect(i2?.grounded).toBe(false);
    // The rolled-back extrude is dropped; only the sketch prefix is sent.
    expect(i1?.features.map((f) => f.id)).toEqual(["f-sketch"]);
    expect(i1?.part_key).toBe("part-1@tip");
    expect(i2?.part_key).toBe("part-1@tip");
  });

  it("maps mates to {mate_id, order_index, mate}", () => {
    const req = buildEvaluateAssemblyRequest(
      graph(),
      new Map([["part-1", tree("part-1")]]),
    );
    expect(req.mates).toEqual([
      {
        mate_id: "m1",
        order_index: 0,
        mate: { type: "lock", a_instance_id: "i1", b_instance_id: "i2" },
      },
    ]);
  });

  it("contributes an empty prefix when a part tree is missing (no crash)", () => {
    const req = buildEvaluateAssemblyRequest(graph(), new Map());
    expect(req.instances[0]?.features).toEqual([]);
  });
});
