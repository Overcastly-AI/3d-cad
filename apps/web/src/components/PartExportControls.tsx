import { partExportBinding } from "../features/partExport";
import type { PartBuild } from "../features/partBuild";
import { ExportRow } from "./ExportRow";

export interface PartExportControlsProps {
  /** The part whose CURRENT evaluated tree is exported. */
  partId: string;
  /**
   * What the workspace knows about the body on screen — the SAME facts the
   * Solve and Status cells read (`features/partBuild.ts`). The gate is derived
   * from it, never from "is there a mesh id": the strict-prefix rule hands back
   * a mesh for the last-good PREFIX, so `hasBody` was true over a truncated
   * rebuild and the row said "Ready" about a file that was missing every
   * feature from the failure onward (AUDIT-ENGINEERING J2).
   */
  build: PartBuild;
}

/**
 * The part workspace's EXPORT strip: issues the CURRENT part's evaluated body
 * as STEP or STL via the gateway's tree-export route — the file matches the
 * solid on screen, not a bare primitive.
 *
 * The strip refuses to write a file it cannot vouch for. A feature error or an
 * unverified rebuild makes it inert and names what to fix; a deliberate travel
 * stop still exports, with `Partial` in the cell AND `-partial` in the filename
 * (see `exportGate` for why those two prefixes get different answers).
 *
 * The gate and the request that honours it come from `features/partExport.ts`,
 * which the command band's EXPORT tool group reads too: the strip is the NOTICE
 * surface ("this file would be partial"), the band is the ACTION surface that
 * survives a panel collapse, and neither derives its own answer (EXPORT-1).
 */
export function PartExportControls({ partId, build }: PartExportControlsProps) {
  const { gate, exporter } = partExportBinding(partId, build);
  return (
    <ExportRow
      testIdPrefix="part-export"
      exporter={exporter}
      disabledReason={gate.blockedReason}
      statusLabel={gate.partial ? "Partial" : undefined}
      notice={
        gate.notice === null
          ? null
          : {
              text: gate.notice,
              tone: gate.state === "feature-error" ? "flag" : "quiet",
            }
      }
      state={gate.state}
    />
  );
}
