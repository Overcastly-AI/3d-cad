/**
 * FORMULAS IN EVERY NUMERIC FIELD (PART-PARAMETERS step 8, RESEARCH §20): the
 * pure rules and the two small stores behind `<ValueField>`.
 *
 * Stored form (step 4): a feature field's formula travels in the envelope's
 * `expressions` as `{json-pointer: formula}` (`{"/distance_mm": "H/2"}`), with
 * the resolved number in `params`. A sketch dimension keeps its formula in the
 * constraint's own `expression`, so the sketcher never uses a pointer.
 *
 * - The PARAMETER SCOPE store holds the part's table as the field reads it
 *   (names, values, kinds), fed by the part workspace. It is a store and not a
 *   React context because the sketcher's dimension box renders inside the r3f
 *   canvas, which no DOM context crosses.
 * - The FORMULA SESSION store holds the open feature editor's formulas by
 *   pointer, and the server's refusals by pointer, so the save path reads the
 *   formulas without every editor's submit growing an argument.
 */
import { create } from "zustand";

import { FUNCTION_NAMES, type Quantity } from "./expr";

// --- the parameter scope ---------------------------------------------------------

/** One part parameter, as a field reads it. */
export interface ScopeParameter {
  name: string;
  /** mm for a length, degrees for an angle. */
  value: number;
  unit: "length" | "angle" | "unitless";
}

interface ParameterScopeState {
  /** The part's table; null while it has not been read. */
  parameters: readonly ScopeParameter[] | null;
  setParameters: (parameters: readonly ScopeParameter[] | null) => void;
}

export const useParameterScopeStore = create<ParameterScopeState>()((set) => ({
  parameters: null,
  setParameters: (parameters) => set({ parameters }),
}));

/** A same-sketch dimension a sketcher formula may read (its number, unitless). */
export interface ScopeDimension {
  name: string;
  value: number;
}

/**
 * The names a formula may read, typed: the parameters, then (in the sketcher)
 * the sketch's own dimensions, which win over a parameter of the same name and
 * read their NUMBER unitless, as sketch formulas always have. Null while the
 * table is unread.
 */
export function scopeQuantities(
  parameters: readonly ScopeParameter[] | null,
  dimensions: readonly ScopeDimension[] = [],
): Map<string, Quantity> | null {
  if (parameters === null) return null;
  const names = new Map<string, Quantity>();
  for (const p of parameters) {
    names.set(p.name, { value: p.value, kind: p.unit });
  }
  for (const d of dimensions) {
    names.set(d.name, { value: d.value, kind: "unitless" });
  }
  return names;
}

// --- autocomplete ----------------------------------------------------------------

/** Something the field can offer while a name is typed. */
export interface CompletionCandidate {
  name: string;
  /** The value beside the name (`20 mm`), or the word `function`. */
  detail: string;
  source: "parameter" | "dimension" | "function";
}

export interface Completion {
  /** The typed word's span in the text, replaced on accept. */
  from: number;
  to: number;
  prefix: string;
  options: CompletionCandidate[];
}

/** Most options the list shows. */
export const MAX_COMPLETIONS = 8;

const WORD_BEFORE = /[A-Za-z_][A-Za-z0-9_]*$/;
const WORD_AFTER = /^[A-Za-z0-9_]*/;

/** The function names, offered after the scope's own names. */
export function functionCandidates(): CompletionCandidate[] {
  return FUNCTION_NAMES.map((name) => ({
    name,
    detail: "function",
    source: "function",
  }));
}

/**
 * The completion list for the word at `caret`, or null when there is nothing
 * to offer. A word right after a number is a unit (`10 mm`), not a name. With
 * `force` (Ctrl+Space) an empty word at an operand position lists everything.
 */
