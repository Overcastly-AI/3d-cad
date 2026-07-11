/**
 * The DRO — a machine-shop digital readout pinned to the viewport's bottom
 * edge while sketching. X/Y in the data face with explicit sign and fixed
 * decimals, plus the SNAP and PLANE cells. This is the title-block signature
 * extended into the viewport; it earns its pixels with live precision.
 */
import { Panel, PanelActionCell } from "@loft/design";

import { formatDroMm } from "../lib/format";
import { SNAP_STEP_MM, useSketchStore } from "../sketch/store";

export function SketchDro() {
  const mode = useSketchStore((state) => state.mode);
  const plane = useSketchStore((state) => state.plane);
  const cursor = useSketchStore((state) => state.cursor);
  const snapEnabled = useSketchStore((state) => state.snapEnabled);
  const toggleSnap = useSketchStore((state) => state.toggleSnap);

  if (mode !== "draw") return null;

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
    </Panel>
  );
}
