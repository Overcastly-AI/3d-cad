import { useEffect, useState } from "react";

import { cx } from "../cx";

/**
 * THE INDETERMINATE WAIT — one carriage, one bed, one honest number.
 *
 * Built for UI-REVIEW 2026-08-27 P1-B: a STEP import held the whole register on
 * a static twelve-pixel sentence with no `role="progressbar"` anywhere and no
 * animation on any descendant, so a long parse was indistinguishable from a
 * hung tab. Measured then: a 52 KB fixture took 3.35 s against a 16 MiB client
 * ceiling — over 300x that file — which is a long time to look at a frozen
 * screen and wonder. This is the thing every long operation seats from now on,
 * so the answer is made once.
 *
 * ## Why indeterminate, and why a carriage
 *
 * The client cannot know when the work ends: the bytes leave in one POST and a
 * kernel parses a solid model on the far side, and no byte count predicts that.
 * A bar that FILLS would be a prediction, so it would be a lie — and a
 * progress bar that lies is worse than none, because the user plans around it.
 * A machine tool cutting has a carriage travelling its bed: something is
 * plainly moving, and the distance covered claims nothing. That is exactly the
 * available truth, in the register's own vernacular.
 *
 * The carriage RECIPROCATES rather than wrapping, so there is no frame where it
 * teleports back to the start, and it stays wholly inside the bed — the travel
 * distance is derived from its own width in `tokens.ts`, never transcribed.
 *
 * ## The elapsed readout is not decoration, it is the liveness proof
 *
 * A CSS animation keeps running when the main thread is wedged, so a moving
 * carriage cannot actually distinguish "working" from "hung" — the very
 * question the finding is about. A counter driven by React state can: it stops
 * the instant the app stops. So it is always rendered, in both motion modes,
 * and it is what carries the reduced-motion path rather than being an extra.
 *
 * ## Accessibility contract
 *
 * `role="progressbar"` with an accessible name, and DELIBERATELY no
 * `aria-valuenow` — that omission is how ARIA spells "indeterminate", and
 * supplying a number would be the same lie as a filling bar. `aria-valuetext`
 * is likewise omitted: ARIA only defines it alongside `aria-valuenow`.
 *
 * Under `prefers-reduced-motion` the carriage does not move; it spans the bed
 * as a plain brass rule (a stationary 28 % segment would read as "28 % done",
 * which is a claim this component must never make), and the seconds do the
 * talking.
 *
 * ## Cancel lives in the CALLER, not here
 *
 * Only the caller holds the `AbortController`, knows what withdrawing means
 * (an upload can be abandoned; a committed server-side write cannot), and can
 * name the verb in its own vocabulary — "Stop import" is not "Cancel export".
 * A slot rendered here for a button this component cannot wire would be chrome
 * that only decorates, which the design mandate calls a defect outright. So
 * this draws the state and nothing else; the caller composes its own verb
 * beside it. If a second caller wants the identical pairing, THAT is when the
 * pairing gets extracted (extract on the second real use).
 */
export interface ProgressTrackProps {
  /**
   * What is working, in the user's words — this becomes the accessible name,
   * e.g. "Importing nema17-front-plate.step". Required: an unnamed progressbar
   * announces "busy" and nothing else, which is the pixels problem again.
   */
  label: string;
  /** Test hook, forwarded to the `progressbar` element itself. */
  "data-testid"?: string;
  className?: string;
}

/** How often the elapsed readout advances (ms). One second; nothing finer reads. */
const TICK_MS = 1000;

export function ProgressTrack({
  label,
  "data-testid": testId,
  className,
}: ProgressTrackProps) {
  const [seconds, setSeconds] = useState(0);

  // Mount time is the operation's start: the component is rendered when the
  // work begins and unmounted when it ends, so there is no separate "running"
  // flag that could disagree with what is on screen.
  useEffect(() => {
    const started = Date.now();
    const id = window.setInterval(
      () => setSeconds(Math.floor((Date.now() - started) / 1000)),
      TICK_MS,
    );
    return () => window.clearInterval(id);
  }, []);

  return (
    <span
      data-testid={testId}
      className={cx("inline-flex min-w-0 items-center gap-2", className)}
    >
      {/*
        THE BED IS THE PROGRESSBAR, not a wrapper around it. `progressbar` is a
        leaf role — assistive technology does not expose its contents — so the
        elapsed readout below is a SIBLING rather than a child, or it would be
        visible only as pixels, which is the finding this component answers.

        `overflow-hidden` keeps the travel honest if the derived distance is
        ever edited by hand.
      */}
      <span
        role="progressbar"
        aria-label={label}
        data-testid={testId === undefined ? undefined : `${testId}-bed`}
        className="relative h-track min-w-progress grow overflow-hidden bg-hairline"
      >
        <span
          aria-hidden="true"
          data-testid={testId === undefined ? undefined : `${testId}-carriage`}
          className={cx(
            "absolute inset-y-0 left-0 w-carriage bg-brass",
            "motion-safe:animate-travel",
            // Stationary, it must not imply a fraction — so it fills the bed.
            "motion-reduce:w-full motion-reduce:opacity-70",
          )}
        />
      </span>
      {/* Driven by React, so it stops when the app does — see the docstring. */}
      <span
        data-testid={testId === undefined ? undefined : `${testId}-elapsed`}
        className="shrink-0 font-data text-2xs tabular-nums text-gauge"
      >
        {seconds}s<span className="sr-only"> elapsed</span>
      </span>
    </span>
  );
}
