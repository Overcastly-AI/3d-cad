/**
 * Starting a sketch: on a face, on an offset plane, from the pre-selection
 * or from a viewport proposal.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { useCallback } from "react";

import {
  createFeature,
  type DatumOffsetParams,
  datumFeatureCreate,
  datumOnFaceFeatureCreate,
  fetchFeatureTree,
  type OverlayFace,
  type PlanarFaceSignature,
} from "../../api/parts";
import { preselectedFace, usePreselectStore } from "../../features/preselect";
import { faceSpecFromDatum, offsetSpecFromDatum } from "../../sketch/plane";
import { lastBodyFeatureId, onFaceDatumParams } from "../../features/face";
import { useSketchStore } from "../../sketch/store";
import type { PartDocument } from "./usePartDocument";
import type { PickState } from "./usePickState";
import type { FeatureCatalog } from "./useFeatureCatalog";
import type { ActionFlags } from "./useActionFlags";
import type { PickOverlays } from "./usePickOverlays";
import type { TreeWrites } from "./useTreeWrites";
import type { WorkspaceActions } from "./useWorkspaceActions";
import type { FeatureOpeners } from "./useFeatureOpeners";

type SketchEntryParams = Pick<PartDocument, "partId" | "queryClient" | "tree"> &
  Pick<
    PickState,
    | "facePicking"
    | "setFacePicking"
    | "setFacePlaneBusy"
    | "setFacePlaneError"
    | "setPendingFaceIndex"
  > &
  Pick<FeatureCatalog, "features"> &
  Pick<ActionFlags, "setOffsetPlaneBusy" | "setOffsetPlaneError"> &
  Pick<PickOverlays, "bodyFeatureId" | "facePickRefusal"> &
  Pick<TreeWrites, "freshTreeVersion"> &
  Pick<WorkspaceActions, "handleNewSketch"> &
  Pick<FeatureOpeners, "openCreateExtrude">;

export function useSketchEntry({
  partId,
  queryClient,
  tree,
  facePicking,
  setFacePicking,
  setFacePlaneBusy,
  setFacePlaneError,
  setPendingFaceIndex,
  features,
  setOffsetPlaneBusy,
  setOffsetPlaneError,
  bodyFeatureId,
  facePickRefusal,
  freshTreeVersion,
  handleNewSketch,
  openCreateExtrude,
}: SketchEntryParams) {
  // "Sketch on face" from the viewport menu: begin a sketch and arm the
  // face-pick step (the same flow the sketch strip's "Pick face" button drives).
  const startSketchOnFace = useCallback(() => {
    handleNewSketch();
    // PICK-2: the viewport menu reaches this without passing the strip's
    // `canPickFace` gate, so the refusal has to be enforced here too. The
    // sketch still opens — the plane picker's other routes (origin planes,
    // offset) are all still available, and closing the sketch outright would
    // punish the user for the tree's state.
    setFacePlaneError(null);
    setFacePicking(facePickRefusal === null);
  }, [handleNewSketch, facePickRefusal]);

  // The inline "sketch at a height" path: author a datum feature, then enter
  // the sketcher on it. One extra field, not a separate multi-step ritual —
  // the datum write returns the feature id the sketch's plane FeatureRef needs.
  const authorOffsetPlane = useCallback(
    (params: DatumOffsetParams) => {
      const nextIndex =
        features.filter((f) => f.feature.type === "datum").length + 1;
      setOffsetPlaneBusy(true);
      setOffsetPlaneError(null);
      void (async () => {
        try {
          const create = (version: number) =>
            createFeature(
              partId,
              datumFeatureCreate(`Plane${nextIndex}`, params, version),
            );
          let response;
          try {
            response = await create(await freshTreeVersion());
          } catch {
            response = await create(
              (await fetchFeatureTree(partId)).tree_version,
            );
          }
          await queryClient.invalidateQueries({
            queryKey: ["features", partId],
          });
          useSketchStore
            .getState()
            .choosePlaneSpec(offsetSpecFromDatum(response.feature.id, params));
        } catch (error) {
          setOffsetPlaneError(
            error instanceof Error
              ? error.message
              : "The offset plane could not be created.",
          );
        } finally {
          setOffsetPlaneBusy(false);
        }
      })();
    },
    [partId, features, freshTreeVersion, queryClient],
  );

  // The "Pick a face" path: author an `on_face` datum from the clicked face's
  // stage-1 signature, then seat this sketch on it — the datum-node route
  // (datum-planes §7), so the sketch's plane is the SAME FeatureRef slot an
  // offset datum uses. The face's plane basis is reconstructed client-side from
  // the signature (origin + deterministic x-axis), matching the kernel's
  // `resolve_sketch_plane` exactly, so the ink lands on the rendered face.
  const authorFacePlane = useCallback(
    (face: { signature: PlanarFaceSignature; index?: number }) => {
      const featureList = tree.data?.features ?? [];
      const anchorId = lastBodyFeatureId(featureList);
      if (anchorId === null) {
        setFacePlaneError(
          "Add a feature that creates a body before sketching on a face.",
        );
        return;
      }
      // Not remembered as a pre-selection (SKETCH-PLANE-PICK): the sketch
      // consumed the face, and a remembered one seated every later New Sketch
      // on it. Fusion clears the selection once a sketch is created.
      const { signature } = face;
      const nextIndex =
        featureList.filter((f) => f.feature.type === "datum").length + 1;
      setFacePlaneBusy(true);
      setPendingFaceIndex(face.index ?? null);
      setFacePlaneError(null);
      void (async () => {
        try {
          const params = onFaceDatumParams(anchorId, signature, 0);
          const create = (version: number) =>
            createFeature(
              partId,
              datumOnFaceFeatureCreate(`Plane${nextIndex}`, params, version),
            );
          let response;
          try {
            response = await create(await freshTreeVersion());
          } catch {
            response = await create(
              (await fetchFeatureTree(partId)).tree_version,
            );
          }
          await queryClient.invalidateQueries({
            queryKey: ["features", partId],
          });
          useSketchStore
            .getState()
            .choosePlaneSpec(
              faceSpecFromDatum(response.feature.id, signature, 0),
            );
          setFacePicking(false);
        } catch (error) {
          setFacePlaneError(
            error instanceof Error
              ? error.message
              : "The sketch could not be placed on that face.",
          );
        } finally {
          setFacePlaneBusy(false);
          setPendingFaceIndex(null);
        }
      })();
    },
    [partId, tree.data, freshTreeVersion, queryClient],
  );

  /** Arm/disarm the face-pick mode (clears any stale error on toggle). */
  const togglePickFace = useCallback(() => {
    // Disarming is always allowed — a stand-down must never be blocked by the
    // thing it stands down from.
    if (facePicking) {
      setFacePlaneError(null);
      setFacePicking(false);
      return;
    }
    // PICK-2: refuse to ARM over an overlay that cannot populate. The strip's
    // prompt states the refusal (`FacePickPrompt`'s blocked reading).
    setFacePlaneError(null);
    setFacePicking(facePickRefusal === null);
  }, [facePicking, facePickRefusal]);

  /**
   * New sketch — ON the pre-selected face when there is one (UI-W3).
   *
   * Selecting a face and asking for a sketch is an unambiguous instruction, and
   * making the user re-pick the face they just picked is exactly the friction
   * the founder reported. With nothing selected this is the plane picker as
   * before; the picker is the fallback, not the toll booth.
   *
   * "Selected" means a settled pick on the current body (SKETCH-PLANE-PICK):
   * a pick left over from a cancelled Shell or Draft is not one
   * (`preselectedFace` refuses provisional picks).
   */
  const startSketch = useCallback(() => {
    const seed = preselectedFace(usePreselectStore.getState(), bodyFeatureId);
    handleNewSketch();
    if (seed !== null) {
      authorFacePlane({ signature: seed.signature });
    }
  }, [bodyFeatureId, handleNewSketch, authorFacePlane]);

  /**
   * Accept the viewport's sketch proposal (FLOW-1).
   *
   * Deliberately the SAME two calls the toolbar's Sketch -> pick-a-face flow
   * makes, in the same order and with the same arguments — `handleNewSketch()`
   * then `authorFacePlane(face)` with the overlay face the user addressed. A
   * second way to compute a sketch plane would be a second thing to keep
   * correct, and the two would drift silently: nothing would fail, the planes
   * would just stop agreeing.
   */
  const acceptSketchProposal = useCallback(
    (face: OverlayFace & { signature: PlanarFaceSignature }) => {
      handleNewSketch();
      authorFacePlane(face);
    },
    [handleNewSketch, authorFacePlane],
  );

  /**
   * Accept the viewport's EXTRUDE proposal (FLOW-B1) — the offer a sketch's own
   * solve writes on its profile.
   *
   * Deliberately the same call the band's Extrude button makes, with the noun
   * the chip named. The chip promises "the Extrude command on THIS sketch", so
   * the editor opens with that profile already in `extrude-profile`, the
   * distance focused and the drag handle live — the user re-picks nothing. It
   * does NOT commit: one more Enter does, which is the same accept vocabulary
   * one step further on.
   */
  const acceptExtrudeProposal = useCallback(
    (profileFeatureId: string) => {
      openCreateExtrude(profileFeatureId);
    },
    [openCreateExtrude],
  );
  return {
    startSketchOnFace,
    authorOffsetPlane,
    authorFacePlane,
    togglePickFace,
    startSketch,
    acceptSketchProposal,
    acceptExtrudeProposal,
  };
}

export type SketchEntry = ReturnType<typeof useSketchEntry>;
