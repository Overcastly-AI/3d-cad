/**
 * `<ValueField>` (PART-PARAMETERS step 8): a number or a formula in any
 * numeric field, the formula marked `fx` with what it comes to, the editor's
 * form fed the resolved number, names offered as they are typed, and every
 * reason a formula fails said on the field.
 */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  clearFormulaSession,
  type FormulaSession,
  sessionFormulas,
  setSessionFieldError,
  useFormulaSessionStore,
  useParameterScopeStore,
} from "../features/fieldFormulas";
import { DocumentUnitProvider } from "../units/documentUnit";
import type { FieldKind } from "../units/length";
import { FormulaSessionContext, ValueField } from "./ValueField";

beforeEach(() => {
  useParameterScopeStore.getState().setParameters([
    { name: "H", value: 20, unit: "length" },
    { name: "Height", value: 30, unit: "length" },
    { name: "Draft", value: 3, unit: "angle" },
  ]);
});

afterEach(() => {
  cleanup();
  clearFormulaSession();
  useParameterScopeStore.getState().setParameters(null);
});

interface HostProps {
  initial?: string;
  kind?: FieldKind;
  pointer?: string;
  session?: FormulaSession | null;
  unit?: "mm" | "in";
  error?: string | null;
  onKeyDown?: () => void;
}

/** An editor in miniature: the form's text, and what it last received. */
function mount({
  initial = "5",
  kind = "length",
  pointer = "/distance_mm",
  session = null,
  unit = "mm",
  error = null,
  onKeyDown,
}: HostProps = {}) {
  const seen: string[] = [];
  let setExternally: (text: string) => void = () => undefined;
  function Host() {
    const [value, setValue] = useState(initial);
    setExternally = setValue;
    return (
      <DocumentUnitProvider unit={unit}>
        <FormulaSessionContext.Provider value={session}>
          <ValueField
            label="Distance"
            unit={unit}
            kind={kind}
            pointer={pointer}
            data-testid="field"
            value={value}
            error={error}
            onValueChange={(text) => {
              seen.push(text);
              setValue(text);
            }}
            {...(onKeyDown !== undefined ? { onKeyDown } : {})}
          />
          <output data-testid="form">{value}</output>
        </FormulaSessionContext.Provider>
      </DocumentUnitProvider>
    );
  }
  render(<Host />);
  const input = screen.getByTestId<HTMLInputElement>("field");
  return {
    input,
    seen,
    form: () => screen.getByTestId("form").textContent,
    type: (text: string) =>
      fireEvent.change(input, { target: { value: text } }),
    gauge: (text: string) => act(() => setExternally(text)),
  };
}

const mark = (input: HTMLElement) =>
  input.parentElement?.querySelector("[data-formula-mark]") ?? null;

describe("ValueField", () => {
  it("passes a typed number through untouched, with no mark", () => {
    const f = mount();
    f.type("12");
    expect(f.form()).toBe("12");
    expect(mark(f.input)).toBeNull();
    expect(screen.queryByTestId("field-hint")).toBeNull();
  });

  it("shows a formula as typed, marks it fx, and feeds the form its value", () => {
    const f = mount();
    f.type("H/2");
    expect(f.input.value).toBe("H/2");
    expect(mark(f.input)?.textContent).toBe("fx");
    expect(screen.getByTestId("field-hint").textContent).toBe("= 10 mm");
    expect(f.form()).toBe("10");
    expect(f.input).toHaveAttribute("data-formula");
  });

  it("feeds the form in the document unit", () => {
    const f = mount({ unit: "in", initial: "1" });
    f.type("H + 5.4 mm");
    expect(Number(f.form())).toBeCloseTo(1, 12);
    expect(screen.getByTestId("field-hint").textContent).toBe("= 1 in");
  });

  it("says on the field why a formula does not resolve, and keeps Save shut", () => {
    const f = mount();
    f.type("Q/2");
    expect(screen.getByRole("alert").textContent).toBe(
      "Parameter 'Q' not found.",
    );
    expect(f.input).toHaveAttribute("aria-invalid", "true");
    // The form holds the formula text, which no editor reads as a number.
    expect(f.form()).toBe("Q/2");
  });

  it("refuses an angle where a length goes", () => {
    const f = mount();
    f.type("Draft * 2");
    expect(screen.getByRole("alert").textContent).toBe(
      "This is an angle; the field needs a length.",
    );
  });

  it("drops the formula when a gauge writes a number", () => {
    const f = mount();
    f.type("H/2");
    expect(f.form()).toBe("10");
    f.gauge("17");
    expect(f.input.value).toBe("17");
    expect(mark(f.input)).toBeNull();
    // ...and does not put its own number back.
    expect(f.form()).toBe("17");
  });

  it("returns to a number when one is typed over the formula", () => {
    const f = mount();
    f.type("H/2");
    f.type("8");
    expect(f.form()).toBe("8");
    expect(mark(f.input)).toBeNull();
  });

  it("shows the editor's own refusal of the resolved value", () => {
    const f = mount({ error: "Enter a distance above 0." });
    f.type("H - H");
    expect(screen.getByRole("alert").textContent).toBe(
      "Enter a distance above 0.",
    );
  });

  it("counts: a formula must come to a whole number", () => {
    const f = mount({ kind: "int", initial: "3", pointer: "/count" });
    f.type("H / 1 mm / 8");
    expect(screen.getByRole("alert").textContent).toBe(
      "This field needs a whole number.",
    );
    f.type("H / 1 mm / 4");
    expect(f.form()).toBe("5");
  });
});

