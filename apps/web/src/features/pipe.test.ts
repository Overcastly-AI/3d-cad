import { describe, expect, it } from "vitest";

import type { FeatureResponse } from "../api/parts";
import { buildAlongPathParams, defaultAlongPathForm } from "./datumPath";
import {
  buildPipeParams,
  chainOf,
  curveKey,
  defaultPipeForm,
  formFromPipeParams,
  pipeCurveOptions,
  pipeSubmitBlocker,
  toggleCurve,
} from "./pipe";
import { alongPathBasis } from "../sketch/pathBasis";
import { originBasis } from "../sketch/plane";

type Entity = Extract<
  FeatureResponse["feature"],
  { type: "sketch" }
>["params"]["entities"][number];

const line = (
  id: string,
  a: [number, number],
  b: [number, number],
): Entity => ({
  id,
  kind: "line",
  construction: false,
  start: { x: a[0], y: a[1] },
  end: { x: b[0], y: b[1] },
});

function sketch(id: string, name: string, entities: Entity[]): FeatureResponse {
  return {
    id,
    name,
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "datum_plane", plane: "XZ" },
        entities,
        constraints: [],
      },
    },
  } as unknown as FeatureResponse;
}

// A bike skeleton: four tube lines and a construction horizontal at the BB,
// plus an L-bend with a tangent arc in it.
const SKELETON = sketch("s1", "Skeleton", [
  { ...line("h", [0, 0], [600, 0]), construction: true },
  line("seat", [0, 0], [-142, 479]),
  line("top", [-142, 479], [390, 570]),
  line("head", [390, 570], [434, 427]),
  line("down", [0, 0], [434, 427]),
]);
const BEND = sketch("s2", "Bend", [
  line("a", [0, 0], [50, 0]),
  {
    id: "r",
    kind: "arc",
    construction: false,
    center: { x: 50, y: 30 },
    start: { x: 50, y: 0 },
    end: { x: 80, y: 30 },
  },
  line("b", [80, 30], [80, 70]),
  line("c", [80, 70], [60, 70]),
]);
const CURVES = pipeCurveOptions([SKELETON, BEND]);

describe("pipe path picking", () => {
  it("lists every curve with its length", () => {
    expect(CURVES.map((c) => c.key)).toContain(curveKey("s1", "top"));
    const top = CURVES.find((c) => c.entityId === "top");
    expect(top?.lengthMm).toBeCloseTo(Math.hypot(532, 91), 9);
    const arc = CURVES.find((c) => c.entityId === "r");
    expect(arc?.lengthMm).toBeCloseTo((Math.PI * 30) / 2, 9);
  });

  it("chains through tangent joints and stops at corners and branches", () => {
    // Every skeleton joint is a corner (or the BB branch): one line, one tube.
    expect(chainOf(CURVES, curveKey("s1", "top"))).toEqual([
      curveKey("s1", "top"),
    ]);
    // The tangent arc joins a and b; the square corner stops at c.
    expect(new Set(chainOf(CURVES, curveKey("s2", "a")))).toEqual(
      new Set([curveKey("s2", "a"), curveKey("s2", "r"), curveKey("s2", "b")]),
    );
  });

  it("toggles one curve, or its chain, and unpicks alone", () => {
    let form = defaultPipeForm();
    form = toggleCurve(form, CURVES, curveKey("s2", "r"));
    expect(form.curves).toHaveLength(3);
    form = toggleCurve(form, CURVES, curveKey("s2", "b"));
    expect(form.curves).toHaveLength(2);
    const single = toggleCurve(
      { ...defaultPipeForm(), chain: false },
      CURVES,
      curveKey("s2", "r"),
    );
    expect(single.curves).toEqual([curveKey("s2", "r")]);
  });
});

describe("pipe params", () => {
  it("builds join / new body / cut with an optional wall", () => {
    const form = {
      ...defaultPipeForm(),
      curves: [curveKey("s1", "down")],
      odInput: "44",
      wallInput: "1.2",
    };
    expect(buildPipeParams(form, "mm")).toEqual({
      path: [
        {
          kind: "sketch_curve",
          sketch: { kind: "feature", feature_id: "s1" },
          entity: "down",
        },
      ],
      outer_diameter_mm: 44,
      wall_thickness_mm: 1.2,
      operation: "add",
      merge: true,
    });
    const bar = buildPipeParams(
      { ...form, hollow: false, operation: "newBody" },
      "mm",
    );
    expect(bar?.wall_thickness_mm).toBeUndefined();
    expect(bar?.merge).toBe(false);
    expect(
      buildPipeParams({ ...form, operation: "cut" }, "mm")?.operation,
    ).toBe("cut");
  });

  it("says why it is blocked", () => {
    expect(pipeSubmitBlocker(defaultPipeForm(), "mm")).toBe(
      "Pick the path curves.",
    );
    const picked = { ...defaultPipeForm(), curves: [curveKey("s1", "top")] };
    expect(pipeSubmitBlocker({ ...picked, wallInput: "20" }, "mm")).toBe(
      "Make the wall thinner.",
    );
    expect(pipeSubmitBlocker(picked, "mm")).toBeNull();
  });

  it("round-trips a stored pipe", () => {
    const params = buildPipeParams(
      { ...defaultPipeForm(), curves: [curveKey("s1", "head")] },
      "mm",
    );
    expect(params).not.toBeNull();
    const form = formFromPipeParams(params!, "mm");
    expect(buildPipeParams(form, "mm")).toEqual(params);
  });
});

describe("plane along path", () => {
  it("places the plane where the kernel does (line on XZ)", () => {
    const params = buildAlongPathParams(
      {
        ...defaultAlongPathForm(),
        curve: curveKey("s9", "e1"),
        positionInput: "0.25",
      },
      "mm",
    );
    expect(params).not.toBeNull();
    const basis = alongPathBasis(
      params!,
      line("e1", [10, 0], [70, 80]),
      originBasis("XZ"),
    );
    // test_pipe.py::test_plane_along_a_line_by_ratio_distance_and_flip
    expect(basis?.origin).toEqual([25, 0, 20].map((v) => expect.closeTo(v, 9)));
    expect(basis?.normal.map((v) => +v.toFixed(12))).toEqual([0.6, 0, 0.8]);
    expect(basis?.u.map((v) => +v.toFixed(12) + 0)).toEqual([0, -1, 0]);
  });
});
