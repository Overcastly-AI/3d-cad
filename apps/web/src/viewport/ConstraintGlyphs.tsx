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
import {
  ExpressionField,
  NumberField,
  Panel,
  SegmentedControl,
  SketchGlyph,
  TextField,
} from "@loft/design";
import { sketch } from "@loft/design/tokens";
import { Html } from "@react-three/drei";
import {
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";

import {
  constraintGlyphs,
  dimensionEditorAnchor,
  formatDimensionMm,
  type ConstraintGlyph,
  type SolvedDimension,
} from "../sketch/constraints";
import {
  classifyDimensionValue,
  dimensionNameError,
} from "../sketch/dimensionExpr";
import { cornerPoint } from "../sketch/corner";
import { entityAnchor } from "../sketch/geometry";
import { planeToWorld, type PlaneBasis } from "../sketch/plane";
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
    case "radius": {
      const bare = glyph.label.replace(/[()R]/g, "");
      const noun = glyph.kind === "radius" ? "Radius" : "Distance";
      const ref = glyph.driven ? " reference" : "";
      const from = glyph.expression ? ` from ${glyph.expression}` : "";
      return `${noun}${ref} ${bare} mm${from} — edit`;
    }
    case "parallel":
      return "Parallel constraint";
    case "perpendicular":
      return "Perpendicular constraint";
    case "tangent":
      return "Tangent constraint";
    case "equal":
      return "Equal constraint";
    case "symmetric":
      return "Symmetric constraint";
    case "concentric":
      return "Concentric constraint";
  }
}

/**
 * The inline dimension spec a glyph opens into. Three cells in the title-block
 * idiom: the VALUE cell takes a literal (`20`) or an expression over other
 * dimension names (`width/2`), echoing the last resolved value in brass; a
 * NAME cell makes the dimension referenceable (identifier-hinted, server owns
 * uniqueness); and a DRIVING/DRIVEN toggle — driven marks it a measured
 * reference (`false` on the wire), excluded from the solver so it can't
 * over-constrain. Enter applies; Escape dismisses.
 */
