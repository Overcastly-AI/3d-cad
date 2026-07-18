/**
 * A pickable node projected into the viewport — the DOM-in-canvas target the
 * measurement overlay places at every snappable vertex and edge. Rendered
 * through drei `Html` so it is a real button: keyboard focusable, screen-reader
 * named, and e2e-drivable, with zero chrome so it reads as a scribed mark, not
 * UI (the same posture as the constraint glyphs).
 *
 * A two-tone reticle so the mark stays legible over BOTH the light machined
 * body faces and the dark ground: a bright core reads on the ground, its dark
 * halo ring reads on the aluminum — visible either way, quiet at rest. It takes
 * the brass accent on hover/focus and a brass fill when selected — the
 * selection language of the rest of the app. The shape encodes the entity kind:
 * a round node marks a vertex (a point), a diamond marks an edge (a curve), and
 * an upright square marks a face (a plane you can sketch on). The transparent
 * hit area is a comfortable ≥24px target for mouse and touch.
 */
import type { ButtonHTMLAttributes } from "react";

import { cx } from "../cx";

export interface PickNodeProps extends Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "aria-label"
> {
  /** Vertex = round point mark; edge = diamond curve mark; face = upright square. */
  shape?: "vertex" | "edge" | "face";
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
        // A fixed 24px transparent hit area (WCAG 2.5.8 target size) around a
        // small scribed reticle — easy to click or tap without a large dot
        // cluttering the model, and independent of any padding collapse.
        "group/pn grid h-6 w-6 place-items-center rounded-full",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass",
        className,
      )}
      {...rest}
    >
      <span
        aria-hidden
        className={cx(
          // 12px core + a 2px halo ring: the two-tone reticle that survives
          // both the light body faces and the dark ground.
          "block h-3 w-3 ring-2 transition-colors duration-fast",
          shape === "vertex"
            ? "rounded-full"
            : shape === "face"
              ? "rounded-none"
              : "rotate-45 rounded-none",
          selected
            ? "bg-brass ring-carbide"
            : "bg-mist ring-carbide group-hover/pn:bg-brass-hover group-hover/pn:ring-anvil group-focus-visible/pn:bg-brass-hover",
        )}
      />
    </button>
  );
}
