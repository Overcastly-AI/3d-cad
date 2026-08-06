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
 * a round node marks a vertex (a point), a diamond marks an edge (a curve), an
 * upright square marks a face (a plane you can sketch on), and a HOLLOW ring
 * marks a centre — the drafting centre-mark, for a point that is derived from a
 * circular edge rather than being a vertex of the body (a bore mouth, a boss
 * rim). A filled dot and a ring are told apart at a glance, which is the whole
 * job: on a bored face the two kinds sit millimetres apart. The transparent hit
 * area is a comfortable ≥24px target for mouse and touch.
 */
import type { ButtonHTMLAttributes } from "react";

import { cx } from "../cx";

export interface PickNodeProps extends Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "aria-label"
> {
  /**
   * Vertex = round point mark; edge = diamond curve mark; face = upright
   * square; center = hollow ring (a circular edge's centre).
   */
  shape?: "vertex" | "edge" | "face" | "center";
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
          "block h-3 w-3 ring-2 transition duration-fast",
          // AT REST THE RETICLE RECEDES (SEL-1 A7). It used to sit at full
          // strength, which is how a bored face came to wear a blanket of
          // bright dots over the geometry the modeller is trying to read —
          // the founder's "too many to see what you are clicking" (FB-8),
          // stated as chrome rather than as picking. Since SEL-1 A2 the drawn
          // surface itself is the primary hit-test, so these marks are no
          // longer how you aim: they are the keyboard focus target, the
          // screen-reader name and the touch tap target (spec §5). Chrome that
          // is not the primary affordance should not out-shout the model.
          //
          // Only the OPACITY moves, and only at rest. The hit area stays a
          // full 24px (WCAG 2.5.8) — this is deliberately not a size cut,
          // because a smaller target would trade one founder complaint for a
          // worse one — and hover / focus-visible / selected all return to
          // full strength, so the mark still answers the moment you address it.
          selected
            ? "opacity-100"
            : "opacity-50 group-hover/pn:opacity-100 group-focus-visible/pn:opacity-100",
          shape === "vertex"
            ? "rounded-full"
            : shape === "center"
              ? "rounded-full border-2 bg-transparent"
              : shape === "face"
                ? "rounded-none"
                : "rotate-45 rounded-none",
          shape === "center"
            ? selected
              ? "border-brass ring-carbide"
              : "border-mist ring-carbide group-hover/pn:border-brass-hover group-hover/pn:ring-anvil group-focus-visible/pn:border-brass-hover"
            : selected
              ? "bg-brass ring-carbide"
              : "bg-mist ring-carbide group-hover/pn:bg-brass-hover group-hover/pn:ring-anvil group-focus-visible/pn:bg-brass-hover",
        )}
      />
    </button>
  );
}
