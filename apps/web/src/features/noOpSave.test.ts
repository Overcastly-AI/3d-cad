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
  FeatureResponse,
  FilletParams,
  HoleParams,
  LoftParams,
  PatternParams,
  PlanarFaceSignature,
  RevolveParams,
  SheetMetalBaseFlangeParams,
  SheetMetalCornerReliefParams,
  SheetMetalEdgeFlangeParams,
  SheetMetalHemParams,
  ShellParams,
  SweepParams,
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
import { buildLoftParams, formFromLoftParams } from "./loft";
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
import { buildSweepParams, formFromSweepParams } from "./sweep";
import { readRepoSource } from "../test/wireSource";

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

// --- OPTIONAL KEYS (BASEFLANGE-NOOP-SAVE-KEYS-1) ------------------------------
//
// WHAT CAN AND CANNOT CHANGE A STORED ROW. The documents service validates
// every write and stores `model_dump`, and it re-validates on read. So a row
// always reaches the editor with every optional key present: filled with its
// default, or null. Whatever the editor sends back is filled the same way
// before it is stored. Measured on the running stack: a base flange POSTed
// without `merge`, `direction` and `k_factor` is stored and served with all
// three. So an editor that leaves a default-valued key OUT changes nothing,
// and one that puts it back changes nothing either. The server erases both.
//
// What the server cannot erase is a VALUE the editor did not keep. The base
// flange editor wrote `merge: true` whatever the row said. A flange stored
// with `merge: false` (a second sheet body) was re-saved as merged into the
// first, so the part lost a body on a Save that changed nothing. The edge
// flange dropped a stored `offset_mm: 0`, which the server then stored as
// null. So the check below compares both sides AFTER the server's own
// normalisation, and every fixture sets every optional key it can to a
// NON-default value. A census derived from the contract, not from the
// editors, fails by name if a fixture leaves one at its default.

/** A JSON-Schema node, as much of one as these checks read. */
interface SchemaNode {
  $ref?: string;
  type?: string;
  properties?: Record<string, SchemaNode>;
  required?: string[];
  default?: unknown;
  const?: unknown;
  enum?: unknown[];
  anyOf?: SchemaNode[];
  oneOf?: SchemaNode[];
  discriminator?: { propertyName: string; mapping?: Record<string, string> };
}

let schemas: Record<string, SchemaNode> | null = null;

/** The documents service's wire schemas, read lazily (see `readRepoSource`). */
function wireSchemas(): Record<string, SchemaNode> {
  schemas ??= (
    JSON.parse(
      readRepoSource("packages/contracts/documents.openapi.json", {
        declaredIn: "wireSchemas in apps/web/src/features/noOpSave.test.ts",
        guards: "which param keys are optional, and their defaults",
      }),
    ) as { components: { schemas: Record<string, SchemaNode> } }
  ).components.schemas;
  return schemas;
}

function deref(node: SchemaNode): SchemaNode {
  if (node.$ref === undefined) return node;
  const name = node.$ref.replace("#/components/schemas/", "");
  const target = wireSchemas()[name];
  if (target === undefined) throw new Error(`no schema ${name}`);
  return deref(target);
}

/** The object schema for `row` under `schema` ("Name" or "Name.property"). */
function objectSchema(
  schema: string,
  row: Record<string, unknown>,
): SchemaNode {
  const [name, property] = schema.split(".") as [string, string | undefined];
  let node = wireSchemas()[name];
  if (node !== undefined && property !== undefined) {
    node = deref(node).properties?.[property];
  }
  if (node === undefined) throw new Error(`no schema ${schema}`);
  const resolved = deref(node);
  const disc = resolved.discriminator;
  if (disc?.mapping !== undefined) {
    const ref = disc.mapping[String(row[disc.propertyName])];
    if (ref === undefined) throw new Error(`${schema}: no branch for the row`);
    return deref({ $ref: ref });
  }
  if (resolved.properties === undefined) {
    throw new Error(`${schema}: not an object schema`);
  }
  return resolved;
}

/** An optional key that can hold more than one value (so it CAN be dropped). */
function isChoice(prop: SchemaNode): boolean {
  const p = deref(prop);
  if (p.const !== undefined) return false;
  return !(p.enum !== undefined && p.enum.length === 1);
}

