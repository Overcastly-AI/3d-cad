/**
 * The sketch strip — a horizontal run of title-block cells across the top of
 * the viewport. Plane-pick step: the three datum planes (keyboard path,
 * hover-synced with the 3D sheets). Draw step: tools with their shortcut
 * letters, the buffer count, SAVE and EXIT. Quiet chrome; the viewport keeps
 * the pixels.
 */
import { Panel, PanelActionCell } from "@loft/design";

import { DATUM_PLANES } from "../sketch/plane";
import { useSketchStore } from "../sketch/store";
import type { SketchTool } from "../sketch/tools";

const TOOLS: ReadonlyArray<{
  tool: SketchTool;
  label: string;
  keyHint: string;
  name: string;
}> = [
  { tool: "line", label: "Line", keyHint: "L", name: "Line tool (L)" },
  { tool: "rect", label: "Rect", keyHint: "R", name: "Rectangle tool (R)" },
  { tool: "circle", label: "Circle", keyHint: "C", name: "Circle tool (C)" },
  { tool: "arc", label: "Arc", keyHint: "A", name: "Arc tool (A)" },
];

export interface SketchStripProps {
  onSave: () => void;
  saving: boolean;
  saveError: string | null;
}

export function SketchStrip({ onSave, saving, saveError }: SketchStripProps) {
  const mode = useSketchStore((state) => state.mode);
  const plane = useSketchStore((state) => state.plane);
  const tool = useSketchStore((state) => state.tool);
  const setTool = useSketchStore((state) => state.setTool);
  const choosePlane = useSketchStore((state) => state.choosePlane);
  const setHoveredPlane = useSketchStore((state) => state.setHoveredPlane);
  const hoveredPlane = useSketchStore((state) => state.hoveredPlane);
  const entityCount = useSketchStore((state) => state.entities.length);
  const exit = useSketchStore((state) => state.exit);

  if (mode === "off") return null;

  return (
    <div className="absolute left-3 top-3 max-w-full pr-3">
      <Panel
        aria-label="Sketch"
        data-testid="sketch-strip"
        className="inline-grid grid-flow-col auto-cols-auto divide-x divide-hairline"
      >
        <div className="px-3 py-2">
          <span className="block font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            Sketch
          </span>
          <span
            className="block font-data text-xs text-mist"
            data-testid="sketch-step"
          >
            {mode === "plane" ? "Pick a plane" : `On ${plane ?? "—"}`}
          </span>
        </div>

        {mode === "plane"
          ? DATUM_PLANES.map((name) => (
              <PanelActionCell
                key={name}
                label={name}
                caption="Datum"
                selected={hoveredPlane === name}
                data-testid={`plane-${name}`}
                aria-label={`Sketch on the ${name} plane`}
                onClick={() => choosePlane(name)}
                onMouseEnter={() => setHoveredPlane(name)}
                onMouseLeave={() => setHoveredPlane(null)}
                onFocus={() => setHoveredPlane(name)}
                onBlur={() => setHoveredPlane(null)}
              />
            ))
          : null}

        {mode === "draw" ? (
          <>
            {TOOLS.map(({ tool: t, label, keyHint, name }) => (
              <PanelActionCell
                key={t}
                label={label}
                caption={keyHint}
                selected={tool === t}
                data-testid={`tool-${t}`}
                aria-label={name}
                onClick={() => setTool(t)}
              />
            ))}
            <PanelActionCell
              label={saving ? "Saving…" : "Save sketch"}
              caption={`${entityCount} ${entityCount === 1 ? "entity" : "entities"}`}
              data-testid="sketch-save"
              aria-label="Save sketch"
              aria-busy={saving}
              disabled={saving || entityCount === 0}
              onClick={onSave}
            />
            <PanelActionCell
              label="Exit"
              caption="Esc discards"
              data-testid="sketch-exit"
              aria-label="Exit sketch (discards unsaved entities)"
              disabled={saving}
              onClick={exit}
            />
          </>
        ) : null}
      </Panel>
      {saveError ? (
        <p
          role="alert"
          data-testid="sketch-save-error"
          className="mt-2 max-w-sm border border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
        >
          {saveError}
        </p>
      ) : null}
    </div>
  );
}
