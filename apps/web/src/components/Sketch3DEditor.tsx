/**
 * The 3D sketch editor (SKETCH-3D) — SolidWorks' 3D Sketch, Fusion's 3D
 * sketch: points and lines in model space, in the title-block seat every
 * feature editor uses.
 *
 * ENTRY is the 2D Line tool's draw box with a third cell: X Tab Y Tab Z
 * Enter places a point and joins it to the previous one, so a skeleton is
 * typed as one chain; Escape (or End chain) starts a new chain. Clicking a
 * snap mark in the viewport (the origin, a sketch point, a model vertex)
 * places an ATTACHED point there; clicking one of this sketch's own points
 * continues the chain from it.
 *
 * RELATIONS act on the selection (click a point or line row): one line takes
 * Along X / Y / Z or a Length, two points a Distance or Coincident, one point
 * Fix. The geometry service solves them; an edited sketch shows its solved
 * positions and remaining degrees of freedom.
 */
import { Button, NumberField, Panel, PanelActionCell } from "@loft/design";
import { formatLength, lengthUnitLabel } from "@loft/design";
import {
  type KeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import type { Sketch3DParams, SolvedSketch3DData } from "../api/parts";
import { useCommandBridge } from "../features/commandActions";
import {
  addAlong,
  addCoincident,
  addDimension,
  addFixed,
  availableRelations,
  buildSketch3DParams,
  constraintLabel,
  endChain,
  parseCoordinate,
  placePoint,
  removeConstraint,
  removeEntity,
  type Sketch3DForm,
  sketch3DSubmitBlocker,
  snapLabel,
  toggleConstruction,
  toggleSelected,
} from "../features/sketch3d";
import { useSketch3DStore } from "../features/sketch3dStore";
import { parsePositiveLengthMm } from "../units/length";
import { useDocumentLengthUnit } from "../units/documentUnit";
import { EditorCard } from "./EditorCard";

export interface Sketch3DEditorProps {
  mode: "create" | "edit";
  featureId?: string;
  initial: Sketch3DForm;
  /** The last rebuild's solve of the sketch being edited, or null. */
  solved: SolvedSketch3DData | null;
  onSubmit: (params: Sketch3DParams) => void;
  onCancel: () => void;
  saving: boolean;
  error: string | null;
  rebuildError?: string | null;
}

const AXES = ["x", "y", "z"] as const;

export function Sketch3DEditor({
  mode,
  featureId,
  initial,
  solved,
  onSubmit,
  onCancel,
  saving,
  error,
  rebuildError = null,
}: Sketch3DEditorProps) {
  const unit = useDocumentLengthUnit();
  const open = useSketch3DStore((s) => s.open);
  const close = useSketch3DStore((s) => s.close);
  const update = useSketch3DStore((s) => s.update);
  const form = useSketch3DStore((s) => s.form) ?? initial;
  const [cells, setCells] = useState<[string, string, string]>(["", "", ""]);
  const [dimension, setDimension] = useState("");
  const xRef = useRef<HTMLInputElement>(null);

  // The store holds the form while the editor is open (the viewport layer
  // reads and writes it too); a new `initial` re-opens it.
  useEffect(() => {
    open(initial, featureId ?? null);
    return () => close();
  }, [initial, featureId, open, close]);

  const solvedAt = new Map(
    (solved?.points ?? []).map((p) => [p.id, p.position] as const),
  );
  const coordinate = parseCoordinate(cells, unit);
  const place = useCallback(() => {
    if (coordinate === null) return;
    update((f) => placePoint(f, coordinate));
    xRef.current?.focus();
    xRef.current?.select();
  }, [coordinate, update]);

  const submit = useCallback(() => {
    if (sketch3DSubmitBlocker(form) !== null) return;
    onSubmit(buildSketch3DParams(form));
  }, [form, onSubmit]);

  const blocker = saving ? null : sketch3DSubmitBlocker(form);
  const canSubmit = blocker === null && !saving;
  useCommandBridge(submit, canSubmit);

  const onEntryKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      event.stopPropagation();
      place();
    } else if (event.key === "Escape" && form.chainFrom !== null) {
      event.preventDefault();
      event.stopPropagation();
      update(endChain);
    }
  };
  const onCardKey = (event: KeyboardEvent) => {
    if (event.key === "Enter" && !saving) {
      event.preventDefault();
      submit();
    }
  };

  const relations = availableRelations(form);
  const dimensionMm = parsePositiveLengthMm(dimension, unit);
  const canDimension =
    dimensionMm !== null &&
    (relations.line !== null || relations.points !== null);
  const untouched = JSON.stringify(form) === JSON.stringify(initial);
  const shownError = error ?? (untouched ? rebuildError : null);

  const row = (on: boolean) =>
    `flex-1 px-2 py-0.5 text-left font-body text-xs ${
      on ? "bg-carbide text-brass" : "text-mist hover:text-brass"
    }`;

  return (
    <EditorCard
      onKeyDown={onCardKey}
      footer={
        <>
          {shownError ? (
            <p
              role="alert"
              data-testid="sketch3d-error"
              className="border border-b-0 border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
            >
              {shownError}
            </p>
          ) : null}
          <div className="grid grid-cols-2 divide-x divide-hairline border border-t-0 border-hairline bg-anvil">
            <PanelActionCell
              label="Cancel"
              caption="Esc"
              data-testid="sketch3d-cancel"
              disabled={saving}
              onClick={onCancel}
            />
            <PanelActionCell
              label={saving ? "Saving…" : mode === "create" ? "Create" : "Save"}
              caption="Enter"
              data-testid="sketch3d-submit"
              aria-busy={saving}
              disabled={!canSubmit}
              disabledReason={blocker ?? undefined}
              onClick={submit}
            />
          </div>
        </>
      }
    >
      <Panel aria-label="3D sketch" data-testid="sketch3d-editor">
        <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
          {mode === "create" ? "New 3D sketch" : "Edit 3D sketch"}
        </h2>
        <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
          <div className="grid grid-cols-3 gap-2" data-testid="sketch3d-entry">
            {AXES.map((axis, index) => (
              <NumberField
                key={axis}
                ref={index === 0 ? xRef : undefined}
                label={axis.toUpperCase()}
                unit={lengthUnitLabel(unit)}
                value={cells[index]}
                data-testid={`sketch3d-${axis}`}
                aria-label={`Point ${axis.toUpperCase()}`}
                onKeyDown={onEntryKey}
                onFocus={(e) => e.currentTarget.select()}
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  setCells((prev) => {
                    const next: [string, string, string] = [...prev];
                    next[index] = value;
                    return next;
                  });
                }}
              />
            ))}
          </div>
          <div className="flex items-center justify-between gap-2">
            <span
              className="font-body text-xs text-gauge"
              data-testid="sketch3d-chain"
            >
              {form.chainFrom === null
                ? "Enter places a point; a snap mark attaches one."
                : `Next point joins ${form.chainFrom}.`}
            </span>
            <Button
              data-testid="sketch3d-place"
              disabled={coordinate === null}
              onClick={place}
            >
              Place
            </Button>
            <Button
              data-testid="sketch3d-end-chain"
              disabled={form.chainFrom === null}
              onClick={() => update(endChain)}
            >
              End chain
            </Button>
          </div>

          <span className="font-display text-2xs uppercase tracking-[0.14em] text-gauge">
            Points
          </span>
          <div
            className="flex max-h-[10rem] flex-col overflow-y-auto border border-hairline p-1"
            data-testid="sketch3d-points"
          >
            {form.points.length === 0 ? (
              <p className="font-body text-xs text-gauge">No points yet.</p>
            ) : null}
            {form.points.map((p) => {
              const at = solvedAt.get(p.id) ?? p.position;
              const label = snapLabel(p.snap);
              return (
                <div key={p.id} className="flex items-center">
                  <button
                    type="button"
                    aria-pressed={form.selected.includes(p.id)}
                    data-testid={`sketch3d-point-${p.id}`}
                    className={row(form.selected.includes(p.id))}
                    onClick={() => update((f) => toggleSelected(f, p.id))}
                  >
                    {p.id} (
                    {AXES.map((a) =>
                      formatLength(at[a], unit, { unitSuffix: false }),
                    ).join(", ")}
                    ){label ? ` · ${label}` : ""}
                  </button>
                  <button
                    type="button"
                    aria-label={`Delete point ${p.id}`}
                    data-testid={`sketch3d-delete-${p.id}`}
                    className="px-1 font-body text-xs text-gauge hover:text-flag"
                    onClick={() => update((f) => removeEntity(f, p.id))}
                  >
                    ×
                  </button>
                </div>
              );
            })}
          </div>

          <span className="font-display text-2xs uppercase tracking-[0.14em] text-gauge">
            Lines
          </span>
          <div
            className="flex max-h-[10rem] flex-col overflow-y-auto border border-hairline p-1"
            data-testid="sketch3d-lines"
          >
            {form.lines.length === 0 ? (
              <p className="font-body text-xs text-gauge">No lines yet.</p>
            ) : null}
            {form.lines.map((l) => (
              <div key={l.id} className="flex items-center">
                <button
                  type="button"
                  aria-pressed={form.selected.includes(l.id)}
                  data-testid={`sketch3d-line-${l.id}`}
                  className={row(form.selected.includes(l.id))}
                  onClick={() => update((f) => toggleSelected(f, l.id))}
                >
                  {l.id}: {l.start} → {l.end}
                  {l.construction ? " (construction)" : ""}
                </button>
                <button
                  type="button"
                  aria-label={`Construction ${l.id}`}
                  data-testid={`sketch3d-construction-${l.id}`}
                  className="px-1 font-body text-2xs text-gauge hover:text-brass"
                  onClick={() => update((f) => toggleConstruction(f, l.id))}
                >
                  C
                </button>
                <button
                  type="button"
                  aria-label={`Delete line ${l.id}`}
                  data-testid={`sketch3d-delete-${l.id}`}
                  className="px-1 font-body text-xs text-gauge hover:text-flag"
                  onClick={() => update((f) => removeEntity(f, l.id))}
                >
                  ×
                </button>
              </div>
            ))}
          </div>

          <span className="font-display text-2xs uppercase tracking-[0.14em] text-gauge">
            Relations
          </span>
          <div
            className="flex flex-wrap gap-1"
            data-testid="sketch3d-relations"
          >
            {AXES.map((axis) => (
              <Button
                key={axis}
                data-testid={`sketch3d-along-${axis}`}
                disabled={relations.line === null}
                onClick={() => update((f) => addAlong(f, axis))}
              >
                Along {axis.toUpperCase()}
              </Button>
            ))}
            <Button
              data-testid="sketch3d-coincident"
              disabled={relations.points === null}
              onClick={() => update(addCoincident)}
            >
              Coincident
            </Button>
            <Button
              data-testid="sketch3d-fix"
              disabled={relations.point === null}
              onClick={() => update(addFixed)}
            >
              Fix
            </Button>
          </div>
          <div className="flex items-end gap-2">
            <NumberField
              label={relations.points !== null ? "Distance" : "Length"}
              unit={lengthUnitLabel(unit)}
              value={dimension}
              data-testid="sketch3d-dimension"
              aria-label="Dimension value"
              onChange={(e) => setDimension(e.currentTarget.value)}
              onKeyDown={(e) => {
                if (e.key !== "Enter") return;
                e.preventDefault();
                e.stopPropagation();
                if (canDimension && dimensionMm !== null) {
                  update((f) => addDimension(f, dimensionMm));
                }
              }}
            />
            <Button
              data-testid="sketch3d-add-dimension"
              disabled={!canDimension}
              onClick={() => {
                if (dimensionMm !== null)
                  update((f) => addDimension(f, dimensionMm));
              }}
            >
              Dimension
            </Button>
          </div>
          <div className="flex flex-col" data-testid="sketch3d-constraints">
            {form.constraints.map((c, index) => (
              <div key={index} className="flex items-center">
                <span
                  className="flex-1 px-2 font-body text-xs text-mist"
                  data-testid={`sketch3d-constraint-${index}`}
                >
                  {constraintLabel(c, unit)}
                </span>
                <button
                  type="button"
                  aria-label={`Delete relation ${index + 1}`}
                  className="px-1 font-body text-xs text-gauge hover:text-flag"
                  onClick={() => update((f) => removeConstraint(f, index))}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
          {solved !== null && untouched ? (
            <p
              className="font-body text-xs text-gauge"
              data-testid="sketch3d-dof"
            >
              {solved.dof === 0
                ? "Fully defined."
                : `${solved.dof} degrees of freedom left.`}
            </p>
          ) : null}
        </div>
      </Panel>
    </EditorCard>
  );
}
