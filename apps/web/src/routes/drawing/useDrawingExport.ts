/**
 * The drawing's exports: the client-side SVG serialize of the on-screen sheet
 * and the server-composed PDF / DXF downloads. Split out of `DrawingPage.tsx`
 * (SPLIT-DRAWINGPAGE); behaviour unchanged.
 */
import { useCallback, useRef, useState } from "react";

import {
  type DrawingExportFormat,
  exportDrawing,
} from "../../api/exportDrawing";
import { downloadBlob } from "../../api/exportPart";
import { exportSheetSvg } from "../../drawing/exportSvg";
import type { DrawingActionContext, DrawingData } from "./useDrawingData";

export function useDrawingExport(
  {
    tree,
    hasLayout,
    activeSheetId,
  }: Pick<DrawingData, "tree" | "hasLayout" | "activeSheetId">,
  { drawingId, setActionError }: Omit<DrawingActionContext, "queryClient">,
) {
  // ---------------------------------------------------------------------
  // Export SVG (#5): serialize the already-rendered sheet <svg> to a
  // standalone, self-contained .svg and hand it to the browser as a download.
  // The renderer IS the export — no second drafting engine (DRY).
  // ---------------------------------------------------------------------
  const sheetSvgRef = useRef<SVGSVGElement>(null);
  const handleExportSvg = useCallback(() => {
    const svg = sheetSvgRef.current;
    if (svg === null) return;
    setActionError(null);
    try {
      exportSheetSvg(svg, tree?.drawing.name ?? "drawing");
    } catch (error) {
      setActionError(
        error instanceof Error
          ? error.message
          : "The drawing could not be exported.",
      );
    }
  }, [tree]);

  // ---------------------------------------------------------------------
  // Server-composed export (DE-2 PDF, DE-3 DXF): the shop deliverables. Unlike
  // Export SVG (which serializes the on-screen <svg>), the gateway composes the
  // sheet from the SAME persisted placement — byte-deterministic — and streams
  // the artifact bytes back, which we hand to the browser as a named download.
  // ONE in-flight + error path drives every server format (DRY); the SVG path
  // stays separate because it is a synchronous client-side serialize.
  // ---------------------------------------------------------------------
  const [exporting, setExporting] = useState(false);
  const runServerExport = useCallback(
    (format: DrawingExportFormat) => {
      if (!hasLayout || exporting) return;
      setExporting(true);
      setActionError(null);
      void (async () => {
        try {
          const { blob, filename } = await exportDrawing(
            drawingId,
            format,
            activeSheetId,
          );
          downloadBlob(blob, filename);
        } catch (error) {
          setActionError(
            error instanceof Error
              ? error.message
              : `The drawing could not be exported to ${format.toUpperCase()}.`,
          );
        } finally {
          setExporting(false);
        }
      })();
    },
    [hasLayout, exporting, drawingId, activeSheetId],
  );
  const handleExportPdf = useCallback(
    () => runServerExport("pdf"),
    [runServerExport],
  );
  const handleExportDxf = useCallback(
    () => runServerExport("dxf"),
    [runServerExport],
  );

  return {
    sheetSvgRef,
    exporting,
    handleExportSvg,
    handleExportPdf,
    handleExportDxf,
  };
}
