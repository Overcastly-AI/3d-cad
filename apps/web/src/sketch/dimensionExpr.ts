/**
 * Dimension value + name parsing — pure, testable, no store, no three.js.
 *
 * A dimension's value cell accepts either a bare numeric literal (`20` → the
 * constraint's `value_mm`) or a math expression over other dimension NAMES
 * (`width/2` → the constraint's `expression`, which supersedes `value_mm` and
 * the geometry service re-evaluates each solve). This module decides which,
 * and hints the server's identifier rule for names — the server stays the
 * source of truth (uniqueness / a bad expression come back as `sketch_invalid`).
 */

// The units core alone: the package root pulls the Tailwind preset, which
// Node cannot load when an e2e spec imports the sketch modules.
import {
  isCarpenterLength,
  type LengthUnit,
  parseLength,
} from "@loft/design/units";

import { typedFormulaError } from "../units/length";

/** A bare literal: optional sign, digits, optional decimal. Nothing else. */
const LITERAL_RE = /^[+-]?\d+(\.\d+)?$/;

/** A decimal with a unit suffix: `28 ft`, `20mm`. */
const SUFFIXED_RE = /^[+-]?(?:\d+\.?\d*|\.\d+)\s*(?:mm|cm|m|in|ft)$/i;

/** The server's dimension-name identifier rule (`^[A-Za-z_][A-Za-z0-9_]*$`). */
const NAME_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

export type DimensionValue =
  | { kind: "literal"; valueMm: number }
  | { kind: "expression"; expression: string }
  | { kind: "empty" };

/**
 * Classify a value-cell entry: a bare number is a LITERAL (drives `value_mm`);
 * any other non-empty text is an EXPRESSION (sent verbatim — the server parses
 * and validates it). Empty is its own case so callers can require a value.
 */
export function classifyDimensionValue(
  text: string,
  { length = false, stored = null, unit = "mm" }: ClassifyOptions = {},
): DimensionValue {
  const trimmed = text.trim();
  if (trimmed === "") return { kind: "empty" };
  if (LITERAL_RE.test(trimmed)) {
    // A length box reads a bare number in the PART's unit, as every length
    // field does (`288` in an inch part is 7315.2 mm); an angle in degrees.
    const valueMm = length
      ? parseLength(trimmed, unit)
      : Number.parseFloat(trimmed);
    if (valueMm !== null) return { kind: "literal", valueMm };
  }
  // A length with its own unit (`28 ft`, `20 mm`) and carpenter notation
  // (`11 15/32`, `5' 6"`, RESEARCH §29) are literals in a length box, read in
  // the part's unit unless they carry their own marks. The stored expression,
  // re-committed untouched, keeps the meaning the server gave it.
  if (
    length &&
    trimmed !== stored &&
    (SUFFIXED_RE.test(trimmed) || isCarpenterLength(trimmed, unit))
  ) {
    const valueMm = parseLength(trimmed, unit);
    if (valueMm !== null) return { kind: "literal", valueMm };
  }
  return { kind: "expression", expression: trimmed };
}

export interface ClassifyOptions {
  /** A length dimension (carpenter notation is a literal there). */
  length?: boolean;
  /** The dimension's stored expression, which keeps its meaning. */
  stored?: string | null;
  /** The part's length unit, which a bare number in a length box is in. */
  unit?: LengthUnit;
}

/**
 * Why a length expression typed into the box reads two ways (`2*11-15/32`),
 * or null; the stored expression is the server's and is never questioned.
 */
export function dimensionAmbiguity(
  parsed: DimensionValue,
  { length = false, stored = null, unit = "mm" }: ClassifyOptions = {},
): string | null {
  if (!length || parsed.kind !== "expression") return null;
  if (parsed.expression === stored) return null;
  return typedFormulaError(parsed.expression, "length", unit);
}

/**
 * Client-side name check — a hint, not the authority. Empty is valid (an
 * unnamed dimension still solves, just isn't referenceable). A malformed
 * identifier is caught here so the field flags it before a round-trip;
 * UNIQUENESS is the server's call (a duplicate returns `sketch_invalid`).
 */
export function dimensionNameError(name: string): string | null {
  const trimmed = name.trim();
  if (trimmed === "") return null;
  if (!NAME_RE.test(trimmed)) {
    return "Start with a letter or _, then letters, digits, or _.";
  }
  return null;
}
