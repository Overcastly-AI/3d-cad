/**
 * The quiet chrome around the drawing sheet: the centred status note, the
 * sheet switcher with its header cells, and the set-up hint. Split out of
 * `DrawingPage.tsx` (SPLIT-DRAWINGPAGE); behaviour unchanged.
 */
import { type ReactNode, useEffect, useRef } from "react";

import type {
  SheetContent,
  SheetResponse,
  SheetSize,
} from "../../api/drawings";
import { type OrientationFit, sheetSizeLabel } from "../../drawing/layout";
import {
  CONVENTION_NAME,
  ORIENTATION_NAME,
  OTHER_CONVENTION,
  OTHER_ORIENTATION,
  type SheetOrientation,
  type SheetProjection,
} from "./sheetHeader";

/** A centered status/error note over the bench. */
export function CenterNote({
  testId,
  tone,
  title,
  body,
}: {
  testId: string;
  tone: "quiet" | "error";
  title: string;
  body: string;
}) {
  return (
    <div
      data-testid={testId}
      role={tone === "error" ? "alert" : "status"}
      className="absolute inset-0 flex items-center justify-center p-6"
    >
      <div className="max-w-sm border border-hairline bg-anvil px-4 py-3 text-center shadow-float">
        <p
          className={`font-display text-2xs uppercase tracking-[0.2em] ${
            tone === "error" ? "text-flag" : "text-gauge"
          }`}
        >
          {title}
        </p>
        <p className="mt-1 font-body text-sm text-mist">{body}</p>
      </div>
    </div>
  );
}

/**
 * The ISO projection-convention symbol — a truncated cone drawn twice: its
 * elevation (the trapezoid) and its end view (the two concentric circles). This
 * is the drawing's own vernacular rather than a generic UI icon, and it is the
 * one place this surface spends any boldness; everything around it stays quiet.
 *
 * WHICH SIDE THE CIRCLES SIT ON *IS* THE CONVENTION, and it is derived from the
 * SAME rule the server composer applies to the sheet (`bounds_aware_layout`'s
 * `right_sx`: +1 for third angle, -1 for first). The circles are the frustum's
 * RIGHT-side view, so third angle places them to the RIGHT of the elevation and
 * first angle to the LEFT — exactly where the sheet's own right view will land.
 * The glyph therefore teaches the layout the user is about to see. The two
 * symbols are exact mirrors (one path, one `scale(-1,1)`), as the standard's
 * pair are, with the frustum tapering toward its end view.
 *
 * Drawn in `currentColor` so it inherits the cell's brass/gauge state — no hex
 * literal, and one palette between the chrome and the sheet.
 */
function ProjectionSymbol({ convention }: { convention: SheetProjection }) {
  return (
    <svg
      viewBox="0 0 40 16"
      width="35"
      height="14"
      aria-hidden="true"
      focusable="false"
      className="shrink-0"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.1}
      strokeLinejoin="round"
    >
      <g
        transform={
          convention === "first_angle"
            ? "translate(40 0) scale(-1 1)"
            : undefined
        }
      >
        {/* Elevation: the frustum, large end out, tapering toward its end view.
            The two circles are that SAME frustum's ends seen down its axis —
            outer radius = the large end's half-height, inner = the small end's —
            so the pair reads as one object rather than two marks. */}
        <path d="M1.6 1 L17 3.75 L17 12.25 L1.6 15 Z" />
        <circle cx="32" cy="8" r="7" />
        <circle cx="32" cy="8" r="4.25" />
      </g>
    </svg>
  );
}

/** The paper glyph — a sheet in its orientation, with the title-block corner
 * scribed in so it reads as THIS product's sheet rather than a generic page. */
function OrientationSymbol({ orientation }: { orientation: SheetOrientation }) {
  const landscape = orientation === "landscape";
  const w = landscape ? 14 : 9.5;
  const h = landscape ? 9.5 : 14;
  const x = (16 - w) / 2;
  const y = (16 - h) / 2;
  const block = 4;
  return (
    <svg
      viewBox="0 0 16 16"
      width="13"
      height="13"
      aria-hidden="true"
      focusable="false"
      className="shrink-0"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.2}
      strokeLinejoin="round"
    >
      <rect x={x} y={y} width={w} height={h} />
      <path
        d={`M${x + w - block} ${y + h} L${x + w - block} ${y + h - 3} L${x + w} ${y + h - 3}`}
      />
    </svg>
  );
}

/** One header cell in the sheet strip — a stamped reading that is also the
 * control that changes it. Same idiom as a tab (hairline seat, brass on focus),
 * one notch quieter so the tabs stay the primary rail. */
