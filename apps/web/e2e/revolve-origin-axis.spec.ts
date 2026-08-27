import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * REACH-1 — revolve about a WORLD ORIGIN AXIS, with no centerline drawn.
 *
 * The capability shipped in the kernel and in the gateway contract
 * (`RevolveAxis`'s `origin_axis` member) and no user could reach it: the axis
 * select offered only the profile sketch's own line entities, so a plain closed
 * rectangle defaulted to a PROFILE EDGE and quietly built a disc instead of the
 * turn that was meant. This spec is the reachability oracle
 * (`scripts/check-ui-parity.py` reads the e2e suite), so EVERY modelling step
 * here is real browser input: the plane is picked, the rectangle is drawn with
 * the rect tool at calibrated millimetre coordinates, and the revolve is
 * authored from the editor. Nothing about the revolve is seeded over the API.
 *
 * The part is a WASHER: a 20 x 10 mm rectangle on the XZ datum, its near edge
 * 20 mm clear of the Z axis, turned 360 degrees about origin Z. Pappus gives
 * the volume exactly — 2 * pi * Rbar * A with Rbar = 30 and A = 200 — and the
 * bounding box (80 x 80 x 10) is what proves the axis was Z and not X: about X
 * the same profile sweeps a 20-wide, 80-tall tube, a shape this assertion
 * cannot be satisfied by.
 */

/** Profile: u (=X) from 20 to 40 mm, v (=Z) from 5 to 15 mm, on the XZ datum. */
const NEAR_MM = 20;
const FAR_MM = 40;
const BOTTOM_MM = 5;
const TOP_MM = 15;
const AREA_MM2 = (FAR_MM - NEAR_MM) * (TOP_MM - BOTTOM_MM);
const RBAR_MM = (NEAR_MM + FAR_MM) / 2;
/** Pappus's second theorem: the swept volume of a full turn. */
const WASHER_VOLUME = 2 * Math.PI * RBAR_MM * AREA_MM2;

/**
 * The lit body + B-rep edges paint far more shades than bare ground.
 *
 * NOT `support.ts`'s `expectRenderedModel`, though it looks like the same
 * assertion with a stronger precondition. Measured: that helper first waits for
 * `tessellation-status`, which lives in `InspectorPanel` — a panel this state
 * does not mount (the part page shows `BodyInspector` instead), so it times out
 * on an element that will never exist over a body that has already rendered.
 * `revolve-ui.spec.ts` carries this same local check for the same reason.
 */
async function expectRenderedBody(page: Page): Promise<void> {
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
}

/** The body volume (mm^3) — the cell carries its label + unit, so parse. */
async function bodyVolume(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  const match = text.match(/[\d,]+(?:\.\d+)?/);
  return match ? Number.parseFloat(match[0].replace(/,/g, "")) : Number.NaN;
}

/**
 * The body's three bounding extents (mm), in the readout's own order. The cell
 * carries its label and unit around the triple ("Extents / 80 × 80 × 10 / mm"),
 * so the triple is matched rather than split off the separator.
 */
async function bodyExtents(page: Page): Promise<number[]> {
  const text = await page.getByTestId("prop-extents").innerText();
  const match = text.match(
    /([\d,]+(?:\.\d+)?)\s*×\s*([\d,]+(?:\.\d+)?)\s*×\s*([\d,]+(?:\.\d+)?)/,
  );
  if (match === null) throw new Error(`no extents triple in: ${text}`);
  return match
    .slice(1)
    .map((part) => Number.parseFloat(part.replace(/,/g, "")));
}

/**
 * Build a plane-mm -> screen-px mapper by reading the DRO at two screen points
 * with snap off, so clicks afterwards land on EXACT millimetre coordinates.
 * (The full-flow and constraints specs each carry the same calibrator; the
 * sketcher has no test seam that would let one of them own it.)
 */
async function calibratePlane(
  page: Page,
  s1: { x: number; y: number },
  s2: { x: number; y: number },
): Promise<(pt: { x: number; y: number }) => { x: number; y: number }> {
  await page.keyboard.press("g"); // snap off for raw readings
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
  await page.keyboard.press("g"); // snap back on (1 mm grid) for drawing
  const kx = (s2.x - s1.x) / (p2.x - p1.x);
  const ky = (s2.y - s1.y) / (p2.y - p1.y);
  return (pt) => ({
    x: s1.x + (pt.x - p1.x) * kx,
    y: s1.y + (pt.y - p1.y) * ky,
  });
}

/**
 * Draw the washer's section on the XZ datum through the real sketcher and save
 * it. NO construction geometry: that absence is the whole point — before
 * REACH-1 this sketch had nothing correct to offer as an axis.
 */
async function drawSectionOnXZ(
  page: Page,
  s1: { x: number; y: number },
  s2: { x: number; y: number },
): Promise<void> {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XZ").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XZ");
  await expect(page.getByTestId("sketch-dro")).toBeVisible();

  const at = await calibratePlane(page, s1, s2);
  const click = async (pt: { x: number; y: number }) => {
    const px = at(pt);
    await page.mouse.click(px.x, px.y);
  };
  await page.keyboard.press("r");
  await click({ x: NEAR_MM, y: BOTTOM_MM });
  await click({ x: FAR_MM, y: TOP_MM });
  await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
  await page.keyboard.press("Escape");

  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
    timeout: 30_000,
  });
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
}

