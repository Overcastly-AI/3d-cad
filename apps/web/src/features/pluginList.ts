/**
 * A plugin's LIST input (CASEWORK, RESEARCH §23): an ordered list of rows of
 * number and choice fields, as a cabinet run's boxes. The generated form
 * shows it as an add and remove list; this module is its pure half, kept
 * beside `pluginForm` so the form is unit-tested without a DOM.
 *
 * The form holds every input as text by name, so a list's field text is its
 * rows as JSON: one object per row, each field's text by field name (a
 * length in the document unit, a count, an option key). A new row copies
 * the last one, as Mozaik adds the next cabinet like the one before.
 *
 * A row's fields take plain numbers (with units); a §20 formula on one row
 * is kept by documents (`/inputs/<name>/<row>/<field>`) but not offered
 * here, since adding or removing a row would move the formula to another.
 */
import { type LengthUnit, parseLength } from "@loft/design";

import type { CustomInputValue, PluginInput } from "../api/plugins";
import {
  storedLengthInput,
  storedLengthMm,
  storedNumber,
  storedNumberInput,
} from "./storedNumber";

export type ListInput = Extract<PluginInput, { kind: "list" }>;
export type ListField = ListInput["fields"][number];
/** One row's field texts, by field name. */
export type ListRowText = Record<string, string>;
/** A stored row: field name -> number or option key. */
type StoredRow = Record<string, number | string>;

const PLAIN_NUMBER_RE = /^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i;

