/**
 * A pickable node projected into the viewport — the DOM-in-canvas target the
 * measurement overlay places at every snappable vertex and edge. Rendered
 * through drei `Html` so it is a real button: keyboard focusable, screen-reader
 * named, and e2e-drivable, with zero chrome so it reads as a scribed mark, not
 * UI (the same posture as the constraint glyphs).
 *
 * Quiet at rest, brass-ringed on hover/focus, brass-filled when selected — the
 * selection language of the rest of the app. The shape encodes the entity kind:
 * a round node marks a vertex (a point), a diamond marks an edge (a curve).
 */
import type { ButtonHTMLAttributes } from "react";

import { cx } from "../cx";

export interface PickNodeProps extends Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "aria-label"
> {
  /** Vertex = round point mark; edge = diamond curve mark. */
  shape?: "vertex" | "edge";
  /** Chosen as a measurement target — brass fill + `aria-pressed`. */
  selected?: boolean;
  /** Required: the target's accessible name (e.g. "Vertex at 10, 20, 30 mm"). */
  "aria-label": string;
}

export function PickNode({
  shape = "vertex",
  selected = false,
  className,
  type,
  ...rest
}: PickNodeProps) {
  return (
    <button
      type={type ?? "button"}
      aria-pressed={selected}
      className={cx(
        // A generous transparent hit area around a small scribed mark, so the
        // node is easy to click without a large visible dot cluttering the model.
        "group/pn grid place-items-center rounded-full p-1.5",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass",
        className,
      )}
      {...rest}
    >
      <span
        aria-hidden
        className={cx(
          "block h-2.5 w-2.5 border transition-colors duration-fast",
          shape === "vertex" ? "rounded-full" : "rotate-45 rounded-none",
          selected
            ? "border-brass bg-brass"
            : "border-gauge bg-carbide group-hover/pn:border-brass-hover group-hover/pn:bg-anvil group-focus-visible/pn:border-brass-hover",
        )}
      />
    </button>
  );
}