function SheetHeaderCell({
  testid,
  label,
  onActivate,
  busy,
  attrs,
  tone = "quiet",
  children,
}: {
  testid: string;
  label: string;
  onActivate: () => void;
  busy: boolean;
  attrs: Record<string, string>;
  /** `stamp` is the drafting standard the sheet DECLARES — it has to be
   * readable at a glance, so it carries the same ink as the active tab.
   * `quiet` is for a secondary control whose state the paper itself shows. */
  tone?: "stamp" | "quiet";
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      data-testid={testid}
      aria-label={label}
      title={label}
      disabled={busy}
      onClick={onActivate}
      {...attrs}
      className={`flex shrink-0 items-center gap-1.5 border border-transparent px-1.5 py-1 font-display text-2xs uppercase tracking-[0.14em] transition-colors duration-fast hover:border-hairline hover:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass disabled:pointer-events-none disabled:opacity-40 ${
        tone === "stamp" ? "text-mist" : "text-gauge"
      }`}
    >
      {children}
    </button>
  );
}

/**
 * The sheet header (FINDINGS #18 switcher + REACH-3 sheet convention) — a
 * compact strip in the top-left margin that says WHICH sheet and HOW it is set
 * up, and lets both be changed from where they are read. A quiet precision
 * instrument so the sheet stays the hero: brass underline on the active tab,
 * keyboard-first (every cell is a real button), all wired to real state/actions
 * (mandate 3a — nothing here is decoration).
 *
 * The convention cell stamps the ISO symbol for the sheet's projection standard
 * and flips it on activation; the orientation cell does the same for the paper,
 * and marks itself `data-proposed` when it already matches the orientation the
 * part's own extents argue for.
 *
 * The orientation cell states ONLY what it delivers (REACH-3-FLOW P1-2). It used
 * to read "switch to portrait (1:2)" and then return a sheet still drawn at 1:5
 * — documents refuses a per-view re-scale on a laid-out sheet, so no amount of
 * client work can honour that. The fit comparison lives on the set-up screen's
 * paper cell instead, where the scale is still free; here the cell says what a
 * flip actually does, which is re-draft the SAME scale on the other paper.
 */
export function SheetTabs({
  sheets,
  activeIndex,
  onSelect,
  onAdd,
  adding,
  sheet,
  fit,
  drawnScale,
  onFlipConvention,
  onFlipOrientation,
  reheading,
}: {
  sheets: readonly SheetContent[];
  activeIndex: number;
  onSelect: (index: number) => void;
  onAdd: () => void;
  adding: boolean;
  sheet: SheetResponse | null;
  fit: OrientationFit | null;
  /** The scale the sheet is ACTUALLY drawn at, off the stored views. */
  drawnScale: string;
  onFlipConvention: () => void;
  onFlipOrientation: () => void;
  reheading: boolean;
}) {
  const convention = sheet?.projection ?? "third_angle";
  const orientation = sheet?.orientation ?? "landscape";
  const nextConvention = OTHER_CONVENTION[convention];
  const nextOrientation = OTHER_ORIENTATION[orientation];
  // A scrolling rail must still show you where you ARE. Adding an eleventh
  // sheet selects it, and without this the tab that just became active sits off
  // the end of the rail — the switcher would say "SHEET 10" while the page
  // showed sheet 11. Instant, not smooth: this is a state correction, not an
  // animation, so there is no motion for `prefers-reduced-motion` to suppress.
  const railRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const rail = railRef.current;
    const tab = rail?.querySelector<HTMLElement>('[role="tab"][data-active]');
    tab?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [activeIndex, sheets.length]);
  // The strip is capped and the TAB RAIL scrolls inside it, so the two header
  // cells stay put however many sheets exist. Before: eleven sheets pushed the
  // convention and orientation cells off the right of a 1024 viewport — the
  // controls that DECLARE the sheet's standard were the first thing a
  // many-sheet drawing lost, with nothing to say where they had gone.
  return (
    <div className="absolute left-3 top-3 z-overlay flex max-w-[calc(100%-1.5rem)] items-center gap-1 border border-hairline bg-anvil/95 px-1.5 py-1 shadow-float backdrop-blur-sm">
      <div
        ref={railRef}
        className="flex min-w-0 items-center gap-1 overflow-x-auto"
        role="tablist"
        aria-label="Drawing sheets"
        data-testid="sheet-tabs"
      >
        {sheets.map((content, index) => {
          const active = index === activeIndex;
          return (
            <button
              key={content.sheet.id}
              type="button"
              role="tab"
              aria-selected={active}
              data-testid={`sheet-tab-${index}`}
              data-active={active || undefined}
              onClick={() => onSelect(index)}
              className={`shrink-0 whitespace-nowrap border-b-2 px-2.5 py-1 font-display text-2xs uppercase tracking-[0.14em] transition-colors duration-fast focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass ${
                active
                  ? "border-brass text-mist"
                  : "border-transparent text-gauge hover:text-mist"
              }`}
            >
              {content.sheet.name}
            </button>
          );
        })}
      </div>
      {/* ADD sits OUTSIDE the scrolling rail, beside the header cells. It is an
          action, not a tab (it never carried `role="tab"`, so it did not belong
          inside the tablist either), and inside the rail an eleven-sheet drawing
          would scroll the only way to make a twelfth off the end of it. */}
      <button
        type="button"
        onClick={onAdd}
        disabled={adding}
        data-testid="sheet-tab-add"
        aria-label={
          fit
            ? `Add sheet — ${ORIENTATION_NAME[fit.proposed]} at ${fit.scaleByOrientation[fit.proposed]}`
            : "Add sheet"
        }
        data-proposed-orientation={fit?.proposed}
        className="ml-0.5 shrink-0 rounded-sm px-1.5 py-1 font-display text-xs leading-none text-gauge transition-colors duration-fast hover:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass disabled:pointer-events-none disabled:opacity-40"
      >
        {adding ? "…" : "+"}
      </button>
      {sheet ? (
        <>
          <span aria-hidden="true" className="mx-1 h-4 w-px bg-hairline" />
          <SheetHeaderCell
            testid="sheet-projection"
            label={`Projection convention: ${CONVENTION_NAME[convention]} — switch to ${CONVENTION_NAME[nextConvention]}`}
            onActivate={onFlipConvention}
            busy={reheading}
            tone="stamp"
            attrs={{ "data-projection": convention }}
          >
            <ProjectionSymbol convention={convention} />
            <span>{convention === "third_angle" ? "3rd" : "1st"}</span>
          </SheetHeaderCell>
          <SheetHeaderCell
            testid="sheet-orientation"
            label={`Sheet orientation: ${ORIENTATION_NAME[orientation]}, drawn at ${drawnScale} — switch to ${ORIENTATION_NAME[nextOrientation]} paper, keeping ${drawnScale}${
              fit
                ? `. A fresh ${ORIENTATION_NAME[nextOrientation]} sheet would fit this at ${fit.scaleByOrientation[nextOrientation]}.`
                : "."
            }`}
            onActivate={onFlipOrientation}
            busy={reheading}
            attrs={{
              "data-orientation": orientation,
              ...(fit
                ? {
                    "data-fit-landscape": fit.scaleByOrientation.landscape,
                    "data-fit-portrait": fit.scaleByOrientation.portrait,
                    "data-proposed": String(orientation === fit.proposed),
                  }
                : {}),
            }}
          >
            <OrientationSymbol orientation={orientation} />
          </SheetHeaderCell>
        </>
      ) : null}
    </div>
  );
}

