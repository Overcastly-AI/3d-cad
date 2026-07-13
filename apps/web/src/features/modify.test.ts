import { describe, expect, it } from "vitest";

import type { ChamferParams, EdgeSignature, FilletParams } from "../api/parts";
import {
  buildChamferParams,
  buildEdgeSelector,
  buildFilletParams,
  canSubmitChamfer,
  canSubmitFillet,
  defaultChamferForm,
  defaultFilletForm,
  distanceError,
  EDGE_SELECTORS,
  edgeSelector,
  edgeSelectorId,
  formFromChamferParams,
  formFromFilletParams,
  parseSizeMm,
  pickedFromChamferParams,
  pickedFromFilletParams,
  radiusError,
} from "./modify";

const SIG_A: EdgeSignature = {
  curve: "line",
  end_a: { x: 0, y: 0, z: 20 },
  end_b: { x: 20, y: 0, z: 20 },
  midpoint: { x: 10, y: 0, z: 20 },
  length_mm: 20,
  subshape_type: "edge",
};
const SIG_B: EdgeSignature = {
  curve: "line",
  end_a: { x: 0, y: 20, z: 20 },
  end_b: { x: 20, y: 20, z: 20 },
  midpoint: { x: 10, y: 20, z: 20 },
  length_mm: 20,
  subshape_type: "edge",
};

describe("edge selector", () => {
  it("offers all-edges plus one entry per world axis", () => {
    expect(EDGE_SELECTORS.map((o) => o.id)).toEqual([
      "all_edges",
      "axis_x",
      "axis_y",
      "axis_z",
    ]);
  });

  it("maps each id to its EdgeSelector predicate", () => {
    expect(edgeSelector("all_edges")).toEqual({ kind: "all_edges" });
    expect(edgeSelector("axis_x")).toEqual({
      kind: "axis_parallel",
      axis: "X",
    });
    expect(edgeSelector("axis_z")).toEqual({
      kind: "axis_parallel",
      axis: "Z",
    });
  });

  it("round-trips a selector back to its id", () => {
    expect(edgeSelectorId({ kind: "all_edges" })).toBe("all_edges");
    expect(edgeSelectorId({ kind: "axis_parallel", axis: "Y" })).toBe("axis_y");
  });
});

describe("buildEdgeSelector", () => {
  it("returns the predicate in rule mode (ignores picks + anchor)", () => {
    expect(buildEdgeSelector("rule", "axis_z", [SIG_A], "feat-1")).toEqual({
      kind: "axis_parallel",
      axis: "Z",
    });
  });

  it("returns a picked-edge selector in pick mode", () => {
    expect(buildEdgeSelector("pick", "all_edges", [SIG_A], "feat-1")).toEqual({
      kind: "edges",
      refs: [
        {
          kind: "subshape",
          feature_id: "feat-1",
          subshape_type: "edge",
          selector: { selector_version: 1, signature: SIG_A },
        },
      ],
    });
  });

  it("is null in pick mode with no anchor or no picks", () => {
    expect(buildEdgeSelector("pick", "all_edges", [SIG_A], null)).toBeNull();
    expect(buildEdgeSelector("pick", "all_edges", [], "feat-1")).toBeNull();
  });
});

describe("parseSizeMm", () => {
  it("accepts positive millimetres, rejects zero / negative / empty / NaN", () => {
    expect(parseSizeMm("5")).toBe(5);
    expect(parseSizeMm("2.5")).toBe(2.5);
    expect(parseSizeMm("0")).toBeNull();
    expect(parseSizeMm("-3")).toBeNull();
    expect(parseSizeMm("")).toBeNull();
    expect(parseSizeMm("abc")).toBeNull();
  });
});

