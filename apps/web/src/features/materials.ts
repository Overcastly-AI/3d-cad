/**
 * Material view logic — the pure functions the mass surface shares, kept out of
 * the components so they can be unit-tested without a DOM (the `features/*`
 * convention).
 *
 * The one rule this module exists to hold: **absence is a state, not a zero**
 * (docs/design/materials.md §1.2/§6). `properties.mass_g` is null whenever ANY
 * contributing body has no material, so "no mass" has two very different
 * meanings a surface must tell apart — nobody has assigned anything at all, or
 * SOME bodies have a material and one specific body does not. The second case
 * has a name attached to it (`BodyLumpInfo.material`/`.mass_g`), and going
 * quiet when we know the name is the confidently-vague half of the same defect
 * class as claiming a mass we never computed.
 *
 * Resolution (an override wins over the document default) is NOT re-derived
 * here: the server resolves it once (`resolve_body_material`) and reports the
 * outcome per body, so this module only JOINS that outcome to the body names
 * the tree already gave us.
 */
import type {
  BodyLumpInfo,
  MaterialAssignment,
  MaterialKey,
} from "../api/materials";
import type { BodyInfo } from "./bodies";

/** One body's material row: what it is made of, what it weighs, and its name. */
export interface BodyMaterialRow {
  /** The body's identity — its §MB-0 base (creating) feature id. */
  readonly baseFeatureId: string;
  /** The base feature's name, as the tree shows it ("Extrude1"). */
  readonly name: string;
  /** 1-based order among bodies — the "Body N" label. */
  readonly ordinal: number;
  /** The material the SERVER resolved for this body; null = none assigned. */
  readonly material: MaterialKey | null;
  /** This body's mass (g), or null when it has no material. */
  readonly massG: number | null;
  /** This body carries its OWN override (so the document default is bypassed). */
  readonly override: MaterialKey | null;
  /**
   * The current evaluation reported on this body. A body the tree produces but
   * the last evaluation does not mention (a tree edited since, a rolled-back
   * body) is NOT evidence of a missing material, so it is never named as one.
   */
  readonly evaluated: boolean;
}

/** The override this assignment holds for one body, or null. */
export function overrideFor(
  assignment: MaterialAssignment | null | undefined,
  baseFeatureId: string,
): MaterialKey | null {
  const entry = (assignment?.bodies ?? []).find(
    (b) => b.base_feature_id === baseFeatureId,
  );
  return entry?.material ?? null;
}

/**
 * The part's bodies as material rows, in tree order: the tree's names/ordinals
 * joined to the evaluation's resolved material + mass for the same body id.
 */
export function bodyMaterialRows(
  bodies: readonly BodyInfo[],
  lumps: readonly BodyLumpInfo[],
  assignment: MaterialAssignment | null | undefined,
): BodyMaterialRow[] {
  const byId = new Map(lumps.map((l) => [l.base_feature_id, l]));
  return bodies.map((body) => {
    const lump = byId.get(body.baseFeatureId);
    return {
      baseFeatureId: body.baseFeatureId,
      name: body.name,
      ordinal: body.ordinal,
      material: lump?.material ?? null,
      massG: lump?.mass_g ?? null,
      override: overrideFor(assignment, body.baseFeatureId),
      evaluated: lump !== undefined,
    };
  });
}

/** Evaluated bodies the part could not weigh, in tree order. */
export function unassignedBodies(
  rows: readonly BodyMaterialRow[],
): BodyMaterialRow[] {
  return rows.filter((row) => row.evaluated && row.material === null);
}

/**
 * WHY there is no total mass, naming the bodies responsible — the sentence the
 * panel shows instead of "unknown". Null when every evaluated body has a
 * material (nothing to explain).
 */
export function unassignedNotice(
  rows: readonly BodyMaterialRow[],
): string | null {
  const missing = unassignedBodies(rows);
  if (missing.length === 0) return null;
  const names = missing.map((row) => row.name);
  const listed = names.length > 3 ? names.slice(0, 3) : names;
  const rest = names.length - listed.length;
  const list =
    listed.length === 1
      ? listed[0]
      : `${listed.slice(0, -1).join(", ")} and ${listed[listed.length - 1]}`;
  const tail = rest > 0 ? `${list} (+${rest} more)` : list;
  const verb = names.length === 1 ? "has" : "have";
  return `${tail} ${verb} no material, so the part has no total mass.`;
}

