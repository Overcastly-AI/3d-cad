import { afterEach, describe, expect, it } from "vitest";

import {
  applyCompletion,
  type CompletionCandidate,
  completionAt,
  clearFormulaSession,
  describeInputError,
  expressionsForParams,
  fieldLabelFromPointer,
  inputErrorPointer,
  scopeQuantities,
  sessionFieldErrors,
  sessionFormulas,
  setSessionFieldError,
  setSessionFormula,
  useFormulaSessionStore,
  valueAtPointer,
} from "./fieldFormulas";

const CANDIDATES: CompletionCandidate[] = [
  { name: "Height", detail: "20 mm", source: "parameter" },
  { name: "H", detail: "10 mm", source: "parameter" },
  { name: "Width", detail: "40 mm", source: "parameter" },
  { name: "hub", detail: "8 mm", source: "parameter" },
  { name: "sin", detail: "function", source: "function" },
  { name: "sqrt", detail: "function", source: "function" },
];

describe("completionAt", () => {
  it("offers the names that start with the word at the caret", () => {
    const c = completionAt("H", 1, CANDIDATES);
    expect(c?.options.map((o) => o.name)).toEqual(["H", "Height", "hub"]);
    expect(c).toMatchObject({ from: 0, to: 1, prefix: "H" });
  });

  it("reads the word under the caret mid-formula", () => {
    const c = completionAt("Wi/2 + 1", 2, CANDIDATES);
    expect(c?.options.map((o) => o.name)).toEqual(["Width"]);
    expect(c).toMatchObject({ from: 0, to: 2 });
  });

  it("puts the scope's names before functions", () => {
    const c = completionAt("2*s", 3, [
      ...CANDIDATES,
      { name: "s_gap", detail: "1 mm", source: "parameter" },
    ]);
    expect(c?.options.map((o) => o.name)).toEqual(["s_gap", "sin", "sqrt"]);
  });

  it("offers nothing after a number, where a unit goes", () => {
    expect(completionAt("10 m", 4, CANDIDATES)).toBeNull();
    expect(completionAt("10h", 3, CANDIDATES)).toBeNull();
  });

  it("offers nothing for a complete name with nothing longer", () => {
    expect(completionAt("Width", 5, CANDIDATES)).toBeNull();
    expect(completionAt("Zed", 3, CANDIDATES)).toBeNull();
  });

  it("lists everything on demand at an operand position", () => {
    expect(completionAt("", 0, CANDIDATES)).toBeNull();
    expect(completionAt("2 * ", 4, CANDIDATES, true)?.options).toHaveLength(6);
    expect(completionAt("2 ", 2, CANDIDATES, true)).toBeNull();
  });

  it("replaces the word on accept; a function gains its parenthesis", () => {
    const text = "Wi/2";
    const c = completionAt(text, 2, CANDIDATES);
    expect(c).not.toBeNull();
    const width = c?.options[0] as CompletionCandidate;
    expect(applyCompletion(text, c!, width)).toEqual({
      text: "Width/2",
      caret: 5,
    });
    const s = completionAt("2*si", 4, CANDIDATES)!;
    expect(applyCompletion("2*si", s, s.options[0]!)).toEqual({
      text: "2*sin(",
      caret: 6,
    });
  });
});

describe("pointers into params", () => {
  const params = {
    distance_mm: 10,
    pattern: { axis_point: { x: 1, y: 2 } },
    depth: { kind: "through_all" },
    list: [5, { "a/b": 3 }],
  };

  it("finds the value at a pointer, RFC 6901 escapes included", () => {
    expect(valueAtPointer(params, "/distance_mm")).toBe(10);
    expect(valueAtPointer(params, "/pattern/axis_point/y")).toBe(2);
    expect(valueAtPointer(params, "/list/0")).toBe(5);
    expect(valueAtPointer(params, "/list/1/a~1b")).toBe(3);
    expect(valueAtPointer(params, "/depth/depth_mm")).toBeUndefined();
    expect(valueAtPointer(params, "/list/01")).toBeUndefined();
  });

  it("sends only the formulas whose field is a number of these params", () => {
    expect(
      expressionsForParams(params, {
        "/distance_mm": "H/2",
        "/depth/depth_mm": "H",
        "/depth/kind": "H",
      }),
    ).toEqual({ "/distance_mm": "H/2" });
    expect(expressionsForParams(params, { "/gone": "H" })).toBeUndefined();
    expect(expressionsForParams(params, {})).toBeUndefined();
  });
});

