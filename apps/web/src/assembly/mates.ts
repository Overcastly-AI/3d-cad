/**
 * Pure builders from collected picks → the discriminated `Mate` union the
 * gateway `MateCreate` carries. Kept out of the store + components so the
 * mate-shape logic unit-tests without a DOM. Every shape is from the generated
 * client (CLAUDE.md DRY rule); this only assembles refs the pick UI already
 * produced (the SAME signatures sketch-on-face / edge-pick emit).
 */
import { formatLength, type LengthUnit } from "@loft/design";

import type { Mate } from "../api/assemblies";
import type { MatePick, MateTool } from "./mateStore";

/** A short human label for a mate kind — the tree + readout share it. */
export function mateToolLabel(tool: MateTool): string {
  switch (tool) {
    case "coincident":
      return "Coincident";
    case "concentric":
      return "Concentric";
    case "lock":
      return "Lock";
    case "distance":
      return "Distance";
    case "angle":
      return "Angle";
  }
}

/**
 * Parse a user-typed parametric value (distance mm / angle degrees) → a finite
 * number, or null when the field is empty / not a number. Signed values are
 * valid: distance is a signed gap, angle a signed rotation (schema §2.3).
 */
export function parseMateValue(input: string): number | null {
  const trimmed = input.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

/** A human label for a stored mate (the tree row). */
export function mateLabel(mate: Mate): string {
  switch (mate.type) {
    case "coincident":
      return "Coincident";
    case "concentric":
      return "Concentric";
    case "lock":
      return "Lock";
    case "distance":
      return "Distance";
    case "angle":
      return "Angle";
  }
}

/**
 * THE MATE'S HANDLE — the tag the panel prints on its row and the ONLY name any
 * other surface may call it by.
 *
 * A component has a balloon number; a mate had nothing, so two Coincident mates
 * between the same pair of instances rendered as two identical rows reading
 * `Coincident · ①1 · ②2`. The solve diagnosis then said "Remove or relax mate
 * 4ae95465-…" and the user was pointed at an object with no visible identity —
 * a dead end with extra steps (MATEUI-1).
 *
 * The number is EARNED, not decoration (frontend-design §Structure): the solver
 * processes mates front-to-back in `(order_index, id)` order and reports
 * redundancy greedily in that same order, so "M2" is the position the solver
 * considered it in, which is information a reader of a redundancy diagnosis
 * actually needs. Components are circles (drafting balloons); mates are
 * squared tags, because a joint is not a part.
 */
export function mateTag(index: number): string {
  return `M${index + 1}`;
}

/** How a mate is identified everywhere outside its own row. */
export interface MateIdentity {
  /** The handle alone — `M2`. Enough on its own once the name is in context. */
  readonly tag: string;
  /** Handle plus kind — `M2 Coincident`. The full, unambiguous form. */
  readonly name: string;
}

/**
 * Every mate's panel-visible identity, keyed by id.
 *
 * ONE derivation, read by the tree (which prints the tag) and by the solve
 * diagnosis (which names the offenders). A second, parallel numbering is how
 * the message and the panel would drift apart again.
 */
export function mateNamesById(
  mates: readonly { readonly id: string; readonly mate: Mate }[],
): Map<string, MateIdentity> {
  return new Map(
    mates.map((row, index) => {
      const tag = mateTag(index);
      return [row.id, { tag, name: `${tag} ${mateLabel(row.mate)}` }];
    }),
  );
}

/**
 * The value echo for a parametric mate — the gap of a distance mate formatted
 * in the document `unit` (canonical mm → display), or the signed degrees of an
 * angle mate (angles are always degrees). `null` for non-parametric mates.
 */
export function mateDetail(mate: Mate, unit: LengthUnit): string | null {
  if (mate.type === "distance") return formatLength(mate.distance_mm, unit);
  if (mate.type === "angle") {
    const deg = Object.is(mate.angle_deg, -0) ? 0 : mate.angle_deg;
    return `${deg}°`;
  }
  return null;
}

/** The two instance ids a mate relates (for tree cross-highlight / cleanup). */
export function mateInstanceIds(mate: Mate): [string, string] {
  switch (mate.type) {
    case "coincident":
    case "distance":
    case "angle":
      return [mate.a.instance_id, mate.b.instance_id];
    case "concentric":
      return [mate.a.instance_id, mate.b.instance_id];
    case "lock":
      return [mate.a_instance_id, mate.b_instance_id];
  }
}

/**
 * Build the `Mate` from a complete pick pair for `tool`, or null when the pair
 * is incomplete / the wrong kind (a coincident, distance, or angle needs two
 * faces; a concentric two axes; a lock two instances — all on distinct
 * instances, the store's invariant). A parametric mate (distance / angle) also
 * needs its finite numeric `value` (mm / degrees); it is null until the user
 * supplies one. A coincident mates the two faces flush (mating faces touch).
 */
export function buildMate(
  tool: MateTool,
  picks: readonly MatePick[],
  value?: number | null,
): Mate | null {
  const [a, b] = picks;
  if (a === undefined || b === undefined) return null;
  if (a.instanceId === b.instanceId) return null;

  if (tool === "coincident") {
    if (a.kind !== "face" || b.kind !== "face") return null;
    return {
      type: "coincident",
      flush: true,
      a: { kind: "face", instance_id: a.instanceId, signature: a.signature },
      b: { kind: "face", instance_id: b.instanceId, signature: b.signature },
    };
  }
  if (tool === "distance") {
    if (a.kind !== "face" || b.kind !== "face") return null;
    if (value == null || !Number.isFinite(value)) return null;
    return {
      type: "distance",
      distance_mm: value,
      a: { kind: "face", instance_id: a.instanceId, signature: a.signature },
      b: { kind: "face", instance_id: b.instanceId, signature: b.signature },
    };
  }
  if (tool === "angle") {
    if (a.kind !== "face" || b.kind !== "face") return null;
    if (value == null || !Number.isFinite(value)) return null;
    return {
      type: "angle",
      angle_deg: value,
      a: { kind: "face", instance_id: a.instanceId, signature: a.signature },
      b: { kind: "face", instance_id: b.instanceId, signature: b.signature },
    };
  }
  if (tool === "concentric") {
    if (a.kind !== "axis" || b.kind !== "axis") return null;
    return {
      type: "concentric",
      a: { kind: "axis", instance_id: a.instanceId, signature: a.signature },
      b: { kind: "axis", instance_id: b.instanceId, signature: b.signature },
    };
  }
  // lock
  if (a.kind !== "instance" || b.kind !== "instance") return null;
  return {
    type: "lock",
    a_instance_id: a.instanceId,
    b_instance_id: b.instanceId,
  };
}