/**
 * What the surface is entitled to say about mass.
 *
 * - `known` — every contributing body has a material; the mass is real.
 * - `partial` — some bodies are assigned and at least one is not; the missing
 *   ones are named (a partial sum would under-report while looking complete).
 * - `unassigned` — nothing has been assigned; the panel is Volume/Area/Centroid
 *   and offers the picker. It must NOT be titled "mass properties" (§6.1).
 */
export type MassState =
  | { readonly kind: "known"; readonly massG: number }
  | { readonly kind: "partial"; readonly missing: readonly BodyMaterialRow[] }
  | { readonly kind: "unassigned" };

/** Classify a part's mass from the wire value + the per-body rows. */
export function massState(
  massG: number | null | undefined,
  rows: readonly BodyMaterialRow[],
): MassState {
  if (massG !== null && massG !== undefined) return { kind: "known", massG };
  const missing = unassignedBodies(rows);
  const assigned = rows.some((row) => row.evaluated && row.material !== null);
  if (missing.length > 0 && assigned) return { kind: "partial", missing };
  return { kind: "unassigned" };
}

/**
 * The panel's eyebrow. A title is a CLAIM: "mass properties" over a panel with
 * no mass in it is the overstated surface this whole slice exists to remove, so
 * the words are earned by the presence of a mass, never by the presence of a
 * mass FIELD.
 */
export function propertiesEyebrow(state: MassState): string {
  return state.kind === "known" ? "Mass properties" : "Properties";
}

/** The assignment with a new document default (null clears it). */
export function withDefaultMaterial(
  assignment: MaterialAssignment | null | undefined,
  material: MaterialKey | null,
): MaterialAssignment {
  return {
    default_material: material,
    bodies: [...(assignment?.bodies ?? [])],
  };
}

/**
 * The assignment with one body's override set (null removes it, falling back to
 * the document default). Duplicates are impossible by construction — the
 * boundary REJECTS them, because a body's mass must not depend on array order
 * (design §2, RESEARCH §9).
 */
export function withBodyMaterial(
  assignment: MaterialAssignment | null | undefined,
  baseFeatureId: string,
  material: MaterialKey | null,
): MaterialAssignment {
  const bodies = (assignment?.bodies ?? []).filter(
    (b) => b.base_feature_id !== baseFeatureId,
  );
  if (material !== null) {
    bodies.push({ base_feature_id: baseFeatureId, material });
  }
  return { default_material: assignment?.default_material ?? null, bodies };
}

/** True when the part has no material anywhere — the honest empty state. */
export function isUnassigned(
  assignment: MaterialAssignment | null | undefined,
): boolean {
  return (
    (assignment?.default_material ?? null) === null &&
    (assignment?.bodies ?? []).length === 0
  );
}

/**
 * The ONE material in play, or null when there is none or several. The density
 * readout hangs off this: quoting "2700 kg/m³" over a part whose second body is
 * steel would be a true number making a false claim, so a mixed part shows the
 * densities on the per-body rows instead of one headline figure.
 */
export function soleMaterial(
  assignment: MaterialAssignment | null | undefined,
  rows: readonly BodyMaterialRow[],
): MaterialKey | null {
  const resolved = rows
    .filter((row) => row.evaluated)
    .map((row) => row.material);
  const first = resolved[0];
  if (first !== undefined) {
    return new Set(resolved).size === 1 ? first : null;
  }
  // Nothing evaluated yet — the default speaks for the whole part iff no body
  // overrides it.
  return (assignment?.bodies ?? []).length === 0
    ? (assignment?.default_material ?? null)
    : null;
}

/** The library entry for a key, by name — never a density typed client-side. */
export function materialName(
  library: readonly { key: MaterialKey; name: string }[],
  key: MaterialKey | null,
): string | null {
  if (key === null) return null;
  return library.find((m) => m.key === key)?.name ?? key;
}
