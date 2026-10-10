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

type Token =
  { t: "num"; v: string } | { t: "id"; v: string } | { t: "op"; v: string };

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
    if (match[1] !== undefined) tokens.push({ t: "num", v: match[1] });
    else if (match[2] !== undefined) tokens.push({ t: "id", v: match[2] });
    else tokens.push({ t: "op", v: match[3] as string });
  }
  return tokens;
}

type Node =
  | { n: "num"; q: Quantity }
  | { n: "ref"; name: string }
  | { n: "neg"; operand: Node }
  | { n: "bin"; op: string; left: Node; right: Node }
  | { n: "call"; name: string; args: Node[] };

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
      node = { n: "bin", op, left: node, right: term() };
    }
    return node;
  }

  function term(): Node {
    let node = factor();
    while (isOp("*") || isOp("/")) {
      const op = (tokens[at] as Token).v;
      at += 1;
      node = { n: "bin", op, left: node, right: factor() };
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
        const op = (tokens[at] as Token).v;
        at += 1;
        const operand = factor();
        return op === "-" ? { n: "neg", operand } : operand;
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
        return { n: "num", q: { value: value * factorTo, kind } };
      }
      return { n: "num", q: { value, kind: "unitless" } };
    }
    if (token.t === "id") {
      at += 1;
      return word(token.v);
    }
    if (token.v === "(") {
      at += 1;
      const node = expr();
      expect(")");
      return node;
    }
    throw new ExprError("expression_syntax", `unexpected '${token.v}'`);
  }

  function word(name: string): Node {
    const calls = isOp("(");
    if (names.has(name) && !calls) return { n: "ref", name };
    if (FUNCTIONS[name] !== undefined) {
      if (!calls) {
        throw new ExprError(
          "expression_syntax",
          `'${name}' is a function; write ${name}(...)`,
        );
      }
      return call(name);
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
    if (name === "pi")
      return { n: "num", q: { value: Math.PI, kind: "unitless" } };
    return { n: "ref", name };
  }

  function call(name: string): Node {
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
    return { n: "call", name, args };
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
