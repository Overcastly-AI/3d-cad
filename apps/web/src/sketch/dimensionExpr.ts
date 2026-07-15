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

/** A bare literal: optional sign, digits, optional decimal. Nothing else. */
const LITERAL_RE = /^[+-]?\d+(\.\d+)?$/;

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
export function classifyDimensionValue(text: string): DimensionValue {
  const trimmed = text.trim();
  if (trimmed === "") return { kind: "empty" };
  if (LITERAL_RE.test(trimmed)) {
    return { kind: "literal", valueMm: Number.parseFloat(trimmed) };
  }
  return { kind: "expression", expression: trimmed };
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
