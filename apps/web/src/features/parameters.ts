/**
 * The Parameters panel's table state (PART-PARAMETERS, docs/RESEARCH.md §20),
 * pure so every rule is unit-tested without a browser.
 *
 * The panel edits a WORKING copy of the server's table. A committed cell (Enter
 * or blur) changes one row of it; the whole working table is then sent as one
 * PUT, which is one undo step. What can go wrong is answered on the row, and
 * the user's text is never dropped:
 *
 *  - the server refuses the table (422): the working rows stay as typed and the
 *    error is mapped onto the row it blames ({@link mapTableError});
 *  - the table moved underneath (stale version, undo, another window): the
 *    fresh table is taken and the user's unsaved edits are re-applied on top of
 *    it, field by field ({@link rebaseRows}) — a three-way merge, so a change
 *    nobody made locally always takes the server's word.
 *
 * Two rules belong to the client rather than the server:
 *
 *  - THE UNIT-APPEND RULE. The expression language reads a bare number in a
 *    length row as mm, because mm is the kernel's unit. A user in an inch
 *    document who types `2` means two inches, so a bare number TYPED in this
 *    session is sent with the document unit (`2 in`) — Fusion's rule. Only a
 *    typed cell: a stored `40` in a document that was mm when it was written
 *    keeps meaning 40 mm, so it is re-sent untouched.
 *  - THE KIND. The wire makes the client declare each row's kind (length,
 *    angle or unitless). The row keeps the kind it has (a new row is a length,
 *    the document's unit, as in Fusion) unless the expression it is given says
 *    otherwise: `30 deg`, `atan(...)` or `W * 2` over a length `W` decide it
 *    ({@link inferKind}). Unitless joins either kind, so a ratio or a count is
 *    chosen from the row's Unit cell.
 */
import { formatAngle, formatLength, type LengthUnit } from "@loft/design";

import type {
  ParameterTableError,
  ParameterUnit,
  PartParameter,
  PartParameterInput,
} from "../api/parameters";

/** One row of the working table. */
export interface DraftRow {
  /** Stable identity; a rename keeps it. Minted here for a new row. */
  id: string;
  name: string;
  /** The expression as the user sees it: as typed, or as stored. */
  expression: string;
  comment: string;
  unit: ParameterUnit;
  /** The server's value for the stored row; null for a row never stored. */
  value: number | null;
  /**
   * The document unit a bare number typed in THIS session is read in, or null
   * for an expression the server already stored (sent exactly as it reads).
   */
  bareUnit: LengthUnit | null;
}

/** An editable cell. */
export type ParameterField = "name" | "expression" | "comment";

/** A refusal, placed on the row it is about. */
export interface RowError {
  /** The row it blames, or null when it is about the whole table. */
  rowId: string | null;
  /** The cell that carries it on that row. */
  field: "name" | "expression";
  /** One sentence, ready to show. */
  message: string;
  /** The stable server code, or `local_*` for a check made before sending. */
  code: string;
}

/** Most parameters a part may define (RESEARCH §20, `MAX_PARAMETERS`). */
export const MAX_PARAMETERS = 200;

/** Expression unit words, as the grammar spells them (`loft_wire/expr.py`). */
const UNIT_KINDS: Readonly<Record<string, ParameterUnit>> = {
  mm: "length",
  cm: "length",
  m: "length",
  in: "length",
  ft: "length",
  deg: "angle",
  rad: "angle",
};

/** The stored table, as working rows. */
export function rowsFromServer(rows: readonly PartParameter[]): DraftRow[] {
  return rows.map((row) => ({
    id: row.id,
    name: row.name,
    expression: row.expression,
    comment: row.comment,
    unit: row.unit,
    value: row.value,
    bareUnit: null,
  }));
}

/**
 * A fresh RFC 4122 v4 id. `crypto.randomUUID` exists only in a secure
 * context, and a self-hosted Loft on a LAN address over plain HTTP is not one;
 * `getRandomValues` is available everywhere.
 */
export function newParameterId(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x40;
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0"));
  return [
    hex.slice(0, 4).join(""),
    hex.slice(4, 6).join(""),
    hex.slice(6, 8).join(""),
    hex.slice(8, 10).join(""),
    hex.slice(10, 16).join(""),
  ].join("-");
}

/** An empty row, appended by Add. A length, like a new Fusion parameter. */
export function blankRow(id: string = newParameterId()): DraftRow {
  return {
    id,
    name: "",
    expression: "",
    comment: "",
    unit: "length",
    value: null,
    bareUnit: null,
  };
}

