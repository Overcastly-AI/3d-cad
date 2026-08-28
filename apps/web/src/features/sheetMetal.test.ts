import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type {
  EdgeSignature,
  FeatureResponse,
  SheetMetalBaseFlangeParams,
  SheetMetalCornerReliefParams,
  SheetMetalEdgeFlangeParams,
  SheetMetalHemParams,
} from "../api/parts";
import {
  bendAngleError,
  buildBaseFlangeParams,
  buildCornerReliefParams,
  buildEdgeFlangeParams,
  buildHemParams,
  canAuthorCornerRelief,
  canSubmitBaseFlange,
  canSubmitCornerRelief,
  canSubmitEdgeFlange,
  canSubmitHem,
  cornerReliefBendHighlights,
  defaultBaseFlangeForm,
  defaultCornerReliefForm,
  defaultEdgeFlangeForm,
  defaultHemForm,
  derivedHemRadiusMm,
  edgeFlangeOptions,
  edgeFlangeSpanPreview,
  flangeLengthError,
  flangeOffsetError,
  flangeWidthError,
  formFromBaseFlangeParams,
  formFromCornerReliefParams,
  formFromEdgeFlangeParams,
  formFromHemParams,
  HEM_CLOSED_MAX_RADIUS_RATIO,
  HEM_CLOSED_RADIUS_RATIO,
  HEM_OPEN_RADIUS_RATIO,
  hemGapInGauges,
  hemGapMm,
  hemLengthError,
  hemRadiusBoundaryMm,
  hemRadiusConflict,
  isSheetMetalPart,
  kFactorError,
  parseBendAngleDeg,
  parseKFactor,
  parseReliefRatio,
  pickedFromEdgeFlangeParams,
  pickedFromHemParams,
  reliefRatioError,
  resolvedHemRadiusMm,
  SHEET_METAL_DEFAULT_K_FACTOR,
  sheetMetalDefaults,
  thicknessError,
  unresolvedBendRef,
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

describe("edge flange width extents (§4.5.1)", () => {
  // A 100 mm edge from end_a (0,0,2) to end_b (0,100,2) — the founder case's edge.
  const EDGE: EdgeSignature = {
    curve: "line",
    end_a: { x: 0, y: 0, z: 2 },
    end_b: { x: 0, y: 100, z: 2 },
    midpoint: { x: 0, y: 50, z: 2 },
    length_mm: 100,
    subshape_type: "edge",
  };

  it("full width (the default) sends NEITHER width nor offset — legacy byte-identity", () => {
    const params = buildEdgeFlangeParams(
      defaultEdgeFlangeForm(),
      [EDGE],
      "bf",
      "mm",
    );
    expect(params).not.toBe(null);
    expect("width_mm" in (params as object)).toBe(false);
    expect("offset_mm" in (params as object)).toBe(false);
  });

  it("the founder case (offset 0 + width 50) sends width, omits the 0 offset", () => {
    const form = {
      ...defaultEdgeFlangeForm(),
      flangeLengthInput: "50",
      widthExtent: "offset" as const,
      widthInput: "50",
      offsetInput: "0",
    };
    const params = buildEdgeFlangeParams(form, [EDGE], "bf", "mm");
    expect(params?.width_mm).toBe(50);
    expect("offset_mm" in (params as object)).toBe(false);
  });

  it("an explicit non-zero offset is sent", () => {
    const form = {
      ...defaultEdgeFlangeForm(),
      widthExtent: "offset" as const,
      widthInput: "40",
      offsetInput: "10",
    };
    const params = buildEdgeFlangeParams(form, [EDGE], "bf", "mm");
    expect(params?.width_mm).toBe(40);
    expect(params?.offset_mm).toBe(10);
  });

  it("centered computes the offset that centers width on the edge", () => {
    const form = {
      ...defaultEdgeFlangeForm(),
      widthExtent: "centered" as const,
      widthInput: "50",
    };
    const params = buildEdgeFlangeParams(form, [EDGE], "bf", "mm");
    // (100 − 50) / 2 = 25.
    expect(params?.width_mm).toBe(50);
    expect(params?.offset_mm).toBe(25);
  });

  it("blocks submit on a non-positive width or a width wider than the edge", () => {
    const zero = {
      ...defaultEdgeFlangeForm(),
      widthExtent: "offset" as const,
      widthInput: "0",
      offsetInput: "0",
    };
    expect(canSubmitEdgeFlange(zero, [EDGE], "bf", "mm")).toBe(false);
    // Centered wider than the edge → the computed offset would be negative.
    const tooWide = {
      ...defaultEdgeFlangeForm(),
      widthExtent: "centered" as const,
      widthInput: "120",
    };
    expect(canSubmitEdgeFlange(tooWide, [EDGE], "bf", "mm")).toBe(false);
  });

  it("blocks submit on a negative offset (schema bound, client-side)", () => {
    const form = {
      ...defaultEdgeFlangeForm(),
      widthExtent: "offset" as const,
      widthInput: "40",
      offsetInput: "-5",
    };
    expect(canSubmitEdgeFlange(form, [EDGE], "bf", "mm")).toBe(false);
    expect(flangeOffsetError("-5", "mm")).not.toBe(null);
    expect(flangeOffsetError("0", "mm")).toBe(null);
    expect(flangeWidthError("0", "mm")).not.toBe(null);
    expect(flangeWidthError("40", "mm")).toBe(null);
  });

  it("round-trips an offset-extent flange (edit seed)", () => {
    const params: SheetMetalEdgeFlangeParams = {
      edge: {
        kind: "subshape",
        feature_id: "bf",
        subshape_type: "edge",
        selector: { selector_version: 1, signature: EDGE },
      },
      flange_length_mm: 50,
      bend_angle_deg: 90,
      width_mm: 40,
      offset_mm: 10,
    };
    const form = formFromEdgeFlangeParams(params, "mm");
    expect(form.widthExtent).toBe("offset");
    expect(form.widthInput).toBe("40");
    expect(form.offsetInput).toBe("10");
    expect(buildEdgeFlangeParams(form, [EDGE], "bf", "mm")).toEqual(params);
  });

  it("a legacy flange (no width/offset) round-trips to Full width", () => {
    const params: SheetMetalEdgeFlangeParams = {
      edge: {
        kind: "subshape",
        feature_id: "bf",
        subshape_type: "edge",
        selector: { selector_version: 1, signature: EDGE },
      },
      flange_length_mm: 30,
      bend_angle_deg: 90,
    };
    const form = formFromEdgeFlangeParams(params, "mm");
    expect(form.widthExtent).toBe("full");
    expect(buildEdgeFlangeParams(form, [EDGE], "bf", "mm")).toEqual(params);
  });

  it("previews the chosen span ON the edge, measured from end_a", () => {
    const form = {
      ...defaultEdgeFlangeForm(),
      widthExtent: "offset" as const,
      widthInput: "50",
      offsetInput: "0",
    };
    const span = edgeFlangeSpanPreview(form, [EDGE], "mm");
    // [0, 50] from end_a along +y.
    expect(span?.start).toEqual({ x: 0, y: 0, z: 2 });
    expect(span?.end).toEqual({ x: 0, y: 50, z: 2 });
    expect(span?.spanMm).toBe(50);
    // Full width spans the whole edge.
    const full = edgeFlangeSpanPreview(defaultEdgeFlangeForm(), [EDGE], "mm");
    expect(full?.spanMm).toBe(100);
    // No preview without exactly one picked edge.
    expect(edgeFlangeSpanPreview(form, [], "mm")).toBe(null);
  });
});

describe("part sheet-metal state", () => {
  it("reads defaults from the first live base flange", () => {
    const features = [
      feature("sk", "sketch", {}),
      baseFlangeFeature({ bend_radius_mm: 3, k_factor: 0.44 }),
    ];
    expect(sheetMetalDefaults(features)).toEqual({
      thicknessMm: 2,
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

/**
 * The py-kit module the client's hem rule mirrors. Named by path deliberately:
 * if the schema module moves, this fails loudly instead of quietly guarding
 * nothing (the `thread.test.ts` idiom).
 */
const PY_KIT_FEATURES = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../../packages/py-kit/src/py_kit/schemas/features.py",
);

/** Read a module-level `NAME = <float>` constant out of the py-kit source. */
function pyConstant(source: string, name: string): number {
  const match = new RegExp(`^${name} = ([\\d.]+)$`, "m").exec(source);
  expect(match, `py-kit constant ${name} not found`).not.toBe(null);
  return Number((match as RegExpExecArray)[1]);
}

describe("the hem radius rule mirrors py-kit", () => {
  // HEM-1C's whole cause was a SECOND, drifted copy of this rule: the editor
  // hinted 0.5 x gauge for a closed hem — the OPEN ratio, and the one value the
  // evaluator refuses by name. The ratios are module constants behind
  // `resolve_hem_bend_radius_mm`, not schema fields, so the generated client
  // carries no wire value to read; this pin is what keeps the copy honest.
  const source = readFileSync(PY_KIT_FEATURES, "utf8");

  it("uses py_kit's own ratios, not a hand-kept second opinion", () => {
    expect(HEM_CLOSED_RADIUS_RATIO).toBe(
      pyConstant(source, "HEM_CLOSED_RADIUS_RATIO"),
    );
    expect(HEM_CLOSED_MAX_RADIUS_RATIO).toBe(
      pyConstant(source, "HEM_CLOSED_MAX_RADIUS_RATIO"),
    );
    expect(HEM_OPEN_RADIUS_RATIO).toBe(
      pyConstant(source, "HEM_OPEN_RADIUS_RATIO"),
    );
  });

  it("mirrors the refusal the evaluator actually raises", () => {
    // The client says this BEFORE the rebuild, so it has to be the same rule:
    // a closed hem refuses a radius ABOVE the boundary, an open one BELOW it,
    // and the boundary itself belongs to both (the bands partition the line).
    expect(source).toContain("if override_mm > boundary:");
    expect(source).toContain("if override_mm < boundary:");
    expect(source).toContain("boundary = HEM_CLOSED_MAX_RADIUS_RATIO");
  });
});

describe("the hem radius rule", () => {
  // 2 mm gauge, the fixture the HEM-1 defect was measured on.
  const T = 2;

  it("derives the radius from the TYPE and the gauge", () => {
    expect(derivedHemRadiusMm("closed", T)).toBeCloseTo(0.1, 12);
    expect(derivedHemRadiusMm("open", T)).toBeCloseTo(1, 12);
    // Gauge-proportional, so a second gauge exercises the rule rather than a
    // memorised pair of numbers.
    expect(derivedHemRadiusMm("closed", 1.5)).toBeCloseTo(0.075, 12);
    expect(derivedHemRadiusMm("open", 1.5)).toBeCloseTo(0.75, 12);
  });

  it("reads the gap as twice the radius — 0.1 t closed, 1 t open", () => {
    expect(hemGapMm(derivedHemRadiusMm("closed", T))).toBeCloseTo(0.2, 12);
    expect(hemGapMm(derivedHemRadiusMm("open", T))).toBeCloseTo(2, 12);
    expect(hemGapInGauges(derivedHemRadiusMm("closed", T), T)).toBeCloseTo(
      0.1,
      12,
    );
    expect(hemGapInGauges(derivedHemRadiusMm("open", T), T)).toBeCloseTo(1, 12);
  });

  it("refuses a radius that describes the OTHER type, naming both ways out", () => {
    // 1 mm on 2 mm sheet is 0.5 x gauge — the OPEN ratio, and exactly what the
    // editor used to suggest for a CLOSED hem (HEM-1C).
    const closedTooWide = hemRadiusConflict("closed", 1, T, "mm");
    expect(closedTooWide).toContain("2 mm gap");
    expect(closedTooWide).toContain("Open");
    expect(closedTooWide).toContain("at most 0.25 mm");

    const openTooTight = hemRadiusConflict("open", 0.1, T, "mm");
    expect(openTooTight).toContain("Closed");
    expect(openTooTight).toContain("at least 0.25 mm");
  });

  it("accepts the boundary for BOTH types — no gap, no overlap", () => {
    const boundary = hemRadiusBoundaryMm(T);
    expect(boundary).toBeCloseTo(0.25, 12);
    expect(hemRadiusConflict("closed", boundary, T, "mm")).toBe(null);
    expect(hemRadiusConflict("open", boundary, T, "mm")).toBe(null);
    // …and each type's own derived radius is, of course, consistent with it.
    expect(
      hemRadiusConflict("closed", derivedHemRadiusMm("closed", T), T, "mm"),
    ).toBe(null);
    expect(
      hemRadiusConflict("open", derivedHemRadiusMm("open", T), T, "mm"),
    ).toBe(null);
  });

  it("resolves the radius the card shows: override first, else derived", () => {
    const defaults = { thicknessMm: T, bendRadiusMm: 3, kFactor: 0.44 };
    const base = defaultHemForm();
    // The part's own 3 mm bend radius is NEVER the answer (HEM-1).
    expect(resolvedHemRadiusMm(base, defaults, "mm")).toBeCloseTo(0.1, 12);
    expect(
      resolvedHemRadiusMm({ ...base, hemType: "open" }, defaults, "mm"),
    ).toBeCloseTo(1, 12);
    expect(
      resolvedHemRadiusMm(
        { ...base, overrideBendRadius: true, bendRadiusInput: "0.2" },
        defaults,
        "mm",
      ),
    ).toBeCloseTo(0.2, 12);
    // Nothing honest to show: an enabled-but-empty override, or no sheet body.
    expect(
      resolvedHemRadiusMm(
        { ...base, overrideBendRadius: true, bendRadiusInput: "" },
        defaults,
        "mm",
      ),
    ).toBe(null);
    expect(resolvedHemRadiusMm(base, null, "mm")).toBe(null);
  });
});

describe("hem form", () => {
  it("defaults to a 6 mm folded-back return, closed, radius derived", () => {
    const form = defaultHemForm();
    expect(form.lengthInput).toBe("6");
    expect(form.hemType).toBe("closed");
    expect(form.overrideBendRadius).toBe(false);
    expect(form.overrideKFactor).toBe(false);
  });

  it("authors an OPEN hem — the type is the user's, not a hardcode", () => {
    // HEM-1D: `buildHemParams` pinned `hem_type: "closed"`, so the open hem the
    // API ships could not be reached by clicking at all.
    const params = buildHemParams(
      { ...defaultHemForm(), hemType: "open" },
      [SIG],
      "bf",
      "mm",
    );
    expect(params?.hem_type).toBe("open");
    // Still no radius on the wire: the type derives it server-side.
    expect("bend_radius_mm" in (params as object)).toBe(false);
  });

  it("round-trips an open hem, and reads absent as closed", () => {
    const open: SheetMetalHemParams = {
      edge: {
        kind: "subshape",
        feature_id: "bf",
        subshape_type: "edge",
        selector: { selector_version: 1, signature: SIG },
      },
      length_mm: 8,
      hem_type: "open",
    };
    expect(formFromHemParams(open, "mm").hemType).toBe("open");
    expect(
      buildHemParams(formFromHemParams(open, "mm"), [SIG], "bf", "mm"),
    ).toEqual(open);
    // A feature stored before `hem_type` shipped reads as the closed hem it is.
    const legacy = { ...open } as Partial<SheetMetalHemParams>;
    delete legacy.hem_type;
    expect(formFromHemParams(legacy as SheetMetalHemParams, "mm").hemType).toBe(
      "closed",
    );
  });

  it("still BUILDS a conflicting radius — the card advises, the kernel decides", () => {
    // Deliberate: the client mirrors the rule to state it early, and blocking on
    // a mirror would turn any drift into a lockout on a value the evaluator
    // would have accepted. The typed `hem_type_radius_conflict` is the gate.
    const form = {
      ...defaultHemForm(),
      overrideBendRadius: true,
      bendRadiusInput: "1",
    };
    expect(hemRadiusConflict("closed", 1, 2, "mm")).not.toBe(null);
    expect(canSubmitHem(form, [SIG], "bf", "mm")).toBe(true);
    expect(buildHemParams(form, [SIG], "bf", "mm")?.bend_radius_mm).toBe(1);
  });

  it("needs exactly one picked edge and a body anchor", () => {
    const form = defaultHemForm();
    expect(canSubmitHem(form, [], "bf", "mm")).toBe(false);
    expect(canSubmitHem(form, [SIG, SIG], "bf", "mm")).toBe(false);
    expect(canSubmitHem(form, [SIG], null, "mm")).toBe(false);
    expect(canSubmitHem(form, [SIG], "bf", "mm")).toBe(true);
  });

  it("builds a closed hem ref, omitting inherited defaults", () => {
    const params = buildHemParams(defaultHemForm(), [SIG], "bf", "mm");
    expect(params).not.toBe(null);
    expect(params?.edge.feature_id).toBe("bf");
    expect(params?.edge.selector.signature).toEqual(SIG);
    expect(params?.length_mm).toBe(6);
    expect(params?.hem_type).toBe("closed");
    // Inherited defaults are omitted, not sent as null (the edge-flange idiom).
    expect("bend_radius_mm" in (params as object)).toBe(false);
    expect("k_factor" in (params as object)).toBe(false);
  });

  it("sends per-hem overrides only when enabled + valid", () => {
    const form = {
      ...defaultHemForm(),
      overrideBendRadius: true,
      bendRadiusInput: "1",
      overrideKFactor: true,
      kFactorInput: "0.4",
    };
    const params = buildHemParams(form, [SIG], "bf", "mm");
    expect(params?.bend_radius_mm).toBe(1);
    expect(params?.k_factor).toBe(0.4);
    // An enabled-but-blank override blocks the build (honest, not silently 0).
    expect(
      buildHemParams({ ...form, bendRadiusInput: "" }, [SIG], "bf", "mm"),
    ).toBe(null);
    expect(hemLengthError("-3", "mm")).not.toBe(null);
    expect(hemLengthError("", "mm")).toBe(null);
  });

  it("round-trips an override hem (edit seed)", () => {
    const params: SheetMetalHemParams = {
      edge: {
        kind: "subshape",
        feature_id: "bf",
        subshape_type: "edge",
        selector: { selector_version: 1, signature: SIG },
      },
      length_mm: 8,
      hem_type: "closed",
      bend_radius_mm: 1,
      k_factor: 0.4,
    };
    const form = formFromHemParams(params, "mm");
    expect(form.lengthInput).toBe("8");
    expect(form.overrideBendRadius).toBe(true);
    expect(form.overrideKFactor).toBe(true);
    expect(pickedFromHemParams(params)).toEqual([SIG]);
    expect(buildHemParams(form, [SIG], "bf", "mm")).toEqual(params);
  });
});

describe("corner relief form", () => {
  const edgeFlange = (id: string, rolled_back = false): FeatureResponse =>
    feature(
      id,
      "sheet_metal_edge_flange",
      {
        edge: {
          kind: "subshape",
          feature_id: "bf",
          subshape_type: "edge",
          selector: { selector_version: 1, signature: SIG },
        },
        flange_length_mm: 20,
        bend_angle_deg: 90,
      },
      rolled_back,
    );

  it("lists edge flanges by id + name and gates on two of them", () => {
    const one = [
      feature("bf", "sheet_metal_base_flange", {}),
      edgeFlange("f1"),
    ];
    const two = [...one, edgeFlange("f2")];
    expect(edgeFlangeOptions(one)).toEqual([{ id: "f1", name: "f1" }]);
    expect(canAuthorCornerRelief(one)).toBe(false);
    expect(canAuthorCornerRelief(two)).toBe(true);
    // A rolled-back edge flange does not count toward the gate.
    expect(canAuthorCornerRelief([...one, edgeFlange("f2", true)])).toBe(false);
  });

  it("needs two DISTINCT bends and a positive ratio", () => {
    expect(canSubmitCornerRelief(defaultCornerReliefForm("a", "b"), "mm")).toBe(
      true,
    );
    expect(canSubmitCornerRelief(defaultCornerReliefForm("a", "a"), "mm")).toBe(
      false,
    );
    expect(canSubmitCornerRelief(defaultCornerReliefForm("", "b"), "mm")).toBe(
      false,
    );
    expect(parseReliefRatio("1")).toBe(1);
    expect(parseReliefRatio("0")).toBe(null);
    expect(parseReliefRatio("-1")).toBe(null);
    expect(reliefRatioError("0")).not.toBe(null);
    expect(reliefRatioError("")).toBe(null);
  });

  it("builds two FeatureRefs + rectangular type, ratio by default", () => {
    const params = buildCornerReliefParams(
      defaultCornerReliefForm("a", "b"),
      "mm",
    );
    expect(params).toEqual({
      bend_a: { kind: "feature", feature_id: "a" },
      bend_b: { kind: "feature", feature_id: "b" },
      relief_ratio: 1,
      relief_type: "rectangular",
    });
    // No size override → no size_mm on the wire (the ratio drives the notch).
    expect("size_mm" in (params as object)).toBe(false);
  });

  it("sends an absolute size override only when enabled + valid", () => {
    const form = {
      ...defaultCornerReliefForm("a", "b"),
      overrideSize: true,
      sizeInput: "3",
    };
    const params = buildCornerReliefParams(form, "mm");
    expect(params?.size_mm).toBe(3);
    // relief_ratio still rides the wire (it has no null slot), ignored server-side.
    expect(params?.relief_ratio).toBe(1);
    // An enabled-but-blank override blocks the build.
    expect(buildCornerReliefParams({ ...form, sizeInput: "" }, "mm")).toBe(
      null,
    );
  });

  it("round-trips a size-override corner relief (edit seed)", () => {
    const params: SheetMetalCornerReliefParams = {
      bend_a: { kind: "feature", feature_id: "a" },
      bend_b: { kind: "feature", feature_id: "b" },
      relief_ratio: 1.5,
      relief_type: "rectangular",
      size_mm: 4,
    };
    const form = formFromCornerReliefParams(params, "mm");
    expect(form.bendAId).toBe("a");
    expect(form.bendBId).toBe("b");
    expect(form.reliefRatioInput).toBe("1.5");
    expect(form.overrideSize).toBe(true);
    expect(form.sizeInput).toBe("4");
    expect(buildCornerReliefParams(form, "mm")).toEqual(params);
  });
});

describe("corner relief bend refs + viewport highlight", () => {
  const sig = (y: number): EdgeSignature => ({
    ...SIG,
    end_b: { x: 50, y, z: 2 },
    midpoint: { x: 50, y: y / 2, z: 2 },
    length_mm: y,
  });
  const edgeFlange = (
    id: string,
    signature: EdgeSignature,
    rolled_back = false,
  ): FeatureResponse =>
    feature(
      id,
      "sheet_metal_edge_flange",
      {
        edge: {
          kind: "subshape",
          feature_id: "bf",
          subshape_type: "edge",
          selector: { selector_version: 1, signature },
        },
        flange_length_mm: 20,
        bend_angle_deg: 90,
      },
      rolled_back,
    );
  const tree = [
    feature("bf", "sheet_metal_base_flange", {}),
    edgeFlange("f1", sig(20)),
    edgeFlange("f2", sig(30)),
    edgeFlange("gone", sig(40), true),
  ];

  it("flags a stored bend ref that no longer resolves to a live flange", () => {
    const options = edgeFlangeOptions(tree);
    expect(unresolvedBendRef(options, "f1")).toBe(false);
    // A rolled-back flange is filtered from the options → its ref is stale.
    expect(unresolvedBendRef(options, "gone")).toBe(true);
    expect(unresolvedBendRef(options, "deleted")).toBe(true);
    // Empty is "not selected yet", never a stale ref.
    expect(unresolvedBendRef(options, "")).toBe(false);
  });

  it("resolves the selected bends to tagged fold-edge signatures", () => {
    expect(cornerReliefBendHighlights(tree, "f1", "f2")).toEqual([
      { tag: "A", signature: sig(20) },
      { tag: "B", signature: sig(30) },
    ]);
  });

  it("drops unresolved / empty refs instead of guessing a flange", () => {
    // The rolled-back flange and an unknown id yield NO highlight (the select
    // guard owns that state); the live pick still draws.
    expect(cornerReliefBendHighlights(tree, "gone", "f2")).toEqual([
      { tag: "B", signature: sig(30) },
    ]);
    expect(cornerReliefBendHighlights(tree, "", "deleted")).toEqual([]);
  });

  it("collapses the same flange picked twice into one A · B tag", () => {
    expect(cornerReliefBendHighlights(tree, "f1", "f1")).toEqual([
      { tag: "A · B", signature: sig(20) },
    ]);
  });
});
