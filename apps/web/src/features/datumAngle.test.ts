import { describe, expect, it } from "vitest";

import {
  buildDatumParams,
  datumSubmitBlocker,
  defaultDatumForm,
  defaultFormForKind,
  formFromDatumParams,
} from "./datum";
import {
  angleLineOptions,
  decodeAngleLine,
  encodeSketchLine,
  parseDatumAngleDeg,
} from "./datumAngle";

const edge = {
  signature: {
    subshape_type: "edge" as const,
    curve: "line" as const,
    end_a: { x: 40, y: 0, z: 10 },
    end_b: { x: 40, y: 20, z: 10 },
    midpoint: { x: 40, y: 10, z: 10 },
    length_mm: 20,
  },
  anchorId: "body-1",
};

describe("the plane-at-an-angle form", () => {
  it("encodes and decodes the line dropdown", () => {
    expect(decodeAngleLine("axis:Y")).toEqual({
      kind: "origin_axis",
      axis: "Y",
    });
    expect(decodeAngleLine(encodeSketchLine("s-1", "e3"))).toEqual({
      kind: "sketch_line",
      sketch: { kind: "feature", feature_id: "s-1" },
      entity: "e3",
    });
    expect(decodeAngleLine("")).toBeNull();
    expect(decodeAngleLine("sketch:s-1:")).toBeNull();
    expect(
      angleLineOptions([
        {
          sketchId: "s",
          sketchName: "Sketch1",
          entityId: "e1",
          construction: true,
        },
      ]).map((o) => o.label),
    ).toEqual([
      "Choose a line…",
      "X axis",
      "Y axis",
      "Z axis",
      "Sketch1 · construction line e1",
    ]);
  });

  it("accepts signed angles to 360 and nothing past it", () => {
    expect(parseDatumAngleDeg("-25")).toBe(-25);
    expect(parseDatumAngleDeg("360")).toBe(360);
    expect(parseDatumAngleDeg("360.5")).toBeNull();
    expect(parseDatumAngleDeg("abc")).toBeNull();
  });

  it("gates on the line, then the reference, then the angle", () => {
    const form = defaultFormForKind("angle", false);
    expect(datumSubmitBlocker(form, "mm")).toBe("Choose the line.");
    expect(form.kind === "angle" && form.reference).toEqual({
      source: "ref",
      value: "origin:XY",
    });
    const withLine =
      form.kind === "angle"
        ? { ...form, line: { source: "ref" as const, value: "axis:X" } }
        : form;
    expect(datumSubmitBlocker(withLine, "mm")).toBeNull();
    expect(buildDatumParams(withLine, "mm")).toEqual({
      kind: "angle",
      line: { kind: "origin_axis", axis: "X" },
      reference: { kind: "datum_plane", plane: "XY" },
      angle_deg: 30,
      flip: false,
    });
  });

  it("a selected straight edge opens a plane at an angle about it", () => {
    const form = defaultDatumForm(null, edge);
    expect(form.kind).toBe("angle");
    expect(datumSubmitBlocker(form, "mm")).toBe("Choose the reference plane.");
    const params = buildDatumParams(
      form.kind === "angle"
        ? { ...form, reference: { source: "ref", value: "origin:XY" } }
        : form,
      "mm",
    );
    expect(params).toMatchObject({
      kind: "angle",
      line: {
        kind: "subshape",
        feature_id: "body-1",
        subshape_type: "edge",
        selector: { selector_version: 1, signature: edge.signature },
      },
    });
  });

  it("a stored angle datum round-trips through the form unchanged", () => {
    const stored = {
      kind: "angle" as const,
      line: {
        kind: "sketch_line" as const,
        sketch: { kind: "feature" as const, feature_id: "s-1" },
        entity: "head",
      },
      reference: { kind: "feature" as const, feature_id: "d-1" },
      angle_deg: -25,
      flip: true,
    };
    expect(buildDatumParams(formFromDatumParams(stored, "mm"), "mm")).toEqual(
      stored,
    );
  });
});
