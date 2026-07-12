/**
 * The sketch toolbar — one thin title-block row across the top of the
 * viewport, icon-forward. Plane-pick step: the three datum planes (keyboard
 * path, hover-synced with the 3D sheets). Draw step, all on a single ruled
 * row so the viewport keeps the pixels: a flat status cell (plane + live
 * selection), the four sketch tools as scribed icons, the twelve constraint
 * verbs grouped by kind (Geometric / Dimensional / Relational) behind labeled
 * flyouts, the Construction toggle, then SAVE and EXIT as icon buttons —
 * their counts/reasons engraved in tooltips, never stacked into tall cells.
 *
 * One keyboard, two vocabularies survives untouched: the global key handler
 * still arms tools (L/R/C/A) with nothing selected and fires constraint verbs
 * (H/V/D/R/X/C/P/L/T/E/S/O + N) with a selection. The toolbar is the
 * DISCOVERABLE surface — every icon's tooltip engraves its accelerator — but
 * the letters remain the fast path. Quiet chrome; the viewport keeps the
 * pixels.
 */
import {
  ArcIcon,
  CheckIcon,
  CircleIcon,
  CloseIcon,
  CoincidentIcon,
  ConcentricIcon,
  ConstructionIcon,
  DistanceIcon,
  EqualIcon,
  FixedIcon,
  Flyout,
  type FlyoutItem,
  HorizontalIcon,
  LineIcon,
  Panel,
  ParallelIcon,
  PerpendicularIcon,
  RadiusIcon,
  RectIcon,
  SymmetricIcon,
  TangentIcon,
  ToolButton,
  ToolGroup,
  VerticalIcon,
} from "@loft/design";
import type { ReactNode } from "react";

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
  icon: ReactNode;
}> = [
  {
    tool: "line",
    label: "Line",
    keyHint: "L",
    name: "Line tool (L)",
    icon: <LineIcon />,
  },
  {
    tool: "rect",
    label: "Rect",
    keyHint: "R",
    name: "Rectangle tool (R)",
    icon: <RectIcon />,
  },
  {
    tool: "circle",
    label: "Circle",
    keyHint: "C",
    name: "Circle tool (C)",
    icon: <CircleIcon />,
  },
  {
    tool: "arc",
    label: "Arc",
    keyHint: "A",
    name: "Arc tool (A)",
    icon: <ArcIcon />,
  },
];

interface ConstraintSpec {
  action: ConstraintAction;
  label: string;
  keyHint: string;
  name: string;
  icon: ReactNode;
}

/**
 * The constraint verbs, grouped by the family the constraint belongs to —
 * the same taxonomy the docs call out: Geometric (orientation of curves),
 * Dimensional (driving values), Relational (ties between points/entities).
 * Structure encodes the real vocabulary, not decoration.
 */
const CONSTRAINT_GROUPS: ReadonlyArray<{
  key: string;
  eyebrow: string;
  triggerLabel: string;
  triggerIcon: ReactNode;
  items: readonly ConstraintSpec[];
}> = [
  {
    key: "geometric",
    eyebrow: "Geometric",
    triggerLabel: "Geometric",
    triggerIcon: <PerpendicularIcon />,
    items: [
      {
        action: "horizontal",
        label: "Horizontal",
        keyHint: "H",
        name: "Horizontal constraint (H, on selected lines)",
        icon: <HorizontalIcon />,
      },
      {
        action: "vertical",
        label: "Vertical",
        keyHint: "V",
        name: "Vertical constraint (V, on selected lines)",
        icon: <VerticalIcon />,
      },
      {
        action: "parallel",
        label: "Parallel",
        keyHint: "P",
        name: "Parallel constraint (P, on two selected lines)",
        icon: <ParallelIcon />,
      },
      {
        action: "perpendicular",
        label: "Perpendicular",
        keyHint: "L",
        name: "Perpendicular constraint (L, on two selected lines)",
        icon: <PerpendicularIcon />,
      },
      {
        action: "tangent",
        label: "Tangent",
        keyHint: "T",
        name: "Tangent constraint (T, on a selected line and arc/circle, or two curves)",
        icon: <TangentIcon />,
      },
    ],
  },
  {
    key: "dimensional",
    eyebrow: "Dimensional",
    triggerLabel: "Dimension",
    triggerIcon: <DistanceIcon />,
    items: [
      {
        action: "distance",
        label: "Distance",
        keyHint: "D",
        name: "Distance dimension (D, on one selected line)",
        icon: <DistanceIcon />,
      },
      {
        action: "radius",
        label: "Radius",
        keyHint: "R",
        name: "Radius dimension (R, on one selected circle or arc)",
        icon: <RadiusIcon />,
      },
      {
        action: "equal",
        label: "Equal",
        keyHint: "E",
        name: "Equal constraint (E, on two selected lines or two circles/arcs)",
        icon: <EqualIcon />,
      },
    ],
  },
  {
    key: "relational",
    eyebrow: "Relational",
    triggerLabel: "Relational",
    triggerIcon: <CoincidentIcon />,
    items: [
      {
        action: "coincident",
        label: "Coincident",
        keyHint: "C",
        name: "Coincident constraint (C, on two selected points)",
        icon: <CoincidentIcon />,
      },
      {
        action: "concentric",
        label: "Concentric",
        keyHint: "O",
        name: "Concentric constraint (O, on two selected circles or arcs)",
        icon: <ConcentricIcon />,
      },
      {
        action: "symmetric",
        label: "Symmetric",
        keyHint: "S",
        name: "Symmetric constraint (S, on two selected points about a selected line)",
        icon: <SymmetricIcon />,
      },
      {
        action: "fixed",
        label: "Fixed",
        keyHint: "X",
        name: "Fix point (X, on selected points)",
        icon: <FixedIcon />,
      },
    ],
  },
];

