/**
 * The datum editor's face pick, and the plane at an angle's edge pick.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE).
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { type OverlayFace, type PlanarFaceSignature } from "../../api/parts";
import { type DatumFaceSlot } from "../../features/datum";
import { type DatumEdge, isStraightEdge } from "../../features/datumAngle";
import { useEdgePickStore } from "../../features/edgePickStore";
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
      // Provisional until the datum saves (preselect rule 3).
      if (bodyFeatureId !== null) {
        usePreselectStore
          .getState()
          .rememberFaces(
            [{ signature: face.signature, anchorId: bodyFeatureId }],
            { provisional: true },
          );
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

  // DATUM-PLANE-ANGLE: Fusion's Plane at Angle takes its line by a click on a
  // model edge. "Pick edge" opens a single-select edge-pick session (the
  // fillet's overlay, of the body a face pick comes from); the first straight
  // edge clicked becomes the line and the session closes. Arming it disarms a
  // face pick, and arming a face pick disarms it.
  const [datumEdgePickArmed, setDatumEdgePickArmed] = useState(false);
  const [datumEdgePicked, setDatumEdgePicked] = useState<{
    nonce: number;
    edge: DatumEdge;
  } | null>(null);
  const [datumEdgePickError, setDatumEdgePickError] = useState<string | null>(
    null,
  );
  const edgeNonce = useRef(0);
  const disarmEdgePick = useCallback(() => {
    setDatumEdgePickArmed(false);
    const store = useEdgePickStore.getState();
    if (store.active) store.close();
  }, []);
  const toggleDatumEdgePick = useCallback(() => {
    setDatumEdgePickError(null);
    if (datumEdgePickArmed) {
      disarmEdgePick();
      return;
    }
    if (datumPickRefusal !== null) return;
    setDatumFacePick(null);
    useEdgePickStore.getState().open([], true, { singleSelect: true });
    setDatumEdgePickArmed(true);
  }, [datumEdgePickArmed, datumPickRefusal, disarmEdgePick]);
  const edgePicks = useEdgePickStore((s) => s.picked);
  useEffect(() => {
    if (!datumEdgePickArmed) return;
    const [signature] = edgePicks;
    if (signature === undefined) return;
    disarmEdgePick();
    if (!isStraightEdge(signature)) {
      setDatumEdgePickError(
        "Pick a straight edge: a plane turns about a line.",
      );
      return;
    }
    // PICK-1: anchored strictly earlier than the datum, as a face pick is.
    if (pickAnchorFeatureId === null) {
      setDatumEdgePickError(
        "Add a feature that creates a body before picking an edge.",
      );
      return;
    }
    edgeNonce.current += 1;
    setDatumEdgePicked({
      nonce: edgeNonce.current,
      edge: { signature, anchorId: pickAnchorFeatureId },
    });
  }, [datumEdgePickArmed, edgePicks, pickAnchorFeatureId, disarmEdgePick]);
  useEffect(() => {
    if (datumFacePick !== null && datumEdgePickArmed) disarmEdgePick();
  }, [datumFacePick, datumEdgePickArmed, disarmEdgePick]);
  // Escape cancels the command, as during a fillet's edge pick (Fusion); the
  // close below and `usePickSessions` end the session with it.
  useEffect(() => {
    if (editor?.kind !== "datum") {
      setDatumEdgePickArmed(false);
      setDatumEdgePicked(null);
      setDatumEdgePickError(null);
    }
  }, [editor]);

  return {
    toggleDatumFacePick,
    pickDatumFace,
    toggleDatumEdgePick,
    datumEdgePickArmed,
    datumEdgePicked,
    datumEdgePickError,
  };
}

export type DatumFacePicking = ReturnType<typeof useDatumFacePicking>;
