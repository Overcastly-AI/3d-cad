/**
 * `<ValueField>`: every numeric field takes a number OR a formula
 * (PART-PARAMETERS step 8, docs/RESEARCH.md §20), as in Fusion 360, where any
 * dimension box accepts `Width / 2`.
 *
 *  - A NUMBER behaves exactly as the field always did: the editor reads it in
 *    the document unit (`2` in an inch part is 2 in; `50 mm` overrides).
 *  - A FORMULA (`H/2`) is shown as typed with an `fx` mark, and what it comes
 *    to (`= 10 mm`) is set at the cell's tail. The editor's form is handed the
 *    resolved number, so its validation, its live preview and its gauges work
 *    unchanged, and the formula itself is kept by JSON pointer for the save
 *    (`expressions: {"/distance_mm": "H/2"}`), which documents resolves again.
 *  - Typing a name offers the part's parameters (and, in the sketcher, the
 *    sketch's own dimensions) with their values: arrows to move, Enter or Tab
 *    to take one, Escape to close the list, Ctrl+Space to open it on demand.
 *  - A formula that cannot resolve says why ON the field (`Parameter 'Q' not
 *    found.`), and so does the server's refusal of a save, and the feature's
 *    `input_error` when the table moved under it.
 *  - Dragging a gauge sets a NUMBER: the field drops its formula, as Fusion's
 *    manipulators replace an expression with the value they leave.
 *
 * The cell is UNCONTROLLED (the browser owns the text): the sketcher's
 * dimension box lives inside the canvas, where a controlled cell loses
 * keystrokes at typing speed (DIM-1), and one rule for every field is simpler
 * than two. React keeps a shadow of the DOM's text and writes the cell only
 * when something other than typing changed what it should show.
 */
