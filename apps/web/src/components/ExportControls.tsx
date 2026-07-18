import { exportBox } from "../api/exportPart";
import type { BoxParams } from "../api/tessellate";
import { ExportRow } from "./ExportRow";

export interface ExportControlsProps {
  /** Current validated dimensions — the part the file is issued for. */
  dimensions: BoxParams;
}

/**
 * The EXPORT row of the first-light box title block. Binds the box exporter to
 * the shared {@link ExportRow} strip (STEP / STL) — same ruled anatomy as the
 * part workspace's export, one component (DRY).
 */
export function ExportControls({ dimensions }: ExportControlsProps) {
  return (
    <ExportRow
      testIdPrefix="export"
      exporter={(format) => exportBox(format, dimensions)}
    />
  );
}
