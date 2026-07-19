/**
 * The drawing command band — the full-width surface under the brand bar, the
 * sibling of the assembly command band. It carries the ONE signature action of
 * this workspace: drop the standard four views (front / top / right + iso) onto
 * the sheet. The reference part and scale are chosen here before layout; after
 * layout they become live readouts and the action re-projects the part against
 * its current tip (functional, never decorative — design mandate 3a). Chrome
 * recedes; the sheet is the hero.
 */
import {
  FlatPatternIcon,
  RectIcon,
  SelectField,
  SheetExportIcon,
  ToolButton,
  ToolGroup,
} from "@loft/design";

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
  /** True when the laid-out sheet is a flat-pattern (sheet-metal) sheet. */
  isFlatPattern?: boolean;
  /** Name of the part the sheet drafts (shown as a readout after layout). */
  draftedPartName: string | null;
  onLayout: () => void;
  /** Unfold the selected part's flat pattern onto a lone-view sheet (§7). */
  onFlatPattern: () => void;
  onReproject: () => void;
  /** Serialize the laid-out sheet to a downloadable `.svg` (#5). */
  onExportSvg: () => void;
  /** Server-compose the laid-out sheet to a downloadable `.pdf` (DE-2). */
  onExportPdf: () => void;
  /** Server-compose the laid-out sheet to a downloadable `.dxf` (DE-3). */
  onExportDxf: () => void;
  /** True while a server-composed export (PDF or DXF) is in flight. */
  exporting: boolean;
  busy: boolean;
}

export function DrawingCommandBand({
  parts,
  selectedPartId,
  onSelectPart,
  scaleValue,
  onSelectScale,
  hasLayout,
  isFlatPattern = false,
  draftedPartName,
  onLayout,
  onFlatPattern,
  onReproject,
  onExportSvg,
  onExportPdf,
  onExportDxf,
  exporting,
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
            caption={
              busy
                ? "Projecting…"
                : isFlatPattern
                  ? "Refresh the flat pattern from the part"
                  : "Refresh views from the part"
            }
            data-testid="drawing-reproject"
            onClick={onReproject}
          />
        ) : (
          <>
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
            <ToolButton
              icon={<FlatPatternIcon />}
              label="Flat pattern"
              showLabel
              shortcut="F"
              disabled={!canLayout}
              caption={
                layoutReason ??
                (busy ? "Unfolding…" : "Unfold a sheet-metal blank")
              }
              data-testid="drawing-flat-pattern"
              onClick={onFlatPattern}
            />
          </>
        )}
      </ToolGroup>
      <ToolGroup eyebrow="Export">
        <ToolButton
          icon={<SheetExportIcon />}
          label="Export SVG"
          showLabel
          shortcut="E"
          // Enabled only once the sheet has laid-out views — an honest disabled
          // state (with a reason) when there is nothing to download yet.
          disabled={!hasLayout || busy}
          caption={
            !hasLayout
              ? "Lay out the views first"
              : busy
                ? "Projecting…"
                : "Download the sheet as .svg"
          }
          data-testid="drawing-export-svg"
          onClick={onExportSvg}
        />
        <ToolButton
          icon={<SheetExportIcon />}
          label="Export PDF"
          showLabel
          shortcut="P"
          // The server-composed shop deliverable: enabled only once the sheet
          // has views, and while a compose is in flight (honest disabled state).
          disabled={!hasLayout || busy || exporting}
          caption={
            !hasLayout
              ? "Lay out the views first"
              : exporting
                ? "Composing…"
                : busy
                  ? "Projecting…"
                  : "Download the sheet as .pdf"
          }
          data-testid="drawing-export-pdf"
          onClick={onExportPdf}
        />
        <ToolButton
          icon={<SheetExportIcon />}
          label="Export DXF"
          showLabel
          shortcut="D"
          // The interchange deliverable — real CAD entities the shop's tools
          // reopen. Server-composed like PDF: enabled only once the sheet has
          // views, and honestly disabled while a compose is in flight.
          disabled={!hasLayout || busy || exporting}
          caption={
            !hasLayout
              ? "Lay out the views first"
              : exporting
                ? "Composing…"
                : busy
                  ? "Projecting…"
                  : "Download the sheet as .dxf"
          }
          data-testid="drawing-export-dxf"
          onClick={onExportDxf}
        />
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
