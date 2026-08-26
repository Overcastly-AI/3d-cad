import type { HTMLAttributes } from "react";

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
 * FORM. It RECEDES at rest, because at rest it is not the affordance — the
 * drawn arrow underneath it is, and two brass rings at the same point would be
 * one too many. What sits here at rest is a faint collar: enough to say the tip
 * is a place you may take hold of, quiet enough that the arrow stays the
 * picture. Hover, focus and grab bring it forward in one step each, and the
 * transparent 24px hit area (WCAG 2.2 SC 2.5.8) is constant through all of
 * them — the target never moves or shrinks, only its ink changes.
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
}

export function AxisGrip({
  value,
  min,
  max,
  valueText,
  grabbed = false,
  className,
  ...rest
}: AxisGripProps) {
  return (
    <div
      role="slider"
      tabIndex={0}
      aria-valuenow={value}
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuetext={valueText}
      data-grabbed={grabbed ? "true" : "false"}
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
          // Rest: a quiet collar around the drawn arrowhead. Hover/focus: the
          // full accent. Grabbed: the hover accent plus a filled core, so the
          // held state is distinguishable from the merely-addressed one
          // without moving anything.
          grabbed
            ? "border-brass-hover bg-brass-hover/30"
            : "border-brass/40 group-hover/grip:border-brass group-focus-visible/grip:border-brass",
        )}
      />
    </div>
  );
}
