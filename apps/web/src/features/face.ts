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
 * face `SubshapeRef` (topo-naming §4). Mirrors the kernel's canonical
 * `BODY_AFFECTING_FEATURE_TYPES` (`py_kit.schemas.features`) exactly;
 * `datum`/`sketch` are NOT body-affecting. `import` produces the base body
 * (step-import.md §1) — so a later face/edge pick can anchor to an imported
 * part's geometry, and the import affordance disables once it exists.
 */
export const BODY_AFFECTING_FEATURE_TYPES: ReadonlySet<string> = new Set([
  "extrude",
  "revolve",
  "sweep",
  "loft",
  "fillet",
  "chamfer",
  "shell",
  "draft",
  // `hole` drills a cylinder into the body (a body-affecting modifier like
  // fillet/shell/draft), so its result faces/edges anchor a later SubshapeRef —
  // a datum on the new bore face, a hole near an earlier hole. Its ABSENCE would
  // make `lastBodyFeatureId` skip a just-drilled hole and mis-anchor the next
  // face/edge pick to the pre-hole body (subshape_unresolved / wrong dependency).
  "hole",
  "pattern",
  // `mirror` reflects the current body about a plane and boolean-unions the
  // reflection back in (a body-affecting modifier like pattern/boolean), so its
  // result faces/edges anchor a later SubshapeRef. Its ABSENCE would make
  // `lastBodyFeatureId` skip a just-created mirror and mis-anchor the next
  // face/edge pick to the pre-mirror body (subshape_unresolved / wrong dep).
  "mirror",
  "import",
  // Sheet metal: the base flange produces the sheet body; edge flange / hem /
  // corner relief each MODIFY it (sheet-metal.md §4, parity §2/§4.4) — all
  // anchor a later face/edge pick.
  "sheet_metal_base_flange",
  "sheet_metal_edge_flange",
  "sheet_metal_hem",
  "sheet_metal_corner_relief",
  // `boolean` produces a combined body (multi-body §Decisions-3), so its result
  // faces/edges are nameable by a later SubshapeRef (a fillet on a boolean seam).
  "boolean",
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

/**
 * The B-rep ORDINAL of the face a signature names — what a raycast reports, and
 * what `pickHiddenFaces` is keyed on — or null when the overlay lists no such
 * pickable face.
 *
 * Resolved by matching the signature the editor already holds rather than
 * carrying a second copy of the index, so the two can never drift.
 * `OverlayFace.index` IS the mesh's face ordinal (`glbGeometry.ts` — "group
 * ordinal === face ordinal === OverlayFace.index"), which is the identity
 * `FacePickOverlay` already relies on.
 *
 * Extracted from `HolePointOverlay` on the second real use (the overlay
 * resolves it to aim its free-placement raycast; the editor resolves it to ask
 * whether the placement body is switched off) — DRY rule, second use not first
 * imagined one.
 */
export function faceOrdinalOfSignature(
  signature: PlanarFaceSignature | null,
  faces: readonly OverlayFace[] | null,
): number | null {
  if (signature === null || faces === null) return null;
  const key = faceSignatureKey(signature);
  const match = faces.find(
    (face) => isPickableFace(face) && faceSignatureKey(face.signature) === key,
  );
  return match?.index ?? null;
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
