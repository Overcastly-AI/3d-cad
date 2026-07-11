/**
 * The DRO — a machine-shop digital readout pinned to the viewport's bottom
 * edge while sketching. X/Y in the data face with explicit sign and fixed
 * decimals, the SNAP and PLANE cells, and — once the sketch is persisted —
 * the SOLVE cell: degrees of freedom + solver status, the parametric loop's
 * own readout. This is the title-block signature extended into the viewport;
 * it earns its pixels with live precision.
 */
import { Panel, PanelActionCell } from "@loft/design";

import { formatDroMm } from "../lib/format";
import { formatSolveCell } from "../sketch/constraints";
import { SNAP_STEP_MM, useSketchStore } from "../sketch/store";

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
  const toggleSnap = useSketchStore((state) => state.toggleSnap);
  const solve = useSketchStore((state) => state.solve);
  const bound = useSketchStore((state) => state.featureId !== null);

  if (mode !== "draw") return null;
  const solveCell = formatSolveCell(solve, solving);

  return (
    <Panel
      aria-label="Position readout"
      data-testid="sketch-dro"
      className="absolute bottom-3 left-3 inline-grid grid-flow-col auto-cols-auto divide-x divide-hairline"
    >
      {(["x", "y"] as const).map((axis) => (
        <div key={axis} className="min-w-24 px-3 py-2">
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
        label="Snap"
        caption={snapEnabled ? `${SNAP_STEP_MM} mm · G` : "off · G"}
        selected={snapEnabled}
        aria-label={`Grid snap ${SNAP_STEP_MM} mm (G)`}
        data-testid="dro-snap"
        onClick={toggleSnap}
      />
      <div className="px-3 py-2">
        <span className="block font-display text-2xs uppercase tracking-[0.18em] text-gauge">
          Plane
        </span>
        <span className="block font-data text-md text-mist">{plane}</span>
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
