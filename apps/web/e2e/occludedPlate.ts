import { expect, type Locator, type Page } from "@playwright/test";

import { seedOccludedEdgePlate } from "./partSeed";
import { litPoints } from "./reachability";
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
