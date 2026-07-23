import { readFile, stat } from "node:fs/promises";

import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
  TEST_PASSWORD,
  uniqueEmail,
} from "./support";

/**
 * BACKLOG #8 — the Phase 1 exit gate. The roadmap's acceptance loop
 * (login → sketch → extrude → edit param → export) driven end to end through
 * the real browser against the real stack (gateway + documents + geometry, no
 * mocks) with NO API shortcuts for the user-facing steps: a real registration,
 * a part created from the register UI, a plane picked, a rectangle drawn and
 * dimensioned by keyboard, an extrude authored from the workspace, the solid
 * rendered with real OCCT mass properties, the extrude param edited live, and
 * both files (STEP + STL) exported and asserted byte-real. Closing this is the
 * signal to advance to Phase 2.
 */

/** The lit aluminium solid + B-rep edges paint far more shades than ground. */
async function expectRenderedBody(page: Page): Promise<void> {
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
}

/** The z-extent of the rendered body (mm) — an XY extrude's distance. */
async function bodyDepth(page: Page): Promise<number> {
  const extents = await page.getByTestId("prop-extents").innerText();
  const parts = extents.split("×").map((p) => Number.parseFloat(p.trim()));
  return parts[parts.length - 1] ?? Number.NaN;
}

/** The body volume (mm³) — the cell carries its label + unit, so parse. */
async function bodyVolume(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  const match = text.match(/[\d,]+(?:\.\d+)?/);
  return match ? Number.parseFloat(match[0].replace(/,/g, "")) : Number.NaN;
}

/** Enter sketch mode on a datum plane. */
async function enterSketch(page: Page, plane: "XY" | "XZ" | "YZ") {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId(`plane-${plane}`).click();
  await expect(page.getByTestId("sketch-step")).toHaveText(`On ${plane}`);
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
}

/**
 * Build a plane-mm → screen-px mapper by reading the DRO at two screen points
 * with snap off (0.01 mm readings). With it, clicks land on EXACT millimetre
 * coordinates — the drawn rectangle IS 40 × 25, so the driving dimensions
 * solve with zero movement. Mirrors the constraints spec's calibrator.
 */
async function calibratePlane(
  page: Page,
  s1: { x: number; y: number },
  s2: { x: number; y: number },
): Promise<(pt: { x: number; y: number }) => { x: number; y: number }> {
  await page.keyboard.press("g"); // snap off for raw readings
  {
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
  await page.keyboard.press("g"); // snap back on for drawing
  const kx = (s2.x - s1.x) / (p2.x - p1.x);
  const ky = (s2.y - s1.y) / (p2.y - p1.y);
  return (pt) => ({
    x: s1.x + (pt.x - p1.x) * kx,
    y: s1.y + (pt.y - p1.y) * ky,
  });
}

async function clickPlane(
  page: Page,
  at: (pt: { x: number; y: number }) => { x: number; y: number },
  pt: { x: number; y: number },
) {
  const px = at(pt);
  await page.mouse.click(px.x, px.y);
}

/**
 * Draw a 40 × 25 mm rectangle and dimension it: horizontal + vertical on two
 * edges, coincident at the shared corner, and the two DRIVING dimensions
 * (40, 25). Leaves the sketch persisted and solved. `s1`/`s2` calibrate the
 * plane; they differ by viewport so the sketch lands on-screen at each width.
 */
async function sketchDimensionedRectangle(
  page: Page,
  s1: { x: number; y: number },
  s2: { x: number; y: number },
): Promise<void> {
  const at = await calibratePlane(page, s1, s2);

  // Draw the rectangle exactly: (0,0) → (40,25), four CCW lines (closed loop).
  await page.keyboard.press("r");
  await clickPlane(page, at, { x: 0, y: 0 });
  await clickPlane(page, at, { x: 40, y: 25 });
  await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
  await page.keyboard.press("Escape"); // back to the select tool

  // Horizontal on the bottom line — the first constraint persists the sketch.
  await clickPlane(page, at, { x: 20, y: 0 });
  await page.keyboard.press("h");
  await expect(page.getByTestId("glyph-0")).toHaveText("H");

  // Vertical on the right line.
  await clickPlane(page, at, { x: 40, y: 12.5 });
  await page.keyboard.press("v");
  await expect(page.getByTestId("glyph-1")).toHaveText("V");

  // Coincident at the shared bottom-right corner (two clicks cycle the stack).
  await clickPlane(page, at, { x: 40, y: 0 });
  await clickPlane(page, at, { x: 40, y: 0 });
  await page.keyboard.press("c");
  await expect(page.getByTestId("glyph-2")).toHaveText("C");

  // Driving dimension 40 on the bottom edge (the inline mm editor).
  await clickPlane(page, at, { x: 20, y: 0 });
  await page.keyboard.press("d");
  const input = page.getByTestId("dimension-input");
  await expect(input).toBeVisible();
  await input.fill("40");
  await input.press("Enter");
  await expect(page.getByTestId("glyph-3")).toHaveText("40");

  // Driving dimension 25 on the right edge.
  await clickPlane(page, at, { x: 40, y: 12.5 });
  await page.keyboard.press("d");
  await expect(input).toBeVisible();
  await input.fill("25");
  await input.press("Enter");
  await expect(page.getByTestId("glyph-4")).toHaveText("25");

  // Finish the sketch; the tree solves.
  await page.getByTestId("sketch-save").click();
  // The strip closes only after the sketch solve round-trips back — 30s (matches
  // the sibling eval-status wait) so a slow solve under CPU load isn't read as a
  // stuck transition.
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
    timeout: 30_000,
  });
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
}