describe("ValueField autocomplete", () => {
  it("offers the parameters that match, with their values", () => {
    const f = mount();
    f.type("He");
    const list = screen.getByTestId("field-suggestions");
    expect(list).toHaveAttribute("role", "listbox");
    expect(
      Array.from(list.querySelectorAll("[role=option]")).map(
        (o) => o.textContent,
      ),
    ).toEqual(["Height30 mm"]);
    expect(f.input).toHaveAttribute("aria-expanded", "true");
  });

  it("moves with the arrows and takes a name with Enter, not submitting", () => {
    const submit = vi.fn();
    const f = mount({ onKeyDown: submit });
    f.type("H");
    const options = () =>
      screen.getAllByRole("option").map((o) => o.getAttribute("data-value"));
    expect(options()).toEqual(["H", "Height"]);
    fireEvent.keyDown(f.input, { key: "ArrowDown" });
    expect(f.input.getAttribute("aria-activedescendant")).toMatch(/option-1$/);
    fireEvent.keyDown(f.input, { key: "Enter" });
    expect(submit).not.toHaveBeenCalled();
    expect(f.input.value).toBe("Height");
    expect(f.form()).toBe("30");
    expect(screen.queryByTestId("field-suggestions")).toBeNull();
    // With the list closed, Enter is the editor's again.
    fireEvent.keyDown(f.input, { key: "Enter" });
    expect(submit).toHaveBeenCalledTimes(1);
  });

  it("lets Enter and Tab through when the word already is the name", () => {
    // `H` with `Height` below it: taking `H` would change nothing, so the
    // key is the editor's (QA-RECT-BOX-NAMES: `W` Tab `H` Enter).
    const keys = vi.fn();
    const f = mount({ onKeyDown: keys });
    f.type("H");
    expect(screen.getByTestId("field-suggestions")).toBeInTheDocument();
    fireEvent.keyDown(f.input, { key: "Tab" });
    expect(keys).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("field-suggestions")).toBeNull();
    expect(f.input.value).toBe("H");
  });

  it("takes a name with a click, keeping focus in the cell", () => {
    const f = mount();
    f.type("2*He");
    fireEvent.mouseDown(screen.getByRole("option", { name: /Height/ }));
    expect(f.input.value).toBe("2*Height");
    expect(f.form()).toBe("60");
  });

  it("closes on Escape without letting the editor see it", () => {
    const escape = vi.fn();
    const f = mount({ onKeyDown: escape });
    f.type("H");
    fireEvent.keyDown(f.input, { key: "Escape" });
    expect(screen.queryByTestId("field-suggestions")).toBeNull();
    expect(escape).not.toHaveBeenCalled();
  });

  it("opens on Ctrl+Space with everything in scope", () => {
    const f = mount();
    f.type("2*");
    fireEvent.keyDown(f.input, { key: " ", ctrlKey: true });
    const names = screen
      .getAllByRole("option")
      .map((o) => o.getAttribute("data-value"));
    // The scope's names first, then the functions, up to the list's length.
    expect(names.slice(0, 4)).toEqual(["Draft", "H", "Height", "abs"]);
    expect(names).toHaveLength(8);
  });
});

