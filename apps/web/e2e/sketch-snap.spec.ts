import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * Entity snapping in the sketcher (UI-W5 — the founder's "what about snapping
 * to a face or point? With control or command?").
 *
 * The polarity under test is the INVERSE of the phrasing: snapping is on by
 * default and Ctrl/Cmd suppresses it. And the thing actually asserted here is
 * HONESTY — that the mark at the cursor names the snap the click will take,
 * and that the point which lands in the persisted sketch is the point the mark
 * promised. A snap that grabs the wrong thing silently is worse than no snap.
 *
 * The discriminator throughout: the GRID snap is turned OFF (`g`) before every
 * snap assertion. With no grid, only an entity snap can put an exact whole
 * millimetre in the DRO — so `+40.00` under an off-target cursor is proof the
 * entity snap ran, not the grid. Real stack: gateway + documents + geometry.
 */

interface SketchEntityRow {
  id: string;
  kind: string;
  start?: { x: number; y: number };
  end?: { x: number; y: number };
}

async function enterSketch(page: Page, plane: "XY" | "XZ" | "YZ") {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId(`plane-${plane}`).click();
  await expect(page.getByTestId("sketch-step")).toHaveText(`On ${plane}`);
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
}

/**
 * Plane-mm → screen-px mapper (the technique `constraints.spec` established):
 * read the DRO at two screen points with the grid off, so later clicks land on
 * exact millimetre coordinates.
 */
async function calibratePlane(
  page: Page,
  s1: { x: number; y: number },
  s2: { x: number; y: number },
): Promise<(pt: { x: number; y: number }) => { x: number; y: number }> {
  await page.keyboard.press("g"); // grid off for raw readings
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
  await page.keyboard.press("g"); // grid back on for drawing
  const kx = (s2.x - s1.x) / (p2.x - p1.x);
  const ky = (s2.y - s1.y) / (p2.y - p1.y);
  return (pt) => ({
    x: s1.x + (pt.x - p1.x) * kx,
    y: s1.y + (pt.y - p1.y) * ky,
  });
}

type Mapper = (pt: { x: number; y: number }) => { x: number; y: number };

/** Move the pointer to a plane-mm point, optionally nudged by screen pixels. */
async function hoverPlane(
  page: Page,
  at: Mapper,
  pt: { x: number; y: number },
  nudgePx: { x: number; y: number } = { x: 0, y: 0 },
) {
  const px = at(pt);
  // Two moves: the first wakes the r3f raycast, the second is the reading.
  await page.mouse.move(px.x + nudgePx.x + 1, px.y + nudgePx.y + 1);
  await page.mouse.move(px.x + nudgePx.x, px.y + nudgePx.y);
}

async function clickPlane(
  page: Page,
  at: Mapper,
  pt: { x: number; y: number },
) {
  const px = at(pt);
  await page.mouse.click(px.x, px.y);
}

/**
 * A 40x25 rectangle plus a full-width line at y = 8 (for intersections).
 * y = 8 rather than the middle on purpose: the right edge's own MIDPOINT sits
 * at (40, 12.5) and outranks an intersection (the AutoCAD priority order, and
 * what `RANK` in snap.ts encodes), so a crossing near it resolves to the
 * midpoint. That is correct behaviour and the mark says so — it just makes a
 * mid-height crossing the wrong fixture for testing intersections.
 */
async function drawFixture(page: Page, at: Mapper) {
  await page.keyboard.press("r");
  await clickPlane(page, at, { x: 0, y: 0 });
  await clickPlane(page, at, { x: 40, y: 25 });
  await expect(page.getByTestId("sketch-save")).toContainText("4 entities");

  await page.keyboard.press("l");
  await clickPlane(page, at, { x: -6, y: 8 });
  await clickPlane(page, at, { x: 46, y: 8 });
  await expect(page.getByTestId("sketch-save")).toContainText("5 entities");
  await page.keyboard.press("Escape"); // back to select
}

const marker = (page: Page) => page.getByTestId("snap-marker");

test.describe("sketch entity snapping", () => {
  test("the mark names endpoint / midpoint / centre / intersection before the click", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Snap plate");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );
    await drawFixture(page, at);

    // A circle to give the set a centre to find. Centre (20,18), r 6.
    await page.keyboard.press("c");
    await clickPlane(page, at, { x: 20, y: 18 });
    await clickPlane(page, at, { x: 26, y: 18 });
    await expect(page.getByTestId("sketch-save")).toContainText("6 entities");

    // Grid OFF: from here on, any exact millimetre in the DRO can ONLY have
    // come from an entity snap.
    await page.keyboard.press("g");
    await expect(page.getByTestId("dro-snap")).toContainText("no grid");
    await page.keyboard.press("l"); // a placement tool, so snapping is live

    // ENDPOINT — aim 5 px off the (40,25) corner.
    await hoverPlane(page, at, { x: 40, y: 25 }, { x: -5, y: 4 });
    await expect(marker(page)).toHaveAttribute("data-snap-kind", "endpoint");
    await expect(marker(page)).toContainText("Endpoint");
    await expect(page.getByTestId("dro-x")).toHaveText("+40.00");
    await expect(page.getByTestId("dro-y")).toHaveText("+25.00");

    // MIDPOINT — the middle of the bottom edge, which is nowhere near a corner.
    await hoverPlane(page, at, { x: 20, y: 0 }, { x: 4, y: -4 });
    await expect(marker(page)).toHaveAttribute("data-snap-kind", "midpoint");
    await expect(marker(page)).toContainText("Midpoint");
    await expect(page.getByTestId("dro-x")).toHaveText("+20.00");
    await expect(page.getByTestId("dro-y")).toHaveText("+0.00");

    // CENTRE — the circle's centre, a point with no ink of its own.
    await hoverPlane(page, at, { x: 20, y: 18 }, { x: 5, y: 5 });
    await expect(marker(page)).toHaveAttribute("data-snap-kind", "center");
    await expect(marker(page)).toContainText("Centre");
    await expect(page.getByTestId("dro-y")).toHaveText("+18.00");

    // INTERSECTION — where the y=8 line crosses the right edge at (40,8).
    await hoverPlane(page, at, { x: 40, y: 8 }, { x: -4, y: 4 });
    await expect(marker(page)).toHaveAttribute(
      "data-snap-kind",
      "intersection",
    );
    await expect(marker(page)).toContainText("Intersection");
    await expect(page.getByTestId("dro-x")).toHaveText("+40.00");
    await expect(page.getByTestId("dro-y")).toHaveText("+8.00");
    // …and it names both curves it came from, so the claim is checkable.
    const sources =
      (await marker(page).getAttribute("data-snap-entities")) ?? "";
    expect(sources.split(" ")).toHaveLength(2);
  });

  test("Ctrl suppresses every snap — with the pointer standing still", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Snap plate");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );
    await drawFixture(page, at);

    await page.keyboard.press("g"); // grid off
    await page.keyboard.press("l");
    await hoverPlane(page, at, { x: 40, y: 25 }, { x: -6, y: 5 });
    await expect(marker(page)).toHaveAttribute("data-snap-kind", "endpoint");
    await expect(page.getByTestId("dro-x")).toHaveText("+40.00");

    // Hold Ctrl WITHOUT moving: the mark must go, or it would be asserting a
    // snap the next click will not take.
    await page.keyboard.down("Control");
    await expect(marker(page)).toHaveCount(0);
    await expect(page.getByTestId("dro-snap")).toContainText("held off");
    await expect(page.getByTestId("dro-x")).not.toHaveText("+40.00");

    // Releasing restores it, again with no pointer movement.
    await page.keyboard.up("Control");
    await expect(marker(page)).toHaveAttribute("data-snap-kind", "endpoint");
    await expect(page.getByTestId("dro-x")).toHaveText("+40.00");
  });

  test("Shift locks the aim to an axis through the open placement", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Snap plate");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 10, y: 10 }); // the anchor
    await page.keyboard.press("g"); // grid off, so only the lock can flatten y

    await page.keyboard.down("Shift");
    await hoverPlane(page, at, { x: 35, y: 14 });
    await expect(marker(page)).toHaveAttribute("data-snap-kind", "axis-h");
    await expect(marker(page)).toContainText("Horizontal");
    await expect(page.getByTestId("dro-y")).toHaveText("+10.00");
    await page.keyboard.up("Shift");

    // Released: the aim is free again and follows the pointer off the axis.
    await hoverPlane(page, at, { x: 35, y: 14 });
    await expect(marker(page)).toHaveCount(0);
    await expect(page.getByTestId("dro-y")).not.toHaveText("+10.00");
    await page.keyboard.press("Escape");
  });

  test("the point that lands in the saved sketch is the point the mark promised", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Snap plate");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );
    await drawFixture(page, at);

    // Grid OFF, then draw a diagonal by clicking NEAR (never on) two corners.
    // Without snapping those clicks would persist as fractional millimetres.
    await page.keyboard.press("g");
    await page.keyboard.press("l");
    await hoverPlane(page, at, { x: 0, y: 0 }, { x: 6, y: -5 });
    await expect(marker(page)).toHaveAttribute("data-snap-kind", "endpoint");
    await page.mouse.down();
    await page.mouse.up();
    await hoverPlane(page, at, { x: 40, y: 25 }, { x: -6, y: 5 });
    await expect(marker(page)).toHaveAttribute("data-snap-kind", "endpoint");
    await page.mouse.down();
    await page.mouse.up();
    await expect(page.getByTestId("sketch-save")).toContainText("6 entities");
    await page.keyboard.press("Escape");

    const featurePromise = page.waitForResponse(
      (r) =>
        r.url().includes(`/parts/${part.id}/features`) &&
        r.request().method() === "POST",
    );
    await page.getByTestId("sketch-save").click();
    expect((await featurePromise).status()).toBe(201);
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0);

    const treeResponse = await page.request.get(
      `/api/v1/parts/${part.id}/features`,
      { headers: { Authorization: `Bearer ${account.token}` } },
    );
    const treeBody = (await treeResponse.json()) as {
      features: Array<{ feature: { params: { entities: SketchEntityRow[] } } }>;
    };
    const entities = treeBody.features[0]?.feature.params.entities ?? [];
    const diagonal = entities[5];
    expect(diagonal?.kind).toBe("line");
    // Exact, not approximate: the snap resolved to the rectangle's own
    // endpoints, so the persisted coordinates ARE the corner coordinates.
    expect(diagonal?.start?.x).toBe(0);
    expect(diagonal?.start?.y).toBe(0);
    expect(diagonal?.end?.x).toBe(40);
    expect(diagonal?.end?.y).toBe(25);
  });
});