function DimensionEditor({ basis }: { basis: PlaneBasis }) {
  const target = useSketchStore((state) => state.dimensionEdit);
  const entities = useSketchStore((state) => state.entities);
  const solvedDimensions = useSketchStore((state) => state.solvedDimensions);
  const commitDimension = useSketchStore((state) => state.commitDimension);
  const cancelDimension = useSketchStore((state) => state.cancelDimension);
  const removeConstraint = useSketchStore((state) => state.removeConstraint);
  const [value, setValue] = useState<string | null>(null);
  const [name, setName] = useState<string | null>(null);
  const [driving, setDriving] = useState<boolean | null>(null);

  const anchor = useMemo(
    () =>
      target === null
        ? null
        : dimensionEditorAnchor(target, entities, sketch.glyphOffsetMm),
    [target, entities],
  );

  // The last solved readout for this dimension — the resolved value an
  // expression currently evaluates to / the measured value of a driven one.
  const solved: SolvedDimension | undefined =
    target?.constraintIndex == null
      ? undefined
      : solvedDimensions.find(
          (d) => d.constraint_index === target.constraintIndex,
        );

  // Reset the local draft whenever the editor retargets a different constraint.
  const editKey =
    target === null
      ? null
      : `${target.constraintIndex ?? "new"}:${target.entity}`;
  useEffect(() => {
    setValue(null);
    setName(null);
    setDriving(null);
  }, [editKey]);

  if (target === null || anchor === null) return null;

  const noun = target.kind === "distance" ? "Distance" : "Radius";
  const isDriving = driving ?? target.initialDriving;
  const valueText =
    value ?? target.initialExpression ?? formatDimensionMm(target.initialMm);
  const nameText = name ?? target.initialName ?? "";

  const parsedValue = classifyDimensionValue(valueText);
  const nameError = dimensionNameError(nameText);
  // A driving literal must be > 0; a driving expression is the server's to
  // validate (accepted here). A driven dim is measured — its cell is read-only,
  // always valid, and commits the last measured/placeholder value.
  const valueError = !isDriving
    ? null
    : parsedValue.kind === "empty"
      ? "Enter a value or an expression."
      : parsedValue.kind === "literal" && !(parsedValue.valueMm > 0)
        ? "Enter a value above 0."
        : null;
  const valid = valueError === null && nameError === null;

  // The positive `value_mm` sent to the wire: the literal itself, or — while an
  // expression drives / a driven cell measures — a positive placeholder (the
  // last resolved value, else the measured prefill).
  const placeholderMm =
    solved?.value_mm && solved.value_mm > 0
      ? solved.value_mm
      : target.initialMm > 0
        ? target.initialMm
        : 1;

  const resolved =
    isDriving && parsedValue.kind === "expression" && solved !== undefined
      ? `= ${formatDimensionMm(solved.value_mm)} mm`
      : null;

  const trimmedName = nameText.trim();
  const close = (commit: boolean) => {
    if (commit && valid) {
      commitDimension({
        valueMm:
          isDriving && parsedValue.kind === "literal"
            ? parsedValue.valueMm
            : placeholderMm,
        expression:
          isDriving && parsedValue.kind === "expression"
            ? parsedValue.expression
            : null,
        name: trimmedName === "" ? null : trimmedName,
        driving: isDriving,
      });
    } else {
      cancelDimension();
    }
    setValue(null);
    setName(null);
    setDriving(null);
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
      position={planeToWorld(basis, anchor)}
      center
      zIndexRange={GLYPH_Z_RANGE}
    >
      <Panel className="w-52 space-y-2 p-2" data-testid="dimension-editor">
        <form onSubmit={onSubmit} className="space-y-2">
          {isDriving ? (
            <ExpressionField
              label={noun}
              unit="mm"
              value={valueText}
              error={valueError}
              resolved={resolved}
              onChange={(event) => setValue(event.target.value)}
              onKeyDown={onKeyDown}
              autoFocus
              onFocus={(event) => event.target.select()}
              data-testid="dimension-input"
              aria-label={`${noun} — value or expression`}
            />
          ) : (
            // Driven: measured from geometry, read-only. Show the live measured
            // value; committing keeps it as the placeholder `value_mm`.
            <NumberField
              label={`${noun} · reference`}
              unit="mm"
              value={formatDimensionMm(solved?.value_mm ?? target.initialMm)}
              readOnly
              data-testid="dimension-input"
              aria-label={`${noun} reference value (measured)`}
            />
          )}
          <TextField
            label="Name"
            value={nameText}
            error={nameError}
            placeholder="optional, e.g. width"
            onChange={(event) => setName(event.target.value)}
            onKeyDown={onKeyDown}
            data-testid="dimension-name"
            aria-label={`${noun} name (optional, for expressions)`}
          />
          <SegmentedControl
            label="Role"
            value={isDriving ? "driving" : "driven"}
            onChange={(next) => setDriving(next === "driving")}
            options={[
              {
                value: "driving",
                label: "Driving",
                "data-testid": "dimension-driving",
                "aria-label": "Driving — the value controls the geometry",
              },
              {
                value: "driven",
                label: "Driven",
                "data-testid": "dimension-driven",
                "aria-label":
                  "Driven — the value is measured from the geometry",
              },
            ]}
          />
          {/* Enter applies; the submit button exists for pointer users. */}
          <div className="flex items-center justify-between gap-2 pt-0.5">
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
                  close(false);
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

/** Default offset when the editor opens (mm) — a typical rib/wall thickness. */
const DEFAULT_OFFSET_MM = 2;

/**
 * The inline signed-distance field the Offset tool opens on the picked curve.
 * Signed by the left-hand-normal convention (documented in the caption): a
 * positive distance offsets to the LEFT of the directed curve — for a CCW
 * arc/circle the left normal points inward, so +shrinks the radius. Enter
 * applies; "Flip side" negates; Escape dismisses. Mirrors the dimension
 * editor's in-canvas idiom so the two read as one annotation language.
 */
function OffsetEditor({ basis }: { basis: PlaneBasis }) {
  const draft = useSketchStore((state) => state.offsetDraft);
  const entities = useSketchStore((state) => state.entities);
  const armOffset = useSketchStore((state) => state.armOffset);
  const cancelOffset = useSketchStore((state) => state.cancelOffset);
  const [text, setText] = useState<string | null>(null);

  const target =
    draft === null
      ? null
      : (entities.find((e) => e.id === draft.target) ?? null);
  const anchor = useMemo(
    () => (target === null ? null : entityAnchor(target)),
    [target],
  );

  // Reset the field to its default whenever the editor closes or retargets, so
  // a fresh pick never inherits the previous curve's typed value.
  useEffect(() => {
    setText(null);
  }, [draft?.target]);

  if (draft === null || target === null || anchor === null) return null;

  const value = text ?? String(DEFAULT_OFFSET_MM);
  const parsed = Number.parseFloat(value);
  const valid = Number.isFinite(parsed) && parsed !== 0;

  const apply = () => {
    if (valid) {
      armOffset(parsed);
      setText(null);
    }
  };
  const flip = () => {
    if (Number.isFinite(parsed)) setText(formatDimensionMm(-parsed));
  };
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    apply();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      cancelOffset();
      setText(null);
    }
  };

  return (
    <Html
      position={planeToWorld(basis, anchor)}
      center
      zIndexRange={GLYPH_Z_RANGE}
    >
      <Panel className="w-48 p-2" data-testid="offset-editor">
        <form onSubmit={onSubmit}>
          <NumberField
            label="Offset"
            unit="mm"
            value={value}
            error={valid ? null : "Enter a nonzero distance."}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={onKeyDown}
            autoFocus
            onFocus={(event) => event.target.select()}
            data-testid="offset-input"
            aria-label="Offset distance (mm, signed)"
          />
          {/* Sign convention, spelled out so the direction is never a guess. */}
          <p className="mt-1 font-body text-2xs text-gauge">
            + left of the curve · − right. One curve at a time.
          </p>
          <div className="mt-2 flex items-center justify-between gap-2">
            <button
              type="submit"
              className="font-display text-2xs uppercase tracking-[0.14em] text-brass hover:text-brass-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass disabled:opacity-50"
              disabled={!valid}
              data-testid="offset-apply"
            >
              Add offset
            </button>
            <button
              type="button"
              className="font-display text-2xs uppercase tracking-[0.14em] text-gauge hover:text-mist focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass disabled:opacity-50"
              disabled={!Number.isFinite(parsed)}
              data-testid="offset-flip"
              onClick={flip}
            >
              Flip side
            </button>
          </div>
        </form>
      </Panel>
    </Html>
  );
}

