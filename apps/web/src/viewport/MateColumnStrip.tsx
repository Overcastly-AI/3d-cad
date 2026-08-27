/**
 * UNDER CURSOR — the "select other" instrument for mate authoring (MATE-1).
 *
 * ## Why this exists at all
 *
 * A coincident mate joins two faces that end up touching, and in the audit's
 * S-15 fixture they touch already: a bracket seated on a plate has its bottom
 * face at the same plane as the plate's top. Look from above and the bracket
 * hides it; look from below and the plate hides it. Measured through the real
 * UI on that fixture — 528 pointer samples per camera, four cameras — the
 * bracket's bottom face was addressable at ZERO of them. There is no camera to
 * orbit to, so no amount of better aiming fixes it. What fixes it is admitting
 * that the ray under the cursor crosses SEVERAL faces and letting the modeller
 * say which. Every incumbent has this; we did not.
 *
 * ## The shape it takes, and why not a floating popup at the cursor
 *
 * Fusion puts its select-other next to the pointer. That is good for the eye
 * and bad here for a specific reason: a DOM element over the canvas swallows
 * pointer events, which is the exact class of defect MATE-1 is about. A list
 * that appears under the cursor either blocks the geometry it is describing or
 * disappears as you reach for it. So this docks — bottom-left, one seat, always
 * the same place — and the model keeps the middle of the frame (design mandate
 * §3: the viewport is the hero, chrome recedes).
 *
 * ## The device
 *
 * A section line. One hairline runs down the gutter — that is the ray — and
 * each face it pierces gets a tick, ordered near to far exactly as the ray
 * meets them. The tick you are aimed at is drawn heavy and brass; the rest are
 * hairline. It is not a dropdown dressed as CAD; it is the drawing a machinist
 * would sketch to explain the problem, which is the whole point of a section.
 *
 * Every row is a real `<button>`: hover or focus it and the viewport traces
 * that face, click it and the mate takes it. Nothing here is decorative — the
 * strip does not render at all unless the scene has registered a way to commit
 * a pick and there is more than one candidate to choose between (design mandate
 * §3a(c)).
 */
import { cx } from "@loft/design";
import { useCallback, type KeyboardEvent } from "react";

import {
  useMateColumnStore,
  type MateColumnEntry,
} from "../assembly/mateColumn";

export function MateColumnStrip() {
  const entries = useMateColumnStore((s) => s.entries);
  const depth = useMateColumnStore((s) => s.depth);
  const commit = useMateColumnStore((s) => s.commit);
  const setDepth = useMateColumnStore((s) => s.setDepth);
  const setAddressing = useMateColumnStore((s) => s.setAddressing);

  /**
   * Aiming at a row IS aiming, so the scene traces that face exactly as
   * pointing at it would. Without this the strip would be a list of names for
   * geometry you cannot see — and for a BURIED face, which you cannot see
   * anyway, that is the difference between a pick and a guess.
   */
  const aim = useCallback(
    (index: number) => {
      setDepth(index);
      setAddressing(true);
    },
    [setDepth, setAddressing],
  );

  const onKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        aim(depth + 1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        aim(depth - 1);
      }
    },
    [depth, aim],
  );

  // One candidate is not a choice, and a choice with no way to act on it is
  // decoration. Either way: draw nothing.
  if (commit === null || entries.length < 2) return null;

  const pick = (entry: MateColumnEntry, index: number) => {
    aim(index);
    commit(entry);
  };

  return (
    <div
      data-testid="mate-column"
      data-depth={depth}
      data-count={entries.length}
      role="group"
      aria-label="Faces under the cursor, nearest first"
      onKeyDown={onKeyDown}
      // Leaving the strip stops aiming, exactly as leaving the geometry does —
      // one rule for "what is lit", two surfaces it can be aimed from.
      onMouseLeave={() => setAddressing(false)}
      onBlur={() => setAddressing(false)}
      className="absolute bottom-3 left-3 z-hud w-[15rem] max-w-[calc(100%-1.5rem)] border border-hairline bg-anvil/95 px-2.5 py-2 shadow-float backdrop-blur-sm"
    >
      <div className="flex items-baseline justify-between">
        <span className="font-display text-2xs uppercase tracking-[0.18em] text-brass">
          Under cursor
        </span>
        <span className="font-display text-2xs tabular-nums text-gauge">
          {depth + 1}/{entries.length}
        </span>
      </div>

      {/*
        The section. `before:` draws the ray — one continuous hairline down the
        gutter — and each row hangs its own tick off it, so the list reads as
        depth rather than as a menu.
      */}
      <div className="relative mt-1.5 pl-3 before:absolute before:bottom-1.5 before:left-[3px] before:top-1.5 before:w-px before:bg-etch before:content-['']">
        {entries.map((entry, index) => {
          const on = index === depth;
          return (
            <button
              key={`${entry.instanceId}:${entry.faceIndex}`}
              type="button"
              data-testid={`mate-column-row-${index}`}
              data-instance={entry.instanceId}
              data-face={entry.faceIndex}
              data-active={on ? "true" : "false"}
              aria-pressed={on}
              aria-label={`${entry.instanceName}, ${entry.faceLabel}`}
              onMouseEnter={() => aim(index)}
              onFocus={() => aim(index)}
              onClick={() => pick(entry, index)}
              className={cx(
                "group/mc relative flex w-full items-baseline justify-between gap-2 py-0.5 text-left outline-none",
                "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brass",
              )}
            >
              {/* The tick: this face, where the ray meets it. */}
              <span
                aria-hidden
                className={cx(
                  "absolute -left-3 top-1/2 -translate-y-1/2 transition-colors duration-fast",
                  on ? "h-0.5 w-2.5 bg-brass" : "h-px w-2 bg-etch",
                  "group-hover/mc:bg-brass-hover",
                )}
              />
              <span
                className={cx(
                  "truncate font-body text-xs transition-colors duration-fast",
                  on
                    ? "text-brass"
                    : "text-mist group-hover/mc:text-brass-hover",
                )}
              >
                {entry.instanceName}
              </span>
              <span
                className={cx(
                  "shrink-0 font-display text-2xs tabular-nums transition-colors duration-fast",
                  on ? "text-brass" : "text-gauge",
                )}
              >
                {entry.centroidLabel}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
