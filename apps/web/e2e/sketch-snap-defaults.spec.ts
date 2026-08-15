import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, distinctCanvasColors, seedSession } from "./support";

/**
 * SNAP-1 — the founder's "snap points do not work" (2026-08-14), pinned.
 *
 * WHY THIS FILE EXISTS ALONGSIDE `sketch-snap.spec.ts`. That suite is green and
 * always has been, and it turns the GRID OFF (`g`) before every assertion — it
 * has to, because with no grid an exact whole millimetre in the DRO can only
 * have come from an entity snap, which is what makes it a proof. The cost is
 * that the one configuration it never exercises is the DEFAULT one: grid ON,
 * which is what the founder was actually using. Same for the other four
 * configurations below — the press-drag-release gesture (FB-15), a RE-OPENED
 * sketch's loaded geometry, the non-XY datum planes, and a FACE-seated sketch
 * whose zero is the face's area centroid rather than a datum's fixed zero.
 * Every one of those is a different `plane`/`entities` input into the SAME
 * `resolveSnap`, and none of them had a spec. A report that cannot be
 * reproduced is usually a configuration nobody tested, so the answer to
 * "snap points do not work" is to test the configurations, not to re-read the
 * module.
 *
 * MEASURED RESULT: snapping fires and lands EXACTLY in all of them. SNAP-1 is
 * therefore not a snap-detection defect. What is genuinely broken at the origin
 * is SELECTING it — clicking the drawn origin ring or either axis with the
 * select tool returns "nothing selected" while a drawn line returns "1 ent" —
 * and that is SKETCH-2 (constraint-target selectability), a different code
 * path. This file deliberately asserts only behaviour that is correct today and
 * must stay correct, so it cannot block SKETCH-2's fix.
 *
 * The reads use the park-then-wait shape (`pick-affordance.spec.ts`'s
 * `confirmsPlacementFace`): park somewhere with NO snap and wait for the marker
 * to go, then move onto the target and wait for it to appear. Reading the
 * marker straight after a pointer move yields both lagging and leading values,
 * so without the park a stale kind masquerades as a fresh one — which would
 * make this evidence exactly as unreliable as the bug it is ruling out.
 */

interface SketchEntityRow {
  id: string;
  kind: string;
  start?: { x: number; y: number };
  end?: { x: number; y: number };
}

type Mapper = (pt: { x: number; y: number }) => { x: number; y: number };

/**
 * Plane-mm -> screen-px mapper. Reads the DRO at two screen points with the
 * grid off, then restores the grid, so the caller can click exact millimetre
 * coordinates in whatever configuration it is testing.
 */
async function calibratePlane(
  page: Page,
  s1: { x: number; y: number },
  s2: { x: number; y: number },
): Promise<Mapper> {
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
  await page.keyboard.press("g"); // grid back ON — the default under test
  const kx = (s2.x - s1.x) / (p2.x - p1.x);
  const ky = (s2.y - s1.y) / (p2.y - p1.y);
  return (pt) => ({
    x: s1.x + (pt.x - p1.x) * kx,
    y: s1.y + (pt.y - p1.y) * ky,
  });
}

/**
 * Assert the snap at `target` (nudged by `nudgePx` so the cursor is deliberately
 * OFF it) is `kind` and reads `x`/`y` in the DRO. `neutral` must be a point with
 * no snap of its own — the park that makes a stale read impossible.
 */
async function expectSnapAt(
  page: Page,
  at: Mapper,
  options: {
    neutral: { x: number; y: number };
    target: { x: number; y: number };
    nudgePx: { x: number; y: number };
    kind: string;
    x: string;
    y: string;
  },
): Promise<void> {
  const n = at(options.neutral);
  await page.mouse.move(n.x + 1, n.y + 1);
  await page.mouse.move(n.x, n.y);
  // The park: no marker here, so anything seen next was produced by the move
  // below rather than left over from the move before.
  await expect(page.getByTestId("snap-marker")).toHaveCount(0);
  const t = at(options.target);
  await page.mouse.move(
    t.x + options.nudgePx.x + 1,
    t.y + options.nudgePx.y + 1,
  );
  await page.mouse.move(t.x + options.nudgePx.x, t.y + options.nudgePx.y);
  await expect(page.getByTestId("snap-marker")).toHaveAttribute(
    "data-snap-kind",
    options.kind,
  );
  await expect(page.getByTestId("dro-x")).toHaveText(options.x);
  await expect(page.getByTestId("dro-y")).toHaveText(options.y);
}

/** A 2,2 -> corner rectangle drawn with the rect tool at exact millimetres. */
async function drawRect(
  page: Page,
  at: Mapper,
  corner: { x: number; y: number },
): Promise<void> {
  await page.keyboard.press("r");
  const a = at({ x: 2, y: 2 });
  await page.mouse.click(a.x, a.y);
  const b = at(corner);
  await page.mouse.click(b.x, b.y);
  await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
  await page.keyboard.press("Escape");
}

