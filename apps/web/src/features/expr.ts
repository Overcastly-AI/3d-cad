/**
 * The expression language, read the way the server reads it
 * (`packages/loft-wire/src/loft_wire/expr.py`, RESEARCH §20), so a field can
 * show what a formula comes to while it is typed (`H/2` → `= 10 mm`) and drive
 * the live preview from it.
 *
 * The server stays the authority: documents evaluates every formula again on
 * write and stores the number it gets. This is the same grammar, kinds, units
 * and function whitelist, so the two agree; a disagreement can only make the
 * client refuse less than the server (the server's 422 then lands on the field).
 *
 * Kinds: `length` is held in mm, `angle` in degrees, `unitless` joins either.
 * Trig takes degrees. Never `eval`: anything outside the grammar is an
 * {@link ExprError} with the server's stable code.
 */

import {
  isCarpenterLength,
  lengthExpression,
  type LengthUnit,
} from "@loft/design";

export type ExprKind = "length" | "angle" | "unitless";

export interface Quantity {
  value: number;
  kind: ExprKind;
}

/** The server's stable codes (`loft_wire/expr.py`), plus the field's own. */
export type ExprErrorCode =
  | "expression_syntax"
  | "expression_too_complex"
  | "expression_units"
  | "expression_domain"
  | "expression_unknown_name";

export class ExprError extends Error {
  constructor(
    readonly code: ExprErrorCode,
    message: string,
    /** The unresolved name, for `expression_unknown_name`. */
    readonly unknownName: string | null = null,
  ) {
    super(message);
    this.name = "ExprError";
  }
}

export const MAX_EXPRESSION_LENGTH = 256;
const MAX_DEPTH = 150;

/** Unit suffix → factor to the kind's canonical unit, and the kind. */
const UNITS: Readonly<Record<string, readonly [number, ExprKind]>> = {
  mm: [1, "length"],
  cm: [10, "length"],
  m: [1000, "length"],
  in: [25.4, "length"],
  ft: [304.8, "length"],
  deg: [1, "angle"],
  rad: [180 / Math.PI, "angle"],
};

/** Whitelisted function → [min, max] argument count (max null = variadic). */
const FUNCTIONS: Readonly<Record<string, readonly [number, number | null]>> = {
  sin: [1, 1],
  cos: [1, 1],
  tan: [1, 1],
  asin: [1, 1],
  acos: [1, 1],
  atan: [1, 1],
  atan2: [2, 2],
  sqrt: [1, 1],
  abs: [1, 1],
  min: [1, null],
  max: [1, null],
  round: [1, 1],
  floor: [1, 1],
  ceil: [1, 1],
  rad: [1, 1],
  deg: [1, 1],
};

/** Words that are never a name: units, constants and functions. */
export const RESERVED_WORDS: ReadonlySet<string> = new Set([
  ...Object.keys(UNITS),
  "pi",
  ...Object.keys(FUNCTIONS),
]);

/** The function names, for the field's completion list. */
export const FUNCTION_NAMES: readonly string[] = Object.keys(FUNCTIONS);

/** A token and where it sits in the text (`s`..`e`, whitespace excluded). */
type Token = { t: "num" | "id" | "op"; v: string; s: number; e: number };

