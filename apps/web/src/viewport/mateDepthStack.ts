/**
 * THE SECTION AT THE CURSOR — every offered mate face the ray pierces, ordered
 * near → far, across instances.
 *
 * MATE-1. The defect this exists for is not "the highlight is hard to hit"; it
 * is that a mate-target face can be BURIED, and burial is the normal case
 * rather than the awkward one. A coincident mate joins two faces that will END
 * UP touching, and in the audit's fixture (S-15) they touch ALREADY: a bracket
 * seated on a plate has its bottom face and the plate's top face at the same
 * plane. Look from above and the bracket hides it; look from below and the
 * plate hides it. Measured on that fixture through the real UI — 528 pointer
 * samples per camera, four cameras — the bracket's bottom face was addressable
 * at zero of them. Orbiting is not the answer because there is no answer to
 * orbit to.
 *
 * SO THE PICK STOPS BEING "WHAT IS IN FRONT" AND BECOMES "WHICH OF THESE".
 * The ray under the cursor crosses a COLUMN of faces; this module names them,
 * in order, and the user chooses a depth. That is the incumbents' "select
 * other", and it is the only affordance that can reach geometry no camera
 * shows.
 *
 * IT ALSO CLOSES A WORSE, QUIETER DEFECT MEASURED ON THE WAY IN. Each instance
 * mounted its own pick surface with an `onPointerMove` that did NOT stop
 * propagation, while its `onClick` DID. r3f delivers a move to every struck
 * object near → far, so the LAST writer — the FARTHEST face — won the hover,
 * while the click, stopped at the first, took the NEAREST. They are opposite
 * ends of this same column. On the S-15 fixture at (668, 372) the viewport
 * highlighted the bracket's bottom face and the click committed the PLATE's
 * bottom face: a different face on a different part, silently. A pick that
 * mates the wrong face is worse than one that mates nothing, so hover and
 * commit now read the same entry of the same list — there is only one answer
 * to be had.
 *
 * Pure and node-testable on purpose (the `unit` vitest project, same precedent
 * as `pickRaycast.ts`): "which faces does the cursor address, in what order" is
 * exactly the decision a screenshot cannot check.
 */

/** A B-rep face the ray pierced, at the depth it pierced it. */
export interface MateCandidate {
  /** Which assembly instance owns the face. */
  instanceId: string;
  /** The B-rep face ordinal, in `OverlayFace.index` space. */
  faceIndex: number;
  /** Ray origin → entry point, in scene mm (near first). */
  distance: number;
}

/**
 * As much of an r3f intersection as the column reads.
 *
 * `index` is the FACE ORDINAL, stamped by `faceColumnRaycast` — the same field
 * r3f dedupes on, read back by the same pair, so the two cannot drift.
 */
export interface DepthHit {
  index?: number | undefined;
  distance: number;
  object: { userData?: { pickId?: unknown } | undefined };
}

/** Is this instance/face pair actually on offer for the armed tool? */
export type OfferTest = (instanceId: string, faceIndex: number) => boolean;

/**
 * The column of offered faces under the cursor, near → far.
 *
 * Hits with no `pickId` are not pick surfaces at all (the balloon `Html`, an
 * instance body's own select handler) and are skipped rather than treated as
 * anonymous geometry — a candidate nobody can name is a dead entry in a list
 * whose whole job is to be chosen from.
 *
 * A repeated (instance, face) pair is dropped, keeping the NEAREST occurrence:
 * one face is one candidate no matter how many times the ray re-enters its
 * tessellation. The input is assumed near-first (r3f sorts by distance before
 * dispatch) and is sorted again anyway — it costs nothing at these lengths and
 * it makes the ordering a property of this function rather than of its caller.
 */
export function mateDepthStack(
  hits: readonly DepthHit[],
  isOffered: OfferTest,
): MateCandidate[] {
  const ordered = [...hits].sort((a, b) => a.distance - b.distance);
  const seen = new Set<string>();
  const column: MateCandidate[] = [];
  for (const hit of ordered) {
    const pickId = hit.object.userData?.pickId;
    if (typeof pickId !== "string") continue;
    const faceIndex = hit.index;
    if (typeof faceIndex !== "number") continue;
    if (!isOffered(pickId, faceIndex)) continue;
    const key = `${pickId}:${faceIndex}`;
    if (seen.has(key)) continue;
    seen.add(key);
    column.push({ instanceId: pickId, faceIndex, distance: hit.distance });
  }
  return column;
}

/**
 * A stable identity for a column — what changed, ignoring how far away it is.
 *
 * Pointer moves fire continuously and each one re-derives the column, so
 * without this every mouse micro-move would replace the state object, reset the
 * chosen depth, and make the deeper entry impossible to click. Distances are
 * deliberately NOT part of the key: sliding the cursor along one face changes
 * them every frame while the choice on offer is identical.
 */
export function columnKey(column: readonly MateCandidate[]): string {
  return column.map((c) => `${c.instanceId}:${c.faceIndex}`).join("|");
}

/**
 * The chosen depth, clamped into a column that may have shrunk.
 *
 * Returns 0 for an empty column so callers never index a hole; the caller
 * decides whether an empty column means "nothing addressed".
 */
export function clampDepth(
  depth: number,
  column: readonly MateCandidate[],
): number {
  if (column.length === 0) return 0;
  return Math.min(Math.max(depth, 0), column.length - 1);
}
