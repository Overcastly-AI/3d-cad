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
} from "../units/length";

export type DrawEntry =
  /** Nothing typed: the box leaves its measure as drawn. */
  | { kind: "empty" }
  /** A value (mm); `expression` is the formula that made it, if any. */
  | { kind: "value"; mm: number; expression: string | null }
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
  return { kind: "value", mm, expression };
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
    const entry = resolveDrawEntry(textOf(index), unit, names);
    if (entry.kind === "error") out.errors[field.key] = entry.message;
    if (entry.kind !== "value") return;
    out.values[field.key] = entry.mm;
    if (entry.expression !== null) {
      out.expressions[field.key] = entry.expression;
    }
  });
  return out;
}

/** True when no cell refused its text. */
export const drawCellsOk = (cells: DrawCells): boolean =>
  Object.keys(cells.errors).length === 0;
