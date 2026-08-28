import { expect, type Locator, type Page } from "@playwright/test";

import { seedOccludedEdgePlate } from "./partSeed";
import { litPoints, type Point } from "./reachability";
import {
  createPartViaApi,
  distinctCanvasColors,
  seedSession,
  waitForFrames,
} from "./support";

/**
 * THE TWO-BODY OCCLUSION FIXTURE, shared by every spec that asks what a HIDDEN
 * body does to a pick.
 *
 * Extracted from `pick-affordance.spec.ts` when `qa-sel6-verify.spec.ts` needed
 * the same framing and the same "which row is the wall" discovery: two copies of
 * a fixture that pins screen pixels is two chances for the two specs to be
 * measuring different frames while reporting the same units.
 */

/**
 * The two-body fixture, framed FRONT-ON and pinned.
 *
 * `seedOccludedEdgePlate` puts a 40 × 20 × 40 wall at y = 0…20 and a
 * 60 × 20 × 10 plate at y = 30…50, so from the front view the wall sits exactly
 * between the camera and the middle of the plate. Every screen-pixel number
 * measured on this fixture is only comparable between runs because the fit is
 * pinned here.
 */
export async function openOccludedPlate(page: Page): Promise<Locator> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Wall and plate");
  await seedOccludedEdgePlate(page, account.token, part.id);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("prop-volume")).toContainText(/\d/, {
    timeout: 30_000,
  });
  const viewport = page.getByTestId("viewport");
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
    .toBeGreaterThan(24);
  await page.getByTestId("view-front").click();
  await viewport.evaluate((node) => {
    node.dataset["fitRect"] = "";
  });
  await page.getByTestId("view-fit").click();
  await expect(viewport).not.toHaveAttribute("data-fit-rect", "", {
    timeout: 20_000,
  });
  await waitForFrames(page, 6);
  await expect(page.getByTestId("body-row")).toHaveCount(2, {
    timeout: 20_000,
  });
  return viewport;
}

/** Cycle a body's eye to a wanted state (solid → ghost → hidden → solid). */
export async function setBodyMode(
  page: Page,
  index: number,
  mode: string,
): Promise<void> {
  const row = page.getByTestId("body-row").nth(index);
  for (let i = 0; i < 4; i += 1) {
    if ((await row.getAttribute("data-visibility")) === mode) return;
    await page.getByTestId(`body-visibility-${index}`).click();
  }
  await expect(row).toHaveAttribute("data-visibility", mode);
}

/**
 * Which body row is the WALL — the one in FRONT — DISCOVERED, never hardcoded.
 *
 * A kernel ordinal is not a contract, so the row is found by measurement: hide
 * each body in turn and count the lit silhouette that remains. In the front
 * view the plate is 60 × 10 mm and the wall 40 × 40 mm, so hiding the WALL
 * leaves a much smaller lit region than hiding the plate (measured 135 vs 625
 * points at `step: 24`). The caller asserts the two counts are far enough apart
 * for that to be a decision rather than a coin flip.
 */
export async function litAfterHiding(
  page: Page,
  index: number,
): Promise<number> {
  await setBodyMode(page, index, "hidden");
  await waitForFrames(page, 6);
  const count = (await litPoints(page, { step: 24 })).length;
  await setBodyMode(page, index, "solid");
  await waitForFrames(page, 6);
  return count;
}

/**
 * WHERE AN ENTITY IS, read off its own accessible name.
 *
 * Both overlay grammars — `Edge 7, line, centred at x, y, z millimetres` and
 * `Planar face 7, centred at x, y, z millimetres` — carry the OCCT position in
 * the same clause, which is the only thing about a mark that is a contract: its
 * kernel ordinal is not. Every "which body / which face" decision in these
 * specs is derived from this rather than hardcoded.
 */
export function labelCentroid(label: string): {
  x: number;
  y: number;
  z: number;
} {
  const parts = label.match(
    /centred at (-?[\d.]+), (-?[\d.]+), (-?[\d.]+) millimetres/,
  );
  expect(parts, `a located label: ${label}`).not.toBeNull();
  const [x, y, z] = [1, 2, 3].map((i) =>
    Number.parseFloat((parts ?? [])[i] ?? "NaN"),
  ) as [number, number, number];
  expect(
    Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(z),
    `a numeric position in: ${label}`,
  ).toBe(true);
  return { x, y, z };
}