import {
  DimensionTagCell,
  isCarpenterLength,
  type LengthUnit,
  Notice,
  NumberField,
  type NumberFieldProps,
  SuggestionList,
  suggestionOptionId,
} from "@loft/design";
import {
  type ChangeEvent,
  type CSSProperties,
  createContext,
  type FocusEvent,
  type KeyboardEvent,
  type ReactNode,
  type Ref,
  useCallback,
  useContext,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";

import {
  applyCompletion,
  type Completion,
  type CompletionCandidate,
  completionAt,
  type FormulaSession,
  functionCandidates,
  mountFormulaField,
  type ScopeDimension,
  scopeQuantities,
  sessionFieldErrors,
  sessionFormulas,
  setSessionFieldError,
  setSessionFormula,
  useFormulaSessionStore,
  useParameterScopeStore,
} from "../features/fieldFormulas";
import { formatParameterValue } from "../features/parameters";
import { storedLengthInput } from "../features/storedNumber";
import { useDocumentLengthUnit } from "../units/documentUnit";
import {
  bareFieldFormula,
  carpenterHint,
  type FieldKind,
  formatFieldHint,
  formatFieldValue,
  type FormulaResult,
  parseFieldEntry,
  resolveFieldFormula,
  typedFormulaError,
} from "../units/length";

/** The open feature editor, for the fields inside it (FeatureEditorSeat). */
export const FormulaSessionContext = createContext<FormulaSession | null>(null);

export interface ValueFieldProps extends Omit<
  NumberFieldProps,
  "value" | "defaultValue" | "onChange" | "ref" | "formula" | "hint"
> {
  /** What the field measures: mm, degrees, a plain number or a count. */
  kind: FieldKind;
  /**
   * The editor's text for this field: a number as typed, or (while a formula
   * drives it) the number the formula resolves to. In the sketcher (no
   * `pointer`), the dimension's text itself: a literal or its formula.
   */
  value: string;
  onValueChange: (text: string) => void;
  /**
   * The params field this drives (`/distance_mm`). With it, a formula is kept
   * for the save's `expressions`; without it the text IS the value (the
   * sketcher, whose formula lives in the dimension).
   */
  pointer?: string;
  /** Sketcher: this sketch's named dimensions, offered and read as numbers. */
  dimensions?: readonly ScopeDimension[];
  /** A reading to show when the field cannot work one out (the solver's). */
  fallbackHint?: string | null;
  /** Handle on the cell, for a caller that reads the DOM at commit time. */
  inputRef?: Ref<HTMLInputElement>;
  /** The cell's test hook; its hint and list take `-hint`, `-suggestions`. */
  "data-testid"?: string;
  /**
   * Render as a drafting tag cell (`DimensionTagCell`, this many characters
   * wide) instead of a form field: the sketcher's draw-time boxes, which hang
   * on the shape being drawn (QA-RECT-BOX-NAMES). Same formula engine, same
   * autocomplete; the error is shown by the cell's flag and by its strip.
   */
  tagWidth?: number;
  /**
   * A tag cell's own unit (`°`), for a strip whose cells do not share one
   * (a line's length and angle, SKETCH-LINE-ANGLE). Tag cells only.
   */
  tagUnit?: string;
  /**
   * The unit a carpenter-notation number in this field reads in, when it is
   * not the document's: the sketcher's dimension box, whose literals are mm.
   */
  lengthUnit?: LengthUnit;
}

/**
 * Place a fixed-position list under the cell that holds `input`, kept there
 * while it is open. Fixed and portalled: an editor card scrolls (and clips),
 * and the sketcher's box sits in a transformed layer.
 */
function useAnchoredStyle(
  input: { readonly current: HTMLInputElement | null },
  open: boolean,
): CSSProperties | null {
  const [style, setStyle] = useState<CSSProperties | null>(null);
  useLayoutEffect(() => {
    const anchor = input.current?.parentElement ?? null;
    // Closed: nothing to place, and no state to touch (a closed field must
    // cost its editor no extra commit; `useGaugeFedForm.test`).
    if (!open || anchor === null) return;
    const place = () => {
      const box = anchor.getBoundingClientRect();
      setStyle({
        position: "fixed",
        left: box.left,
        top: box.bottom + 2,
        minWidth: Math.max(box.width, 160),
      });
    };
    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [input, open]);
  return open ? style : null;
}

export function ValueField({
  kind,
  value,
  onValueChange,
  pointer,
  dimensions,
  fallbackHint = null,
  inputRef,
  error,
  onKeyDown,
  onBlur,
  "data-testid": testId,
  tagWidth,
  tagUnit,
  lengthUnit,
  ...rest
}: ValueFieldProps) {
  const unit = useDocumentLengthUnit();
  // What a carpenter-notation number reads in (its echo, and the mixed-number
  // spelling a refusal suggests); everything else keeps the document's unit.
  const bareUnit = lengthUnit ?? unit;
  const session = useContext(FormulaSessionContext);
  const listId = useId();
  const input = useRef<HTMLInputElement | null>(null);

  // --- the formula -----------------------------------------------------------
  // A pointer field inside an open editor keeps its formula in the editor's
  // session (the save reads it there); a pointer field anywhere else (a test
  // harness) keeps it locally; a sketch dimension has none apart from its text.
  const inSession = pointer !== undefined && session !== null;
  const storedFormula = useFormulaSessionStore((state) =>
    inSession
      ? (sessionFormulas(state, session.key, session.seed)[pointer] ?? null)
      : null,
  );
  const fieldError = useFormulaSessionStore((state) =>
    inSession
      ? (sessionFieldErrors(state, session.key)[pointer] ?? null)
      : null,
  );
  const [localFormula, setLocalFormula] = useState<string | null>(null);
  const formula =
    pointer === undefined ? null : inSession ? storedFormula : localFormula;
  const setFormula = useCallback(
    (next: string | null) => {
      if (pointer === undefined) return;
      if (session !== null) setSessionFormula(session, pointer, next);
      else setLocalFormula(next);
    },
    [pointer, session],
  );

  useEffect(
    () => (inSession ? mountFormulaField(pointer) : undefined),
    [inSession, pointer],
  );

  // --- what it resolves to ----------------------------------------------------
  const parameters = useParameterScopeStore((state) => state.parameters);
  const names = useMemo(
    () =>
      scopeQuantities(
        // In the sketcher a formula over its own dimensions needs no table.
        parameters ?? (dimensions !== undefined ? [] : null),
        dimensions,
      ),
    [parameters, dimensions],
  );
  const display = pointer === undefined ? value : (formula ?? value);
  // The sketcher sends anything but a plain number as the dimension's
  // formula (`20mm` included), so that is what wears the mark there.
  // A length in carpenter notation (`11-15/32`, `5' 6"`) is a number there
  // too: the box reads it as one (RESEARCH §29), so it is never a formula.
  const textFormula =
    pointer === undefined
      ? (() => {
          if (kind === "length" && isCarpenterLength(display, bareUnit)) {
            return null;
          }
          const entry = parseFieldEntry(display, "unitless", unit);
          return entry.kind === "formula" ? entry.expression : null;
        })()
      : formula;
  // The formula this field opened with: stored, so the server's reading of
  // it stands. Only a formula typed since is checked for a hyphenated mixed
  // number that reads two ways (`2*11-15/32`), and refused rather than guessed.
  const openedWith = useRef(display);
  const seedFormula = inSession
    ? (session.seed[pointer] ?? null)
    : pointer === undefined
      ? openedWith.current.trim()
      : null;
  const stored = textFormula !== null && textFormula === seedFormula;
  const ambiguity = stored
    ? null
    : textFormula === null
      ? null
      : typedFormulaError(textFormula, kind, bareUnit);
  // FORMULA-BARE-UNIT: a feature field's stored formula is read as stored
  // (and flagged below when a bare term in it reads as mm); one typed here is
  // read as the save will store it, with the part's unit written into its
  // bare terms (`wall + 1/2` is `wall + 1 in/2`). The sketcher's text is the
  // dimension itself, read as the solver reads it.
  const entered =
    pointer === undefined || textFormula === null || stored
      ? null
      : bareFieldFormula(textFormula, kind, names, unit);
  const result: FormulaResult | null =
    textFormula === null
      ? null
      : ambiguity !== null
        ? { ok: false, message: ambiguity, code: "expression_syntax" }
        : resolveFieldFormula(entered?.text ?? textFormula, kind, names);
  const stale =
    pointer !== undefined && stored && textFormula !== null
      ? bareFieldFormula(textFormula, kind, names, unit)
      : null;
  const staleFixed =
    stale === null ? null : resolveFieldFormula(stale.text, kind, names);

  // The editor's form follows the formula: its resolved number, or the
  // formula's text while it does not resolve (the editor's own check then
  // refuses it, so Save stays shut). A number written by anyone else (a gauge
  // drag, a re-seed) replaces the formula. A length is written as the
  // editor's own seed writes the same millimetres (`storedLengthInput`), so
  // re-seeding the stored number after a save or a refetch is no write at all:
  // `wall + 1 in/2` is 152.39999999999998 mm, which seeds as `6`.
  const pushed = useRef(value);
  const want =
    formula === null || result === null
      ? null
      : result.ok
        ? kind === "length"
          ? storedLengthInput(result.value, unit)
          : formatFieldValue(result.value, kind, unit)
        : formula;
  useEffect(() => {
    if (pointer === undefined) return;
    if (formula === null || want === null) {
      pushed.current = value;
      return;
    }
    if (value !== pushed.current) {
      pushed.current = value;
      setFormula(null);
      return;
    }
    if (value !== want) {
      pushed.current = want;
      onValueChange(want);
    }
  }, [pointer, formula, want, value, setFormula, onValueChange]);

  // --- the uncontrolled cell ---------------------------------------------------
  const domText = useRef(display);
  /**
   * What typing has handed the caller since the field last showed someone
   * else's text. In the sketcher the caller ECHOES each text back as `value`,
   * and an echo can land after the typist has moved on (the draw boxes live in
   * drei's own React root, so their owner renders a frame behind): `2` coming
   * back after `23` was typed is old news, not a write, and writing it is a
   * lost keystroke (DIM-1's class).
   */
  const echoes = useRef<string[]>([]);
  useLayoutEffect(() => {
    const node = input.current;
    if (node === null || display === domText.current) return;
    if (pointer === undefined && echoes.current.includes(display)) return;
    echoes.current = [];
    domText.current = display;
    if (node.value !== display) node.value = display;
  }, [display, pointer]);

  const setRefs = useCallback(
    (node: HTMLInputElement | null) => {
      input.current = node;
      if (typeof inputRef === "function") inputRef(node);
      else if (inputRef != null) {
        (inputRef as { current: HTMLInputElement | null }).current = node;
      }
    },
    [inputRef],
  );

  // --- autocomplete ------------------------------------------------------------
  const candidates = useMemo<CompletionCandidate[]>(() => {
    const own: CompletionCandidate[] = (dimensions ?? []).map((d) => ({
      name: d.name,
      detail: formatParameterValue(d.value, "unitless", unit),
      source: "dimension",
    }));
    const ownNames = new Set(own.map((c) => c.name));
    const table: CompletionCandidate[] = (parameters ?? [])
      .filter((p) => !ownNames.has(p.name))
      .map((p) => ({
        name: p.name,
        detail: formatParameterValue(p.value, p.unit, unit),
        source: "parameter",
      }));
    return [...own, ...table, ...functionCandidates()];
  }, [dimensions, parameters, unit]);
  const [completion, setCompletion] = useState<Completion | null>(null);
  const [active, setActive] = useState(0);
  const listStyle = useAnchoredStyle(input, completion !== null);

  const take = (text: string) => {
    domText.current = text;
    if (pointer === undefined) {
      echoes.current = [...echoes.current.slice(-31), text];
      onValueChange(text);
      return;
    }
    if (session !== null) setSessionFieldError(session, pointer, null);
    const entry = parseFieldEntry(text, kind, unit);
    if (entry.kind === "formula") {
      setFormula(entry.expression);
      return;
    }
    setFormula(null);
    pushed.current = text;
    onValueChange(text);
  };

  const suggest = (text: string, caret: number, force = false) => {
    const next = completionAt(text, caret, candidates, force);
    setCompletion(next);
    setActive(0);
  };

  const accept = (index: number) => {
    const node = input.current;
    const option = completion?.options[index];
    if (node === null || completion === null || option === undefined) return;
    const applied = applyCompletion(node.value, completion, option);
    node.value = applied.text;
    node.setSelectionRange(applied.caret, applied.caret);
    setCompletion(null);
    take(applied.text);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (completion !== null) {
      const count = completion.options.length;
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        event.stopPropagation();
        setActive(
          (i) => (i + (event.key === "ArrowDown" ? 1 : count - 1)) % count,
        );
        return;
      }
      const option = completion.options[active];
      // The word already IS the highlighted name (`D`, with `deg` below it):
      // taking it changes nothing, so the key keeps its own meaning, Tab
      // to the next cell and Enter to apply (QA-RECT-BOX-NAMES: `W` Tab `H`
      // Enter must not need two Tabs and two Enters).
      const complete =
        option !== undefined &&
        option.source !== "function" &&
        option.name === completion.prefix;
      if ((event.key === "Enter" || event.key === "Tab") && complete) {
        setCompletion(null);
      } else if (event.key === "Enter" || event.key === "Tab") {
        event.preventDefault();
        event.stopPropagation();
        accept(active);
        return;
      }
      if (event.key === "Escape") {
        // The list's own step back; the editor behind it stays open.
        event.preventDefault();
        event.stopPropagation();
        setCompletion(null);
        return;
      }
    }
    if (event.key === " " && event.ctrlKey) {
      event.preventDefault();
      const node = event.currentTarget;
      suggest(node.value, node.selectionStart ?? node.value.length, true);
      return;
    }
    onKeyDown?.(event);
  };

  // --- what the cell says -------------------------------------------------------
  const inputError =
    inSession &&
    session.inputError !== null &&
    session.inputError.pointer === pointer &&
    formula === (session.seed[pointer] ?? null)
      ? session.inputError.message
      : null;
  const formulaError =
    ambiguity ??
    (pointer !== undefined &&
    result !== null &&
    !result.ok &&
    result.code !== "pending"
      ? result.message
      : null);
  const shownError = formulaError ?? fieldError ?? inputError ?? error ?? null;
  const hint =
    result === null
      ? kind === "length"
        ? carpenterHint(display, bareUnit)
        : null
      : result.ok
        ? formatFieldHint(result.value, kind, unit)
        : result.code === "pending"
          ? "= …"
          : pointer === undefined
            ? fallbackHint
            : null;

  const open = completion !== null && listStyle !== null;
  const cellProps = {
    ref: setRefs,
    "data-testid": testId,
    "data-formula": textFormula !== null ? "" : undefined,
    defaultValue: display,
    inputMode: "text",
    autoCapitalize: "off",
    role: "combobox",
    "aria-autocomplete": "list",
    "aria-expanded": open,
    "aria-controls": open ? listId : undefined,
    "aria-activedescendant": open
      ? suggestionOptionId(listId, active)
      : undefined,
    formula: textFormula !== null,
    hint: hint ?? undefined,
    ...(testId !== undefined ? { hintTestId: `${testId}-hint` } : {}),
    onChange: (event: ChangeEvent<HTMLInputElement>) => {
      const node = event.target;
      take(node.value);
      suggest(node.value, node.selectionStart ?? node.value.length);
    },
    onKeyDown: handleKeyDown,
    onBlur: (event: FocusEvent<HTMLInputElement>) => {
      setCompletion(null);
      onBlur?.(event);
    },
  } as const;
  let cell: ReactNode;
  if (tagWidth === undefined) {
    cell = <NumberField {...rest} {...cellProps} error={shownError} />;
  } else {
    // A tag cell has no caption row: the unit is the strip's (or the cell's
    // own `tagUnit`), and the reason for an error is written under the strip
    // by its owner.
    const tag = { ...rest };
    delete tag.unit;
    delete tag.emphasis;
    delete tag.layout;
    cell = (
      <DimensionTagCell
        {...tag}
        {...cellProps}
        width={tagWidth}
        unit={tagUnit}
        aria-invalid={shownError !== null || undefined}
      />
    );
  }
  const reading = (r: typeof result): string =>
    r?.ok === true ? formatFieldHint(r.value, kind, unit).slice(2) : "no value";
  const staleNotice =
    stale === null ? null : (
      <Notice
        role="status"
        label="Read as mm"
        tone="flag"
        layout="stacked"
        data-testid={testId === undefined ? undefined : `${testId}-bare-unit`}
        action={{
          label: `Read as ${unit}`,
          onClick: () => setFormula(stale.text),
          ...(testId !== undefined
            ? { testId: `${testId}-bare-unit-fix` }
            : {}),
        }}
      >
        {`${stale.literals.join(", ")} in this formula is read as mm, so it ` +
          `gives ${reading(result)}. Read as ${unit} (${stale.text}), it ` +
          `gives ${reading(staleFixed)}.`}
      </Notice>
    );
  return (
    <>
      {cell}
      {staleNotice}
      {open && completion !== null
        ? createPortal(
            <SuggestionList
              id={listId}
              options={completion.options.map((option) => ({
                value: option.name,
                detail: option.detail,
              }))}
              activeIndex={active}
              onPick={accept}
              style={listStyle}
              aria-label="Parameters"
              {...(testId !== undefined
                ? { "data-testid": `${testId}-suggestions` }
                : {})}
            />,
            document.body,
          )
        : null}
    </>
  );
}
