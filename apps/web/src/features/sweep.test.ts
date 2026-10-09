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
  sweepSubmitBlocker,
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
        merge: true,
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
      merge: true,
      twistInput: "",
    });
  });
});

describe("formFromSweepParams", () => {
  it("round-trips an existing sweep's params into editable form state", () => {
    const params: SweepParams = {
      profile: { kind: "feature", feature_id: "s1" },
      path: { kind: "feature", feature_id: "s2" },
      operation: "cut",
      merge: true,
    };
    expect(formFromSweepParams(params)).toEqual({
      profileFeatureId: "s1",
      pathFeatureId: "s2",
      operation: "cut",
      merge: true,
      twistInput: "",
      stored: params,
    });
  });
});

describe("canSubmitSweep", () => {
  it("needs a profile, a path, and the two to be different sketches", () => {
    expect(canSubmitSweep(defaultSweepForm("s1", "s2"))).toBe(true);
    expect(canSubmitSweep(defaultSweepForm("", "s2"))).toBe(false);
    expect(canSubmitSweep(defaultSweepForm("s1", ""))).toBe(false);
    // A sketch is the profile OR the path, never both.
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
      merge: true,
    });
  });

  it("is null when the form is incomplete or self-referential", () => {
    expect(buildSweepParams(defaultSweepForm("", "s2"))).toBeNull();
    expect(buildSweepParams(defaultSweepForm("s1", "s1"))).toBeNull();
  });
});

describe("twist along path (TWIST-TO-SWEEP)", () => {
  const plain: SweepParams = {
    profile: { kind: "feature", feature_id: "s1" },
    path: { kind: "feature", feature_id: "s2" },
    operation: "add",
    merge: true,
  };
  const twisted: SweepParams = {
    ...plain,
    twist_angle_deg: 31.280937437761875,
  };

  it("a typed twist sends the signed angle", () => {
    for (const [input, deg] of [
      ["30", 30],
      ["-45", -45],
      ["3600", 3600],
    ] as const) {
      const form = { ...defaultSweepForm("s1", "s2"), twistInput: input };
      expect(buildSweepParams(form)).toEqual({
        ...plain,
        twist_angle_deg: deg,
      });
    }
  });

  it("NO twist sends NO twist key: absent, not null or 0", () => {
    for (const input of ["", " ", "0", "-0", "1e-12"]) {
      const form = { ...defaultSweepForm("s1", "s2"), twistInput: input };
      const params = buildSweepParams(form);
      expect(params).toEqual(plain);
      expect(Object.keys(params ?? {})).not.toContain("twist_angle_deg");
    }
  });

  it("a stored twist round-trips params -> form -> params EXACTLY (no-op Save)", () => {
    for (const angle of [31.280937437761875, -0.1 - 0.2, 12.358, -3600]) {
      const stored = { ...plain, twist_angle_deg: angle };
      expect(buildSweepParams(formFromSweepParams(stored))).toEqual(stored);
    }
  });

  it("editing ONLY the path, operation or merge keeps the stored twist", () => {
    // The review's blocking finding: a PATCH replaces the params wholesale,
    // so a form that dropped the twist straightened a stored twisted sweep
    // (loft-script, the helical gear) on any edit.
    const form = formFromSweepParams(twisted);
    expect(buildSweepParams({ ...form, pathFeatureId: "s3" })).toEqual({
      ...twisted,
      path: { kind: "feature", feature_id: "s3" },
    });
    expect(buildSweepParams({ ...form, operation: "cut" })).toEqual({
      ...twisted,
      operation: "cut",
    });
    expect(buildSweepParams({ ...form, merge: false })).toEqual({
      ...twisted,
      merge: false,
    });
  });

  it("clearing a stored twist removes it", () => {
    const form = { ...formFromSweepParams(twisted), twistInput: "" };
    expect(buildSweepParams(form)).toEqual(plain);
  });

  it("a wrong twist holds Create with a reason; an empty one does not", () => {
    const form = defaultSweepForm("s1", "s2");
    expect(sweepSubmitBlocker({ ...form, twistInput: "" })).toBeNull();
    for (const bad of ["abc", "3600.5", "-4000", "NaN"]) {
      expect(sweepSubmitBlocker({ ...form, twistInput: bad })).toBe(
        "Check the twist.",
      );
      expect(buildSweepParams({ ...form, twistInput: bad })).toBeNull();
    }
  });
});
