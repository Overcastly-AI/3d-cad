/**
 * The hit sleeve's band refs, and the frame a NEW band is owed.
 *
 * `ParametricGauge` lays one DOM band per drawn spine segment, and only its
 * frame loop places them: a band mounts at `display: none` and is shown by the
 * next frame that measures the projection. The bands live inside drei `Html`,
 * which commits its children in a SEPARATE React root, and the viewport is
 * `frameloop="demand"`. So the commit that mounts a band can land after the
 * last frame the change asked for, and nothing renders again until an
 * unrelated change does. The band stays hidden, and a finger on that stretch
 * of the drawn arc hits the canvas.
 *
 * Measured before this existed (e2e `gauge-touch`, "revolve arc grown after it
 * is drawn"): 130 -> 300 deg left 45 of 80 bands hidden and 60 -> 180 left 32
 * of 48, 3 runs of 3 — every band the growth added. The same race on the
 * gauge's first mount is the CI red where the shaft midpoint resolved to
 * `viewport`.
 *
 * Only an UN-PLACED band asks for a frame, so a re-commit of bands that are
 * already laid out costs nothing.
 */
export function attachBand(
  bands: (HTMLDivElement | null)[],
  index: number,
  node: HTMLDivElement | null,
  invalidate: () => void,
): void {
  bands[index] = node;
  if (node !== null && node.style.display === "none") invalidate();
}
