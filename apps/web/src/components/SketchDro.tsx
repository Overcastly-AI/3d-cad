/**
 * The DRO — a machine-shop digital readout pinned to the viewport's bottom
 * edge while sketching. X/Y in the data face with explicit sign and fixed
 * decimals, the SNAP and PLANE cells, and — once the sketch is persisted —
 * the SOLVE cell: degrees of freedom + solver status, the parametric loop's
 * own readout. This is the title-block signature extended into the viewport;
 * it earns its pixels with live precision.
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
  const bound = useSketchStore((state) => state.featureId !== null);

  if (mode !== "draw") return null;
  const solveCell = formatSolveCell(solve, solving);

  // The SNAP cell reports the MODE (what is armed); the mark at the cursor
  // reports the live candidate. One job each — nothing does double duty.
  // Naming "points" is the whole point of the cell: entity snapping is always
  // on, so a caption that only mentioned the grid would understate it.
  const primaryModifier = isMacPlatform() ? "⌘" : "Ctrl";
  const snapCaption = snapSuppressed
    ? `held off · ${primaryModifier}`
    : snapEnabled
      ? `points · ${snapStepMm} mm · G`
      : "points · no grid · G";

  return (
    <Panel
      aria-label="Position readout"
      data-testid="sketch-dro"
      className="absolute bottom-3 left-3 inline-grid grid-flow-col auto-cols-auto divide-x divide-hairline"
    >
      {(["x", "y"] as const).map((axis) => (
        <div key={axis} className="min-w-[6rem] px-3 py-2">
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
      <PanelActionCell
        icon={<GridSnapIcon />}
        label="Snap"
        caption={snapCaption}
        selected={snapEnabled && !snapSuppressed}
        aria-label={`Snap — endpoints, midpoints, centres and intersections always snap; grid ${snapStepMm} mm is ${snapEnabled ? "on" : "off"} (G to toggle); hold ${primaryModifier} to place freehand`}
        data-testid="dro-snap"
        data-snap-suppressed={snapSuppressed || undefined}
        onClick={toggleSnap}
      />
      {/* THE GRID STEP (helical-gear gap G2). The store has always had a
          configurable step and nothing ever set it, so every sketch snapped to
          1 mm. It lives HERE, beside the SNAP cell that reports it, and not in
          the command band: a permanent 140 px control in the band pushed the
          offer rail's words off at 1280 px ("D R Del" instead of "Diameter,
          Radius, Delete"), which is chrome eating the band's most specific
          information to make room for a setting. Offered in the document's
          unit, always listing the step in use. */}
      <div className="flex items-center px-3 py-2">
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
      <div className="px-3 py-2">
        <span className="block font-display text-2xs uppercase tracking-[0.18em] text-gauge">
          Plane
        </span>
        <span
          className="block font-data text-md text-mist"
          data-testid="dro-plane"
        >
          {describePlane(plane)}
        </span>
      </div>
      {bound || solve !== null ? (
        <div className="px-3 py-2">
          <span className="block font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            Solve
          </span>
          <span
            className={`block font-data text-md tabular-nums ${SOLVE_TONE_CLASS[solveCell.tone]}`}
            data-testid="dro-solve"
            aria-live="polite"
          >
            {solveCell.value}
          </span>
        </div>
      ) : null}
    </Panel>
  );
}