export function completionAt(
  text: string,
  caret: number,
  candidates: readonly CompletionCandidate[],
  force = false,
): Completion | null {
  const before = text.slice(0, caret);
  const word = WORD_BEFORE.exec(before);
  const prefix = word?.[0] ?? "";
  const from = caret - prefix.length;
  const lead = text.slice(0, from);
  // `10 m|`: a unit suffix position.
  if (/[0-9.]\s*$/.test(lead)) return null;
  if (prefix === "") {
    if (!force) return null;
    if (!/(^|[-+*/(,])\s*$/.test(lead)) return null;
  } else if (/^[0-9]/.test(prefix)) {
    return null;
  }
  const to = caret + (WORD_AFTER.exec(text.slice(caret))?.[0].length ?? 0);
  const lower = prefix.toLowerCase();
  const seen = new Set<string>();
  const matches = candidates.filter((candidate) => {
    if (seen.has(candidate.name)) return false;
    if (!candidate.name.toLowerCase().startsWith(lower)) return false;
    seen.add(candidate.name);
    return true;
  });
  // Case-exact prefix first; the scope's own names before functions.
  const rank = (c: CompletionCandidate): number =>
    (c.name.startsWith(prefix) ? 0 : 2) + (c.source === "function" ? 1 : 0);
  matches.sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
  const options = matches.slice(0, MAX_COMPLETIONS);
  if (options.length === 0) return null;
  // The word is already complete and nothing longer starts with it.
  if (options.length === 1 && options[0]?.name === prefix) return null;
  return { from, to, prefix, options };
}

/** The text after accepting `option` (a function gains its `(`), and the caret. */
export function applyCompletion(
  text: string,
  completion: Completion,
  option: CompletionCandidate,
): { text: string; caret: number } {
  const insert = option.source === "function" ? `${option.name}(` : option.name;
  const next =
    text.slice(0, completion.from) + insert + text.slice(completion.to);
  return { text: next, caret: completion.from + insert.length };
}

// --- pointers into params --------------------------------------------------------

/** RFC 6901 tokens of a pointer (`~1` is `/`, `~0` is `~`). */
function pointerTokens(pointer: string): string[] | null {
  if (!pointer.startsWith("/")) return null;
  return pointer
    .slice(1)
    .split("/")
    .map((t) => t.replace(/~1/g, "/").replace(/~0/g, "~"));
}

/** The value at `pointer` in a params tree, or undefined when it misses. */
export function valueAtPointer(params: unknown, pointer: string): unknown {
  const tokens = pointerTokens(pointer);
  if (tokens === null) return undefined;
  let node: unknown = params;
  for (const token of tokens) {
    if (Array.isArray(node)) {
      if (!/^(0|[1-9][0-9]*)$/.test(token)) return undefined;
      node = node[Number(token)];
    } else if (typeof node === "object" && node !== null) {
      if (!Object.prototype.hasOwnProperty.call(node, token)) return undefined;
      node = (node as Record<string, unknown>)[token];
    } else {
      return undefined;
    }
  }
  return node;
}

/**
 * The `expressions` a save sends: every formula whose pointer lands on a
 * number of these params. A field the form no longer sends (a hole switched to
 * Through all drops its depth) takes its formula with it, so the server never
 * sees a pointer to nothing. Undefined when no formula is left, which stores
 * none.
 */
export function expressionsForParams(
  params: unknown,
  formulas: Readonly<Record<string, string>>,
): Record<string, string> | undefined {
  const out: Record<string, string> = {};
  for (const [pointer, formula] of Object.entries(formulas)) {
    if (typeof valueAtPointer(params, pointer) === "number") {
      out[pointer] = formula;
    }
  }
  return Object.keys(out).length > 0 ? out : undefined;
}

// --- a feature's input_error -----------------------------------------------------

/** The two `input_error` codes a formula's feature can carry (RESEARCH §20). */
export const INPUT_ERROR_CODES: ReadonlySet<string> = new Set([
  "parameter_unresolved",
  "parameter_value_invalid",
]);

/**
 * The field an `input_error` (or a write's refusal) names, from its message:
 * `/distance_mm = 'H/2': …` or `refused by its field (params/distance_mm)`.
 */
export function inputErrorPointer(message: string): string | null {
  const lead = /^(\/\S+) = /.exec(message);
  if (lead !== null) return lead[1] ?? null;
  const refused = /\(params(\/[^)\s]+)\)/.exec(message);
  return refused === null ? null : (refused[1] ?? null);
}

/** `/bend_radius_mm` → `Bend radius`; `/axis/point/x` → `X`. */
export function fieldLabelFromPointer(pointer: string): string {
  const tokens = pointerTokens(pointer) ?? [pointer];
  const last = (tokens[tokens.length - 1] ?? "").replace(/_(mm|deg)$/, "");
  const words = last.replace(/_/g, " ").trim();
  if (words === "") return "Value";
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * The message without its pointer lead, in the field's own words:
 * `unknown parameter 'W'` → `parameter 'W' not found.`
 */
export function inputErrorSentence(message: string): string {
  let body = message
    .replace(/^\/\S+ = (?:'[^']*'|"[^"]*"):\s*/, "")
    .replace(/^A resolved value is refused by its field \([^)]*\):\s*/, "")
    .replace(/^expression for \S+ /, "");
  body = body
    .replace(/unknown parameter '([^']+)'/, "parameter '$1' not found")
    // A sketch formula reads its own dimensions first, then the parameters.
    .replace(
      /unknown dimension name '([^']+)' in expression/,
      "no dimension or parameter is named '$1'",
    );
  body = body.replace(/^Input should be/, "the value must be");
  return /[.!?]$/.test(body) ? body : `${body}.`;
}

