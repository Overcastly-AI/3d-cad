/**
 * FLOW-A1 — KEYSTROKES THAT ARRIVE BEFORE THE CELLS EXIST.
 *
 * The draw-time size strip (`SketchScene.tsx`, {@link DrawDimensionTag}) says
 * *"Type a size"* from the instant a shape is placed. Measured in the real
 * browser, that instant and the instant it can RECEIVE a character are 75 ms
 * apart at best, and the whole promise is a lie for the duration:
 *
 *   pointerdown (the shape is placed, the store's draft is set)    t+0.0 ms
 *   keydown "1" — cell in DOM: NO, data-state: "live"              t+26.7 ms
 *   keydown "0" — cell in DOM: NO                                  t+27.0 ms
 *   keydown "0" — cell in DOM: NO                                  t+27.2 ms
 *   React commits the armed strip; the window listener attaches     t+101.7 ms
 *
 * The three digits are dispatched by the browser in the same burst as the
 * pointer event, so NOTHING that runs in a React effect — or in a React render
 * at all — can be in the path: the render has not happened yet. That rules out
 * every "attach the listener sooner" fix, including focusing the cell in the
 * commit that places the shape, because there is no such commit to focus in.
 *
 * So the keys are BUFFERED the moment they arrive, against the store's draft
 * (which `placeAt` sets synchronously, inside the pointer handler), and
 * replayed into the cells the instant those cells attach — in their REF
 * CALLBACK, not in a layout effect. That distinction is measured, not
 * stylistic: the cells live inside drei's `<Html>`, which portals them in a
 * commit of its own, so the arming commit's layout effect runs while the inputs
 * still do not exist (traced: `armed: true`, buffer `["100", ""]`, ref map
 * `[]`), and a ref registration schedules no render, so that effect never runs
 * again. See `SketchScene.registerCell` for the full trace.
 *
 * This module is that buffer: pure, so the state machine is unit-testable
 * without a browser, and so the listener in `SketchScene` stays a thin adapter.
 *
 * WHAT IT DELIBERATELY DOES NOT DO: swallow the keyboard. Only the characters
 * that start or continue a SIZE are taken; `r`, `l`, `g`, Escape and everything
 * else fall through to the canvas exactly as they do with no strip up, which is
 * the contract the armed strip has always advertised ("typing a DIGIT anywhere
 * puts it in the first cell", not "typing anything"). Auto-focusing the cell
 * instead would have taken every key and quietly broken that.
 *
 * Two exceptions, both QA-RECT-BOX-NAMES: once a value has begun, the rest of
 * it (letters included: `2*W`) is the value's, not the tools'; and while a
 * rectangle or circle is still being dragged its size box owns the keyboard
 * outright, as Fusion's does, so `W` is the parameter and not the Point tool.
 */

/** Characters that open a value — the same set the mounted strip accepts. */
const VALUE_CHARACTER = /^[0-9.]$/;

/** ...and a coordinate, which can be negative (typed X / Y, G2). */
const SIGNED_VALUE_CHARACTER = /^[-0-9.]$/;

/**
 * Characters of a FORMULA (`W/2 + 5`, QA-RECT-BOX-NAMES): a parameter or
 * dimension name, an operator, a bracket. A letter is a tool shortcut until a
 * value has begun (or a gesture's size box owns the keyboard, `formula:
 * "always"`); after that it is part of the value and never reaches the tools.
 */
const FORMULA_CHARACTER = /^[-+*/^()A-Za-z0-9_. ]$/;

