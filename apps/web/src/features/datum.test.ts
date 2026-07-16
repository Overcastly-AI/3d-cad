import { describe, expect, it } from "vitest";

import {
  buildDatumParams,
  buildOffsetParams,
  canSubmitDatum,
  canSubmitOffset,
  decodeMidplaneSide,
  defaultDatumForm,
  defaultFormForKind,
  defaultOffsetForm,
  encodeMidplaneSide,
  formFromDatumParams,
  midplaneSideOptions,
  offsetError,
  parseOffsetMm,
} from "./datum";

describe("parseOffsetMm", () => {
  it("accepts any finite value (0, negative, positive)", () => {
    expect(parseOffsetMm("30")).toBe(30);
    expect(parseOffsetMm("0")).toBe(0);
    expect(parseOffsetMm("-12.5")).toBe(-12.5);
    expect(parseOffsetMm("  8 ")).toBe(8);
  });

  it("rejects empty and non-numeric input", () => {
    expect(parseOffsetMm("")).toBeNull();
    expect(parseOffsetMm("  ")).toBeNull();
    expect(parseOffsetMm("abc")).toBeNull();
    expect(parseOffsetMm("Infinity")).toBeNull();
  });
});

describe("offsetError", () => {
  it("is null while empty (pending) or valid", () => {
    expect(offsetError("")).toBeNull();
    expect(offsetError("30")).toBeNull();
    expect(offsetError("-5")).toBeNull();
  });

  it("flags a non-numeric offset", () => {
    expect(offsetError("abc")).toMatch(/millimetres/i);
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
      buildOffsetParams({ base: "XY", offsetInput: "30", flip: false }),
    ).toEqual({ kind: "offset", base: "XY", offset_mm: 30, flip: false });
    expect(
      buildOffsetParams({ base: "XZ", offsetInput: "-10", flip: true }),
    ).toEqual({ kind: "offset", base: "XZ", offset_mm: -10, flip: true });
    expect(
      buildOffsetParams({ base: "XY", offsetInput: "", flip: false }),
    ).toBeNull();
    expect(canSubmitOffset({ base: "XY", offsetInput: "x", flip: false })).toBe(
      false,
    );
    expect(
      canSubmitOffset({ base: "XY", offsetInput: "30", flip: false }),
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
      buildDatumParams({
        kind: "offset",
        base: "XZ",
        offsetInput: "-10",
        flip: true,
      }),
    ).toEqual({ kind: "offset", base: "XZ", offset_mm: -10, flip: true });
  });

  it("builds an offset_from datum from a chosen base datum", () => {
    expect(
      buildDatumParams({
        kind: "offset_from",
        baseFeatureId: "d1",
        offsetInput: "12",
        flip: false,
      }),
    ).toEqual({
      kind: "offset_from",
      base: { kind: "feature", feature_id: "d1" },
      offset_mm: 12,
      flip: false,
    });
  });

  it("blocks offset_from until a base + finite offset are present", () => {
    expect(
      canSubmitDatum({
        kind: "offset_from",
        baseFeatureId: "",
        offsetInput: "12",
        flip: false,
      }),
    ).toBe(false);
    expect(
      canSubmitDatum({
        kind: "offset_from",
        baseFeatureId: "d1",
        offsetInput: "",
        flip: false,
      }),
    ).toBe(false);
  });

  it("builds a midplane over an origin datum and an earlier datum", () => {
    expect(
      buildDatumParams({
        kind: "midplane",
        a: "origin:XY",
        b: "feature:d1",
        flip: false,
      }),
    ).toEqual({
      kind: "midplane",
      a: { kind: "datum_plane", plane: "XY" },
      b: { kind: "feature", feature_id: "d1" },
      flip: false,
    });
  });

  it("blocks a midplane until both sides are chosen", () => {
    expect(
      canSubmitDatum({ kind: "midplane", a: "origin:XY", b: "", flip: false }),
    ).toBe(false);
    expect(
      canSubmitDatum({ kind: "midplane", a: "", b: "feature:d1", flip: false }),
    ).toBe(false);
    expect(
      canSubmitDatum({
        kind: "midplane",
        a: "origin:XY",
        b: "origin:XZ",
        flip: true,
      }),
    ).toBe(true);
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
      a: "",
      b: "",
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
    expect(buildDatumParams(formFromDatumParams(params))).toEqual(params);
  });

  it("offset_from", () => {
    const params = {
      kind: "offset_from",
      base: { kind: "feature", feature_id: "d1" },
      offset_mm: -8,
      flip: false,
    } as const;
    expect(buildDatumParams(formFromDatumParams(params))).toEqual(params);
  });

  it("midplane", () => {
    const params = {
      kind: "midplane",
      a: { kind: "datum_plane", plane: "XY" },
      b: { kind: "feature", feature_id: "d2" },
      flip: true,
    } as const;
    expect(buildDatumParams(formFromDatumParams(params))).toEqual(params);
  });
});