export interface SketchStripProps {
  onSave: () => void;
  saving: boolean;
  saveError: string | null;
}

/**
 * The strip's one-line status cell — the title-block reading folded flat:
 * the active plane, and (while drawing) the live selection, on a single
 * gauge-face line so the toolbar stays icon-thin. No stacked eyebrow.
 */
function StatusCell({ children }: { children: ReactNode }) {
  return (
    <div className="flex shrink-0 items-center gap-2 whitespace-nowrap px-3 font-data text-xs">
      {children}
    </div>
  );
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
      {/* One thin instrument row: status → draw tools → constraint families →
          construction → finish. Collapsed from the former two-panel stack so
          the viewport keeps the pixels (chrome recedes). */}
      <Panel
        aria-label="Sketch"
        data-testid="sketch-strip"
        className="flex items-stretch divide-x divide-hairline"
      >
        <StatusCell>
          <span
            className={mode === "plane" ? "text-mist" : "text-mist"}
            data-testid="sketch-step"
          >
            {mode === "plane" ? "Pick a plane" : `On ${plane ?? "—"}`}
          </span>
          {mode === "draw" ? (
            <>
              <span aria-hidden className="text-etch">
                ·
              </span>
              <span className="text-gauge" data-testid="selection-readout">
                {describeSelection(selection)}
                {constraintCount > 0 ? ` · ${constraintCount} applied` : ""}
              </span>
            </>
          ) : null}
        </StatusCell>

        {mode === "plane" ? (
          <ToolGroup aria-label="Datum plane">
            {DATUM_PLANES.map((name) => (
              <ToolButton
                key={name}
                icon={
                  <span className="font-display text-2xs tracking-[0.08em]">
                    {name}
                  </span>
                }
                label={`${name} plane`}
                showLabel={false}
                active={hoveredPlane === name}
                data-testid={`plane-${name}`}
                aria-label={`Sketch on the ${name} plane`}
                onClick={() => choosePlane(name)}
                onMouseEnter={() => setHoveredPlane(name)}
                onMouseLeave={() => setHoveredPlane(null)}
                onFocus={() => setHoveredPlane(name)}
                onBlur={() => setHoveredPlane(null)}
              />
            ))}
          </ToolGroup>
        ) : null}

        {mode === "draw" ? (
          <>
            <ToolGroup aria-label="Sketch tools">
              {TOOLS.map(({ tool: t, keyHint, name, icon }) => (
                <ToolButton
                  key={t}
                  icon={icon}
                  label={name}
                  shortcut={keyHint}
                  active={tool === t}
                  data-testid={`tool-${t}`}
                  aria-label={name}
                  onClick={() => setTool(t)}
                />
              ))}
            </ToolGroup>

            <ToolGroup aria-label="Constrain">
              {CONSTRAINT_GROUPS.map((group) => (
                <Flyout
                  key={group.key}
                  label={group.triggerLabel}
                  icon={group.triggerIcon}
                  eyebrow={group.eyebrow}
                  data-testid={`constraint-group-${group.key}`}
                  items={group.items.map<FlyoutItem>((item) => ({
                    key: item.action,
                    icon: item.icon,
                    label: item.label,
                    shortcut: item.keyHint,
                    onSelect: () => applyConstraint(item.action),
                    "data-testid": `constraint-${item.action}`,
                    "aria-label": item.name,
                  }))}
                />
              ))}
              <ToolButton
                icon={<ConstructionIcon />}
                shortcut="N"
                label="Construction"
                active={selectionAllConstruction(selection, entities)}
                data-testid="sketch-construction"
                aria-label="Toggle construction geometry (N, on selected entities) — reference-only, excluded from the extrude profile"
                onClick={toggleConstruction}
              />
            </ToolGroup>

            <ToolGroup aria-label="Sketch">
              <ToolButton
                icon={<CheckIcon />}
                label={
                  saving ? "Saving…" : bound ? "Finish sketch" : "Save sketch"
                }
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
              <ToolButton
                icon={<CloseIcon />}
                label="Exit"
                caption={bound ? "Esc closes" : "Esc discards"}
                shortcut="Esc"
                data-testid="sketch-exit"
                aria-label={
                  bound
                    ? "Exit sketch (saved)"
                    : "Exit sketch (discards unsaved entities)"
                }
                disabled={saving}
                onClick={exit}
              />
            </ToolGroup>
          </>
        ) : null}
      </Panel>

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
