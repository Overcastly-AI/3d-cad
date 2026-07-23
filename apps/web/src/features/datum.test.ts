import { describe, expect, it } from "vitest";

import type { PlanarFaceSignature } from "../api/parts";
import {
  applyFacePick,
  buildDatumParams,
  buildOffsetParams,
  canSubmitDatum,
  canSubmitOffset,
  decodeMidplaneSide,
  defaultDatumForm,
  defaultFormForKind,
  defaultOffsetForm,
  EMPTY_MIDPLANE_SIDE,
  encodeMidplaneSide,
  faceMidplaneSide,
  formFromDatumParams,
  midplaneSideOptions,
  offsetError,
  parseOffsetMm,
  refMidplaneSide,
} from "./datum";

/** A minimal planar-face signature fixture (the fields the datum wire needs). */
function faceSignatureFixture(): PlanarFaceSignature {
  return {
    subshape_type: "face",
    surface: "plane",
    normal: { x: 0, y: 0, z: 1 },
    centroid: { x: 10, y: 20, z: 30 },
    area_mm2: 100,
  };
}

describe("parseOffsetMm", () => {
  it("accepts any finite value (0, negative, positive)", () => {
    expect(parseOffsetMm("30", "mm")).toBe(30);
    expect(parseOffsetMm("0", "mm")).toBe(0);
    expect(parseOffsetMm("-12.5", "mm")).toBe(-12.5);
    expect(parseOffsetMm("  8 ", "mm")).toBe(8);
  });

  it("converts a signed offset through the document unit", () => {
    expect(parseOffsetMm("-2", "in")).toBe(-50.8);
    expect(parseOffsetMm("1in", "mm")).toBe(25.4);
  });

  it("rejects empty and non-numeric input", () => {
    expect(parseOffsetMm("", "mm")).toBeNull();
    expect(parseOffsetMm("  ", "mm")).toBeNull();
    expect(parseOffsetMm("abc", "mm")).toBeNull();
    expect(parseOffsetMm("Infinity", "mm")).toBeNull();
  });
});

describe("offsetError", () => {
  it("is null while empty (pending) or valid", () => {
    expect(offsetError("", "mm")).toBeNull();
    expect(offsetError("30", "mm")).toBeNull();
    expect(offsetError("-5", "mm")).toBeNull();
  });

  it("flags a non-numeric offset", () => {
    expect(offsetError("abc", "mm")).toMatch(/distance/i);
  });
});

describe("offset form (the inline picker + editor's offset kind)", () => {
  it("defaults to 30 mm above XY", () => {
    expect(defaultOffsetForm()).toEqual({
      base: "XY",
      offsetInput: "30",
      flip: false,
    });
  });

  it("builds offset params, gated on a finite offset", () => {
    expect(
      buildOffsetParams({ base: "XY", offsetInput: "30", flip: false }, "mm"),
    ).toEqual({ kind: "offset", base: "XY", offset_mm: 30, flip: false });
    expect(
      buildOffsetParams({ base: "XZ", offsetInput: "-10", flip: true }, "mm"),
    ).toEqual({ kind: "offset", base: "XZ", offset_mm: -10, flip: true });
    expect(
      buildOffsetParams({ base: "XY", offsetInput: "", flip: false }, "mm"),
    ).toBeNull();
    expect(
      canSubmitOffset({ base: "XY", offsetInput: "x", flip: false }, "mm"),
    ).toBe(false);
    expect(
      canSubmitOffset({ base: "XY", offsetInput: "30", flip: false }, "mm"),
    ).toBe(true);
  });
});

