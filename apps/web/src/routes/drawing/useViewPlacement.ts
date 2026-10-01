/**
 * Drag-to-place for the sheet's views: persist a dragged centre, return one
 * view (or the check strip's set) to auto-layout. Split out of
 * `DrawingPage.tsx` (SPLIT-DRAWINGPAGE); behaviour unchanged.
 */
import { useCallback, useState } from "react";

import { type ViewProjection, updateView } from "../../api/drawings";
import type { DrawingActionContext, DrawingData } from "./useDrawingData";

export function useViewPlacement(
  { docVersion, views }: Pick<DrawingData, "docVersion" | "views">,
  { drawingId, queryClient, setActionError }: DrawingActionContext,
) {
  // ---------------------------------------------------------------------
  // Drag-to-place: the sheet reports a dragged/nudged view centre (sheet mm,
  // y-up); we persist it with `auto_place: false` so the composer honours it
  // verbatim — the placement survives reload. "Reset" returns the view to
  // bounds-aware auto-layout. One in-flight flag serialises the OCC writes.
  // ---------------------------------------------------------------------
  const [placingView, setPlacingView] = useState(false);
  const handlePlaceView = useCallback(
    (viewId: string, position: { x_mm: number; y_mm: number }) => {
      if (placingView) return;
      setPlacingView(true);
      setActionError(null);
      void (async () => {
        try {
          await updateView(drawingId, viewId, {
            expected_version: docVersion,
            position,
            auto_place: false,
          });
          await queryClient.invalidateQueries({
            queryKey: ["drawing", drawingId],
          });
          void queryClient.invalidateQueries({ queryKey: ["drawing-sheet"] });
        } catch (error) {
          setActionError(
            error instanceof Error
              ? error.message
              : "The view could not be moved.",
          );
        } finally {
          setPlacingView(false);
        }
      })();
    },
    [placingView, drawingId, docVersion, queryClient],
  );
  const handleResetView = useCallback(
    (viewId: string) => {
      if (placingView) return;
      setPlacingView(true);
      setActionError(null);
      void (async () => {
        try {
          await updateView(drawingId, viewId, {
            expected_version: docVersion,
            auto_place: true,
          });
          await queryClient.invalidateQueries({
            queryKey: ["drawing", drawingId],
          });
          void queryClient.invalidateQueries({ queryKey: ["drawing-sheet"] });
        } catch (error) {
          setActionError(
            error instanceof Error
              ? error.message
              : "The view could not be returned to auto-layout.",
          );
        } finally {
          setPlacingView(false);
        }
      })();
    },
    [placingView, drawingId, docVersion, queryClient],
  );

  // The sheet-check strip's fix action (audit N2): return the named views to
  // bounds-aware auto-layout in ONE gesture. A collision only ever involves
  // hand-placed views the composer was told to honour verbatim, so undoing that
  // intent IS the fix — and it is the same `auto_place: true` write the per-view
  // AUTO grip sends, threaded through the bumped version so a pair resets in a
  // single click without a stale-OCC race.
  const handleAutoPlaceViews = useCallback(
    (projections: readonly ViewProjection[]) => {
      if (placingView || projections.length === 0) return;
      setPlacingView(true);
      setActionError(null);
      void (async () => {
        try {
          let version = docVersion;
          for (const projection of projections) {
            const view = views.find((v) => v.projection === projection);
            if (view === undefined) continue;
            const updated = await updateView(drawingId, view.id, {
              expected_version: version,
              auto_place: true,
            });
            version = updated.doc_version;
          }
          await queryClient.invalidateQueries({
            queryKey: ["drawing", drawingId],
          });
          void queryClient.invalidateQueries({ queryKey: ["drawing-sheet"] });
        } catch (error) {
          setActionError(
            error instanceof Error
              ? error.message
              : "The views could not be returned to auto-layout.",
          );
        } finally {
          setPlacingView(false);
        }
      })();
    },
    [placingView, views, drawingId, docVersion, queryClient],
  );

  return {
    placingView,
    handlePlaceView,
    handleResetView,
    handleAutoPlaceViews,
  };
}
