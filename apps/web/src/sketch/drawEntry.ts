/**
 * What a draw-time box's text comes to (QA-RECT-BOX-NAMES): pure, no store.
 *
 * Every value box the sketcher hangs on a gesture (a rectangle's W and H, a
 * circle's diameter, a line's length, the typed X / Y of a point) takes a
 * number OR a formula, as Fusion's do: `80`, `W`, `W/2 + 5`. A number reads in
 * the document unit, as it always did. A formula is resolved HERE, over the
 * part's parameters and this sketch's named dimensions, because the geometry
 * is rewritten to the typed size the moment Enter lands (see
 * `drawDimensions.ts`), and the formula itself rides on the dimension it
 * creates (`expression`), exactly as the dimension box sends it.
 *
 * A formula that does not resolve is an ERROR the box shows, never a silent
 * nothing: the QA defect was `W` Enter applying no dimension and saying so
 * nowhere.
 */
import type { LengthUnit } from "@loft/design";

import type { Quantity } from "../features/expr";
import type {
  DrawDimensionExpressions,
  DrawDimensionField,
  DrawDimensionKey,
  DrawDimensionValues,
} from "./drawDimensions";
import {
  parseFieldEntry,
  parseSignedLengthMm,
  resolveFieldFormula,
  typedFormulaError,
} from "../units/length";

export type DrawEntry =
  /** Nothing typed: the box leaves its measure as drawn. */
  | { kind: "empty" }
  /**
   * A value: mm, or degrees from an angle cell; `expression` is the formula
   * that made it, if any.
   */
  | { kind: "value"; value: number; expression: string | null }
  /** Typed, but not a value the box can take: the reason, for the box. */
  | { kind: "error"; message: string };

/**
 * Resolve one box's text. `signed` boxes (coordinates) take zero and negatives;
 * size boxes take only a positive length.
 */
export function resolveDrawEntry(
  text: string,
  unit: LengthUnit,
  names: ReadonlyMap<string, Quantity>,
  { signed = false }: { signed?: boolean } = {},
): DrawEntry {
  const entry = parseFieldEntry(text, "length", unit);
  if (entry.kind === "empty") return { kind: "empty" };
  let mm: number | null;
  let expression: string | null = null;
  if (entry.kind === "number") {
    mm = parseSignedLengthMm(text.trim(), unit);
    if (mm === null) return { kind: "error", message: "Enter a number." };
  } else {
    const ambiguous = typedFormulaError(entry.expression, "length", unit);
    if (ambiguous !== null) return { kind: "error", message: ambiguous };
    const result = resolveFieldFormula(entry.expression, "length", names);
    if (!result.ok) return { kind: "error", message: result.message };
    mm = result.value;
    expression = entry.expression;
  }
  if (!Number.isFinite(mm)) {
    return { kind: "error", message: "Enter a number." };
  }
  if (!signed && !(mm > 0)) {
    return {
      kind: "error",
      message:
        expression === null
          ? "Enter a size above 0."
          : `${expression} comes to ${mm}; a size must be above 0.`,
    };
  }
  return { kind: "value", value: mm, expression };
}

/**
 * The message for an angle typed outside (0, 180). A number past 180 is most
 * often the Y of an end point typed into the line's box after the click (the
 * LINE-LENGTH-TAB mistake, now landing in the angle cell), so it says how to
 * type a point instead.
 */
export function angleRangeMessage(deg: number, expression: string | null) {
  const range = "An angle must be above 0° and below 180°.";
  const said =
    expression === null ? range : `${expression} comes to ${deg}°. ${range}`;
  return deg > 180
    ? `${said} To place the end point, type X Tab Y before you click.`
    : said;
}

/**
 * Resolve a line's ANGLE cell (SKETCH-LINE-ANGLE): degrees, whatever the
 * document's length unit (a bare number is degrees, `30 deg` and `A/2` are
 * formulas), strictly within (0, 180) as `AngleConstraint` requires.
 */
export function resolveAngleEntry(
  text: string,
  names: ReadonlyMap<string, Quantity>,
): DrawEntry {
  const entry = parseFieldEntry(text, "angle", "mm");
  if (entry.kind === "empty") return { kind: "empty" };
  let deg: number;
  let expression: string | null = null;
  if (entry.kind === "number") {
    deg = Number(text.trim());
  } else {
    const result = resolveFieldFormula(entry.expression, "angle", names);
    if (!result.ok) return { kind: "error", message: result.message };
    deg = result.value;
    expression = entry.expression;
  }
  if (!Number.isFinite(deg)) {
    return { kind: "error", message: "Enter a number." };
  }
  if (!(deg > 0 && deg < 180)) {
    return { kind: "error", message: angleRangeMessage(deg, expression) };
  }
  return { kind: "value", value: deg, expression };
}

/** A gesture's size cells, resolved together. */
export interface DrawCells {
  values: DrawDimensionValues;
  expressions: DrawDimensionExpressions;
  /** Per cell, why it cannot apply. Any entry here and nothing applies. */
  errors: Partial<Record<DrawDimensionKey, string>>;
}

/**
 * Resolve every size cell of a gesture from its text (`textOf(index)`). One
 * bad cell holds back the lot: applying W while H says `Q` is not found would
 * be the half-applied silent outcome this module exists to end.
 */
export function resolveDrawCells(
  fields: readonly Pick<DrawDimensionField, "key">[],
  textOf: (index: number) => string,
  unit: LengthUnit,
  names: ReadonlyMap<string, Quantity>,
): DrawCells {
  const out: DrawCells = { values: {}, expressions: {}, errors: {} };
  fields.forEach((field, index) => {
    const entry =
      field.key === "angle"
        ? resolveAngleEntry(textOf(index), names)
        : resolveDrawEntry(textOf(index), unit, names);
    if (entry.kind === "error") out.errors[field.key] = entry.message;
    if (entry.kind !== "value") return;
    out.values[field.key] = entry.value;
    if (entry.expression !== null) {
      out.expressions[field.key] = entry.expression;
    }
  });
  return out;
}

/** True when no cell refused its text. */
export const drawCellsOk = (cells: DrawCells): boolean =>
  Object.keys(cells.errors).length === 0;

/**
 * LINE-LENGTH-TAB (docs/reference-parts/bike.md finding 3). A drawn line's box
 * has ONE cell, its length; an engineer who means the end point types
 * "426.562 Tab 450.469 Enter" into it. Tab used to leave the box (for the
 * Horizontal glyph), and the second number was then appended to the first
 * ("426.562450.469"), refused with a parse error that named no cause; retyped,
 * the second number became the LENGTH. A one-cell box keeps the keyboard on
 * Tab, as Fusion's draw boxes do, and says what it takes instead.
 */
export function oneValueMessage(
  field: Pick<DrawDimensionField, "key" | "name">,
): string {
  const what = `This box takes one value, the ${field.name.toLowerCase()}.`;
  return field.key === "length"
    ? `${what} To place the end point, type X Tab Y before you click.`
    : what;
}

/**
 * Was a second value typed after a Tab in a one-cell box? `textAtTab` is the
 * cell's text when Tab was pressed (empty: nothing was typed before it, so the
 * typing after it is the only value). True when the text still begins with it
 * and has grown: the second number would be glued onto the first.
 */
export function secondValueTyped(textAtTab: string, text: string): boolean {
  if (textAtTab.trim() === "") return false;
  return (
    text.startsWith(textAtTab) && text.slice(textAtTab.length).trim() !== ""
  );
}
