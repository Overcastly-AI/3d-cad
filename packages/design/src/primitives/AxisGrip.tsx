import type { HTMLAttributes, Ref } from "react";

import { cx } from "../cx";

/**
 * THE GRIP — the thing you take hold of on a direct-manipulation handle.
 *
 * It is the DOM half of a WebGL manipulator, placed over the handle's tip
 * through drei `Html`, the same DOM-in-canvas posture the measurement pick
 * nodes use and for the same three reasons: a real focusable element is
 * keyboard-operable, screen-reader nameable, and e2e-drivable, none of which a
 * `<mesh>` with a raycast can ever be. A drag affordance QA cannot drive is a
 * drag affordance that rots silently.
 *
 * IT IS A SLIDER, and that is not a costume. `role="slider"` is exactly what a
 * one-dimensional continuous value with a min, a max and arrow-key stepping
 * IS — so the value, its bounds and its spoken form travel with the element
 * instead of being narrated in a label, and `getByRole("slider", { name })` is
 * the natural handle for a test. The consumer owns the pointer maths and the
 * key semantics; this owns the target, the states, and the ring.
 *
 * FORM. AT REST THERE IS NO COLLAR AT ALL (CRAFT-7). There used to be a faint
 * one, and it was the weaker of two rings claiming to be the affordance: the
 * drawn arrowhead beneath it, at 0.92 opacity, and this at 0.40. Once the whole
 * drawn arrow became the target — the hit sleeve — the arrow IS the affordance,
 * and a second accessory saying the same thing more quietly is the accessory
 * Chanel's rule says to take off before leaving the house. The collar returns
 * the instant the pointer or the keyboard ADDRESSES the gauge, which is when
 * "you are on it" is new information rather than a repetition.
 *
 * The transparent 24px hit area (WCAG 2.2 SC 2.5.8) is constant through every
 * state — the target never moves or shrinks, only its ink changes. That is what
 * makes removing the rest ink safe: nothing about where you can press changed.
 */
export interface AxisGripProps extends Omit<
  HTMLAttributes<HTMLDivElement>,
  "aria-label" | "aria-valuenow" | "aria-valuemin" | "aria-valuemax"
> {
  /** Required: what this handle drives, e.g. "Extrude depth". */
  "aria-label": string;
  /** Current value in the consumer's own units. */
  value: number;
  min: number;
  max: number;
  /** Spoken/inspected form of the value, e.g. "12.5 mm". */
  valueText: string;
  /** True while the pointer holds it — the grabbed state. */
  grabbed?: boolean;
  /**
   * True while the gauge is ADDRESSED — hovered, or holding keyboard focus.
   *
   * Driven by the owner rather than by `:hover` on this element, because the
   * hover that matters is the hover on the whole INSTRUMENT: the pointer is
   * usually on the sleeve, halfway down the shaft, and a collar that only lit
   * when the pointer reached the arrow's point would tell the user the opposite
   * of the truth about where the target is.
   */
  addressed?: boolean;
  ref?: Ref<HTMLDivElement>;
}

export function AxisGrip({
  value,
  min,
  max,
  valueText,
  grabbed = false,
  addressed = false,
  className,
  ref,
  ...rest
}: AxisGripProps) {
  return (
    <div
      ref={ref}
      role="slider"
      tabIndex={0}
      aria-valuenow={value}
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuetext={valueText}
      data-grabbed={grabbed ? "true" : "false"}
      data-addressed={addressed || grabbed ? "true" : "false"}
      className={cx(
        // A constant 24px transparent target around a 12px collar.
        "group/grip grid h-6 w-6 place-items-center rounded-full",
        "touch-none select-none",
        grabbed ? "cursor-grabbing" : "cursor-grab",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass",
        className,
      )}
      {...rest}
    >
      <span
        aria-hidden
        className={cx(
          "block h-3 w-3 rounded-full border-2",
          "transition-colors duration-fast motion-reduce:transition-none",
          // Rest: NOTHING. The drawn arrowhead is the affordance and this would
          // be a second ring saying so more quietly. Addressed (hover or
          // keyboard focus): the full accent. Grabbed: the accent plus a filled
          // core, so the held state is distinguishable from the merely-
          // addressed one without moving anything.
          grabbed
            ? "border-brass-hover bg-brass-hover/30"
            : addressed
              ? "border-brass"
              : "border-transparent group-hover/grip:border-brass group-focus-visible/grip:border-brass",
        )}
      />
    </div>
  );
}
