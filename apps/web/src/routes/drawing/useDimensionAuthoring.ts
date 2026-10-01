/**
 * Dimension authoring and editing on the sheet: the pick state machine, the
 * place stage (pointer, typed offset, grab-to-move), delete and the
 * re-anchor heal. Split out of `DrawingPage.tsx` (SPLIT-DRAWINGPAGE);
 * behaviour unchanged.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import {
  type DimensionParams,
  createDimension,
  deleteDimension,
} from "../../api/drawings";
import {
  type DimensionGrabEvent,
  type EdgePickEvent,
  type EndpointPickEvent,
  edgeKey,
  vertexKey,
} from "../../components/DrawingSheet";
import {
  IDLE,
  type AuthoringState,
  type DimensionAction,
  armPair,
  armedSignatures,
  beginPlacement,
  beginReplacement,
  buildDimension,
  commitParams,
  menuActions,
  menuAnchor,
  movePlacement,
  pickEdge,
  pickEndpoint,
  pickHint,
  placementMoved,
  placementOffsetMm,
  placementReplaces,
  placementTarget,
  selectedEndpoints,
  setPlacementOffset,
} from "../../drawing/authoring";
import {
  healDimensionParams,
  reanchoredAnchor,
} from "../../drawing/anchorHeal";
import {
  ghostFor,
  offsetPlacementFromComposed,
  textPlacementFromComposed,
} from "../../drawing/placement";
import type { DrawingActionContext, DrawingData } from "./useDrawingData";

export function useDimensionAuthoring(
  {
    docVersion,
    dimensions,
    composed,
    measuredById,
  }: Pick<
    DrawingData,
    "docVersion" | "dimensions" | "composed" | "measuredById"
  >,
  { drawingId, queryClient, setActionError }: DrawingActionContext,
) {
  // ---------------------------------------------------------------------
  // Dimension authoring: pick sheet geometry → choose a valid type → persist it
  // (CRUD) → the re-evaluate measures + renders it model-true. Most types take
  // one pick; angular and edge-to-edge take two straight edges and point-to-point
  // two endpoints, staged through the pure `authoring` state machine (§3.1/§3.3).
  // ---------------------------------------------------------------------
  const [authoring, setAuthoring] = useState<AuthoringState>(IDLE);
  const [dimBusy, setDimBusy] = useState(false);

  // Highlight sets the sheet reads: the single selected edge, all armed edges,
  // and the selected endpoint handles for the in-progress pick.
  const armed = armedSignatures(authoring);
  const selectedEdgeKey = armed[0]
    ? edgeKey(armed[0].projection, armed[0].sourceEdge)
    : null;
  const armedEdgeKeys = armed.map((a) => edgeKey(a.projection, a.sourceEdge));
  const selectedVertexKeys = selectedEndpoints(authoring).map((e) =>
    vertexKey(e.projection, e.sourceEdge, e.endpoint),
  );
  // A point-to-point pick is in progress — reveal every endpoint handle (and put
  // it in the tab order) so the second vertex is reachable on any edge; at rest
  // handles only appear on their edge's hover/focus (frontend-QA P2).
  const endpointPickActive =
    authoring.kind === "one-endpoint" || authoring.kind === "p2p-ready";
  const menuActionList = menuActions(authoring);
  const anchor = menuAnchor(authoring);
  const hint = pickHint(authoring);
  // The live placement: the ghost the sheet draws and the offset it reads out.
  const placingGhost =
    authoring.kind === "placing" ? ghostFor(authoring.target) : null;
  const placingOffsetMm = placementOffsetMm(authoring);

  const handlePickEdge = useCallback((event: EdgePickEvent) => {
    setAuthoring((state) =>
      pickEdge(state, {
        projection: event.projection,
        viewId: event.viewId,
        sourceEdge: event.sourceEdge,
        primitive: event.primitive,
        clientX: event.clientX,
        clientY: event.clientY,
        geometry: event.geometry,
      }),
    );
  }, []);

  const handlePickEndpoint = useCallback((event: EndpointPickEvent) => {
    setAuthoring((state) =>
      pickEndpoint(state, {
        projection: event.projection,
        viewId: event.viewId,
        sourceEdge: event.sourceEdge,
        endpoint: event.endpoint,
        clientX: event.clientX,
        clientY: event.clientY,
        at: event.at,
        viewAnchor: event.viewAnchor,
      }),
    );
  }, []);

  /** POST the authored dimension (with whatever placement it carries) + refresh. */
  const persistDimension = useCallback(
    (viewId: string, params: DimensionParams) => {
      setDimBusy(true);
      setActionError(null);
      void (async () => {
        try {
          await createDimension(drawingId, viewId, {
            dimension: params,
            expected_version: docVersion,
          });
          await queryClient.invalidateQueries({
            queryKey: ["drawing", drawingId],
          });
          setAuthoring(IDLE);
        } catch (error) {
          setActionError(
            error instanceof Error
              ? error.message
              : "The dimension could not be added.",
          );
        } finally {
          setDimBusy(false);
        }
      })();
    },
    [drawingId, docVersion, queryClient],
  );

  const handleChooseAction = useCallback(
    (action: DimensionAction) => {
      if (dimBusy) return;
      // "Angle" / "Distance to edge" arm a second-edge pick rather than
      // authoring immediately; the intent orders the menu that follows.
      if (action === "start_angular" || action === "start_edge_to_edge") {
        const intent = action === "start_angular" ? "angular" : "edge_to_edge";
        setAuthoring((state) => armPair(state, intent));
        return;
      }
      const built = buildDimension(authoring, action);
      if (built === null) return;
      // The measurement is settled — now say WHERE it goes. The ghost tracks the
      // pointer from the auto-placement default, so the user is adjusting a real
      // proposal (REACH-3). A pick that carried no composed geometry has nothing
      // to place against and authors straight away, exactly as it always did.
      const target = placementTarget(authoring, action);
      if (target !== null) {
        setAuthoring((state) =>
          beginPlacement(state, built.viewId, built.params, target),
        );
        return;
      }
      persistDimension(built.viewId, built.params);
    },
    [authoring, dimBusy, persistDimension],
  );

  /** Track the pointer across the paper while a placement is live. */
  const handlePlacePointer = useCallback((at: { x: number; y: number }) => {
    setAuthoring((state) => movePlacement(state, at));
  }, []);

  /** Set when a grab begins from the sheet — see {@link handlePlaceClick}. */
  const grabClickGuard = useRef(false);

  /**
   * MOVE a dimension already on the paper: re-enter the same PLACE stage it was
   * born in (REACH-3's own commit named "not afterwards" as the defect and
   * fixed only the first half — frontend-QA P1-E).
   *
   * The placement is recovered from the COMPOSED annotation rather than from
   * the stored params, because most dimensions on a sheet have no stored
   * placement at all — the composer auto-placed them, and it is exactly those
   * the user most often wants to nudge out of the way.
   */
  const handleGrabDimension = useCallback(
    (event: DimensionGrabEvent) => {
      if (dimBusy) return;
      const row = dimensions.find((d) => d.id === event.dimensionId);
      if (row === undefined) return;
      const target =
        event.dim.dimension_type === "linear"
          ? offsetPlacementFromComposed(event.dim.lines, event.viewAnchor)
          : textPlacementFromComposed(event.dim.lines, event.dim.text);
      if (target === null) return;
      setAuthoring(
        beginReplacement(row.id, row.view_id, row.dimension, target),
      );
    },
    [dimBusy, dimensions],
  );

  /**
   * Commit the live placement — the click that puts the dimension down.
   *
   * Safe to read `authoring` from the closure ONLY because the sheet reports the
   * pointer on `pointerdown` as well as on `pointermove`: a discrete event
   * flushes before the click that follows it, so this sees the placement the
   * user is looking at. See the `onPointerDown` note on the place surface for
   * what went wrong when it did not.
   */
  const handlePlaceCommit = useCallback(() => {
    if (dimBusy) return;
    const replaces = placementReplaces(authoring);
    const commit = commitParams(authoring);
    if (commit === null) {
      // A re-placement that never moved: nothing to write, and leaving the
      // ghost up would be a dead end. Put the dimension back and stand down.
      if (replaces !== null) setAuthoring(IDLE);
      return;
    }
    if (replaces === null) {
      persistDimension(commit.viewId, commit.params);
      return;
    }
    // No PATCH route for a dimension, so: APPEND the moved copy, then DELETE
    // the original. That order is deliberate and matches `handleHealDimension`
    // — a failure between the two leaves a visible duplicate the user can
    // remove, never a lost dimension.
    setDimBusy(true);
    setActionError(null);
    void (async () => {
      try {
        const created = await createDimension(drawingId, commit.viewId, {
          dimension: commit.params,
          expected_version: docVersion,
        });
        await deleteDimension(drawingId, replaces, created.doc_version);
        await queryClient.invalidateQueries({
          queryKey: ["drawing", drawingId],
        });
        setAuthoring(IDLE);
      } catch (error) {
        setActionError(
          error instanceof Error
            ? error.message
            : "The dimension could not be moved.",
        );
      } finally {
        setDimBusy(false);
      }
    })();
  }, [
    authoring,
    dimBusy,
    persistDimension,
    drawingId,
    docVersion,
    queryClient,
  ]);

  /** The end of a press-drag: commit only if the placement actually moved, so
   * a bare press (click-to-grab) leaves the ghost up for a second click. */
  const handlePlaceRelease = useCallback(() => {
    if (placementMoved(authoring)) handlePlaceCommit();
  }, [authoring, handlePlaceCommit]);

  /**
   * A CLICK on the paper drops the placement — with one exception.
   *
   * THE TAIL OF THE GRAB PRESS IS NOT A DROP. Pressing a placed dimension
   * opens the stage on `pointerdown`, and the release that ends that same
   * press produces a `click` — which Chrome retargets onto the place surface,
   * because the grab the press started on has just been unmounted (the
   * dimension is drawn as the ghost while it moves). Acting on it would make a
   * bare click on a dimension a no-op that opens and shuts the stage in one
   * frame. Exactly one click is swallowed per grab; every click after it drops
   * the dimension normally, and the guard is on the CLICK path only so a
   * press-drag still commits on release.
   */
  const handlePlaceClick = useCallback(() => {
    if (grabClickGuard.current) {
      grabClickGuard.current = false;
      return;
    }
    handlePlaceCommit();
  }, [handlePlaceCommit]);

  /** The sheet's grab route — the only one that arms the click guard, because
   * it is the only one whose gesture ends in a click on the paper. */
  const handleGrabFromSheet = useCallback(
    (event: DimensionGrabEvent) => {
      grabClickGuard.current = true;
      handleGrabDimension(event);
    },
    [handleGrabDimension],
  );

  /** The panel's Move — the same grab, found by id instead of by pointer. */
  const handleMoveFromPanel = useCallback(
    (dimensionId: string) => {
      const row = dimensions.find((d) => d.id === dimensionId);
      if (row === undefined || composed === undefined) return;
      for (const view of composed.views ?? []) {
        for (const dim of view.dimensions ?? []) {
          if (dim.kind !== "measured" || dim.dimension_id !== dimensionId) {
            continue;
          }
          handleGrabDimension({
            dimensionId,
            viewId: row.view_id,
            projection: view.projection,
            dim,
            viewAnchor: { x: view.anchor.x_mm, y: view.anchor.y_mm },
          });
          return;
        }
      }
    },
    [composed, dimensions, handleGrabDimension],
  );

  // --- the typed route to the offset (P1-D) -------------------------------
  // The offset field is CONTROLLED by the placement (the pointer moves it at
  // pointer rate) except while the user has it focused, when the text is
  // theirs: a controlled field rewritten mid-keystroke eats characters. A
  // non-null draft means "the user is typing; leave their text alone".
  const [offsetDraft, setOffsetDraft] = useState<string | null>(null);
  const offsetFieldRef = useRef<HTMLInputElement | null>(null);
  const offsetText =
    offsetDraft ?? (placingOffsetMm !== null ? placingOffsetMm.toFixed(2) : "");
  useEffect(() => {
    if (authoring.kind !== "placing") {
      setOffsetDraft(null);
      // Never leak a swallowed click into a later gesture.
      grabClickGuard.current = false;
    }
  }, [authoring.kind]);

  const handleOffsetTyped = useCallback((text: string) => {
    setOffsetDraft(text);
    const value = Number(text);
    // A half-typed "-" or "1." parses to NaN; hold the placement where it is
    // and let the digits arrive rather than snapping the ghost to nothing.
    if (text.trim() !== "" && Number.isFinite(value)) {
      setAuthoring((state) => setPlacementOffset(state, value));
    }
  }, []);

  // The window key handler below must see the CURRENT placement without being
  // re-registered on every pointer move (a placement changes state at pointer
  // rate), so the two things it needs live in refs.
  const placingRef = useRef(false);
  const commitPlacementRef = useRef(handlePlaceCommit);
  useEffect(() => {
    placingRef.current = authoring.kind === "placing";
    commitPlacementRef.current = handlePlaceCommit;
  }, [authoring, handlePlaceCommit]);

  const handleDeleteDimension = useCallback(
    (dimensionId: string) => {
      if (dimBusy) return;
      setDimBusy(true);
      setActionError(null);
      void (async () => {
        try {
          await deleteDimension(drawingId, dimensionId, docVersion);
          await queryClient.invalidateQueries({
            queryKey: ["drawing", drawingId],
          });
        } catch (error) {
          setActionError(
            error instanceof Error
              ? error.message
              : "The dimension could not be deleted.",
          );
        } finally {
          setDimBusy(false);
        }
      })();
    },
    [dimBusy, drawingId, docVersion, queryClient],
  );

  // Confirm a re-anchored reference (topological-naming §11 / audit N1): the
  // part changed, the stored stage-1 signature no longer matched verbatim, and
  // geometry re-anchored the dimension on its rebuild invariant — reporting
  // `tier: "durable"` plus the signature of the edge it landed on. One click
  // stores that signature, so the reference stops being a re-derived guess.
  //
  // There is no PATCH route for a dimension, so the write is an APPEND of the
  // healed dimension followed by a DELETE of the stale one. That order matters:
  // a failure between the two leaves a visible duplicate the user can remove,
  // never a lost dimension.
  const handleHealDimension = useCallback(
    (dimensionId: string) => {
      if (dimBusy) return;
      const dim = dimensions.find((d) => d.id === dimensionId);
      const anchor = reanchoredAnchor(measuredById.get(dimensionId));
      if (dim === undefined || anchor === null) return;
      const healed = healDimensionParams(dim.dimension, anchor);
      if (healed === null) return;
      setDimBusy(true);
      setActionError(null);
      void (async () => {
        try {
          const created = await createDimension(drawingId, dim.view_id, {
            dimension: healed,
            expected_version: docVersion,
          });
          await deleteDimension(drawingId, dim.id, created.doc_version);
          await queryClient.invalidateQueries({
            queryKey: ["drawing", drawingId],
          });
        } catch (error) {
          setActionError(
            error instanceof Error
              ? error.message
              : "The reference could not be confirmed.",
          );
        } finally {
          setDimBusy(false);
        }
      })();
    },
    [dimBusy, dimensions, measuredById, drawingId, docVersion, queryClient],
  );

  return {
    authoring,
    setAuthoring,
    dimBusy,
    selectedEdgeKey,
    armedEdgeKeys,
    selectedVertexKeys,
    endpointPickActive,
    menuActionList,
    anchor,
    hint,
    placingGhost,
    placingOffsetMm,
    handlePickEdge,
    handlePickEndpoint,
    handleChooseAction,
    handlePlacePointer,
    handlePlaceClick,
    handlePlaceRelease,
    handleGrabFromSheet,
    handleMoveFromPanel,
    setOffsetDraft,
    offsetFieldRef,
    offsetText,
    handleOffsetTyped,
    placingRef,
    commitPlacementRef,
    handleDeleteDimension,
    handleHealDimension,
  };
}
