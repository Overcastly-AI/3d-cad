/**
 * The hole editor's face and point picks.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { useCallback, useEffect } from "react";

import {
  type OverlayFace,
  type PlanarFaceSignature,
  type Vec3,
} from "../../api/parts";
import { type HolePickTarget, type HolePreview } from "../../features/hole";
import { usePreselectStore } from "../../features/preselect";
import type { PartBody } from "./usePartBody";
import type { PickState } from "./usePickState";
import type { PickOverlays } from "./usePickOverlays";

type HolePickingParams = Pick<PartBody, "editor"> &
  Pick<
    PickState,
    | "holePick"
    | "setHolePick"
    | "setHoleFacePicked"
    | "setHolePointPicked"
    | "setHolePickError"
    | "setHolePreview"
    | "holePickNonce"
  > &
  Pick<
    PickOverlays,
    "bodyFeatureId" | "holePickRefusal" | "pickAnchorFeatureId"
  >;

export function useHolePicking({
  editor,
  holePick,
  setHolePick,
  setHoleFacePicked,
  setHolePointPicked,
  setHolePickError,
  setHolePreview,
  holePickNonce,
  bodyFeatureId,
  holePickRefusal,
  pickAnchorFeatureId,
}: HolePickingParams) {
  // Hole authoring picks. Arming a target highlights the body (faces for the
  // placement face, points on the face for the drill point); a click resolves
  // to a full-precision signature / world point the editor folds in. The face
  // anchor is the last body-affecting feature — the same rule sketch-on-face and
  // the datum picker use.
  const toggleHolePick = useCallback(
    (target: HolePickTarget) => {
      // Disarming is always allowed (see `togglePickFace`).
      if (holePick === target) {
        setHolePickError(null);
        setHolePick(null);
        return;
      }
      // PICK-2, as `toggleDatumFacePick`: the refusal was already here, the
      // honest reason was not — and it is stated once, by the face row's
      // disabled Pick control, not copied into the error slot as well.
      setHolePickError(null);
      if (holePickRefusal !== null) return;
      setHolePick(target);
    },
    [holePick, holePickRefusal],
  );

  const pickHoleFace = useCallback(
    (face: OverlayFace & { signature: PlanarFaceSignature }) => {
      // PICK-1: strictly earlier than the hole being written. This is the path
      // M17's "Re-pick face" repair drives, and stamping the tip here made that
      // repair write an id the server had to refuse — the hole under repair IS
      // the tip in the common case, so it named itself.
      const anchorId = pickAnchorFeatureId;
      if (anchorId === null) {
        setHolePickError(
          "Add a feature that creates a body before drilling a hole.",
        );
        setHolePick(null);
        return;
      }
      holePickNonce.current += 1;
      setHoleFacePicked({
        nonce: holePickNonce.current,
        face: { signature: face.signature, anchorId },
      });
      // Remembered against the body it was picked FROM (the tip's overlay),
      // not the reference anchor, and PROVISIONAL: it becomes a selection only
      // if this hole saves (preselect rule 3; a cancelled pick is forgotten).
      if (bodyFeatureId !== null) {
        usePreselectStore
          .getState()
          .rememberFaces(
            [{ signature: face.signature, anchorId: bodyFeatureId }],
            { provisional: true },
          );
      }
      // A face chosen → disarm (the editor seeds the point to the centre); the
      // user arms the POINT pick next to refine the placement.
      setHolePick(null);
    },
    [pickAnchorFeatureId, bodyFeatureId],
  );

  const pickHolePoint = useCallback((point: Vec3) => {
    holePickNonce.current += 1;
    setHolePointPicked({ nonce: holePickNonce.current, position: point });
    setHolePick(null);
  }, []);

  const onHolePreviewChange = useCallback(
    (preview: HolePreview | null) => setHolePreview(preview),
    [],
  );

  // The hole pick session ends whenever the hole editor closes (or the seat
  // holds a different editor) — drop the armed target, pending picks, preview,
  // and any error so a reopened editor starts clean.
  useEffect(() => {
    if (editor?.kind !== "hole") {
      setHolePick(null);
      setHoleFacePicked(null);
      setHolePointPicked(null);
      setHolePickError(null);
      setHolePreview(null);
    }
  }, [editor]);
  return { toggleHolePick, pickHoleFace, pickHolePoint, onHolePreviewChange };
}

export type HolePicking = ReturnType<typeof useHolePicking>;