describe("ValueField inside an editor's session", () => {
  const session: FormulaSession = {
    key: "extrude:f1",
    seed: { "/distance_mm": "H/2" },
    inputError: null,
  };

  it("opens on the stored formula and keeps edits for the save", () => {
    const f = mount({ session, initial: "10" });
    expect(f.input.value).toBe("H/2");
    expect(mark(f.input)).not.toBeNull();
    f.type("H/4");
    expect(f.form()).toBe("5");
    expect(
      sessionFormulas(
        useFormulaSessionStore.getState(),
        session.key,
        session.seed,
      ),
    ).toEqual({ "/distance_mm": "H/4" });
    f.type("7");
    expect(
      sessionFormulas(
        useFormulaSessionStore.getState(),
        session.key,
        session.seed,
      ),
    ).toEqual({});
  });

  it("shows the server's refusal on the field until it is edited", () => {
    const f = mount({ session, initial: "10" });
    act(() =>
      setSessionFieldError(session, "/distance_mm", "Parameter 'Q' not found."),
    );
    expect(screen.getByRole("alert").textContent).toBe(
      "Parameter 'Q' not found.",
    );
    f.type("H/3");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows the feature's input_error on the field it names", () => {
    mount({
      session: {
        ...session,
        inputError: {
          pointer: "/distance_mm",
          message: "The value must be greater than 0.",
        },
      },
      initial: "10",
    });
    expect(screen.getByRole("alert").textContent).toBe(
      "The value must be greater than 0.",
    );
  });

  it("says it is reading the table rather than calling a name unknown", () => {
    useParameterScopeStore.getState().setParameters(null);
    const f = mount({ session, initial: "10" });
    expect(screen.getByTestId("field-hint").textContent).toBe("= …");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(f.form()).toBe("H/2");
  });
});

describe("ValueField in the sketcher (no pointer)", () => {
  it("is the dimension's text, with the mark and the value it comes to", () => {
    const seen: string[] = [];
    const DIMENSIONS = [{ name: "width", value: 40 }];
    function Box() {
      // The dimension box keeps a shadow of the cell's text (`useTypedField`).
      const [text, setText] = useState("5");
      return (
        <ValueField
          label="Distance"
          kind="length"
          value={text}
          dimensions={DIMENSIONS}
          data-testid="dim"
          onValueChange={(next) => {
            seen.push(next);
            setText(next);
          }}
        />
      );
    }
    render(<Box />);
    const input = screen.getByTestId<HTMLInputElement>("dim");
    fireEvent.change(input, { target: { value: "wi" } });
    expect(screen.getByRole("option", { name: /width/ })).toBeTruthy();
    fireEvent.keyDown(input, { key: "Tab" });
    expect(input.value).toBe("width");
    fireEvent.change(input, { target: { value: "width/2" } });
    expect(seen.at(-1)).toBe("width/2");
    expect(screen.getByTestId("dim-hint").textContent).toBe("= 20 mm");
    expect(mark(input)).not.toBeNull();
  });

  it("never writes a late echo of its own typing over newer keys", () => {
    // A draw box's owner renders a frame behind (drei's own React root): its
    // echo of `2` can land after `23` was typed, and must not undo the `3`.
    let echo: (text: string) => void = () => undefined;
    function Box() {
      const [text, setText] = useState("");
      echo = setText;
      return (
        <ValueField
          label="X"
          kind="length"
          value={text}
          dimensions={[]}
          data-testid="x"
          onValueChange={() => undefined}
        />
      );
    }
    render(<Box />);
    const input = screen.getByTestId<HTMLInputElement>("x");
    fireEvent.change(input, { target: { value: "2" } });
    fireEvent.change(input, { target: { value: "23" } });
    act(() => echo("2"));
    expect(input.value).toBe("23");
    // Someone else's text still lands.
    act(() => echo("7"));
    expect(input.value).toBe("7");
  });
});