/**
 * The origin snap on an empty sheet, then an endpoint snap on a rectangle —
 * the two claims that matter, run against whatever plane the caller has open.
 */
async function expectSnapsOnOpenSketch(
  page: Page,
  corner: { x: number; y: number },
): Promise<void> {
  const at = await calibratePlane(
    page,
    { x: 700, y: 620 },
    { x: 1000, y: 420 },
  );
  await page.keyboard.press("l"); // a placement tool, so snapping is live
  await expectSnapAt(page, at, {
    neutral: { x: corner.x + 20, y: corner.y + 14 },
    target: { x: 0, y: 0 },
    nudgePx: { x: 5, y: -4 },
    kind: "origin",
    x: "+0.00",
    y: "+0.00",
  });
  await page.keyboard.press("Escape");
  await drawRect(page, at, corner);
  await page.keyboard.press("l");
  await expectSnapAt(page, at, {
    neutral: { x: (2 + corner.x) / 2, y: (2 + corner.y) / 2 },
    target: corner,
    nudgePx: { x: -5, y: 4 },
    kind: "endpoint",
    x: `+${corner.x.toFixed(2)}`,
    y: `+${corner.y.toFixed(2)}`,
  });
  await page.keyboard.press("Escape");
}

async function openSketch(page: Page, plane: "XY" | "XZ" | "YZ") {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId(`plane-${plane}`).click();
  await expect(page.getByTestId("sketch-step")).toHaveText(`On ${plane}`);
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
}

async function newPart(
  page: Page,
  name: string,
): Promise<{ id: string; token: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, name);
  await page.goto(`/parts/${part.id}`);
  return { id: part.id, token: account.token };
}

