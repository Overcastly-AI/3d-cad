/**
 * Draft this assembly (§7): create a drawing named after it and open the
 * sheet with the assembly ALREADY chosen as the source (`?source=`), so the
 * next step is visible from where the user already is rather than hunted for
 * in another register. The sheet is not laid out here on purpose — paper size
 * and scale are the drafter's first two decisions, and pre-empting them would
 * trade one hunt for a re-layout.
 *
 * Split from `AssemblyPage` (file-size ratchet), unchanged.
 */
import { useNavigate } from "@tanstack/react-router";
import { useCallback, useState } from "react";

import { DrawingNameTakenError, createDrawing } from "../api/drawings";

export function useOpenDrawing(
  assemblyId: string,
  assemblyName: string | undefined,
  onError: (message: string | null) => void,
): { drawingBusy: boolean; openDrawing: () => void } {
  const navigate = useNavigate();
  const [drawingBusy, setDrawingBusy] = useState(false);
  const openDrawing = useCallback(() => {
    if (drawingBusy || assemblyName === undefined) return;
    setDrawingBusy(true);
    onError(null);
    void (async () => {
      try {
        // A name is unique per owner, so an assembly drafted twice needs a
        // suffix rather than a failure (same retry the part editor's flat
        // pattern uses — one register, one convention).
        const baseName = `${assemblyName} — drawing`;
        let drawing = null;
        for (let attempt = 0; attempt < 6 && drawing === null; attempt += 1) {
          const name = attempt === 0 ? baseName : `${baseName} ${attempt + 1}`;
          try {
            drawing = await createDrawing(name);
          } catch (error) {
            if (error instanceof DrawingNameTakenError) continue;
            throw error;
          }
        }
        if (drawing === null) {
          throw new Error("A drawing for this assembly already exists.");
        }
        await navigate({
          to: "/drawings/$drawingId",
          params: { drawingId: drawing.id },
          search: { source: assemblyId },
        });
      } catch (error) {
        onError(
          error instanceof Error
            ? error.message
            : "The drawing could not be created.",
        );
      } finally {
        setDrawingBusy(false);
      }
    })();
  }, [drawingBusy, assemblyName, navigate, assemblyId, onError]);
  return { drawingBusy, openDrawing };
}