/** Does `key` start a value in a size box that takes formulas outright? */
export function startsAFormula(key: string): boolean {
  return /^[A-Za-z0-9_.(]$/.test(key);
}

/** Typing captured before the size cells existed, addressed by cell index. */
export interface DrawKeyBuffer {
  /**
   * Which draft this typing belongs to (the drawn entity ids). A buffer never
   * crosses shapes: draw, type into the void, draw again, and the second
   * shape must come up empty rather than wearing the first one's number.
   */
  draftId: string;
  /** The cell the next character goes into. */
  index: number;
  /** What has been typed, per cell index. */
  text: string[];
  /** Enter was pressed — apply as soon as there is something to apply to. */
  apply: boolean;
}

/** What the listener should do with a key. */
export type DrawKeyOutcome =
  /** Not ours. The canvas keeps it, unprevented. */
  | { kind: "ignored" }
  /** Ours: swallow it and hold this buffer until the cells mount. */
  | { kind: "buffered"; buffer: DrawKeyBuffer };

const IGNORED: DrawKeyOutcome = { kind: "ignored" };

/** An empty buffer for `fieldCount` cells. */
function empty(draftId: string, fieldCount: number): DrawKeyBuffer {
  return {
    draftId,
    index: 0,
    text: Array.from({ length: fieldCount }, () => ""),
    apply: false,
  };
}

function withText(
  buffer: DrawKeyBuffer,
  index: number,
  text: string,
): DrawKeyBuffer {
  const next = [...buffer.text];
  next[index] = text;
  return { ...buffer, text: next };
}

/**
 * Fold one keystroke into the buffer.
 *
 * `buffer` is the buffer so far, or `null` if nothing has been typed yet.
 * Passing a buffer belonging to a DIFFERENT draft is the same as passing
 * `null` — the stale typing is dropped rather than inherited.
 *
 * Enter closes the buffer: once `apply` is set, further characters are ignored,
 * because the user has already said they are done and the next thing they type
 * belongs to whatever comes after the commit.
 */
export function bufferDrawKey(
  buffer: DrawKeyBuffer | null,
  key: string,
  options: {
    draftId: string;
    fieldCount: number;
    shiftKey?: boolean;
    /** The cells take a signed value (a coordinate), so a minus is ours. */
    signed?: boolean;
    /**
     * When a formula's letters are ours: `"started"` once the cell being
     * typed holds text, `"always"` while a gesture's size box owns the keys.
     */
    formula?: "started" | "always";
  },
): DrawKeyOutcome {
  const {
    draftId,
    fieldCount,
    shiftKey = false,
    signed = false,
    formula = "started",
  } = options;
  if (fieldCount < 1) return IGNORED;
  const current = buffer !== null && buffer.draftId === draftId ? buffer : null;
  if (current !== null && current.apply) return IGNORED;

  if (key === "Enter") {
    // Enter with nothing typed means "the shape is right as drawn" — which the
    // mounted strip handles by applying an empty set of values. Same here: it
    // is a commit either way, so it opens a buffer if there is none.
    return {
      kind: "buffered",
      buffer: { ...(current ?? empty(draftId, fieldCount)), apply: true },
    };
  }

  if (key === "Tab") {
    const base = current ?? empty(draftId, fieldCount);
    const step = shiftKey ? -1 : 1;
    // Wrapping, because a dimension pair is a loop — tabbing out of the
    // viewport mid-value is the dead end the mounted strip already avoids.
    const index = (base.index + step + fieldCount) % fieldCount;
    return { kind: "buffered", buffer: { ...base, index } };
  }

  if (key === "Backspace") {
    // Only meaningful once something has been typed; with no buffer there is
    // nothing to correct and Backspace is the canvas's (it is not ours to eat).
    if (current === null) return IGNORED;
    const text = current.text[current.index] ?? "";
    return {
      kind: "buffered",
      buffer: withText(current, current.index, text.slice(0, -1)),
    };
  }

  const base = current ?? empty(draftId, fieldCount);
  const text = base.text[base.index] ?? "";
  const started = formula === "always" ? true : text !== "";
  const opens = (signed ? SIGNED_VALUE_CHARACTER : VALUE_CHARACTER).test(key);
  const continues =
    started &&
    FORMULA_CHARACTER.test(key) &&
    (text !== "" || startsAFormula(key));
  if (!opens && !continues) return IGNORED;
  return { kind: "buffered", buffer: withText(base, base.index, text + key) };
}

/** The buffer's text for a cell index, or `""` — never `undefined`. */
export function bufferedText(buffer: DrawKeyBuffer, index: number): string {
  return buffer.text[index] ?? "";
}

/** True when the user typed something, as opposed to only Tab-ing or Enter-ing. */
export function bufferHasText(buffer: DrawKeyBuffer): boolean {
  return buffer.text.some((text) => text !== "");
}
