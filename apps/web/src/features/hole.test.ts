import { describe, expect, it } from "vitest";

import type { HoleParams, PlanarFaceSignature, Vec3 } from "../api/parts";
import {
  applyHoleFace,
  applyHolePosition,
  buildHoleParams,
  canSubmitHole,
  coplanarVertexIndices,
  defaultHoleForm,
  depthError,
  diameterError,
  formFromHoleParams,
  type HoleForm,
  positionReadout,
  samePoint,
} from "./hole";

const TOP: PlanarFaceSignature = {
  normal: { x: 0, y: 0, z: 1 },
  centroid: { x: 5, y: 5, z: 10 },
  area_mm2: 100,
  subshape_type: "face",
  surface: "plane",
};

const withFace = (): HoleForm =>
  applyHoleFace(defaultHoleForm(), {
    signature: TOP,
    anchorId: "extrude-1",
  });

describe("defaultHoleForm", () => {
  it("is a Ø6 through-all with nothing picked yet", () => {
    const f = defaultHoleForm();
    expect(f.face).toBeNull();
    expect(f.position).toBeNull();
    expect(f.diameterInput).toBe("6");
    expect(f.depthMode).toBe("through_all");
  });
});

describe("applyHoleFace", () => {
  it("adopts the face and seeds the position to its centroid", () => {
    const f = withFace();
    expect(f.face?.anchorId).toBe("extrude-1");
    expect(f.position).toEqual(TOP.centroid);
  });
});

describe("applyHolePosition", () => {
  it("refines the drill point without touching the face", () => {
    const moved = applyHolePosition(withFace(), { x: 2, y: 3, z: 10 });
    expect(moved.position).toEqual({ x: 2, y: 3, z: 10 });
    expect(moved.face?.anchorId).toBe("extrude-1");
  });
});

describe("diameterError / depthError", () => {
  it("flags a non-positive or unparseable value, passes a valid one", () => {
    expect(diameterError("", "mm")).toBeNull(); // pending, not wrong
    expect(diameterError("0", "mm")).not.toBeNull();
    expect(diameterError("-1", "mm")).not.toBeNull();
    expect(diameterError("abc", "mm")).not.toBeNull();
    expect(diameterError("6", "mm")).toBeNull();
    expect(depthError("5", "mm")).toBeNull();
    expect(depthError("0", "mm")).not.toBeNull();
  });
});

describe("buildHoleParams", () => {
  it("returns null until a face + point + valid diameter are present", () => {
    expect(buildHoleParams(defaultHoleForm(), "mm")).toBeNull();
    const noDiameter: HoleForm = { ...withFace(), diameterInput: "0" };
    expect(buildHoleParams(noDiameter, "mm")).toBeNull();
  });

  it("builds a through-all hole with the face's stage-1 SubshapeRef", () => {
    const params = buildHoleParams(withFace(), "mm");
    expect(params).not.toBeNull();
    expect(params?.diameter_mm).toBe(6);
    expect(params?.depth).toEqual({ kind: "through_all" });
    expect(params?.position).toEqual(TOP.centroid);
    expect(params?.face.kind).toBe("subshape");
    expect(params?.face.feature_id).toBe("extrude-1");
    expect(params?.face.subshape_type).toBe("face");
    expect(params?.face.selector.signature).toEqual(TOP);
  });

  it("builds a blind hole, guarding a non-positive depth", () => {
    const blind: HoleForm = {
      ...withFace(),
      depthMode: "blind",
      depthInput: "4",
    };
    expect(buildHoleParams(blind, "mm")?.depth).toEqual({
      kind: "blind",
      depth_mm: 4,
    });
    expect(buildHoleParams({ ...blind, depthInput: "0" }, "mm")).toBeNull();
  });

  it("reads lengths through the document unit", () => {
    const inch: HoleForm = { ...withFace(), diameterInput: "0.5" };
    expect(buildHoleParams(inch, "in")?.diameter_mm).toBeCloseTo(12.7, 6);
  });
});

describe("canSubmitHole", () => {
  it("mirrors buildHoleParams", () => {
    expect(canSubmitHole(defaultHoleForm(), "mm")).toBe(false);
    expect(canSubmitHole(withFace(), "mm")).toBe(true);
  });
});

describe("formFromHoleParams round-trip", () => {
  it("seeds an editable form from stored blind params", () => {
    const params: HoleParams = {
      face: {
        kind: "subshape",
        feature_id: "extrude-1",
        subshape_type: "face",
        selector: { selector_version: 1, signature: TOP },
      },
      position: { x: 5, y: 5, z: 10 },
      diameter_mm: 8,
      depth: { kind: "blind", depth_mm: 3 },
    };
    const form = formFromHoleParams(params, "mm");
    expect(form.depthMode).toBe("blind");
    expect(form.depthInput).toBe("3");
    expect(form.diameterInput).toBe("8");
    expect(form.face?.anchorId).toBe("extrude-1");
    // The seeded form rebuilds to the same params.
    expect(buildHoleParams(form, "mm")).toEqual(params);
  });
});

describe("positionReadout", () => {
  it("names the centre while the point sits on the centroid", () => {
    expect(positionReadout(withFace())).toContain("Centre of face");
    const moved = applyHolePosition(withFace(), { x: 0, y: 0, z: 10 });
    expect(positionReadout(moved)).not.toContain("Centre");
    expect(positionReadout(moved)).toContain("mm");
  });
});

describe("coplanarVertexIndices", () => {
  const verts: Vec3[] = [
    { x: 0, y: 0, z: 10 }, // on the z=10 plane
    { x: 10, y: 10, z: 10 }, // on the plane
    { x: 0, y: 0, z: 0 }, // a bottom vertex, off the plane
  ];
  it("keeps only vertices on the face plane", () => {
    expect(coplanarVertexIndices(TOP, verts)).toEqual([0, 1]);
  });
});

describe("samePoint", () => {
  it("treats within-epsilon points as the same placement", () => {
    expect(samePoint({ x: 1, y: 2, z: 3 }, { x: 1, y: 2, z: 3 })).toBe(true);
    expect(samePoint(null, { x: 0, y: 0, z: 0 })).toBe(false);
    expect(samePoint({ x: 1, y: 2, z: 3 }, { x: 1, y: 2, z: 4 })).toBe(false);
  });
});
