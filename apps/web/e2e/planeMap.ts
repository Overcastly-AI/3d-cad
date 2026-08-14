import { expect, type Page } from "@playwright/test";

/**
 * Plane-mm → screen-px, measured from the running app rather than assumed.
 *
 * The sketcher's camera is normal-on but its distance (and therefore its scale)
 * depends on the plane — a datum sheet frames differently from a 400 mm face —
 * so no spec can hard-code a mm-per-pixel number. The technique
 * `constraints.spec` established: turn the GRID OFF, read the DRO at two known
 * screen points, and derive the affine map from those two readings. With the
 * grid off the DRO reports the raw plane point, so the map is exact.
 *
 * DRY NOTE: `constraints.spec.ts` and `sketch-snap.spec.ts` each carry an older
 * private copy of this helper. This module is the seam they should fold into
 * next time either is opened (BACKLOG P3) — a third copy was the line at which
 * "two specs disagreeing about where 25 mm is" stopped being hypothetical.
 */

export type PlaneMapper = (pt: { x: number; y: number }) => {
  x: number;
  y: number;
};

/** Enter the sketcher on an origin datum and wait for the sheet to be live. */
export async function enterSketch(
  page: Page,
  plane: "XY" | "XZ" | "YZ",
): Promise<void> {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId(`plane-${plane}`).click();
  await expect(page.getByTestId("sketch-step")).toHaveText(`On ${plane}`);
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
}

/**
 * Calibrate the plane↔screen map from two screen points. Leaves the grid ON
 * (it is toggled off only for the readings), so a caller that needs the grid
 * off for a snap discriminator presses `g` itself and says why.
 */
export async function calibratePlane(
  page: Page,
  s1: { x: number; y: number },
  s2: { x: number; y: number },
): Promise<PlaneMapper> {
  await page.keyboard.press("g"); // grid off for raw readings
  {
    // The first raycast after entry can report a stale point while the camera
    // is still easing in; wait until two identical readings agree.
    let last: number | null = null;
    await expect
      .poll(
        async () => {
          await page.mouse.move(s1.x + 2, s1.y);
          await page.mouse.move(s1.x, s1.y);
          const value = Number.parseFloat(
            await page.getByTestId("dro-x").innerText(),
          );
          const stable =
            last !== null && Number.isFinite(value) && value === last;
          last = value;
          return stable;
        },
        { timeout: 15_000 },
      )
      .toBe(true);
  }
  const read = async (
    sx: number,
    sy: number,
    distinctFromX?: number,
  ): Promise<{ x: number; y: number }> => {
    await page.mouse.move(sx, sy);
    await expect
      .poll(async () => {
        const value = Number.parseFloat(
          await page.getByTestId("dro-x").innerText(),
        );
        return (
          Number.isFinite(value) &&
          (distinctFromX === undefined ||
            Math.abs(value - distinctFromX) > 1e-9)
        );
      })
      .toBe(true);
    return {
      x: Number.parseFloat(await page.getByTestId("dro-x").innerText()),
      y: Number.parseFloat(await page.getByTestId("dro-y").innerText()),
    };
  };
  const p1 = await read(s1.x, s1.y);
  const p2 = await read(s2.x, s2.y, p1.x);
  await page.keyboard.press("g"); // grid back on
  const kx = (s2.x - s1.x) / (p2.x - p1.x);
  const ky = (s2.y - s1.y) / (p2.y - p1.y);
  return (pt) => ({
    x: s1.x + (pt.x - p1.x) * kx,
    y: s1.y + (pt.y - p1.y) * ky,
  });
}

/** Move the pointer to a plane-mm point, optionally nudged by screen pixels. */
export async function hoverPlane(
  page: Page,
  at: PlaneMapper,
  pt: { x: number; y: number },
  nudgePx: { x: number; y: number } = { x: 0, y: 0 },
): Promise<void> {
  const px = at(pt);
  // Two moves: the first wakes the r3f raycast, the second is the reading.
  await page.mouse.move(px.x + nudgePx.x + 1, px.y + nudgePx.y + 1);
  await page.mouse.move(px.x + nudgePx.x, px.y + nudgePx.y);
}

/** Click a plane-mm point, optionally nudged by screen pixels. */
export async function clickPlane(
  page: Page,
  at: PlaneMapper,
  pt: { x: number; y: number },
  nudgePx: { x: number; y: number } = { x: 0, y: 0 },
): Promise<void> {
  const px = at(pt);
  await page.mouse.click(px.x + nudgePx.x, px.y + nudgePx.y);
}
