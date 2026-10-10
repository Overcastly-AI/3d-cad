/**
 * TYPE WHERE THE POINT GOES (helical-gear gap G2). Split out of
 * `SketchScene.tsx` (FILE-SIZE-RATCHET) when its cells learned formulas
 * (QA-RECT-BOX-NAMES): X and Y take a number or a formula over the part's
 * parameters and this sketch's named dimensions (`W/2`), resolved as typed.
 * A coordinate creates no dimension, so a formula here places the point at
 * what it comes to now; a name nothing defines is said on the cells.
 *
 * The gear test placed 24 involute fit points by reading the DRO at
 * 0.024 mm/px: there was no way to say "this point is at (21.5705, 5.8494)".
 * In the FB-16 idiom (a dimension is typed where it forms, not recovered
 * later), a digit typed while a point-placing tool is live opens X / Y cells
 * at the cursor: the first key lands in X, Tab moves to Y, Enter places the
 * point exactly there, Escape abandons it. An empty cell keeps the aimed
 * value, so "12 Enter" pins X and takes Y from the pointer. With exactly one
 * point selected, the same keys move THAT point. `pointEntryOpening` says
 * which placements take a typed point.
 *
 * The cells are uncontrolled, and the keys typed before they exist are
 * buffered and replayed from the ref callback, for the reasons
 * `DrawDimensionTag` documents (FLOW-A1).
 *
 * THE STORE ROUTES THE KEYS, NEVER THE DOM (TYPED-COORD-HIJACK,
 * TYPED-POINT-RACE). The DOM trails the store by a frame or more: after an
 * Enter, the cells of the point just placed are still attached (and focused)
 * while the next point's keys arrive. So:
 *
 *  - Enter places the point IN ITS OWN KEYDOWN, from the buffered keys when
 *    the cells are not up yet, and spends the cells at once (blurred and
 *    disowned), so the next keystroke meets a store that has moved on.
 *  - A buffer and a set of cells belong to one entry (its `nonce`), so keys
 *    can never replay into, or be swallowed by, another entry's cells.
 *  - The listener runs in the capture phase, ahead of the sketch's own Enter
 *    (which finishes a spline), and the Enter it takes is `preventDefault`ed.
 */
