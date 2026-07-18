/**
 * Click-specific edge selection view logic — the pure functions the Fillet /
 * Chamfer "Pick edges" flow shares, kept out of the components + store so they
 * unit-test without a DOM or a WebGL context (the face-pick sibling; see
 * `./face.ts`). Every shape comes from the generated client (CLAUDE.md DRY
 * rule); this module only assembles the request from picked overlay edges.
 *
 * A picked edge becomes an `EdgeSubshapeRef`: its `OverlayEdge.signature` — the
 * SAME stage-1 fingerprint the kernel resolver matches against — is echoed
 * through UNCHANGED (full precision; §7.2 forbids quantizing the stored
 * identity), exactly as a picked face echoes its `PlanarFaceSignature`. The
 * `feature_id` anchors the reference to the prior body-affecting feature whose
 * body carries the edge (the `lastBodyFeatureId` re-exported from `./face`).
 */
import type {
  EdgeSelector,
  EdgeSignature,
  EdgeSubshapeRef,
} from "../api/parts";

/**
 * Build the stage-1 edge reference from a picked edge's signature. The
 * signature passes through UNCHANGED so the kernel resolver matches the SAME
 * edge (the edge twin of `faceSubshapeRef`).
 */
export function edgeSubshapeRef(
  featureId: string,
  signature: EdgeSignature,
): EdgeSubshapeRef {
  return {
    kind: "subshape",
    feature_id: featureId,
    subshape_type: "edge",
    selector: { selector_version: 1, signature },
  };
}

/**
 * The `{kind:"edges"}` picked-edge selector from the anchor feature + the
 * chosen signatures, or null when there is no body anchor or nothing picked
 * (the backend rejects an empty ref list — a picked-edge fillet with zero
 * edges is never submitted).
 */
export function pickedEdgesSelector(
  featureId: string | null,
  signatures: readonly EdgeSignature[],
): EdgeSelector | null {
  if (featureId === null || signatures.length === 0) return null;
  return {
    kind: "edges",
    refs: signatures.map((signature) => edgeSubshapeRef(featureId, signature)),
  };
}

/**
 * A stable string key for a full-precision edge signature — its identity for
 * set membership + toggling. Two DISTINCT edges of an authored part differ in
 * at least one field (curve family, an endpoint/midpoint, or length), so the
 * key collides only for genuinely identical edges (which is exactly what a
 * toggle should treat as the same pick).
 */
export function edgeSignatureKey(signature: EdgeSignature): string {
  const p = (v: { x: number; y: number; z: number }): string =>
    `${v.x},${v.y},${v.z}`;
  return [
    signature.curve,
    p(signature.end_a),
    p(signature.end_b),
    p(signature.midpoint),
    signature.length_mm,
  ].join("|");
}

/** True when a signature is already in the picked set (by identity key). */
export function isEdgePicked(
  picked: readonly EdgeSignature[],
  signature: EdgeSignature,
): boolean {
  const key = edgeSignatureKey(signature);
  return picked.some((s) => edgeSignatureKey(s) === key);
}

/**
 * Toggle an edge into/out of the picked set: a repeat click on a selected edge
 * removes it, a click on an unselected edge appends it (order preserved — the
 * set is a small authored list, not a hot path).
 */
export function toggleEdge(
  picked: readonly EdgeSignature[],
  signature: EdgeSignature,
): EdgeSignature[] {
  const key = edgeSignatureKey(signature);
  return isEdgePicked(picked, signature)
    ? picked.filter((s) => edgeSignatureKey(s) !== key)
    : [...picked, signature];
}
