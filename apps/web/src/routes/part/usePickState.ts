/**
 * The face-pick sessions' state: sketch-on-face, the datum editor's face
 * slot, and the hole's face + point picks.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { useRef, useState } from "react";

import { type DatumFacePick, type DatumFaceSlot } from "../../features/datum";
import {
  type HoleFacePick,
  type HolePickTarget,
  type HolePointPick,
  type HolePreview,
} from "../../features/hole";

export function usePickState() {
  // Face-pick (the plane-pick "Pick a face" path): arm → highlight the body's
  // planar faces → click one → author an on_face datum → seat the sketch.
  // Declared up here because the sketch keyboard effect (Escape cancels the
  // pick) reads `facePicking`.
  const [facePicking, setFacePicking] = useState(false);
  const [facePlaneBusy, setFacePlaneBusy] = useState(false);
  const [facePlaneError, setFacePlaneError] = useState<string | null>(null);
  const [pendingFaceIndex, setPendingFaceIndex] = useState<number | null>(null);

  // Datum-editor face picking: the DatumEditor arms a pick for one slot (the
  // on_face base, or either midplane side); a clicked face is folded into that
  // slot's form field. Reuses the SAME FacePickOverlay + overlay fetch the
  // sketch-on-face flow uses — one enumeration, pick side and resolve side.
  const [datumFacePick, setDatumFacePick] = useState<DatumFaceSlot | null>(
    null,
  );
  const [datumFacePicked, setDatumFacePicked] = useState<DatumFacePick | null>(
    null,
  );
  const [datumFacePickError, setDatumFacePickError] = useState<string | null>(
    null,
  );
  const datumFacePickNonce = useRef(0);

  // Hole authoring pick session: the HoleEditor arms a FACE pick (the planar
  // placement face) then a POINT pick (a point ON it). Both reuse the SAME
  // overlay fetch + DOM-in-canvas pick affordances the datum/measure flows use
  // — one enumeration, pick side and resolve side. `holePreview` mirrors the
  // editor's live face + position up so the point overlay draws ON the face.
  const [holePick, setHolePick] = useState<HolePickTarget | null>(null);
  const [holeFacePicked, setHoleFacePicked] = useState<HoleFacePick | null>(
    null,
  );
  const [holePointPicked, setHolePointPicked] = useState<HolePointPick | null>(
    null,
  );
  const [holePickError, setHolePickError] = useState<string | null>(null);
  const [holePreview, setHolePreview] = useState<HolePreview | null>(null);
  const holePickNonce = useRef(0);
  return {
    facePicking,
    setFacePicking,
    facePlaneBusy,
    setFacePlaneBusy,
    facePlaneError,
    setFacePlaneError,
    pendingFaceIndex,
    setPendingFaceIndex,
    datumFacePick,
    setDatumFacePick,
    datumFacePicked,
    setDatumFacePicked,
    datumFacePickError,
    setDatumFacePickError,
    datumFacePickNonce,
    holePick,
    setHolePick,
    holeFacePicked,
    setHoleFacePicked,
    holePointPicked,
    setHolePointPicked,
    holePickError,
    setHolePickError,
    holePreview,
    setHolePreview,
    holePickNonce,
  };
}

export type PickState = ReturnType<typeof usePickState>;
