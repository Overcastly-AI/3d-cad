/**
 * Right-button drag vs. right-button CLICK — the discriminator the viewport
 * context menu is gated on (FINDINGS burn-down 2026-07-25 #4).
 *
 * The orbit rig binds the right button to PAN (three-stdlib `OrbitControls`
 * defaults `RIGHT: MOUSE.PAN`), and its own `contextmenu` handler only calls
 * `preventDefault()` — the event still bubbles to the container. Without this
 * gate every right-drag pan ends by popping the menu at the release point,
 * which no modeling tool does (Fusion 360 / Plasticity both open the menu only
 * on a right-button click that did not move the camera).
 *
 * The rule is the standard click-slop test: remember where the right button
 * went down, and treat the gesture as a drag once the pointer has travelled
 * past a few pixels — small enough that a hand-shake click still opens the
 * menu, large enough that any real pan suppresses it. Kept pure so it is
 * testable without a DOM.
 */

/** A pointer position in client (viewport) pixels. */
export interface PointerPoint {
  x: number;
  y: number;
}

/**
 * Click slop in CSS pixels. 4px is the conventional threshold (below a typical
 * hand tremor of a deliberate click, far below any useful pan).
 */
export const CONTEXT_MENU_DRAG_SLOP_PX = 4;

/**
 * True when the gesture that ended at `up` should COUNT AS A DRAG, i.e. the
 * context menu must stay shut. An unknown origin (`null` — the button went down
 * outside the viewport, or a keyboard/menu-key request) is treated as a click,
 * so the menu still opens.
 */
export function isDragGesture(
  down: PointerPoint | null,
  up: PointerPoint,
  slopPx: number = CONTEXT_MENU_DRAG_SLOP_PX,
): boolean {
  if (down === null) return false;
  return Math.hypot(up.x - down.x, up.y - down.y) > slopPx;
}
