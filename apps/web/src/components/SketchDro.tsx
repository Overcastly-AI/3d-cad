/**
 * The DRO — a machine-shop digital readout pinned to the viewport's bottom
 * edge while sketching. This is the title-block signature extended into the
 * viewport, and it earns its pixels with live precision.
 *
 * TWO TIERS, because the readout reports two kinds of thing:
 *
 *   · the TOP tier is the HAND: X/Y of the cursor in the data face (explicit
 *     sign, fixed decimals), what snaps (SNAP) and at what pitch (GRID). It
 *     changes as you move.
 *   · the BOTTOM tier is the SKETCH: the plane it is on and the solver's
 *     verdict (SOLVE: degrees of freedom and status). It changes when the
 *     geometry does.
 *
 * ONE FOOTPRINT, whatever it says. The DRO floats over the canvas, so a cell
 * that grows with its text moves chrome over the geometry being drawn. The
 * single-row DRO did that. At 1280x800 it ran 12..593 px until the sketch's
 * first save mounted the SOLVE cell, then 687 px for "SOLVING…", then 834 px
 * for "DOF 3 · UNDER-CONSTRAINED". That crossed the centre line, where the
 * sketch origin sits, and it moved again on every snap toggle and grid change.
 * A click aimed there hit chrome or canvas depending on the solver's timing
 * (`constraints.spec.ts:1112`, fixed in `8c55183`). So:
 *
 *   · every column is a FIXED width, sized to the longest thing it can say
 *     (`DRO_COLUMNS`);
 *   · SOLVE is always present, reading "—" until there is a verdict, and it
 *     gets the width of two columns, which fits the longest verdict;
 *   · the PLANE label is the one unbounded string (a datum can be named
 *     anything), so it truncates and the full name is its tooltip.
 *
 * `sketch-dro-footprint.spec.ts` watches the box every frame through all of
 * this, at 1280 and 1440, and holds it left of the canvas centre.
 */
import {
  GridSnapIcon,
  InlineSelect,
  Panel,
  PanelActionCell,
  isMacPlatform,
} from "@loft/design";

import { formatDroMm } from "../lib/format";
import { formatSolveCell } from "../sketch/constraints";
import { describePlane } from "../sketch/plane";
import { gridStepOptions } from "../sketch/pointEntry";
import { useSketchStore } from "../sketch/store";
import { useDocumentLengthUnit } from "../units/documentUnit";

const SOLVE_TONE_CLASS = {
  brass: "text-brass",
  mist: "text-mist",
  flag: "text-flag",
  gauge: "text-gauge",
} as const;

/**
 * X, Y, SNAP, GRID. X and Y hold "-99999.99" (100 m) in the data face. SNAP
 * holds its longest caption, "points · no grid · G". GRID holds the longest
 * step label `gridStepOptions` can produce, 12 characters ("0.0000328 ft":
 * 0.01 mm listed in a foot document). A native select is as wide as its widest
 * option, and the panel does not clip, so a label that did not fit would spill
 * over the canvas while the DRO's own box stayed put.
 */
const DRO_COLUMNS = "grid-cols-[6.25rem_6.25rem_11.5rem_12rem]";

/** The inline eyebrow of a bottom-tier cell. */
const TIER_LABEL =
  "shrink-0 font-display text-2xs uppercase tracking-[0.18em] text-gauge";

export interface SketchDroProps {
  /** True while a save or re-evaluate round-trip is in flight. */
  solving: boolean;
}

