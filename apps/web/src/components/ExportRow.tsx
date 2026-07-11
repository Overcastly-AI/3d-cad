import { PanelActionCell } from "@loft/design";
import { useState } from "react";

import {
  downloadBlob,
  type ExportedFile,
  type ExportFormat,
} from "../api/exportPart";

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

export interface ExportRowProps {
  /**
   * Fetch the file for a format — the caller binds the shape or part. On
   * resolve the blob is handed to the browser as a named download; on reject
   * the row flags the failure.
   */
  exporter: (format: ExportFormat) => Promise<ExportedFile>;
  /** Test-hook + a11y prefix: `${prefix}-controls|status|step|stl|error`. */
  testIdPrefix: string;
  /**
   * When set, the whole row is inert and the status cell states this reason —
   * an honest "nothing to export" state (e.g. a sketch-only tree, no body).
   */
  disabledReason?: string;
}

/**
 * The EXPORT strip of a title block: a status cell plus one actionable cell
 * per file format, in the same ruled 3-column rhythm as the UNITS / KERNEL /
 * STATUS strip above it. Presentational + self-contained (busy/error state);
 * the `exporter` prop is the only thing that differs between the box demo and
 * the part workspace, so both draw the same signature strip (DRY).
 */
export function ExportRow({
  exporter,
  testIdPrefix,
  disabledReason,
}: ExportRowProps) {
  const [busy, setBusy] = useState<ExportFormat | null>(null);
  const [failed, setFailed] = useState<ExportFormat | null>(null);
  const disabled = disabledReason !== undefined;

  const handleExport = async (format: ExportFormat) => {
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
  };

  const status = disabled
    ? disabledReason
    : busy
      ? "Writing…"
      : failed
        ? "Failed"
        : "Ready";

  return (
    <div
      role="group"
      aria-label="Export"
      className="border-t border-hairline"
      data-testid={`${testIdPrefix}-controls`}
    >
      <div className="grid grid-cols-3 divide-x divide-hairline">
        <div className="px-3 py-2">
          <span className="block font-display text-2xs uppercase tracking-[0.14em] text-gauge">
            Export
          </span>
          <span
            className={`block font-data text-xs ${failed ? "text-flag" : "text-mist"}`}
            data-testid={`${testIdPrefix}-status`}
            aria-live="polite"
          >
            {status}
          </span>
        </div>
        {FORMATS.map(({ format, label, caption, name }) => (
          <PanelActionCell
            key={format}
            label={label}
            caption={busy === format ? "Writing…" : caption}
            aria-label={name}
            aria-busy={busy === format}
            disabled={disabled || busy !== null}
            data-testid={`${testIdPrefix}-${format}`}
            onClick={() => void handleExport(format)}
          />
        ))}
      </div>
      {failed ? (
        <p
          role="alert"
          className="border-t border-hairline px-3 py-2 font-body text-xs text-flag"
          data-testid={`${testIdPrefix}-error`}
        >
          Export failed — the {failed.toUpperCase()} file could not be written.
          Check that the gateway is running, then try again.
        </p>
      ) : null}
    </div>
  );
}
