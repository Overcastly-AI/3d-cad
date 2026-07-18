import { describe, expect, it } from "vitest";

import type { FeatureResponse, RevolveParams } from "../api/parts";
import {
  angleError,
  axisOptions,
  canSubmitRevolve,
  defaultAxisId,
  defaultRevolveForm,
  formFromRevolveParams,
  parseAngleDeg,
} from "./revolve";

/** A sketch feature whose entities include a construction axis line. */
function annulusSketch(id: string): FeatureResponse {
  return {
    id,
    name: "Sketch1",
    part_id: "p",
    order_index: 0,
    created_at: "2026-07-11T00:00:00Z",
    updated_at: "2026-07-11T00:00:00Z",
    rolled_back: false,
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "datum_plane", plane: "XY" },
        entities: [
          {
            id: "e1",
            kind: "line",
            start: { x: 10, y: 0 },
            end: { x: 20, y: 0 },
            construction: false,
          },
          {
            id: "e2",
            kind: "line",
            start: { x: 20, y: 0 },
            end: { x: 20, y: 15 },
            construction: false,
          },
          // A construction centerline — the natural axis of revolution.
          {
            id: "axis",
            kind: "line",
            start: { x: 0, y: 0 },
            end: { x: 0, y: 15 },
            construction: true,
          },
          // A circle is not a candidate axis.
          {
            id: "c1",
            kind: "circle",
            center: { x: 15, y: 7 },
            radius: 2,
            construction: true,
          },
        ],
        constraints: [],
      },
    },
  };
}

const revolveParams: RevolveParams = {
  profile: { kind: "feature", feature_id: "sk" },
  axis: { kind: "sketch_line", entity: "axis" },
  angle_deg: 360,
  operation: "add",
  direction: "normal",
  merge: true,
};

describe("parseAngleDeg", () => {
  it("accepts (0, 360], rejects empty/non-numeric/out-of-range", () => {
    expect(parseAngleDeg("360")).toBe(360);
    expect(parseAngleDeg(" 90 ")).toBe(90);
    expect(parseAngleDeg("0.5")).toBe(0.5);
    expect(parseAngleDeg("")).toBeNull();
    expect(parseAngleDeg("abc")).toBeNull();
    expect(parseAngleDeg("0")).toBeNull();
    expect(parseAngleDeg("-90")).toBeNull();
    expect(parseAngleDeg("361")).toBeNull();
  });
});

describe("angleError", () => {
  it("is quiet while empty (pending) and flags invalid non-empty input", () => {
    expect(angleError("")).toBeNull();
    expect(angleError("360")).toBeNull();
    expect(angleError("0")).toContain("360");
    expect(angleError("400")).toContain("360");
  });
});

describe("defaultRevolveForm", () => {
  it("is 360° / add / normal against the given profile + axis", () => {
    expect(defaultRevolveForm("sk", "axis")).toEqual({
      profileFeatureId: "sk",
      axisEntityId: "axis",
      angleInput: "360",
      operation: "add",
      direction: "normal",
      merge: true,
    });
  });
});

describe("formFromRevolveParams", () => {
  it("round-trips an existing revolve's params into editable form state", () => {
    const half: RevolveParams = {
      ...revolveParams,
      angle_deg: 180,
      operation: "cut",
      direction: "reverse",
    };
    expect(formFromRevolveParams(half)).toEqual({
      profileFeatureId: "sk",
      axisEntityId: "axis",
      angleInput: "180",
      operation: "cut",
      direction: "reverse",
      merge: true,
    });
  });
});

describe("canSubmitRevolve", () => {
  it("needs a profile, an axis, and a valid angle", () => {
    expect(canSubmitRevolve(defaultRevolveForm("sk", "axis"))).toBe(true);
    expect(canSubmitRevolve(defaultRevolveForm("", "axis"))).toBe(false);
    expect(canSubmitRevolve(defaultRevolveForm("sk", ""))).toBe(false);
    expect(
      canSubmitRevolve({
        ...defaultRevolveForm("sk", "axis"),
        angleInput: "0",
      }),
    ).toBe(false);
  });
});

describe("axisOptions", () => {
  it("offers only line entities, construction (centerline) ranked first", () => {
    const options = axisOptions([annulusSketch("sk")], "sk");
    expect(options.map((o) => o.id)).toEqual(["axis", "e1", "e2"]);
    expect(options[0]?.construction).toBe(true);
    expect(options[0]?.label).toContain("construction");
    expect(options[0]?.label).toContain("(axis)");
    // The circle is excluded — a revolve axis must be a line.
    expect(options.some((o) => o.id === "c1")).toBe(false);
  });

  it("labels lines by orientation and length", () => {
    const options = axisOptions([annulusSketch("sk")], "sk");
    const e1 = options.find((o) => o.id === "e1");
    expect(e1?.label).toContain("Horizontal");
    expect(e1?.label).toContain("10 mm");
    const e2 = options.find((o) => o.id === "e2");
    expect(e2?.label).toContain("Vertical");
    expect(e2?.label).toContain("15 mm");
  });

  it("is empty for an unknown or non-sketch profile", () => {
    expect(axisOptions([annulusSketch("sk")], "missing")).toEqual([]);
    expect(axisOptions([], "sk")).toEqual([]);
  });
});

describe("defaultAxisId", () => {
  it("prefers the first construction line, else the first line, else ''", () => {
    const options = axisOptions([annulusSketch("sk")], "sk");
    expect(defaultAxisId(options)).toBe("axis");
    expect(
      defaultAxisId([
        {
          id: "e1",
          label: "Horizontal · 10 mm · profile edge (e1)",
          construction: false,
        },
      ]),
    ).toBe("e1");
    expect(defaultAxisId([])).toBe("");
  });
});
