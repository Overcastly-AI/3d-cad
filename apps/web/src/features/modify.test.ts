import { describe, expect, it } from "vitest";

import type { ChamferParams, FilletParams } from "../api/parts";
import {
  buildChamferParams,
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
  radiusError,
} from "./modify";

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
  it("defaults to a 2 mm round of every edge", () => {
    const form = defaultFilletForm();
    expect(form.radiusInput).toBe("2");
    expect(form.edges).toBe("all_edges");
  });

  it("builds FilletParamsV1 from a valid form, null otherwise", () => {
    expect(buildFilletParams({ radiusInput: "5", edges: "axis_z" })).toEqual({
      radius_mm: 5,
      edges: { kind: "axis_parallel", axis: "Z" },
    } satisfies FilletParams);
    expect(
      buildFilletParams({ radiusInput: "0", edges: "all_edges" }),
    ).toBeNull();
    expect(canSubmitFillet({ radiusInput: "", edges: "all_edges" })).toBe(
      false,
    );
  });

  it("round-trips existing params into the form", () => {
    const params: FilletParams = {
      radius_mm: 3,
      edges: { kind: "all_edges" },
    };
    expect(formFromFilletParams(params)).toEqual({
      radiusInput: "3",
      edges: "all_edges",
    });
  });

  it("flags a non-positive radius, stays quiet while empty", () => {
    expect(radiusError("")).toBeNull();
    expect(radiusError("5")).toBeNull();
    expect(radiusError("0")).toContain("positive");
  });
});

describe("chamfer form", () => {
  it("defaults to a 1 mm bevel of every edge", () => {
    const form = defaultChamferForm();
    expect(form.distanceInput).toBe("1");
    expect(form.edges).toBe("all_edges");
  });

  it("builds ChamferParamsV1 from a valid form, null otherwise", () => {
    expect(
      buildChamferParams({ distanceInput: "1.5", edges: "axis_x" }),
    ).toEqual({
      distance_mm: 1.5,
      edges: { kind: "axis_parallel", axis: "X" },
    } satisfies ChamferParams);
    expect(
      buildChamferParams({ distanceInput: "-1", edges: "all_edges" }),
    ).toBeNull();
    expect(canSubmitChamfer({ distanceInput: "2", edges: "all_edges" })).toBe(
      true,
    );
  });

  it("round-trips existing params into the form", () => {
    const params: ChamferParams = {
      distance_mm: 2,
      edges: { kind: "axis_parallel", axis: "Y" },
    };
    expect(formFromChamferParams(params)).toEqual({
      distanceInput: "2",
      edges: "axis_y",
    });
  });

  it("flags a non-positive distance, stays quiet while empty", () => {
    expect(distanceError("")).toBeNull();
    expect(distanceError("1")).toBeNull();
    expect(distanceError("0")).toContain("positive");
  });
});
