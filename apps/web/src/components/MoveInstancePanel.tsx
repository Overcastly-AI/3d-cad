/**
 * The Move panel — the typed half of Fusion 360's Move command, beside the
 * triad in the viewport. Six cells in the kernel frame: X, Y, Z in the
 * document unit and Rx, Ry, Rz in degrees (fixed-axis X→Y→Z, `movePose`).
 *
 * The cells FOLLOW the triad (a drag re-seeds them) and DRIVE the preview (a
 * parseable edit moves the part live). Enter or OK commits the typed pose as
 * ONE `PATCH`; Esc or Cancel drops it and the part returns. Keyboard-first:
 * the first cell takes focus, so `M`, a number and Enter is a whole move.
 */
import { NumberField, Panel, PanelActionCell } from "@loft/design";
import { type KeyboardEvent, useState } from "react";

import {
  fieldsFromPlacement,
  invalidFields,
  type MoveField,
  type MoveFields,
  placementFromFields,
  ROTATION_FIELDS,
} from "../assembly/movePose";
import type { Placement } from "../assembly/placement";
import { useDocumentLengthUnit } from "../units/documentUnit";
import { EditorCard } from "./EditorCard";

export interface MoveInstancePanelProps {
  instanceName: string;
  /** The session's re-seed counter (`useMoveSession`). */
  seed: number;
  /** The pose drawn now — what the cells seed from. */
  placement: Placement;
  /** The instance has mates: the solver, not the drop, has the last word. */
  mated: boolean;
  committing: boolean;
  onPreview: (placement: Placement) => void;
  onCommit: () => void;
  onCancel: () => void;
}

const CELLS: { key: MoveField; label: string }[] = [
  { key: "x", label: "X" },
  { key: "y", label: "Y" },
  { key: "z", label: "Z" },
  { key: "rx", label: "Rx" },
  { key: "ry", label: "Ry" },
  { key: "rz", label: "Rz" },
];

interface Seeded {
  seed: number;
  fields: MoveFields;
  base: Placement;
  rotationEdited: boolean;
}

export function MoveInstancePanel({
  instanceName,
  seed,
  placement,
  mated,
  committing,
  onPreview,
  onCommit,
  onCancel,
}: MoveInstancePanelProps) {
  const unit = useDocumentLengthUnit();
  const [seeded, setSeeded] = useState<Seeded>(() => ({
    seed,
    fields: fieldsFromPlacement(placement, unit),
    base: placement,
    rotationEdited: false,
  }));
  // Re-seed from the drawn pose when it moved from OUTSIDE the panel (a drag,
  // a landed solve) — derived during render, so the cells never show a frame
  // of the old pose.
  if (seeded.seed !== seed) {
    setSeeded({
      seed,
      fields: fieldsFromPlacement(placement, unit),
      base: placement,
      rotationEdited: false,
    });
  }

  const invalid = invalidFields(seeded.fields, unit);

  const edit = (key: MoveField, value: string) => {
    const fields = { ...seeded.fields, [key]: value };
    const rotationEdited =
      seeded.rotationEdited ||
      (ROTATION_FIELDS as readonly MoveField[]).includes(key);
    setSeeded({ ...seeded, fields, rotationEdited });
    const next = placementFromFields(fields, unit, seeded.base, rotationEdited);
    if (next !== null) onPreview(next);
  };

  const canCommit = invalid.size === 0 && !committing;
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Enter") {
      event.preventDefault();
      if (canCommit) onCommit();
    } else if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      onCancel();
    }
  };

  return (
    <EditorCard
      onKeyDown={onKeyDown}
      footer={
        <div className="grid grid-cols-2 divide-x divide-hairline border border-t-0 border-hairline bg-anvil">
          <PanelActionCell
            label="Cancel"
            caption="Esc"
            data-testid="move-cancel"
            disabled={committing}
            onClick={onCancel}
          />
          <PanelActionCell
            label={committing ? "Moving…" : "OK"}
            caption="Enter"
            data-testid="move-ok"
            aria-busy={committing}
            disabled={!canCommit}
            disabledReason={
              invalid.size > 0 ? "Enter a number in every cell" : undefined
            }
            onClick={onCommit}
          />
        </div>
      }
    >
      <Panel aria-label="Move" data-testid="move-panel">
        <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
          Move
          <span className="ml-2 normal-case tracking-normal text-mist">
            {instanceName}
          </span>
        </h2>
        <div className="grid grid-cols-3 gap-2 px-3 pb-2 pt-1">
          {CELLS.map(({ key, label }, index) => (
            <NumberField
              key={key}
              label={label}
              unit={index < 3 ? unit : "°"}
              data-testid={`move-${key}`}
              autoFocus={index === 0}
              value={seeded.fields[key]}
              error={invalid.has(key) ? "Not a number" : null}
              onChange={(event) => edit(key, event.target.value)}
              onFocus={(event) => event.currentTarget.select()}
            />
          ))}
        </div>
        <p className="px-3 pb-3 font-body text-xs text-gauge">
          {mated
            ? "Mated: after the move, the part settles where its mates hold it."
            : "Drag the triad or type a position. Angles turn about the world X, then Y, then Z."}
        </p>
      </Panel>
    </EditorCard>
  );
}
