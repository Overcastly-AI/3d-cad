/**
 * HOW A PICK MARK IS PLANTED IN THE SCENE — one drei `Html` host for every
 * `PickNode`, with an INERT wrapper.
 *
 * ## The defect this exists to remove (MEASURE-PROXY-1, T-14)
 *
 * drei's `Html` (non-`transform` mode) renders an absolutely-positioned div
 * around its children and centres it with `translate3d(-50%,-50%,0)`. That div
 * inherits `pointer-events: auto`, has NO handler of its own, and takes the
 * BOX of what it wraps — while a `PickNode` is `rounded-full`, so its hit
 * region is a Ø24 circle inside that 24x24 box. The corners of every mark were
 * therefore a pointer target that did nothing at all, and a NEIGHBOUR's corner
 * lands squarely on other marks: measured on the audit's own motor-mount plate
 * (150 x 80 x 8, R10 corners, 4 x M6.6 + Ø25 bore — 26 vertex + 39 edge proxies,
 * exactly T-14's counts), `measure-edge-4`, `-5` and `-6` each had another
 * mark's wrapper corner sitting on their own centre, and a real
 * `page.mouse.click` there registered NOTHING. That is T-14's sentence
 * verbatim: "a click at the exact centre of `measure-edge-4`'s bounding box
 * registered no selection at all".
 *
 * With the wrapper inert those pixels fall through to the canvas, where the
 * band answers — measured at the same three points: edge 6 for its own mark,
 * and the entity actually in front for the two whose edge is buried. A dead
 * pointer surface becomes the real hit-test, which is the only honest thing
 * for "you aimed 12 px diagonally off the mark".
 *
 * ## Why a component and not thirteen `style` props
 *
 * `ExtrudeDragHandle` already carries this fix, with a comment describing the
 * same mechanism ("without it the tag's box sits over the grip's 24 px target
 * and swallows the press"). It was applied there, to one instance, and the
 * thirteen mark sites never got it — which is the design-system rule this repo
 * reviews as a defect: fix the primitive, never the instance. So the wrapper
 * is a component, and `PickNode` opts ITSELF back in (`pointer-events-auto`),
 * because a control that cannot be pointed at is not a control and that is the
 * primitive's business rather than each caller's.
 *
 * NB `<Html pointerEvents="none">` — drei's own prop — is NOT the same thing
 * and does nothing here: read in the shipped source, it is applied to
 * `transformInnerStyles`, which is only rendered on the `transform` branch.
 * The `style` prop is what reaches the wrapper in the mode we use.
 */
import { Html } from "@react-three/drei";
import type { ReactNode } from "react";

/** Stable identity, so drei is not handed a new style object every render. */
const INERT_WRAPPER = { pointerEvents: "none" } as const;

export interface PickMarkProps {
  /** Scene-space anchor for the mark. */
  position: [number, number, number];
  /**
   * drei's depth→z-index band for this class of mark. Overlays use it to keep
   * a vertex above an edge mark and both below the HUD.
   */
  zIndexRange: [number, number];
  /** The mark itself — a `PickNode`, which opts back into pointer events. */
  children: ReactNode;
}

export function PickMark({ position, zIndexRange, children }: PickMarkProps) {
  return (
    <Html
      position={position}
      center
      zIndexRange={zIndexRange}
      style={INERT_WRAPPER}
    >
      {children}
    </Html>
  );
}
