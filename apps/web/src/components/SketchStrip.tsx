/**
 * The sketch toolbar — two title-block rows across the top of the viewport,
 * now icon-forward. Plane-pick step: the three datum planes (keyboard path,
 * hover-synced with the 3D sheets). Draw step: the four sketch tools as
 * scribed icon buttons, then SAVE and EXIT — plus a second ruled row, the
 * CONSTRAIN strip: the twelve constraint verbs grouped by kind (Geometric /
 * Dimensional / Relational) behind labeled flyouts, then the Construction
 * toggle and the live selection readout.
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

/** One ruled identity cell — the row's title-block header + live value. */
function IdentityCell({
  eyebrow,
  children,
}: {
  eyebrow: string;
  children: ReactNode;
}) {
  return (
    <div className="flex shrink-0 flex-col justify-center px-3 py-2">
      <span className="block font-display text-2xs uppercase tracking-[0.18em] text-gauge">
        {eyebrow}
      </span>
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
      <Panel
        aria-label="Sketch"
        data-testid="sketch-strip"
        className="flex items-stretch divide-x divide-hairline"
      >
        <IdentityCell eyebrow="Sketch">
          <span
            className="block font-data text-xs text-mist"
            data-testid="sketch-step"
          >
            {mode === "plane" ? "Pick a plane" : `On ${plane ?? "—"}`}
          </span>
        </IdentityCell>

        {mode === "plane" ? (
          <ToolGroup eyebrow="Datum plane">
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
            <ToolGroup>
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
            <ToolGroup>
              <ToolButton
                icon={<CheckIcon />}
                showLabel
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
              <ToolButton
                icon={<CloseIcon />}
                showLabel
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

      {mode === "draw" ? (
        <Panel
          aria-label="Constraints"
          data-testid="constraint-strip"
          className="mt-2 flex items-stretch divide-x divide-hairline"
        >
          <IdentityCell eyebrow="Constrain">
            <span
              className="block font-data text-xs text-mist"
              data-testid="selection-readout"
            >
              {describeSelection(selection)}
              {constraintCount > 0 ? ` · ${constraintCount} applied` : ""}
            </span>
          </IdentityCell>

          <ToolGroup>
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
          </ToolGroup>

          <ToolGroup>
            <ToolButton
              icon={<ConstructionIcon />}
              showLabel
              label="Construction"
              shortcut="N"
              active={selectionAllConstruction(selection, entities)}
              data-testid="sketch-construction"
              aria-label="Toggle construction geometry (N, on selected entities) — reference-only, excluded from the extrude profile"
              onClick={toggleConstruction}
            />
          </ToolGroup>
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