test.describe("SNAP-1 — snapping in the configurations no spec covered", () => {
  test("with the GRID ON (the default) every snap class still fires and lands exactly", async ({
    page,
  }) => {
    await newPart(page, "Snap defaults");
    await openSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );
    // The grid is ON — this is the whole point of the test, so say so rather
    // than assume it: `calibratePlane` toggles it twice and a lost keystroke
    // would silently turn this into a duplicate of the existing suite.
    await expect(page.getByTestId("dro-snap")).not.toContainText("no grid");

    await page.keyboard.press("l");
    // An EMPTY sheet: the only things to hold onto are the plane's own frame.
    await expectSnapAt(page, at, {
      neutral: { x: 33.3, y: 17.7 },
      target: { x: 0, y: 0 },
      nudgePx: { x: 5, y: -4 },
      kind: "origin",
      x: "+0.00",
      y: "+0.00",
    });
    await expectSnapAt(page, at, {
      neutral: { x: 33.3, y: 17.7 },
      target: { x: 24, y: 0 },
      nudgePx: { x: 0, y: -4 },
      kind: "x-axis",
      x: "+24.00",
      y: "+0.00",
    });

    await page.keyboard.press("Escape");
    await drawRect(page, at, { x: 44, y: 29 });
    await page.keyboard.press("l");
    await expectSnapAt(page, at, {
      neutral: { x: 33.3, y: 17.7 },
      target: { x: 44, y: 29 },
      nudgePx: { x: -5, y: 4 },
      kind: "endpoint",
      x: "+44.00",
      y: "+29.00",
    });
    await expectSnapAt(page, at, {
      neutral: { x: 33.3, y: 17.7 },
      target: { x: 23, y: 2 },
      nudgePx: { x: 4, y: -4 },
      kind: "midpoint",
      x: "+23.00",
      y: "+2.00",
    });
    await page.keyboard.press("Escape");
  });

  test("a PRESS-DRAG-RELEASE line snaps at BOTH ends, not just the press", async ({
    page,
  }) => {
    const { id: partId, token } = await newPart(page, "Snap drag");
    await openSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );
    await drawRect(page, at, { x: 44, y: 29 });

    // Grid OFF for this one: it is the discriminator. With no grid, exact whole
    // millimetres in the SAVED sketch can only have come from an entity snap,
    // so it proves the release resolved a snap rather than taking the raw
    // pointer — a press-drag-release that snapped only on the press would
    // persist a fractional end and still look right on screen.
    await page.keyboard.press("g");
    await expect(page.getByTestId("dro-snap")).toContainText("no grid");
    await page.keyboard.press("l");
    const a = at({ x: 2, y: 2 });
    const b = at({ x: 44, y: 29 });
    await page.mouse.move(a.x + 6, a.y - 5);
    await page.mouse.move(a.x + 5, a.y - 5);
    await page.mouse.down();
    await page.mouse.move((a.x + b.x) / 2, (a.y + b.y) / 2);
    await page.mouse.move(b.x - 6, b.y + 5);
    await page.mouse.move(b.x - 5, b.y + 5);
    await page.mouse.up();
    await expect(page.getByTestId("sketch-save")).toContainText("5 entities");
    await page.keyboard.press("Escape");

    const featurePromise = page.waitForResponse(
      (r) =>
        r.url().includes(`/parts/${partId}/features`) &&
        r.request().method() === "POST",
    );
    await page.getByTestId("sketch-save").click();
    expect((await featurePromise).status()).toBe(201);

    const treeResponse = await page.request.get(
      `/api/v1/parts/${partId}/features`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const treeBody = (await treeResponse.json()) as {
      features: Array<{ feature: { params: { entities: SketchEntityRow[] } } }>;
    };
    const entities = treeBody.features[0]?.feature.params.entities ?? [];
    const dragged = entities[4];
    expect(dragged?.kind).toBe("line");
    expect(dragged?.start?.x).toBe(2);
    expect(dragged?.start?.y).toBe(2);
    expect(dragged?.end?.x).toBe(44);
    expect(dragged?.end?.y).toBe(29);
  });

  test("a RE-OPENED sketch snaps to the geometry it loaded", async ({
    page,
  }) => {
    const { id: partId } = await newPart(page, "Snap reopen");
    await openSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );
    await drawRect(page, at, { x: 44, y: 29 });
    const featurePromise = page.waitForResponse(
      (r) =>
        r.url().includes(`/parts/${partId}/features`) &&
        r.request().method() === "POST",
    );
    await page.getByTestId("sketch-save").click();
    expect((await featurePromise).status()).toBe(201);
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
      timeout: 30_000,
    });

    await page.getByTestId("feature-row").first().click({ button: "right" });
    await page.getByTestId("tree-ctx-edit").click();
    await expect(page.getByTestId("sketch-dro")).toBeVisible({
      timeout: 30_000,
    });

    const at2 = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );
    await page.keyboard.press("l");
    // Entities that arrived over the wire, not ones this session drew: the
    // hydrated set has to reach `snapCandidates` or a re-opened sketch is a
    // sketch you cannot extend accurately.
    await expectSnapAt(page, at2, {
      neutral: { x: 23, y: 15 },
      target: { x: 44, y: 29 },
      nudgePx: { x: -5, y: 4 },
      kind: "endpoint",
      x: "+44.00",
      y: "+29.00",
    });
    await page.keyboard.press("Escape");
  });

  for (const plane of ["XZ", "YZ"] as const) {
    test(`the ${plane} datum plane snaps like XY does`, async ({ page }) => {
      await newPart(page, `Snap ${plane}`);
      await openSketch(page, plane);
      await expectSnapsOnOpenSketch(page, { x: 44, y: 29 });
    });
  }

  test("a FACE-seated sketch snaps to its face centre and to drawn geometry", async ({
    page,
  }) => {
    await newPart(page, "Snap face");

    // Base box: rect on XY, extrude 10 mm, so there is a top face to seat on.
    await openSketch(page, "XY");
    await page.keyboard.press("r");
    await expect(page.getByTestId("tool-rect")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.mouse.click(650, 420);
    await page.mouse.move(980, 640);
    await page.mouse.click(980, 640);
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("new-extrude")).toBeEnabled({
      timeout: 30_000,
    });
    await page.getByTestId("new-extrude").click();
    await expect(page.getByTestId("extrude-distance")).toHaveValue("10");
    await page.getByTestId("extrude-distance").press("Enter");
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 40_000,
    });
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
      .toBeGreaterThan(24);

    // Seat on the TOP face — greatest z in the pick node's accessible name.
    await page.getByTestId("new-sketch").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("Pick a plane");
    await page.getByTestId("plane-pick-face").click();
    await expect(page.getByTestId("face-pick-prompt")).toBeVisible();
    const nodes = page.locator('[data-testid^="plane-pick-face-"]');
    await expect(nodes.first()).toBeVisible({ timeout: 30_000 });
    const count = await nodes.count();
    let bestZ = -Infinity;
    let bestIndex = 0;
    for (let i = 0; i < count; i += 1) {
      const label = (await nodes.nth(i).getAttribute("aria-label")) ?? "";
      const nums = label.match(/-?\d+(?:\.\d+)?/g) ?? [];
      const z = Number.parseFloat(nums[nums.length - 1] as string);
      if (Number.isFinite(z) && z > bestZ) {
        bestZ = z;
        bestIndex = i;
      }
    }
    await nodes.nth(bestIndex).click();
    await expect(page.getByTestId("sketch-dro")).toBeVisible({
      timeout: 30_000,
    });
    // This plane's zero is the face's area centroid, which MOVES — the snap has
    // to offer it under its own honest name, not "Origin".
    await expect(page.getByTestId("sketch-origin")).toHaveAttribute(
      "data-origin-label",
      "Face centre",
    );
    await expectSnapsOnOpenSketch(page, { x: 12, y: 8 });
  });
});