/** Default corner size when the editor opens (mm) — a typical break radius. */
const DEFAULT_CORNER_MM = 2;

/**
 * The inline value field the Fillet/Chamfer tools open once both line legs are
 * picked. Fillet collects a radius, chamfer an equal setback (mm). Anchored at
 * the shared corner, it mirrors the dimension/offset in-canvas idiom so the
 * three read as one annotation language. Enter applies; Escape dismisses (the
 * store's Escape cascade clears the picks). v1 is line-line corners only.
 */
function CornerEditor({ basis }: { basis: PlaneBasis }) {
  const corner = useSketchStore((state) => state.corner);
  const entities = useSketchStore((state) => state.entities);
  const armCorner = useSketchStore((state) => state.armCorner);
  const cancelCorner = useSketchStore((state) => state.cancelCorner);
  const [text, setText] = useState<string | null>(null);

  const open = corner !== null && corner.picks.length === 2;
  const legA = open
    ? entities.find((e) => e.id === corner.picks[0])
    : undefined;
  const legB = open
    ? entities.find((e) => e.id === corner.picks[1])
    : undefined;
  const anchor = useMemo(
    () =>
      legA?.kind === "line" && legB?.kind === "line"
        ? cornerPoint(legA, legB)
        : null,
    [legA, legB],
  );

  // Reset to the default whenever the picks change, so a fresh corner never
  // inherits the previous one's typed value.
  const picksKey = corner?.picks.join(",");
  useEffect(() => {
    setText(null);
  }, [picksKey]);

  if (!open || corner === null || anchor === null) return null;

  const isFillet = corner.op === "fillet";
  const value = text ?? String(DEFAULT_CORNER_MM);
  const parsed = Number.parseFloat(value);
  const valid = Number.isFinite(parsed) && parsed > 0;
  const label = isFillet ? "Radius" : "Distance";

  const apply = () => {
    if (valid) {
      armCorner(parsed);
      setText(null);
    }
  };
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    apply();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      cancelCorner();
      setText(null);
    }
  };

  return (
    <Html
      position={planeToWorld(basis, anchor)}
      center
      zIndexRange={GLYPH_Z_RANGE}
    >
      <Panel className="w-48 p-2" data-testid="corner-editor">
        <form onSubmit={onSubmit}>
          <NumberField
            label={isFillet ? "Fillet radius" : "Chamfer distance"}
            unit="mm"
            value={value}
            error={valid ? null : "Enter a value above 0."}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={onKeyDown}
            autoFocus
            onFocus={(event) => event.target.select()}
            data-testid="corner-input"
            aria-label={`${label} (mm)`}
          />
          <p className="mt-1 font-body text-2xs text-gauge">
            {isFillet
              ? "Rounds the corner where the two lines meet."
              : "Bevels the corner where the two lines meet."}{" "}
            Two lines only.
          </p>
          <div className="mt-2 flex items-center justify-between gap-2">
            <button
              type="submit"
              className="font-display text-2xs uppercase tracking-[0.14em] text-brass hover:text-brass-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass disabled:opacity-50"
              disabled={!valid}
              data-testid="corner-apply"
            >
              {isFillet ? "Round corner" : "Bevel corner"}
            </button>
          </div>
        </form>
      </Panel>
    </Html>
  );
}

