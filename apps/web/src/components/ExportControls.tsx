import { PanelActionCell } from "@loft/design";
import { useState } from "react";

import { downloadBlob, exportBox, type ExportFormat } from "../api/exportPart";
import type { BoxParams } from "../api/tessellate";

export interface ExportControlsProps {
  /** Current validated dimensions — the part the file is issued for. */
  dimensions: BoxParams;
}

const FORMATS: ReadonlyArray<{
  format: ExportFormat;
  label: string;
  caption: string;
  name: string;
}> = [
  {
    format: "step",
    label: "STEP",
    caption: "B-rep",
    name: "Export STEP (exact B-rep)",
  },
  {
    format: "stl",
    label: "STL",
    caption: "Mesh",
    name: "Export STL (faceted mesh)",
  },
];

/**
 * The EXPORT row of the title block: a status cell in the footer-strip
 * anatomy plus one actionable cell per file format. Issuing the part file
 * is title-block business — same ruled 3-column rhythm as UNITS / KERNEL /
 * STATUS above it.
 */
export function ExportControls({ dimensions }: ExportControlsProps) {
  const [busy, setBusy] = useState<ExportFormat | null>(null);
  const [failed, setFailed] = useState<ExportFormat | null>(null);

  const handleExport = async (format: ExportFormat) => {
    setBusy(format);
    setFailed(null);
    try {
      const { blob, filename } = await exportBox(format, dimensions);
      downloadBlob(blob, filename);
    } catch {
      setFailed(format);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div
      role="group"
      aria-label="Export"
      className="border-t border-hairline"
      data-testid="export-controls"
    >
      <div className="grid grid-cols-3 divide-x divide-hairline">
        <div className="px-3 py-2">
          <span className="block font-display text-2xs uppercase tracking-[0.14em] text-gauge">
            Export
          </span>
          <span
            className={`block font-data text-xs ${failed ? "text-flag" : "text-mist"}`}
            data-testid="export-status"
            aria-live="polite"
          >
            {busy ? "Writing…" : failed ? "Failed" : "Ready"}
          </span>
        </div>
        {FORMATS.map(({ format, label, caption, name }) => (
          <PanelActionCell
            key={format}
            label={label}
            caption={busy === format ? "Writing…" : caption}
            aria-label={name}
            aria-busy={busy === format}
            disabled={busy !== null}
            data-testid={`export-${format}`}
            onClick={() => void handleExport(format)}
          />
        ))}
      </div>
      {failed ? (
        <p
          role="alert"
          className="border-t border-hairline px-3 py-2 font-body text-xs text-flag"
          data-testid="export-error"
        >
          Export failed — the {failed.toUpperCase()} file could not be written.
          Check that the gateway is running, then try again.
        </p>
      ) : null}
    </div>
  );
}