describe("fillet form", () => {
  it("defaults to a 2 mm round of every edge, by rule", () => {
    const form = defaultFilletForm();
    expect(form.radiusInput).toBe("2");
    expect(form.mode).toBe("rule");
    expect(form.edges).toBe("all_edges");
  });

  it("builds a predicate FilletParamsV1 in rule mode, null for a bad radius", () => {
    expect(
      buildFilletParams(
        { radiusInput: "5", mode: "rule", edges: "axis_z" },
        [],
        null,
      ),
    ).toEqual({
      radius_mm: 5,
      edges: { kind: "axis_parallel", axis: "Z" },
    } satisfies FilletParams);
    expect(
      buildFilletParams(
        { radiusInput: "0", mode: "rule", edges: "all_edges" },
        [],
        null,
      ),
    ).toBeNull();
    expect(
      canSubmitFillet(
        { radiusInput: "", mode: "rule", edges: "all_edges" },
        [],
        null,
      ),
    ).toBe(false);
  });

  it("builds a picked-edge FilletParamsV1 in pick mode", () => {
    const params = buildFilletParams(
      { radiusInput: "5", mode: "pick", edges: "all_edges" },
      [SIG_A],
      "feat-1",
    );
    expect(params).toEqual({
      radius_mm: 5,
      edges: {
        kind: "edges",
        refs: [
          {
            kind: "subshape",
            feature_id: "feat-1",
            subshape_type: "edge",
            selector: { selector_version: 1, signature: SIG_A },
          },
        ],
      },
    } satisfies FilletParams);
  });

  it("cannot submit a pick-mode fillet with no picks", () => {
    expect(
      canSubmitFillet(
        { radiusInput: "5", mode: "pick", edges: "all_edges" },
        [],
        "feat-1",
      ),
    ).toBe(false);
  });

  it("round-trips a predicate fillet into the form", () => {
    const params: FilletParams = { radius_mm: 3, edges: { kind: "all_edges" } };
    expect(formFromFilletParams(params)).toEqual({
      radiusInput: "3",
      mode: "rule",
      edges: "all_edges",
    });
    expect(pickedFromFilletParams(params)).toEqual([]);
  });

  it("round-trips a picked-edge fillet into pick mode + its signatures", () => {
    const params: FilletParams = {
      radius_mm: 4,
      edges: {
        kind: "edges",
        refs: [
          {
            kind: "subshape",
            feature_id: "feat-1",
            subshape_type: "edge",
            selector: { selector_version: 1, signature: SIG_A },
          },
          {
            kind: "subshape",
            feature_id: "feat-1",
            subshape_type: "edge",
            selector: { selector_version: 1, signature: SIG_B },
          },
        ],
      },
    };
    expect(formFromFilletParams(params).mode).toBe("pick");
    expect(pickedFromFilletParams(params)).toEqual([SIG_A, SIG_B]);
  });

  it("flags a non-positive radius, stays quiet while empty", () => {
    expect(radiusError("")).toBeNull();
    expect(radiusError("5")).toBeNull();
    expect(radiusError("0")).toContain("positive");
  });
});

describe("chamfer form", () => {
  it("defaults to a 1 mm bevel of every edge, by rule", () => {
    const form = defaultChamferForm();
    expect(form.distanceInput).toBe("1");
    expect(form.mode).toBe("rule");
    expect(form.edges).toBe("all_edges");
  });

  it("builds a predicate ChamferParamsV1 in rule mode, null for a bad value", () => {
    expect(
      buildChamferParams(
        { distanceInput: "1.5", mode: "rule", edges: "axis_x" },
        [],
        null,
      ),
    ).toEqual({
      distance_mm: 1.5,
      edges: { kind: "axis_parallel", axis: "X" },
    } satisfies ChamferParams);
    expect(
      buildChamferParams(
        { distanceInput: "-1", mode: "rule", edges: "all_edges" },
        [],
        null,
      ),
    ).toBeNull();
    expect(
      canSubmitChamfer(
        { distanceInput: "2", mode: "rule", edges: "all_edges" },
        [],
        null,
      ),
    ).toBe(true);
  });

  it("builds a picked-edge ChamferParamsV1 in pick mode", () => {
    const params = buildChamferParams(
      { distanceInput: "2", mode: "pick", edges: "all_edges" },
      [SIG_B],
      "feat-1",
    );
    expect(params?.edges).toEqual({
      kind: "edges",
      refs: [
        {
          kind: "subshape",
          feature_id: "feat-1",
          subshape_type: "edge",
          selector: { selector_version: 1, signature: SIG_B },
        },
      ],
    });
  });

  it("round-trips a predicate chamfer into the form", () => {
    const params: ChamferParams = {
      distance_mm: 2,
      edges: { kind: "axis_parallel", axis: "Y" },
    };
    expect(formFromChamferParams(params)).toEqual({
      distanceInput: "2",
      mode: "rule",
      edges: "axis_y",
    });
    expect(pickedFromChamferParams(params)).toEqual([]);
  });

  it("flags a non-positive distance, stays quiet while empty", () => {
    expect(distanceError("")).toBeNull();
    expect(distanceError("1")).toBeNull();
    expect(distanceError("0")).toContain("positive");
  });
});
