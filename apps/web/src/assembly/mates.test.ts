import { describe, expect, it } from "vitest";

import type { EdgeSignature, PlanarFaceSignature } from "../api/parts";
import type { MatePick } from "./mateStore";
import {
  buildMate,
  mateInstanceIds,
  mateLabel,
  mateToolLabel,
  parseMateValue,
} from "./mates";

const faceSig: PlanarFaceSignature = {
  subshape_type: "face",
  surface: "plane",
  normal: { x: 0, y: 0, z: 1 },
  centroid: { x: 5, y: 5, z: 0 },
  area_mm2: 100,
};

const axisSig: EdgeSignature = {
  subshape_type: "edge",
  curve: "circle",
  end_a: { x: 10, y: 0, z: 0 },
  end_b: { x: 10, y: 0, z: 0 },
  midpoint: { x: 10, y: 0, z: 5 },
  length_mm: 31.4,
};

const facePick = (instanceId: string): MatePick => ({
  kind: "face",
  instanceId,
  faceIndex: 0,
  signature: faceSig,
});
const axisPick = (instanceId: string): MatePick => ({
  kind: "axis",
  instanceId,
  edgeIndex: 0,
  signature: axisSig,
});
const instancePick = (instanceId: string): MatePick => ({
  kind: "instance",
  instanceId,
});

describe("buildMate", () => {
  it("builds a flush coincident from two face picks on distinct instances", () => {
    const mate = buildMate("coincident", [facePick("i1"), facePick("i2")]);
    expect(mate).toEqual({
      type: "coincident",
      flush: true,
      a: { kind: "face", instance_id: "i1", signature: faceSig },
      b: { kind: "face", instance_id: "i2", signature: faceSig },
    });
  });

  it("builds a concentric from two axis picks", () => {
    const mate = buildMate("concentric", [axisPick("i1"), axisPick("i2")]);
    expect(mate?.type).toBe("concentric");
    if (mate?.type === "concentric") {
      expect(mate.a.instance_id).toBe("i1");
      expect(mate.b.signature).toBe(axisSig);
    }
  });

  it("builds a lock from two instance picks", () => {
    const mate = buildMate("lock", [instancePick("i1"), instancePick("i2")]);
    expect(mate).toEqual({
      type: "lock",
      a_instance_id: "i1",
      b_instance_id: "i2",
    });
  });

  it("builds a distance mate from two face picks + a value", () => {
    const mate = buildMate("distance", [facePick("i1"), facePick("i2")], 12.5);
    expect(mate).toEqual({
      type: "distance",
      distance_mm: 12.5,
      a: { kind: "face", instance_id: "i1", signature: faceSig },
      b: { kind: "face", instance_id: "i2", signature: faceSig },
    });
  });

  it("builds an angle mate from two face picks + a value (signed ok)", () => {
    const mate = buildMate("angle", [facePick("i1"), facePick("i2")], -30);
    expect(mate).toEqual({
      type: "angle",
      angle_deg: -30,
      a: { kind: "face", instance_id: "i1", signature: faceSig },
      b: { kind: "face", instance_id: "i2", signature: faceSig },
    });
  });

  it("returns null for a distance/angle mate with no value", () => {
    expect(buildMate("distance", [facePick("i1"), facePick("i2")])).toBeNull();
    expect(
      buildMate("angle", [facePick("i1"), facePick("i2")], null),
    ).toBeNull();
  });

  it("returns null for a non-finite parametric value", () => {
    expect(
      buildMate("distance", [facePick("i1"), facePick("i2")], Number.NaN),
    ).toBeNull();
  });

  it("returns null for a distance mate with non-face picks", () => {
    expect(
      buildMate("distance", [axisPick("i1"), axisPick("i2")], 10),
    ).toBeNull();
  });

  it("returns null for a distance mate on the same instance", () => {
    expect(
      buildMate("distance", [facePick("i1"), facePick("i1")], 10),
    ).toBeNull();
  });

  it("returns null for an incomplete pair", () => {
    expect(buildMate("coincident", [facePick("i1")])).toBeNull();
    expect(buildMate("distance", [facePick("i1")], 10)).toBeNull();
  });

  it("returns null when both picks are on the same instance", () => {
    expect(
      buildMate("coincident", [facePick("i1"), facePick("i1")]),
    ).toBeNull();
  });

  it("returns null for a kind/tool mismatch (faces on a concentric)", () => {
    expect(
      buildMate("concentric", [facePick("i1"), facePick("i2")]),
    ).toBeNull();
  });
});

describe("mateInstanceIds", () => {
  it("reads both ids from a lock", () => {
    expect(
      mateInstanceIds({
        type: "lock",
        a_instance_id: "i1",
        b_instance_id: "i2",
      }),
    ).toEqual(["i1", "i2"]);
  });

  it("reads both ids from a coincident's face refs", () => {
    const mate = buildMate("coincident", [facePick("i1"), facePick("i2")]);
    expect(mate && mateInstanceIds(mate)).toEqual(["i1", "i2"]);
  });
});

describe("mateLabel", () => {
  it("names each stored mate kind", () => {
    expect(
      mateLabel({ type: "lock", a_instance_id: "a", b_instance_id: "b" }),
    ).toBe("Lock");
  });
});

describe("mateToolLabel", () => {
  it("names the parametric tools", () => {
    expect(mateToolLabel("distance")).toBe("Distance");
    expect(mateToolLabel("angle")).toBe("Angle");
  });
});

describe("parseMateValue", () => {
  it("parses finite signed numbers", () => {
    expect(parseMateValue("12.5")).toBe(12.5);
    expect(parseMateValue(" -30 ")).toBe(-30);
    expect(parseMateValue("0")).toBe(0);
  });

  it("rejects empty / non-numeric input", () => {
    expect(parseMateValue("")).toBeNull();
    expect(parseMateValue("  ")).toBeNull();
    expect(parseMateValue("abc")).toBeNull();
  });
});
