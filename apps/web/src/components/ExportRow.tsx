import { PanelActionCell } from "@loft/design";
import { useState } from "react";

import {
  downloadBlob,
  type ExportedFile,
  type ExportFormat,
} from "../api/exportPart";
import {
  EXPORT_FORMATS,
  type ExportFormatEntry,
} from "../features/exportAction";

/** The catalogue in rows of two — the strip's 2x2 block (see the layout note). */
const formatRows: ReadonlyArray<readonly ExportFormatEntry[]> =
  EXPORT_FORMATS.reduce<ExportFormatEntry[][]>((rows, entry) => {
    const last = rows.at(-1);
    if (last === undefined || last.length === 2) rows.push([entry]);
    else last.push(entry);
    return rows;
  }, []);

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
  /**
   * Replaces "Ready" while the row IS actionable — for the one case where a
   * file can be written but is not the whole model ("Partial", from the part
   * workspace's travel stop). Omit it and an actionable row reads "Ready".
   */
  statusLabel?: string;
  /**
   * One sentence under the row about the state of the file it would write:
   * why the row is inert, or what is missing from the artifact if it is not.
   * `flag` for an exception the user must act on, `quiet` for a fact.
   */
  notice?: { text: string; tone: "flag" | "quiet" } | null;
  /**
   * QA hook stamped on the row as `data-export-state` — the state name of
   * whatever gate the caller derived, so a spec asserts the DECISION rather
   * than the sentence it produced.
   */
  state?: string;
}

/**
 * The EXPORT strip of a title block: a status line, then one actionable cell
 * per file format. Presentational + self-contained (busy/error state); the
 * `exporter` prop is the only thing that differs between the box demo and the
 * part workspace, so both draw the same signature strip (DRY), and the format
 * catalogue is the SAME constant the command band renders
 * (`features/exportAction.EXPORT_FORMATS`) — there is no second list.
 *
 * **Layout, and why it changed at EXPORT-2.** This was a single ruled row of
 * three: status, STEP, STL — echoing the UNITS / KERNEL / STATUS strip above
 * it. Four formats do not divide into that rhythm; three columns would leave a
 * hole in the second row, and five would squeeze every cell to ~70 px in the
 * Inspector, where the captions that make the new formats legible ("Print",
 * "Share") are the whole point. So the status takes the full width — which it
 * had earned anyway, since after EXPORT-1 this strip is the NOTICE surface and
 * its cell carries sentences, not a word — and the formats sit in a ruled 2x2
 * below it. The rhythm is kept where it is load-bearing (the hairline rules,
 * the cell proportions) and spent where the content changed.
 */
export function ExportRow({
  exporter,
  testIdPrefix,
  disabledReason,
  statusLabel,
  notice = null,
  state,
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
        : (statusLabel ?? "Ready");

  return (
    <div
      role="group"
      aria-label="Export"
      className="border-t border-hairline"
      data-testid={`${testIdPrefix}-controls`}
      data-export-state={state}
    >
      <div className="flex items-baseline gap-2 px-3 py-2">
        <span className="font-display text-2xs uppercase tracking-[0.14em] text-gauge">
          Export
        </span>
        <span
          className={`min-w-0 font-data text-xs ${failed ? "text-flag" : "text-mist"}`}
          data-testid={`${testIdPrefix}-status`}
          aria-live="polite"
        >
          {status}
        </span>
      </div>
      {/*
        One wrapper per PAIR rather than one grid with `divide-y`: Tailwind's
        divide utilities key off DOM order, not grid position, so on a 2x2 they
        rule the wrong edges (a top border on the first row's second cell).
        Chunking makes each rule an explicit statement about a row.
      */}
      {formatRows.map((row) => (
        <div
          key={row[0]?.format}
          className="grid grid-cols-2 divide-x divide-hairline border-t border-hairline"
        >
          {row.map(({ format, label, caption, name, icon }) => (
            <PanelActionCell
              key={format}
              icon={icon}
              label={label}
              caption={busy === format ? "Writing…" : caption}
              aria-label={name}
              aria-busy={busy === format}
              disabled={disabled || busy !== null}
              // The row already knows why it is inert; the CELL is what a user
              // hovers or tabs to, so the reason belongs on it too (it was
              // unreachable while the cell was natively disabled — UI-REVIEW
              // 2026-07-30 P2).
              disabledReason={disabledReason}
              data-testid={`${testIdPrefix}-${format}`}
              onClick={() => void handleExport(format)}
            />
          ))}
        </div>
      ))}
      {failed ? (
        <p
          role="alert"
          className="border-t border-hairline px-3 py-2 font-body text-xs text-flag"
          data-testid={`${testIdPrefix}-error`}
        >
          Export failed — the {failed.toUpperCase()} file could not be written.
          Check that the gateway is running, then try again.
        </p>
      ) : notice ? (
        // What the file WOULD be, stated before the click rather than after the
        // download (AUDIT-ENGINEERING J2 — "Ready" over a truncated rebuild is a
        // wrong file, not a wrong label).
        <p
          className={`border-t border-hairline px-3 py-2 font-body text-xs ${
            notice.tone === "flag" ? "text-flag" : "text-gauge"
          }`}
          data-testid={`${testIdPrefix}-notice`}
        >
          {notice.text}
        </p>
      ) : null}
    </div>
  );
}
