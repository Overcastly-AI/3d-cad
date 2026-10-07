/**
 * Solve feedback and the verb offers — pure functions, no store, no three.js.
 *
 * Split out of `constraints.ts` (file-size ratchet, SKETCH-POINT-DISTANCE)
 * unchanged: the DRO/diagnostic view of a solve, and which constraint verbs a
 * selection unlocks.
 */
import {
  applyConstraintAction,
  CONSTRAINT_SHORTCUTS,
  type ConstraintAction,
  type SketchConstraint,
  type SolveStatus,
} from "./constraints";
import { isDatumPin } from "./datum";
import type { SketchPick } from "./pick";
import type { SketchEntity } from "./tools";

// ---------------------------------------------------------------------------
// Solve feedback
// ---------------------------------------------------------------------------

/**
 * The DRO/diagnostic view of one evaluate round-trip for the bound sketch.
 * `"invalid"` is the sketcher's local status for a `sketch_invalid` feature
 * error (bad expression / cycle / unknown or driven reference / div-by-zero) —
 * the sketch didn't solve at all, so it has no solver status; `message` carries
 * the server's descriptive text for the diagnostic stamp.
 */
export interface SolveInfo {
  status: SolveStatus | "invalid";
  dof: number | null;
  conflicting: number[];
  redundant: number[];
  /** The `sketch_invalid` message when `status === "invalid"`; else absent. */
  message?: string;
}

// Conflicting sketches now carry their offending constraint ids in the TYPED
// `FeatureError.sketch_diagnosis` field (BACKLOG #6), read directly in
// PartPage — the former `parseConflictIndices` regex over the human message
// was removed once the backend promoted the ids to a structured field.

/** DRO SOLVE cell: value text + ink. Status vocabulary stays terse (DRO). */
export function formatSolveCell(
  info: SolveInfo | null,
  busy: boolean,
): { value: string; tone: "brass" | "mist" | "flag" | "gauge" } {
  if (busy) return { value: "SOLVING…", tone: "gauge" };
  if (info === null) return { value: "—", tone: "gauge" };
  switch (info.status) {
    case "converged":
      return { value: "DOF 0 · CONVERGED", tone: "brass" };
    case "underconstrained":
      return {
        value: `DOF ${info.dof ?? "?"} · UNDER-CONSTRAINED`,
        tone: "mist",
      };
    case "overconstrained":
      return { value: "OVER-CONSTRAINED", tone: "flag" };
    case "conflicting":
      return { value: "CONFLICT", tone: "flag" };
    case "diverged":
      return { value: "DIVERGED", tone: "flag" };
    case "invalid":
      return { value: "INVALID EXPRESSION", tone: "flag" };
  }
}

/** The in-viewport diagnostic stamp for a sick solve; null when healthy. */
export function solveDiagnostic(
  info: SolveInfo | null,
): { title: string; body: string } | null {
  if (info === null) return null;
  switch (info.status) {
    case "conflicting":
      return {
        title: "Solve conflict",
        body:
          info.conflicting.length > 0
            ? `${info.conflicting.length} constraints cannot all hold — they are flagged in the sketch. Remove or edit one.`
            : // Nothing is flagged, so do not claim there is. The solver
              // located the conflict only in constraints the user cannot
              // reach — in practice the frame's own pins, which are the only
              // hidden constraints there are (`sketch/datum.ts`). Never
              // silenced: a conflicting sketch did not solve, so the geometry
              // on screen is wrong and saying so is mandatory. Point at the
              // one place it can be, instead of at a flag that is not there.
              "The constraints cannot all hold, and the conflict is with the origin and axes — the frame cannot move. Remove or edit a constraint that reaches for it.",
      };
    case "overconstrained":
      return {
        title: "Over-constrained",
        body:
          info.redundant.length > 0
            ? "A redundant constraint is flagged in the sketch. Remove it — the geometry is already determined without it."
            : "The sketch has one constraint more than it needs, and the solver could not say which. Remove the last one you added.",
      };
    case "invalid":
      return {
        title: "Dimension expression",
        body:
          info.message ??
          "A dimension expression could not be evaluated. Check the names it references, and for cycles or division by zero.",
      };
    case "diverged":
      return {
        title: "Solve diverged",
        body: "The solver could not converge from the current positions. Edit a dimension or remove the last constraint.",
      };
    default:
      return null;
  }
}

