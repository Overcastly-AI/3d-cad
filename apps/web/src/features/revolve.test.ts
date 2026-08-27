import { describe, expect, it } from "vitest";

import type {
  DatumPlaneName,
  FeatureResponse,
  RevolveParams,
} from "../api/parts";
import {
  angleError,
  axisOptions,
  axisReason,
  axisRef,
  canSubmitRevolve,
  defaultAxisId,
  defaultRevolveForm,
  formFromRevolveParams,
  originAxisId,
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

/**
 * A plain closed rectangle, no construction geometry — the REACH-1 case: before
 * the origin axes were offered, this sketch's only axes were its own four edges.
 * `plane` is a datum-plane name or a `FeatureRef` to a datum feature id.
 */
function rectangleSketch(
  id: string,
  plane: DatumPlaneName | { datum: string },
): FeatureResponse {
  const corners = [
    { x: 20, y: 0 },
    { x: 40, y: 0 },
    { x: 40, y: 10 },
    { x: 20, y: 10 },
  ] as const;
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
        plane:
          typeof plane === "string"
            ? { kind: "datum_plane", plane }
            : { kind: "feature", feature_id: plane.datum },
        entities: corners.map((start, i) => ({
          id: `e${i + 1}`,
          kind: "line" as const,
          start,
          end: corners[(i + 1) % corners.length] ?? start,
          construction: false,
        })),
        constraints: [],
      },
    },
  };
}

/** An offset datum feature — a plane slid off an origin datum along its normal. */
function offsetDatum(id: string, base: DatumPlaneName): FeatureResponse {
  return {
    id,
    name: "Datum1",
    part_id: "p",
    order_index: 0,
    created_at: "2026-07-11T00:00:00Z",
    updated_at: "2026-07-11T00:00:00Z",
    rolled_back: false,
    feature: {
      type: "datum",
      version: 1,
      params: { kind: "offset", base, offset_mm: 30, flip: false },
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
      axisId: "axis",
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
      axisId: "axis",
      angleInput: "180",
      operation: "cut",
      direction: "reverse",
      merge: true,
    });
  });

  it("round-trips an ORIGIN axis instead of seeding blank (REACH-1)", () => {
    const turned: RevolveParams = {
      ...revolveParams,
      axis: { kind: "origin_axis", axis: "Z" },
    };
    expect(formFromRevolveParams(turned).axisId).toBe("origin:Z");
  });
});

describe("canSubmitRevolve", () => {
  it("needs a profile, a choosable axis, and a valid angle", () => {
    const options = axisOptions([annulusSketch("sk")], "sk");
    expect(canSubmitRevolve(defaultRevolveForm("sk", "axis"), options)).toBe(
      true,
    );
    expect(canSubmitRevolve(defaultRevolveForm("", "axis"), options)).toBe(
      false,
    );
    expect(canSubmitRevolve(defaultRevolveForm("sk", ""), options)).toBe(false);
    expect(
      canSubmitRevolve(
        { ...defaultRevolveForm("sk", "axis"), angleInput: "0" },
        options,
      ),
    ).toBe(false);
  });

  it("refuses an axis the kernel would refuse, before the round-trip", () => {
    // The XY sketch's normal is Z: offered, disabled, and not submittable.
    const options = axisOptions([annulusSketch("sk")], "sk");
    expect(axisReason(options, "origin:Z")).toContain(
      "Not in the sketch plane",
    );
    expect(
      canSubmitRevolve(defaultRevolveForm("sk", "origin:Z"), options),
    ).toBe(false);
    expect(
      canSubmitRevolve(defaultRevolveForm("sk", "origin:Y"), options),
    ).toBe(true);
  });

  it("refuses an axis that is not on the list at all", () => {
    const options = axisOptions([annulusSketch("sk")], "sk");
    expect(canSubmitRevolve(defaultRevolveForm("sk", "gone"), options)).toBe(
      false,
    );
  });
});

describe("axisRef", () => {
  it("returns the wire axis each option means, and null off-list", () => {
    const options = axisOptions([annulusSketch("sk")], "sk");
    expect(axisRef(options, "axis")).toEqual({
      kind: "sketch_line",
      entity: "axis",
    });
    expect(axisRef(options, "origin:Y")).toEqual({
      kind: "origin_axis",
      axis: "Y",
    });
    expect(axisRef(options, "nope")).toBeNull();
  });
});

