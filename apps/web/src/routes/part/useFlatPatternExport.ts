/**
 * The sheet-metal exports: the flat-pattern drawing and the DXF cut path.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { useCallback } from "react";

import { downloadBlob, exportPartFlatPatternDxf } from "../../api/exportPart";
import {
  createDrawing,
  createSheet,
  createView,
  DrawingNameTakenError,
} from "../../api/drawings";
import { sheetDimensions, sheetHeaderForNewSheet } from "../../drawing/layout";
import type { PartDocument } from "./usePartDocument";
import type { ActionFlags } from "./useActionFlags";

type FlatPatternExportParams = Pick<
  PartDocument,
  "partId" | "navigate" | "part"
> &
  Pick<
    ActionFlags,
    | "flatPatternBusy"
    | "setFlatPatternBusy"
    | "setFlatPatternError"
    | "flatDxfBusy"
    | "setFlatDxfBusy"
  >;

export function useFlatPatternExport({
  partId,
  navigate,
  part,
  flatPatternBusy,
  setFlatPatternBusy,
  setFlatPatternError,
  flatDxfBusy,
  setFlatDxfBusy,
}: FlatPatternExportParams) {
  // Flat pattern (sheet-metal.md §7): unfold the sheet body onto a lone drawing
  // sheet, so the model → flatten loop is click-through from the part. It
  // creates a drawing named after the part (a numeric suffix dodges a name
  // clash), a sheet, and a single flat_pattern view, then opens the drawing —
  // where the reused flat-pattern renderer draws the blank + bend table. A
  // non-sheet-metal part composes an honest `flat_pattern_not_sheet_metal` view
  // there, never a crash.
  const openFlatPattern = useCallback(() => {
    if (flatPatternBusy) return;
    setFlatPatternBusy(true);
    setFlatPatternError(null);
    void (async () => {
      try {
        const baseName = `${part.data?.name ?? "Part"} — flat pattern`;
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
          throw new Error("A drawing for this flat pattern already exists.");
        }
        // The SAME header derivation every other create path uses
        // (REACH-3-FLOW): a lone flat-pattern sheet, so it takes the shop
        // default paper rather than a proposal — the four-view fit the proposal
        // reads does not model an unfolded blank, and this hand-off has no
        // sheet to inherit a convention from either.
        const header = sheetHeaderForNewSheet({
          name: "Sheet 1",
          size: "A4",
          layout: "lone",
          fit: null,
          inherit: null,
        });
        const sheet = await createSheet(drawing.id, {
          name: header.name,
          size: header.size,
          orientation: header.orientation,
          projection: header.projection,
          expected_version: drawing.doc_version,
        });
        const dims = sheetDimensions(header.size, header.orientation);
        await createView(drawing.id, sheet.sheet.id, {
          projection: "flat_pattern",
          ref_document_id: partId,
          ref_document_kind: "part",
          scale: { numerator: 1, denominator: 1 },
          position: { x_mm: dims.width / 2, y_mm: dims.height / 2 },
          auto_place: true,
          expected_version: sheet.doc_version,
        });
        await navigate({
          to: "/drawings/$drawingId",
          params: { drawingId: drawing.id },
        });
      } catch (error) {
        setFlatPatternError(
          error instanceof Error
            ? error.message
            : "The flat pattern could not be opened.",
        );
      } finally {
        setFlatPatternBusy(false);
      }
    })();
  }, [flatPatternBusy, part.data, partId, navigate]);

  // Flat-pattern DXF (AUDIT-PRODUCT F-2a): the cut path a laser/turret vendor
  // asks for by name, straight from the part — no drawing sheet to author, and
  // no A4 border and title block to delete afterwards. 1:1 by construction on
  // the server, so there is nothing to get wrong here.
  const exportFlatDxf = useCallback(() => {
    if (flatDxfBusy) return;
    setFlatDxfBusy(true);
    setFlatPatternError(null);
    void (async () => {
      try {
        const file = await exportPartFlatPatternDxf(partId);
        downloadBlob(file.blob, file.filename);
      } catch (error) {
        setFlatPatternError(
          error instanceof Error
            ? error.message
            : "The flat-pattern DXF could not be written.",
        );
      } finally {
        setFlatDxfBusy(false);
      }
    })();
  }, [flatDxfBusy, partId]);
  return { openFlatPattern, exportFlatDxf };
}

export type FlatPatternExport = ReturnType<typeof useFlatPatternExport>;
