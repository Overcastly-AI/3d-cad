import { describe, expect, it } from "vitest";

import type { DraftParams, PlanarFaceSignature } from "../api/parts";
import {
  angleError,
  buildDraftParams,
  buildNeutralPlane,
  canSubmitDraft,
  defaultDraftForm,
  type DraftForm,
  formFromDraftParams,
  neutralOffsetError,
  parseAngleDeg,
  pickedFacesFromDraftParams,
} from "./draft";
import { faceSubshapeRef } from "./face";

const SIDE_A: PlanarFaceSignature = {
  normal: { x: 1, y: 0, z: 0 },
  centroid: { x: 20, y: 10, z: 10 },
  area_mm2: 400,
  subshape_type: "face",
  surface: "plane",
};
const SIDE_B: PlanarFaceSignature = {
  normal: { x: 0, y: 1, z: 0 },
  centroid: { x: 10, y: 20, z: 10 },
  area_mm2: 400,
  subshape_type: "face",
  surface: "plane",
};

/** A well-formed form with a 5° taper about XY at offset 0. */
const form: DraftForm = {
  angleInput: "5",
  neutral: { base: "XY", offsetInput: "0", flip: false },
};

describe("parseAngleDeg", () => {
  it("parses a signed value inside the open (-90, 90) interval", () => {
    expect(parseAngleDeg("5")).toBe(5);
    expect(parseAngleDeg(" -12.5 ")).toBe(-12.5);
    expect(parseAngleDeg("0")).toBe(0);
  });

  it("rejects empty, non-numeric, and out-of-range angles", () => {
    expect(parseAngleDeg("")).toBeNull();
    expect(parseAngleDeg("abc")).toBeNull();
    expect(parseAngleDeg("90")).toBeNull();
    expect(parseAngleDeg("-90")).toBeNull();
    expect(parseAngleDeg("120")).toBeNull();
  });
});

describe("angleError", () => {
  it("is null while empty (pending) and for a valid non-zero angle", () => {
    expect(angleError("")).toBeNull();
    expect(angleError("5")).toBeNull();
    expect(angleError("-8")).toBeNull();
  });

  it("messages an out-of-range angle", () => {
    expect(angleError("90")).toBe("Angle must be between −90 and 90 degrees.");
  });

  it("messages a zero angle as a no-op", () => {
    expect(angleError("0")).toBe("A draft needs a non-zero angle to taper by.");
  });
});

describe("neutralOffsetError", () => {
  it("is null while empty and for any finite value", () => {
    expect(neutralOffsetError("")).toBeNull();
    expect(neutralOffsetError("0")).toBeNull();
    expect(neutralOffsetError("-4")).toBeNull();
  });

  it("messages a non-numeric offset", () => {
    expect(neutralOffsetError("abc")).toBe(
      "Enter a distance in millimetres (0, negative, or positive).",
    );
  });
});

describe("buildNeutralPlane", () => {
  it("builds a datum-kind neutral plane from base + offset + flip", () => {
    expect(
      buildNeutralPlane({ base: "XZ", offsetInput: "-4", flip: true }),
    ).toEqual({ kind: "datum", base: "XZ", offset_mm: -4, flip: true });
  });

  it("is null for a missing/invalid offset", () => {
    expect(
      buildNeutralPlane({ base: "XY", offsetInput: "", flip: false }),
    ).toBeNull();
  });
});

describe("buildDraftParams", () => {
  it("builds params from angle + picked faces + neutral plane", () => {
    const params = buildDraftParams(form, [SIDE_A, SIDE_B], "feat-1");
    expect(params).toEqual({
      angle_deg: 5,
      faces: {
        kind: "faces",
        refs: [
          faceSubshapeRef("feat-1", SIDE_A),
          faceSubshapeRef("feat-1", SIDE_B),
        ],
      },
      neutral_plane: { kind: "datum", base: "XY", offset_mm: 0, flip: false },
    });
  });

  it("is null with NO picked faces (a draft has nothing to taper)", () => {
    expect(buildDraftParams(form, [], "feat-1")).toBeNull();
  });

  it("is null for a zero, out-of-range, or missing angle", () => {
    expect(
      buildDraftParams({ ...form, angleInput: "0" }, [SIDE_A], "feat-1"),
    ).toBeNull();
    expect(
      buildDraftParams({ ...form, angleInput: "90" }, [SIDE_A], "feat-1"),
    ).toBeNull();
    expect(
      buildDraftParams({ ...form, angleInput: "" }, [SIDE_A], "feat-1"),
    ).toBeNull();
  });

  it("is null when faces are picked without a body anchor", () => {
    expect(buildDraftParams(form, [SIDE_A], null)).toBeNull();
  });

  it("is null for an invalid neutral offset", () => {
    const bad: DraftForm = {
      ...form,
      neutral: { ...form.neutral, offsetInput: "abc" },
    };
    expect(buildDraftParams(bad, [SIDE_A], "feat-1")).toBeNull();
  });
});

describe("canSubmitDraft", () => {
  it("allows a valid angle with at least one picked face", () => {
    expect(canSubmitDraft(form, [SIDE_A], "feat-1")).toBe(true);
  });

  it("blocks with no picked faces", () => {
    expect(canSubmitDraft(form, [], "feat-1")).toBe(false);
  });
});

describe("defaultDraftForm", () => {
  it("seeds a 3° taper about XY at offset 0", () => {
    expect(defaultDraftForm()).toEqual({
      angleInput: "3",
      neutral: { base: "XY", offsetInput: "0", flip: false },
    });
  });
});

describe("formFromDraftParams / pickedFacesFromDraftParams", () => {
  const params: DraftParams = {
    angle_deg: -7.5,
    faces: { kind: "faces", refs: [faceSubshapeRef("feat-1", SIDE_A)] },
    neutral_plane: { kind: "datum", base: "YZ", offset_mm: 12, flip: true },
  };

  it("seeds the form from persisted params (angle + neutral)", () => {
    expect(formFromDraftParams(params)).toEqual({
      angleInput: "-7.5",
      neutral: { base: "YZ", offsetInput: "12", flip: true },
    });
  });

  it("seeds the picked-to-taper signatures", () => {
    expect(pickedFacesFromDraftParams(params)).toEqual([SIDE_A]);
  });

  it("treats a missing refs list as no picks", () => {
    const noRefs = {
      ...params,
      faces: { kind: "faces" },
    } as unknown as DraftParams;
    expect(pickedFacesFromDraftParams(noRefs)).toEqual([]);
  });
});
