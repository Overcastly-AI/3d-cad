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
