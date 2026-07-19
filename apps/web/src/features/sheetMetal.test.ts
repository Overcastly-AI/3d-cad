import { describe, expect, it } from "vitest";

import type {
  EdgeSignature,
  FeatureResponse,
  SheetMetalBaseFlangeParams,
  SheetMetalEdgeFlangeParams,
} from "../api/parts";
import {
  bendAngleError,
  buildBaseFlangeParams,
  buildEdgeFlangeParams,
  canSubmitBaseFlange,
  canSubmitEdgeFlange,
  defaultBaseFlangeForm,
  defaultEdgeFlangeForm,
  flangeLengthError,
  formFromBaseFlangeParams,
  formFromEdgeFlangeParams,
  isSheetMetalPart,
  kFactorError,
  parseBendAngleDeg,
  parseKFactor,
  pickedFromEdgeFlangeParams,
  SHEET_METAL_DEFAULT_K_FACTOR,
  sheetMetalDefaults,
  thicknessError,
} from "./sheetMetal";

const SIG: EdgeSignature = {
  curve: "line",
  end_a: { x: 50, y: 0, z: 2 },
  end_b: { x: 50, y: 20, z: 2 },
  midpoint: { x: 50, y: 10, z: 2 },
  length_mm: 20,
  subshape_type: "edge",
};

function feature(
  id: string,
  type: string,
  params: unknown,
  rolled_back = false,
): FeatureResponse {
  return {
    id,
    name: id,
    part_id: "p",
    order_index: 0,
    created_at: "2026-07-19T00:00:00Z",
    updated_at: "2026-07-19T00:00:00Z",
    rolled_back,
    // The union type is validated at the call sites; the tests only need the
    // discriminant + params shape.
    feature: { type, version: 1, params } as FeatureResponse["feature"],
  };
}

const baseFlangeFeature = (
  overrides: Partial<SheetMetalBaseFlangeParams> = {},
  rolled_back = false,
): FeatureResponse =>
  feature(
    "bf",
    "sheet_metal_base_flange",
    {
      profile: { kind: "feature", feature_id: "sk" },
      thickness_mm: 2,
      bend_radius_mm: 3,
      k_factor: 0.44,
      direction: "normal",
      merge: true,
      ...overrides,
    },
    rolled_back,
  );

describe("base flange form", () => {
  it("defaults to a light-gauge bracket with the pinned K", () => {
    const form = defaultBaseFlangeForm("sk");
    expect(form.profileFeatureId).toBe("sk");
    expect(form.kFactorInput).toBe(String(SHEET_METAL_DEFAULT_K_FACTOR));
    expect(canSubmitBaseFlange(form, "mm")).toBe(true);
  });

  it("builds params in canonical mm, carrying merge=true", () => {
    const params = buildBaseFlangeParams(
      {
        profileFeatureId: "sk",
        thicknessInput: "2",
        bendRadiusInput: "3",
        kFactorInput: "0.44",
        direction: "reverse",
      },
      "mm",
    );
    expect(params).toEqual({
      profile: { kind: "feature", feature_id: "sk" },
      thickness_mm: 2,
      bend_radius_mm: 3,
      k_factor: 0.44,
      direction: "reverse",
      merge: true,
    });
  });

  it("rejects a missing profile or a non-positive gauge / radius", () => {
    const ok = defaultBaseFlangeForm("sk");
    expect(buildBaseFlangeParams({ ...ok, profileFeatureId: "" }, "mm")).toBe(
      null,
    );
    expect(buildBaseFlangeParams({ ...ok, thicknessInput: "0" }, "mm")).toBe(
      null,
    );
    expect(buildBaseFlangeParams({ ...ok, bendRadiusInput: "-1" }, "mm")).toBe(
      null,
    );
  });

  it("rejects a K-factor outside [0, 1]", () => {
    expect(parseKFactor("0")).toBe(0);
    expect(parseKFactor("1")).toBe(1);
    expect(parseKFactor("0.44")).toBe(0.44);
    expect(parseKFactor("1.5")).toBe(null);
    expect(parseKFactor("-0.1")).toBe(null);
    expect(parseKFactor("")).toBe(null);
  });

  it("field errors are null while pending and set when invalid", () => {
    expect(thicknessError("", "mm")).toBe(null);
    expect(thicknessError("0", "mm")).not.toBe(null);
    expect(kFactorError("")).toBe(null);
    expect(kFactorError("2")).not.toBe(null);
  });

  it("round-trips through form ↔ params (edit seed)", () => {
    const params: SheetMetalBaseFlangeParams = {
      profile: { kind: "feature", feature_id: "sk" },
      thickness_mm: 1.5,
      bend_radius_mm: 4,
      k_factor: 0.33,
      direction: "reverse",
      merge: true,
    };
    const form = formFromBaseFlangeParams(params, "mm");
    expect(form.thicknessInput).toBe("1.5");
    expect(form.bendRadiusInput).toBe("4");
    expect(form.kFactorInput).toBe("0.33");
    expect(form.direction).toBe("reverse");
    expect(buildBaseFlangeParams(form, "mm")).toEqual(params);
  });
});