/** `2`, `-0.5`, `.25`: a plain number, no unit and no formula. */
export function isBareNumber(text: string): boolean {
  return /^\s*[+-]?(\d+(\.\d*)?|\.\d+)\s*$/.test(text);
}

/**
 * The expression to SEND for a row: a bare number typed this session in a
 * length row of a non-mm document gets the document unit (`2` → `2 in`).
 */
export function wireExpression(row: DraftRow): string {
  const text = row.expression.trim();
  if (
    row.unit === "length" &&
    row.bareUnit !== null &&
    row.bareUnit !== "mm" &&
    isBareNumber(text)
  ) {
    return `${text} ${row.bareUnit}`;
  }
  return text;
}

// --- kind inference ------------------------------------------------------------

type Token = { t: "num" } | { t: "id"; v: string } | { t: "op"; v: string };

function tokenize(text: string): Token[] | null {
  const tokens: Token[] = [];
  const re =
    /\s*(?:(\d+(?:\.\d*)?|\.\d+)|([A-Za-z_][A-Za-z0-9_]*)|([-+*/(),]))/y;
  let at = 0;
  while (at < text.length) {
    if (/^\s*$/.test(text.slice(at))) break;
    re.lastIndex = at;
    const match = re.exec(text);
    if (match === null) return null;
    at = re.lastIndex;
    if (match[1] !== undefined) tokens.push({ t: "num" });
    else if (match[2] !== undefined) tokens.push({ t: "id", v: match[2] });
    else tokens.push({ t: "op", v: match[3] as string });
  }
  return tokens;
}

/** `null` = the expression mixes kinds or does not parse. */
type Kind = ParameterUnit | null;

function joinKinds(a: Kind, b: Kind): Kind {
  if (a === null || b === null) return null;
  if (a === b || b === "unitless") return a;
  if (a === "unitless") return b;
  return null;
}

/**
 * What an expression measures, read the way the server's grammar reads it, or
 * null when it does not parse or mixes kinds (the server will say why).
 * `kinds` maps the OTHER parameters' names to their kinds.
 */
export function inferKind(
  expression: string,
  kinds: ReadonlyMap<string, ParameterUnit>,
): Kind {
  const tokens = tokenize(expression);
  if (tokens === null || tokens.length === 0) return null;
  let at = 0;
  const peek = (): Token | undefined => tokens[at];
  const isOp = (v: string): boolean => {
    const token = peek();
    return token?.t === "op" && token.v === v;
  };

  function sum(): Kind {
    let kind = product();
    while (isOp("+") || isOp("-")) {
      at += 1;
      kind = joinKinds(kind, product());
    }
    return kind;
  }

  function product(): Kind {
    let kind = unary();
    while (isOp("*") || isOp("/")) {
      const divide = (peek() as { v: string }).v === "/";
      at += 1;
      const right = unary();
      if (kind === null || right === null) return null;
      if (right === "unitless") continue;
      if (divide) kind = kind === right ? "unitless" : null;
      else kind = kind === "unitless" ? right : null;
    }
    return kind;
  }

  function unary(): Kind {
    if (isOp("+") || isOp("-")) {
      at += 1;
      return unary();
    }
    return atom();
  }

  function args(): Kind[] | null {
    if (!isOp("(")) return null;
    at += 1;
    const out: Kind[] = [sum()];
    while (isOp(",")) {
      at += 1;
      out.push(sum());
    }
    if (!isOp(")")) return null;
    at += 1;
    return out;
  }

  function call(name: string): Kind {
    const list = args();
    if (list === null || list.includes(null)) return null;
    const first = list[0] as ParameterUnit;
    switch (name) {
      case "sin":
      case "cos":
      case "tan":
      case "rad":
        return "unitless";
      case "asin":
      case "acos":
      case "atan":
      case "atan2":
      case "deg":
        return "angle";
      case "sqrt":
        return first === "unitless" ? "unitless" : null;
      case "min":
      case "max":
        return list.reduce<Kind>((acc, k) => joinKinds(acc, k), "unitless");
      default:
        // abs, round, floor, ceil keep their argument's kind.
        return first;
    }
  }

  function atom(): Kind {
    const token = peek();
    if (token === undefined) return null;
    at += 1;
    if (token.t === "num") {
      const next = peek();
      if (next?.t === "id" && UNIT_KINDS[next.v] !== undefined) {
        at += 1;
        return UNIT_KINDS[next.v] as ParameterUnit;
      }
      return "unitless";
    }
    if (token.t === "id") {
      if (isOp("(")) return call(token.v);
      if (token.v === "pi") return "unitless";
      return kinds.get(token.v) ?? "unitless";
    }
    if (token.v === "(") {
      const kind = sum();
      if (!isOp(")")) return null;
      at += 1;
      return kind;
    }
    return null;
  }

  const kind = sum();
  return at === tokens.length ? kind : null;
}

