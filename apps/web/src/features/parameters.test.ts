import { describe, expect, it } from "vitest";

import type { PartParameter } from "../api/parameters";
import {
  blankRow,
  commitCell,
  type DraftRow,
  deleteRow,
  formatChain,
  formatParameterValue,
  inferKind,
  isBareNumber,
  mapTableError,
  newParameterId,
  rebaseRows,
  restoreDeletedRow,
  rowsFromServer,
  sameAsStored,
  setRowUnit,
  tableToWire,
  valuePending,
  wireExpression,
} from "./parameters";

const W_ID = "00000000-0000-4000-8000-000000000001";
const H_ID = "00000000-0000-4000-8000-000000000002";

function stored(
  id: string,
  name: string,
  expression: string,
  value: number,
  unit: PartParameter["unit"] = "length",
): PartParameter {
  return { id, name, expression, unit, value, comment: "" };
}

const BASE = rowsFromServer([
  stored(W_ID, "W", "40", 40),
  stored(H_ID, "H", "W - 15", 25),
]);

function wire(rows: readonly DraftRow[], base: readonly DraftRow[] = BASE) {
  const result = tableToWire(rows, base);
  if ("error" in result) throw new Error(result.error.message);
  return result.body;
}

describe("the unit-append rule", () => {
  it("recognises a bare number and nothing else", () => {
    for (const text of ["2", " 2 ", "-0.5", "+3.", ".25"]) {
      expect(isBareNumber(text)).toBe(true);
    }
    for (const text of ["2 in", "2in", "W", "2*3", "", "1e3", "pi"]) {
      expect(isBareNumber(text)).toBe(false);
    }
  });

  it("sends a typed bare number in an inch document as inches", () => {
    const rows = commitCell(BASE, W_ID, "expression", "2", "in");
    expect(rows[0]?.expression).toBe("2");
    expect(wireExpression(rows[0] as DraftRow)).toBe("2 in");
    expect(wire(rows)[0]?.expression).toBe("2 in");
  });

  it("leaves a bare number alone in a mm document", () => {
    const rows = commitCell(BASE, W_ID, "expression", "2", "mm");
    expect(wire(rows)[0]?.expression).toBe("2");
  });

  it("never appends to a formula, a unit-carrying number, or a non-length row", () => {
    let rows = commitCell(BASE, H_ID, "expression", "W / 2", "in");
    expect(wire(rows)[1]?.expression).toBe("W / 2");
    rows = commitCell(BASE, W_ID, "expression", "25.4 mm", "in");
    expect(wire(rows)[0]?.expression).toBe("25.4 mm");
    rows = setRowUnit(
      commitCell(BASE, W_ID, "expression", "6", "in"),
      W_ID,
      "unitless",
    );
    expect(wire(rows)[0]?.expression).toBe("6");
  });

  it("re-sends a STORED bare number untouched (it was written in mm)", () => {
    const rows = commitCell(BASE, H_ID, "comment", "height", "in");
    expect(wire(rows)[0]?.expression).toBe("40");
    // Re-committing the same text is not a new entry either.
    const again = commitCell(BASE, W_ID, "expression", " 40 ", "in");
    expect(again[0]).toBe(BASE[0]);
  });
});

