/**
 * DIMENSION WHILE YOU DRAW (FB-16) — the size cells hung on the shape being
 * made. Split out of `SketchScene.tsx` (FILE-SIZE-RATCHET) when the cells
 * learned formulas (QA-RECT-BOX-NAMES). Three states, deliberately continuous:
 *
 *  · **live**, while the pointer still owns the size: a read-only strip showing
 *    the width/height (or length, or diameter) the rubber band currently has.
 *    Pointer-inert, so it can never eat the click that finishes the shape.
 *  · **typing**, a rectangle or circle still being dragged once a value key is
 *    pressed: the strip's cells take the keys, as Fusion's boxes do mid-drag.
 *    Enter places the shape at the typed size, in the direction of the drag.
 *  · **armed**, the moment the shape commits: the same numbers in the same
 *    place become cells you type into. Tab walks them (and wraps — a dimension
 *    pair is a loop), Enter applies, Escape hands the canvas back with the
 *    shape kept.
 *
 * EVERY CELL TAKES A NUMBER OR A FORMULA (`<ValueField>`, PART-PARAMETERS):
 * `80`, `W`, `W/2 + 5`, with the part's parameters and this sketch's named
 * dimensions offered as a name is typed. A formula becomes the dimension's own
 * `expression`, so the shape follows the parameter, exactly as the dimension
 * box's does. A name nothing defines is flagged on its cell and the strip
 * says why; Enter applies nothing until it is fixed (the QA defect was `W`
 * Enter applying nothing and saying so nowhere).
 *
 * KEYS. With the strip armed, typing a DIGIT anywhere puts it in the first
 * cell; other letters still reach the canvas (`r`, `l`), unless a value has
 * begun, when the rest of it is the value's. Mid-drag the size box owns the
 * keyboard outright: `W` is the parameter, never the Point tool. Keys the
 * strip takes stop at the window (capture phase), so no tool shortcut also
 * fires on them.
 *
 * EXCEPT AFTER A TYPED SHAPE (TYPED-COORD-HIJACK). When the shape's last point
 * came from the typed X / Y cells its size is already exact, and the user is
 * typing points: the strip arms for a click but takes no keys.
 *
 * WHY VALUES APPLY ON ENTER, NOT PER KEYSTROKE: each applied value is a
 * revision — a solve and a debounced save. Applying per keystroke would rebuild
 * the sketch at "5" on the way to "50", and would make Escape unable to
 * abandon anything.
 */