describe("buildDatumParams — the editor's union form", () => {
  it("defaults to a 30 mm offset above XY", () => {
    expect(defaultDatumForm()).toEqual({
      kind: "offset",
      base: "XY",
      offsetInput: "30",
      flip: false,
    });
  });

  it("builds an offset datum", () => {
    expect(
      buildDatumParams(
        {
          kind: "offset",
          base: "XZ",
          offsetInput: "-10",
          flip: true,
        },
        "mm",
      ),
    ).toEqual({ kind: "offset", base: "XZ", offset_mm: -10, flip: true });
  });

  it("builds an offset_from datum from a chosen base datum", () => {
    expect(
      buildDatumParams(
        {
          kind: "offset_from",
          baseFeatureId: "d1",
          offsetInput: "12",
          flip: false,
        },
        "mm",
      ),
    ).toEqual({
      kind: "offset_from",
      base: { kind: "feature", feature_id: "d1" },
      offset_mm: 12,
      flip: false,
    });
  });

  it("blocks offset_from until a base + finite offset are present", () => {
    expect(
      canSubmitDatum(
        {
          kind: "offset_from",
          baseFeatureId: "",
          offsetInput: "12",
          flip: false,
        },
        "mm",
      ),
    ).toBe(false);
    expect(
      canSubmitDatum(
        {
          kind: "offset_from",
          baseFeatureId: "d1",
          offsetInput: "",
          flip: false,
        },
        "mm",
      ),
    ).toBe(false);
  });

  it("builds a midplane over an origin datum and an earlier datum", () => {
    expect(
      buildDatumParams(
        {
          kind: "midplane",
          a: refMidplaneSide("origin:XY"),
          b: refMidplaneSide("feature:d1"),
          flip: false,
        },
        "mm",
      ),
    ).toEqual({
      kind: "midplane",
      a: { kind: "datum_plane", plane: "XY" },
      b: { kind: "feature", feature_id: "d1" },
      flip: false,
    });
  });

  it("builds a midplane with a picked FACE side (a SubshapeRef)", () => {
    const sig = faceSignatureFixture();
    expect(
      buildDatumParams(
        {
          kind: "midplane",
          a: refMidplaneSide("origin:XY"),
          b: faceMidplaneSide({ signature: sig, anchorId: "b1" }),
          flip: false,
        },
        "mm",
      ),
    ).toEqual({
      kind: "midplane",
      a: { kind: "datum_plane", plane: "XY" },
      b: {
        kind: "subshape",
        feature_id: "b1",
        subshape_type: "face",
        selector: { selector_version: 1, signature: sig },
      },
      flip: false,
    });
  });

  it("blocks a midplane until both sides are chosen", () => {
    expect(
      canSubmitDatum(
        {
          kind: "midplane",
          a: refMidplaneSide("origin:XY"),
          b: refMidplaneSide(""),
          flip: false,
        },
        "mm",
      ),
    ).toBe(false);
    expect(
      canSubmitDatum(
        {
          kind: "midplane",
          a: refMidplaneSide(""),
          b: refMidplaneSide("feature:d1"),
          flip: false,
        },
        "mm",
      ),
    ).toBe(false);
    expect(
      canSubmitDatum(
        {
          kind: "midplane",
          a: refMidplaneSide("origin:XY"),
          b: refMidplaneSide("origin:XZ"),
          flip: true,
        },
        "mm",
      ),
    ).toBe(true);
  });

  it("builds an on_face datum from a picked face + offset", () => {
    const sig = faceSignatureFixture();
    expect(
      buildDatumParams(
        {
          kind: "on_face",
          face: { signature: sig, anchorId: "b1" },
          offsetInput: "5",
        },
        "mm",
      ),
    ).toEqual({
      kind: "on_face",
      face: {
        kind: "subshape",
        feature_id: "b1",
        subshape_type: "face",
        selector: { selector_version: 1, signature: sig },
      },
      offset_mm: 5,
    });
  });

  it("blocks an on_face datum until a face is picked", () => {
    expect(
      canSubmitDatum({ kind: "on_face", face: null, offsetInput: "0" }, "mm"),
    ).toBe(false);
    expect(
      canSubmitDatum(
        {
          kind: "on_face",
          face: { signature: faceSignatureFixture(), anchorId: "b1" },
          offsetInput: "0",
        },
        "mm",
      ),
    ).toBe(true);
  });
});

