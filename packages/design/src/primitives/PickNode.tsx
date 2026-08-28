/**
 * A pickable node projected into the viewport — the DOM-in-canvas target the
 * measurement overlay places at every snappable vertex and edge. Rendered
 * through drei `Html` so it is a real button: keyboard focusable, screen-reader
 * named, and e2e-drivable, with zero chrome so it reads as a scribed mark, not
 * UI (the same posture as the constraint glyphs).
 *
 * A two-tone reticle so the mark stays legible over BOTH the light machined
 * body faces and the dark ground: a bright core reads on the ground, its dark
 * halo ring reads on the aluminum — visible either way, and quiet at rest on
 * the surfaces that have a raycast of their own (`recede`). It takes
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
  /**
   * The mark is NOT the primary hit-test on this surface — the drawn geometry
   * behind it is — so it may rest quietly and come back on hover / focus /
   * selection. OFF by default, and that default is the safety property: an
   * overlay where this button is still the only thing listening keeps the mark
   * at full strength, because there it IS the aim affordance. See the opacity
   * block below for the measured contrast either way.
   */
  recede?: boolean;
  /**
   * NO PART OF THIS MARK'S ENTITY IS ADDRESSABLE FROM THE CURRENT CAMERA — it
   * is behind the material (PICKMARK-OCCLUDE-1).
   *
   * The mark then draws nothing and takes no pointer, because a diamond at full
   * strength over a face that hides its edge is a promise the hit-test refuses
   * to keep: measured on the audit's coupling, 13 of 21 marks pointed at
   * geometry the band would not give you, 5 of them silently handing back a
   * DIFFERENT edge. It is NOT hidden, though — `opacity-0` keeps the button in
   * the tab order with its accessible name intact, and focus brings it back at
   * full strength, so the keyboard and screen-reader route to a buried edge is
   * exactly as long as it was. `visibility:hidden` or `display:none` would take
   * that away, which is why neither is used.
   */
  occluded?: boolean;
  /** Required: the target's accessible name (e.g. "Vertex at 10, 20, 30 mm"). */
  "aria-label": string;
}

export function PickNode({
  shape = "vertex",
  selected = false,
  recede = false,
  occluded = false,
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
        // A buried mark is out of the pointer's way and out of the picture, and
        // still on the tab route. Focus restores both, so a keyboard user is
        // never sent to a control they cannot see.
        // `focus:`, not `focus-visible:`. Chromium's focus-visible heuristic
        // says NO to a programmatic `.focus()` that follows a mouse gesture,
        // and something that deliberately moves focus to a mark — a roving
        // tab-stop, a "go to edge" action, an AT — has just as much right to
        // see it as a Tab press does. Measured: with `focus-visible:` the
        // opacity stayed 0 after `element.focus()`.
        occluded
          ? "pointer-events-none opacity-0 focus:pointer-events-auto focus:opacity-100"
          : null,
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
          // AT REST THE RETICLE RECEDES — BUT ONLY WHERE IT IS NO LONGER THE
          // WAY YOU AIM (SEL-1 A7). It used to sit at full strength
          // everywhere, which is how a bored face came to wear a blanket of
          // bright dots over the geometry the modeller is trying to read — the
          // founder's "too many to see what you are clicking" (FB-8), stated as
          // chrome rather than as picking. SEL-1 A2 made the drawn SURFACE the
          // primary hit-test for the sketch-plane face pick, which is what
          // demotes the mark there to the keyboard focus target, the
          // screen-reader name and the touch tap target (spec §5).
          //
          // That demotion is per-surface, so the recession is too, and the
          // default stays OFF: on a surface where this button is still the sole
          // hit-test, dimming it would dim the aim affordance itself — the exact
          // trade A7 refuses. SEL-4 (2026-08-08) converted the remaining five —
          // fillet/chamfer edge, measure EDGES, shell/draft, instance-mate and
          // hole placement — so those now pass `recede` too. Measure VERTICES
          // deliberately do not: a projected point has no boundary to raycast,
          // so a 24 px square around it already IS the proximity test and this
          // button remains the only target there.
          //
          // WHERE IT DOES RECEDE, THE FLOOR IS MEASURED, NOT ESTIMATED. The
          // mark is two-tone: a `mist` core that carries it over the dark
          // ground, a `carbide` halo ring that carries it over the light
          // machined face. The ring is the weaker of the two, so it sets the
          // limit. Composited over `aluminum` (WCAG 1.4.11 non-text, 3:1):
          //
          //   100 %  10.07:1     60 %  3.86:1  <- here
          //    75 %   5.78:1     55 %  3.41:1
          //    65 %   4.44:1     50 %  2.98:1  <- FAILS the 3:1 floor
          //
          // and the core over `carbide` at 60 % measures 5.81:1 (5.49:1 against
          // the brightest point of the skylight glow). 60 % is therefore the
          // furthest this can recede and still be a control rather than a
          // suggestion — the first cut shipped 50 %, which is below the floor.
          //
          // Only the OPACITY moves, and only at rest. The hit area stays a full
          // 24px (WCAG 2.5.8) — deliberately not a size cut, because a smaller
          // target would trade one founder complaint for a worse one — and
          // hover / focus-visible / selected all return to full strength, so
          // the mark still answers the moment you address it.
          selected || !recede
            ? "opacity-100"
            : "opacity-60 group-hover/pn:opacity-100 group-focus-visible/pn:opacity-100",
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