import { DimensionTag, DimensionTagCell, lengthUnitLabel } from "@loft/design";
import { Html } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import {
  useCallback,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";

import { ValueField } from "../components/ValueField";
import { useGlobalKeys } from "../lib/modalGate";
import {
  drawDimensionFields,
  drawShapeOf,
  resizedTo,
  type DrawDimensionExpressions,
  type DrawDimensionField,
  type DrawDimensionKey,
  type DrawDimensionValues,
} from "../sketch/drawDimensions";
import { drawCellsOk, resolveDrawCells } from "../sketch/drawEntry";
import { planeToWorld, type PlaneBasis, type Point2D } from "../sketch/plane";
import { useSketchStore, type SketchState } from "../sketch/store";
import { useDocumentLengthUnit } from "../units/documentUnit";
import {
  bufferDrawKey,
  bufferedText,
  startsAFormula,
  type DrawKeyBuffer,
} from "./drawDimensionKeys";
import {
  DIMENSION_TAG_Z_RANGE,
  replayText,
  sizeText,
  useDrawNames,
} from "./drawTag";

/** Keys that start a value in the ARMED strip: digits, a decimal point. */
const STARTS_A_VALUE = /^[0-9.]$/;

/**
 * WHICH CORNER THE TAG HANGS FROM. The rail is anchored at the gesture's second
 * point and pushed into the quadrant the drag was heading, so it hangs OFF the
 * shape rather than over it, clear of the snap mark's word
 * (docs/design/pre-selection.md §2 — one aim, one indicator).
 */
function tagTransform(from: Point2D, to: Point2D): string {
  const gap = 10;
  // Plane +y is up on screen, so a drag in +y hangs the rail upward.
  const x = to.x >= from.x ? `${gap}px` : `calc(-100% - ${gap}px)`;
  const y = to.y >= from.y ? `calc(-100% - ${gap}px)` : `${gap}px`;
  return `translate(${x}, ${y})`;
}

/**
 * The gesture whose size box takes typing MID-DRAG, as an identity, or null:
 * a rectangle or circle with its first point down. A line's next point is
 * typed as X / Y (G2), so it is not one of these.
 */
function dragSizing(
  state: Pick<
    SketchState,
    "mode" | "tool" | "pending" | "pointEntry" | "dimensionEdit"
  >,
): string | null {
  if (state.mode !== "draw" || state.pointEntry !== null) return null;
  if (state.dimensionEdit !== null || state.pending.length !== 1) return null;
  const shape = drawShapeOf(state.tool);
  const from = state.pending[0];
  if ((shape !== "rect" && shape !== "circle") || from === undefined) {
    return null;
  }
  return `live:${shape}:${from.x},${from.y}`;
}

/**
 * Place the shape being dragged at the typed size, along the drag, and record
 * the dimensions: the click's own path (`aim`, `placeAt`) with snaps held off,
 * because the corner is where the numbers put it, not where the pointer is.
 */
function placeSized(
  values: DrawDimensionValues,
  expressions: DrawDimensionExpressions,
): void {
  const state = useSketchStore.getState();
  const shape = drawShapeOf(state.tool);
  const from = state.pending[0];
  if (shape === null || from === undefined) return;
  const end = resizedTo(shape, from, state.cursor ?? from, values);
  const { snapSuppressed, axisLock } = state;
  state.aim(end, 0, { suppressed: true, axisLock: false });
  useSketchStore.getState().placeAt(end);
  useSketchStore.setState({ snapSuppressed, axisLock });
  useSketchStore.getState().commitDrawDimensions(values, expressions);
}

interface TagState {
  from: Point2D;
  to: Point2D;
  fields: DrawDimensionField[];
  /** Armed = the shape is drawn and the cells take typing. */
  armed: boolean;
}

type CellErrors = Partial<Record<DrawDimensionKey, string>>;

export function DrawDimensionTag({ basis }: { basis: PlaneBasis }) {
  const draft = useSketchStore((state) => state.drawDimension);
  const typingPoint = useSketchStore((state) => state.pointEntry !== null);
  const tool = useSketchStore((state) => state.tool);
  const pending = useSketchStore((state) => state.pending);
  const cursor = useSketchStore((state) => state.cursor);
  const sizingId = useSketchStore(dragSizing);
  const commit = useSketchStore((state) => state.commitDrawDimensions);
  const dismiss = useSketchStore((state) => state.dismissDrawDimensions);
  const focusCell = useSketchStore((state) => state.focusDrawDimension);
  const unit = useDocumentLengthUnit();
  const { dimensions, names } = useDrawNames();
  const invalidate = useThree((state) => state.invalidate);
  const inputs = useRef(new Map<DrawDimensionKey, HTMLInputElement>());
  /**
   * The draft the cells in `inputs` belong to, or null once they are spent.
   * The DOM lags the store: right after a commit (or a new shape) the old
   * cells are still attached, and a key routed to them would be typed into a
   * shape that is finished.
   */
  const cellsDraft = useRef<string | null>(null);
  /** Keys typed before the cells existed, waiting for a commit to land in. */
  const buffered = useRef<DrawKeyBuffer | null>(null);
  /** The drag whose size box has begun taking keys (`dragSizing`). */
  const [typingIn, setTypingIn] = useState<string | null>(null);
  /** Each cell's text as React last saw it: it drives the `fx` mark and hint. */
  const [texts, setTexts] = useState<{
    draft: string;
    byKey: Partial<Record<DrawDimensionKey, string>>;
  }>({ draft: "", byKey: {} });
  /** Why a cell refused its text, for the draft it was typed in. */
  const [errors, setErrors] = useState<{ draft: string; byKey: CellErrors }>({
    draft: "",
    byKey: {},
  });

  const typingLive =
    draft === null && sizingId !== null && typingIn === sizingId;

  const state: TagState | null = useMemo(() => {
    if (draft !== null) {
      return {
        from: draft.from,
        to: draft.to,
        fields: draft.fields,
        armed: true,
      };
    }
    // Typed X / Y cells own the next point (G2): the live size of a rubber
    // band that is about to be REPLACED by a typed point is not news.
    if (typingPoint) return null;
    const shape = drawShapeOf(tool);
    const from = pending[0];
    if (shape === null || from === undefined || cursor === null) return null;
    if (pending.length !== 1) return null;
    const fields = drawDimensionFields(shape, from, cursor);
    // Nothing to say about a zero-size rubber band, unless it is being typed.
    if (!typingLive && fields.every((field) => field.measuredMm === 0)) {
      return null;
    }
    return { from, to: cursor, fields, armed: false };
  }, [draft, typingPoint, tool, pending, cursor, typingLive]);

  const armed = state?.armed === true;
  const editable = armed || typingLive;
  // One identity per drawn shape (or per drag being typed): it re-keys the
  // cells, so a new rectangle never inherits the numbers typed into the last.
  const draftKey =
    draft !== null ? draft.ids.join(",") : typingLive ? sizingId : "live";

  /** The live draft's identity, read from the STORE (it leads the render). */
  const liveDraftKey = (): string | null => {
    const store = useSketchStore.getState();
    if (store.drawDimension !== null) return store.drawDimension.ids.join(",");
    return dragSizing(store);
  };

  /**
   * Apply the cells' texts: commit an armed shape's sizes, or place the shape
   * being dragged at them. A cell that does not resolve holds everything back
   * and says why on itself. True when it applied.
   */
  const applyTexts = useCallback(
    (
      key: string,
      fields: readonly DrawDimensionField[],
      textOf: (index: number) => string,
    ): boolean => {
      const cells = resolveDrawCells(fields, textOf, unit, names);
      if (!drawCellsOk(cells)) {
        setErrors({ draft: key, byKey: cells.errors });
        invalidate();
        return false;
      }
      setErrors({ draft: "", byKey: {} });
      buffered.current = null;
      cellsDraft.current = null;
      if (useSketchStore.getState().drawDimension !== null) {
        commit(cells.values, cells.expressions);
      } else {
        placeSized(cells.values, cells.expressions);
        setTypingIn(null);
      }
      invalidate();
      return true;
    },
    [commit, invalidate, names, unit],
  );

  /** The DOM's text for each cell (the browser owns it; see `ValueField`). */
  const readCells = useCallback(
    (fields: readonly DrawDimensionField[]) => (index: number) => {
      const field = fields[index];
      return field === undefined
        ? ""
        : (inputs.current.get(field.key)?.value ?? "");
    },
    [],
  );

  /**
   * Type anywhere to start dimensioning (FLOW-A1 for why this listens for the
   * whole session and reads the STORE rather than the render, and
   * `drawDimensionKeys.ts` for which keys are ours). Capture phase, so a key
   * the strip takes is stopped before any tool shortcut hears it.
   */
  useGlobalKeys(
    "sketch draw sizes",
    (event) => {
      // `useGlobalKeys` has already left a typing target's keys to it.
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const store = useSketchStore.getState();
      const live = store.drawDimension;
      // A TYPED shape's cells do not take the keyboard: the next keystrokes
      // are the next point's (TYPED-COORD-HIJACK). A click still reaches them.
      if (live?.typed === true) {
        buffered.current = null;
        return;
      }
      const sizing = live === null ? dragSizing(store) : null;
      if (live === null && sizing === null) {
        buffered.current = null;
        return;
      }
      const draftId = live !== null ? live.ids.join(",") : (sizing as string);
      const fields =
        live !== null
          ? live.fields
          : drawDimensionFields(
              drawShapeOf(store.tool) ?? "rect",
              store.pending[0] as Point2D,
              store.cursor ?? (store.pending[0] as Point2D),
            );
      const firstKey = fields[0]?.key;
      if (firstKey === undefined) return;
      // Cells in the DOM that belong to an EARLIER draft (the render has not
      // caught up with the shape just placed) are not this draft's cells.
      const cell =
        cellsDraft.current === draftId
          ? inputs.current.get(firstKey)
          : undefined;
      if (cell === undefined) {
        // Mid-drag, Enter with nothing typed is not ours: it means nothing.
        if (
          live === null &&
          event.key === "Enter" &&
          buffered.current?.draftId !== draftId
        ) {
          return;
        }
        // THE CELLS ARE NOT IN THE DOM YET. Hold the keys against this draft
        // and replay them in the commit that creates the cells.
        const outcome = bufferDrawKey(buffered.current, event.key, {
          draftId,
          fieldCount: fields.length,
          shiftKey: event.shiftKey,
          formula: live === null ? "always" : "started",
        });
        if (outcome.kind === "ignored") return;
        event.preventDefault();
        event.stopPropagation();
        // The typing takes the keyboard: a toolbar button left focused by a
        // click would otherwise claim the Enter that applies it.
        const active = document.activeElement;
        if (active instanceof HTMLElement && active !== document.body) {
          active.blur();
        }
        if (live === null) setTypingIn(draftId);
        if (outcome.buffer.apply) {
          // Enter applies IN THIS KEYDOWN, from the keys themselves, not when
          // the cells mount: the next keystroke must meet a store that has
          // already moved on (TYPED-POINT-RACE).
          const { buffer } = outcome;
          const applied = applyTexts(draftId, fields, (index) =>
            bufferedText(buffer, index),
          );
          // Refused: keep the text (not the Enter) for the cells to show.
          buffered.current = applied ? null : { ...buffer, apply: false };
          return;
        }
        buffered.current = outcome.buffer;
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        event.stopPropagation();
        applyTexts(draftId, fields, readCells(fields));
        return;
      }
      const opens =
        live === null
          ? startsAFormula(event.key)
          : STARTS_A_VALUE.test(event.key);
      if (!opens && event.key !== "Tab") return;
      // Focus DURING keydown and let the BROWSER deliver the character to the
      // newly-focused cell; inserting it by hand is what loses it (DIM-1).
      event.stopPropagation();
      if (event.key === "Tab") event.preventDefault();
      cell.focus();
    },
    { capture: true },
  );

  if (state === null) return null;

  const { from, to, fields } = state;
  const cellErrors = errors.draft === draftKey ? errors.byKey : {};
  const firstError = fields
    .map((field) => cellErrors[field.key])
    .find((message) => message !== undefined);

  /**
   * Register a cell's node and, if keys were typed before it existed, put them
   * in (FLOW-A1). THE REPLAY LIVES IN THE REF CALLBACK, NOT IN AN EFFECT: the
   * cells are inside drei's `<Html>`, which portals them in a commit of its
   * own, so an effect of this component runs before the inputs exist.
   */
  const registerCell = (
    key: DrawDimensionKey,
    index: number,
    node: HTMLInputElement | null,
  ) => {
    if (node === null) {
      inputs.current.delete(key);
      return;
    }
    // A render that has not caught up with the store (the draft was applied,
    // dismissed or replaced since) mounts cells nobody may type into.
    if (liveDraftKey() !== draftKey) return;
    inputs.current.set(key, node);
    cellsDraft.current = draftKey;
    const held = buffered.current;
    // Typing that belongs to another shape is never replayed here.
    if (held?.draftId !== draftKey) return;
    const text = bufferedText(held, index);
    if (text !== "" || index === held.index) {
      replayText(node, text, index === held.index);
    }
    // Hold the buffer until every cell has had its turn.
    if (inputs.current.size < fields.length) return;
    buffered.current = null;
    invalidate();
  };

  const onKeyDown = (
    event: ReactKeyboardEvent<HTMLInputElement>,
    index: number,
  ) => {
    if (event.key === "Escape") {
      // The field's own Escape: abandon the typing, keep the shape (or the
      // drag), hand the canvas back with the tool still armed.
      event.stopPropagation();
      event.preventDefault();
      event.currentTarget.blur();
      buffered.current = null;
      setErrors({ draft: "", byKey: {} });
      if (armed) dismiss();
      else setTypingIn(null);
      invalidate();
      return;
    }
    if (event.key === "Enter") {
      // Explicit, not an implicit form submission (a two-cell form swallows it).
      event.preventDefault();
      const cell = event.currentTarget;
      // Spend the cells on success: a focused dead cell would eat the next
      // keystrokes, which belong to the next shape (TYPED-POINT-RACE).
      if (applyTexts(draftKey, fields, readCells(fields))) cell.blur();
      return;
    }
    if (event.key !== "Tab" || fields.length < 2) return;
    const step = event.shiftKey ? -1 : 1;
    const next = fields[(index + step + fields.length) % fields.length];
    if (next === undefined) return;
    event.preventDefault();
    inputs.current.get(next.key)?.focus();
  };

  const textOf = (key: DrawDimensionKey) =>
    texts.draft === draftKey ? (texts.byKey[key] ?? "") : "";
  return (
    <Html
      position={planeToWorld(basis, to)}
      zIndexRange={DIMENSION_TAG_Z_RANGE}
      style={{ pointerEvents: "none" }}
    >
      <div style={{ transform: tagTransform(from, to) }}>
        <div
          key={draftKey}
          role={editable ? "group" : undefined}
          data-testid="draw-dimensions"
          data-state={armed ? "armed" : typingLive ? "typing" : "live"}
          style={{ pointerEvents: armed ? "auto" : "none" }}
          aria-label={
            armed
              ? "Size of the shape you just drew"
              : typingLive
                ? "Size of the shape you are drawing"
                : undefined
          }
        >
          <DimensionTag unit={lengthUnitLabel(unit)}>
            {fields.map((field, index) =>
              editable ? (
                <ValueField
                  key={field.key}
                  tagWidth={6}
                  kind="length"
                  label={field.label}
                  value={textOf(field.key)}
                  onValueChange={(text) => {
                    setTexts((prev) => ({
                      draft: draftKey,
                      byKey: {
                        ...(prev.draft === draftKey ? prev.byKey : {}),
                        [field.key]: text,
                      },
                    }));
                    if (cellErrors[field.key] !== undefined) {
                      setErrors({ draft: "", byKey: {} });
                    }
                  }}
                  dimensions={dimensions}
                  error={cellErrors[field.key] ?? null}
                  placeholder={sizeText(field.measuredMm, unit)}
                  aria-label={`${field.name} in ${lengthUnitLabel(unit)}`}
                  data-testid={`draw-dimension-${field.key}`}
                  inputRef={(node: HTMLInputElement | null) =>
                    registerCell(field.key, index, node)
                  }
                  onFocus={() => focusCell(field.key)}
                  onBlur={() => focusCell(null)}
                  onKeyDown={(event) => onKeyDown(event, index)}
                />
              ) : (
                <DimensionTagCell
                  key={field.key}
                  label={field.label}
                  width={6}
                  readout={sizeText(field.measuredMm, unit)}
                />
              ),
            )}
          </DimensionTag>
          {firstError !== undefined ? (
            <p
              className="mt-1 font-body text-2xs text-flag"
              role="alert"
              data-testid="draw-dimensions-error"
            >
              {firstError}
            </p>
          ) : editable ? (
            <p className="mt-1 font-body text-2xs text-gauge">
              {draft?.typed === true
                ? // Typed points: the keyboard has moved on to the next point.
                  "Click a size to change it"
                : fields.length > 1
                  ? "Number or parameter · Tab switches · Enter applies"
                  : "Number or parameter · Enter applies"}
            </p>
          ) : null}
        </div>
      </div>
    </Html>
  );
}
