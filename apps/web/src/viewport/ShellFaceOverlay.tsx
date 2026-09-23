/**
 * The shell/draft face-pick overlay inside the WebGL viewport — the face-pick
 * step of the Shell and Draft editors. The DRAWN SURFACE is the hit-test
 * (`PickSurface`, SEL-4): a raycast resolves the struck triangle back to its
 * B-rep face ordinal, so clicking anywhere on a face toggles that face. Every
 * PLANAR face also carries a DOM-in-canvas `PickNode` (drei `Html`) at its area
 * centroid, which is the keyboard focus target, the screen-reader name and the
 * touch tap target — the same posture as the sketch-on-face overlay. Faces of a
 * SWITCHED-OFF body are not offered at all (`hiddenPicks.ts`).
 *
 * Clicking TOGGLES that face into the "open" set; the shell then leaves ONLY
 * those faces open (empty set = a sealed hollow). Unlike the single-select
 * sketch-on-face picker (`FacePickOverlay`), this is a store-driven MULTI-select
 * set (the edge picker's posture), keyed by full-precision
 * `PlanarFaceSignature` — never the transient overlay index — so a refetch never
 * mismarks a pick. Selected faces take the brass fill (the app's selection
 * language); the parent store owns the picked set + hover.
 *
 * The hovered face gets the shared `FacePatch` laid on its plane. That is new
 * with the raycast and it is not decoration: before SEL-4 this overlay drew no
 * topology highlight at all, and a surface hit-test with no hover feedback
 * would be WORSE than the dot it replaces — the dot at least said where the
 * target was.
 */
import { PickNode } from "@loft/design";
import { useThree } from "@react-three/fiber";
import { useCallback, useEffect, useMemo, useRef } from "react";
import type { Mesh } from "three";

import type { OverlayFace, PlanarFaceSignature } from "../api/parts";
import { faceLabel, faceSignatureKey, isPickableFace } from "../features/face";
import { useFacePickStore } from "../features/facePickStore";
import { occtToScene } from "../measure/geometry";
import { BuriedMark } from "./BuriedMark";
import { ANNOTATION_LAYER } from "./instruments";
import { FacePatch } from "./facePatch";
import { useHiddenPicks } from "./hiddenPicks";
import { PickMark } from "./PickMark";
import { PickSurface, usePickSurfaceTarget } from "./pickSurface";
import { useViewportPickStamp } from "./pickStamp";
import {
  useSurfaceMarkBurial,
  type SurfaceMarkSubject,
} from "./useSurfaceMarkBurial";

export interface ShellFaceOverlayProps {
  /**
   * Prefix for each pick node's `data-testid` (e.g. `shell-face` → `shell-face-3`).
   * The shell and draft editors share this ONE store-driven overlay (only one is
   * ever open), so QA drives each by its own prefix. Defaults to `shell-face`.
   */
  testIdPrefix?: string;
}