/** The kinds of every row but `exceptId`, by name, for {@link inferKind}. */
function kindsByName(
  rows: readonly DraftRow[],
  exceptId: string,
): Map<string, ParameterUnit> {
  const kinds = new Map<string, ParameterUnit>();
  for (const row of rows) {
    if (row.id !== exceptId && row.name !== "") kinds.set(row.name, row.unit);
  }
  return kinds;
}

// --- edits -------------------------------------------------------------------

/**
 * Commit one cell's text into the working table. An expression is trimmed,
 * remembers the document unit a bare number is read in, and may set the row's
 * kind when it states one.
 */
export function commitCell(
  rows: readonly DraftRow[],
  id: string,
  field: ParameterField,
  text: string,
  documentUnit: LengthUnit,
): DraftRow[] {
  return rows.map((row) => {
    if (row.id !== id) return row;
    if (field === "comment") return { ...row, comment: text };
    if (field === "name") return { ...row, name: text.trim() };
    const expression = text.trim();
    // Unchanged text keeps how it was read: re-committing a stored `40` in an
    // inch document must not start reading it as inches.
    if (expression === row.expression) return row;
    const inferred = inferKind(expression, kindsByName(rows, id));
    return {
      ...row,
      expression,
      bareUnit: documentUnit,
      unit: inferred === "length" || inferred === "angle" ? inferred : row.unit,
    };
  });
}

/** Set a row's kind from its Unit cell. */
export function setRowUnit(
  rows: readonly DraftRow[],
  id: string,
  unit: ParameterUnit,
): DraftRow[] {
  return rows.map((row) => (row.id === id ? { ...row, unit } : row));
}

export function deleteRow(rows: readonly DraftRow[], id: string): DraftRow[] {
  return rows.filter((row) => row.id !== id);
}

/**
 * Put back a STORED row the user deleted, when the server refused the table
 * over it (a parameter still in use): a refusal about a row that is no longer
 * on screen would have nothing to sit on. Back at its stored position.
 */
export function restoreDeletedRow(
  rows: readonly DraftRow[],
  base: readonly DraftRow[],
  name: string | null,
): DraftRow[] {
  if (name === null || rows.some((row) => row.name === name)) return [...rows];
  const index = base.findIndex((row) => row.name === name);
  const stored = base[index];
  if (stored === undefined || rows.some((row) => row.id === stored.id)) {
    return [...rows];
  }
  const out = [...rows];
  out.splice(Math.min(index, out.length), 0, stored);
  return out;
}

/** A row nobody has stored, still missing its name or its expression. */
export function isIncompleteDraft(
  row: DraftRow,
  stored: ReadonlySet<string>,
): boolean {
  return !stored.has(row.id) && (row.name === "" || row.expression === "");
}

/**
 * The PUT body for the working table, or the first local refusal.
 *
 * A new row still missing its name or expression is a draft and is NOT sent
 * (it stays on screen, waiting); a STORED row emptied of either is refused
 * here, on the row, because the server could only reject it less helpfully.
 */
export function tableToWire(
  rows: readonly DraftRow[],
  base: readonly DraftRow[],
): { body: PartParameterInput[] } | { error: RowError } {
  const stored = new Set(base.map((row) => row.id));
  const body: PartParameterInput[] = [];
  for (const row of rows) {
    if (isIncompleteDraft(row, stored)) continue;
    if (row.name === "") {
      return {
        error: {
          rowId: row.id,
          field: "name",
          message: "Give the parameter a name.",
          code: "local_name_empty",
        },
      };
    }
    if (row.expression === "") {
      return {
        error: {
          rowId: row.id,
          field: "expression",
          message: "Enter a value or a formula.",
          code: "local_expression_empty",
        },
      };
    }
    body.push({
      id: row.id,
      name: row.name,
      expression: wireExpression(row),
      unit: row.unit,
      comment: row.comment,
    });
  }
  if (body.length > MAX_PARAMETERS) {
    return {
      error: {
        rowId: null,
        field: "expression",
        message: `A part may define at most ${MAX_PARAMETERS} parameters.`,
        code: "local_too_many",
      },
    };
  }
  return { body };
}

