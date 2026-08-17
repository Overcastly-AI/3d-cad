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
import { GlbIcon, StepIcon, StlIcon, ThreeMfIcon } from "@loft/design";
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
 * THE single list, as of EXPORT-2: `ExportRow.tsx` used to carry a second copy
 * (left behind deliberately while EXPORT-1 and EXPORT-2 were in flight at once)
 * and now reads this one. `ExportToolGroup.test.tsx` still cross-checks that
 * the two surfaces render the same set, so a format added to one mount and not
 * the other fails loudly rather than shipping a workspace where the panel and
 * the band disagree about what a part can be written as.
 *
 * Order is a claim about intent, not alphabetical: **STEP first** because it is
 * the only lossless one and the answer to "send this to a machine shop"; then
 * the three faceted formats in descending fidelity of what they carry — STL
 * (triangles, no units), 3MF (triangles + declared millimetres + one object per
 * body: what a slicer actually wants), GLB (triangles for a screen, metres and
 * Y-up per the glTF spec). STL stays ahead of 3MF because it is what people
 * reach for by name today; the captions are what tell them 3MF is the better
 * print file.
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
  {
    format: "3mf",
    label: "3MF",
    caption: "Print",
    name: "Export 3MF (faceted mesh with units, for slicers)",
    icon: <ThreeMfIcon />,
  },
  {
    format: "glb",
    label: "GLB",
    caption: "Share",
    name: "Export GLB (binary glTF, for viewers and rendering)",
    icon: <GlbIcon />,
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
