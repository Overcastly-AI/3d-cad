/**
 * The datum editor's face pick.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { useCallback, useEffect } from "react";

import { type OverlayFace, type PlanarFaceSignature } from "../../api/parts";
import { type DatumFaceSlot } from "../../features/datum";
import { usePreselectStore } from "../../features/preselect";
import type { PartBody } from "./usePartBody";
import type { PickState } from "./usePickState";
import type { PickOverlays } from "./usePickOverlays";

type DatumFacePickingParams = Pick<PartBody, "editor"> &
  Pick<
    PickState,
    | "datumFacePick"
    | "setDatumFacePick"
    | "setDatumFacePicked"
    | "setDatumFacePickError"
    | "datumFacePickNonce"
  > &
  Pick<
    PickOverlays,
    "bodyFeatureId" | "datumPickRefusal" | "pickAnchorFeatureId"
  >;

export function useDatumFacePicking({
  editor,
  datumFacePick,
  setDatumFacePick,
  setDatumFacePicked,
  setDatumFacePickError,
  datumFacePickNonce,
  bodyFeatureId,
  datumPickRefusal,
  pickAnchorFeatureId,
}: DatumFacePickingParams) {
  // Datum-editor face picking. Arming a slot highlights the body's planar faces
  // in the viewport (the shared FacePickOverlay); a click resolves to a
  // full-precision signature the editor folds into that slot. The anchor is the
  // last body-affecting feature — the same rule sketch-on-face uses.
  const toggleDatumFacePick = useCallback(
    (slot: DatumFaceSlot) => {
      // Disarming is always allowed (see `togglePickFace`).
      if (datumFacePick === slot) {
        setDatumFacePickError(null);
        setDatumFacePick(null);
        return;
      }
      // PICK-2: this already refused on `hasBody`, but said the wrong thing for
      // the case that actually reaches a modeller — a part whose extrude is
      // right there in the tree and simply did not build. The reason is NOT
      // copied into `datumFacePickError` here: `datumPickRefusal` is already on
      // screen the whole time the condition holds, and stating it twice would
      // make one refusal look like two problems.
      setDatumFacePickError(null);
      if (datumPickRefusal !== null) return;
      setDatumFacePick(slot);
    },
    [datumFacePick, datumPickRefusal],
  );

  const pickDatumFace = useCallback(
    (face: OverlayFace & { signature: PlanarFaceSignature }) => {
      const slot = datumFacePick;
      if (slot === null) return;
      // PICK-1: the REFERENCE is anchored strictly earlier than the datum being
      // written (the tip while creating; the feature before it while editing).
      const anchorId = pickAnchorFeatureId;
      if (anchorId === null) {
        setDatumFacePickError(
          "Add a feature that creates a body before picking a face.",
        );
        setDatumFacePick(null);
        return;
      }
      datumFacePickNonce.current += 1;
      setDatumFacePicked({
        nonce: datumFacePickNonce.current,
        slot,
        face: { signature: face.signature, anchorId },
      });
      // Remembered for the next command (UI-W3) against the body it was picked
      // FROM — always the tip's overlay — not the reference anchor above.
      if (bodyFeatureId !== null) {
        usePreselectStore
          .getState()
          .rememberFaces([
            { signature: face.signature, anchorId: bodyFeatureId },
          ]);
      }
      setDatumFacePick(null);
    },
    [datumFacePick, pickAnchorFeatureId, bodyFeatureId],
  );

  // The datum face-pick session ends whenever the datum editor closes (or the
  // seat holds a different editor) — drop the armed slot, the pending pick, and
  // any pick error so a reopened editor starts clean (the nonce guard already
  // stops a stale pick re-folding, but a cleared session is the honest state).
  useEffect(() => {
    if (editor?.kind !== "datum") {
      setDatumFacePick(null);
      setDatumFacePicked(null);
      setDatumFacePickError(null);
    }
  }, [editor]);
  return { toggleDatumFacePick, pickDatumFace };
}

export type DatumFacePicking = ReturnType<typeof useDatumFacePicking>;