/**
 * The whole exit-gate loop, parameterised by the plane calibration points so
 * it runs at both widths. Returns the part id for any follow-up assertions.
 */
async function runFullFlow(
  page: Page,
  s1: { x: number; y: number },
  s2: { x: number; y: number },
): Promise<void> {
  // 1) Register a fresh account through the sign-in sheet (real keystrokes).
  const email = uniqueEmail();
  await page.goto("/");
  await expect(page).toHaveURL(/\/sign-in$/);
  await page.getByTestId("auth-mode-register").click();
  await page.getByTestId("auth-email").fill(email);
  await page.getByTestId("auth-password").fill(TEST_PASSWORD);
  await page.getByTestId("auth-password").press("Enter");

  // 2) Land on the parts home; create a part from the register UI.
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByTestId("session-email")).toHaveText(email);
  await page.getByTestId("create-part-name").fill("Baseplate");
  await page.getByTestId("create-part-name").press("Enter");
  const row = page.getByTestId("part-row").filter({ hasText: "Baseplate" });
  await expect(row).toBeVisible();

  // Before a body exists the EXPORT strip is absent (no tree yet).
  await row.getByTestId("part-open").click();
  await expect(page).toHaveURL(/\/parts\/[0-9a-f-]+$/);
  await expect(page.getByTestId("part-name")).toHaveText("Baseplate");

  // 3) Pick a plane, draw + dimension the rectangle (real clicks + keys).
  await enterSketch(page, "XY");
  await sketchDimensionedRectangle(page, s1, s2);

  // Sketch-only tree: the EXPORT strip is present but honestly disabled.
  await expect(page.getByTestId("part-export-idle")).toBeVisible();
  await expect(page.getByTestId("part-export-status")).toHaveText("No body");
  await expect(page.getByTestId("part-export-step")).toBeDisabled();

  // 4) Extrude the profile from the workspace (keyboard-first: 10 mm, Enter).
  const extrudeAction = page.getByTestId("new-extrude");
  // Extrude enables only once the sketch solve round-trips back (canExtrude =
  // hasSolvedSketch) — 30s so a slow solve under load isn't misread as a broken
  // button; a genuinely never-enabling button still fails at 30s.
  await expect(extrudeAction).toBeEnabled({ timeout: 30_000 });
  await extrudeAction.click();
  await expect(page.getByTestId("extrude-editor")).toBeVisible();
  await expect(page.getByTestId("extrude-distance")).toHaveValue("10");
  await page.getByTestId("extrude-distance").press("Enter");

  // 5) The body renders and its mass properties reach the inspector: a
  //    40 × 25 × 10 = 10,000 mm³ solid, exactly what was modeled.
  // The extrude feature + evaluated body arrive via a geometry eval round-trip
  // (POST feature → tree refetch → evaluation) — 30s under contention.
  await expect(page.getByTestId("feature-row")).toHaveCount(2, {
    timeout: 30_000,
  });
  // The inspector mounts only once bodyProperties land (mass-props eval
  // round-trip) — 30s, matching the sketch-on-face body-inspector waits.
  await expect(page.getByTestId("body-inspector")).toBeVisible({
    timeout: 30_000,
  });
  await expectRenderedBody(page);
  await expect(page.getByTestId("prop-volume")).toContainText("10,000");
  await expect(page.getByTestId("prop-extents")).toContainText("40 × 25 × 10");
  expect(await bodyDepth(page)).toBeCloseTo(10, 3);

  // 6) Edit the extrude param live: 10 → 20 mm; the body deepens.
  await page.getByTestId("feature-select-1").click();
  await expect(page.getByTestId("extrude-distance")).toHaveValue("10");
  await page.getByTestId("extrude-distance").fill("20");
  await page.getByTestId("extrude-distance").press("Enter");
  await expect
    .poll(() => bodyDepth(page), { timeout: 30_000 })
    .toBeCloseTo(20, 3);
  await expectRenderedBody(page);
  expect(await bodyVolume(page)).toBeGreaterThan(15_000); // 40×25×20 = 20,000

  // 7) Export STEP — a real ISO-10303-21 part-21 file of the MODELED body.
  await expect(page.getByTestId("part-export-controls")).toBeVisible();
  await expect(page.getByTestId("part-export-status")).toHaveText("Ready");
  const stepDownload = page.waitForEvent("download");
  await page.getByTestId("part-export-step").click();
  const step = await stepDownload;
  expect(step.suggestedFilename()).toMatch(/\.step$/);
  const stepContent = await readFile(await step.path(), "utf-8");
  expect(stepContent.startsWith("ISO-10303-21")).toBe(true);
  expect(stepContent).toContain("END-ISO-10303-21");
  await expect(page.getByTestId("part-export-status")).toHaveText("Ready");
  await expect(page.getByTestId("part-export-error")).toHaveCount(0);

  // 8) Export STL — the faceted binary mesh, keyboard-only (focus + Enter).
  await page.getByTestId("part-export-stl").focus();
  const stlDownload = page.waitForEvent("download");
  await page.keyboard.press("Enter");
  const stl = await stlDownload;
  expect(stl.suggestedFilename()).toMatch(/\.stl$/);
  const { size } = await stat(await stl.path());
  expect(size).toBeGreaterThan(0);
}

