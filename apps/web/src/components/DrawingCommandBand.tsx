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
  SectionIcon,
  SelectField,
  SheetExportIcon,
  ToolButton,
  ToolGroup,
} from "@loft/design";

import type { PartResponse } from "../api/parts";
import {
  SCALE_OPTIONS,
  SHEET_SIZE_OPTIONS,
  sheetSizeLabel,
} from "../drawing/layout";
import type { SheetSize } from "../api/drawings";

export interface DrawingCommandBandProps {
  parts: readonly PartResponse[];
  selectedPartId: string | null;
  onSelectPart: (partId: string) => void;
  scaleValue: string;
  onSelectScale: (value: string) => void;
  /** The chosen sheet size before layout; the persisted sheet's size after. */
  sizeValue: SheetSize;
  onSelectSize: (value: SheetSize) => void;
  /** True once the standard views have been laid out on the sheet. */
  hasLayout: boolean;
  /** True when the laid-out sheet is a flat-pattern (sheet-metal) sheet. */
  isFlatPattern?: boolean;
  /** Name of the part the sheet drafts (shown as a readout after layout). */
  draftedPartName: string | null;
  onLayout: () => void;
  /** Unfold the selected part's flat pattern onto a lone-view sheet (§7). */
  onFlatPattern: () => void;
  /** Toggle the section-view author (pick a cutting plane + flip; §1). */
  onToggleSection: () => void;
  /** True while the section-view author panel is open. */
  sectionOpen: boolean;
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
  sizeValue,
  onSelectSize,
  hasLayout,
  isFlatPattern = false,
  draftedPartName,
  onLayout,
  onFlatPattern,
  onToggleSection,
  sectionOpen,
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
  const sizeOptions = SHEET_SIZE_OPTIONS.map((s) => ({
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
            className="w-[11rem]"
            onChange={(event) => onSelectPart(event.currentTarget.value)}
          />
        )}
        {hasLayout ? (
          <Readout
            label="Size"
            value={sheetSizeLabel(sizeValue)}
            testId="drawing-size-readout"
          />
        ) : (
          <SelectField
            label="Size"
            options={sizeOptions}
            value={sizeValue}
            disabled={busy}
            data-testid="drawing-size-select"
            className="w-[10rem]"
            onChange={(event) =>
              onSelectSize(event.currentTarget.value as SheetSize)
            }
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
            className="w-[6rem]"
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
            <ToolButton
              icon={<SectionIcon />}
              label="Section view"
              showLabel
              shortcut="S"
              active={sectionOpen}
              disabled={!canLayout}
              caption={
                layoutReason ?? (busy ? "Cutting…" : "Cut on a datum plane")
              }
              data-testid="drawing-section"
              onClick={onToggleSection}
            />
          </>
        )}
      </ToolGroup>
      {/* Export outranks the sheet verbs (see `CreateStrip.tsx`): these cells
          are distinguished by their FORMAT, and a format is an identifier the
          glyph cannot spell. The Sheet group stays at the default. */}
      <ToolGroup eyebrow="Export" labelPriority={40}>
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
