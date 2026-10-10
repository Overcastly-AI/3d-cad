import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Notice, NumberField } from "@loft/design";

import type { DrawingBomLine, ViewProjection } from "../api/drawings";
import { Breadcrumb } from "../components/Breadcrumb";
import { DimensionAuthorMenu } from "../components/DimensionAuthorMenu";
import { DrawingCommandBand } from "../components/DrawingCommandBand";
import { DrawingSheet } from "../components/DrawingSheet";
import { FloatingPanel } from "../components/FloatingPanel";
import { SectionAuthorPanel } from "../components/SectionAuthorPanel";
import { SheetIssueStrip } from "../components/SheetIssueStrip";
import { TopBar } from "../components/TopBar";
import { TopToolbar } from "../components/TopToolbar";
import {
  IDLE,
  PLACE_NUDGE_MM,
  cancelPlacement,
  nudgePlacement,
  placementReplaces,
  setPlacementOffset,
} from "../drawing/authoring";
import { drawingSourceName } from "../drawing/source";
import { capitalise, PARTIAL_POSE_CLAUSE } from "../features/assemblyExport";
import { isTypingTarget } from "../lib/isTypingTarget";
import { drawingRoute } from "../router";
import { CenterNote, SetupHint, SheetTabs } from "./drawing/SheetChrome";
import {
  BendSchedulePanel,
  DimensionsPanel,
  NotesPanel,
  PartsListPanel,
  ViewsPanel,
} from "./drawing/SheetPanels";
import { useDimensionAuthoring } from "./drawing/useDimensionAuthoring";
import { useDrawingData } from "./drawing/useDrawingData";
import { useDrawingExport } from "./drawing/useDrawingExport";
import { useDrawingNotes } from "./drawing/useDrawingNotes";
import { useLayoutActions } from "./drawing/useLayoutActions";
import { useSheetManagement } from "./drawing/useSheetManagement";
import { useViewPlacement } from "./drawing/useViewPlacement";

/**
 * The drawing editor — an engineering sheet on the blued-steel bench. The
 * signature action drops the standard four views (front / top / right + iso,
 * third-angle) onto the sheet: it creates the views (CRUD) and projects the
 * referenced part through `/geometry/drawing/evaluate`, then renders each view
 * as scale-correct SVG — visible edges solid, hidden edges dashed. The sheet is
 * the hero; the chrome recedes.
 */
