/**
 * Face-pick view logic — the pure functions the "Pick a face" flow shares,
 * kept out of the components so they can be unit-tested without a DOM or a
 * WebGL context. Every shape comes from the generated client (CLAUDE.md DRY
 * rule); this module only assembles the request from an overlay face.
 *
 * A picked planar face becomes an `on_face` datum: its `OverlayFace.signature`
 * (the SAME stage-1 fingerprint the kernel resolver matches against) is echoed
 * into a `SubshapeRef`, exactly as a measurement vertex echoes its coordinates
 * into a `PointTarget` — one enumeration, pick side and resolve side
 * (docs/design/topological-naming.md §4). The `SubshapeRef.feature_id` anchors
 * the reference to the prior body-affecting feature whose body carries the face
 * (write-time dependency + strict-backward check).
 */
import type {
  DatumOnFaceParams,
  FeatureResponse,
  OverlayFace,
  PlanarFaceSignature,
  SubshapeRef,
} from "../api/parts";

/**
 * Feature types that produce/mutate the body chain — the acceptable anchor of a
 * face `SubshapeRef` (topo-naming §4). Mirrors the kernel's
 * `BODY_AFFECTING_FEATURE_TYPES`; `datum`/`sketch` are NOT body-affecting.
 */
export const BODY_AFFECTING_FEATURE_TYPES: ReadonlySet<string> = new Set([
  "extrude",
  "revolve",
  "sweep",
  "loft",
  "fillet",
  "chamfer",
  "shell",
  "pattern",
]);

/**
 * The id of the feature that produced the CURRENTLY rendered body — the last
 * non-rolled-back body-affecting feature in tree order. This is the anchor the
 * kernel signature-matches the picked face against (`state.body`), and the
 * strict-backward dependency the write records. Null when no body exists.
 */
export function lastBodyFeatureId(
  features: readonly FeatureResponse[],
): string | null {
  for (let i = features.length - 1; i >= 0; i -= 1) {
    const feature = features[i];
    if (feature === undefined) continue;
    if (
      !feature.rolled_back &&
      BODY_AFFECTING_FEATURE_TYPES.has(feature.feature.type)
    ) {
      return feature.id;
    }
  }
  return null;
}

/**
 * Build the stage-1 face reference from a planar overlay face's signature. The
 * signature is passed through UNCHANGED (full precision — §7.2 forbids
 * quantizing the stored identity) so the kernel resolver matches the SAME face.
 */
export function faceSubshapeRef(
  featureId: string,
  signature: PlanarFaceSignature,
): SubshapeRef {
  return {
    kind: "subshape",
    feature_id: featureId,
    subshape_type: "face",
    selector: { selector_version: 1, signature },
  };
}

/**
 * The `on_face` datum params for a picked face: the `SubshapeRef` plus a signed
 * offset along the face normal (0 sits on the face). The datum node a later
 * sketch seats on via its `FeatureRef` plane slot.
 */
export function onFaceDatumParams(
  featureId: string,
  signature: PlanarFaceSignature,
  offsetMm = 0,
): DatumOnFaceParams {
  return {
    kind: "on_face",
    face: faceSubshapeRef(featureId, signature),
    offset_mm: offsetMm,
  };
}

/** A planar overlay face carries a non-null signature; only these are pickable. */
export function isPickableFace(
  face: OverlayFace,
): face is OverlayFace & { signature: PlanarFaceSignature } {
  return face.planar && face.signature != null;
}

/** A short accessible name for a planar face from its centroid (shared by the
 * sketch-on-face and shell face overlays — one label grammar). */
export function faceLabel(
  index: number,
  signature: PlanarFaceSignature,
): string {
  const round = (n: number) => Math.round(n * 10) / 10;
  const { x, y, z } = signature.centroid;
  return `Planar face ${index + 1}, centred at ${round(x)}, ${round(y)}, ${round(z)} millimetres`;
}

/**
 * A stable string key for a full-precision planar-face signature — its identity
 * for set membership + toggling (the face twin of `edgeSignatureKey`). Two
 * DISTINCT faces of an authored part differ in at least one of (normal,
 * centroid, area), so the key collides only for genuinely identical faces —
 * exactly what a toggle should treat as the same pick.
 */
export function faceSignatureKey(signature: PlanarFaceSignature): string {
  const p = (v: { x: number; y: number; z: number }): string =>
    `${v.x},${v.y},${v.z}`;
  return [p(signature.normal), p(signature.centroid), signature.area_mm2].join(
    "|",
  );
}

/** True when a face signature is already in the picked (open) set, by identity. */
export function isFacePicked(
  picked: readonly PlanarFaceSignature[],
  signature: PlanarFaceSignature,
): boolean {
  const key = faceSignatureKey(signature);
  return picked.some((s) => faceSignatureKey(s) === key);
}

/**
 * Toggle a face into/out of the picked (open) set: a repeat click on a chosen
 * face removes it, a click on an unchosen face appends it (order preserved —
 * the set is a small authored list). The shell "faces to open" twin of
 * `toggleEdge`.
 */
export function toggleFace(
  picked: readonly PlanarFaceSignature[],
  signature: PlanarFaceSignature,
): PlanarFaceSignature[] {
  const key = faceSignatureKey(signature);
  return isFacePicked(picked, signature)
    ? picked.filter((s) => faceSignatureKey(s) !== key)
    : [...picked, signature];
}
