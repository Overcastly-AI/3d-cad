/**
 * Click or drag? — the one place the viewport decides whether a pointer
 * gesture placed a point / picked a curve, or panned the camera.
 *
 * FB-12 (founder, 2026-08-01: *"the line wouldn't even select"*). The rule used
 * to be a bare `if (e.delta > 4) return;` inlined at two call sites. Measured by
 * the QA pass driving real pointer travel:
 *
 *     0 px SELECTS · 1 · 2 · 3 · 4 SELECTS · 5 DEAD · 6 · 8 · 10 DEAD
 *
 * On a MacBook trackpad 5–10 px of drift between press and release is ordinary
 * — so ordinary clicks were being discarded, silently, and the product read as
 * broken. 4 px was below EVERY platform's drag threshold:
 *
 *   · the web itself: `click` is not distance-gated at all. A browser fires it
 *     whenever press and release share a target, however far the pointer moved;
 *   · Qt: `QApplication::startDragDistance()` — 10 px;
 *   · GTK: `gtk-dnd-drag-threshold` — 8 px;
 *   · Windows: `SM_CXDRAG` — 4 px at 96 dpi, i.e. 8 device px on a 2x display;
 *   · macOS AppKit drag hysteresis — conventionally ~5–10 pt.
 *
 * So 4 was not a considered value, it was the smallest one anybody uses,
 * applied in CSS px on top of a device that jitters.
 *
 * DISTANCE ALONE IS THE WRONG DISCRIMINATOR, which is why this is a function
 * and not a constant. The gesture we must keep rejecting is an orbit/pan, and
 * what actually distinguishes it is not that it is BIG — a nudge-pan can be
 * small — but that it is FAST and deliberate. A hand wobbling on a trackpad
 * moves slowly. So:
 *
 *   · under {@link CLICK_SLOP_PX} of travel it is a click, whatever the speed
 *     (nobody deliberately pans 12 px);
 *   · between that and {@link DRIFT_SLOP_PX} it is still a click IF it was
 *     slow — a shaky press, not a flick;
 *   · beyond that, or fast, it is a drag.
 *
 * The camera moved in every rejected case, which is the feedback: the view
 * visibly changed under the pointer. The pathological version — a discarded
 * click where NOTHING moved perceptibly — is what the 4 px rule produced and
 * what these numbers remove.
 */

/** Travel (CSS px) that is a click regardless of how fast it happened. */
export const CLICK_SLOP_PX = 12;

/**
 * Travel (CSS px) that is still a click if it happened SLOWLY. Twice the plain
 * slop: it covers a genuinely shaky press without reaching into the range where
 * a user would have seen the view move.
 */
export const DRIFT_SLOP_PX = 24;

/**
 * Speed (CSS px per millisecond) below which travel reads as hand tremor rather
 * than intent. A deliberate flick-pan runs ~1 px/ms; a wobble during a 150 ms
 * press covers its 20 px at ~0.13. 0.2 sits between them with room either side.
 */
export const DRIFT_SPEED_PX_PER_MS = 0.2;

export interface PointerGesture {
  /** Accumulated pointer travel between press and release (CSS px). */
  travelPx: number;
  /** Press duration (ms), or null when it was not recorded. */
  durationMs: number | null;
}

/**
 * True when this gesture should act on the model (place / pick / choose a
 * plane) rather than be swallowed as a camera move.
 */
export function isClick({ travelPx, durationMs }: PointerGesture): boolean {
  if (travelPx <= CLICK_SLOP_PX) return true;
  if (travelPx > DRIFT_SLOP_PX) return false;
  // No timing available (a synthetic event, or a release with no matching
  // press): fall back to distance alone rather than guessing at speed.
  if (durationMs === null || durationMs <= 0) return false;
  return travelPx / durationMs < DRIFT_SPEED_PX_PER_MS;
}
