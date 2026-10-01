/**
 * Free-text note annotations on the sheet: add (stacked below the last) and
 * delete. Split out of `DrawingPage.tsx` (SPLIT-DRAWINGPAGE); behaviour
 * unchanged.
 */
import { useCallback, useState } from "react";

import { drawing } from "@loft/design";

import { createAnnotation, deleteAnnotation } from "../../api/drawings";
import type { DrawingActionContext, DrawingData } from "./useDrawingData";

export function useDrawingNotes(
  {
    docVersion,
    sheet,
    composed,
    annotations,
  }: Pick<DrawingData, "docVersion" | "sheet" | "composed" | "annotations">,
  { drawingId, queryClient, setActionError }: DrawingActionContext,
) {
  // ---------------------------------------------------------------------
  // Note annotations: author a free-text note → persist it (CRUD) → the
  // re-compose places it at its sheet point and the sheet draws it from
  // `ComposedSheet.notes` (design §2.2). A note bumps `doc_version`, so the
  // compose query (keyed on it) refetches with the note — one placement source.
  // ---------------------------------------------------------------------
  const [noteBusy, setNoteBusy] = useState(false);

  const refetchDrawingAndSheet = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["drawing", drawingId] });
    // The composed sheet is keyed on `doc_version` (bumped by the write) so it
    // refetches on its own, but invalidate it too so the note appears at once.
    void queryClient.invalidateQueries({ queryKey: ["drawing-sheet"] });
  }, [queryClient, drawingId]);

  const handleAddNote = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (trimmed.length === 0 || noteBusy || sheet === null) return;
      setNoteBusy(true);
      setActionError(null);
      // A default anchor just inside the top-left border, each new note stacked
      // below the last so they never land on top of one another (v1 has no
      // drag-to-place yet — the note is placed verbatim in final sheet-mm space).
      const margin = composed?.margin_mm ?? 10;
      const x = margin + 6;
      const y = margin + 12 + annotations.length * (drawing.noteTextMm + 3);
      void (async () => {
        try {
          await createAnnotation(drawingId, sheet.id, {
            annotation: {
              type: "note",
              text: trimmed,
              position: { x_mm: x, y_mm: y },
            },
            expected_version: docVersion,
          });
          await refetchDrawingAndSheet();
        } catch (error) {
          setActionError(
            error instanceof Error
              ? error.message
              : "The note could not be added.",
          );
        } finally {
          setNoteBusy(false);
        }
      })();
    },
    [
      noteBusy,
      sheet,
      composed,
      annotations.length,
      drawingId,
      docVersion,
      refetchDrawingAndSheet,
    ],
  );

  const handleDeleteNote = useCallback(
    (annotationId: string) => {
      if (noteBusy) return;
      setNoteBusy(true);
      setActionError(null);
      void (async () => {
        try {
          await deleteAnnotation(drawingId, annotationId, docVersion);
          await refetchDrawingAndSheet();
        } catch (error) {
          setActionError(
            error instanceof Error
              ? error.message
              : "The note could not be deleted.",
          );
        } finally {
          setNoteBusy(false);
        }
      })();
    },
    [noteBusy, drawingId, docVersion, refetchDrawingAndSheet],
  );

  return { noteBusy, handleAddNote, handleDeleteNote };
}