/** Whether `body` would change nothing about the stored `base`. */
export function sameAsStored(
  body: readonly PartParameterInput[],
  base: readonly DraftRow[],
): boolean {
  if (body.length !== base.length) return false;
  return body.every((row, index) => {
    const stored = base[index] as DraftRow;
    return (
      row.id === stored.id &&
      row.name === stored.name &&
      row.expression === stored.expression &&
      row.unit === stored.unit &&
      row.comment === stored.comment
    );
  });
}

/** Whether a stored row's expression or kind has an unsaved change. */
export function valuePending(
  row: DraftRow,
  base: ReadonlyMap<string, DraftRow>,
): boolean {
  const stored = base.get(row.id);
  return (
    stored === undefined ||
    wireExpression(row) !== stored.expression ||
    row.unit !== stored.unit
  );
}

/**
 * Re-apply the user's unsaved edits (`mine`, made against `base`) on top of a
 * newer table (`theirs`). Field by field: what the user changed wins, what
 * they did not takes the newer table's word. A row the user deleted stays
 * deleted, a row they added is kept at the end, and a row the newer table
 * dropped is dropped unless the user had added it.
 */
export function rebaseRows(
  base: readonly DraftRow[],
  mine: readonly DraftRow[],
  theirs: readonly DraftRow[],
): DraftRow[] {
  const baseById = new Map(base.map((row) => [row.id, row]));
  const mineById = new Map(mine.map((row) => [row.id, row]));
  const theirIds = new Set(theirs.map((row) => row.id));
  const out: DraftRow[] = [];
  for (const their of theirs) {
    const was = baseById.get(their.id);
    const now = mineById.get(their.id);
    if (was !== undefined && now === undefined) continue;
    if (was === undefined || now === undefined) {
      out.push(now ?? their);
      continue;
    }
    const typed =
      now.expression !== was.expression || now.bareUnit !== was.bareUnit;
    out.push({
      id: their.id,
      name: now.name !== was.name ? now.name : their.name,
      comment: now.comment !== was.comment ? now.comment : their.comment,
      unit: now.unit !== was.unit ? now.unit : their.unit,
      expression: typed ? now.expression : their.expression,
      bareUnit: typed ? now.bareUnit : their.bareUnit,
      value: their.value,
    });
  }
  for (const row of mine) {
    if (!baseById.has(row.id) && !theirIds.has(row.id)) out.push(row);
  }
  return out;
}

// --- errors ------------------------------------------------------------------

/** `a → b → a`, the loop as the panel prints it. */
export function formatChain(chain: readonly string[]): string {
  return chain.join(" → ");
}

/** The server's sentence without the "Parameter 'W': " lead the row makes redundant. */
function rowSentence(message: string): string {
  const bare = message.replace(/^\s*parameter\s+'[^']*'\s*:?\s*/i, "");
  const text = bare === "" ? message : bare;
  const sentence = text.charAt(0).toUpperCase() + text.slice(1);
  return /[.!?]$/.test(sentence) ? sentence : `${sentence}.`;
}

/** Map the server's refusal onto the working row it blames. */
export function mapTableError(
  error: Pick<ParameterTableError, "code" | "parameter" | "chain" | "message">,
  rows: readonly DraftRow[],
): RowError {
  const named =
    error.parameter ??
    /parameter\s+'([^']+)'/i.exec(error.message)?.[1] ??
    null;
  const nameFault =
    error.code === "expression_name_invalid" ||
    error.code === "parameter_id_duplicate";
  const matches = rows.filter((row) => named !== null && row.name === named);
  // A repeated name is the SECOND definition's fault: the first one stood.
  const row = nameFault ? matches[matches.length - 1] : matches[0];
  const message =
    error.code === "expression_cycle" && error.chain.length > 0
      ? `Circular reference: ${formatChain(error.chain)}.`
      : rowSentence(error.message);
  return {
    rowId: row?.id ?? null,
    field: nameFault ? "name" : "expression",
    message,
    code: error.code,
  };
}

// --- display -----------------------------------------------------------------

/** The Value column: lengths in the document unit, angles in degrees. */
export function formatParameterValue(
  value: number | null,
  unit: ParameterUnit,
  documentUnit: LengthUnit,
): string {
  if (value === null) return "—";
  if (unit === "length") return formatLength(value, documentUnit);
  if (unit === "angle") return formatAngle(value);
  return formatAngle(value, { unitSuffix: false });
}

/** The Unit cell's choices: the document unit, degrees, or none. */
export function unitOptions(
  documentUnit: LengthUnit,
): { value: ParameterUnit; label: string }[] {
  return [
    { value: "length", label: documentUnit },
    { value: "angle", label: "deg" },
    { value: "unitless", label: "none" },
  ];
}