test.describe("REACH-1 — revolve about a world origin axis", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("a plain rectangle turns about origin Z with no centerline drawn", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Washer");
    await page.goto(`/parts/${part.id}`);
    await drawSectionOnXZ(page, { x: 560, y: 520 }, { x: 840, y: 360 });

    const revolveAction = page.getByTestId("new-revolve");
    await expect(revolveAction).toBeEnabled({ timeout: 30_000 });
    await revolveAction.click();
    await expect(page.getByTestId("revolve-editor")).toBeVisible();
    // Captured BEFORE the assertions on purpose: run this spec against a tree
    // with the origin group removed and this same shot is the "before" — the
    // axis cell proposing a profile edge — with the failure right behind it.
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/revolve-origin-axis-editor-1280.png`,
    });

    // The PROPOSAL: with no centerline in the sketch, the editor opens on the
    // in-plane origin axis rather than on one of the rectangle's own edges.
    const axis = page.getByTestId("revolve-axis");
    await expect(axis).toHaveValue("origin:Z");
    await expect(axis.locator("option").first()).toHaveText(
      "Z axis · through the origin",
    );
    // …and it is a turn the user can commit as-is, before touching anything.
    await expect(page.getByTestId("revolve-submit")).toBeEnabled();

    // NEGATIVE CONTROL: the origin axis NORMAL to the sketch plane (Y, for a
    // sketch on XZ) is offered — disabled, wearing the kernel's own refusal in
    // its label — rather than silently dropped.
    const normalAxis = axis.locator("option[value='origin:Y']");
    await expect(normalAxis).toHaveCount(1);
    await expect(normalAxis).toBeDisabled();
    await expect(normalAxis).toHaveText(
      "Y axis · not in the sketch plane — it is the plane normal",
    );
    // It is listed LAST: a refused axis is never in the proposal's seat.
    await expect(axis.locator("option").last()).toHaveText(
      /^Y axis · not in the sketch plane/,
    );

    await page.getByTestId("revolve-angle").press("Enter");
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("body-inspector")).toBeVisible();
    await expectRenderedBody(page);

    // Pappus: a full turn of a 20 x 10 section whose centroid orbits at R=30.
    const volume = await bodyVolume(page);
    expect(volume).toBeGreaterThan(WASHER_VOLUME * 0.995);
    expect(volume).toBeLessThan(WASHER_VOLUME * 1.005);
    // The bounding box is what names the AXIS: a washer 80 across and 10 thick.
    // Turned about X instead, the same section is 20 across and 80 tall.
    const extents = await bodyExtents(page);
    expect(extents).toHaveLength(3);
    expect(extents[0]).toBeCloseTo(2 * FAR_MM, 0);
    expect(extents[1]).toBeCloseTo(2 * FAR_MM, 0);
    expect(extents[2]).toBeCloseTo(TOP_MM - BOTTOM_MM, 0);

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/revolve-origin-axis-body-1280.png`,
    });

    // ROUND-TRIP: re-opening the feature reads the axis it was given back out
    // of the stored params. Before REACH-1 `formFromRevolveParams` seeded an
    // `origin_axis` revolve BLANK, so the feature could be opened and not saved.
    //
    // THE SAVE-ENABLED CHECK IS THE GATE HERE, NOT `toHaveValue` — measured, by
    // restoring the blank seed: a controlled <select> handed a value no option
    // carries leaves the browser's selectedIndex at 0, so `.value` reads back
    // "origin:Z" and the assertion below PASSES over a form whose state is "".
    // Only `revolve-submit`, which reads the form and not the DOM, went red.
    await page.getByTestId("feature-select-1").click();
    await expect(page.getByTestId("revolve-editor")).toBeVisible();
    await expect(page.getByTestId("revolve-axis")).toHaveValue("origin:Z");
    await expect(page.getByTestId("revolve-submit")).toBeEnabled();
  });
});
