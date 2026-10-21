/**
 * The parts list's structure: Top level, Indented or Parts only
 * (DRAWING-PARTS-LIST-LEVEL), SolidWorks' BOM types. The choice is stored on
 * the sheet, so it is a sheet write: it bumps `doc_version`, which re-keys the
 * BOM query, and the server numbers the list in the new structure. While the
 * write is in flight the control shows the choice the user just made.
 */
import { useCallback, useState } from "react";

import { updateSheet, type PartsListStructure } from "../../api/drawings";
import type { DrawingActionContext, DrawingData } from "./useDrawingData";

export function usePartsListStructure(
  { docVersion, sheet }: Pick<DrawingData, "docVersion" | "sheet">,
  { drawingId, queryClient, setActionError }: DrawingActionContext,
) {
  const [pending, setPending] = useState<PartsListStructure | null>(null);
  const stored: PartsListStructure = sheet?.parts_list_structure ?? "top_level";

  const setStructure = useCallback(
    (structure: PartsListStructure) => {
      if (sheet === null || pending !== null || structure === stored) return;
      setPending(structure);
      setActionError(null);
      void (async () => {
        try {
          await updateSheet(drawingId, sheet.id, {
            expected_version: docVersion,
            parts_list_structure: structure,
          });
          await queryClient.invalidateQueries({
            queryKey: ["drawing", drawingId],
          });
        } catch (error) {
          setActionError(
            error instanceof Error
              ? error.message
              : "The parts list structure could not be changed.",
          );
        } finally {
          setPending(null);
        }
      })();
    },
    [
      sheet,
      pending,
      stored,
      drawingId,
      docVersion,
      queryClient,
      setActionError,
    ],
  );

  return {
    partsListStructure: pending ?? stored,
    partsListBusy: pending !== null,
    setPartsListStructure: setStructure,
  };
}