/**
 * WHICH BODY AN ENTITY BELONGS TO, read off its own accessible name.
 *
 * `seedOccludedEdgePlate` puts the wall at OCCT y = 0…20 and the plate at
 * y = 30…50, so the y of any mid-span or centroid says which solid it is —
 * without hardcoding a kernel ordinal, which is not a contract.
 */
export function labelIsWall(label: string): boolean {
  return labelCentroid(label).y < 25;
}

/** A screen-space axis-aligned rect in PAGE pixels — `page.mouse` space. */
export interface ScreenRect {
  x0: number;
  x1: number;
  y0: number;
  y1: number;
}

/** Shrink a rect on all four sides; a NEGATIVE `by` grows it. */
export function insetRect(rect: ScreenRect, by: number): ScreenRect {
  return {
    x0: rect.x0 + by,
    x1: rect.x1 - by,
    y0: rect.y0 + by,
    y1: rect.y1 - by,
  };
}

/** Strictly inside — a point ON the boundary does not count as covered. */
export function containsPoint(rect: ScreenRect, point: Point): boolean {
  return (
    point.x > rect.x0 &&
    point.x < rect.x1 &&
    point.y > rect.y0 &&
    point.y < rect.y1
  );
}

export interface BodyScreenRects {
  /** Where the WALL — the body in FRONT — covers the screen. */
  wall: ScreenRect;
  /** Where the PLATE — the body BEHIND — covers the screen. */
  plate: ScreenRect;
  /**
   * Screen distance between the wall's FRONT (OCCT y = 0) and BACK (y = 20)
   * face-mark centres — the depth parallax this derivation must NOT have.
   * Reported so a caller can print the number that licensed its region.
   */
  parallaxPx: number;
}

/**
 * The most depth parallax {@link bodyScreenRects} will derive a rect through.
 *
 * The number is not arbitrary and it is not slack: for a box tilted by θ about
 * the view-up axis the silhouette is 40·cos θ + 20·sin θ wide while the centroid
 * bounding box is 40·cos θ, so the rect's error and the measured front/back
 * parallax are THE SAME 20·sin θ. The tolerance therefore IS the worst-case
 * error of the region, in pixels, and 12 px is half the census grid step — the
 * rect cannot be wrong by a whole sample column.
 *
 * Measured both ways rather than assumed. In the pinned front view, across five
 * runs: **0.45, 0.71, 0.76, 1.63, 2.19 px** — the view is axis-aligned to about
 * a third of a degree, and the spread is the fit's own settle, not the spec's.
 * Its negative control is the 45 degree front-top view `pick-affordance.spec.ts`
 * tilts into through the reference cube: **166.77 px**, refused by name. So the
 * guard has ~5x headroom below and ~14x above, and it has been SEEN to fire.
 */
export const FRONT_ON_TOLERANCE_PX = 12;

/**
 * WHERE EACH BODY COVERS THE SCREEN, from the product's own face marks.
 *
 * WHY THIS EXISTS, because it is the seat of a trap that has already been paid
 * for once. A spec asking an OCCLUSION question needs the REGION the occluder
 * covers, and until ORTHO-1 (`9a04a6a`) it was possible to skip that and use a
 * whole-frame SHARE instead: under the perspective front view this fixture used
 * to open in, the nearer wall was magnified enough to cover all but a ~0.8 mm
 * sliver of the 60 mm plate, so "the plate answered at all" and "the plate
 * answered THROUGH the wall" were within 0.6 % of each other and a 5 % ceiling
 * separated them. A parallel projection removes the magnification, so the
 * plate's two 10 mm overhangs became their true size and answer 68 of 1003
 * points (6.8 %) with nothing wrong — the app is correct and the SHARE stopped
 * meaning what it was standing in for. The region is the quantity that was
 * always intended; a third consumer should take it from here rather than
 * re-derive a proxy for it.
 *
 * HOW, and why the marks rather than the camera. Each `shell-face-N` mark is a
 * DOM node seated on its face's centroid, so front-on the wall's four SIDE
 * faces (x = 10, x = 50, z = 0, z = 40) put a mark centre exactly on each of
 * the four silhouette edges. Measured against the same rect projected through
 * the live camera (`projectionMatrix · matrixWorldInverse`, the arithmetic
 * `projection.spec.ts` uses): agreement of **0.2 px or better on all four
 * edges** — 424.9 vs 424.7, 1175.1 vs 1175.3, 127.9 vs 127.8, 878.1 vs 878.2.
 * So the marks are exact here and cost no duplicated projection maths.
 *
 * AND THE GUARD, which is the whole reason this can be shared. A centroid
 * bounding box is the silhouette ONLY while the view has no depth parallax; in
 * an oblique view it UNDER-claims, which is the silent direction — a genuine
 * leak would fall outside the rect and pass. So the helper measures the
 * parallax it depends on, from the wall's own front and back face marks — the
 * quantity a parallel front-on projection sets to zero — and REFUSES above
 * {@link FRONT_ON_TOLERANCE_PX} rather than returning a rect that is quietly
 * too small. Requires the shell pick to be armed so the marks exist.
 */