describe("kind inference", () => {
  const kinds = new Map<string, PartParameter["unit"]>([
    ["W", "length"],
    ["A", "angle"],
    ["N", "unitless"],
  ]);

  it("reads a kind from units, references and functions", () => {
    expect(inferKind("40", kinds)).toBe("unitless");
    expect(inferKind("2 in", kinds)).toBe("length");
    expect(inferKind("2in + 3", kinds)).toBe("length");
    expect(inferKind("30 deg", kinds)).toBe("angle");
    expect(inferKind("W - 15", kinds)).toBe("length");
    expect(inferKind("W * N", kinds)).toBe("length");
    expect(inferKind("W / W", kinds)).toBe("unitless");
    expect(inferKind("A / 2", kinds)).toBe("angle");
    expect(inferKind("atan2(1, 2)", kinds)).toBe("angle");
    expect(inferKind("sin(A) * W", kinds)).toBe("length");
    expect(inferKind("max(W, 3 mm)", kinds)).toBe("length");
    expect(inferKind("-(W + 1)", kinds)).toBe("length");
    expect(inferKind("deg(pi / 2)", kinds)).toBe("angle");
  });

  it("answers null for a clash or a parse failure", () => {
    expect(inferKind("W + A", kinds)).toBeNull();
    expect(inferKind("W * W", kinds)).toBeNull();
    expect(inferKind("2 / W", kinds)).toBeNull();
    expect(inferKind("(W", kinds)).toBeNull();
    expect(inferKind("W $ 2", kinds)).toBeNull();
    expect(inferKind("", kinds)).toBeNull();
  });

  it("sets the row's kind only when the expression states one", () => {
    let rows = commitCell(BASE, W_ID, "expression", "30 deg", "mm");
    expect(rows[0]?.unit).toBe("angle");
    rows = setRowUnit(BASE, W_ID, "unitless");
    rows = commitCell(rows, W_ID, "expression", "6", "mm");
    expect(rows[0]?.unit).toBe("unitless");
  });
});