/**
 * The empty-bench invitation before any views are laid out — and the one place
 * the orientation PROPOSAL is answerable before it costs anything.
 *
 * The paper cell is the same instrument the sheet header wears after layout
 * (`SheetHeaderCell` + `OrientationSymbol`), deliberately: one vocabulary for
 * one decision, so what the user learns here still reads after the sheet
 * exists. It only appears once there is a measured proposal to state — an
 * unmeasurable source gets no cell rather than a cell asserting the default,
 * which would be chrome that only decorates (mandate 3a).
 */
export function SetupHint({
  hasParts,
  size,
  orientation,
  fit,
  onFlipPaper,
  busy,
}: {
  hasParts: boolean;
  size: SheetSize;
  orientation: SheetOrientation;
  fit: OrientationFit | null;
  onFlipPaper: () => void;
  busy: boolean;
}) {
  const next = OTHER_ORIENTATION[orientation];
  const paper = `${sheetSizeLabel(size)} ${ORIENTATION_NAME[orientation]}`;
  return (
    <div
      data-testid="drawing-setup-hint"
      style={{ pointerEvents: "none" }}
      className="absolute inset-0 flex items-center justify-center p-6"
    >
      <div className="max-w-md text-center">
        <p className="font-display text-2xs uppercase tracking-[0.2em] text-gauge">
          Empty sheet
        </p>
        <h2 className="mt-2 font-body text-lg text-mist">
          {hasParts ? "Lay out the standard views." : "Create a part first."}
        </h2>
        <p className="mt-1 font-body text-sm text-gauge">
          {hasParts
            ? "Choose a part, sheet size and scale above, then lay out the standard views — front, top, right and isometric — or unfold a sheet-metal part's flat pattern with its bend table."
            : "A drawing projects a part. Model a part, then return to draft it."}
        </p>
        {hasParts && fit ? (
          <div className="mt-4 flex items-center justify-center [pointer-events:auto]">
            <SheetHeaderCell
              testid="setup-paper"
              label={`Sheet paper: ${paper}, fits ${fit.scaleByOrientation[orientation]} — switch to ${ORIENTATION_NAME[next]} (${fit.scaleByOrientation[next]})`}
              onActivate={onFlipPaper}
              busy={busy}
              tone="stamp"
              attrs={{
                "data-orientation": orientation,
                "data-fit-landscape": fit.scaleByOrientation.landscape,
                "data-fit-portrait": fit.scaleByOrientation.portrait,
                "data-proposed": String(orientation === fit.proposed),
              }}
            >
              <OrientationSymbol orientation={orientation} />
              <span>
                {paper} · {fit.scaleByOrientation[orientation]}
              </span>
            </SheetHeaderCell>
          </div>
        ) : null}
      </div>
    </div>
  );
}
