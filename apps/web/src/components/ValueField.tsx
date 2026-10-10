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
  NumberField,
  type NumberFieldProps,
  SuggestionList,
  suggestionOptionId,
} from "@loft/design";
import {
  type CSSProperties,
  createContext,
  type KeyboardEvent,
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
import { useDocumentLengthUnit } from "../units/documentUnit";
import {
  type FieldKind,
  formatFieldHint,
  formatFieldValue,
  parseFieldEntry,
  resolveFieldFormula,
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
  ...rest
}: ValueFieldProps) {
  const unit = useDocumentLengthUnit();
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
  const textFormula =
    pointer === undefined
      ? (() => {
          const entry = parseFieldEntry(display, "unitless", unit);
          return entry.kind === "formula" ? entry.expression : null;
        })()
      : formula;
  const result =
    textFormula === null ? null : resolveFieldFormula(textFormula, kind, names);

  // The editor's form follows the formula: its resolved number, or the
  // formula's text while it does not resolve (the editor's own check then
  // refuses it, so Save stays shut). A number written by anyone else (a gauge
  // drag, a re-seed) replaces the formula.
  const pushed = useRef(value);
  const want =
    formula === null || result === null
      ? null
      : result.ok
        ? formatFieldValue(result.value, kind, unit)
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
  useLayoutEffect(() => {
    const node = input.current;
    if (node === null || display === domText.current) return;
    domText.current = display;
    if (node.value !== display) node.value = display;
  }, [display]);

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
      if (event.key === "Enter" || event.key === "Tab") {
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
    pointer !== undefined &&
    result !== null &&
    !result.ok &&
    result.code !== "pending"
      ? result.message
      : null;
  const shownError = formulaError ?? fieldError ?? inputError ?? error ?? null;
  const hint =
    result === null
      ? null
      : result.ok
        ? formatFieldHint(result.value, kind, unit)
        : result.code === "pending"
          ? "= …"
          : pointer === undefined
            ? fallbackHint
            : null;

  const open = completion !== null && listStyle !== null;
  return (
    <>
      <NumberField
        {...rest}
        ref={setRefs}
        data-testid={testId}
        data-formula={textFormula !== null ? "" : undefined}
        defaultValue={display}
        inputMode="text"
        autoCapitalize="off"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-activedescendant={
          open ? suggestionOptionId(listId, active) : undefined
        }
        formula={textFormula !== null}
        hint={hint ?? undefined}
        {...(testId !== undefined ? { hintTestId: `${testId}-hint` } : {})}
        error={shownError}
        onChange={(event) => {
          const node = event.target;
          take(node.value);
          suggest(node.value, node.selectionStart ?? node.value.length);
        }}
        onKeyDown={handleKeyDown}
        onBlur={(event) => {
          setCompletion(null);
          onBlur?.(event);
        }}
      />
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