describe("table state", () => {
  it("adds, deletes and sends nothing for an unchanged table", () => {
    expect(sameAsStored(wire(BASE), BASE)).toBe(true);
    const added = [...BASE, blankRow("00000000-0000-4000-8000-000000000003")];
    // A blank new row is a draft: not sent, and the table is still unchanged.
    expect(sameAsStored(wire(added), BASE)).toBe(true);
    const named = commitCell(added, added[2]!.id, "name", " D ", "mm");
    const filled = commitCell(named, added[2]!.id, "expression", "5", "mm");
    expect(wire(filled).map((row) => row.name)).toEqual(["W", "H", "D"]);
    expect(sameAsStored(wire(deleteRow(BASE, H_ID)), BASE)).toBe(false);
  });

  it("refuses a stored row emptied of its name or expression, on that row", () => {
    const rows = commitCell(BASE, H_ID, "expression", "  ", "mm");
    const result = tableToWire(rows, BASE);
    expect(result).toEqual({
      error: expect.objectContaining({ rowId: H_ID, field: "expression" }),
    });
    const unnamed = commitCell(BASE, W_ID, "name", "", "mm");
    expect(tableToWire(unnamed, BASE)).toEqual({
      error: expect.objectContaining({ rowId: W_ID, field: "name" }),
    });
  });

  it("marks a value pending until the server has evaluated the new text", () => {
    const byId = new Map(BASE.map((row) => [row.id, row]));
    expect(valuePending(BASE[0]!, byId)).toBe(false);
    const rows = commitCell(BASE, W_ID, "expression", "50", "mm");
    expect(valuePending(rows[0]!, byId)).toBe(true);
    expect(
      valuePending(commitCell(BASE, W_ID, "comment", "x", "mm")[0]!, byId),
    ).toBe(false);
  });

  it("mints RFC 4122 v4 ids", () => {
    const id = newParameterId();
    expect(id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
    expect(newParameterId()).not.toBe(id);
  });
});

describe("rebasing unsaved edits onto a newer table", () => {
  const THEIRS = rowsFromServer([
    stored(W_ID, "W", "60", 60),
    stored(H_ID, "H", "W - 15", 45),
  ]);

  it("takes the newer table where the user changed nothing", () => {
    expect(rebaseRows(BASE, BASE, THEIRS)).toEqual(THEIRS);
  });

  it("keeps what the user typed, field by field, on top", () => {
    const mine = commitCell(BASE, H_ID, "expression", "W - 20", "in");
    const rows = rebaseRows(BASE, mine, THEIRS);
    expect(rows[0]).toEqual(THEIRS[0]);
    expect(rows[1]).toMatchObject({
      expression: "W - 20",
      bareUnit: "in",
      value: 45,
    });
  });

  it("keeps a deleted row deleted and an added row added", () => {
    const extra = {
      ...blankRow("00000000-0000-4000-8000-000000000009"),
      name: "T",
    };
    const mine = [...deleteRow(BASE, W_ID), extra];
    const rows = rebaseRows(BASE, mine, THEIRS);
    expect(rows.map((row) => row.name)).toEqual(["H", "T"]);
  });

  it("takes a stored normalisation once the typed text was sent", () => {
    const sent = commitCell(BASE, W_ID, "expression", "2", "in");
    const response = rowsFromServer([
      stored(W_ID, "W", "2 in", 50.8),
      stored(H_ID, "H", "W - 15", 35.8),
    ]);
    const rows = rebaseRows(sent, sent, response);
    expect(rows[0]).toMatchObject({ expression: "2 in", bareUnit: null });
  });
});

describe("error mapping", () => {
  const ROWS = rowsFromServer([
    stored(W_ID, "a", "b + 1", 1),
    stored(H_ID, "b", "a + 1", 1),
  ]);

  it("puts back a deleted row the server refused to let go, where it was", () => {
    const rows = restoreDeletedRow(deleteRow(BASE, W_ID), BASE, "W");
    expect(rows.map((row) => row.name)).toEqual(["W", "H"]);
    const error = mapTableError(
      {
        code: "parameter_in_use",
        parameter: "W",
        chain: [],
        message: "Parameter 'W' is used by Extrude1",
      },
      rows,
    );
    expect(error.rowId).toBe(W_ID);
    // Nothing to restore: no name, or the row is still there.
    expect(restoreDeletedRow(BASE, BASE, "W")).toEqual(BASE);
    expect(restoreDeletedRow(deleteRow(BASE, W_ID), BASE, null)).toHaveLength(
      1,
    );
  });

  it("puts a cycle's chain on the row it starts from", () => {
    const error = mapTableError(
      {
        code: "expression_cycle",
        parameter: "a",
        chain: ["a", "b", "a"],
        message: "parameter cycle: a -> b -> a",
      },
      ROWS,
    );
    expect(error).toEqual({
      rowId: W_ID,
      field: "expression",
      message: "Circular reference: a → b → a.",
      code: "expression_cycle",
    });
    expect(formatChain(["a", "b", "a"])).toBe("a → b → a");
  });

  it("names the unknown name without repeating the row's own", () => {
    const error = mapTableError(
      {
        code: "expression_unknown_name",
        parameter: "b",
        chain: [],
        message: "Parameter 'b': unknown name 'Q' in expression",
      },
      ROWS,
    );
    expect(error.rowId).toBe(H_ID);
    expect(error.message).toBe("Unknown name 'Q' in expression.");
  });

  it("blames the SECOND of two rows with one name, on the name cell", () => {
    const twice = [...ROWS, { ...blankRow(), name: "a", expression: "3" }];
    const error = mapTableError(
      {
        code: "expression_name_invalid",
        parameter: "a",
        chain: [],
        message: "Parameter 'a' is defined twice.",
      },
      twice,
    );
    expect(error.rowId).toBe(twice[2]!.id);
    expect(error.field).toBe("name");
  });

  it("finds the row in the message when details name none, else blames the table", () => {
    const units = mapTableError(
      {
        code: "expression_units",
        parameter: null,
        chain: [],
        message: "parameter 'b' evaluates to an angle; expected a length",
      },
      ROWS,
    );
    expect(units.rowId).toBe(H_ID);
    expect(units.message).toBe("Evaluates to an angle; expected a length.");
    const limit = mapTableError(
      {
        code: "expression_too_complex",
        parameter: null,
        chain: [],
        message: "201 parameters; a part may define at most 200",
      },
      ROWS,
    );
    expect(limit.rowId).toBeNull();
  });
});

describe("the Value column", () => {
  it("formats lengths in the document unit, angles in degrees", () => {
    expect(formatParameterValue(25, "length", "mm")).toBe("25 mm");
    expect(formatParameterValue(50.8, "length", "in")).toBe("2 in");
    expect(formatParameterValue(30, "angle", "in")).toBe("30°");
    expect(formatParameterValue(6, "unitless", "in")).toBe("6");
    expect(formatParameterValue(null, "length", "mm")).toBe("—");
  });
});