describe("applyFacePick folds a picked face into its slot", () => {
  const face = { signature: faceSignatureFixture(), anchorId: "b1" };

  it("sets the on_face base", () => {
    const next = applyFacePick(
      { kind: "on_face", face: null, offsetInput: "0" },
      "on_face",
      face,
    );
    expect(next).toEqual({ kind: "on_face", face, offsetInput: "0" });
  });

  it("sets midplane side a / b", () => {
    const seed = {
      kind: "midplane" as const,
      a: refMidplaneSide(""),
      b: refMidplaneSide(""),
      flip: false,
    };
    expect(applyFacePick(seed, "midplane-a", face)).toMatchObject({
      a: { source: "face", face },
      b: { source: "ref", value: "" },
    });
    expect(applyFacePick(seed, "midplane-b", face)).toMatchObject({
      a: { source: "ref", value: "" },
      b: { source: "face", face },
    });
  });

  it("ignores a pick that doesn't match the current kind", () => {
    const offset = {
      kind: "offset" as const,
      base: "XY" as const,
      offsetInput: "30",
      flip: false,
    };
    expect(applyFacePick(offset, "on_face", face)).toBe(offset);
  });
});

describe("midplane side encoding", () => {
  it("round-trips origin + feature sides", () => {
    expect(decodeMidplaneSide("origin:YZ")).toEqual({
      kind: "datum_plane",
      plane: "YZ",
    });
    expect(decodeMidplaneSide("feature:abc")).toEqual({
      kind: "feature",
      feature_id: "abc",
    });
    expect(decodeMidplaneSide("")).toBeNull();
    expect(decodeMidplaneSide("origin:ZZ")).toBeNull();
    expect(encodeMidplaneSide({ kind: "datum_plane", plane: "XZ" })).toBe(
      "origin:XZ",
    );
    expect(encodeMidplaneSide({ kind: "feature", feature_id: "d9" })).toBe(
      "feature:d9",
    );
  });

  it("lists origin datums then earlier datum features", () => {
    const options = midplaneSideOptions([{ id: "d1", name: "Plane1" }]);
    expect(options.map((o) => o.value)).toEqual([
      "",
      "origin:XY",
      "origin:XZ",
      "origin:YZ",
      "feature:d1",
    ]);
  });
});

describe("defaultFormForKind carries flip across the switch", () => {
  it("keeps flip when switching kinds", () => {
    expect(defaultFormForKind("midplane", true)).toEqual({
      kind: "midplane",
      a: EMPTY_MIDPLANE_SIDE,
      b: EMPTY_MIDPLANE_SIDE,
      flip: true,
    });
    expect(defaultFormForKind("offset_from", false)).toEqual({
      kind: "offset_from",
      baseFeatureId: "",
      offsetInput: "30",
      flip: false,
    });
  });
});

describe("formFromDatumParams round-trips each kind", () => {
  it("offset", () => {
    const params = {
      kind: "offset",
      base: "YZ",
      offset_mm: 12.5,
      flip: true,
    } as const;
    expect(buildDatumParams(formFromDatumParams(params, "mm"), "mm")).toEqual(
      params,
    );
  });

  it("offset_from", () => {
    const params = {
      kind: "offset_from",
      base: { kind: "feature", feature_id: "d1" },
      offset_mm: -8,
      flip: false,
    } as const;
    expect(buildDatumParams(formFromDatumParams(params, "mm"), "mm")).toEqual(
      params,
    );
  });

  it("midplane", () => {
    const params = {
      kind: "midplane",
      a: { kind: "datum_plane", plane: "XY" },
      b: { kind: "feature", feature_id: "d2" },
      flip: true,
    } as const;
    expect(buildDatumParams(formFromDatumParams(params, "mm"), "mm")).toEqual(
      params,
    );
  });

  it("round-trips an offset through inches without drift", () => {
    const params = {
      kind: "offset",
      base: "XY",
      offset_mm: 50.8,
      flip: false,
    } as const;
    const form = formFromDatumParams(params, "in");
    if (form.kind !== "offset") throw new Error("expected an offset form");
    expect(form.offsetInput).toBe("2");
    expect(buildDatumParams(form, "in")).toEqual(params);
  });
});