/**
 * Constraints the USER authored — the frame's pins excluded. The "N applied"
 * readout counts these: grounding a corner to the origin is one constraint the
 * user made, and reporting the pin that came with it would be the readout
 * claiming work nobody did.
 */
export function authoredConstraintCount(
  constraints: readonly SketchConstraint[],
): number {
  return constraints.filter((c) => !isDatumPin(c)).length;
}

/** Short selection readout for the constraint strip ("1 line · 2 pts"). */
export function describeSelection(selection: readonly SketchPick[]): string {
  const entities = selection.filter((p) => p.kind === "entity").length;
  const points = selection.length - entities;
  if (selection.length === 0) return "nothing selected";
  const parts: string[] = [];
  if (entities > 0)
    parts.push(`${entities} ${entities === 1 ? "ent" : "ents"}`);
  if (points > 0) parts.push(`${points} ${points === 1 ? "pt" : "pts"}`);
  return parts.join(" · ");
}

/** A surfaced keyboard verb — the key to press and its plain-verb label. */
export interface SketchVerbHint {
  key: string;
  label: string;
  /** The verb the key runs, so the keycap can also be CLICKED to run it. */
  action: ConstraintAction;
}

/**
 * The verbs the offer rail may propose, MOST SPECIFIC FIRST.
 *
 * Order is the whole design. Every verb below is already reachable by key, and
 * a list of everything the selection accepts would be a menu — which is the
 * thing the user was already failing to read. So the rail proposes the verbs
 * that this PARTICULAR selection unlocks and a general toolbar cannot: the
 * dimension the selection implies, then the relations that need a specific
 * shape of pick (an angle needs two lines; symmetric needs a centerline in the
 * selection). The broad relations that apply to almost any pair — parallel,
 * perpendicular, equal — come last and usually fall off the end.
 */
const VERB_OFFER_ORDER: readonly ConstraintAction[] = [
  "angle",
  // Diameter before distance: on a round, D routes to diameter, so both verbs
  // accept the same selection and the more specific label must win the key.
  "diameter",
  "distance",
  "radius",
  "collinear",
  "symmetric",
  "midpoint",
  "concentric",
  "tangent",
  "equal",
  "parallel",
  "perpendicular",
];

/** Plain-verb labels — what the user is about to do, in their words. */
const VERB_LABEL: Readonly<Record<ConstraintAction, string>> = {
  horizontal: "horizontal",
  vertical: "vertical",
  distance: "dimension",
  radius: "radius",
  diameter: "diameter",
  angle: "angle",
  fixed: "fix",
  coincident: "join",
  parallel: "parallel",
  perpendicular: "perpendicular",
  collinear: "collinear",
  tangent: "tangent",
  equal: "equal",
  symmetric: "symmetric",
  midpoint: "midpoint",
  concentric: "concentric",
};

/**
 * THE PICK SHAPE EACH VERB NEEDS — a noun phrase, never a sentence.
 *
 * The one thing a user cannot deduce from a verb's NAME is what to hold before
 * pressing it, and it is the only reason the offer rail is not the whole
 * answer: the rail proposes a verb once the selection already fits, so it can
 * never teach the selection that would make it appear. "Angle" is not
 * discoverable from an empty selection at any price; "angle · needs 2 lines"
 * is.
 *
 * Deliberately NOT derived from `applyConstraintAction`'s refusal strings.
 * Those are full sentences aimed at a user who has just been refused ("Select
 * two lines to dimension the angle between them"), and sixteen of them stacked
 * in a menu is prose, not an instrument. The totality is what keeps the two
 * honest instead: this is an exhaustive `Record<ConstraintAction, …>`, so a new
 * verb cannot compile without stating its shape here.
 */
