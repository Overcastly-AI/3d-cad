/**
 * Pure builders from collected picks → the discriminated `Mate` union the
 * gateway `MateCreate` carries. Kept out of the store + components so the
 * mate-shape logic unit-tests without a DOM. Every shape is from the generated
 * client (CLAUDE.md DRY rule); this only assembles refs the pick UI already
 * produced (the SAME signatures sketch-on-face / edge-pick emit).
 */
import type { Mate } from "../api/assemblies";
import type { MatePick, MateTool } from "./mateStore";

/** A short human label for a mate kind — the tree + readout share it. */
export function mateToolLabel(tool: MateTool): string {
  return tool === "coincident"
    ? "Coincident"
    : tool === "concentric"
      ? "Concentric"
      : "Lock";
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
 * is incomplete / the wrong kind (a coincident needs two faces, a concentric
 * two axes, a lock two instances — all on distinct instances, the store's
 * invariant). A coincident mates the two faces flush (mating faces touch).
 */
export function buildMate(
  tool: MateTool,
  picks: readonly MatePick[],
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