export function DrawingPage() {
  const { drawingId } = drawingRoute.useParams();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  // The page's state lives in hooks under `./drawing/` (SPLIT-DRAWINGPAGE):
  // the reads, then each family of writes, in the order they were declared
  // when this was one function, so every effect still runs in that order.
  // The single error banner every write reports into stays here.
  const [actionError, setActionError] = useState<string | null>(null);
  const ctx = { drawingId, queryClient, setActionError };
  const data = useDrawingData(drawingId);
  const {
    drawingQuery,
    tree,
    sheetCount,
    setActiveSheetIndex,
    activeIndex,
    sheet,
    views,
    requestedViews,
    isFlatPatternSheet,
    dimensions,
    annotations,
    hasLayout,
    draftedSourceId,
    assemblyPartial,
    parts,
    sources,
    selectedSourceId,
    setSelectedSourceId,
    setScaleValue,
    setSizeValue,
    effectiveSourceKind,
    effectiveScaleValue,
    effectiveSize,
    partTreeQuery,
    orientationFit,
    paperOrientation,
    paperScale,
    evalQuery,
    evaluation,
    resultByProjection,
    measuredById,
    sheetQuery,
    composed,
    composedByProjection,
    bomQuery,
  } = data;

  const {
    busy,
    sectionOpen,
    setSectionOpen,
    sectionError,
    sectionPartTreeQuery,
    sectionDatumOptions,
    handleLayout,
    handleFlatPattern,
    handleAuthorSection,
    handleToggleSection,
  } = useLayoutActions(data, ctx);

  // "What IS item 2?" — open the document a parts-list line names, in its own
  // workspace. The list is the only place on this sheet where another document
  // is named, so it is the only place that answer can be reached from; without
  // it the numbers are a dead end (design mandate: no chrome that only reads).
  const handleOpenBomLine = useCallback(
    (line: DrawingBomLine) => {
      if (line.missing) return;
      void (line.ref_document_kind === "assembly"
        ? navigate({
            to: "/assemblies/$assemblyId",
            params: { assemblyId: line.ref_document_id },
          })
        : navigate({
            to: "/parts/$partId",
            params: { partId: line.ref_document_id },
          }));
    },
    [navigate],
  );

  const {
    addingSheet,
    handleAddSheet,
    reheading,
    handleFlipConvention,
    handleFlipOrientation,
    handleFlipPaper,
    handleReproject,
  } = useSheetManagement(data, ctx);

  const {
    placingView,
    handlePlaceView,
    handleResetView,
    handleAutoPlaceViews,
  } = useViewPlacement(data, ctx);

  const {
    sheetSvgRef,
    exporting,
    handleExportSvg,
    handleExportPdf,
    handleExportDxf,
  } = useDrawingExport(data, ctx);

  const {
    authoring,
    setAuthoring,
    dimBusy,
    selectedEdgeKey,
    armedEdgeKeys,
    selectedVertexKeys,
    endpointPickActive,
    menuActionList,
    anchor,
    hint,
    placingGhost,
    placingOffsetMm,
    handlePickEdge,
    handlePickEndpoint,
    handleChooseAction,
    handlePlacePointer,
    handlePlaceClick,
    handlePlaceRelease,
    handleGrabFromSheet,
    handleMoveFromPanel,
    setOffsetDraft,
    offsetFieldRef,
    offsetText,
    handleOffsetTyped,
    placingRef,
    commitPlacementRef,
    handleDeleteDimension,
    handleHealDimension,
  } = useDimensionAuthoring(data, ctx);

  const { noteBusy, handleAddNote, handleDeleteNote } = useDrawingNotes(
    data,
    ctx,
  );

  // Keyboard-first: L lays out (or re-projects once laid out).
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        // Escape during a placement backs out ONE stage: the pick that led here
        // survives, so a mis-drag never costs you the geometry you selected
        // (CLAUDE.md flow rule — no ambiguous exits).
        setAuthoring((state) =>
          state.kind === "placing" ? cancelPlacement(state) : IDLE,
        );
        setSectionOpen(false);
        return;
      }
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;
      // Keyboard parity for the placement drag: arrows nudge, Enter commits.
      // Claimed BEFORE the single-letter commands so an arrow/Enter mid-place
      // can never fire an export instead.
      if (placingRef.current) {
        // TYPE A NUMBER AND YOU ARE SETTING IT. A digit (or a leading minus)
        // hands the keystroke to the offset field and focuses it, so the
        // precision route costs no hunting and no mouse — the same reflex a
        // modeller already has from every other CAD tool. Intent captured
        // where it forms (CLAUDE.md flow rule), not recovered afterwards.
        const field = offsetFieldRef.current;
        if (field && /^[0-9.-]$/.test(event.key)) {
          event.preventDefault();
          // FOCUS FIRST, then seed. `focus()` fires the field's own onFocus
          // synchronously, which opens a draft from the CURRENT value — so
          // seeding before focusing hands the user "11.0025" instead of "-25".
          field.focus();
          setOffsetDraft(event.key);
          const seed = Number(event.key);
          if (Number.isFinite(seed)) {
            setAuthoring((state) => setPlacementOffset(state, seed));
          }
          return;
        }
        const step = event.shiftKey ? PLACE_NUDGE_MM * 5 : PLACE_NUDGE_MM;
        const delta: Record<string, [number, number]> = {
          ArrowUp: [0, -1],
          ArrowDown: [0, 1],
          ArrowLeft: [-1, 0],
          ArrowRight: [1, 0],
        };
        const move = delta[event.key];
        if (move) {
          event.preventDefault();
          setAuthoring((state) =>
            nudgePlacement(state, move[0], move[1], step),
          );
          return;
        }
        if (event.key === "Enter") {
          event.preventDefault();
          commitPlacementRef.current();
          return;
        }
      }
      if (event.key.toLowerCase() === "l") {
        event.preventDefault();
        if (hasLayout) handleReproject();
        else handleLayout();
      }
      // F unfolds the flat pattern (a lone flat blank + bend table). No-op once
      // laid out (mirrors the command band's Flat pattern action).
      if (event.key.toLowerCase() === "f" && !hasLayout) {
        event.preventDefault();
        handleFlatPattern();
      }
      // S opens the section-view author (pick a cutting plane + flip). Pre-layout
      // only, mirroring the command band's Section action.
      if (event.key.toLowerCase() === "s" && !hasLayout) {
        event.preventDefault();
        handleToggleSection();
      }
      // E exports the laid-out sheet to a .svg (keyboard-first, mirrors the
      // command band's Export SVG action). No-op before layout.
      if (event.key.toLowerCase() === "e" && hasLayout) {
        event.preventDefault();
        handleExportSvg();
      }
      // P server-composes the laid-out sheet to a .pdf (the shop deliverable),
      // mirroring the command band's Export PDF action. No-op before layout.
      if (event.key.toLowerCase() === "p" && hasLayout) {
        event.preventDefault();
        handleExportPdf();
      }
      // D server-composes the laid-out sheet to a .dxf (the interchange
      // deliverable), mirroring the command band's Export DXF action.
      if (event.key.toLowerCase() === "d" && hasLayout) {
        event.preventDefault();
        handleExportDxf();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [
    hasLayout,
    handleLayout,
    handleFlatPattern,
    handleToggleSection,
    handleReproject,
    handleExportSvg,
    handleExportPdf,
    handleExportDxf,
  ]);

  const draftedSourceName = drawingSourceName(sources, draftedSourceId);

  // The composer's own layout measurements (audit N2) — a colliding or crowded
  // pair of views, in millimetres, with the sentence every export stamps. The
  // strip below is the on-screen half of that banner.
  const layoutIssues = composed?.layout_issues ?? [];
  // Which views carry a hand-dragged placement: those are the only ones a
  // "return to auto-layout" fix can act on (the composer honours an
  // `auto_place: false` position verbatim, which is how a collision gets made).
  const handPlacedViews = useMemo(() => {
    const set = new Set<ViewProjection>();
    for (const view of views) {
      if (view.auto_place === false) set.add(view.projection);
    }
    return set;
  }, [views]);

  const projecting =
    evalQuery.isFetching || partTreeQuery.isFetching || sheetQuery.isFetching;

  return (
    <div className="flex h-full flex-col">
      <TopBar>
        <Breadcrumb
          register="drawings"
          documentName={tree?.drawing.name ?? "Drawing"}
          documentTestId="drawing-name"
          mode={hasLayout ? null : "Set up"}
        />
      </TopBar>
      <TopToolbar>
        {/* Only once the drawing has loaded — otherwise the band invites "Lay
            out" against a not-yet-known doc_version (a stale-OCC race). */}
        {drawingQuery.isSuccess ? (
          <DrawingCommandBand
            sources={sources}
            selectedSourceId={selectedSourceId}
            onSelectSource={setSelectedSourceId}
            sourceKind={effectiveSourceKind}
            scaleValue={effectiveScaleValue}
            onSelectScale={setScaleValue}
            sizeValue={effectiveSize}
            onSelectSize={setSizeValue}
            paperOrientation={paperOrientation}
            paperScale={paperScale}
            hasLayout={hasLayout}
            isFlatPattern={isFlatPatternSheet}
            draftedSourceName={draftedSourceName}
            onLayout={handleLayout}
            onFlatPattern={handleFlatPattern}
            onToggleSection={handleToggleSection}
            sectionOpen={sectionOpen}
            onReproject={handleReproject}
            onExportSvg={handleExportSvg}
            onExportPdf={handleExportPdf}
            onExportDxf={handleExportDxf}
            exporting={exporting}
            busy={busy || projecting}
          />
        ) : null}

        {/* The section-view author hangs from the band into the viewport (the
            sketch strip's offset-plane idiom), so the Sheet actions stay one
            row above. Pre-layout only — a section is a lone-view sheet in v1. */}
        {sectionOpen && !hasLayout ? (
          <div className="absolute left-3 top-full z-overlay mt-2">
            <SectionAuthorPanel
              datumPlanes={sectionDatumOptions}
              loadingDatums={sectionPartTreeQuery.isFetching}
              onCut={handleAuthorSection}
              onClose={() => setSectionOpen(false)}
              busy={busy}
              error={sectionError}
            />
          </div>
        ) : null}
      </TopToolbar>

      <main className="relative min-h-0 grow overflow-hidden bg-carbide">
        {/* The bench under the sheet — same grid the viewport + registers use. */}
        <div
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_38%,theme(colors.anvil),theme(colors.carbide)_72%)]"
          aria-hidden="true"
        />

        {/* The sheet switcher (FINDINGS #18) — move between the drawing's sheets,
            add a new one. Appears once the drawing has a sheet (post-layout). */}
        {tree && sheetCount > 0 ? (
          <SheetTabs
            sheets={tree.sheets}
            activeIndex={activeIndex}
            onSelect={setActiveSheetIndex}
            onAdd={handleAddSheet}
            adding={addingSheet}
            sheet={sheet}
            fit={orientationFit}
            drawnScale={effectiveScaleValue}
            onFlipConvention={handleFlipConvention}
            onFlipOrientation={handleFlipOrientation}
            reheading={reheading}
          />
        ) : null}

        {drawingQuery.isError ? (
          <CenterNote
            testId="drawing-load-error"
            tone="error"
            title="Drawing could not be loaded"
            body={
              drawingQuery.error instanceof Error
                ? drawingQuery.error.message
                : "Reload and try again."
            }
          />
        ) : !tree ? (
          <CenterNote
            testId="drawing-loading"
            tone="quiet"
            title="Loading drawing…"
            body="Fetching the sheet."
          />
        ) : hasLayout && sheet && composed ? (
          // Reserve the right gutter for the Views panel so the paper never
          // slides under it (the panel would clip the sheet's framed corner).
          // The check strip stacks ABOVE the paper rather than floating over it:
          // a diagnostic that covers the geometry it is about is not a
          // diagnostic. It only occupies rows when there is something to say.
          <div
            className={`absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 sm:p-10 lg:pr-[22rem] ${
              // The check strip needs clearance from the sheet switcher, which
              // floats in this same top-left margin; without it the two touch at
              // narrow widths. Only paid for when the strip is there.
              layoutIssues.length > 0 || assemblyPartial !== null
                ? "pt-12 sm:pt-12"
                : ""
            }`}
          >
            {/* The assembly's mates did not all solve, so the views draw its
                parts where the solve left them — the export strip's "Partial",
                carried onto the paper (QA 2026-10-10). */}
            {assemblyPartial !== null && draftedSourceId !== null ? (
              <Notice
                role="status"
                label="Partial"
                tone="flag"
                data-testid="drawing-assembly-partial"
                className="w-full max-w-3xl shrink-0"
                action={{
                  label: "Open assembly",
                  testId: "drawing-assembly-partial-open",
                  onClick: () =>
                    void navigate({
                      to: "/assemblies/$assemblyId",
                      params: { assemblyId: draftedSourceId },
                    }),
                }}
              >
                {capitalise(assemblyPartial)} in{" "}
                {drawingSourceName(sources, draftedSourceId) ?? "the assembly"},
                so these views draw the {PARTIAL_POSE_CLAUSE}.
              </Notice>
            ) : null}
            <SheetIssueStrip
              issues={layoutIssues}
              handPlaced={handPlacedViews}
              onAutoPlace={handleAutoPlaceViews}
              busy={placingView}
            />
            <div className="min-h-0 w-full grow">
              <DrawingSheet
                svgRef={sheetSvgRef}
                composed={composed}
                views={views}
                resultByProjection={resultByProjection}
                selectedEdgeKey={selectedEdgeKey}
                armedEdgeKeys={armedEdgeKeys}
                selectedVertexKeys={selectedVertexKeys}
                endpointPickActive={endpointPickActive}
                placementBusy={placingView}
                dimensionGhost={placingGhost}
                movingDimensionId={placementReplaces(authoring)}
                onPickEdge={handlePickEdge}
                onPickEndpoint={handlePickEndpoint}
                onPlaceView={handlePlaceView}
                onPlacePointer={handlePlacePointer}
                onPlaceCommit={handlePlaceClick}
                onPlaceRelease={handlePlaceRelease}
                onGrabDimension={handleGrabFromSheet}
                onResetView={handleResetView}
              />
            </div>
          </div>
        ) : hasLayout && sheet && sheetQuery.isError ? (
          <CenterNote
            testId="drawing-compose-error"
            tone="error"
            title="Sheet could not be composed"
            body={
              sheetQuery.error instanceof Error
                ? sheetQuery.error.message
                : "Reload and try again."
            }
          />
        ) : hasLayout && sheet ? (
          <CenterNote
            testId="drawing-composing"
            tone="quiet"
            title="Composing sheet…"
            body="Placing the standard views."
          />
        ) : (
          <SetupHint
            hasParts={parts.length > 0}
            size={effectiveSize}
            orientation={paperOrientation}
            fit={orientationFit}
            onFlipPaper={handleFlipPaper}
            busy={reheading || busy}
          />
        )}

        {/* Honest projection-failure banner (part produced no body). */}
        {evaluation?.part_error ? (
          <div
            role="alert"
            data-testid="drawing-part-error"
            className="absolute bottom-3 left-3 max-w-sm border border-flag bg-anvil px-3 py-2"
          >
            <span className="block font-display text-2xs uppercase tracking-[0.18em] text-flag">
              Projection failed
            </span>
            <span className="mt-1 block font-body text-xs text-mist">
              {evaluation.part_error.message}
            </span>
          </div>
        ) : null}

        {actionError ? (
          <div
            role="alert"
            data-testid="drawing-action-error"
            className="absolute bottom-3 left-3 max-w-sm border border-flag bg-anvil px-3 py-2"
          >
            <span className="block font-display text-2xs uppercase tracking-[0.18em] text-flag">
              Layout failed
            </span>
            <span className="mt-1 block font-body text-xs text-mist">
              {actionError}
            </span>
            <button
              type="button"
              onClick={() => setActionError(null)}
              className="mt-2 font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
            >
              Dismiss
            </button>
          </div>
        ) : null}

        {hasLayout ? (
          // A 2D sheet has no r3f gizmo cube, so reclaim the default right-panel
          // bottom clearance that reserves space for it (frontend-QA P2).
          <FloatingPanel
            side="right"
            title="Views"
            id="drawing-views"
            maxHeightClassName="max-h-[calc(100%-4.5rem)]"
          >
            <div className="flex flex-col gap-3">
              <ViewsPanel
                projecting={projecting}
                projections={requestedViews}
                resultByProjection={resultByProjection}
                composedByProjection={composedByProjection}
              />
              <BendSchedulePanel
                rows={resultByProjection.get("flat_pattern")?.bend_table ?? []}
              />
              <DimensionsPanel
                dimensions={dimensions}
                measuredById={measuredById}
                busy={dimBusy}
                movingId={placementReplaces(authoring)}
                onMove={handleMoveFromPanel}
                onDelete={handleDeleteDimension}
                onHeal={handleHealDimension}
              />
              <NotesPanel
                annotations={annotations}
                busy={noteBusy}
                onAdd={handleAddNote}
                onDelete={handleDeleteNote}
              />
              <PartsListPanel
                sourceKind={effectiveSourceKind}
                lines={bomQuery.data?.lines ?? []}
                totalInstances={bomQuery.data?.total_instances ?? 0}
                loading={bomQuery.isLoading}
                error={bomQuery.error}
                onOpen={handleOpenBomLine}
              />
            </div>
          </FloatingPanel>
        ) : null}

        {/* One chip for the whole authoring gesture: the "pick the second …"
            hint while a two-pick dimension is in progress, then "click to
            place" once the measurement is settled. Same chip, next sentence —
            placing is a continuation of the pick, not a new mode. Non-modal so
            the sheet stays live; Esc steps back one stage. */}
        {hint ? (
          <div
            role="status"
            data-testid="dimension-pick-hint"
            className="pointer-events-none absolute bottom-3 left-1/2 flex -translate-x-1/2 items-center gap-2 border border-brass/60 bg-anvil px-3 py-1.5 shadow-float"
          >
            <span className="font-display text-2xs whitespace-nowrap uppercase tracking-[0.16em] text-brass">
              {hint}
            </span>
            {/* THE PRECISION FALLBACK, not the live reading. The number you are
                watching rides the ghost on the paper (see PlacementGhostLayer);
                this is the field you reach for when the answer is exactly -25.
                Sheet millimetres: a distance on the PAPER, not in the model, so
                it is unit-free by nature — an A3 sheet is 420 mm whatever the
                part is drawn in. The chip stays pointer-transparent so it can
                never swallow a placement click; only the cell takes input. */}
            {placingOffsetMm !== null ? (
              <NumberField
                layout="inline"
                label="Offset"
                unit="mm"
                className="pointer-events-auto w-[13rem] shrink-0"
                ref={offsetFieldRef}
                data-testid="dimension-offset-field"
                data-offset-mm={placingOffsetMm.toFixed(2)}
                aria-label="Dimension offset in sheet millimetres"
                value={offsetText}
                onChange={(event) => handleOffsetTyped(event.target.value)}
                onFocus={() => setOffsetDraft(offsetText)}
                onBlur={() => setOffsetDraft(null)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    commitPlacementRef.current();
                    return;
                  }
                  // Up/Down keep nudging while the caret is in the cell (the
                  // numeric-field convention); Left/Right stay caret motion.
                  const sense =
                    event.key === "ArrowUp"
                      ? 1
                      : event.key === "ArrowDown"
                        ? -1
                        : 0;
                  if (sense !== 0) {
                    event.preventDefault();
                    const step = event.shiftKey
                      ? PLACE_NUDGE_MM * 5
                      : PLACE_NUDGE_MM;
                    setOffsetDraft(null);
                    setAuthoring((state) =>
                      nudgePlacement(state, 0, -sense, step),
                    );
                  }
                }}
              />
            ) : null}
            <span className="font-body text-2xs whitespace-nowrap text-gauge">
              {authoring.kind === "placing"
                ? placingOffsetMm !== null
                  ? "Type a value · arrows nudge · Enter places · Esc back"
                  : "Arrows nudge · Enter places · Esc back"
                : "Esc to cancel"}
            </span>
          </div>
        ) : null}

        {/* The gated dimension author menu — opens by the completing pick. A
            backdrop closes it on an outside click; it renders only for a menu
            state (a single-edge / two-edge / two-endpoint selection), never
            while a second pick is still being made. */}
        {anchor && menuActionList.length > 0 ? (
          <>
            <div
              // Same layer as the menu it dismisses (the menu is the later
              // sibling, so it paints above) — the scrim must cover EVERY
              // page-level surface, including the band.
              className="fixed inset-0 z-menu"
              aria-hidden="true"
              onClick={() => setAuthoring(IDLE)}
            />
            <DimensionAuthorMenu
              actions={menuActionList}
              x={anchor.x}
              y={anchor.y}
              busy={dimBusy}
              onChoose={handleChooseAction}
              onClose={() => setAuthoring(IDLE)}
            />
          </>
        ) : null}
      </main>
    </div>
  );
}