import { DimensionTag, lengthUnitLabel } from "@loft/design";
import { Html } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import {
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";

import { ValueField } from "../components/ValueField";
import { useGlobalKeys } from "../lib/modalGate";
import { resolveDrawEntry } from "../sketch/drawEntry";
import { planeToWorld, type PlaneBasis, type Point2D } from "../sketch/plane";
import { opensACoordinate, pointEntryOpening } from "../sketch/pointEntry";
import { useSketchStore } from "../sketch/store";
import { useDocumentLengthUnit } from "../units/documentUnit";
import {
  bufferDrawKey,
  bufferedText,
  type DrawKeyBuffer,
} from "./drawDimensionKeys";
import {
  DIMENSION_TAG_Z_RANGE,
  replayText,
  sizeText,
  useDrawNames,
} from "./drawTag";

/** One typed-point entry's buffer identity: typing never crosses entries. */
const pointDraftId = (nonce: number): string => `point:${nonce}`;

export function PointEntry({ basis }: { basis: PlaneBasis }) {
  const entry = useSketchStore((state) => state.pointEntry);
  const open = useSketchStore((state) => state.openPointEntry);
  const close = useSketchStore((state) => state.closePointEntry);
  const commit = useSketchStore((state) => state.commitPointEntry);
  const unit = useDocumentLengthUnit();
  const { dimensions, names } = useDrawNames();
  const invalidate = useThree((state) => state.invalidate);
  /** The attached cells, and the entry (by nonce) they belong to. */
  const cellsRef = useRef<{
    nonce: number | null;
    nodes: [HTMLInputElement | null, HTMLInputElement | null];
  }>({ nonce: null, nodes: [null, null] });
  /** Keys typed before the cells existed, waiting for them to attach. */
  const buffered = useRef<DrawKeyBuffer | null>(null);
  /** Why the typing could not place, or null. */
  const [invalid, setInvalid] = useState<string | null>(null);
  /** Each cell's text as React last saw it (drives the `fx` mark and hint). */
  const [texts, setTexts] = useState<{ nonce: number; xy: [string, string] }>({
    nonce: -1,
    xy: ["", ""],
  });

  /**
   * Place (or move) the point from the typed text of each cell. An empty cell
   * keeps the anchor's value. False when a cell does not resolve.
   */
  const place = (
    anchor: Point2D,
    typed: readonly [string, string],
  ): boolean => {
    const x = resolveDrawEntry(typed[0], unit, names, { signed: true });
    const y = resolveDrawEntry(typed[1], unit, names, { signed: true });
    if (x.kind === "error" || y.kind === "error") {
      const bad = x.kind === "error" ? x : (y as { message: string });
      setInvalid(bad.message);
      return false;
    }
    buffered.current = null;
    cellsRef.current = { nonce: null, nodes: [null, null] };
    commit({
      x: x.kind === "value" ? x.mm : anchor.x,
      y: y.kind === "value" ? y.mm : anchor.y,
    });
    invalidate();
    return true;
  };

  useGlobalKeys(
    "sketch point entry",
    (event) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const state = useSketchStore.getState();
      if (state.mode !== "draw") return;
      const live = state.pointEntry;
      if (live === null) {
        // Which keys open one: `opensACoordinate` (`0` too, to place a point).
        const opening = pointEntryOpening(state);
        if (opening === null || !opensACoordinate(event.key, opening)) return;
        event.preventDefault();
        // The typing takes the keyboard: a toolbar button left focused by a
        // click would otherwise claim the Enter that places this point.
        const active = document.activeElement;
        if (active instanceof HTMLElement && active !== document.body) {
          active.blur();
        }
        open(opening.anchor, opening.target);
        const nonce = useSketchStore.getState().pointEntry?.nonce ?? 0;
        const outcome = bufferDrawKey(null, event.key, {
          draftId: pointDraftId(nonce),
          fieldCount: 2,
          signed: true,
        });
        buffered.current = outcome.kind === "buffered" ? outcome.buffer : null;
        setInvalid(null);
        invalidate();
        return;
      }
      // This entry's cells are up: they take their own keys.
      if (cellsRef.current.nonce === live.nonce) return;
      // Open, but its cells are not in the DOM yet: hold the keys for them
      // (a formula's letters too, once the value has begun).
      const outcome = bufferDrawKey(buffered.current, event.key, {
        draftId: pointDraftId(live.nonce),
        fieldCount: 2,
        shiftKey: event.shiftKey,
        signed: true,
      });
      if (outcome.kind === "ignored") return;
      event.preventDefault();
      event.stopPropagation();
      const { buffer } = outcome;
      if (!buffer.apply) {
        buffered.current = buffer;
        return;
      }
      const typed = [bufferedText(buffer, 0), bufferedText(buffer, 1)] as const;
      // Unresolved: keep the text (not the Enter) for the cells to show.
      if (!place(live.anchor, typed)) {
        buffered.current = { ...buffer, apply: false };
      }
    },
    { capture: true },
  );

  if (entry === null) return null;

  const apply = (): boolean => {
    const [x, y] = cellsRef.current.nodes;
    return place(entry.anchor, [x?.value ?? "", y?.value ?? ""]);
  };

  const remember = (index: 0 | 1, text: string) =>
    setTexts((prev) => {
      const xy: [string, string] =
        prev.nonce === entry.nonce ? [...prev.xy] : ["", ""];
      xy[index] = text;
      return { nonce: entry.nonce, xy };
    });

  /**
   * Register a cell and replay what was typed before it existed. React calls
   * an inline ref again on every render, so everything here happens only while
   * a replay is pending: a later render must never pull focus back to X while
   * the user is typing Y.
   */
  const register = (index: 0 | 1, node: HTMLInputElement | null) => {
    const own = cellsRef.current.nonce === entry.nonce;
    if (node === null) {
      if (own) cellsRef.current.nodes[index] = null;
      return;
    }
    // A render that has not caught up with the store (this entry was placed
    // or abandoned since) mounts cells nobody may type into.
    if (useSketchStore.getState().pointEntry?.nonce !== entry.nonce) return;
    if (!own) cellsRef.current = { nonce: entry.nonce, nodes: [null, null] };
    cellsRef.current.nodes[index] = node;
    const pending = buffered.current;
    if (pending?.draftId !== pointDraftId(entry.nonce)) return;
    const text = bufferedText(pending, index);
    if (text !== "" || index === pending.index) {
      replayText(node, text, index === pending.index);
    }
    if (index === 1) buffered.current = null;
  };

  /** Hand the keyboard back: the cells stay in the DOM until the next render. */
  const spend = (cell: HTMLInputElement) => {
    cellsRef.current = { nonce: null, nodes: [null, null] };
    cell.blur();
  };

  const onKeyDown = (
    event: ReactKeyboardEvent<HTMLInputElement>,
    index: 0 | 1,
  ) => {
    if (event.key === "Escape") {
      // The cells' own Escape: abandon the typing, keep the tool armed.
      event.stopPropagation();
      event.preventDefault();
      buffered.current = null;
      spend(event.currentTarget);
      close();
      invalidate();
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const cell = event.currentTarget;
      if (apply()) cell.blur();
      return;
    }
    if (event.key !== "Tab") return;
    // A coordinate pair is a loop, like the size cells.
    event.preventDefault();
    cellsRef.current.nodes[index === 0 ? 1 : 0]?.focus();
  };

  const cells = [
    { index: 0, axis: "x", label: "X" },
    { index: 1, axis: "y", label: "Y" },
  ] as const;
  return (
    <Html
      position={planeToWorld(basis, entry.anchor)}
      zIndexRange={DIMENSION_TAG_Z_RANGE}
      style={{ pointerEvents: "none" }}
    >
      {/* Down and right of the point: the snap mark's word and the size rail
          hang up and right of the cursor, so this never sits on either. */}
      <div style={{ transform: "translate(12px, 12px)" }}>
        <div
          key={entry.nonce}
          role="group"
          aria-label={
            entry.target === null
              ? "Coordinates of the next point"
              : "Move the selected point to"
          }
          data-testid="point-entry"
          style={{ pointerEvents: "auto" }}
        >
          <DimensionTag unit={lengthUnitLabel(unit)}>
            {cells.map(({ index, axis, label }) => (
              <ValueField
                key={axis}
                tagWidth={9}
                kind="length"
                label={label}
                value={texts.nonce === entry.nonce ? texts.xy[index] : ""}
                onValueChange={(text) => {
                  remember(index, text);
                  setInvalid(null);
                }}
                dimensions={dimensions}
                error={invalid}
                placeholder={sizeText(entry.anchor[axis], unit)}
                aria-label={`${label} in ${lengthUnitLabel(unit)}`}
                data-testid={`point-entry-${axis}`}
                inputRef={(node: HTMLInputElement | null) =>
                  register(index, node)
                }
                onKeyDown={(event) => onKeyDown(event, index)}
              />
            ))}
          </DimensionTag>
          <p
            className={`mt-1 font-body text-2xs ${invalid === null ? "text-gauge" : "text-flag"}`}
            {...(invalid === null ? {} : { role: "alert" })}
          >
            {invalid ??
              (entry.target === null
                ? "Tab switches · Enter places · Esc cancels"
                : "Tab switches · Enter moves · Esc cancels")}
          </p>
        </div>
      </div>
    </Html>
  );
}
