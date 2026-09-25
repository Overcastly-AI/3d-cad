/**
 * A PICK MARK WHOSE SUBJECT IS BEHIND THE MATERIAL — drawn, not deleted.
 *
 * ## The defect this exists for (board item #76)
 *
 * A product audit modelled a gearbox housing and filleted THREE of four
 * corners without noticing, catching it only from the volume. The mechanism is
 * this component's whole reason to exist: when a pick mark's subject is behind
 * the body, `PickNode`'s `occluded` state draws **nothing at all**
 * (`opacity-0`). So "this edge is behind the part" and "this edge does not
 * exist" are the same picture, and a modeller counting four corners and seeing
 * three marks has no way to tell which they are looking at. Measured on the
 * housing at 1280x800 with fillet armed: 4 of 24 edge marks were invisible for
 * this reason, with nothing on screen to say so.
 *
 * ## Why a dashed hairline, and why that is the whole design
 *
 * Because it is not a UI convention — it is the audience's own. Every drafting
 * standard in the world draws an edge you cannot see as a **hidden line**:
 * same geometry, broken stroke. Our users read that before they read anything
 * we could write, so the cue needs no legend, no tooltip, no copy and no
 * colour of its own. It stays inside the app's single accent (brass, the
 * selection language) and spends its distinctiveness on TREATMENT rather than
 * on hue, which is what keeps a viewport full of them quiet.
 *
 * The alternative considered and rejected was a floating "select other" list
 * on hover — what Fusion and Plasticity do. It is a good idea and it is the
 * NEXT wave, not this one: it is a new chrome surface over the hero, it needs
 * copy and a key binding, and it would not have fixed any of the three
 * measured defects, because the marks still collide underneath it.
 *
 * ## It is a DRAWING, never a control
 *
 * It carries no handler, no tab stop and no accessible name, and it never opts
 * into pointer events — the slot `PickMark` plants it in is inert and this
 * stays that way. That is load-bearing rather than tidy: the reason a buried
 * mark must not take the pointer is that the pixel it sits on belongs to the
 * face the modeller can SEE, and a mark that answers there is how "click the
 * front wall" came to open the bottom one. The reachable route to a buried
 * subject is the keyboard, which `PickNode` already keeps open — it stays in
 * the tab order with its name, and focus restores it at full strength.
 *
 * It is also positioned ABSOLUTELY within the slot, so it contributes no
 * layout. `PickMark`'s slot centres on its own box; a ghost that took part in
 * that box would move every mark by half its own height.
 */
import { color } from "@loft/design/tokens";

/** Which entity this ghost stands for — matches `PickNode`'s `shape`. */
export type BuriedMarkShape = "vertex" | "edge" | "face" | "center";

export interface BuriedMarkProps {
  /**
   * The entity kind, so a buried mark reads as the same KIND of thing as its
   * live twin: a diamond is still a curve, a square is still a plane. Losing
   * that would trade one ambiguity for another.
   */
  shape?: BuriedMarkShape;
}

/**
 * Hidden-line weights, in the units of the 24x24 box every mark occupies.
 *
 * The dash is deliberately short (2.2 on, 2.2 off). A long dash on a glyph
 * this small resolves to two or three marks and reads as a broken shape rather
 * than as a hidden line; at 2.2 the 12 px glyph carries eight or nine, which is
 * the cadence a drawing uses.
 */
const STROKE_WIDTH = 1.25;
const DASH = "2.2 2.2";

/**
 * Below full strength, because a buried subject is INFORMATION rather than an
 * invitation — it must be findable when looked for and must not compete with
 * the live marks beside it, which are the ones the pointer can actually use.
 * On `carbide` (the viewport ground) brass at 0.62 still clears AA legibility
 * at hairline weight; the halo below is what carries it over a light machined
 * face, the same two-tone reasoning `PickNode`'s own reticle uses.
 */
const GHOST_OPACITY = 0.62;
const HALO_OPACITY = 0.38;
const HALO_WIDTH = 2.75;

/** The glyph path for each entity kind, centred in a 24-unit box. */
function glyph(shape: BuriedMarkShape): React.ReactElement {
  if (shape === "edge") {
    // A diamond: the curve mark, matching `PickNode`'s rotated square.
    return <path d="M12 5.2 L18.8 12 L12 18.8 L5.2 12 Z" />;
  }
  if (shape === "face") {
    // An upright square: a plane you can address.
    return <rect x="5.8" y="5.8" width="12.4" height="12.4" />;
  }
  // Vertex and centre are both points; the ring is the drafting centre-mark.
  return <circle cx="12" cy="12" r="6.2" />;
}

export function BuriedMark({ shape = "vertex" }: BuriedMarkProps) {
  const path = glyph(shape);
  return (
    <svg
      aria-hidden
      // Absolute inside the slot so it adds nothing to the box `PickMark`
      // centres on, and inert so the surface underneath keeps the pixel.
      style={{
        position: "absolute",
        left: "50%",
        top: "50%",
        width: 24,
        height: 24,
        transform: "translate(-50%, -50%)",
        pointerEvents: "none",
        overflow: "visible",
      }}
      viewBox="0 0 24 24"
      data-buried-ghost={shape}
    >
      {/*
        Two passes of the SAME path: a dark halo first, the brass hidden line
        over it. The model is light machined aluminum and the ground is near
        black, and a single stroke cannot carry both — this is the two-tone
        reticle argument applied to a hairline. The halo is drawn solid, not
        dashed, so it never reads as a second broken line of its own.
      */}
      <g
        fill="none"
        stroke={color.carbide}
        strokeWidth={HALO_WIDTH}
        strokeOpacity={HALO_OPACITY}
        strokeLinejoin="round"
      >
        {path}
      </g>
      <g
        fill="none"
        stroke={color.brass}
        strokeWidth={STROKE_WIDTH}
        strokeOpacity={GHOST_OPACITY}
        strokeDasharray={DASH}
        strokeLinejoin="round"
      >
        {path}
      </g>
    </svg>
  );
}