describe("edge flange form", () => {
  it("defaults to a 20 mm leg folded 90°, defaults inherited", () => {
    const form = defaultEdgeFlangeForm();
    expect(form.bendAngleInput).toBe("90");
    expect(form.overrideBendRadius).toBe(false);
    expect(form.overrideKFactor).toBe(false);
  });

  it("needs exactly one picked edge and a body anchor", () => {
    const form = defaultEdgeFlangeForm();
    expect(canSubmitEdgeFlange(form, [], "bf", "mm")).toBe(false);
    expect(canSubmitEdgeFlange(form, [SIG, SIG], "bf", "mm")).toBe(false);
    expect(canSubmitEdgeFlange(form, [SIG], null, "mm")).toBe(false);
    expect(canSubmitEdgeFlange(form, [SIG], "bf", "mm")).toBe(true);
  });

  it("builds a single-edge ref, omitting inherited defaults", () => {
    const params = buildEdgeFlangeParams(
      defaultEdgeFlangeForm(),
      [SIG],
      "bf",
      "mm",
    );
    expect(params).not.toBe(null);
    expect(params?.edge.feature_id).toBe("bf");
    expect(params?.edge.selector.signature).toEqual(SIG);
    expect(params?.flange_length_mm).toBe(20);
    expect(params?.bend_angle_deg).toBe(90);
    // Inherited defaults are omitted, not sent as null.
    expect("bend_radius_mm" in (params as object)).toBe(false);
    expect("k_factor" in (params as object)).toBe(false);
  });

  it("sends per-bend overrides only when enabled + valid", () => {
    const form = {
      ...defaultEdgeFlangeForm(),
      overrideBendRadius: true,
      bendRadiusInput: "5",
      overrideKFactor: true,
      kFactorInput: "0.5",
    };
    const params = buildEdgeFlangeParams(form, [SIG], "bf", "mm");
    expect(params?.bend_radius_mm).toBe(5);
    expect(params?.k_factor).toBe(0.5);
    // An enabled-but-blank override blocks the build (honest, not silently 0).
    expect(
      buildEdgeFlangeParams(
        { ...form, bendRadiusInput: "" },
        [SIG],
        "bf",
        "mm",
      ),
    ).toBe(null);
  });

  it("rejects a bend angle outside (0, 180]", () => {
    expect(parseBendAngleDeg("90")).toBe(90);
    expect(parseBendAngleDeg("180")).toBe(180);
    expect(parseBendAngleDeg("0")).toBe(null);
    expect(parseBendAngleDeg("181")).toBe(null);
    expect(bendAngleError("200")).not.toBe(null);
    expect(flangeLengthError("-3", "mm")).not.toBe(null);
  });

  it("round-trips an override edge flange (edit seed)", () => {
    const params: SheetMetalEdgeFlangeParams = {
      edge: {
        kind: "subshape",
        feature_id: "bf",
        subshape_type: "edge",
        selector: { selector_version: 1, signature: SIG },
      },
      flange_length_mm: 30,
      bend_angle_deg: 120,
      bend_radius_mm: 4,
      k_factor: 0.4,
    };
    const form = formFromEdgeFlangeParams(params, "mm");
    expect(form.flangeLengthInput).toBe("30");
    expect(form.bendAngleInput).toBe("120");
    expect(form.overrideBendRadius).toBe(true);
    expect(form.overrideKFactor).toBe(true);
    expect(pickedFromEdgeFlangeParams(params)).toEqual([SIG]);
    expect(buildEdgeFlangeParams(form, [SIG], "bf", "mm")).toEqual(params);
  });
});

describe("part sheet-metal state", () => {
  it("reads defaults from the first live base flange", () => {
    const features = [
      feature("sk", "sketch", {}),
      baseFlangeFeature({ bend_radius_mm: 3, k_factor: 0.44 }),
    ];
    expect(sheetMetalDefaults(features)).toEqual({
      bendRadiusMm: 3,
      kFactor: 0.44,
    });
    expect(isSheetMetalPart(features)).toBe(true);
  });

  it("ignores a rolled-back base flange", () => {
    const features = [baseFlangeFeature({}, true)];
    expect(sheetMetalDefaults(features)).toBe(null);
    expect(isSheetMetalPart(features)).toBe(false);
  });

  it("is not sheet metal without a base flange", () => {
    const features = [
      feature("sk", "sketch", {}),
      feature("ex", "extrude", {
        profile: { kind: "feature", feature_id: "sk" },
        distance_mm: 10,
        operation: "add",
        direction: "normal",
        merge: true,
      }),
    ];
    expect(isSheetMetalPart(features)).toBe(false);
  });
});
