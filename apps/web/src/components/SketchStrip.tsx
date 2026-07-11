/**
 * The sketch strip — a horizontal run of title-block cells across the top of
 * the viewport. Plane-pick step: the three datum planes (keyboard path,
 * hover-synced with the 3D sheets). Draw step: tools with their shortcut
 * letters, the buffer count, SAVE and EXIT — plus a second ruled row, the
 * CONSTRAIN strip: the six constraint verbs and the live selection readout.
 * One keyboard, two vocabularies: with nothing selected the letters arm
 * tools; with a selection they are constraint verbs. Quiet chrome; the
 * viewport keeps the pixels.
 */
import { Panel, PanelActionCell } from "@loft/design";

import {
  describeSelection,
  selectionAllConstruction,
  type ConstraintAction,
} from "../sketch/constraints";
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

const CONSTRAINTS: ReadonlyArray<{
  action: ConstraintAction;
  label: string;
  keyHint: string;
  name: string;
}> = [
  {
    action: "horizontal",
    label: "Horiz",
    keyHint: "H",
    name: "Horizontal constraint (H, on selected lines)",
  },
  {
    action: "vertical",
    label: "Vert",
    keyHint: "V",
    name: "Vertical constraint (V, on selected lines)",
  },
  {
    action: "distance",
    label: "Dist",
    keyHint: "D",
    name: "Distance dimension (D, on one selected line)",
  },
  {
    action: "radius",
    label: "Radius",
    keyHint: "R",
    name: "Radius dimension (R, on one selected circle or arc)",
  },
  {
    action: "fixed",
    label: "Fix",
    keyHint: "X",
    name: "Fix point (X, on selected points)",
  },
  {
    action: "coincident",
    label: "Coinc",
    keyHint: "C",
    name: "Coincident constraint (C, on two selected points)",
  },
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
  const constraintCount = useSketchStore((state) => state.constraints.length);
  const selection = useSketchStore((state) => state.selection);
  const entities = useSketchStore((state) => state.entities);
  const applyConstraint = useSketchStore((state) => state.applyConstraint);
  const toggleConstruction = useSketchStore(
    (state) => state.toggleConstruction,
  );
  const hint = useSketchStore((state) => state.hint);
  const bound = useSketchStore((state) => state.featureId !== null);
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
              label={saving ? "Saving…" : bound ? "Finish" : "Save sketch"}
              caption={
                bound
                  ? "edits save live"
                  : `${entityCount} ${entityCount === 1 ? "entity" : "entities"}`
              }
              data-testid="sketch-save"
              aria-label={bound ? "Finish sketch (saved)" : "Save sketch"}
              aria-busy={saving}
              disabled={saving || (!bound && entityCount === 0)}
              onClick={onSave}
            />
            <PanelActionCell
              label="Exit"
              caption={bound ? "Esc closes" : "Esc discards"}
              data-testid="sketch-exit"
              aria-label={
                bound
                  ? "Exit sketch (saved)"
                  : "Exit sketch (discards unsaved entities)"
              }
              disabled={saving}
              onClick={exit}
            />
          </>
        ) : null}
      </Panel>

      {mode === "draw" ? (
        <Panel
          aria-label="Constraints"
          data-testid="constraint-strip"
          className="mt-2 inline-grid grid-flow-col auto-cols-auto divide-x divide-hairline"
        >
          <div className="px-3 py-2">
            <span className="block font-display text-2xs uppercase tracking-[0.18em] text-gauge">
              Constrain
            </span>
            <span
              className="block font-data text-xs text-mist"
              data-testid="selection-readout"
            >
              {describeSelection(selection)}
              {constraintCount > 0 ? ` · ${constraintCount} applied` : ""}
            </span>
          </div>
          {CONSTRAINTS.map(({ action, label, keyHint, name }) => (
            <PanelActionCell
              key={action}
              label={label}
              caption={keyHint}
              data-testid={`constraint-${action}`}
              aria-label={name}
              onClick={() => applyConstraint(action)}
            />
          ))}
          <PanelActionCell
            label="Constr"
            caption="N"
            selected={selectionAllConstruction(selection, entities)}
            data-testid="sketch-construction"
            aria-label="Toggle construction geometry (N, on selected entities) — reference-only, excluded from the extrude profile"
            onClick={toggleConstruction}
          />
        </Panel>
      ) : null}

      {hint ? (
        <p
          role="status"
          data-testid="constraint-hint"
          className="mt-2 max-w-sm border border-hairline bg-anvil px-3 py-2 font-body text-xs text-gauge"
        >
          {hint}
        </p>
      ) : null}
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
