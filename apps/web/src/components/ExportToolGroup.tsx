import { ToolButton, ToolGroup } from "@loft/design";

import type { ExportedFile, ExportFormat } from "../api/exportPart";
import { EXPORT_FORMATS, useExportAction } from "../features/exportAction";

export interface ExportToolGroupProps {
  /** Fetch the file for a format — the caller binds the part or assembly. */
  exporter: (format: ExportFormat) => Promise<ExportedFile>;
  /** Test-hook prefix: `${prefix}-controls|step|stl`. */
  testIdPrefix: string;
  /**
   * When set, the group is inert and every cell states this reason — the same
   * honest "nothing to export yet" the panel strip shows, carried into the band
   * so a collapsed panel cannot hide WHY the verb is unavailable.
   */
  disabledReason?: string;
  /** Allowed, but the file would be a prefix of the tree (a travel stop). */
  partial?: boolean;
  /**
   * QA hook stamped as `data-export-state` — the gate state name the caller
   * derived, so a spec asserts the DECISION, not the sentence it produced.
   */
  state?: string;
  /**
   * How hard this group holds its labels as the band narrows (`ToolGroup`).
   * Bands rank export HIGHEST: these labels are format CODES, and a code is
   * an identifier no glyph can spell — see the table in `CreateStrip.tsx`.
   */
  labelPriority?: number;
}

/**
 * EXPORT as a command-band tool group — the document-level home of the verb.
 *
 * Why this exists (EXPORT-1, founder 2026-08-17): export used to live ONLY as
 * the last cell of the Inspector's readout stack, so collapsing that panel —
 * which design mandate 3 actively invites, since the viewport is the hero —
 * deleted the only way to get a file out of the product. A readout is what the
 * model tells you; export is something you DO to the model, and an action
 * parented to a measurement panel is unfindable. Measured before the fix: with
 * the Inspector collapsed, `part-export-controls` count 0, and 53 Tab presses
 * to reach the export cell at 1600x1000.
 *
 * This is deliberately NOT a new affordance. `DrawingCommandBand.tsx` already
 * puts export in its band as `<ToolGroup eyebrow="Export">`; the part and
 * assembly workspaces were the two that never got it. Same primitive, same
 * position (last in the band, after the inspect tools — the band reads left to
 * right as the work, ending in the deliverable), same disabled-with-a-reason
 * grammar as every other gated tool. One export language across three
 * workspaces.
 */
export function ExportToolGroup({
  exporter,
  testIdPrefix,
  disabledReason,
  partial = false,
  state,
  labelPriority,
}: ExportToolGroupProps) {
  const { busy, failed, run } = useExportAction(exporter);
  const blocked = disabledReason !== undefined;
  /** The clause every cell carries: why it is inert, or what the file will be. */
  const qualifier =
    disabledReason ?? (partial ? "marks the file partial" : undefined);

  return (
    <ToolGroup
      eyebrow="Export"
      labelPriority={labelPriority}
      data-testid={`${testIdPrefix}-controls`}
      data-export-state={state}
    >
      {EXPORT_FORMATS.map(({ format, label, caption, name, icon }) => (
        <ToolButton
          key={format}
          icon={icon}
          label={label}
          showLabel
          // What this click would DO rides the accessible NAME, not only the
          // tooltip: `ToolButton` describes a button by its caption while the
          // button is disabled, so an ENABLED-but-qualified state ("the file
          // will be a prefix") would otherwise be reachable by hover alone.
          aria-label={qualifier === undefined ? name : `${name} — ${qualifier}`}
          aria-busy={busy === format}
          disabled={blocked || busy !== null}
          caption={
            busy === format
              ? "Writing…"
              : (disabledReason ??
                (failed === format
                  ? "Failed — check the gateway, then retry"
                  : partial
                    ? `${caption} · marks the file partial`
                    : caption))
          }
          data-testid={`${testIdPrefix}-${format}`}
          onClick={() => void run(format)}
        />
      ))}
      {failed !== null ? (
        // The band has no room for the strip's ruled alert, and a failure the
        // user only discovers by hovering is a failure they do not discover.
        // The visible half is the cell's own caption above; this is the half a
        // screen reader gets, announced without stealing focus.
        <span
          role="status"
          className="sr-only"
          data-testid={`${testIdPrefix}-error`}
        >
          {failed.toUpperCase()} export failed — the file could not be written.
          Check that the gateway is running, then try again.
        </span>
      ) : null}
    </ToolGroup>
  );
}
