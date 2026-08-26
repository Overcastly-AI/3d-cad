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
 *
 * NB for anyone applying the sketcher's depth policy (see the note at the top
 * of `SketchScene.tsx`): nothing in this file needs it. `Html` renders into a
 * DOM layer ABOVE the canvas and drei's optional `occlude` mode is not used
 * here, so every glyph, editor and handle already floats over the solid on any
 * plane. The z-fight that made a sketch on a face vanish could never reach
 * them — which is also why the constraint annotations stayed visible in the
 * founder's report while the ink they annotate did not.
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
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
  type RefObject,
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
  type DimensionValue,
} from "../sketch/dimensionExpr";
import { cornerPoint } from "../sketch/corner";
import { entityAnchor } from "../sketch/geometry";
import { planeToWorld, type PlaneBasis } from "../sketch/plane";
import { useSketchStore } from "../sketch/store";

/** Keep annotation overlays under the HUD strips (Viewport hud sits at z-40). */
const GLYPH_Z_RANGE: [number, number] = [20, 0];

/**
 * Local editor state that belongs to ONE target and dies with it: `null` means
 * "nothing typed yet — use the target's own value". The reset happens DURING
 * render (React's documented "adjust state when a prop changes" pattern), not
 * in an effect, because the cells below read it to build `defaultValue`: a
 * reset that landed one commit later would re-mount a cell still holding the
 * PREVIOUS dimension's text, which is a wrong-number bug rather than a slow one.
 */
function useRetargetedDraft<T>(
  resetKey: string | null,
): [T | null, (next: T | null) => void] {
  const [draft, setDraft] = useState<{ key: string | null; value: T | null }>({
    key: resetKey,
    value: null,
  });
  const current =
    draft.key === resetKey ? draft : { key: resetKey, value: null };
  if (current !== draft) setDraft(current);
  return [current.value, (value) => setDraft({ key: resetKey, value })];
}

/** A cell whose text the BROWSER owns — see {@link useTypedField}. */
interface TypedField {
  /** Attach to the design-system cell (the primitive forwards it to its input). */
  ref: RefObject<HTMLInputElement | null>;
  /** What React last SAW. Drives the live error/echo — never the cell's text. */
  text: string;
  /** Mount-time text. Only a retarget (or a programmatic write) moves it. */
  defaultValue: string;
  /** What the cell ACTUALLY holds right now — the only value a commit may use. */
  read: () => string;
  /** Write the cell from code (e.g. "Flip side") — DOM and shadow together. */
  write: (next: string) => void;
  onChange: (event: ChangeEvent<HTMLInputElement>) => void;
}

/**
 * THE IN-CANVAS VALUE CELLS ARE UNCONTROLLED, and that is the fix for a P0
 * (DIM-1), not a style preference.
 *
 * A CONTROLLED cell round-trips every keystroke through React before the DOM is
 * allowed to keep it, and these cells live inside the r3f canvas via `Html` —
 * so a commit here can take tens of milliseconds, and the keystrokes that land
 * inside that window are overwritten when React finally re-renders from state
 * that predates them. Measured against the real browser on this build, typing
 * "125" over a pre-filled "43": the cell ended at **"43"** — every character
 * lost — at 0/20/40/60/80 ms per key, and only survived from 120 ms. That is
 * inside ordinary human typing speed, which is exactly the founder's report
 * ("I still cannot click dimension and actually have it assign a dimension").
 *
 * `SketchScene.tsx`'s draw-time cells (FB-16) hit the identical defect and fixed
 * it the same way; this is that remedy applied to the dimension/offset/corner
 * editors. The browser owns the text; React keeps a SHADOW copy purely so the
 * live error and the resolved-value echo can render, and every commit reads the
 * node (`read()`), never the shadow — the shadow is allowed to lag, the number
 * that gets solved is not.
 */