/** The row as the server stores it: absent optional keys filled. */
function serverSide(
  row: Record<string, unknown>,
  node: SchemaNode,
): Record<string, unknown> {
  const out: Record<string, unknown> = { ...row };
  for (const [key, prop] of Object.entries(node.properties ?? {})) {
    if (key in out || (node.required ?? []).includes(key)) continue;
    out[key] = "default" in prop ? prop.default : null;
  }
  return out;
}

/**
 * A no-op Save keeps every OPTIONAL key's value. `stored` must set each
 * optional key that can hold more than one value to something other than its
 * default (the census); the saved row, filled the way the server fills it,
 * must then equal the stored row filled the same way.
 */
function expectOptionalKeysKept<T extends object>(
  stored: T,
  schema: string,
  save: (row: T) => unknown,
): void {
  const row = stored as Record<string, unknown>;
  const node = objectSchema(schema, row);
  for (const [key, prop] of Object.entries(node.properties ?? {})) {
    if ((node.required ?? []).includes(key) || !isChoice(prop)) continue;
    const at = row[key];
    expect(
      at !== undefined &&
        at !== null &&
        canonical(at) !== canonical(deref(prop).default),
      `${schema}.${key}: the fixture must set this optional key to a ` +
        "non-default value, or a Save that drops it cannot be caught",
    ).toBe(true);
  }
  const saved = save(stored);
  expect(saved).not.toBeNull();
  expect(canonical(serverSide(saved as Record<string, unknown>, node))).toBe(
    canonical(serverSide(row, node)),
  );
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

for (const unit of UNITS) {
  describe(`a no-op Save keeps every optional key's value (${unit} document)`, () => {
    it("extrude: direction and merge", () => {
      const stored: ExtrudeParams = {
        profile: { kind: "feature", feature_id: "sk" },
        distance_mm: A,
        operation: "add",
        direction: "reverse",
        merge: false,
        twist_angle_deg: 30,
        twist_center: { x: 1, y: 2 },
      };
      expectOptionalKeysKept(stored, "ExtrudeParamsV1", (row) => {
        const form = formFromParams(row, unit);
        return extrudeParamsFromForm(
          form,
          extrudeDistanceMm(form, unit) as number,
        );
      });
    });

    it("revolve: angle, direction and merge", () => {
      const stored: RevolveParams = {
        profile: { kind: "feature", feature_id: "sk" },
        axis: { kind: "origin_axis", axis: "Z" },
        angle_deg: 123.456789012345,
        operation: "add",
        direction: "reverse",
        merge: false,
      };
      expectOptionalKeysKept(stored, "RevolveParamsV1", (row) =>
        revolveParamsFromForm(formFromRevolveParams(row), row.axis),
      );
    });

    it("sweep and loft: merge", () => {
      const sweep: SweepParams = {
        profile: { kind: "feature", feature_id: "sk" },
        path: { kind: "feature", feature_id: "path" },
        operation: "add",
        merge: false,
      };
      expectOptionalKeysKept(sweep, "SweepParamsV1", (row) =>
        buildSweepParams(formFromSweepParams(row)),
      );
      const loft: LoftParams = {
        profiles: [
          { kind: "feature", feature_id: "s1" },
          { kind: "feature", feature_id: "s2" },
        ],
        operation: "add",
        merge: false,
      };
      expectOptionalKeysKept(loft, "LoftParamsV1", (row) =>
        buildLoftParams(formFromLoftParams(row)),
      );
    });

    it("hole: type and thread", () => {
      const stored: HoleParams = {
        face: faceSubshapeRef(BODY, FACE),
        position: { x: 1, y: 2, z: 20 },
        diameter_mm: 8.5,
        depth: { kind: "through_all" },
        type: { kind: "counterbore", cbore_diameter_mm: 16, cbore_depth_mm: 6 },
        thread: {
          standard: "iso_metric",
          nominal_diameter_mm: 10,
          pitch_mm: 1.5,
        },
      };
      expectOptionalKeysKept(stored, "HoleParamsV1", (row) =>
        buildHoleParams(formFromHoleParams(row, unit), unit),
      );
    });

    it("pattern: a features scope", () => {
      const stored: PatternParams = {
        pattern: {
          kind: "linear",
          direction: { x: 1, y: 0, z: 0 },
          spacing_mm: B,
          count: 4,
        },
        scope: {
          kind: "features",
          features: [{ kind: "feature", feature_id: "x1" }],
        },
      };
      // The editor names a scope's features from the tree it is handed.
      const tree = [
        {
          id: "x1",
          name: "Extrude2",
          part_id: "p",
          order_index: 1,
          created_at: "2026-09-25T00:00:00Z",
          updated_at: "2026-09-25T00:00:00Z",
          rolled_back: false,
          feature: {
            type: "extrude",
            version: 1,
            params: {
              profile: { kind: "feature", feature_id: "sk" },
              distance_mm: 5,
              operation: "cut",
            },
          },
        } as FeatureResponse,
      ];
      expectOptionalKeysKept(stored, "PatternParamsV1", (row) =>
        buildPatternParams(formFromPatternParams(row, unit, tree), unit),
      );
    });

    it("datum: flip, and an on-face offset", () => {
      const save = (row: DatumParams) =>
        buildDatumParams(formFromDatumParams(row, unit), unit);
      const cases: DatumParams[] = [
        { kind: "offset", base: "XY", offset_mm: -B, flip: true },
        {
          kind: "offset_from",
          base: { kind: "feature", feature_id: "d1" },
          offset_mm: A,
          flip: true,
        },
        onFaceDatumParams(BODY, FACE, B),
        {
          kind: "midplane",
          a: { kind: "datum_plane", plane: "XY" },
          b: { kind: "feature", feature_id: "d1" },
          flip: true,
        },
      ];
      for (const stored of cases) {
        expectOptionalKeysKept(stored, "DatumFeature.params", save);
      }
    });

    it("draft: the neutral plane's flip and offset", () => {
      const stored: DraftParams = {
        angle_deg: -3.123456789,
        faces: { kind: "faces", refs: [faceSubshapeRef(BODY, FACE)] },
        neutral_plane: { kind: "datum", base: "XZ", offset_mm: B, flip: true },
      };
      const save = (row: DraftParams) =>
        buildDraftParams(formFromDraftParams(row, unit), [FACE], BODY, unit);
      expectOptionalKeysKept(
        stored.neutral_plane,
        "DraftNeutralPlaneV1",
        (plane) => save({ ...stored, neutral_plane: plane })?.neutral_plane,
      );
    });

    it("base flange: k-factor, direction and merge", () => {
      // The reported case. `merge: false` is a SECOND sheet body; the editor
      // wrote `merge: true` whatever the row said.
      const stored: SheetMetalBaseFlangeParams = {
        profile: { kind: "feature", feature_id: "sk" },
        thickness_mm: B,
        bend_radius_mm: A,
        k_factor: 0.4123456789,
        direction: "reverse",
        merge: false,
      };
      expectOptionalKeysKept(stored, "SheetMetalBaseFlangeParamsV1", (row) =>
        buildBaseFlangeParams(formFromBaseFlangeParams(row, unit), unit),
      );
    });

    it("edge flange: width, offset, bend radius and k-factor", () => {
      const stored: SheetMetalEdgeFlangeParams = {
        edge: edgeSubshapeRef(BODY, EDGE),
        flange_length_mm: A,
        bend_angle_deg: 90,
        width_mm: 20,
        offset_mm: B,
        bend_radius_mm: B,
        k_factor: 0.4123456789,
      };
      const save = (row: SheetMetalEdgeFlangeParams) =>
        buildEdgeFlangeParams(
          formFromEdgeFlangeParams(row, unit),
          [EDGE],
          BODY,
          unit,
        );
      expectOptionalKeysKept(stored, "SheetMetalEdgeFlangeParamsV1", save);
      // A stored 0 offset is a value too: dropping it stores null.
      const atZero = { ...stored, offset_mm: 0 };
      expectUnchanged(save(atZero), atZero);
    });

    it("hem: type, bend radius and k-factor", () => {
      const stored: SheetMetalHemParams = {
        edge: edgeSubshapeRef(BODY, EDGE),
        length_mm: B,
        hem_type: "open",
        bend_radius_mm: A,
        k_factor: 0.4123456789,
      };
      expectOptionalKeysKept(stored, "SheetMetalHemParamsV1", (row) =>
        buildHemParams(formFromHemParams(row, unit), [EDGE], BODY, unit),
      );
    });

    it("corner relief: ratio and size", () => {
      const stored: SheetMetalCornerReliefParams = {
        bend_a: { kind: "feature", feature_id: "f1" },
        bend_b: { kind: "feature", feature_id: "f2" },
        relief_ratio: 1.123456789012,
        relief_type: "rectangular",
        size_mm: B,
      };
      expectOptionalKeysKept(stored, "SheetMetalCornerReliefParamsV1", (row) =>
        buildCornerReliefParams(formFromCornerReliefParams(row, unit), unit),
      );
    });
  });
}
