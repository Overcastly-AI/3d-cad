/**
 * EXPORT, DERIVED ONCE — the format catalogue and the download state machine
 * that every mount of the verb reads.
 *
 * Export now appears in TWO places on a workspace, deliberately (EXPORT-1,
 * founder 2026-08-17: *"the button to export should not be with all the mass
 * properties"*). The panel strip is the NOTICE surface — it has room for "this
 * file would be partial" — and the command band is the ACTION surface, which
 * survives a panel collapse. Two surfaces, one set of facts: the formats a part
 * can be written to, and what a click is currently doing, live here so the two
 * cannot drift into saying different things about the same file. That is the
 * DRY rule applied to state, the same cure `features/partBuild.ts` applies to
 * the Solve / Status / Export claims.
 */
import { StepIcon, StlIcon } from "@loft/design";
import type { ReactNode } from "react";
import { useCallback, useState } from "react";

import {
  downloadBlob,
  type ExportedFile,
  type ExportFormat,
} from "../api/exportPart";

export interface ExportFormatEntry {
  readonly format: ExportFormat;
  /** The cell's word: a format is what an engineer recognises it by. */
  readonly label: string;
  /** What the file IS, in one or two words ("B-rep" / "Mesh"). */
  readonly caption: string;
  /** Accessible name — the verb plus what it writes. */
  readonly name: string;
  readonly icon: ReactNode;
}

/**
 * The formats a solid can be issued as, in the order both surfaces show them.
 *
 * NOTE for whoever lands EXPORT-2 (adds `3mf` + `glb`): `ExportRow.tsx` still
 * carries its own copy of this list — the two were not merged here because the
 * two changes were in flight at the same time and that file belonged to the
 * other agent. `ExportToolGroup.test.tsx` cross-checks the two lists and FAILS
 * if a format is added to one and not the other, so folding `ExportRow`'s
 * `FORMATS` into this constant is the intended next step, not an optional one.
 */
export const EXPORT_FORMATS: readonly ExportFormatEntry[] = [
  {
    format: "step",
    label: "STEP",
    caption: "B-rep",
    name: "Export STEP (exact B-rep)",
    icon: <StepIcon />,
  },
  {
    format: "stl",
    label: "STL",
    caption: "Mesh",
    name: "Export STL (faceted mesh)",
    icon: <StlIcon />,
  },
];

export interface ExportAction {
  /** The format currently being written, or null. */
  readonly busy: ExportFormat | null;
  /** The format whose last attempt failed, or null. */
  readonly failed: ExportFormat | null;
  /** Fetch the file and hand it to the browser as a named download. */
  readonly run: (format: ExportFormat) => Promise<void>;
}

/**
 * The write itself: one request in flight at a time, and a failure that is
 * remembered until the next attempt (a download that silently does nothing is
 * indistinguishable from a broken button).
 */
export function useExportAction(
  exporter: (format: ExportFormat) => Promise<ExportedFile>,
): ExportAction {
  const [busy, setBusy] = useState<ExportFormat | null>(null);
  const [failed, setFailed] = useState<ExportFormat | null>(null);

  const run = useCallback(
    async (format: ExportFormat) => {
      setBusy(format);
      setFailed(null);
      try {
        const { blob, filename } = await exporter(format);
        downloadBlob(blob, filename);
      } catch {
        setFailed(format);
      } finally {
        setBusy(null);
      }
    },
    [exporter],
  );

  return { busy, failed, run };
}
