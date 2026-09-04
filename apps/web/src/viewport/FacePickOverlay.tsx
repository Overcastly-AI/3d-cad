/**
 * The face-pick overlay inside the WebGL viewport — the "Pick a face" step of
 * the sketch plane picker. The DRAWN SURFACE is the hit-test (`PickSurface`,
 * SEL-1 A2): a raycast resolves the struck triangle back to its B-rep face
 * ordinal, so clicking anywhere on the face picks the face. Every PLANAR face
 * also carries a DOM-in-canvas `PickNode` (drei `Html`) at its area centroid,
 * which is now the keyboard focus target, the screen-reader name and the touch
 * tap target rather than the way you aim. Non-planar faces carry no signature
 * and are NOT pickable in v1 — they are omitted, never a dead target. So are
 * the faces of a SWITCHED-OFF body (`hiddenPicks.ts`).
 *
 * "Omitted, never a dead target" was true PER FACE and false for the overlay as
 * a whole (PICK-2). When the tip feature builds no body the parent's overlay
 * query is disabled, `faces` arrives null, and this renders NOTHING — no
 * `PickSurface`, no `PickNode` — so the entire viewport became the dead target
 * the per-face rule forbids, and said nothing about it. That case is now
 * refused BEFORE a pick is armed (`./pickTargets`), which is what makes the
 * guarantee hold for the surface and not only for its parts: a mode that could
 * only ever offer zero faces is not entered.
 *
 * The pick reads as TOPOLOGY, not a blanket of floating squares (UI audit
 * #19a): the face under the cursor (hovered) — or the one currently armed —
 * also gets a translucent brass patch laid ON its plane (`FacePatch`), so the
 * highlight is the real surface, cursor-driven. Every color/opacity comes from
 * `@loft/design` tokens.
 *
 * A clicked face echoes its stage-1 `signature` into an `on_face` datum (the
 * parent owns that write + the sketch seating); this layer is presentational.
 */
import { PickNode } from "@loft/design";
import { useThree } from "@react-three/fiber";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { OverlayFace, PlanarFaceSignature } from "../api/parts";
import { faceLabel, isPickableFace } from "../features/face";
import { occtToScene } from "../measure/geometry";
import { FacePatch } from "./facePatch";
import { useHiddenPicks } from "./hiddenPicks";
import { PickMark } from "./PickMark";
import { PickSurface } from "./pickSurface";
import { useViewportPickStamp } from "./pickStamp";

export interface FacePickOverlayProps {
  /** The evaluated body's faces (from `OverlayResult.faces`), or null. */
  faces: readonly OverlayFace[] | null;
  /** Author an `on_face` datum from the picked face and seat the sketch. */
  onPick: (face: OverlayFace & { signature: PlanarFaceSignature }) => void;
  /** The `body.faces()` index currently being authored (brass-fill busy cue). */
  pendingIndex: number | null;
}

export function FacePickOverlay({
  faces,
  onPick,
  pendingIndex,
}: FacePickOverlayProps) {
  const invalidate = useThree((s) => s.invalidate);
  const [hovered, setHovered] = useState<number | null>(null);
  const hiddenPicks = useHiddenPicks();

  /**
   * The faces ON OFFER. A switched-off body's faces leave the offer with it:
   * `PickSurface` already refuses to raycast them (SEL-6), but the centroid
   * `PickNode` is a DOM button that never asked the scene, so without this it
   * still seated a sketch on a face nobody can see — and the hover patch
   * painted brass over the empty space where the body was.
   */
  const offered = useMemo(
    () =>
      faces === null
        ? []
        : faces.filter(
            (face): face is OverlayFace & { signature: PlanarFaceSignature } =>
              isPickableFace(face) && !hiddenPicks.isHiddenFace(face.index),
          ),
    [faces, hiddenPicks],
  );

  // frameloop="demand": redraw when the pickable set / pending / hover changes.
  useEffect(() => {
    invalidate();
  }, [offered, pendingIndex, hovered, invalidate]);

  // Drop a stale hover when the OFFER changes out from under it — a refetch,
  // or the body under the cursor being switched off.
  useEffect(() => {
    setHovered(null);
  }, [offered]);

  /** QA hook: which face the armed pick is currently addressing (SEL-1 / A2). */
  useViewportPickStamp("facePickHover", hovered);

  /**
   * A hit on a face that is not ON OFFER — non-planar (it carries no signature,
   * so there is nothing to seat a datum on), or owned by a switched-off body —
   * resolves to null and is IGNORED rather than snapped to a neighbouring
   * pickable face. A pick that quietly acts on geometry the user did not
   * address is worse than one that does nothing, and "nothing" here is honest:
   * the overlay draws no patch there either, so the screen already said this
   * face is not on offer.
   */
  const pickableAt = useCallback(
    (
      ordinal: number | null,
    ): (OverlayFace & { signature: PlanarFaceSignature }) | null => {
      if (ordinal === null) return null;
      return offered.find((candidate) => candidate.index === ordinal) ?? null;
    },
    [offered],
  );

  const onSurfaceMove = useCallback(
    (ordinal: number | null) => {
      const face = pickableAt(ordinal);
      setHovered((current) => {
        const next = face?.index ?? null;
        return current === next ? current : next;
      });
    },
    [pickableAt],
  );

  const onSurfaceClick = useCallback(
    (ordinal: number | null, event: { stopPropagation: () => void }) => {
      const face = pickableAt(ordinal);
      if (face === null) return;
      event.stopPropagation();
      onPick(face);
    },
    [pickableAt, onPick],
  );

  if (faces === null) return null;

  return (
    <group>
      <PickSurface
        onMove={onSurfaceMove}
        onOut={() => setHovered(null)}
        onClick={onSurfaceClick}
      />
      {offered.map((face) => (
        <group key={`f${face.index}`}>
          {pendingIndex === face.index || hovered === face.index ? (
            <FacePatch
              signature={face.signature}
              selected={pendingIndex === face.index}
            />
          ) : null}
          <PickMark
            position={occtToScene(face.signature.centroid)}
            zIndexRange={[30, 10]}
          >
            <PickNode
              shape="face"
              // A7's recession: the drawn surface is this pick's primary
              // hit-test, so the mark here is the keyboard/touch fallback and
              // may rest quiet.
              recede
              selected={pendingIndex === face.index}
              data-testid={`plane-pick-face-${face.index}`}
              aria-label={faceLabel(face.index, face.signature)}
              onClick={() => onPick(face)}
              onPointerOver={() => setHovered(face.index)}
              onPointerOut={() =>
                setHovered((h) => (h === face.index ? null : h))
              }
              onFocus={() => setHovered(face.index)}
              onBlur={() => setHovered((h) => (h === face.index ? null : h))}
            />
          </PickMark>
        </group>
      ))}
    </group>
  );
}
