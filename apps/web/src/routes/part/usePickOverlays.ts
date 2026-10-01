/**
 * Every pick overlay fetch and what it feeds: face, datum, hole, edge and
 * shell picks, the hover proposal, the selection and pre-selection tints,
 * and PICK-1's reference anchor.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";

import { fetchOverlay } from "../../api/measure";
import { buildEvaluateTree } from "../../measure/geometry";
import { type FeatureTreeResponse } from "../../api/parts";
import { useEdgePickStore } from "../../features/edgePickStore";
import { useFacePickStore } from "../../features/facePickStore";
import { preselectedFaces, usePreselectStore } from "../../features/preselect";
import {
  anchorBodyFeatureId,
  faceOrdinalOfSignature,
  faceSignatureKey,
  isPickableFace,
  lastBodyFeatureId,
} from "../../features/face";
import { useIsHiddenFaceOrdinal } from "../../viewport/hiddenPicks";
import { pickRefusal } from "../../viewport/pickTargets";
import { highlightedFeatureIds } from "../../viewport/scopeHighlight";
import type { PartDocument } from "./usePartDocument";
import type { PartBody } from "./usePartBody";
import type { PickState } from "./usePickState";
import type { MeasureSession } from "./useMeasureSession";
import type { EditorSeat } from "./useEditorSeat";

type PickOverlaysParams = Pick<
  PartDocument,
  "partId" | "mode" | "tree" | "treeVersion"
> &
  Pick<
    PartBody,
    "meshGlbId" | "editor" | "displayTree" | "hasBody" | "hasPickTargets"
  > &
  Pick<
    PickState,
    "facePicking" | "datumFacePick" | "holePick" | "holePreview"
  > &
  Pick<MeasureSession, "measureActive"> &
  Pick<EditorSeat, "selectedFeatureId" | "scopedFeatureIds">;

export function usePickOverlays({
  partId,
  mode,
  tree,
  treeVersion,
  meshGlbId,
  editor,
  displayTree,
  hasBody,
  hasPickTargets,
  facePicking,
  datumFacePick,
  holePick,
  holePreview,
  measureActive,
  selectedFeatureId,
  scopedFeatureIds,
}: PickOverlaysParams) {
  // The pickable face overlay for the current evaluated body — fetched exactly
  // as measurement fetches its overlay (same request/key: one cache entry, and
  // the faces line up with the body the viewport renders). Only while arming a
  // face pick and a body exists.
  const facesQuery = useQuery({
    queryKey: ["overlay", partId, treeVersion, meshGlbId],
    queryFn: () =>
      fetchOverlay(buildEvaluateTree(tree.data as FeatureTreeResponse)),
    enabled: facePicking && tree.data !== undefined && meshGlbId !== null,
    staleTime: Infinity,
    retry: false,
  });
  const pickableFaces = facePicking ? (facesQuery.data?.faces ?? null) : null;

  // The pickable face overlay while the datum editor is armed for a slot —
  // same request/key (one cache entry, faces line up with the rendered body).
  const datumFacesQuery = useQuery({
    queryKey: ["overlay", partId, treeVersion, meshGlbId],
    queryFn: () =>
      fetchOverlay(buildEvaluateTree(tree.data as FeatureTreeResponse)),
    enabled:
      datumFacePick !== null && tree.data !== undefined && meshGlbId !== null,
    staleTime: Infinity,
    retry: false,
  });
  const datumPickableFaces =
    datumFacePick !== null ? (datumFacesQuery.data?.faces ?? null) : null;

  // The pickable overlay for the WHOLE hole command — same request/key as every
  // other overlay (one cache entry, faces + vertices + edges line up with the
  // rendered body). `.faces` feeds the face pick; `.vertices` feed the point
  // pick's face-corner snaps; `.edges` feed the coordinate cells' live material
  // check and the concentric snaps (QA3-1), which is why this is no longer
  // gated on a pick being armed — typing a coordinate needs the geometry too.
  const holeEditing = editor?.kind === "hole";
  const holeOverlayQuery = useQuery({
    queryKey: ["overlay", partId, treeVersion, meshGlbId],
    queryFn: () =>
      fetchOverlay(buildEvaluateTree(tree.data as FeatureTreeResponse)),
    enabled: holeEditing && tree.data !== undefined && meshGlbId !== null,
    staleTime: Infinity,
    retry: false,
  });
  const holePickableFaces =
    holePick === "face" ? (holeOverlayQuery.data?.faces ?? null) : null;
  const holeOverlayFaces = holeOverlayQuery.data?.faces ?? null;
  const holeOverlayVertices = holeOverlayQuery.data?.vertices ?? null;
  const holeOverlayEdges = holeOverlayQuery.data?.edges ?? null;
  /**
   * Is the placement face's own body switched OFF (SEL-7)? The viewport
   * withholds the whole placement overlay in that state; the EDITOR has to say
   * why, or the crosshair just vanishes mid-command and the pick becomes a dead
   * end. Ordinal-only — a set membership, no weld pass — and the hook reads the
   * store, so it is safe out here outside the r3f `Canvas`.
   */
  const holePlacementHidden = useIsHiddenFaceOrdinal(
    faceOrdinalOfSignature(holePreview?.signature ?? null, holeOverlayFaces),
  );

  // ---------------------------------------------------------------------
  // Fillet/Chamfer edge picking. The edge-pick store bridges the editor and the
  // in-canvas overlay; PartPage owns the overlay fetch and the session lifecycle
  // (open on a fillet/chamfer editor, close otherwise). The anchor a picked
  // edge's `SubshapeRef` carries is `pickAnchorFeatureId` below, NOT the tip.
  // ---------------------------------------------------------------------
  const bodyFeatureId = useMemo(
    () => lastBodyFeatureId(tree.data?.features ?? []),
    [tree.data],
  );

  /**
   * PICK-2 — what every arming guard below asks `pickRefusal` about. Split in
   * two on purpose: a part that has never had a body-affecting feature needs
   * "add one", while a part whose body-affecting feature exists but did not
   * build needs "clear the error" — and telling a modeller to add the feature
   * they can see in the tree is how a refusal stops being believed.
   */
  const pickTargetState = useMemo(
    () => ({ hasPickTargets, hasBodyFeature: bodyFeatureId !== null }),
    [hasPickTargets, bodyFeatureId],
  );
  /**
   * PICK-2 — why the hole / datum / sketch face picks cannot be armed, or null.
   *
   * DERIVED, never mirrored into state. An armed pick whose targets disappear
   * (the tip stops building while the editor is open) has to become honest at
   * that instant, and a copy of the reason held in `holePickError` would only
   * become honest the next time somebody pressed something. Each editor states
   * its own refusal on a surface that is NOT gated on a pick being armed, so
   * "refuse to arm" and "say why" are the same fact told once.
   */
  const holePickRefusal = pickRefusal(
    pickTargetState,
    "Add a feature that creates a body before drilling a hole.",
  );
  const datumPickRefusal = pickRefusal(
    pickTargetState,
    "Add a feature that creates a body before picking a face.",
  );
  const facePickRefusal = pickRefusal(
    pickTargetState,
    "Add a feature that creates a body before sketching on a face.",
  );

  // --- Hover-to-sketch (FLOW-1, founder report 2026-08-14) --------------------
  //
  // The face the pointer is addressing while NOTHING is armed. Idle hover used
  // to light a face (SEL-1) and mean nothing — no click handler, no selection —
  // so there is no existing meaning for the proposal to collide with; it gives
  // that highlight the action it was already implying.
  const [hoveredFaceOrdinal, setHoveredFaceOrdinal] = useState<number | null>(
    null,
  );
  const noteFaceHover = useCallback((ordinal: number | null) => {
    setHoveredFaceOrdinal((current) =>
      current === ordinal ? current : ordinal,
    );
  }, []);
  /**
   * The context a proposal may be offered in — the SAME conditions that make
   * the body interactive, plus PICK-2's refusal (a tip that builds no body has
   * no faces to sketch on, and an offer that cannot be honoured is worse than
   * no offer).
   */
  const proposalContext =
    mode === "off" &&
    editor === null &&
    !measureActive &&
    hasBody &&
    facePickRefusal === null;
  const proposalArmed = proposalContext && hoveredFaceOrdinal !== null;
  // LAZY on purpose: nothing is requested until the pointer first addresses a
  // face. Same request/key as every other overlay (`staleTime: Infinity`), so
  // this is one shared cache entry — the first idle hover warms the very entry
  // the Sketch, measure, hole and datum flows all go on to reuse.
  const proposalFacesQuery = useQuery({
    queryKey: ["overlay", partId, treeVersion, meshGlbId],
    queryFn: () =>
      fetchOverlay(buildEvaluateTree(tree.data as FeatureTreeResponse)),
    enabled: proposalArmed && tree.data !== undefined && meshGlbId !== null,
    staleTime: Infinity,
    retry: false,
  });
  /**
   * The hovered face, resolved to one a sketch can actually sit on. A
   * non-planar face carries no signature and is NOT proposable — the same rule
   * `FacePickOverlay` applies, so the two surfaces offer exactly the same set
   * and hovering a fillet proposes nothing rather than proposing a dead end.
   */
  const proposedFace = useMemo(() => {
    if (!proposalArmed) return null;
    const faces = proposalFacesQuery.data?.faces;
    if (faces === undefined) return null;
    const hit = faces.find(
      (candidate) => candidate.index === hoveredFaceOrdinal,
    );
    return hit !== undefined && isPickableFace(hit) ? hit : null;
  }, [proposalArmed, proposalFacesQuery.data, hoveredFaceOrdinal]);

  // PICK-1 (M16) — the anchor a SUBSHAPE REFERENCE gets stamped with, which is
  // NOT always `bodyFeatureId`. A reference must name a feature strictly earlier
  // than the one carrying it (documents `_validate_references` → 422
  // `reference_not_earlier`), and it is resolved against THAT feature's body. At
  // create the new feature lands at the tip, so the two coincide; while EDITING a
  // mid-tree feature the tip is later than — or IS — the referrer, which is why
  // no picked-edge fillet / picked-face shell could be re-saved at all (M9/M10)
  // and why M17's "re-pick the face" recovery wrote an id the server refused.
  //
  // `bodyFeatureId` stays the TIP on purpose: it answers "does a body exist, and
  // which body is on screen" (the import gate, the pre-selection carry-over —
  // the overlays a pick comes FROM are always the tip's). Only the reference
  // stamp moves.
  const editingFeatureId =
    editor !== null && editor.mode === "edit"
      ? (editor.featureId ?? null)
      : null;
  const pickAnchorFeatureId = useMemo(
    () => anchorBodyFeatureId(tree.data?.features ?? [], editingFeatureId),
    [tree.data, editingFeatureId],
  );

  const edgePicking = useEdgePickStore((s) => s.active && s.picking);
  const setEdgeOverlay = useEdgePickStore((s) => s.setOverlay);
  const setEdgeOverlayError = useEdgePickStore((s) => s.setOverlayError);

  // WHICH BODY THE EDGES COME FROM. Creating, it is the tip (the shared overlay
  // entry). EDITING, it is the body the feature under edit is BUILT ON, the
  // same body its picked edges resolve against. The tip is wrong there: it
  // already carries this feature, so the edge a fillet rounds is not in it,
  // and a re-pick of a moved edge (EDGE-RESOLVE-WARN-1) had nothing to click.
  const edgeOverlayQuery = useQuery({
    queryKey:
      editingFeatureId === null
        ? ["overlay", partId, treeVersion, meshGlbId]
        : ["overlay-before", partId, treeVersion, editingFeatureId],
    queryFn: () =>
      fetchOverlay(
        buildEvaluateTree(
          tree.data as FeatureTreeResponse,
          editingFeatureId ?? undefined,
        ),
      ),
    enabled: edgePicking && tree.data !== undefined && meshGlbId !== null,
    staleTime: Infinity,
    retry: false,
  });

  useEffect(() => {
    if (edgePicking && edgeOverlayQuery.data !== undefined) {
      setEdgeOverlay(edgeOverlayQuery.data);
    }
  }, [edgePicking, edgeOverlayQuery.data, setEdgeOverlay]);

  useEffect(() => {
    if (edgePicking && edgeOverlayQuery.error) {
      setEdgeOverlayError(
        edgeOverlayQuery.error instanceof Error
          ? edgeOverlayQuery.error.message
          : "The edge overlay could not be built.",
      );
    }
  }, [edgePicking, edgeOverlayQuery.error, setEdgeOverlayError]);

  // Face picking (shell + draft). A shell OR draft editor arms a face-pick
  // session on the SAME store (only one editor is open at a time); the pickable
  // face overlay for the current body is fetched exactly as the edge/measure
  // overlays are (same request/key — one cache entry, faces line up with the
  // rendered body). The anchor for a picked face's `SubshapeRef` is the same
  // `pickAnchorFeatureId` fillet/chamfer use — the tip while creating, the
  // feature before the one under edit while editing (PICK-1).
  const shellPicking = useFacePickStore((s) => s.active);
  const setShellOverlay = useFacePickStore((s) => s.setOverlay);
  const setShellOverlayError = useFacePickStore((s) => s.setOverlayError);

  // Editing, the faces come from the body the feature is built on, as the
  // edges do above: a shell's open faces are not faces of the shelled tip.
  const shellOverlayQuery = useQuery({
    queryKey:
      editingFeatureId === null
        ? ["overlay", partId, treeVersion, meshGlbId]
        : ["overlay-before", partId, treeVersion, editingFeatureId],
    queryFn: () =>
      fetchOverlay(
        buildEvaluateTree(
          tree.data as FeatureTreeResponse,
          editingFeatureId ?? undefined,
        ),
      ),
    enabled: shellPicking && tree.data !== undefined && meshGlbId !== null,
    staleTime: Infinity,
    retry: false,
  });

  useEffect(() => {
    if (shellPicking && shellOverlayQuery.data !== undefined) {
      setShellOverlay(shellOverlayQuery.data);
    }
  }, [shellPicking, shellOverlayQuery.data, setShellOverlay]);

  useEffect(() => {
    if (shellPicking && shellOverlayQuery.error) {
      setShellOverlayError(
        shellOverlayQuery.error instanceof Error
          ? shellOverlayQuery.error.message
          : "The face overlay could not be built.",
      );
    }
  }, [shellPicking, shellOverlayQuery.error, setShellOverlayError]);

  // ---------------------------------------------------------------------
  // Feature-localized selection (FINDINGS #9). Selecting a feature in the tree
  // highlights ONLY the faces that feature owns — the studio matcap stays on
  // the rest of the body (never a whole-body clay swap). The overlay carries
  // per-face `feature_id` provenance; the selected feature's faces are every
  // OverlayFace whose `feature_id` matches it, and each face's `index` is its
  // GLB primitive ordinal — the mesh face set to tint. Fetched through the SAME
  // request/key as every other overlay (one cache entry, faces line up with the
  // rendered body). Mirrors `bodySelected` exactly (selecting a feature opens
  // its editor, so it must NOT gate on `editor === null`) — it localizes the
  // same warm the body already shows, refining whole-body → this feature's faces.
  //
  // REACH-2-FLOW-B: WHAT gets tinted is the OPEN COMMAND's scope whenever one is
  // asking, and the tree selection otherwise — the same source the tree stamp
  // and the timeline chip read, so the three surfaces answer one question. See
  // `viewport/scopeHighlight.ts` for why `This body` paints nothing.
  // ---------------------------------------------------------------------
  // A feature past the displayed stop is not in the body on screen, so it
  // lights nothing. The fillet under edit (its input body drawn) owns no face
  // there, and would otherwise fall back to warming the whole body.
  const highlightFeatureIds = useMemo(() => {
    const ids = highlightedFeatureIds(scopedFeatureIds, selectedFeatureId);
    const past = new Set(
      (displayTree?.features ?? [])
        .filter((f) => f.rolled_back)
        .map((f) => f.id),
    );
    return past.size === 0 ? ids : ids.filter((id) => !past.has(id));
  }, [scopedFeatureIds, selectedFeatureId, displayTree]);
  const selectionActive =
    mode === "off" && highlightFeatureIds.length > 0 && !measureActive;
  const selectionOverlayQuery = useQuery({
    queryKey: ["overlay", partId, treeVersion, meshGlbId],
    queryFn: () =>
      fetchOverlay(buildEvaluateTree(tree.data as FeatureTreeResponse)),
    enabled: selectionActive && tree.data !== undefined && meshGlbId !== null,
    staleTime: Infinity,
    retry: false,
  });
  const selectedFaceIndices = useMemo<number[] | null>(() => {
    if (!selectionActive) return null;
    const faces = selectionOverlayQuery.data?.faces;
    if (faces === undefined) return null;
    // `feature_id` is null/absent on any face the server did not attribute (an
    // older payload, or a body past the provenance bound) — an unattributed
    // face matches nothing, exactly as the single-id equality it replaces did.
    const owners = new Set<string>(highlightFeatureIds);
    const owned = faces
      .filter((face) => {
        const owner = face.feature_id;
        return owner !== null && owner !== undefined && owners.has(owner);
      })
      .map((face) => face.index);
    return owned.length > 0 ? owned : null;
  }, [selectionActive, highlightFeatureIds, selectionOverlayQuery.data]);

  // ---------------------------------------------------------------------
  // Pre-selection highlight (UI-W3). A selection you cannot see is a trap: the
  // next command would prefill itself from something invisible. So the faces
  // the cursor has picked STAY lit after the editor that picked them closes —
  // the same feature-localized brass a tree selection lights, on the same
  // cached overlay (the pick already fetched it, so this costs no request).
  // A tree selection wins while one is active: one highlight, one meaning.
  // ---------------------------------------------------------------------
  const preselectedFaceSet = usePreselectStore((s) => s.faces);
  const livePreselectedFaces = useMemo(
    () => preselectedFaces({ faces: preselectedFaceSet }, bodyFeatureId),
    [preselectedFaceSet, bodyFeatureId],
  );
  const preselectHighlightActive =
    mode === "off" &&
    !measureActive &&
    selectedFeatureId === null &&
    livePreselectedFaces.length > 0;
  const preselectOverlayQuery = useQuery({
    queryKey: ["overlay", partId, treeVersion, meshGlbId],
    queryFn: () =>
      fetchOverlay(buildEvaluateTree(tree.data as FeatureTreeResponse)),
    enabled:
      preselectHighlightActive && tree.data !== undefined && meshGlbId !== null,
    staleTime: Infinity,
    retry: false,
  });
  const preselectedFaceIndices = useMemo<number[] | null>(() => {
    if (!preselectHighlightActive) return null;
    const faces = preselectOverlayQuery.data?.faces;
    if (faces === undefined) return null;
    const keys = new Set(
      livePreselectedFaces.map((face) => faceSignatureKey(face.signature)),
    );
    const lit = faces
      .filter(
        (face) =>
          isPickableFace(face) && keys.has(faceSignatureKey(face.signature)),
      )
      .map((face) => face.index);
    return lit.length > 0 ? lit : null;
  }, [
    preselectHighlightActive,
    livePreselectedFaces,
    preselectOverlayQuery.data,
  ]);

  return {
    pickableFaces,
    datumPickableFaces,
    holePickableFaces,
    holeOverlayFaces,
    holeOverlayVertices,
    holeOverlayEdges,
    holePlacementHidden,
    bodyFeatureId,
    holePickRefusal,
    datumPickRefusal,
    facePickRefusal,
    noteFaceHover,
    proposalContext,
    proposedFace,
    pickAnchorFeatureId,
    edgePicking,
    shellPicking,
    highlightFeatureIds,
    selectedFaceIndices,
    preselectedFaceIndices,
  };
}

export type PickOverlays = ReturnType<typeof usePickOverlays>;
