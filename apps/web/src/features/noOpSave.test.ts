/**
 * A NO-OP SAVE LEAVES EVERY STORED PARAM BYTE-IDENTICAL, IN EVERY EDITOR.
 *
 * Each case seeds the editor's form from stored params exactly as the editor
 * does (`formFrom...Params`) and builds the params exactly as its Save does
 * (`build...Params`), touching nothing in between. Before the shared
 * `storedNumber` helpers, a length seeded through the 4-fraction-digit display
 * formatter came back as 12.3457 for a stored 12.345678901234: every editor
 * rewrote geometry, and the rebuild cache key, on a Save that changed nothing.
 *
 * Two values are used on purpose. 12.345678901234 mm has a shortest inch text
 * that multiplies back to itself; 7.123456789012 mm has NONE (x / 25.4 * 25.4
 * is not x), so in an inch document only the "untouched field means the stored
 * value" comparison can carry it. Every editor is run in mm AND in inches.
 *
 * Byte-identical is checked as canonical JSON (sorted keys, the wire's own
 * dropping of undefined), which is what the rebuild cache keys on.
 */
import { describe, expect, it } from "vitest";

import type {
  ChamferParams,
  DatumParams,
  DraftParams,
  EdgeSignature,
  ExtrudeParams,
  FilletParams,
  HoleParams,
  PatternParams,
  PlanarFaceSignature,
  RevolveParams,
  SheetMetalBaseFlangeParams,
  SheetMetalCornerReliefParams,
  SheetMetalEdgeFlangeParams,
  SheetMetalHemParams,
  ShellParams,
} from "../api/parts";
import { buildDatumParams, formFromDatumParams } from "./datum";
import { buildDraftParams, formFromDraftParams } from "./draft";
import { edgeSubshapeRef } from "./edge";
import {
  extrudeDistanceMm,
  extrudeParamsFromForm,
  formFromParams,
} from "./extrude";
import { faceSubshapeRef, onFaceDatumParams } from "./face";
import { buildHoleParams, formFromHoleParams } from "./hole";
import {
  buildChamferParams,
  buildFilletParams,
  edgeSelector,
  formFromChamferParams,
  formFromFilletParams,
} from "./modify";
import { buildPatternParams, formFromPatternParams } from "./pattern";
import { formFromRevolveParams, revolveParamsFromForm } from "./revolve";
import {
  buildBaseFlangeParams,
  buildCornerReliefParams,
  buildEdgeFlangeParams,
  buildHemParams,
  formFromBaseFlangeParams,
  formFromCornerReliefParams,
  formFromEdgeFlangeParams,
  formFromHemParams,
} from "./sheetMetal";
import { buildShellParams, formFromShellParams } from "./shell";

/** Survives the shortest inch text. */
const A = 12.345678901234;
/** Has NO inch text that multiplies back to itself. */
const B = 7.123456789012;
const UNITS = ["mm", "in"] as const;

/** Canonical JSON: sorted keys, undefined dropped (the cache key's view). */
function canonical(value: unknown): string {
  return JSON.stringify(value, (_key, v: unknown) =>
    v !== null && typeof v === "object" && !Array.isArray(v)
      ? Object.fromEntries(
          Object.entries(v as Record<string, unknown>).sort(([a], [b]) =>
            a < b ? -1 : a > b ? 1 : 0,
          ),
        )
      : v,
  );
}

function expectUnchanged(saved: unknown, stored: unknown): void {
  expect(saved).not.toBeNull();
  expect(canonical(saved)).toBe(canonical(stored));
}

const FACE: PlanarFaceSignature = {
  normal: { x: 0, y: 0, z: 1 },
  centroid: { x: 10, y: 10, z: 20 },
  area_mm2: 400,
  subshape_type: "face",
  surface: "plane",
};
const EDGE: EdgeSignature = {
  curve: "line",
  end_a: { x: 0, y: 0, z: 20 },
  end_b: { x: 40, y: 0, z: 20 },
  midpoint: { x: 20, y: 0, z: 20 },
  length_mm: 40,
  subshape_type: "edge",
};
const BODY = "body-feature";

