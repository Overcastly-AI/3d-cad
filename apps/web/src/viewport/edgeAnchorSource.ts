/**
 * WHERE THE FILLET / CHAMFER ANCHORS COME FROM TODAY (CRAFT-9a).
 *
 * This is deliberately a SEPARATE module from the gauges it feeds, and the
 * separation is the whole point. Direction §11 puts a persistent selection
 * store (CRAFT-12, W4) ahead of us; when it lands, every verb's anchor comes
 * from there instead of from the verb's own pick session. A gauge that READS
 * the pick store would have to be rewritten then. A gauge that takes its anchor
 * as a PROP is re-wired by changing this one file — which is what this file is
 * for.
 *
 * So: `FilletGauge` and `ChamferGauge` know nothing about `edgePickStore`, and
 * this hook knows nothing about r3f.
 *
 * ## The frame conversion happens exactly here
 *
 * The overlay speaks OCCT world-mm (Z-up); the scene is Y-up. `occtToScene` is
 * the one rotation in the app and it is a proper rotation, so it carries FACE
 * NORMALS as faithfully as it carries points — which is why the normals are put
 * through it rather than re-derived on the other side.
 */
import { useMemo } from "react";

import type { OverlayResult, Vec3 as OcctVec3 } from "../api/measure";
import type { EdgeSignature } from "../api/parts";
import { edgeSignatureKey } from "../features/edge";
import { useEdgePickStore } from "../features/edgePickStore";
import { occtToScene } from "../measure/geometry";
import { edgeAnchor, type EdgeAnchor, type EdgeFacePlane } from "./edgeAnchor";

/** The body's planar faces as bare planes, scene frame. */
function scenePlanes(overlay: OverlayResult): EdgeFacePlane[] {
  const planes: EdgeFacePlane[] = [];
  for (const face of overlay.faces) {
    const signature = face.signature;
    if (signature == null) continue; // non-planar: no normal to stand on.
    planes.push({
      normal: occtToScene(signature.normal),
      centroid: occtToScene(signature.centroid),
    });
  }
  return planes;
}

/**
 * Seat one anchor per picked edge, newest LAST.
 *
 * Edges the overlay no longer carries (a pick that survived a rebuild but whose
 * body changed) and edges whose adjacent faces cannot be identified are simply
 * absent from the result — see {@link edgeAnchor}, which refuses rather than
 * guesses. The caller mounts a gauge only if there is something to mount it on.
 */
export function seatEdgeAnchors(
  overlay: OverlayResult | null,
  picked: readonly EdgeSignature[],
): EdgeAnchor[] {
  if (overlay === null || picked.length === 0) return [];
  const planes = scenePlanes(overlay);
  const byKey = new Map<string, (typeof overlay.edges)[number]>();
  for (const edge of overlay.edges) {
    byKey.set(edgeSignatureKey(edge.signature), edge);
  }
  const anchors: EdgeAnchor[] = [];
  for (const signature of picked) {
    const key = edgeSignatureKey(signature);
    const edge = byKey.get(key);
    if (edge === undefined) continue;
    const seated = edgeAnchor(
      {
        key,
        polyline: edge.polyline.map((p: OcctVec3) => occtToScene(p)),
        midpoint: occtToScene(signature.midpoint),
        lengthMm: signature.length_mm,
      },
      planes,
    );
    if (seated !== null) anchors.push(seated);
  }
  return anchors;
}

/**
 * The picked edges of the open fillet/chamfer session, seated.
 *
 * Memoised on the two store slices it reads: the anchors are the input to a
 * `linearTrack`, and a track rebuilt every render would rebuild the gauge's
 * drawn geometry and its stop set every frame of a drag — the render-loop
 * allocation the viewport rules forbid, and the reason `ExtrudeDragHandle`
 * memoises its own.
 */
export function useEdgeGaugeAnchors(): EdgeAnchor[] {
  const overlay = useEdgePickStore((s) => s.overlay);
  const picked = useEdgePickStore((s) => s.picked);
  return useMemo(() => seatEdgeAnchors(overlay, picked), [overlay, picked]);
}