describe("axisOptions", () => {
  it("offers line entities and the world origin axes, centerline first", () => {
    const options = axisOptions([annulusSketch("sk")], "sk");
    // Ranked: centerline, in-plane origin axes (spindle order), profile edges,
    // then the origin axis normal to the sketch plane, disabled.
    expect(options.map((o) => o.id)).toEqual([
      "axis",
      "origin:Y",
      "origin:X",
      "e1",
      "e2",
      "origin:Z",
    ]);
    expect(options[0]?.construction).toBe(true);
    expect(options[0]?.label).toContain("construction");
    expect(options[0]?.label).toContain("(axis)");
    // The circle is excluded — a revolve axis must be a line.
    expect(options.some((o) => o.id === "c1")).toBe(false);
  });

  it("offers the three origin axes to a sketch with NO construction line", () => {
    // The REACH-1 gap: this list used to be four profile edges and nothing else.
    const options = axisOptions([rectangleSketch("sk", "XZ")], "sk");
    expect(options.map((o) => o.id).slice(0, 2)).toEqual([
      "origin:Z",
      "origin:X",
    ]);
    expect(options.find((o) => o.id === "origin:Z")?.label).toBe(
      "Z axis · through the origin",
    );
    expect(defaultAxisId(options)).toBe("origin:Z");
  });

  it("disables the origin axis NORMAL to the sketch plane, with the reason", () => {
    for (const [plane, normal] of [
      ["XY", "Z"],
      ["XZ", "Y"],
      ["YZ", "X"],
    ] as const) {
      const options = axisOptions([rectangleSketch("sk", plane)], "sk");
      const refused = options.filter((o) => o.reason !== null);
      expect(refused.map((o) => o.id)).toEqual([originAxisId(normal)]);
      expect(refused[0]?.reason).toBe(
        "Not in the sketch plane — it is the plane normal.",
      );
      expect(refused[0]?.label).toBe(
        `${normal} axis · not in the sketch plane — it is the plane normal`,
      );
      // A refused axis is listed LAST — never proposed.
      expect(options[options.length - 1]?.id).toBe(originAxisId(normal));
    }
  });

  it("disables EVERY origin axis for a sketch on an offset datum", () => {
    const options = axisOptions(
      [offsetDatum("d1", "XZ"), rectangleSketch("sk", { datum: "d1" })],
      "sk",
    );
    const origins = options.filter((o) => o.kind === "origin_axis");
    expect(origins).toHaveLength(3);
    for (const origin of origins) {
      expect(origin.reason).toBe(
        "Not in the sketch plane — the plane is offset from the origin.",
      );
    }
    // …so the proposal falls back to a profile edge, as it did before REACH-1.
    expect(defaultAxisId(options)).toBe("e1");
  });

  it("omits the origin group when the plane cannot be placed client-side", () => {
    // A datum the tree does not carry (rolled back, or an on_face basis that
    // only the sketch-on-face flow can resolve): no in-plane claim is possible.
    const options = axisOptions(
      [rectangleSketch("sk", { datum: "gone" })],
      "sk",
    );
    expect(options.every((o) => o.kind === "sketch_line")).toBe(true);
  });

  it("lets a real entity keep an id that shadows an origin axis", () => {
    const sketch = rectangleSketch("sk", "XZ");
    const entities =
      sketch.feature.type === "sketch" ? sketch.feature.params.entities : [];
    const shadowed = entities[0];
    if (shadowed !== undefined) shadowed.id = "origin:Z";
    const options = axisOptions([sketch], "sk");
    expect(options.filter((o) => o.id === "origin:Z")).toHaveLength(1);
    expect(axisRef(options, "origin:Z")).toEqual({
      kind: "sketch_line",
      entity: "origin:Z",
    });
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
  it("proposes the first CHOOSABLE option, so it tracks the ranking", () => {
    expect(defaultAxisId(axisOptions([annulusSketch("sk")], "sk"))).toBe(
      "axis",
    );
    expect(
      defaultAxisId(axisOptions([rectangleSketch("sk", "XZ")], "sk")),
    ).toBe("origin:Z");
    expect(defaultAxisId([])).toBe("");
  });

  it("never proposes an axis the kernel would refuse", () => {
    // Every option refused (the offset-datum origins, with the edges removed):
    // an empty proposal is the honest answer, not the first refused entry.
    const refusedOnly = axisOptions(
      [offsetDatum("d1", "XZ"), rectangleSketch("sk", { datum: "d1" })],
      "sk",
    ).filter((o) => o.kind === "origin_axis");
    expect(refusedOnly).not.toHaveLength(0);
    expect(defaultAxisId(refusedOnly)).toBe("");
  });
});
