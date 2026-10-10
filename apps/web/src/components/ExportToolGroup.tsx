import { ToolButton, ToolGroup } from "@loft/design";

import type { ExportedFile, ExportFormat } from "../api/exportPart";
import { EXPORT_FORMATS, useExportAction } from "../features/exportAction";
import { ExportConfirm } from "./ExportConfirm";

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
  /** Allowed, but the file would be a prefix of the tree. */
  partial?: boolean;
  /**
   * What makes it a prefix, in a clause (`ExportGate.qualifier`) — e.g. "stops
   * at Extrude1, marked partial".
   *
   * The band has no notice line, and after EXPORT-3 a prefix can be caused by a
   * FAILURE as well as by a travel stop. "Marks the file partial" is true of
   * both and names neither, so a user working with the Inspector collapsed —
   * the exact case this group exists for — would get the file without ever
   * being told where it stops. Falls back to the generic clause.
   */
  partialQualifier?: string;
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
  /**
   * Set = a format click asks once before it writes; this is why. The band has
   * no notice line, so the confirm hangs under the group (`ExportConfirm`).
   */
  confirmReason?: string | null;
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
  partialQualifier,
  state,
  labelPriority,
  confirmReason = null,
}: ExportToolGroupProps) {
  const { busy, failed, failure, request, armed, confirm, cancel } =
    useExportAction(exporter, confirmReason !== null);
  const blocked = disabledReason !== undefined;
  /** The clause every cell carries: why it is inert, or what the file will be. */
  const qualifier =
    disabledReason ??
    (partial ? (partialQualifier ?? "marks the file partial") : undefined);

  return (
    <ToolGroup
      eyebrow="Export"
      labelPriority={labelPriority}
      data-testid={`${testIdPrefix}-controls`}
      data-export-state={state}
      className="relative"
    >
      {EXPORT_FORMATS.map(({ format, label, caption, name, icon }) => (
        <ToolButton
          key={format}
          icon={icon}
          label={label}
          showLabel
          // The name is the FORMAT, in every state. What this click would DO
          // rides the caption, which `ToolButton` now exposes as the accessible
          // description whether the cell is gated or merely qualified
          // (A11Y-TOOLBTN-1). This used to append the qualifier to the name,
          // because the primitive announced a caption only while disabled — so
          // the cell answered to a different name depending on the gate state,
          // and the qualifier was announced twice the moment that was fixed.
          aria-label={name}
          aria-busy={busy === format}
          disabled={blocked || busy !== null}
          caption={
            busy === format
              ? "Writing…"
              : (disabledReason ??
                (failed === format && failure !== null
                  ? failure.caption
                  : partial && qualifier !== undefined
                    ? `${caption} · ${qualifier}`
                    : caption))
          }
          data-testid={`${testIdPrefix}-${format}`}
          onClick={() => request(format)}
        />
      ))}
      {armed !== null && confirmReason !== null ? (
        <ExportConfirm
          format={armed}
          reason={confirmReason}
          testIdPrefix={testIdPrefix}
          onConfirm={confirm}
          onCancel={cancel}
          className="absolute right-0 top-full z-40 mt-1 w-[18rem] border border-hairline bg-anvil px-3 py-2 shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
        />
      ) : null}
      {failure !== null ? (
        // The band has no room for the strip's ruled alert, and a failure the
        // user only discovers by hovering is a failure they do not discover.
        // The visible half is the cell's own caption above; this is the half a
        // screen reader gets, announced without stealing focus.
        <span
          role="status"
          className="sr-only"
          data-testid={`${testIdPrefix}-error`}
        >
          {failure.sentence}
        </span>
      ) : null}
    </ToolGroup>
  );
}
