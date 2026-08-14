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
import { Html } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { useCallback, useEffect, useMemo } from "react";

import type { OverlayFace, PlanarFaceSignature } from "../api/parts";
import { faceLabel, faceSignatureKey, isPickableFace } from "../features/face";
import { useFacePickStore } from "../features/facePickStore";
import { occtToScene } from "../measure/geometry";
import { FacePatch } from "./facePatch";
import { useHiddenPicks } from "./hiddenPicks";
import { PickSurface } from "./pickSurface";
import { useViewportPickStamp } from "./pickStamp";

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
    <group>
      <PickSurface
        onMove={onSurfaceMove}
        onOut={() => setHoverFace(null)}
        onClick={onSurfaceClick}
      />
      {offered.map((face) => (
        <group key={`f${face.index}`}>
          {pickedKeys.has(faceSignatureKey(face.signature)) ||
          hoverFace === face.index ? (
            <FacePatch
              signature={face.signature}
              selected={pickedKeys.has(faceSignatureKey(face.signature))}
            />
          ) : null}
          <Html
            position={occtToScene(face.signature.centroid)}
            center
            zIndexRange={[30, 10]}
          >
            <PickNode
              shape="face"
              // A7's recession: the drawn surface is this pick's primary
              // hit-test now, so the mark is the keyboard/touch fallback.
              recede
              selected={pickedKeys.has(faceSignatureKey(face.signature))}
              data-testid={`${testIdPrefix}-${face.index}`}
              aria-label={faceLabel(face.index, face.signature)}
              onClick={() => toggle(face.signature)}
              onPointerOver={() => setHoverFace(face.index)}
              onPointerOut={() => setHoverFace(null)}
              onFocus={() => setHoverFace(face.index)}
              onBlur={() => setHoverFace(null)}
            />
          </Html>
        </group>
      ))}
    </group>
  );
}