export function ConstraintGlyphs({ basis }: { basis: PlaneBasis }) {
  const constraints = useSketchStore((state) => state.constraints);
  const entities = useSketchStore((state) => state.entities);
  const selectedConstraint = useSketchStore(
    (state) => state.selectedConstraint,
  );
  const selectConstraint = useSketchStore((state) => state.selectConstraint);
  const editDimension = useSketchStore((state) => state.editDimension);
  const solve = useSketchStore((state) => state.solve);
  const solvedDimensions = useSketchStore((state) => state.solvedDimensions);
  const editing = useSketchStore(
    (state) => state.dimensionEdit?.constraintIndex ?? null,
  );

  const glyphs = useMemo(() => {
    const byIndex = new Map(
      solvedDimensions.map((d) => [d.constraint_index, d]),
    );
    return constraintGlyphs(
      constraints,
      entities,
      sketch.glyphOffsetMm,
      byIndex,
    );
  }, [constraints, entities, solvedDimensions]);
  const flagged = useMemo(
    () => new Set([...(solve?.conflicting ?? []), ...(solve?.redundant ?? [])]),
    [solve],
  );

  return (
    <group>
      {glyphs.map((glyph) => {
        if (glyph.index === editing) return null; // the editor replaces it
        // Driving dims are brass (the parametric handles); DRIVEN (reference)
        // dims are quiet gauge — measured, informational — matching their
        // parenthesised label. Flagged constraints always win.
        const tone = flagged.has(glyph.index)
          ? "flag"
          : glyph.editable && !glyph.driven
            ? "accent"
            : "quiet";
        return (
          <Html
            key={glyph.index}
            position={planeToWorld(basis, glyph.anchor)}
            center
            zIndexRange={GLYPH_Z_RANGE}
          >
            <SketchGlyph
              tone={tone}
              selected={selectedConstraint === glyph.index}
              data-testid={`glyph-${glyph.index}`}
              data-kind={glyph.kind}
              data-driven={glyph.driven || undefined}
              data-expression={glyph.expression ?? undefined}
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
      <DimensionEditor basis={basis} />
      <OffsetEditor basis={basis} />
      <CornerEditor basis={basis} />
    </group>
  );
}