for (const unit of UNITS) {
  describe(`a no-op Save is byte-identical (${unit} document)`, () => {
    it("extrude: distance", () => {
      const stored: ExtrudeParams = {
        profile: { kind: "feature", feature_id: "sk" },
        distance_mm: B,
        operation: "add",
        direction: "normal",
        merge: true,
      };
      const form = formFromParams(stored, unit);
      const distance = extrudeDistanceMm(form, unit);
      expect(distance).not.toBeNull();
      expectUnchanged(extrudeParamsFromForm(form, distance as number), stored);
    });

    it("revolve: angle", () => {
      const stored: RevolveParams = {
        profile: { kind: "feature", feature_id: "sk" },
        axis: { kind: "origin_axis", axis: "Z" },
        angle_deg: 123.456789012345,
        operation: "add",
        direction: "normal",
        merge: true,
      };
      const form = formFromRevolveParams(stored);
      expectUnchanged(revolveParamsFromForm(form, stored.axis), stored);
    });

    it("fillet: radius", () => {
      const stored: FilletParams = {
        radius_mm: A,
        edges: edgeSelector("all_edges"),
      };
      const form = formFromFilletParams(stored, unit);
      expectUnchanged(buildFilletParams(form, [], BODY, unit), stored);
    });

    it("chamfer: distance", () => {
      const stored: ChamferParams = {
        distance_mm: B,
        edges: edgeSelector("axis_z"),
      };
      const form = formFromChamferParams(stored, unit);
      expectUnchanged(buildChamferParams(form, [], BODY, unit), stored);
    });

    it("shell: thickness", () => {
      const stored: ShellParams = {
        thickness_mm: B,
        faces: { kind: "faces", refs: [] },
      };
      const form = formFromShellParams(stored, unit);
      expectUnchanged(buildShellParams(form, [], BODY, unit), stored);
    });

    it("hole: diameter, blind depth, counterbore diameter and depth", () => {
      const stored: HoleParams = {
        face: faceSubshapeRef(BODY, FACE),
        position: { x: 3.3333333333333335, y: 2.718281828459045, z: 20 },
        diameter_mm: A,
        depth: { kind: "blind", depth_mm: B },
        type: {
          kind: "counterbore",
          cbore_diameter_mm: 20.123456789012,
          cbore_depth_mm: B,
        },
      };
      const form = formFromHoleParams(stored, unit);
      expectUnchanged(buildHoleParams(form, unit), stored);
    });

    it("hole: countersink diameter and angle", () => {
      const stored: HoleParams = {
        face: faceSubshapeRef(BODY, FACE),
        position: { x: 1, y: 2, z: 20 },
        diameter_mm: 6,
        depth: { kind: "through_all" },
        type: {
          kind: "countersink",
          csink_diameter_mm: B,
          csink_angle_deg: 82.123456789,
        },
      };
      const form = formFromHoleParams(stored, unit);
      expectUnchanged(buildHoleParams(form, unit), stored);
    });

    it("pattern: linear spacing", () => {
      const stored: PatternParams = {
        pattern: {
          kind: "linear",
          direction: { x: 1, y: 0, z: 0 },
          spacing_mm: B,
          count: 4,
        },
        scope: { kind: "body" },
      };
      const form = formFromPatternParams(stored, unit);
      expectUnchanged(buildPatternParams(form, unit), stored);
    });

    it("pattern: circular axis point and angle", () => {
      const stored: PatternParams = {
        pattern: {
          kind: "circular",
          axis_point: { x: A, y: B, z: -B },
          axis_direction: { x: 0, y: 0, z: 1 },
          angle_deg: 270.123456789,
          count: 6,
        },
        scope: { kind: "body" },
      };
      const form = formFromPatternParams(stored, unit);
      expectUnchanged(buildPatternParams(form, unit), stored);
    });

    it("datum: offset, offset-from and on-face offsets", () => {
      const cases: DatumParams[] = [
        { kind: "offset", base: "XY", offset_mm: -B, flip: false },
        {
          kind: "offset_from",
          base: { kind: "feature", feature_id: "d1" },
          offset_mm: A,
          flip: true,
        },
        onFaceDatumParams(BODY, FACE, B),
      ];
      for (const stored of cases) {
        const form = formFromDatumParams(stored, unit);
        expectUnchanged(buildDatumParams(form, unit), stored);
      }
    });

    it("draft: angle and neutral-plane offset", () => {
      const stored: DraftParams = {
        angle_deg: -3.123456789,
        faces: { kind: "faces", refs: [faceSubshapeRef(BODY, FACE)] },
        neutral_plane: { kind: "datum", base: "XZ", offset_mm: B, flip: true },
      };
      const form = formFromDraftParams(stored, unit);
      expectUnchanged(buildDraftParams(form, [FACE], BODY, unit), stored);
    });

    it("base flange: gauge and bend radius", () => {
      const stored: SheetMetalBaseFlangeParams = {
        profile: { kind: "feature", feature_id: "sk" },
        thickness_mm: B,
        bend_radius_mm: A,
        k_factor: 0.4123456789,
        direction: "normal",
        merge: true,
      };
      const form = formFromBaseFlangeParams(stored, unit);
      expectUnchanged(buildBaseFlangeParams(form, unit), stored);
    });

    it("edge flange: length, width, offset and bend radius", () => {
      const stored: SheetMetalEdgeFlangeParams = {
        edge: edgeSubshapeRef(BODY, EDGE),
        flange_length_mm: A,
        bend_angle_deg: 87.123456789,
        width_mm: 20.123456789012,
        offset_mm: B,
        bend_radius_mm: B,
        k_factor: 0.4123456789,
      };
      const form = formFromEdgeFlangeParams(stored, unit);
      expectUnchanged(buildEdgeFlangeParams(form, [EDGE], BODY, unit), stored);
    });

    it("hem: length and bend radius", () => {
      const stored: SheetMetalHemParams = {
        edge: edgeSubshapeRef(BODY, EDGE),
        length_mm: B,
        hem_type: "open",
        bend_radius_mm: A,
        k_factor: 0.4123456789,
      };
      const form = formFromHemParams(stored, unit);
      expectUnchanged(buildHemParams(form, [EDGE], BODY, unit), stored);
    });

    it("corner relief: ratio and size", () => {
      const stored: SheetMetalCornerReliefParams = {
        bend_a: { kind: "feature", feature_id: "f1" },
        bend_b: { kind: "feature", feature_id: "f2" },
        relief_ratio: 1.123456789012,
        relief_type: "rectangular",
        size_mm: B,
      };
      const form = formFromCornerReliefParams(stored, unit);
      expectUnchanged(buildCornerReliefParams(form, unit), stored);
    });
  });
}