function parsePlain(text: string): number | null {
  const trimmed = text.trim();
  if (!PLAIN_NUMBER_RE.test(trimmed)) return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

function isRow(value: unknown): value is StoredRow {
  return typeof value === "object" && value !== null && !("kind" in value);
}

/** The stored rows of a list input's value, or none. */
export function storedRows(value: CustomInputValue | undefined): StoredRow[] {
  if (!Array.isArray(value)) return [];
  return (value as unknown[]).filter(isRow);
}

function fieldText(
  field: ListField,
  value: number | string | undefined,
  unit: LengthUnit,
): string {
  if (field.kind === "choice") {
    return typeof value === "string" ? value : field.default;
  }
  const number = typeof value === "number" ? value : field.default;
  return field.kind === "length"
    ? storedLengthInput(number, unit)
    : storedNumberInput(number);
}

/** One row's texts from a stored row (a field it leaves out at its default). */
export function rowText(
  input: ListInput,
  row: StoredRow | undefined,
  unit: LengthUnit,
): ListRowText {
  const out: ListRowText = {};
  for (const field of input.fields) {
    out[field.name] = fieldText(field, row?.[field.name], unit);
  }
  return out;
}

/** The field text a list input's form starts with: its default rows. */
export function defaultListText(input: ListInput, unit: LengthUnit): string {
  return JSON.stringify(
    (input.default ?? []).map((row) => rowText(input, row as StoredRow, unit)),
  );
}

/** The field text of a stored list. */
export function storedListText(
  input: ListInput,
  value: CustomInputValue | undefined,
  unit: LengthUnit,
): string {
  return JSON.stringify(
    storedRows(value).map((row) => rowText(input, row, unit)),
  );
}

/** The rows a list field's text holds (none for text that is not rows). */
export function listRows(text: string): ListRowText[] {
  if (text === "") return [];
  try {
    const parsed: unknown = JSON.parse(text);
    if (!Array.isArray(parsed)) return [];
    return (parsed as unknown[]).filter(
      (row): row is ListRowText =>
        typeof row === "object" && row !== null && !Array.isArray(row),
    );
  } catch {
    return [];
  }
}

/** *text* with a row added: a copy of the last, else the default row. */
export function addRow(
  input: ListInput,
  text: string,
  unit: LengthUnit,
): string {
  const rows = listRows(text);
  const last = rows[rows.length - 1];
  const next =
    last === undefined
      ? rowText(input, input.default?.[0] as StoredRow | undefined, unit)
      : { ...last };
  return JSON.stringify([...rows, next]);
}

/** *text* without row *index*. */
export function removeRow(text: string, index: number): string {
  return JSON.stringify(listRows(text).filter((_, i) => i !== index));
}

/** *text* with row *index*'s *field* set to *value*. */
export function setRowField(
  text: string,
  index: number,
  field: string,
  value: string,
): string {
  return JSON.stringify(
    listRows(text).map((row, i) =>
      i === index ? { ...row, [field]: value } : row,
    ),
  );
}

/** A field's value in its own unit (mm, a count, an option key), or null. */
function fieldValue(
  field: ListField,
  text: string,
  unit: LengthUnit,
  stored: number | string | undefined,
): number | string | null {
  if (field.kind === "choice") {
    return field.options.some((o) => o.value === text) ? text : null;
  }
  const storedValue = typeof stored === "number" ? stored : null;
  if (field.kind === "length") {
    return storedLengthMm(text, unit, storedValue, (t, u) => parseLength(t, u));
  }
  return storedNumber(text, storedValue, parsePlain);
}

function fieldError(
  field: ListField,
  text: string,
  value: number | string | null,
): string | null {
  if (field.kind === "choice") {
    return value === null ? `Choose ${field.label.toLowerCase()}.` : null;
  }
  if (text.trim() === "") return `Enter ${field.label.toLowerCase()}.`;
  if (typeof value !== "number") return "Enter a number.";
  if (field.kind === "count" && !Number.isInteger(value)) {
    return "Must be a whole number.";
  }
  const low = field.minimum ?? null;
  const high = field.maximum ?? null;
  const open = field.kind !== "count" && field.exclusive_minimum;
  if (low !== null && (open ? value <= low : value < low)) return "Too small.";
  if (high !== null && value > high) return "Too large.";
  return null;
}

/**
 * Every row field's problem, by `<row>/<field>` (absent = fine), and the
 * list's own (too few or too many rows) under `""`.
 */
export function listErrors(
  input: ListInput,
  text: string,
  unit: LengthUnit,
  stored: CustomInputValue | undefined,
): Record<string, string> {
  const errors: Record<string, string> = {};
  const rows = listRows(text);
  const before = storedRows(stored);
  rows.forEach((row, i) => {
    for (const field of input.fields) {
      const fieldText = row[field.name] ?? "";
      const value = fieldValue(field, fieldText, unit, before[i]?.[field.name]);
      const error = fieldError(field, fieldText, value);
      if (error !== null) errors[`${i}/${field.name}`] = error;
    }
  });
  if (rows.length < input.min_items) {
    errors[""] = `Add at least ${input.min_items}.`;
  } else if (rows.length > input.max_items) {
    errors[""] = `At most ${input.max_items}.`;
  }
  return errors;
}

/** The first problem of a list, as one sentence naming its row. */
export function firstListError(
  input: ListInput,
  errors: Record<string, string>,
): string | null {
  if (errors[""] !== undefined) return errors[""];
  for (const [key, error] of Object.entries(errors)) {
    const [row, name] = key.split("/");
    const field = input.fields.find((f) => f.name === name);
    return `${input.item_label} ${Number(row) + 1}, ${field?.label ?? name}: ${error}`;
  }
  return null;
}

/** The rows a write sends (each field in its own unit), or null if invalid. */
export function listValue(
  input: ListInput,
  text: string,
  unit: LengthUnit,
  stored: CustomInputValue | undefined,
): StoredRow[] | null {
  const before = storedRows(stored);
  const out: StoredRow[] = [];
  for (const [i, row] of listRows(text).entries()) {
    const values: StoredRow = {};
    for (const field of input.fields) {
      const value = fieldValue(
        field,
        row[field.name] ?? "",
        unit,
        before[i]?.[field.name],
      );
      if (value === null) return null;
      values[field.name] = value;
    }
    out.push(values);
  }
  return out;
}