export async function bodyScreenRects(page: Page): Promise<BodyScreenRects> {
  const nodes = page.locator('[data-testid^="shell-face-"]');
  await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
  const seats: { centre: Point; y: number; wall: boolean }[] = [];
  for (const node of await nodes.all()) {
    const label = (await node.getAttribute("aria-label")) ?? "";
    const box = await node.boundingBox();
    expect(box, `a seated face mark: ${label}`).not.toBeNull();
    if (box === null) continue;
    seats.push({
      centre: { x: box.x + box.width / 2, y: box.y + box.height / 2 },
      y: labelCentroid(label).y,
      wall: labelIsWall(label),
    });
  }
  const rectOf = (which: boolean): ScreenRect => {
    const centres = seats.filter((s) => s.wall === which).map((s) => s.centre);
    expect(
      centres.length,
      `${which ? "the wall" : "the plate"} offers the four side-face marks its rect is derived from`,
    ).toBeGreaterThanOrEqual(4);
    return {
      x0: Math.min(...centres.map((c) => c.x)),
      x1: Math.max(...centres.map((c) => c.x)),
      y0: Math.min(...centres.map((c) => c.y)),
      y1: Math.max(...centres.map((c) => c.y)),
    };
  };
  const wallSeats = [...seats.filter((s) => s.wall)].sort((a, b) => a.y - b.y);
  const front = wallSeats[0];
  const back = wallSeats[wallSeats.length - 1];
  expect(front, "the wall's nearest face is on offer").toBeDefined();
  expect(back, "the wall's farthest face is on offer").toBeDefined();
  if (front === undefined || back === undefined) {
    throw new Error("the wall's faces are not on offer");
  }
  // Both ends must be REAL ends, or the parallax below is measured between two
  // faces at the same depth and says nothing about the projection.
  expect(
    back.y - front.y,
    `the wall's front and back faces must be a depth apart, got y=${front.y} and y=${back.y}`,
  ).toBeGreaterThan(1);
  const parallaxPx = Math.hypot(
    front.centre.x - back.centre.x,
    front.centre.y - back.centre.y,
  );
  expect(
    parallaxPx,
    `this region is a centroid bounding box, which is the silhouette ONLY without depth ` +
      `parallax: the wall's y=${front.y} and y=${back.y} face marks are ${parallaxPx.toFixed(2)} px ` +
      `apart, so the view is oblique and the rect would UNDER-claim`,
  ).toBeLessThan(FRONT_ON_TOLERANCE_PX);
  return { wall: rectOf(true), plate: rectOf(false), parallaxPx };
}

/**
 * Discover the wall's row, asserting the two silhouettes are tellable apart.
 *
 * Returns both rows so a caller can address "the body in front" and "the body
 * behind" by role rather than by index.
 */
export async function discoverWallRow(
  page: Page,
): Promise<{ wall: number; plate: number; lit: number[] }> {
  const lit = [await litAfterHiding(page, 0), await litAfterHiding(page, 1)];
  const wall = (lit[0] as number) < (lit[1] as number) ? 0 : 1;
  expect(
    Math.max(...lit) / Math.max(1, Math.min(...lit)),
    `the two bodies must be tellable apart by silhouette: ${lit.join(" vs ")} lit points`,
  ).toBeGreaterThan(1.5);
  return { wall, plate: 1 - wall, lit };
}