export function ShellFaceOverlay({
  testIdPrefix = "shell-face",
}: ShellFaceOverlayProps = {}) {
  const overlay = useFacePickStore((s) => s.overlay);
  const picked = useFacePickStore((s) => s.picked);
  const hoverFace = useFacePickStore((s) => s.hoverFace);
  const toggle = useFacePickStore((s) => s.toggle);
  const setHoverFace = useFacePickStore((s) => s.setHoverFace);
  const invalidate = useThree((s) => s.invalidate);
  const hiddenPicks = useHiddenPicks();

  /**
   * The faces ON OFFER — planar, and owned by a body that is DRAWN. A
   * switched-off body's faces leave with it: `PickSurface` already refuses to
   * raycast them (SEL-6), but the centroid `PickNode` is a DOM button that
   * never asked the scene, so it would still open a shell wall nobody can see.
   */
  const offered = useMemo(
    () =>
      overlay === null
        ? []
        : overlay.faces.filter(
            (face): face is OverlayFace & { signature: PlanarFaceSignature } =>
              isPickableFace(face) && !hiddenPicks.isHiddenFace(face.index),
          ),
    [overlay, hiddenPicks],
  );

  // frameloop="demand": redraw when the pick/hover set changes.
  useEffect(() => {
    invalidate();
  }, [offered, picked, hoverFace, invalidate]);

  /** QA hook: which face the armed shell/draft pick is addressing (SEL-4). */
  useViewportPickStamp("shellFaceHover", hoverFace);

  const pickedKeys = useMemo(
    () => new Set(picked.map(faceSignatureKey)),
    [picked],
  );

  /**
   * WHETHER EACH MARK CAN BE REACHED WHERE IT STANDS (board item #76).
   *
   * A face mark sits at its face's area CENTROID, which is a point in space and
   * not a point on screen — so a box's bottom face plants its mark inside the
   * visible front wall, and a DOM button that never asked the scene anything
   * took that pixel from the face the modeller can see. The oracle is the same
   * surface the pointer uses, so the two cannot disagree.
   */
  const surfaceRef = useRef<Mesh | null>(null);
  const { ordinalAt } = usePickSurfaceTarget();
  const subjects = useMemo<SurfaceMarkSubject[]>(
    () =>
      offered.map((face) => ({
        ordinal: face.index,
        point: face.signature.centroid,
        normal: face.signature.normal,
        areaMm2: face.signature.area_mm2,
      })),
    [offered],
  );
  const seats = useSurfaceMarkBurial(subjects, surfaceRef, ordinalAt);

  /**
   * A hit on a face that is not ON OFFER — non-planar (shell/draft address
   * planar faces only), or owned by a switched-off body — resolves to null and
   * is IGNORED rather than snapped to a neighbouring planar face. A pick that
   * quietly opens a wall the modeller did not address is worse than one that
   * does nothing, and "nothing" is honest here: the overlay draws neither a
   * mark nor a patch there.
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
    (ordinal: number | null) =>
      setHoverFace(pickableAt(ordinal)?.index ?? null),
    [pickableAt, setHoverFace],
  );

  const onSurfaceClick = useCallback(
    (ordinal: number | null, event: { stopPropagation: () => void }) => {
      const face = pickableAt(ordinal);
      if (face === null) return;
      event.stopPropagation();
      toggle(face.signature);
    },
    [pickableAt, toggle],
  );

  if (overlay === null) return null;

  return (
    <group userData={ANNOTATION_LAYER}>
      <PickSurface
        meshRef={surfaceRef}
        onMove={onSurfaceMove}
        onOut={() => setHoverFace(null)}
        onClick={onSurfaceClick}
      />
      {offered.map((face, slot) => {
        // A mark whose face is behind the material yields the pixel to the face
        // in FRONT, and is drawn as a hidden-line ghost (`BuriedMark`).
        const seat = seats[slot];
        const hidden = seat?.buried === true;
        return (
          <group key={`f${face.index}`}>
            {pickedKeys.has(faceSignatureKey(face.signature)) ||
            hoverFace === face.index ? (
              <FacePatch
                signature={face.signature}
                selected={pickedKeys.has(faceSignatureKey(face.signature))}
              />
            ) : null}
            <PickMark
              // The seat the surface pass found ON this face and clear of any
              // gauge — the centroid unless that was hidden or covered.
              position={seat?.position ?? occtToScene(face.signature.centroid)}
              zIndexRange={[30, 10]}
            >
              {/* The hidden-line ghost: a buried face is BEHIND the part, not
                  absent, and the difference is what the audit's modeller could
                  not see. Drawn only while the mark itself is dark. */}
              {hidden ? <BuriedMark shape="face" /> : null}
              <PickNode
                shape="face"
                // A7's recession: the drawn surface is this pick's primary
                // hit-test now, so the mark is the keyboard/touch fallback.
                recede
                occluded={hidden}
                selected={pickedKeys.has(faceSignatureKey(face.signature))}
                data-testid={`${testIdPrefix}-${face.index}`}
                data-buried={hidden ? "true" : "false"}
                aria-label={faceLabel(face.index, face.signature)}
                onClick={() => toggle(face.signature)}
                onPointerOver={() => setHoverFace(face.index)}
                onPointerOut={() => setHoverFace(null)}
                onFocus={() => setHoverFace(face.index)}
                onBlur={() => setHoverFace(null)}
              />
            </PickMark>
          </group>
        );
      })}
    </group>
  );
}