describe("a feature's input_error, in the field's words", () => {
  it("names the field and the missing parameter", () => {
    const message = "/width_mm = 'W/2': unknown parameter 'W'";
    expect(inputErrorPointer(message)).toBe("/width_mm");
    expect(describeInputError(message)).toBe("Width: parameter 'W' not found.");
  });

  it("reads a value its field refuses", () => {
    const message =
      "A resolved value is refused by its field (params/distance_mm): Input should be greater than 0";
    expect(inputErrorPointer(message)).toBe("/distance_mm");
    expect(describeInputError(message)).toBe(
      "Distance: the value must be greater than 0.",
    );
  });

  it("reads a unit mismatch", () => {
    const message =
      '/bend_angle_deg = "it\'s": expression for /bend_angle_deg evaluates to a length; expected an angle';
    expect(describeInputError(message)).toBe(
      "Bend angle: evaluates to a length; expected an angle.",
    );
  });

  it("reads a sketch dimension's unknown name, which has no pointer", () => {
    expect(
      describeInputError("unknown dimension name 'Gap' in expression"),
    ).toBe("No dimension or parameter is named 'Gap'.");
  });

  it("labels a field from its pointer", () => {
    expect(fieldLabelFromPointer("/bend_radius_mm")).toBe("Bend radius");
    expect(fieldLabelFromPointer("/pattern/axis_point/x")).toBe("X");
    expect(fieldLabelFromPointer("/k_factor")).toBe("K factor");
  });
});

describe("scopeQuantities", () => {
  it("types parameters, and reads a sketch's own dimensions as numbers", () => {
    const names = scopeQuantities(
      [{ name: "W", value: 40, unit: "length" }],
      [{ name: "half", value: 20 }],
    );
    expect(names?.get("W")).toEqual({ value: 40, kind: "length" });
    expect(names?.get("half")).toEqual({ value: 20, kind: "unitless" });
    expect(scopeQuantities(null)).toBeNull();
  });
});

describe("the formula session", () => {
  afterEach(clearFormulaSession);
  const session = { key: "extrude:f1", seed: { "/distance_mm": "H/2" } };

  it("reads the stored seed until the editor edits a formula", () => {
    const state = useFormulaSessionStore.getState();
    expect(sessionFormulas(state, session.key, session.seed)).toEqual({
      "/distance_mm": "H/2",
    });
    setSessionFormula(session, "/distance_mm", "H/4");
    expect(
      sessionFormulas(
        useFormulaSessionStore.getState(),
        session.key,
        session.seed,
      ),
    ).toEqual({ "/distance_mm": "H/4" });
    setSessionFormula(session, "/distance_mm", null);
    expect(
      sessionFormulas(
        useFormulaSessionStore.getState(),
        session.key,
        session.seed,
      ),
    ).toEqual({});
  });

  it("never lends one editor's formulas or refusals to another", () => {
    setSessionFormula(session, "/distance_mm", "H/4");
    setSessionFieldError(session, "/distance_mm", "Parameter 'Q' not found.");
    const state = useFormulaSessionStore.getState();
    expect(sessionFormulas(state, "revolve:new", {})).toEqual({});
    expect(sessionFieldErrors(state, "revolve:new")).toEqual({});
    expect(sessionFieldErrors(state, session.key)).toEqual({
      "/distance_mm": "Parameter 'Q' not found.",
    });
    clearFormulaSession();
    expect(
      sessionFormulas(
        useFormulaSessionStore.getState(),
        session.key,
        session.seed,
      ),
    ).toEqual(session.seed);
  });
});
