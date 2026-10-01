/**
 * Managing the drawing's sheets once they exist: adding a sheet, re-heading
 * one in place (projection convention, paper orientation), and re-projecting
 * the drafted part. Split out of `DrawingPage.tsx` (SPLIT-DRAWINGPAGE);
 * behaviour unchanged.
 */
import { useCallback, useMemo, useState } from "react";

import { createSheet, updateView } from "../../api/drawings";
import {
  reframePinnedCentre,
  sheetDimensions,
  sheetHeaderForNewSheet,
  standardLayout,
} from "../../drawing/layout";
import {
  OTHER_CONVENTION,
  OTHER_ORIENTATION,
  type SheetOrientation,
  type SheetProjection,
  updateSheetHeader,
} from "./sheetHeader";
import type { DrawingActionContext, DrawingData } from "./useDrawingData";

export function useSheetManagement(
  data: Pick<
    DrawingData,
    | "tree"
    | "sheetCount"
    | "setActiveSheetIndex"
    | "sheet"
    | "views"
    | "docVersion"
    | "sizeValue"
    | "setScaleValue"
    | "orientationFit"
    | "paperOrientation"
    | "setOrientationOverride"
    | "effectivePartId"
  >,
  { drawingId, queryClient, setActionError }: DrawingActionContext,
) {
  const {
    tree,
    sheetCount,
    setActiveSheetIndex,
    sheet,
    views,
    docVersion,
    sizeValue,
    setScaleValue,
    orientationFit,
    paperOrientation,
    setOrientationOverride,
    effectivePartId,
  } = data;

  // Append a new (empty) sheet and switch to it (FINDINGS #18). The new sheet is
  // laid out through the SAME flow the first sheet uses — selecting it makes the
  // Set-up band + layout actions target its id (createView takes the sheet id, so
  // no per-index guesswork). Appends at the tip → its index is the old count.
  const [addingSheet, setAddingSheet] = useState(false);
  // `Sheet ${count + 1}` collides after a delete: with Sheet 1/2/3, removing
  // Sheet 2 leaves count 2, so the next add is another "Sheet 3" — two tabs
  // with the same label (the tab renders `sheet.name`). Take the lowest free
  // number instead, so names stay unique and stable across deletes.
  const nextSheetName = useMemo(() => {
    const taken = new Set((tree?.sheets ?? []).map((s) => s.sheet.name));
    let n = 1;
    while (taken.has(`Sheet ${n}`)) n += 1;
    return `Sheet ${n}`;
  }, [tree]);
  const handleAddSheet = useCallback(() => {
    if (addingSheet || sheetCount === 0) return;
    setAddingSheet(true);
    setActionError(null);
    void (async () => {
      try {
        // The SAME derivation Sheet 1 is born from (`sheetHeaderForNewSheet`) —
        // this used to be the one smart call site while the four Sheet-1 paths
        // wrote literals, which is exactly the defect REACH-3-FLOW names.
        const header = sheetHeaderForNewSheet({
          name: nextSheetName,
          size: sizeValue,
          layout: "standard",
          fit: orientationFit,
          inherit: sheet,
        });
        await createSheet(drawingId, {
          name: header.name,
          size: header.size,
          orientation: header.orientation,
          projection: header.projection,
          expected_version: docVersion,
        });
        if (header.scaleValue !== null) setScaleValue(header.scaleValue);
        await queryClient.invalidateQueries({
          queryKey: ["drawing", drawingId],
        });
        setActiveSheetIndex(sheetCount);
      } catch (error) {
        setActionError(
          error instanceof Error
            ? error.message
            : "The sheet could not be added.",
        );
      } finally {
        setAddingSheet(false);
      }
    })();
  }, [
    addingSheet,
    sheetCount,
    nextSheetName,
    drawingId,
    sizeValue,
    docVersion,
    queryClient,
    orientationFit,
    sheet,
  ]);

  // ---------------------------------------------------------------------
  // Re-heading the sheet in place (REACH-3): the projection convention and the
  // paper orientation are properties of the SHEET, so both flip through
  // `SheetUpdate` and the server re-composes. Every auto-placed view is
  // re-anchored by the composer from the sheet's own convention, so a flip
  // genuinely re-lays the drawing out — third angle puts the top view above
  // front and the right view to its right; first angle mirrors both.
  //
  // ORIENTATION additionally RE-PLACES every view onto the new paper
  // (REACH-3-FLOW P1-2). A flip used to change the `viewBox` and nothing else,
  // which for a HAND-PLACED view is not cosmetic: `auto_place:false` is honoured
  // verbatim by the composer, and a view pinned 270 mm across a landscape A4 is
  // off the edge of a 210 mm-wide portrait one.
  //
  // It does NOT re-scale, and the cell no longer claims it will. MEASURED
  // 2026-08-28 against the real stack: documents refuses a per-view re-scale on
  // a multi-view sheet with `sheet_view_scale_mismatch` (its H2 "one sheet, one
  // source, one scale" invariant), and the refusal is unavoidable — `siblings[0]`
  // always still holds the OLD scale, so the FIRST view of the four is always
  // rejected whichever order you write them in. There is no sheet-level re-scale
  // verb, so no sequence of frontend writes can re-fit a laid-out sheet.
  //
  // The half of P1-2 that was a genuine defect is therefore fixed at the
  // PROMISE, not the delivery: the fit comparison now lives on the SET-UP
  // screen's paper cell, where the scale is still free and the answer is still
  // free to give, and the post-layout cell states only what it does. That is
  // "capture intent where it forms, not afterwards" — the flow rule this ticket
  // is judged by — rather than a control quoting a scale it cannot produce.
  // The residual (an in-place sheet re-scale) is a documents-service verb;
  // filed as SHEET-RESCALE-1.
  // ---------------------------------------------------------------------
  const [reheading, setReheading] = useState(false);
  const reheadSheet = useCallback(
    (
      change:
        { projection: SheetProjection } | { orientation: SheetOrientation },
    ) => {
      if (reheading || sheet === null) return;
      const from = sheet;
      setReheading(true);
      setActionError(null);
      void (async () => {
        try {
          const rehead = await updateSheetHeader(drawingId, from.id, {
            expected_version: docVersion,
            ...change,
          });
          if ("orientation" in change && views.length > 0) {
            const next = change.orientation;
            const oldDims = sheetDimensions(from.size, from.orientation);
            const newDims = sheetDimensions(from.size, next);
            const anchors = standardLayout(newDims);
            let version = rehead.doc_version;
            for (const view of views) {
              const updated = await updateView(drawingId, view.id, {
                expected_version: version,
                // An auto-placed view re-seeds to the new paper's anchors (the
                // composer re-derives the final placement from them anyway); a
                // HAND-PLACED one keeps its composition, remapped, so the pin
                // lands on paper that exists.
                position: view.auto_place
                  ? {
                      x_mm: anchors[view.projection].x,
                      y_mm: anchors[view.projection].y,
                    }
                  : reframePinnedCentre(view.position, oldDims, newDims),
              });
              version = updated.doc_version;
            }
          }
          await queryClient.invalidateQueries({
            queryKey: ["drawing", drawingId],
          });
          await queryClient.invalidateQueries({ queryKey: ["drawing-sheet"] });
        } catch (error) {
          setActionError(
            error instanceof Error
              ? error.message
              : "The sheet could not be updated.",
          );
        } finally {
          setReheading(false);
        }
      })();
    },
    [reheading, sheet, views, drawingId, docVersion, queryClient],
  );
  const handleFlipConvention = useCallback(() => {
    if (sheet === null) return;
    reheadSheet({ projection: OTHER_CONVENTION[sheet.projection] });
  }, [sheet, reheadSheet]);
  const handleFlipOrientation = useCallback(() => {
    if (sheet === null) return;
    reheadSheet({ orientation: OTHER_ORIENTATION[sheet.orientation] });
  }, [sheet, reheadSheet]);
  /**
   * The paper control on the SET-UP screen — the one place a wrong proposal can
   * be answered before it costs anything (REACH-3-FLOW's P2 flag: the header
   * cells were post-layout only, i.e. absent from the only screen that could
   * have prevented the problem). Same gesture either side of the sheet's
   * existence: re-head the sheet if there is one, otherwise record the answer
   * the very first create will be born with.
   */
  const handleFlipPaper = useCallback(() => {
    if (sheet !== null) {
      handleFlipOrientation();
      return;
    }
    setOrientationOverride(OTHER_ORIENTATION[paperOrientation]);
  }, [sheet, handleFlipOrientation, paperOrientation]);

  const handleReproject = useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: ["drawing-part-tree", effectivePartId],
    });
    void queryClient.invalidateQueries({ queryKey: ["drawing-eval"] });
    // Re-compose the placed sheet too (the VISUAL source) so a reproject repaints.
    void queryClient.invalidateQueries({ queryKey: ["drawing-sheet"] });
  }, [queryClient, effectivePartId]);

  return {
    addingSheet,
    handleAddSheet,
    reheading,
    handleFlipConvention,
    handleFlipOrientation,
    handleFlipPaper,
    handleReproject,
  };
}
