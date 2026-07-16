/**
 * The drawing command band — the full-width surface under the brand bar, the
 * sibling of the assembly command band. It carries the ONE signature action of
 * this workspace: drop the standard four views (front / top / right + iso) onto
 * the sheet. The reference part and scale are chosen here before layout; after
 * layout they become live readouts and the action re-projects the part against
 * its current tip (functional, never decorative — design mandate 3a). Chrome
 * recedes; the sheet is the hero.
 */
import { RectIcon, SelectField, ToolButton, ToolGroup } from "@loft/design";

import type { PartResponse } from "../api/parts";
import { SCALE_OPTIONS } from "../drawing/layout";

export interface DrawingCommandBandProps {
  parts: readonly PartResponse[];
  selectedPartId: string | null;
  onSelectPart: (partId: string) => void;
  scaleValue: string;
  onSelectScale: (value: string) => void;
  /** True once the standard views have been laid out on the sheet. */
  hasLayout: boolean;
  /** Name of the part the sheet drafts (shown as a readout after layout). */
  draftedPartName: string | null;
  onLayout: () => void;
  onReproject: () => void;
  busy: boolean;
}

export function DrawingCommandBand({
  parts,
  selectedPartId,
  onSelectPart,
  scaleValue,
  onSelectScale,
  hasLayout,
  draftedPartName,
  onLayout,
  onReproject,
  busy,
}: DrawingCommandBandProps) {
  const noParts = parts.length === 0;
  const partOptions = parts.map((part) => ({
    value: part.id,
    label: part.name,
  }));
  const scaleOptions = SCALE_OPTIONS.map((s) => ({
    value: s.value,
    label: s.label,
  }));
  const canLayout = !hasLayout && selectedPartId !== null && !busy;
  const layoutReason = hasLayout
    ? "Views already laid out"
    : noParts
      ? "Create a part first"
      : selectedPartId === null
        ? "Choose a part first"
        : undefined;

  return (
    <div className="flex items-stretch divide-x divide-hairline">
      <div className="flex items-center gap-3 px-3">
        {hasLayout ? (
          <Readout
            label="Part"
            value={draftedPartName ?? "—"}
            testId="drawing-part-readout"
          />
        ) : (
          <SelectField
            label="Part"
            options={partOptions}
            value={selectedPartId ?? ""}
            disabled={noParts || busy}
            data-testid="drawing-part-select"
            className="w-44"
            onChange={(event) => onSelectPart(event.currentTarget.value)}
          />
        )}
        {hasLayout ? (
          <Readout
            label="Scale"
            value={scaleValue}
            testId="drawing-scale-readout"
          />
        ) : (
          <SelectField
            label="Scale"
            options={scaleOptions}
            value={scaleValue}
            disabled={busy}
            data-testid="drawing-scale-select"
            className="w-24"
            onChange={(event) => onSelectScale(event.currentTarget.value)}
          />
        )}
      </div>
      <ToolGroup eyebrow="Sheet">
        {hasLayout ? (
          <ToolButton
            icon={<RectIcon />}
            label="Re-project"
            showLabel
            shortcut="L"
            disabled={busy}
            caption={busy ? "Projecting…" : "Refresh views from the part"}
            data-testid="drawing-reproject"
            onClick={onReproject}
          />
        ) : (
          <ToolButton
            icon={<RectIcon />}
            label="Lay out standard views"
            showLabel
            shortcut="L"
            disabled={!canLayout}
            caption={
              layoutReason ??
              (busy ? "Projecting…" : "Front · Top · Right · Iso")
            }
            data-testid="drawing-autolayout"
            onClick={onLayout}
          />
        )}
      </ToolGroup>
    </div>
  );
}

/** A quiet label-over-value readout — the post-layout state of a picker. */
function Readout({
  label,
  value,
  testId,
}: {
  label: string;
  value: string;
  testId: string;
}) {
  return (
    <div className="flex flex-col justify-center">
      <span className="font-display text-2xs uppercase tracking-[0.16em] text-gauge">
        {label}
      </span>
      <span data-testid={testId} className="font-data text-sm text-mist">
        {value}
      </span>
    </div>
  );
}