test.describe("Phase 1 exit gate — full flow", () => {
  test("register → part → sketch → extrude → edit → export STEP + STL", async ({
    page,
  }) => {
    await runFullFlow(page, { x: 700, y: 620 }, { x: 1000, y: 420 });
    // Founder shot: the finished part, body + inspector + EXPORT strip.
    await page.mouse.move(1400, 900); // park the cursor off the model
    await page.screenshot({ path: `${SCREENSHOT_DIR}/full-flow-desktop.png` });
  });
});

test.describe("Phase 1 exit gate — small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("full loop holds at 1280×800; founder screenshot", async ({ page }) => {
    await runFullFlow(page, { x: 560, y: 520 }, { x: 840, y: 360 });
    // The viewport stays the hero even flanked by tree + inspector.
    const box = await page.getByTestId("viewport").boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(560);
    // Park clear of the bottom-right reference cube (viewport makeover).
    await page.mouse.move(1080, 770);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/full-flow-laptop.png` });
  });
});

test.describe("Phase 1 exit gate — touch viewport smoke", () => {
  test.use({ hasTouch: true, viewport: { width: 1024, height: 768 } });

  test("the modeled body exports from a touch profile", async ({ page }) => {
    // Auth + geometry are a fixture here (a separate spec proves authoring);
    // this smoke proves the export affordance works under a touch profile.
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Touch plate");
    const sketch = await page.request.post(
      `/api/v1/parts/${part.id}/features`,
      {
        data: {
          name: "Sketch1",
          feature: {
            type: "sketch",
            version: 1,
            params: {
              plane: { kind: "datum_plane", plane: "XY" },
              entities: [
                {
                  id: "e1",
                  kind: "line",
                  start: { x: 0, y: 0 },
                  end: { x: 40, y: 0 },
                },
                {
                  id: "e2",
                  kind: "line",
                  start: { x: 40, y: 0 },
                  end: { x: 40, y: 25 },
                },
                {
                  id: "e3",
                  kind: "line",
                  start: { x: 40, y: 25 },
                  end: { x: 0, y: 25 },
                },
                {
                  id: "e4",
                  kind: "line",
                  start: { x: 0, y: 25 },
                  end: { x: 0, y: 0 },
                },
              ],
              constraints: [],
            },
          },
          expected_tree_version: 0,
        },
        headers: { Authorization: `Bearer ${account.token}` },
      },
    );
    const sketchBody = (await sketch.json()) as {
      feature: { id: string };
      tree_version: number;
    };
    await page.request.post(`/api/v1/parts/${part.id}/features`, {
      data: {
        name: "Extrude1",
        feature: {
          type: "extrude",
          version: 1,
          params: {
            profile: { kind: "feature", feature_id: sketchBody.feature.id },
            distance_mm: 10,
            operation: "add",
            direction: "normal",
          },
        },
        expected_tree_version: sketchBody.tree_version,
      },
      headers: { Authorization: `Bearer ${account.token}` },
    });

    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByTestId("prop-volume")).toContainText("10,000");

    // Tap the STEP cell — a real download over a touch context.
    const download = page.waitForEvent("download");
    await page.getByTestId("part-export-step").tap();
    const file = await download;
    expect(file.suggestedFilename()).toMatch(/\.step$/);
  });
});