const VERB_SELECTION: Readonly<Record<ConstraintAction, string>> = {
  horizontal: "a line",
  vertical: "a line",
  distance: "a line, 2 points, or a point + a line",
  radius: "a circle/arc",
  diameter: "a circle/arc",
  angle: "2 non-parallel lines",
  fixed: "a point",
  coincident: "2 points",
  parallel: "2 lines",
  perpendicular: "2 lines",
  collinear: "2 lines",
  tangent: "a curve + a circle/arc",
  equal: "2 lines, or 2 circles/arcs",
  // Both forms, even though it wraps: this row is the one the OLD caption got
  // wrong by naming only the points form, and a shorter half-truth here would
  // reintroduce exactly that defect one line lower.
  symmetric: "2 points + a line, or 2 lines + a centerline",
  midpoint: "a point + a line",
  concentric: "2 circles/arcs",
};

/** The pick shape {@link action} needs, for a surface that must say so. */
export function verbSelectionShape(action: ConstraintAction): string {
  return VERB_SELECTION[action];
}

/**
 * Would {@link action} DO something with this exact selection?
 *
 * The single availability predicate, and deliberately the only one. Both
 * surfaces that answer "can I use this verb right now" read it: the offer rail
 * (which verbs to propose) and the constraint catalogue (which rows are live).
 * A second rule written for the catalogue would be a rule that can disagree
 * with the rail about the same selection — the drift `VERB_KEY` was inverted
 * out of `CONSTRAINT_SHORTCUTS` to prevent, in a new place.
 *
 * Truthful by construction: it asks the VERB, rather than re-deriving the
 * verb's own preconditions, so it cannot advertise a row that answers "Select
 * two lines…", and it goes false for a constraint that is already stated.
 */
export function verbIsAvailable(
  action: ConstraintAction,
  selection: readonly SketchPick[],
  entities: readonly SketchEntity[],
  constraints: readonly SketchConstraint[],
): boolean {
  return (
    applyConstraintAction(action, selection, entities, constraints).outcome !==
    "hint"
  );
}

/**
 * The key a verb answers to. Inverted from {@link CONSTRAINT_SHORTCUTS} so the
 * rail can never advertise a key the keyboard does not honour — the two used to
 * be written out twice and that is exactly how a hint becomes a lie.
 */
const VERB_KEY: Readonly<Record<string, string>> = Object.fromEntries(
  Object.entries(CONSTRAINT_SHORTCUTS).map(([key, action]) => [
    action,
    key.toUpperCase(),
  ]),
);

/** Diameter has no key of its own — D is the dimension key (see the doc there). */
const verbKey = (action: ConstraintAction): string =>
  action === "diameter" ? "D" : (VERB_KEY[action] ?? "");

/** How many verbs the rail will show. Three is a glance; five is a menu. */
const MAX_VERB_HINTS = 3;

/**
 * THE SELECTION OFFERS THE VERBS THAT APPLY TO IT — the reachability mechanism
 * for SKETCH-VOCAB-1, and the generalisation of the single dimension hint this
 * replaced (FINDINGS #12: select-then-D was invisible, the probable novice
 * give-up point). Five verbs shipped in the contract with no way for a user to
 * find them; a sixth toolbar row would not have fixed that, because the problem
 * was never that the button was missing — it was that nothing told you your
 * current selection had made a verb available.
 *
 * Truthful by construction: an offer appears only when
 * {@link applyConstraintAction} would actually DO something with this exact
 * selection — open an editor, or add a constraint that is not already there.
 * There is no parallel rule to drift out of sync, and the rail can never
 * propose a key that answers "Select two lines…".
 */
export function selectionVerbHints(
  selection: readonly SketchPick[],
  entities: readonly SketchEntity[],
  constraints: readonly SketchConstraint[],
): SketchVerbHint[] {
  if (selection.length === 0) return [];
  const hints: SketchVerbHint[] = [];
  for (const action of VERB_OFFER_ORDER) {
    if (hints.length === MAX_VERB_HINTS) break;
    const key = verbKey(action);
    // One cap per key: distance and diameter share D, and a rail offering the
    // same keycap twice would be asking the user to choose what the selection
    // has already decided.
    if (hints.some((h) => h.key === key)) continue;
    if (!verbIsAvailable(action, selection, entities, constraints)) continue;
    hints.push({ key, label: VERB_LABEL[action], action });
  }
  return hints;
}
