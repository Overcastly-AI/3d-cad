/**
 * WHAT THE PART WORKSPACE EXPORTS — bound once, read by both surfaces.
 *
 * The gate (`exportGate`) decides whether a file may be written and whether it
 * would be a prefix; this pairs that decision with the request that honours it,
 * so the Inspector's strip and the command band's tool group cannot disagree
 * about either the answer or the FILENAME. Two mounts of one verb, one binding
 * (EXPORT-1).
 */
import {
  exportPartTree,
  markFilenamePartial,
  type ExportedFile,
  type ExportFormat,
} from "../api/exportPart";
import { exportGate, type ExportGate, type PartBuild } from "./partBuild";

export interface PartExportBinding {
  /** Issue the part's CURRENT evaluated tree, named as the gate requires. */
  readonly exporter: (format: ExportFormat) => Promise<ExportedFile>;
  /** The decision itself — blocked reason, partial flag, state name. */
  readonly gate: ExportGate;
}

export function partExportBinding(
  partId: string,
  build: PartBuild,
): PartExportBinding {
  const gate = exportGate(build);
  return {
    gate,
    exporter: async (format: ExportFormat) => {
      const file = await exportPartTree(partId, format);
      // A file outlives the screen that explained it: a deliberate travel stop
      // still exports, and says so in the NAME as well as in the cell.
      return gate.partial
        ? { ...file, filename: markFilenamePartial(file.filename) }
        : file;
    },
  };
}