function useTypedField(resetKey: string | null, initial: string): TypedField {
  const ref = useRef<HTMLInputElement | null>(null);
  const [typed, setTyped] = useRetargetedDraft<string>(resetKey);
  const text = typed ?? initial;
  return {
    ref,
    text,
    // Safe to move per keystroke: changing `defaultValue` sets the input's
    // value ATTRIBUTE, which the HTML spec ignores once the field is dirty —
    // so it re-prefills on a retarget and never fights the typist.
    defaultValue: text,
    read: () => ref.current?.value ?? text,
    write: (next) => {
      if (ref.current !== null) ref.current.value = next;
      setTyped(next);
    },
    onChange: (event) => setTyped(event.target.value),
  };
}

/**
 * The value cell's rule in ONE place: the render reads it for the live error,
 * and the commit re-reads it against the DOM's own text (which can be ahead of
 * anything React has seen). A driven dimension is measured, so it is read-only
 * and always valid; a driving EXPRESSION is the server's to validate.
 */
function dimensionValueError(
  isDriving: boolean,
  parsed: DimensionValue,
): string | null {
  if (!isDriving) return null;
  if (parsed.kind === "empty") return "Enter a value or an expression.";
  if (parsed.kind === "literal" && !(parsed.valueMm > 0)) {
    return "Enter a value above 0.";
  }
  return null;
}

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
    case "midpoint":
      return "Midpoint constraint";
    case "collinear":
      return "Collinear constraint";
    // The kernel gained the `angle` dimension (SKETCH-VOCAB-1); its glyph,
    // editor and dimension-type chooser are the frontend half of that item, and
    // `buildGlyphs` emits nothing for it yet — so this arm exists to keep the
    // switch total, and the label is the plain degrees the solver reports.
    case "angle":
      return `Angle${glyph.driven ? " reference" : ""} ${glyph.label} degrees`;
    // Same note as `angle`: the kernel gained the DIAMETER dimension
    // (SKETCH-VOCAB-1) and `buildGlyphs` does not emit one yet, so this arm
    // keeps the switch total. The drawing convention is a leading diameter sign.
    case "diameter": {
      const bare = glyph.label.replace(/[()\u2300]/g, "");
      return `Diameter${glyph.driven ? " reference" : ""} ${bare} mm — edit`;
    }
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

  // One identity per edited constraint: it re-prefills the cells, so opening a
  // second dimension never inherits the first one's text.
  const editKey =
    target === null
      ? null
      : `${target.constraintIndex ?? "new"}:${target.entity}`;
  const valueField = useTypedField(
    editKey,
    target === null
      ? ""
      : (target.initialExpression ?? formatDimensionMm(target.initialMm)),
  );
  const nameField = useTypedField(editKey, target?.initialName ?? "");
  const [driving, setDriving] = useRetargetedDraft<boolean>(editKey);

  if (target === null || anchor === null) return null;

  const noun = target.kind === "distance" ? "Distance" : "Radius";
  const isDriving = driving ?? target.initialDriving;
  const valueText = valueField.text;
  const nameText = nameField.text;

  const parsedValue = classifyDimensionValue(valueText);
  const nameError = dimensionNameError(nameText);
  const valueError = dimensionValueError(isDriving, parsedValue);
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

  const close = (commit: boolean) => {
    if (!commit) {
      cancelDimension();
      return;
    }
    // Read the CELLS, not React's shadow of them. At typing speed the DOM is
    // ahead of the last render, and committing the render's value is precisely
    // how "125" got solved as 43 (DIM-1).
    const typedValue = valueField.read();
    const typedName = nameField.read();
    const parsed = classifyDimensionValue(typedValue);
    const errors =
      dimensionValueError(isDriving, parsed) ?? dimensionNameError(typedName);
    if (errors !== null) {
      // Stay open, showing the error against what was actually typed. Enter used
      // to fall through to cancelDimension() here — a key that sometimes applies
      // and sometimes discards is the FB-13 defect, not a validation strategy.
      valueField.write(typedValue);
      nameField.write(typedName);
      return;
    }
    const trimmedName = typedName.trim();
    commitDimension({
      valueMm:
        isDriving && parsed.kind === "literal" ? parsed.valueMm : placeholderMm,
      expression:
        isDriving && parsed.kind === "expression" ? parsed.expression : null,
      name: trimmedName === "" ? null : trimmedName,
      driving: isDriving,
    });
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
      <Panel className="w-[13rem] space-y-2 p-2" data-testid="dimension-editor">
        <form onSubmit={onSubmit} className="space-y-2">
          {isDriving ? (
            <ExpressionField
              // Keyed on the target so a retarget REMOUNTS the cell. Moving
              // `defaultValue` is not enough on its own: it sets the value
              // ATTRIBUTE, which the HTML spec ignores once the field is dirty
              // — so clicking a second glyph mid-edit would leave the first
              // dimension's text sitting in the second one's cell.
              key={`value:${editKey ?? ""}`}
              label={noun}
              unit="mm"
              ref={valueField.ref}
              defaultValue={valueField.defaultValue}
              error={valueError}
              resolved={resolved}
              onChange={valueField.onChange}
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
            key={`name:${editKey ?? ""}`}
            label="Name"
            ref={nameField.ref}
            defaultValue={nameField.defaultValue}
            error={nameError}
            placeholder="optional, e.g. width"
            onChange={nameField.onChange}
            onKeyDown={onKeyDown}
            data-testid="dimension-name"
            aria-label={`${noun} name (optional, for expressions)`}
          />
          <SegmentedControl
            label="This dimension"
            value={isDriving ? "driving" : "driven"}
            onChange={(next) => setDriving(next === "driving")}
            options={[
              {
                value: "driving",
                label: "Sets size",
                "data-testid": "dimension-driving",
                "aria-label":
                  "Sets size — the value you type controls the shape",
              },
              {
                value: "driven",
                label: "Reference",
                "data-testid": "dimension-driven",
                "aria-label":
                  "Reference — the value is measured from the shape, not typed",
              },
            ]}
          />
          {/* Plain-language gloss of the choice — no CAD jargon at the first
              dimension (UX audit #20c). */}
          <p className="-mt-0.5 font-body text-2xs text-gauge">
            {isDriving
              ? "Type a number to set the size."
              : "Read-only — measured from the shape."}
          </p>
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
  // Uncontrolled for the same reason as the dimension cell above (DIM-1).
  const field = useTypedField(draft?.target ?? null, String(DEFAULT_OFFSET_MM));

  const target =
    draft === null
      ? null
      : (entities.find((e) => e.id === draft.target) ?? null);
  const anchor = useMemo(
    () => (target === null ? null : entityAnchor(target)),
    [target],
  );

  if (draft === null || target === null || anchor === null) return null;

  const parsed = Number.parseFloat(field.text);
  const valid = Number.isFinite(parsed) && parsed !== 0;

  const apply = () => {
    // The cell, not the shadow — the last digit of "12.5" may not have reached
    // React yet, and offsetting by 12 instead is a wrong part, not a slow one.
    const typed = Number.parseFloat(field.read());
    if (!Number.isFinite(typed) || typed === 0) {
      field.write(field.read()); // surface the error against what was typed
      return;
    }
    armOffset(typed);
  };
  const flip = () => {
    const typed = Number.parseFloat(field.read());
    if (Number.isFinite(typed)) field.write(formatDimensionMm(-typed));
  };
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    apply();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      cancelOffset();
    }
  };

  return (
    <Html
      position={planeToWorld(basis, anchor)}
      center
      zIndexRange={GLYPH_Z_RANGE}
    >
      <Panel className="w-[12rem] p-2" data-testid="offset-editor">
        <form onSubmit={onSubmit}>
          <NumberField
            key={draft.target}
            label="Offset"
            unit="mm"
            ref={field.ref}
            defaultValue={field.defaultValue}
            error={valid ? null : "Enter a nonzero distance."}
            onChange={field.onChange}
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

  // A fresh corner never inherits the previous one's typed value: the picks are
  // the cell's identity. Uncontrolled, as the dimension cell above (DIM-1).
  const picksKey = corner?.picks.join(",") ?? null;
  const field = useTypedField(picksKey, String(DEFAULT_CORNER_MM));

  if (!open || corner === null || anchor === null) return null;

  const isFillet = corner.op === "fillet";
  const parsed = Number.parseFloat(field.text);
  const valid = Number.isFinite(parsed) && parsed > 0;
  const label = isFillet ? "Radius" : "Distance";

  const apply = () => {
    const typed = Number.parseFloat(field.read());
    if (!Number.isFinite(typed) || typed <= 0) {
      field.write(field.read()); // surface the error against what was typed
      return;
    }
    armCorner(typed);
  };
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    apply();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      cancelCorner();
    }
  };

  return (
    <Html
      position={planeToWorld(basis, anchor)}
      center
      zIndexRange={GLYPH_Z_RANGE}
    >
      <Panel className="w-[12rem] p-2" data-testid="corner-editor">
        <form onSubmit={onSubmit}>
          <NumberField
            key={picksKey ?? ""}
            label={isFillet ? "Fillet radius" : "Chamfer distance"}
            unit="mm"
            ref={field.ref}
            defaultValue={field.defaultValue}
            error={valid ? null : "Enter a value above 0."}
            onChange={field.onChange}
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

/**
 * Fit-point handles for the spline being worked on — the pick/constrain surface
 * for a spline's through-points. The fit points already render as brass dots
 * (`definingPoints`) and pick by the same raycast path as any endpoint; these
 * DOM handles add the keyboard-focusable, screen-reader-named, e2e-drivable
 * affordance on top. They read as diamonds (a rotated square) so a spline's
 * through-point is legible as its own thing next to a line endpoint's dot,
 * while staying in the one brass handle language — boldness stays where the
 * sketcher already spent it.
 *
 * Restraint: they appear ONLY when the spline is ENGAGED under the select tool
 * (hovered, or it or one of its fit points is selected), so the viewport stays
 * quiet at rest and the handles wake on approach. Clicking one toggles that fit
 * point into the selection — the same `EntityPointRef` a coincident / fixed /
 * symmetric constraint then consumes, unchanged.
 */
function SplineHandles({ basis }: { basis: PlaneBasis }) {
  const tool = useSketchStore((state) => state.tool);
  const entities = useSketchStore((state) => state.entities);
  const selection = useSketchStore((state) => state.selection);
  const hoverPick = useSketchStore((state) => state.hoverPick);
  const togglePick = useSketchStore((state) => state.togglePick);

  const engaged = useMemo(() => {
    if (tool !== "select") return [];
    return entities.filter((entity) => {
      if (entity.kind !== "spline") return false;
      const inSelection = selection.some(
        (pick) =>
          (pick.kind === "entity" && pick.id === entity.id) ||
          (pick.kind === "point" && pick.entity === entity.id),
      );
      const underHover =
        (hoverPick?.kind === "entity" && hoverPick.id === entity.id) ||
        (hoverPick?.kind === "point" && hoverPick.entity === entity.id);
      return inSelection || underHover;
    });
  }, [tool, entities, selection, hoverPick]);

  if (engaged.length === 0) return null;

  return (
    <group>
      {engaged.flatMap((spline) =>
        (spline.kind === "spline" ? spline.points : []).map((point, index) => {
          const name = `fit${index}`;
          const selected = selection.some(
            (pick) =>
              pick.kind === "point" &&
              pick.entity === spline.id &&
              pick.point === name,
          );
          return (
            <Html
              key={`${spline.id}-${name}`}
              position={planeToWorld(basis, point)}
              center
              zIndexRange={GLYPH_Z_RANGE}
            >
              <button
                type="button"
                data-testid={`fit-handle-${spline.id}-${index}`}
                data-selected={selected || undefined}
                aria-pressed={selected}
                aria-label={`Spline ${spline.id} fit point ${index + 1}`}
                onClick={(event) => {
                  event.stopPropagation();
                  togglePick({ kind: "point", entity: spline.id, point: name });
                }}
                className={`block h-2.5 w-2.5 rotate-45 cursor-pointer border border-brass motion-safe:transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass ${
                  selected ? "bg-brass" : "bg-anvil/60 hover:bg-brass/40"
                }`}
              />
            </Html>
          );
        }),
      )}
    </group>
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
      <SplineHandles basis={basis} />
      <DimensionEditor basis={basis} />
      <OffsetEditor basis={basis} />
      <CornerEditor basis={basis} />
    </group>
  );
}
