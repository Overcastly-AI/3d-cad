import { exportPartTree } from "../api/exportPart";
import { ExportRow } from "./ExportRow";

export interface PartExportControlsProps {
  /** The part whose CURRENT evaluated tree is exported. */
  partId: string;
  /**
   * Whether the evaluated tree has a body to export. A sketch-only (or
   * rolled-back) tree has nothing to write, so the row goes inert and honest.
   */
  hasBody: boolean;
}

/**
 * The part workspace's EXPORT strip: issues the CURRENT part's evaluated body
 * as STEP or STL via the gateway's tree-export route — the file matches the
 * solid on screen, not a bare primitive. Binds the part exporter to the shared
 * {@link ExportRow}; disabled with a "No body" state until an extrude (or
 * other body feature) produces a solid.
 */
export function PartExportControls({
  partId,
  hasBody,
}: PartExportControlsProps) {
  return (
    <ExportRow
      testIdPrefix="part-export"
      exporter={(format) => exportPartTree(partId, format)}
      disabledReason={hasBody ? undefined : "No body"}
    />
  );
}
