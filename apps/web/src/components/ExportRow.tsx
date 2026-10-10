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
  useExportAction,
} from "../features/exportAction";
import { ExportConfirm } from "./ExportConfirm";

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
  /**
   * Set = a format click asks once before it writes ("Export anyway — parts at
   * their last solved or initial positions"); this is why, in a sentence. The
   * assembly sets it while a mate or joint did not solve (QA 2026-10-10).
   */
  confirmReason?: string | null;
  /**
   * Writes the part as a `.loft` file (docs/FILE-FORMAT.md) — the parametric
   * tree, not a body, so the cell stays live when the formats above are
   * blocked (a sketch-only tree is still worth saving). Omit it (the box
   * demo) and the row has no `.loft` cell.
   */
  loftExporter?: () => Promise<ExportedFile>;
  /**
   * Named versions (LOFT-VERSIONS): a "Versions" text link on the status line,
   * like Save .loft, so the strip gains no height (CRAFT-10). The panel it
   * opens leads with Save version; Ctrl+S opens that dialog directly. One
   * link, not two: at the Inspector's width a second one pushed "Save .loft"
   * off the line. Omit it (the box demo) and the row has none.
   */
  versionActions?: {
    onShowVersions: () => void;
  };
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
  confirmReason = null,
  loftExporter,
  versionActions,
}: ExportRowProps) {
  // The band's state machine, not a copy of it: one download path and one
  // table of failure copy for both export surfaces (MESH-TOO-DENSE-COPY-1).
  const { busy, failed, failure, request, armed, confirm, cancel } =
    useExportAction(exporter, confirmReason !== null);
  const disabled = disabledReason !== undefined;

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
        {versionActions !== undefined || loftExporter !== undefined ? (
          <span className="ml-auto flex shrink-0 items-baseline gap-3">
            {versionActions !== undefined ? (
              <button
                type="button"
                aria-haspopup="dialog"
                aria-label="Versions (save, list and restore named versions)"
                data-testid="part-versions"
                onClick={versionActions.onShowVersions}
                className={`${STATUS_LINK} text-brass`}
              >
                Versions
              </button>
            ) : null}
            {loftExporter !== undefined ? (
              <LoftLink exporter={loftExporter} testIdPrefix={testIdPrefix} />
            ) : null}
          </span>
        ) : null}
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
              onClick={() => request(format)}
            />
          ))}
        </div>
      ))}
      {armed !== null && confirmReason !== null ? (
        <ExportConfirm
          format={armed}
          reason={confirmReason}
          testIdPrefix={testIdPrefix}
          onConfirm={confirm}
          onCancel={cancel}
          className="border-t border-hairline px-3 py-2"
        />
      ) : failure !== null ? (
        <p
          role="alert"
          className="border-t border-hairline px-3 py-2 font-body text-xs text-flag"
          data-testid={`${testIdPrefix}-error`}
        >
          {failure.sentence}
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

/** A text action on the status line: no box, so it adds no height. */
const STATUS_LINK =
  "shrink-0 font-display text-2xs uppercase tracking-[0.14em] hover:text-brass-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass";

/**
 * The `.loft` action: a text link at the end of the status line, so it adds
 * NO height. The strip floats over the viewport, and a full-width row here
 * grew it 40 px upward into the space the gauge drags travel through
 * (CRAFT-10). Its own busy / failed state, because it is not a format of the
 * evaluated body and must not share the formats' gate.
 */
function LoftLink({
  exporter,
  testIdPrefix,
}: {
  exporter: () => Promise<ExportedFile>;
  testIdPrefix: string;
}) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const run = async () => {
    setBusy(true);
    setFailed(false);
    try {
      const { blob, filename } = await exporter();
      downloadBlob(blob, filename);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <button
      type="button"
      aria-label="Export .loft (the editable feature tree, for any Loft)"
      aria-busy={busy}
      disabled={busy}
      title={failed ? "The .loft file could not be written; retry" : undefined}
      data-testid={`${testIdPrefix}-loft`}
      data-failed={failed || undefined}
      onClick={() => void run()}
      className={`${STATUS_LINK} ${failed ? "text-flag" : "text-brass"}`}
    >
      {busy ? "Writing…" : failed ? ".loft failed" : "Save .loft"}
    </button>
  );
}