/**
 * A feature's `input_error` as the tree and the editor show it:
 * `Width: parameter 'W' not found.`
 */
export function describeInputError(message: string): string {
  const pointer = inputErrorPointer(message);
  const sentence = inputErrorSentence(message);
  if (pointer === null) {
    return sentence.charAt(0).toUpperCase() + sentence.slice(1);
  }
  return `${fieldLabelFromPointer(pointer)}: ${sentence}`;
}

// --- the open editor's formulas ----------------------------------------------------

/** What the field needs to know about the editor it sits in. */
export interface FormulaSession {
  /** One per open editor: `extrude:<feature id>` or `extrude:new`. */
  key: string;
  /** The stored formulas of the feature being edited (none for a new one). */
  seed: Readonly<Record<string, string>>;
  /** The feature's `input_error`, on the field it names. */
  inputError: { pointer: string | null; message: string } | null;
}

interface FormulaSessionState {
  key: string | null;
  formulas: Readonly<Record<string, string>>;
  /** The server's refusal of the last save, by the field it names. */
  fieldErrors: Readonly<Record<string, string>>;
  /** How many mounted fields carry each pointer. */
  mounted: Readonly<Record<string, number>>;
}

const NONE: Readonly<Record<string, string>> = {};

export const useFormulaSessionStore = create<FormulaSessionState>()(() => ({
  key: null,
  formulas: NONE,
  fieldErrors: NONE,
  mounted: {},
}));

/** The session's formulas: the edits when it has any, else the stored seed. */
export function sessionFormulas(
  state: Pick<FormulaSessionState, "key" | "formulas">,
  key: string,
  seed: Readonly<Record<string, string>>,
): Readonly<Record<string, string>> {
  return state.key === key ? state.formulas : seed;
}

/** The session's server refusals (none for another session). */
export function sessionFieldErrors(
  state: Pick<FormulaSessionState, "key" | "fieldErrors">,
  key: string,
): Readonly<Record<string, string>> {
  return state.key === key ? state.fieldErrors : NONE;
}

/** Adopt `key` if the store holds another session's state. */
function adopt(
  state: FormulaSessionState,
  key: string,
  seed: Readonly<Record<string, string>>,
): Pick<FormulaSessionState, "key" | "formulas" | "fieldErrors"> {
  return state.key === key
    ? state
    : { key, formulas: { ...seed }, fieldErrors: NONE };
}

/** Set (or with null, drop) the formula at `pointer`. */
export function setSessionFormula(
  session: Pick<FormulaSession, "key" | "seed">,
  pointer: string,
  formula: string | null,
): void {
  useFormulaSessionStore.setState((state) => {
    const base = adopt(state, session.key, session.seed);
    if ((base.formulas[pointer] ?? null) === formula) return base;
    const formulas = { ...base.formulas };
    if (formula === null) delete formulas[pointer];
    else formulas[pointer] = formula;
    return { ...base, formulas };
  });
}

/** Put (or with null, clear) the server's refusal on the field at `pointer`. */
export function setSessionFieldError(
  session: Pick<FormulaSession, "key" | "seed">,
  pointer: string,
  message: string | null,
): void {
  useFormulaSessionStore.setState((state) => {
    const base = adopt(state, session.key, session.seed);
    if ((base.fieldErrors[pointer] ?? null) === message) return base;
    const fieldErrors = { ...base.fieldErrors };
    if (message === null) delete fieldErrors[pointer];
    else fieldErrors[pointer] = message;
    return { ...base, fieldErrors };
  });
}

/** A field with `pointer` is on screen (returns its unmount). */
export function mountFormulaField(pointer: string): () => void {
  const bump = (by: number) =>
    useFormulaSessionStore.setState((state) => ({
      mounted: {
        ...state.mounted,
        [pointer]: Math.max(0, (state.mounted[pointer] ?? 0) + by),
      },
    }));
  bump(1);
  return () => bump(-1);
}

/** Whether a field with `pointer` is on screen to carry its error. */
export function formulaFieldMounted(pointer: string): boolean {
  return (useFormulaSessionStore.getState().mounted[pointer] ?? 0) > 0;
}

/** The editor closed: its formulas and refusals go with it. */
export function clearFormulaSession(): void {
  useFormulaSessionStore.setState({
    key: null,
    formulas: NONE,
    fieldErrors: NONE,
  });
}
