import { describe, expect, it } from "vitest";

import type { HoleParams, PlanarFaceSignature, Vec3 } from "../api/parts";
import {
  applyHoleFace,
  applyHolePosition,
  buildHoleParams,
  canSubmitHole,
  coplanarVertexIndices,
  csinkAngleError,
  defaultHoleForm,
  depthError,
  diameterError,
  formFromHoleParams,
  type HoleForm,
  holeThreadDesignation,
  parseCsinkAngleDeg,
  positionReadout,
  recessDiameterError,
  samePoint,
  applyTapDrill,
  applyTapped,
  applyThreadNominal,
  applyThreadPitch,
  boreIsTapDrill,
  threadBoreError,
  threadDesignation,
  threadPitchError,
  threadSizeError,
} from "./hole";

const TOP: PlanarFaceSignature = {
  normal: { x: 0, y: 0, z: 1 },
  centroid: { x: 5, y: 5, z: 10 },
  area_mm2: 100,
  subshape_type: "face",
  surface: "plane",
};

const withFace = (): HoleForm =>
  applyHoleFace(
    defaultHoleForm(null, "mm"),
    { signature: TOP, anchorId: "extrude-1" },
    "mm",
  );

describe("defaultHoleForm", () => {
  it("is a Ø6 through-all SIMPLE hole with nothing picked yet", () => {
    const f = defaultHoleForm(null, "mm");
    expect(f.face).toBeNull();
    expect(f.position).toBeNull();
    expect(f.diameterInput).toBe("6");
    expect(f.depthMode).toBe("through_all");
    expect(f.typeKind).toBe("simple");
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
    const moved = applyHolePosition(withFace(), { x: 2, y: 3, z: 10 }, "mm");
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
    expect(buildHoleParams(defaultHoleForm(null, "mm"), "mm")).toBeNull();
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

  it("OMITS `type` for a simple hole (backward-compatible slice-1 shape)", () => {
    const params = buildHoleParams(withFace(), "mm");
    expect(params).not.toBeNull();
    expect(params).not.toHaveProperty("type");
  });

  it("builds a counterbore recess, guarding Ø-exceeds-bore + positive depth", () => {
    const cbore: HoleForm = {
      ...withFace(),
      typeKind: "counterbore",
      cboreDiameterInput: "11",
      cboreDepthInput: "6",
    };
    expect(buildHoleParams(cbore, "mm")?.type).toEqual({
      kind: "counterbore",
      cbore_diameter_mm: 11,
      cbore_depth_mm: 6,
    });
    // Recess Ø must exceed the Ø6 bore.
    expect(
      buildHoleParams({ ...cbore, cboreDiameterInput: "6" }, "mm"),
    ).toBeNull();
    expect(
      buildHoleParams({ ...cbore, cboreDiameterInput: "5" }, "mm"),
    ).toBeNull();
    // Depth must be a positive length.
    expect(
      buildHoleParams({ ...cbore, cboreDepthInput: "0" }, "mm"),
    ).toBeNull();
  });

  it("builds a countersink recess, guarding Ø-exceeds-bore + angle range", () => {
    const csink: HoleForm = {
      ...withFace(),
      typeKind: "countersink",
      csinkDiameterInput: "12",
      csinkAngleInput: "90",
    };
    expect(buildHoleParams(csink, "mm")?.type).toEqual({
      kind: "countersink",
      csink_diameter_mm: 12,
      csink_angle_deg: 90,
    });
    expect(
      buildHoleParams({ ...csink, csinkDiameterInput: "6" }, "mm"),
    ).toBeNull();
    // Angle must be within the open interval (0, 180).
    expect(
      buildHoleParams({ ...csink, csinkAngleInput: "0" }, "mm"),
    ).toBeNull();
    expect(
      buildHoleParams({ ...csink, csinkAngleInput: "180" }, "mm"),
    ).toBeNull();
  });
});

describe("recessDiameterError", () => {
  it("flags a non-positive or not-wider-than-bore recess, passes a wider one", () => {
    expect(recessDiameterError("", "6", "mm")).toBeNull(); // pending
    expect(recessDiameterError("0", "6", "mm")).not.toBeNull();
    expect(recessDiameterError("6", "6", "mm")).not.toBeNull(); // equal ≠ wider
    expect(recessDiameterError("5", "6", "mm")).not.toBeNull();
    expect(recessDiameterError("11", "6", "mm")).toBeNull();
  });
});

describe("parseCsinkAngleDeg / csinkAngleError", () => {
  it("accepts the open interval (0, 180) and rejects the rest", () => {
    expect(parseCsinkAngleDeg("90")).toBe(90);
    expect(parseCsinkAngleDeg("82")).toBe(82);
    expect(parseCsinkAngleDeg("0")).toBeNull();
    expect(parseCsinkAngleDeg("180")).toBeNull();
    expect(parseCsinkAngleDeg("abc")).toBeNull();
    expect(csinkAngleError("")).toBeNull();
    expect(csinkAngleError("90")).toBeNull();
    expect(csinkAngleError("200")).not.toBeNull();
  });
});

describe("canSubmitHole", () => {
  it("mirrors buildHoleParams", () => {
    expect(canSubmitHole(defaultHoleForm(null, "mm"), "mm")).toBe(false);
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
    expect(form.typeKind).toBe("simple");
    // The seeded form rebuilds to the same params.
    expect(buildHoleParams(form, "mm")).toEqual(params);
  });

  const face: HoleParams["face"] = {
    kind: "subshape",
    feature_id: "extrude-1",
    subshape_type: "face",
    selector: { selector_version: 1, signature: TOP },
  };

  it("round-trips a counterbore hole", () => {
    const params: HoleParams = {
      face,
      position: { x: 5, y: 5, z: 10 },
      diameter_mm: 6,
      depth: { kind: "through_all" },
      type: {
        kind: "counterbore",
        cbore_diameter_mm: 11,
        cbore_depth_mm: 6,
      },
    };
    const form = formFromHoleParams(params, "mm");
    expect(form.typeKind).toBe("counterbore");
    expect(form.cboreDiameterInput).toBe("11");
    expect(form.cboreDepthInput).toBe("6");
    expect(buildHoleParams(form, "mm")).toEqual(params);
  });

  it("round-trips a TAPPED counterbored hole — thread is a SIBLING of type", () => {
    const params: HoleParams = {
      face,
      position: { x: 5, y: 5, z: 10 },
      diameter_mm: 8.5,
      depth: { kind: "through_all" },
      type: {
        kind: "counterbore",
        cbore_diameter_mm: 16,
        cbore_depth_mm: 6,
      },
      thread: {
        standard: "iso_metric",
        nominal_diameter_mm: 10,
        pitch_mm: 1.5,
      },
    };
    const form = formFromHoleParams(params, "mm");
    expect(form.tapped).toBe(true);
    expect(form.typeKind).toBe("counterbore");
    expect(threadDesignation(form)).toBe("M10x1.5");
    expect(buildHoleParams(form, "mm")).toEqual(params);
  });

  it("round-trips an untapped hole with `thread` still absent from the wire", () => {
    const params: HoleParams = {
      face,
      position: { x: 5, y: 5, z: 10 },
      diameter_mm: 6,
      depth: { kind: "through_all" },
    };
    const form = formFromHoleParams(params, "mm");
    expect(form.tapped).toBe(false);
    const built = buildHoleParams(form, "mm");
    expect(built).toEqual(params);
    expect(built !== null && "thread" in built).toBe(false);
  });

  it("round-trips a countersink hole", () => {
    const params: HoleParams = {
      face,
      position: { x: 5, y: 5, z: 10 },
      diameter_mm: 6,
      depth: { kind: "through_all" },
      type: {
        kind: "countersink",
        csink_diameter_mm: 12,
        csink_angle_deg: 82,
      },
    };
    const form = formFromHoleParams(params, "mm");
    expect(form.typeKind).toBe("countersink");
    expect(form.csinkDiameterInput).toBe("12");
    expect(form.csinkAngleInput).toBe("82");
    expect(buildHoleParams(form, "mm")).toEqual(params);
  });
});

describe("tapped holes — the derived bore", () => {
  it("derives the ISO tap drill when Tapped is ticked (M6x1 -> 5)", () => {
    const f = applyTapped(withFace(), true, "mm");
    expect(f.tapped).toBe(true);
    expect(threadDesignation(f)).toBe("M6x1");
    expect(f.diameterInput).toBe("5");
    expect(boreIsTapDrill(f, "mm")).toBe(true);
  });

  it("resets to the COARSE pitch when the size changes, re-deriving the bore", () => {
    let f = applyTapped(withFace(), true, "mm");
    f = applyThreadPitch(f, 0.75, "mm"); // a fine M6 pitch
    expect(f.diameterInput).toBe("5.25");
    f = applyThreadNominal(f, 10, "mm");
    expect(f.threadPitchMm).toBe(1.5); // coarse, not the previous 0.75
    expect(f.diameterInput).toBe("8.5");
  });

  it("leaves the bore alone when Tapped is unticked", () => {
    const on = applyTapped(withFace(), true, "mm");
    const off = applyTapped(on, false, "mm");
    expect(off.tapped).toBe(false);
    expect(off.diameterInput).toBe("5");
  });

  it("keeps an override, and restores the derived value on demand", () => {
    let f = applyThreadNominal(applyTapped(withFace(), true, "mm"), 8, "mm");
    expect(f.diameterInput).toBe("6.75");
    f = { ...f, diameterInput: "6.8" }; // the shop's rounded stock drill
    expect(boreIsTapDrill(f, "mm")).toBe(false);
    expect(threadBoreError(f, "mm")).toBeNull(); // inside [minor, nominal)
    expect(applyTapDrill(f, "mm").diameterInput).toBe("6.75");
  });

  it("derives in the document unit while the designation stays metric", () => {
    const f = applyThreadNominal(applyTapped(withFace(), true, "in"), 10, "in");
    expect(threadDesignation(f)).toBe("M10x1.5");
    expect(Number(f.diameterInput)).toBeCloseTo(8.5 / 25.4, 6);
    expect(boreIsTapDrill(f, "in")).toBe(true);
  });
});

describe("tapped holes — the two typed thread errors", () => {
  it("threadBoreError names the direction of the miss and the fix", () => {
    const base = applyThreadNominal(
      applyTapped(withFace(), true, "mm"),
      10,
      "mm",
    );
    expect(threadBoreError(base, "mm")).toBeNull();
    expect(threadBoreError({ ...base, diameterInput: "8" }, "mm")).toMatch(
      /Too small to tap M10x1.5.*8\.5 mm tap drill/,
    );
    expect(threadBoreError({ ...base, diameterInput: "12" }, "mm")).toMatch(
      /Too wide to tap M10x1.5/,
    );
    // Untapped holes have no thread to mismatch.
    expect(
      threadBoreError({ ...base, tapped: false, diameterInput: "12" }, "mm"),
    ).toBeNull();
  });

  it("threadSizeError fires for a size off the ISO 261 series", () => {
    const f = { ...applyTapped(withFace(), true, "mm"), threadNominalMm: 7 };
    expect(threadSizeError(f)).toMatch(/M7 isn't a standard ISO size/);
    // The pitch message stays quiet — the size owns the failure.
    expect(threadPitchError(f)).toBeNull();
  });

  it("threadPitchError names the pitches that size IS standardised at", () => {
    const f = {
      ...applyThreadNominal(applyTapped(withFace(), true, "mm"), 10, "mm"),
      threadPitchMm: 1.75,
    };
    expect(threadSizeError(f)).toBeNull();
    expect(threadPitchError(f)).toBe(
      "M10 is standardised at 1.5, 1.25, 1, 0.75 mm. Choose a listed pitch.",
    );
  });

  it("blocks the build for either error — the server would build no body", () => {
    const good = applyThreadNominal(
      applyTapped(withFace(), true, "mm"),
      10,
      "mm",
    );
    expect(buildHoleParams(good, "mm")).not.toBeNull();
    // An unsupported designation.
    expect(buildHoleParams({ ...good, threadPitchMm: 1.75 }, "mm")).toBeNull();
    // A bore the tap cannot cut.
    expect(buildHoleParams({ ...good, diameterInput: "12" }, "mm")).toBeNull();
  });
});

describe("holeThreadDesignation", () => {
  const face: HoleParams["face"] = {
    kind: "subshape",
    feature_id: "extrude-1",
    subshape_type: "face",
    selector: { selector_version: 1, signature: TOP },
  };
  const base: HoleParams = {
    face,
    position: { x: 5, y: 5, z: 10 },
    diameter_mm: 8.5,
    depth: { kind: "through_all" },
  };

  it("is null for an untapped hole and the callout for a tapped one", () => {
    expect(holeThreadDesignation(base)).toBeNull();
    expect(
      holeThreadDesignation({
        ...base,
        thread: {
          standard: "iso_metric",
          nominal_diameter_mm: 10,
          pitch_mm: 1.5,
        },
      }),
    ).toBe("M10x1.5");
  });

  it("treats an explicit null thread as untapped (the wire allows both)", () => {
    expect(holeThreadDesignation({ ...base, thread: null })).toBeNull();
  });
});

describe("positionReadout", () => {
  it("names the centre while the point sits on the centroid", () => {
    expect(positionReadout(withFace())).toContain("Centre of face");
    const moved = applyHolePosition(withFace(), { x: 0, y: 0, z: 10 }, "mm");
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