export function SketchDro({ solving }: SketchDroProps) {
  const mode = useSketchStore((state) => state.mode);
  const plane = useSketchStore((state) => state.plane);
  const cursor = useSketchStore((state) => state.cursor);
  const snapEnabled = useSketchStore((state) => state.snapEnabled);
  const snapStepMm = useSketchStore((state) => state.snapStepMm);
  const snapSuppressed = useSketchStore((state) => state.snapSuppressed);
  const toggleSnap = useSketchStore((state) => state.toggleSnap);
  const setSnapStep = useSketchStore((state) => state.setSnapStep);
  const lengthUnit = useDocumentLengthUnit();
  const solve = useSketchStore((state) => state.solve);

  if (mode !== "draw") return null;
  const solveCell = formatSolveCell(solve, solving);
  const planeLabel = describePlane(plane);

  // The SNAP cell reports the MODE (what is armed); the mark at the cursor
  // reports the live candidate. One job each — nothing does double duty.
  // Naming "points" is the whole point of the cell: entity snapping is always
  // on, so a caption that only mentioned the grid would understate it. The
  // grid's PITCH is not repeated here: the GRID cell beside it states it, and
  // saying it twice made this cell change width with every step.
  const primaryModifier = isMacPlatform() ? "⌘" : "Ctrl";
  const snapCaption = snapSuppressed
    ? `held off · ${primaryModifier}`
    : snapEnabled
      ? "points · grid · G"
      : "points · no grid · G";

  return (
    <Panel
      aria-label="Position readout"
      data-testid="sketch-dro"
      className={`absolute bottom-3 left-3 grid ${DRO_COLUMNS}`}
    >
      {(["x", "y"] as const).map((axis) => (
        <div
          key={axis}
          className={`min-w-0 px-3 py-2 ${axis === "y" ? "border-l border-hairline" : ""}`}
        >
          <span className="block font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {axis} · mm
          </span>
          <span
            className="block font-data text-md tabular-nums text-brass"
            data-testid={`dro-${axis}`}
          >
            {formatDroMm(cursor?.[axis] ?? null)}
          </span>
        </div>
      ))}
      <div className="min-w-0 border-l border-hairline">
        <PanelActionCell
          icon={<GridSnapIcon />}
          label="Snap"
          caption={snapCaption}
          selected={snapEnabled && !snapSuppressed}
          aria-label={`Snap — endpoints, midpoints, centres and intersections always snap; grid ${snapStepMm} mm is ${snapEnabled ? "on" : "off"} (G to toggle); hold ${primaryModifier} to place freehand`}
          data-testid="dro-snap"
          data-snap-suppressed={snapSuppressed || undefined}
          // Never wraps: a caption that wrapped would change the DRO's height.
          className="h-full whitespace-nowrap"
          onClick={toggleSnap}
        />
      </div>
      {/* THE GRID STEP (helical-gear gap G2). The store has always had a
          configurable step and nothing ever set it, so every sketch snapped to
          1 mm. It lives HERE, beside the SNAP cell that reports it, and not in
          the command band: a permanent 140 px control in the band pushed the
          offer rail's words off at 1280 px ("D R Del" instead of "Diameter,
          Radius, Delete"), which is chrome eating the band's most specific
          information to make room for a setting. Offered in the document's
          unit, always listing the step in use. */}
      <div className="flex min-w-0 items-center border-l border-hairline px-3 py-2">
        <InlineSelect
          eyebrow="Grid"
          aria-label="Grid snap step"
          data-testid="sketch-grid-step"
          options={gridStepOptions(lengthUnit, snapStepMm).map((step) => ({
            value: String(step.mm),
            label: step.label,
          }))}
          value={String(snapStepMm)}
          onChange={(event) => setSnapStep(Number(event.target.value))}
        />
      </div>
      <div
        className="col-span-2 flex min-w-0 items-baseline gap-2 border-t border-hairline px-3 py-1.5"
        title={planeLabel}
      >
        <span className={TIER_LABEL}>Plane</span>
        <span
          className="min-w-0 truncate font-data text-md text-mist"
          data-testid="dro-plane"
        >
          {planeLabel}
        </span>
      </div>
      <div className="col-span-2 flex min-w-0 items-baseline gap-2 border-l border-t border-hairline px-3 py-1.5">
        <span className={TIER_LABEL}>Solve</span>
        <span
          className={`min-w-0 truncate font-data text-md tabular-nums ${SOLVE_TONE_CLASS[solveCell.tone]}`}
          data-testid="dro-solve"
          aria-live="polite"
        >
          {solveCell.value}
        </span>
      </div>
    </Panel>
  );
}