/**
 * Founder shots. Set `UIW5_SHOT=before` and run this against the PRE-change
 * tree to capture the honest "before" pair — the marker is never asserted
 * here, only the fixture and the hover, so the block runs on either tree. The
 * before pass captures one frame per width (the pre-change sketcher looks the
 * same at every hover: there was nothing to see).
 */
const BEFORE = process.env.UIW5_SHOT === "before";

test.describe("UI-W5 — founder shots", () => {
  for (const [label, width] of [
    ["1440", 1440],
    ["1366", 1366],
  ] as const) {
    test(`snap marks at ${label}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      const account = await seedSession(page);
      const part = await createPartViaApi(page, account.token, "Snap plate");
      await page.goto(`/parts/${part.id}`);
      await enterSketch(page, "XY");
      const at = await calibratePlane(
        page,
        { x: width / 2, y: 620 },
        { x: width / 2 + 260, y: 430 },
      );
      await drawFixture(page, at);
      await page.keyboard.press("c");
      await clickPlane(page, at, { x: 20, y: 18 });
      await clickPlane(page, at, { x: 26, y: 18 });

      await page.keyboard.press("g"); // grid off
      await page.keyboard.press("l");

      const hovers = [
        ["endpoint", { x: 40, y: 25 }, { x: -5, y: 4 }],
        ["midpoint", { x: 20, y: 0 }, { x: 4, y: -4 }],
        ["center", { x: 20, y: 18 }, { x: 5, y: 5 }],
        ["intersection", { x: 40, y: 8 }, { x: -4, y: 4 }],
      ] as const;
      for (const [name, point, nudge] of BEFORE ? hovers.slice(0, 1) : hovers) {
        await hoverPlane(page, at, point, nudge);
        await page.waitForTimeout(300);
        await page.screenshot({
          path: `${SCREENSHOT_DIR}/uiw5-snap-${BEFORE ? "before" : name}-${label}.png`,
        });
      }
    });
  }
});
