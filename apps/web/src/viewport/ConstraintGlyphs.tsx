/**
 * Constraint annotations inside the viewport — engineering-drawing notation
 * projected at the geometry it governs. Geometric constraints (H/V/C/FIX)
 * are quiet gauge ink and select on click (Delete removes); driving
 * dimensions (40, R12.5) are brass — click one and it opens in place as a
 * unit-aware mm field, Enter re-solves the sketch. Conflicting/redundant
 * constraints flip to flag ink (the DRO + diagnostic stamp explain why).
 *
 * DOM-in-canvas via drei `Html`: real buttons and a real input — keyboard
 * focusable, screen-reader named, e2e drivable — with zero chrome, so it
 * reads as annotation, not UI.
 */
import { NumberField, Panel, SketchGlyph } from "@loft/design";
import { sketch } from "@loft/design/tokens";
import { Html } from "@react-three/drei";
import { useMemo, useState, type FormEvent, type KeyboardEvent } from "react";

import {
  constraintGlyphs,
  dimensionEditorAnchor,
  formatDimensionMm,
  type ConstraintGlyph,
} from "../sketch/constraints";
import { planeToWorld, type DatumPlaneName } from "../sketch/plane";
import { useSketchStore } from "../sketch/store";

/** Keep annotation overlays under the HUD strips (Viewport hud sits at z-40). */
const GLYPH_Z_RANGE: [number, number] = [20, 0];

function glyphAria(glyph: ConstraintGlyph): string {
  switch (glyph.kind) {
    case "horizontal":
      return "Horizontal constraint";
    case "vertical":
      return "Vertical constraint";
    case "coincident":
      return "Coincident constraint";
    case "fixed":
      return "Fixed point constraint";
    case "distance":
      return `Distance ${glyph.label} mm — edit`;
    case "radius":
      return `Radius ${glyph.label.slice(1)} mm — edit`;
    case "parallel":
      return "Parallel constraint";
    case "perpendicular":
      return "Perpendicular constraint";
    case "tangent":
      return "Tangent constraint";
    // 4a→4b: equal/symmetric/concentric solve in 4a but have no glyphs yet;
    // a generic label keeps this exhaustive switch green until 4b renders them.
    default:
      return "Constraint";
  }
}

/** The inline mm field a dimension glyph opens into. */
function DimensionEditor({ plane }: { plane: DatumPlaneName }) {
  const target = useSketchStore((state) => state.dimensionEdit);
  const entities = useSketchStore((state) => state.entities);
  const commitDimension = useSketchStore((state) => state.commitDimension);
  const cancelDimension = useSketchStore((state) => state.cancelDimension);
  const removeConstraint = useSketchStore((state) => state.removeConstraint);
  const [text, setText] = useState<string | null>(null);

  const anchor = useMemo(
    () =>
      target === null
        ? null
        : dimensionEditorAnchor(target, entities, sketch.glyphOffsetMm),
    [target, entities],
  );
  if (target === null || anchor === null) return null;

  const value = text ?? formatDimensionMm(target.initialMm);
  const parsed = Number.parseFloat(value);
  const valid = Number.isFinite(parsed) && parsed > 0;

  const close = (commit: boolean) => {
    if (commit && valid) commitDimension(parsed);
    else cancelDimension();
    setText(null);
  };
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    close(true);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      close(false);
    }
  };

  return (
    <Html
      position={planeToWorld(plane, anchor)}
      center
      zIndexRange={GLYPH_Z_RANGE}
    >
      <Panel className="w-40 p-2" data-testid="dimension-editor">
        <form onSubmit={onSubmit}>
          <NumberField
            label={target.kind === "distance" ? "Distance" : "Radius"}
            unit="mm"
            value={value}
            error={valid ? null : "Enter a value above 0."}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={onKeyDown}
            autoFocus
            onFocus={(event) => event.target.select()}
            data-testid="dimension-input"
            aria-label={`${target.kind === "distance" ? "Distance" : "Radius"} (mm)`}
          />
          {/* Enter applies; the submit button exists for pointer users. */}
          <div className="mt-2 flex items-center justify-between gap-2">
            <button
              type="submit"
              className="font-display text-2xs uppercase tracking-[0.14em] text-brass hover:text-brass-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass disabled:opacity-50"
              disabled={!valid}
              data-testid="dimension-apply"
            >
              Apply
            </button>
            {target.constraintIndex !== null ? (
              <button
                type="button"
                className="font-display text-2xs uppercase tracking-[0.14em] text-gauge hover:text-flag focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
                data-testid="dimension-remove"
                onClick={() => {
                  if (target.constraintIndex !== null) {
                    removeConstraint(target.constraintIndex);
                  }
                  setText(null);
                }}
              >
                Remove
              </button>
            ) : null}
          </div>
        </form>
      </Panel>
    </Html>
  );
}

export function ConstraintGlyphs({ plane }: { plane: DatumPlaneName }) {
  const constraints = useSketchStore((state) => state.constraints);
  const entities = useSketchStore((state) => state.entities);
  const selectedConstraint = useSketchStore(
    (state) => state.selectedConstraint,
  );
  const selectConstraint = useSketchStore((state) => state.selectConstraint);
  const editDimension = useSketchStore((state) => state.editDimension);
  const solve = useSketchStore((state) => state.solve);
  const editing = useSketchStore(
    (state) => state.dimensionEdit?.constraintIndex ?? null,
  );

  const glyphs = useMemo(
    () => constraintGlyphs(constraints, entities, sketch.glyphOffsetMm),
    [constraints, entities],
  );
  const flagged = useMemo(
    () => new Set([...(solve?.conflicting ?? []), ...(solve?.redundant ?? [])]),
    [solve],
  );

  return (
    <group>
      {glyphs.map((glyph) => {
        if (glyph.index === editing) return null; // the editor replaces it
        const tone = flagged.has(glyph.index)
          ? "flag"
          : glyph.editable
            ? "accent"
            : "quiet";
        return (
          <Html
            key={glyph.index}
            position={planeToWorld(plane, glyph.anchor)}
            center
            zIndexRange={GLYPH_Z_RANGE}
          >
            <SketchGlyph
              tone={tone}
              selected={selectedConstraint === glyph.index}
              data-testid={`glyph-${glyph.index}`}
              data-kind={glyph.kind}
              data-flagged={flagged.has(glyph.index) || undefined}
              aria-label={glyphAria(glyph)}
              onClick={() =>
                glyph.editable
                  ? editDimension(glyph.index)
                  : selectConstraint(
                      selectedConstraint === glyph.index ? null : glyph.index,
                    )
              }
            >
              {glyph.label}
            </SketchGlyph>
          </Html>
        );
      })}
      <DimensionEditor plane={plane} />
    </group>
  );
}
