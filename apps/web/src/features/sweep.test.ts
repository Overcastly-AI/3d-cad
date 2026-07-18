import { describe, expect, it } from "vitest";

import type { FeatureResponse, SweepParams } from "../api/parts";
import {
  buildSweepParams,
  canSubmitSweep,
  defaultSweepForm,
  defaultSweepPathId,
  defaultSweepProfileId,
  formFromSweepParams,
  pathOptions,
  sweepEligibleSketchCount,
} from "./sweep";

function sketch(id: string, name: string): FeatureResponse {
  return {
    id,
    name,
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
        entities: [],
        constraints: [],
      },
    },
  };
}

function extrude(id: string, profileId: string): FeatureResponse {
  return {
    ...sketch(id, "Extrude1"),
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: profileId },
        distance_mm: 12,
        operation: "add",
        direction: "normal",
      },
    },
  };
}

const twoSketchesAndABody = [
  sketch("s1", "Sketch1"),
  sketch("s2", "Sketch2"),
  extrude("x1", "s1"),
];

describe("defaultSweepForm", () => {
  it("is add against the given profile + path sketches", () => {
    expect(defaultSweepForm("s1", "s2")).toEqual({
      profileFeatureId: "s1",
      pathFeatureId: "s2",
      operation: "add",
    });
  });
});

describe("formFromSweepParams", () => {
  it("round-trips an existing sweep's params into editable form state", () => {
    const params: SweepParams = {
      profile: { kind: "feature", feature_id: "s1" },
      path: { kind: "feature", feature_id: "s2" },
      operation: "cut",
    };
    expect(formFromSweepParams(params)).toEqual({
      profileFeatureId: "s1",
      pathFeatureId: "s2",
      operation: "cut",
    });
  });
});

describe("canSubmitSweep", () => {
  it("needs a profile, a path, and the two to be different sketches", () => {
    expect(canSubmitSweep(defaultSweepForm("s1", "s2"))).toBe(true);
    expect(canSubmitSweep(defaultSweepForm("", "s2"))).toBe(false);
    expect(canSubmitSweep(defaultSweepForm("s1", ""))).toBe(false);
    // A sketch is a closed profile OR an open path, never both.
    expect(canSubmitSweep(defaultSweepForm("s1", "s1"))).toBe(false);
  });
});

describe("pathOptions", () => {
  it("offers only sketches, excluding the chosen profile", () => {
    expect(pathOptions(twoSketchesAndABody, "s1").map((s) => s.id)).toEqual([
      "s2",
    ]);
    expect(pathOptions(twoSketchesAndABody, "s2").map((s) => s.id)).toEqual([
      "s1",
    ]);
    // The extrude is not a sketch — never a path candidate.
    expect(
      pathOptions(twoSketchesAndABody, "s1").some((s) => s.id === "x1"),
    ).toBe(false);
  });
});

describe("defaultSweepProfileId / defaultSweepPathId", () => {
  it("defaults profile to the first sketch and path to the next sketch", () => {
    expect(defaultSweepProfileId(twoSketchesAndABody)).toBe("s1");
    expect(defaultSweepPathId(twoSketchesAndABody, "s1")).toBe("s2");
    // Change the profile and the path default follows to a different sketch.
    expect(defaultSweepPathId(twoSketchesAndABody, "s2")).toBe("s1");
  });

  it("is '' when there is no eligible sketch", () => {
    expect(defaultSweepProfileId([])).toBe("");
    expect(defaultSweepPathId([sketch("s1", "Sketch1")], "s1")).toBe("");
  });
});

describe("sweepEligibleSketchCount", () => {
  it("counts sketch features (the tool needs ≥2)", () => {
    expect(sweepEligibleSketchCount(twoSketchesAndABody)).toBe(2);
    expect(sweepEligibleSketchCount([sketch("s1", "Sketch1")])).toBe(1);
    expect(sweepEligibleSketchCount([extrude("x1", "s1")])).toBe(0);
  });
});

describe("buildSweepParams", () => {
  it("builds the FeatureRef params from a valid form", () => {
    expect(buildSweepParams(defaultSweepForm("s1", "s2"))).toEqual({
      profile: { kind: "feature", feature_id: "s1" },
      path: { kind: "feature", feature_id: "s2" },
      operation: "add",
    });
  });

  it("is null when the form is incomplete or self-referential", () => {
    expect(buildSweepParams(defaultSweepForm("", "s2"))).toBeNull();
    expect(buildSweepParams(defaultSweepForm("s1", "s1"))).toBeNull();
  });
});
