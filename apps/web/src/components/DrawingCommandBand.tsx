/**
 * The drawing command band — the full-width surface under the brand bar, the
 * sibling of the assembly command band. It carries the ONE signature action of
 * this workspace: drop the standard four views (front / top / right + iso) onto
 * the sheet. The SOURCE — a part or an assembly — and the SIZE are chosen here
 * before layout and become engraved readouts after it (changing either is a
 * re-layout, not an edit in place). SCALE is the exception, and the asymmetry
 * is the information: a laid-out sheet's scale IS changeable — SHEET-RESCALE-1
 * rewrites all four views in one transaction — so it stays an operable cell on
 * both sides of the layout, and the action re-projects that source against its
 * current tip (functional, never decorative — design mandate 3a). Chrome
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

import {
  SCALE_OPTIONS,
  sheetSizeLabel,
  sheetSizeOptions,
} from "../drawing/layout";
import {
  SOURCE_GROUP_LABEL,
  SOURCE_KIND_LABEL,
  type DrawingSourceOption,
} from "../drawing/source";
import type {
  RefDocumentKind,
  SheetResponse,
  SheetSize,
} from "../api/drawings";

type SheetOrientation = SheetResponse["orientation"];

export interface DrawingCommandBandProps {
  /**
   * What this sheet can draft — parts AND assemblies (§7). One picker over both
   * registers, grouped by kind; the value is the bare document id (see
   * `drawing/source.ts` for why it is never a `kind:id` composite).
   */
  sources: readonly DrawingSourceOption[];
  selectedSourceId: string | null;
  onSelectSource: (sourceId: string) => void;
  /**
   * The kind of the chosen (pre-layout) or drafted (post-layout) source. Flat
   * pattern and section are PART verbs — an unfold and a datum-plane cut are
   * statements about one body — so they stay honestly disabled, with the
   * reason, on an assembly sheet rather than failing at the server.
   */
  sourceKind: RefDocumentKind;
  /**
   * The scale the sheet is drawn at: the intent the first layout will fit under
   * before layout, the scale its stored views actually carry after. Always the
   * value of a live picker — see {@link DrawingCommandBandProps.rescaling}.
   */
  scaleValue: string;
  /**
   * Pick a scale. Pre-layout that records intent; post-layout it re-scales the
   * laid-out sheet in place (SHEET-RESCALE-1's verb). The cell does NOT hold
   * the picked value optimistically — `scaleValue` keeps deriving from what the
   * sheet is actually drawn at, so a failed write leaves the honest reading.
   */
  onSelectScale: (value: string) => void;
  /**
   * True while a re-scale write is in flight. The picker goes honestly inert
   * for that window: the writer refuses a second change while one is pending,
   * and a control that accepts a gesture it will discard is a dead end
   * (CLAUDE.md flow rule 4), so it says so instead of swallowing it.
   */
  rescaling?: boolean;
  /** The chosen sheet size before layout; the persisted sheet's size after. */
  sizeValue: SheetSize;
  onSelectSize: (value: SheetSize) => void;
  /**
   * The paper the next layout will actually make — the content-led proposal
   * before layout, the persisted sheet's own orientation after. The size picker
   * states THIS paper's extents (REACH-3-FLOW): "A4 · 297 × 210 mm" beside a
   * proposal about to make a 210 × 297 sheet names the wrong paper at the
   * moment the user is choosing it.
   */
  paperOrientation: SheetOrientation;
  /**
   * The scale that paper earns for the chosen source, or null when nothing was
   * measured. Engraved on the layout tool's caption so the proposal is legible
   * BEFORE the click, not discovered after it.
   */
  paperScale: string | null;
  /** True once the standard views have been laid out on the sheet. */
  hasLayout: boolean;
  /** True when the laid-out sheet is a flat-pattern (sheet-metal) sheet. */
  isFlatPattern?: boolean;
  /** Name of the part/assembly the sheet drafts (a readout after layout). */
  draftedSourceName: string | null;
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
  sources,
  selectedSourceId,
  onSelectSource,
  sourceKind,
  scaleValue,
  onSelectScale,
  rescaling = false,
  sizeValue,
  onSelectSize,
  paperOrientation,
  paperScale,
  hasLayout,
  isFlatPattern = false,
  draftedSourceName,
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
  const noSources = sources.length === 0;
  // Grouped so the cell says WHICH REGISTER a name comes from — two documents
  // can share a name across the parts and assemblies registers, and "Gearbox"
  // alone cannot tell you which one this sheet will project.
  const sourceOptions = sources.map((source) => ({
    value: source.id,
    label: source.name,
    group: SOURCE_GROUP_LABEL[source.kind],
  }));
  // The standard ladder, plus — only when needed — the scale the sheet is
  // ACTUALLY at. A native select whose value matches no option silently
  // displays its FIRST one, so a sheet stored at some off-ladder scale (an API
  // client can write any ratio) would be misreported as 1:1 by the very cell
  // that replaced the readout. The guard entry is shown and not choosable, so
  // the cell can still state a scale it cannot offer to re-pick.
  const offLadder =
    scaleValue !== "" && !SCALE_OPTIONS.some((s) => s.value === scaleValue);
  const scaleOptions = [
    ...(offLadder
      ? [{ value: scaleValue, label: scaleValue, disabled: true }]
      : []),
    ...SCALE_OPTIONS.map((s) => ({ value: s.value, label: s.label })),
  ];
  const sizeOptions = sheetSizeOptions(paperOrientation).map((s) => ({
    value: s.value,
    label: s.label,
  }));
  // What the signature action is about to make, in the words the sheet header
  // will then read back. Portrait only ever appears because the SOURCE argued
  // for it, so naming it here is the proposal being visible from the state the
  // user is in — not a decoration (mandate 3a).
  const paperNote = `${sheetSizeLabel(sizeValue)} ${paperOrientation}${
    paperScale === null ? "" : ` at ${paperScale}`
  }`;
  const canLayout = !hasLayout && selectedSourceId !== null && !busy;
  const layoutReason = hasLayout
    ? "Views already laid out"
    : noSources
      ? "Create a part or assembly first"
      : selectedSourceId === null
        ? "Choose a source first"
        : undefined;
  // An assembly source keeps Lay out; it loses the two part-only verbs, and
  // says so where the user is about to reach for them.
  const partOnlyReason =
    layoutReason ??
    (sourceKind === "assembly" ? "Choose a part source" : undefined);
  const canPartOnly = canLayout && sourceKind === "part";

  return (
    <div className="flex items-stretch divide-x divide-hairline">
      <div className="flex items-center gap-3 px-3">
        {hasLayout ? (
          <Readout
            label={SOURCE_KIND_LABEL[sourceKind]}
            value={draftedSourceName ?? "—"}
            testId="drawing-part-readout"
          />
        ) : (
          // The testid stays `drawing-part-select` — the cell WIDENED from
          // parts to every source a view can reference, and renaming the hook
          // would have broken twenty green specs to say the same thing.
          <SelectField
            label="Source"
            options={sourceOptions}
            value={selectedSourceId ?? ""}
            disabled={noSources || busy}
            data-testid="drawing-part-select"
            className="w-[11rem]"
            onChange={(event) => onSelectSource(event.currentTarget.value)}
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
        {/* Live on BOTH sides of the layout (SHEET-RESCALE-2). Source and Size
            above become readouts because changing them means laying out again;
            re-scaling does not, so freezing this cell hid a verb the server
            already had — the founder's own named defect class, a capability
            that exists and cannot be reached. One hook, `drawing-scale-select`,
            for one control that now simply never goes away.

            The CAPTION follows the row it is in. Before layout the cell sits
            between two other pickers and wears the field label they wear;
            after, it sits between two engraved readouts, in a frame where every
            other caption — Part, Size, Sheet, Export, and the sheet's own title
            block — is engraved micro-caps. A single sentence-case "Scale" there
            was the only label in the frame breaking that grammar, i.e. the
            change announcing itself. It should not: the point of this fix is
            that the value simply becomes operable. */}
        <div className="flex flex-col justify-center">
          {hasLayout ? (
            // The <select> carries the same name for assistive tech (the
            // primitive's own `sr-only` label), so this engraving is decoration
            // of the accessible name, not a second copy of it.
            <span
              aria-hidden="true"
              className="font-display text-2xs uppercase tracking-[0.16em] text-gauge"
            >
              Scale
            </span>
          ) : null}
          <SelectField
            label="Scale"
            hideLabel={hasLayout}
            options={scaleOptions}
            value={scaleValue}
            disabled={busy || rescaling}
            data-testid="drawing-scale-select"
            className="w-[6rem]"
            onChange={(event) => onSelectScale(event.currentTarget.value)}
          />
        </div>
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
                (busy
                  ? "Projecting…"
                  : `Front · Top · Right · Iso — on ${paperNote}`)
              }
              data-testid="drawing-autolayout"
              data-paper={`${paperOrientation}${paperScale === null ? "" : ` ${paperScale}`}`}
              onClick={onLayout}
            />
            <ToolButton
              icon={<FlatPatternIcon />}
              label="Flat pattern"
              showLabel
              shortcut="F"
              disabled={!canPartOnly}
              caption={
                partOnlyReason ??
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
              disabled={!canPartOnly}
              caption={
                partOnlyReason ?? (busy ? "Cutting…" : "Cut on a datum plane")
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