const TOKEN_RE =
  /[ \t\r\n]*(?:([0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)|([A-Za-z_][A-Za-z0-9_]*)|([-+*/(),]))/y;

function tokenize(text: string): Token[] {
  const tokens: Token[] = [];
  let at = 0;
  while (at < text.length) {
    TOKEN_RE.lastIndex = at;
    const match = TOKEN_RE.exec(text);
    if (match === null) {
      const rest = text.slice(at).replace(/^[ \t\r\n]+/, "");
      if (rest === "") break;
      throw new ExprError(
        "expression_syntax",
        `invalid character '${rest[0] ?? ""}'`,
      );
    }
    at = TOKEN_RE.lastIndex;
    const v = match[1] ?? match[2] ?? (match[3] as string);
    const t =
      match[1] !== undefined ? "num" : match[2] !== undefined ? "id" : "op";
    tokens.push({ t, v, s: at - v.length, e: at });
  }
  return tokens;
}

/**
 * A parsed node and where it sits (`s`..`e`; a parenthesised group spans its
 * parentheses). `bareEnd` is where a NUMBER with no unit suffix ends.
 */
type Node = { s: number; e: number } & (
  | { n: "num"; q: Quantity; bareEnd?: number }
  | { n: "ref"; name: string }
  | { n: "neg"; operand: Node }
  | { n: "bin"; op: string; left: Node; right: Node }
  | { n: "call"; name: string; args: Node[] }
);

function parse(text: string, names: ReadonlySet<string>): Node {
  if (text.length > MAX_EXPRESSION_LENGTH) {
    throw new ExprError(
      "expression_too_complex",
      `longer than ${MAX_EXPRESSION_LENGTH} characters`,
    );
  }
  const tokens = tokenize(text);
  if (tokens.length === 0) throw new ExprError("expression_syntax", "empty");
  let at = 0;
  let depth = 0;
  const peek = (): Token | undefined => tokens[at];
  const lastEnd = (): number => tokens[at - 1]?.e ?? 0;
  const isOp = (v: string): boolean => {
    const token = peek();
    return token?.t === "op" && token.v === v;
  };
  const expect = (v: string): void => {
    if (!isOp(v)) throw new ExprError("expression_syntax", `missing '${v}'`);
    at += 1;
  };

  function expr(): Node {
    let node = term();
    while (isOp("+") || isOp("-")) {
      const op = (tokens[at] as Token).v;
      at += 1;
      const right = term();
      node = { n: "bin", op, left: node, right, s: node.s, e: right.e };
    }
    return node;
  }

  function term(): Node {
    let node = factor();
    while (isOp("*") || isOp("/")) {
      const op = (tokens[at] as Token).v;
      at += 1;
      const right = factor();
      node = { n: "bin", op, left: node, right, s: node.s, e: right.e };
    }
    return node;
  }

  function factor(): Node {
    depth += 1;
    try {
      if (depth > MAX_DEPTH) {
        throw new ExprError(
          "expression_too_complex",
          `nests deeper than ${MAX_DEPTH}`,
        );
      }
      if (isOp("+") || isOp("-")) {
        const sign = tokens[at] as Token;
        at += 1;
        const operand = factor();
        return sign.v === "-"
          ? { n: "neg", operand, s: sign.s, e: operand.e }
          : operand;
      }
      return primary();
    } finally {
      depth -= 1;
    }
  }

  function primary(): Node {
    const token = peek();
    if (token === undefined) {
      throw new ExprError("expression_syntax", "unexpected end");
    }
    if (token.t === "num") {
      at += 1;
      const value = Number(token.v);
      const unit = peek();
      if (unit?.t === "id" && UNITS[unit.v] !== undefined) {
        at += 1;
        const [factorTo, kind] = UNITS[unit.v] as readonly [number, ExprKind];
        const q = { value: value * factorTo, kind };
        return { n: "num", q, s: token.s, e: unit.e };
      }
      const q: Quantity = { value, kind: "unitless" };
      return { n: "num", q, bareEnd: token.e, s: token.s, e: token.e };
    }
    if (token.t === "id") {
      at += 1;
      return word(token.v, token.s);
    }
    if (token.v === "(") {
      at += 1;
      const node = expr();
      expect(")");
      return { ...node, s: token.s, e: lastEnd() };
    }
    throw new ExprError("expression_syntax", `unexpected '${token.v}'`);
  }

  function word(name: string, s: number): Node {
    const e = lastEnd();
    const calls = isOp("(");
    if (names.has(name) && !calls) return { n: "ref", name, s, e };
    if (FUNCTIONS[name] !== undefined) {
      if (!calls) {
        throw new ExprError(
          "expression_syntax",
          `'${name}' is a function; write ${name}(...)`,
        );
      }
      return call(name, s);
    }
    if (calls) {
      throw new ExprError("expression_syntax", `unknown function '${name}'`);
    }
    if (UNITS[name] !== undefined) {
      throw new ExprError(
        "expression_syntax",
        `unit '${name}' must follow a number, as in 10 ${name}`,
      );
    }
    if (name === "pi") {
      return { n: "num", q: { value: Math.PI, kind: "unitless" }, s, e };
    }
    return { n: "ref", name, s, e };
  }

  function call(name: string, s: number): Node {
    at += 1; // '('
    const args = [expr()];
    while (isOp(",")) {
      at += 1;
      args.push(expr());
    }
    expect(")");
    const [low, high] = FUNCTIONS[name] as readonly [number, number | null];
    if (args.length < low || (high !== null && args.length > high)) {
      const wanted = low === high ? `${low}` : `at least ${low}`;
      throw new ExprError(
        "expression_syntax",
        `${name}() takes ${wanted} argument(s), got ${args.length}`,
      );
    }
    return { n: "call", name, args, s, e: lastEnd() };
  }

  const root = expr();
  const rest = peek();
  if (rest !== undefined) {
    throw new ExprError("expression_syntax", `unexpected '${rest.v}'`);
  }
  return root;
}

const a = (kind: ExprKind): string =>
  kind === "angle" ? "an angle" : `a ${kind}`;

function additive(x: ExprKind, y: ExprKind, what: string): ExprKind {
  if (x === y || y === "unitless") return x;
  if (x === "unitless") return y;
  throw new ExprError("expression_units", `cannot ${what} ${a(x)} and ${a(y)}`);
}

function finite(value: number): number {
  if (!Number.isFinite(value)) {
    throw new ExprError("expression_domain", "the value is not finite");
  }
  return value;
}

const toRadians = (deg: number): number => (deg * Math.PI) / 180;
const toDegrees = (rad: number): number => (rad * 180) / Math.PI;

function degreesIn(fn: string, q: Quantity): number {
  if (q.kind === "length") {
    throw new ExprError(
      "expression_units",
      `${fn}() takes an angle in degrees, not a length`,
    );
  }
  return toRadians(q.value);
}

function unitlessIn(fn: string, q: Quantity): number {
  if (q.kind !== "unitless") {
    throw new ExprError(
      "expression_units",
      `${fn}() takes a plain number, not ${a(q.kind)}`,
    );
  }
  return q.value;
}

/** Half away from zero, as in a spreadsheet (and `expr.py`), not banker's. */
function roundHalfAway(value: number): number {
  const magnitude = Math.abs(value);
  let whole = Math.floor(magnitude);
  if (magnitude - whole >= 0.5) whole += 1;
  return (value < 0 ? -whole : whole) + 0;
}

function applyCall(name: string, args: Quantity[]): Quantity {
  const first = args[0] as Quantity;
  switch (name) {
    case "sin":
    case "cos":
    case "tan": {
      const radians = degreesIn(name, first);
      if (name === "tan" && Math.abs(Math.cos(radians)) < 1e-12) {
        throw new ExprError(
          "expression_domain",
          `tan(${first.value}) is undefined`,
        );
      }
      const fn =
        name === "sin" ? Math.sin : name === "cos" ? Math.cos : Math.tan;
      return { value: fn(radians), kind: "unitless" };
    }
    case "asin":
    case "acos": {
      const x = unitlessIn(name, first);
      if (x < -1 || x > 1) {
        throw new ExprError("expression_domain", `${name}(${x}) is undefined`);
      }
      const fn = name === "asin" ? Math.asin : Math.acos;
      return { value: toDegrees(fn(x)), kind: "angle" };
    }
    case "atan":
      return {
        value: toDegrees(Math.atan(unitlessIn(name, first))),
        kind: "angle",
      };
    case "atan2": {
      const [y, x] = args as [Quantity, Quantity];
      additive(y.kind, x.kind, "compare");
      if (y.value === 0 && x.value === 0) {
        throw new ExprError("expression_domain", "atan2(0, 0) is undefined");
      }
      return { value: toDegrees(Math.atan2(y.value, x.value)), kind: "angle" };
    }
    case "sqrt": {
      const x = unitlessIn(name, first);
      if (x < 0) {
        throw new ExprError(
          "expression_domain",
          `sqrt(${x}) of a negative number`,
        );
      }
      return { value: Math.sqrt(x), kind: "unitless" };
    }
    case "abs":
      return { value: Math.abs(first.value), kind: first.kind };
    case "min":
    case "max": {
      let kind = first.kind;
      for (const arg of args.slice(1))
        kind = additive(kind, arg.kind, "compare");
      const values = args.map((arg) => arg.value);
      return {
        value: name === "min" ? Math.min(...values) : Math.max(...values),
        kind,
      };
    }
    case "round":
      return { value: roundHalfAway(first.value), kind: first.kind };
    case "floor":
      return { value: Math.floor(first.value), kind: first.kind };
    case "ceil":
      return { value: Math.ceil(first.value), kind: first.kind };
    case "rad":
      return { value: degreesIn(name, first), kind: "unitless" };
    default: {
      // deg: radians (a plain number) to an angle.
      if (first.kind !== "unitless") {
        throw new ExprError(
          "expression_units",
          "deg() takes a plain number of radians",
        );
      }
      return { value: toDegrees(first.value), kind: "angle" };
    }
  }
}

function evaluateNode(
  node: Node,
  resolve: (name: string) => Quantity,
): Quantity {
  switch (node.n) {
    case "num":
      return node.q;
    case "ref":
      return resolve(node.name);
    case "neg": {
      const q = evaluateNode(node.operand, resolve);
      return { value: -q.value, kind: q.kind };
    }
    case "call":
      return applyCall(
        node.name,
        node.args.map((arg) => {
          const q = evaluateNode(arg, resolve);
          finite(q.value);
          return q;
        }),
      );
    case "bin": {
      const x = evaluateNode(node.left, resolve);
      const y = evaluateNode(node.right, resolve);
      if (node.op === "+" || node.op === "-") {
        const kind = additive(
          x.kind,
          y.kind,
          node.op === "+" ? "add" : "subtract",
        );
        return {
          value: node.op === "+" ? x.value + y.value : x.value - y.value,
          kind,
        };
      }
      if (node.op === "*") {
        if (x.kind !== "unitless" && y.kind !== "unitless") {
          throw new ExprError(
            "expression_units",
            `cannot multiply ${a(x.kind)} by ${a(y.kind)}`,
          );
        }
        return {
          value: x.value * y.value,
          kind: x.kind === "unitless" ? y.kind : x.kind,
        };
      }
      let kind: ExprKind;
      if (y.kind === "unitless") kind = x.kind;
      else if (x.kind === y.kind) kind = "unitless";
      else {
        throw new ExprError(
          "expression_units",
          `cannot divide ${a(x.kind)} by ${a(y.kind)}`,
        );
      }
      if (y.value === 0)
        throw new ExprError("expression_domain", "division by zero");
      return { value: x.value / y.value, kind };
    }
  }
}

/**
 * Evaluate `text` over `names` (each a typed value). An unknown name is
 * `expression_unknown_name`, carrying the name.
 */
export function evaluateExpression(
  text: string,
  names: ReadonlyMap<string, Quantity>,
): Quantity {
  const root = parse(text, new Set(names.keys()));
  const q = evaluateNode(root, (name) => {
    const found = names.get(name);
    if (found === undefined) {
      throw new ExprError(
        "expression_unknown_name",
        `parameter '${name}' not found`,
        name,
      );
    }
    return found;
  });
  return { value: finite(q.value), kind: q.kind };
}

/**
 * A whole number, a hyphen and a simple fraction with no spaces (or lopsided
 * ones) round the hyphen: `11-15/32`, `11 -15/32`. Spaced evenly (`11 - 15/32`)
 * it is subtraction and is not matched.
 */
const MIXED_HYPHEN_RE = /(?<![\w.])(\d+)(\s*)-(\s*)(\d+)\/(\d+)(?![\w.])/g;

/**
 * Why a length FORMULA typed now is ambiguous, or null (RESEARCH §29).
 *
 * A framer's `11-15/32` means eleven and fifteen thirty-seconds; the grammar
 * reads it as 11 − 15/32. A whole entry in that form never gets here (it is a
 * length, `parseLength`); inside a larger formula (`2*11-15/32`), or with a
 * space on one side only (`11 -15/32`), either reading is plausible, so the
 * field refuses it rather than guess. Applied only to text typed in this
 * session: a stored formula keeps the meaning the server gave it.
 */
export function mixedNumberAmbiguity(
  expression: string,
  unit: LengthUnit,
): string | null {
  for (const match of expression.matchAll(MIXED_HYPHEN_RE)) {
    const [, whole, before, after, num, den] = match;
    if (before !== "" && after !== "") continue;
    const mixed = lengthExpression(`${whole} ${num}/${den}`, unit);
    return (
      `'${match[0].trim()}' could be ${whole} ${num}/${den} or ${whole} minus ` +
      `${num}/${den}: type ${whole} - ${num}/${den} to subtract, or ` +
      `${mixed ?? `${whole} ${num}/${den}`} for the mixed number`
    );
  }
  return null;
}

/**
 * A length field's typed text as the expression to evaluate and send: a
 * carpenter-notation entry spelled out with explicit units (`11-15/32` →
 * `11 mm + 15 mm/32` in `unit`), any other text as typed. A hyphenated mixed
 * number inside a formula reads two ways and is an {@link ExprError}.
 */
export function lengthEntryExpression(text: string, unit: LengthUnit): string {
  const trimmed = text.trim();
  if (isCarpenterLength(trimmed, unit)) {
    const spelled = lengthExpression(trimmed, unit);
    if (spelled !== null) return spelled;
  }
  const why = mixedNumberAmbiguity(trimmed, unit);
  if (why !== null) throw new ExprError("expression_syntax", why);
  return trimmed;
}

/** What a field holds: mm, degrees, a plain number, or a whole number. */
export type FieldKind = "length" | "angle" | "unitless" | "int";

const NOUN: Record<ExprKind, string> = {
  length: "a length",
  angle: "an angle",
  unitless: "a plain number",
};

/**
 * The value of `q` for a field of `kind`, as the server coerces it: unitless
 * fits a length or an angle; an int field takes a unitless value within 1e-9
 * of a whole number.
 */
export function coerceToField(q: Quantity, kind: FieldKind): number {
  const target: ExprKind = kind === "int" ? "unitless" : kind;
  if (q.kind !== target && q.kind !== "unitless") {
    throw new ExprError(
      "expression_units",
      `this is ${NOUN[q.kind]}; the field needs ${NOUN[target]}`,
    );
  }
  if (kind !== "int") return q.value;
  const nearest = Math.round(q.value);
  if (Math.abs(q.value - nearest) > 1e-9) {
    throw new ExprError("expression_domain", "this field needs a whole number");
  }
  return nearest;
}

// --- bare numbers in a non-mm part (FORMULA-BARE-UNIT) --------------------------

const COMPARING = new Set(["min", "max", "atan2"]);
const PASSING = new Set(["abs", "round", "floor", "ceil"]);
const TRIG_IN = new Set(["sin", "cos", "tan", "rad"]);
const PLAIN_IN = new Set(["asin", "acos", "atan", "sqrt", "deg"]);

function staticCallKind(name: string, args: ExprKind[]): ExprKind {
  const first = args[0] as ExprKind;
  const refuse = () => new ExprError("expression_units", `${name}()`);
  if (TRIG_IN.has(name)) {
    if (first === "length") throw refuse();
    return "unitless";
  }
  if (PLAIN_IN.has(name)) {
    if (first !== "unitless") throw refuse();
    return name === "sqrt" ? "unitless" : "angle";
  }
  if (COMPARING.has(name)) {
    const kind = args
      .slice(1)
      .reduce((k, arg) => additive(k, arg, "compare"), first);
    return name === "atan2" ? "angle" : kind;
  }
  return first;
}

/** The kind `node` evaluates to from its names' kinds alone (`expr.py`). */
function staticKind(
  node: Node,
  kinds: ReadonlyMap<string, ExprKind>,
  into: Map<Node, ExprKind>,
): ExprKind {
  let kind: ExprKind;
  switch (node.n) {
    case "num":
      kind = node.q.kind;
      break;
    case "ref": {
      const found = kinds.get(node.name);
      if (found === undefined) {
        throw new ExprError("expression_unknown_name", node.name, node.name);
      }
      kind = found;
      break;
    }
    case "neg":
      kind = staticKind(node.operand, kinds, into);
      break;
    case "bin": {
      const x = staticKind(node.left, kinds, into);
      const y = staticKind(node.right, kinds, into);
      if (node.op === "+" || node.op === "-") kind = additive(x, y, "add");
      else if (node.op === "*") {
        if (x !== "unitless" && y !== "unitless") {
          throw new ExprError("expression_units", "two factors carry a unit");
        }
        kind = x === "unitless" ? y : x;
      } else if (y === "unitless") kind = x;
      else if (x === y) kind = "unitless";
      else throw new ExprError("expression_units", "cannot divide");
      break;
    }
    case "call":
      kind = staticCallKind(
        node.name,
        node.args.map((arg) => staticKind(arg, kinds, into)),
      );
      break;
  }
  into.set(node, kind);
  return kind;
}

function bareTerms(
  node: Node,
  kinds: ReadonlyMap<Node, ExprKind>,
  wantsLength: boolean,
  out: Node[],
): void {
  const kind = kinds.get(node);
  if (wantsLength && kind === "unitless") out.push(node);
  if (node.n === "neg") {
    bareTerms(node.operand, kinds, wantsLength && kind !== "unitless", out);
  } else if (node.n === "bin") {
    const sum = (node.op === "+" || node.op === "-") && kind === "length";
    bareTerms(node.left, kinds, sum, out);
    bareTerms(node.right, kinds, sum, out);
  } else if (node.n === "call") {
    const compared = COMPARING.has(node.name)
      ? node.args.some((arg) => kinds.get(arg) === "length")
      : PASSING.has(node.name) && wantsLength && kind !== "unitless";
    for (const arg of node.args) bareTerms(arg, kinds, compared, out);
  }
}

function unitInsertions(
  node: Node,
  kinds: ReadonlyMap<Node, ExprKind>,
  unit: string,
  out: [number, string][],
): void {
  if (node.n === "num" && node.bareEnd !== undefined) {
    out.push([node.bareEnd, ` ${unit}`]);
  } else if (node.n === "neg") {
    unitInsertions(node.operand, kinds, unit, out);
  } else if (node.n === "bin" && (node.op === "+" || node.op === "-")) {
    unitInsertions(node.left, kinds, unit, out);
    unitInsertions(node.right, kinds, unit, out);
  } else if (node.n === "bin" && kinds.get(node.left) === "unitless") {
    unitInsertions(node.left, kinds, unit, out);
  } else {
    out.push([node.e, `*1 ${unit}`]);
  }
}

/** The bare terms of a formula, and the formula with the unit written in. */
export interface BareLengths {
  /** Each whole unitless term as written (`1/2` in `wall + 1/2`). */
  literals: string[];
  /** `wall + 1 in/2`. */
  text: string;
}

/** `kinds` of `text`'s tree, or null when it does not parse or type. */
function typedTree(
  text: string,
  kinds: ReadonlyMap<string, ExprKind>,
): { root: Node; nodeKinds: Map<Node, ExprKind> } | null {
  const nodeKinds = new Map<Node, ExprKind>();
  try {
    const root = parse(text, new Set(kinds.keys()));
    staticKind(root, kinds, nodeKinds);
    return { root, nodeKinds };
  } catch (error) {
    if (error instanceof ExprError) return null;
    throw error;
  }
}

/**
 * The server's rule (`bare_lengths` in `loft_wire/expr.py`): in a part whose
 * unit is not mm, a whole unitless term added to, subtracted from or
 * compared with a length, or a length field's whole value, reads in the
 * part's unit. Documents writes the unit into a formula a save enters, so
 * the field echoes what the save will store. Null when nothing changes.
 */
export function bareLengths(
  text: string,
  unit: string,
  field: ExprKind,
  kinds: ReadonlyMap<string, ExprKind>,
): BareLengths | null {
  if (unit === "mm" || UNITS[unit]?.[1] !== "length") return null;
  const fits = (kind: ExprKind | undefined) =>
    kind === field || kind === "unitless";
  const tree = typedTree(text, kinds);
  if (tree === null || !fits(tree.nodeKinds.get(tree.root))) return null;
  const terms: Node[] = [];
  bareTerms(tree.root, tree.nodeKinds, field === "length", terms);
  if (terms.length === 0) return null;
  const inserts: [number, string][] = [];
  for (const term of terms) unitInsertions(term, tree.nodeKinds, unit, inserts);
  inserts.sort((x, y) => y[0] - x[0]);
  let fixed = text;
  for (const [at, piece] of inserts) {
    fixed = fixed.slice(0, at) + piece + fixed.slice(at);
  }
  const checked = typedTree(fixed, kinds);
  if (checked === null || !fits(checked.nodeKinds.get(checked.root))) {
    return null;
  }
  return { literals: terms.map((t) => text.slice(t.s, t.e)), text: fixed };
}
