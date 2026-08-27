import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, distinctCanvasColors, seedSession } from "./support";

/**
 * QA sweep over the REACH batch (REACH-1 sketch verbs, REACH-2 pattern/mirror
 * scope, REACH-3 sheet convention). Deliberately NOT the builder's happy path:
 * every case here is a SECOND action on the same object — re-open, re-type,
 * reload, delete the subject, switch sheets, tap instead of click — plus the
 * cross-item interference a per-item review cannot see.
 *
 * CASES ARE `test.fail()` WHILE THEIR DEFECT IS OPEN: they encode the bug as it
 * exists today, so the suite stays green while it is open and turns red the
 * moment someone fixes it without flipping the annotation (the
 * `founder-picking.spec.ts` convention). Each logs the measured values it failed
 * ON — read WHY it failed, never just that it did; a `test.fail()` that starts
 * failing for a NEW reason is a gate that has quietly stopped meaning anything.
 *
 *   - QA-R1  CLOSED — the offer rail pushed FINISH/CANCEL SKETCH out of a 1280
 *            (and 1366) window. Now a live REGRESSION gate at both widths: the
 *            annotation is gone and the cases below must pass.
 *   - QA-R2  CLOSED — an angle glyph kept a value the solver had already moved
 *            off, on the expression/reference path. Now a live regression gate.
 *   - QA-R3  OPEN — a touch device cannot select two entities, so four of
 *            REACH-1's five new verbs are unreachable there.
 *
 * `docs/QA-REVIEW.md` (2026-08-27) carries the full findings and evidence.
 */

/** Ø8 through the plate: the exact material one bore removes. */
function boreVolumeMm3(thicknessMm: number): number {
  return Math.PI * 4 * 4 * thicknessMm;
}

async function expectRenderedBody(page: Page): Promise<void> {
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
}

async function extents(page: Page): Promise<[number, number, number]> {
  const text = await page.getByTestId("prop-extents").innerText();
  const nums = (text.replace(/,/g, "").match(/-?\d+(?:\.\d+)?/g) ?? []).map(
    Number.parseFloat,
  );
  expect(nums.length, `extents readout: ${text}`).toBeGreaterThanOrEqual(3);
  return [nums[0] as number, nums[1] as number, nums[2] as number];
}

async function volume(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  const match = text.replace(/,/g, "").match(/-?\d+(?:\.\d+)?/);
  const value = Number.parseFloat(match?.[0] ?? "");
  expect(Number.isFinite(value), `volume readout: ${text}`).toBe(true);
  return value;
}

async function sketchRectangleAndSave(page: Page): Promise<void> {
  await page.keyboard.press("r");
  await expect(page.getByTestId("tool-rect")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.mouse.click(560, 360);
  await page.mouse.move(1060, 700);
  await page.mouse.click(1060, 700);
  await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
    timeout: 30_000,
  });
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
}

async function buildPlate(page: Page): Promise<void> {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await sketchRectangleAndSave(page);
  await expect(page.getByTestId("new-extrude")).toBeEnabled({
    timeout: 30_000,
  });
  await page.getByTestId("new-extrude").click();
  await expect(page.getByTestId("extrude-distance")).toHaveValue("10");
  await page.getByTestId("extrude-distance").press("Enter");
  await expect(page.getByTestId("body-inspector")).toBeVisible({
    timeout: 30_000,
  });
  await expectRenderedBody(page);
}

async function clickTopFace(page: Page): Promise<void> {
  const nodes = page.locator('[data-testid^="plane-pick-face-"]');
  await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
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
}

interface Drilled {
  centre: { x: number; y: number };
  radius: number;
  thickness: number;
}

async function drillOffCentreHole(page: Page): Promise<Drilled> {
  const [ex, ey, ez] = await extents(page);
  expect(
    Math.min(ex, ey),
    "plate too small for a 6-up Ø8 bolt circle",
  ).toBeGreaterThan(40);
  const radius = Math.min(ex, ey) / 4;

  await expect(page.getByTestId("new-hole")).toBeEnabled({ timeout: 30_000 });
  await page.getByTestId("new-hole").click();
  await expect(page.getByTestId("hole-editor")).toBeVisible();
  await clickTopFace(page);
  await expect(page.getByTestId("hole-frame")).toContainText("X→+X");

  const centre = {
    x: Number.parseFloat(
      await page.getByTestId("hole-position-x").inputValue(),
    ),
    y: Number.parseFloat(
      await page.getByTestId("hole-position-y").inputValue(),
    ),
  };
  await page.getByTestId("hole-position-x").fill(String(centre.x + radius));
  await page.getByTestId("hole-position-y").fill(String(centre.y));
  await page.getByTestId("hole-diameter").fill("8");
  await expect(page.getByTestId("hole-submit")).toBeEnabled();
  await page.getByTestId("hole-submit").click();
  await expect(
    page.getByTestId("feature-row").filter({ hasText: "Hole1" }),
  ).toBeVisible();
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  return { centre, radius, thickness: ez };
}

/** A 3 mm corner fillet — the unrelated feature that separates the two scope
 * readings (without it both give the same body; see pattern-scope.spec.ts). */
async function addFillet(page: Page): Promise<void> {
  await page.getByTestId("new-fillet").click();
  await expect(page.getByTestId("fillet-editor")).toBeVisible();
  await page.getByTestId("fillet-radius").fill("3");
  await page.getByTestId("fillet-radius").press("Enter");
  await expect(
    page.getByTestId("feature-row").filter({ hasText: "Fillet1" }),
  ).toBeVisible();
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
}

test.describe("REACH-2 QA — the scope has to survive the SECOND edit", () => {
  test("re-open a feature-scoped pattern, change the count, and the scope holds", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(
      page,
      account.token,
      "Scope round trip",
    );
    await page.goto(`/parts/${part.id}`);

    await buildPlate(page);
    const drilled = await drillOffCentreHole(page);
    await addFillet(page);
    const filleted = await volume(page);

    // Author the scoped pattern exactly as a user does.
    await page.getByTestId("feature-select-2").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("hole-editor")).toHaveCount(0);
    await page.getByTestId("new-pattern").click();
    await expect(page.getByTestId("pattern-editor")).toBeVisible();
    await expect(page.getByTestId("pattern-scope-features")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.getByTestId("pattern-kind-circular").click();
    await page.getByTestId("pattern-count").fill("6");
    await page.getByTestId("pattern-axis-x").fill(String(drilled.centre.x));
    await page.getByTestId("pattern-axis-y").fill(String(drilled.centre.y));
    await page.getByTestId("pattern-submit").click();
    await expect(
      page.getByTestId("feature-row").filter({ hasText: "Pattern1" }),
    ).toBeVisible();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    const six = await volume(page);
    // Five ADDITIONAL bores (the seed hole is already gone from `filleted`).
    expect(filleted - six).toBeCloseTo(5 * boreVolumeMm3(drilled.thickness), 1);

    // ---- THE CASE UNDER TEST: open it again and change ONE number. ------
    await page.getByTestId("feature-select-4").click();
    await expect(page.getByTestId("pattern-editor")).toBeVisible();
    // The persisted scope must be what the row reads back — a form that opens
    // on `This body` would silently author the legacy reading on submit.
    await expect(page.getByTestId("pattern-scope-features")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("pattern-scope-features")).toContainText(
      "Hole1",
    );
    await page.getByTestId("pattern-count").fill("4");
    await page.getByTestId("pattern-submit").click();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    const four = await volume(page);
    expect(
      filleted - four,
      "a 4-up feature-scoped pattern removes exactly three more bores",
    ).toBeCloseTo(3 * boreVolumeMm3(drilled.thickness), 1);

    // ---- Cross-surface: reload agrees with the viewport and the panel. ---
    await page.reload();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });
    await expectRenderedBody(page);
    expect(await volume(page)).toBeCloseTo(four, 1);
    await expect(
      page.getByTestId("feature-row").filter({ hasText: "Pattern1" }),
    ).toContainText("Hole1");
  });

  test("delete the scoped subject and the part does not silently lie", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Scope orphan");
    await page.goto(`/parts/${part.id}`);

    await buildPlate(page);
    const drilled = await drillOffCentreHole(page);
    await addFillet(page);

    await page.getByTestId("feature-select-2").click();
    await page.keyboard.press("Escape");
    await page.getByTestId("new-pattern").click();
    await expect(page.getByTestId("pattern-editor")).toBeVisible();
    await page.getByTestId("pattern-kind-circular").click();
    await page.getByTestId("pattern-count").fill("6");
    await page.getByTestId("pattern-axis-x").fill(String(drilled.centre.x));
    await page.getByTestId("pattern-axis-y").fill(String(drilled.centre.y));
    await page.getByTestId("pattern-submit").click();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    const six = await volume(page);

    // Now try to delete Hole1 — the feature the pattern NAMES in its scope.
    // The tree's delete warning must know about the scope edge; if it says
    // "nothing else depends on it" the user is one click from a tree the
    // server refuses or a pattern with no source.
    // NB the Pattern1 row's badge also reads "Hole1" (`pattern · Hole1`), so
    // the row is addressed by its own select control, not by text.
    const row = page
      .getByTestId("feature-row")
      .filter({ has: page.getByTestId("feature-select-2") });
    await expect(row).toBeVisible();
    await row.click({ button: "right" });
    await page.getByTestId("tree-ctx-delete").click();
    const confirm = page.getByTestId("feature-delete-confirm");
    await expect(confirm).toBeVisible();
    await expect(
      confirm,
      "a scope reference is a dependency and must block the delete",
    ).toHaveAttribute("data-blocked", "true");
    await expect(page.getByTestId("feature-dependent")).toHaveText("Pattern1");
    await page.getByTestId("feature-delete-cancel").click();

    // Asking did not change the model.
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    expect(await volume(page)).toBeCloseTo(six, 1);
  });
});

// ---------------------------------------------------------------------------
// REACH-1 — the offer rail, at the quality floor and against the other modes
// ---------------------------------------------------------------------------

async function enterSketch(page: Page, plane: "XY" | "XZ" | "YZ") {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId(`plane-${plane}`).click();
  await expect(page.getByTestId("sketch-step")).toHaveText(`On ${plane}`);
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
}

type At = (pt: { x: number; y: number }) => { x: number; y: number };

/** Plane-mm → screen-px mapper, read from the DRO with snap off. */
async function calibratePlane(
  page: Page,
  s1: { x: number; y: number },
  s2: { x: number; y: number },
): Promise<At> {
  await page.keyboard.press("g");
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
  await page.keyboard.press("g");
  const kx = (s2.x - s1.x) / (p2.x - p1.x);
  const ky = (s2.y - s1.y) / (p2.y - p1.y);
  return (pt) => ({
    x: s1.x + (pt.x - p1.x) * kx,
    y: s1.y + (pt.y - p1.y) * ky,
  });
}

async function clickPlane(page: Page, at: At, pt: { x: number; y: number }) {
  const px = at(pt);
  await page.mouse.click(px.x, px.y);
}

async function addPlane(page: Page, at: At, pt: { x: number; y: number }) {
  await page.keyboard.down("Shift");
  await clickPlane(page, at, pt);
  await page.keyboard.up("Shift");
}

async function drawLine(
  page: Page,
  at: At,
  from: { x: number; y: number },
  to: { x: number; y: number },
) {
  await page.keyboard.press("l");
  await clickPlane(page, at, from);
  await clickPlane(page, at, to);
  await page.keyboard.press("Escape");
}

interface ClippedControl {
  testId: string;
  left: number;
  right: number;
}

/**
 * Every control inside `container` whose box extends past the viewport, with
 * the fact that decides whether it is merely off-view or truly unreachable:
 * the document does not scroll horizontally.
 *
 * Playwright's `toBeVisible()` is a CSS/box property, not a viewport-containment
 * one — a button 140 px past the right edge is "visible" — so no ordinary
 * assertion in the suite can see this class of defect.
 */
async function clippedControls(
  page: Page,
  containerTestId: string,
): Promise<{ clipped: ClippedControl[]; scrollable: boolean; width: number }> {
  return page.evaluate((id: string) => {
    const root = document.querySelector(`[data-testid="${id}"]`);
    const vw = document.documentElement.clientWidth;
    const clipped: ClippedControl[] = [];
    if (root !== null) {
      for (const node of root.querySelectorAll("[data-testid]")) {
        const rect = node.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) continue;
        if (rect.right > vw + 0.5 || rect.left < -0.5) {
          clipped.push({
            testId: node.getAttribute("data-testid") ?? "?",
            left: Math.round(rect.left),
            right: Math.round(rect.right),
          });
        }
      }
    }
    return {
      clipped,
      scrollable: document.documentElement.scrollWidth > vw + 0.5,
      width: vw,
    };
  }, containerTestId);
}

// The two widths QA-R1 was measured failing at: the 1280 responsive floor and
// 1366, the commonest laptop width in the wild. 1440/1600 were clean before the
// fix and are held by the census case further down.
for (const width of [1280, 1366]) {
  test.describe(`REACH-1 QA — the offer rail at ${width}x800`, () => {
    test.use({ viewport: { width, height: 800 } });

    test("a live selection must not push FINISH SKETCH out of the window", async ({
      page,
    }) => {
      // QA-R1 — was OPEN, now the regression gate. Measured 3/3 before the fix:
      // with two lines selected the strip ran to 1413px in a 1280px window with
      // `scrollWidth === clientWidth`, so the sketch's own commit and cancel
      // were unreachable by mouse; ONE offer already cost CANCEL at 1280, and
      // 1366 lost SAVE + EXIT. Two halves, and BOTH are needed: `toBeVisible()`
      // is a CSS/box property and passes on a button 140px past the right edge,
      // while a click alone would pass through Playwright's auto-scroll.
      const account = await seedSession(page);
      const part = await createPartViaApi(page, account.token, "Floor gusset");
      await page.goto(`/parts/${part.id}`);
      await enterSketch(page, "XY");
      const at = await calibratePlane(
        page,
        { x: Math.round(width * 0.44), y: 520 },
        { x: Math.round(width * 0.67), y: 340 },
      );

      await drawLine(page, at, { x: 0, y: 0 }, { x: 30, y: 10 });
      await drawLine(page, at, { x: 0, y: 0 }, { x: 10, y: 30 });

      // MEASURE FIRST, ASSERT LAST — deliberately. A failing assertion aborts
      // the test, so an early one costs the evidence for every state after it:
      // asserting the one-offer census before the two-offer screenshot means a
      // regression at 1280 produces no picture of the state QA reported. The
      // shots below are also the before/after pair for the founder update.
      await page.keyboard.press("Escape");
      const idle = await clippedControls(page, "sketch-strip");

      // ONE offer — the most ordinary state in a sketcher, and enough to cost
      // CANCEL SKETCH at 1280 before the fix.
      await clickPlane(page, at, { x: 24, y: 8 });
      await expect(page.getByTestId("dimension-hint")).toBeVisible();
      const single = await clippedControls(page, "sketch-strip");
      console.log(`STRIP-CENSUS-1 ${width}`, JSON.stringify(single));

      // Select the two legs — the state the offer rail is built for.
      await addPlane(page, at, { x: 8, y: 24 });
      await expect(page.getByTestId("verb-hint-angle")).toBeVisible();

      const live = await clippedControls(page, "sketch-strip");
      console.log(`STRIP-CENSUS ${width}`, JSON.stringify(live));
      await page.screenshot({
        path: `test-results/qa-reach1-strip-${width}.png`,
      });

      // The functional half: can a POINTER still finish the sketch? A real
      // mouse click at the control's own centre — not Playwright's
      // auto-scrolling `locator.click()`, which papers over exactly this.
      const saveBox = await page.getByTestId("sketch-save").boundingBox();
      expect(saveBox, "no box for sketch-save").not.toBeNull();
      const box = saveBox as {
        x: number;
        y: number;
        width: number;
        height: number;
      };
      await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
      const stripGone = await page
        .getByTestId("sketch-strip")
        .waitFor({ state: "detached", timeout: 8_000 })
        .then(() => true)
        .catch(() => false);

      expect(
        idle.clipped,
        `idle strip already clips: ${JSON.stringify(idle.clipped)}`,
      ).toEqual([]);
      expect(
        single.clipped,
        `one selected line clips: ${JSON.stringify(single.clipped)}`,
      ).toEqual([]);
      expect(
        { clipped: live.clipped.map((c) => c.testId), stripGone },
        "with two lines selected the sketch's own commit/cancel must stay reachable",
      ).toEqual({ clipped: [], stripGone: true });
    });
  });
}

test.describe("REACH-1 QA — the offer rail's other 1280 guarantees", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("sketch verb keys do not leak into the model-mode create openers", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Key overlap");
    await page.goto(`/parts/${part.id}`);

    // Build a body first, so every model-mode opener (P/I/H/D/O) is ENABLED —
    // a guard that is off because there is nothing to act on proves nothing.
    await buildPlate(page);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 400, y: 520 },
      { x: 700, y: 340 },
    );
    await drawLine(page, at, { x: 0, y: 0 }, { x: 30, y: 10 });
    await drawLine(page, at, { x: 0, y: 0 }, { x: 10, y: 30 });
    await clickPlane(page, at, { x: 24, y: 8 });
    await addPlane(page, at, { x: 8, y: 24 });
    await expect(page.getByTestId("selection-readout")).toContainText("2 ent");

    // I is `collinear` in the sketch and `Mirror` in the model. Same window,
    // two listeners: if the model one is not gated on mode, a constraint press
    // also opens a modelling dialog over the live sketch.
    const shadowed = ["i", "p", "h", "d", "o", "s", "l"];
    const opened: string[] = [];
    for (const key of shadowed) {
      await page.keyboard.press(key);
      for (const editor of [
        "mirror-editor",
        "pattern-editor",
        "shell-editor",
        "draft-editor",
        "hole-editor",
        "sweep-editor",
        "loft-editor",
      ]) {
        if ((await page.getByTestId(editor).count()) > 0) {
          opened.push(`${key}->${editor}`);
        }
      }
      await page.keyboard.press("Escape");
    }
    expect(
      opened,
      "a sketch constraint key opened a model-mode command",
    ).toEqual([]);
    // ...and the sketch is still the thing on screen.
    await expect(page.getByTestId("sketch-strip")).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// REACH-3 — the convention is a property of THE SHEET, and of the deliverable
// ---------------------------------------------------------------------------

const TALL_PART = { width: 40, depth: 40, height: 150 };

/** A 40 x 40 x 150 mm column via the real gateway (portrait earns 1:2, not 1:5). */
async function createTallPartViaApi(
  page: Page,
  token: string,
  name: string,
): Promise<{ id: string }> {
  const auth = { Authorization: `Bearer ${token}` };
  const part = await page.request.post("/api/v1/parts", {
    data: { name },
    headers: auth,
  });
  expect(part.ok(), `create part: ${part.status()}`).toBe(true);
  const partId = ((await part.json()) as { id: string }).id;
  const { width, depth, height } = TALL_PART;
  const sketch = await page.request.post(`/api/v1/parts/${partId}/features`, {
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
              end: { x: width, y: 0 },
            },
            {
              id: "e2",
              kind: "line",
              start: { x: width, y: 0 },
              end: { x: width, y: depth },
            },
            {
              id: "e3",
              kind: "line",
              start: { x: width, y: depth },
              end: { x: 0, y: depth },
            },
            {
              id: "e4",
              kind: "line",
              start: { x: 0, y: depth },
              end: { x: 0, y: 0 },
            },
          ],
          constraints: [],
        },
      },
      expected_tree_version: 0,
    },
    headers: auth,
  });
  expect(sketch.ok(), `sketch: ${sketch.status()}`).toBe(true);
  const sketchBody = (await sketch.json()) as {
    feature: { id: string };
    tree_version: number;
  };
  const extrude = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: {
      name: "Extrude1",
      feature: {
        type: "extrude",
        version: 1,
        params: {
          profile: { kind: "feature", feature_id: sketchBody.feature.id },
          distance_mm: height,
          operation: "add",
          direction: "normal",
        },
      },
      expected_tree_version: sketchBody.tree_version,
    },
    headers: auth,
  });
  expect(extrude.ok(), `extrude: ${extrude.status()}`).toBe(true);
  return { id: partId };
}

async function seedLaidOutDrawing(
  page: Page,
  partId: string,
  name: string,
): Promise<void> {
  await page.goto("/drawings");
  await expect(page.getByTestId("nav-drawings")).toBeVisible();
  await page.getByTestId("create-drawing-name").fill(name);
  await page.getByTestId("create-drawing-submit").click();
  const row = page.getByTestId("drawing-row").first();
  await expect(row).toBeVisible();
  await row.getByTestId("drawing-open").click();
  await expect(page.getByTestId("drawing-setup-hint")).toBeVisible();
  await page.getByTestId("drawing-part-select").selectOption(partId);
  await page.getByTestId("drawing-autolayout").click();
  await expect(page.getByTestId("drawing-sheet")).toBeVisible({
    timeout: 30_000,
  });
}

test.describe("REACH-3 QA — the convention belongs to the sheet, not the app", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("two sheets hold two conventions, and the header strip fits 1280", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createTallPartViaApi(page, account.token, "QA column");
    await seedLaidOutDrawing(page, part.id, "QA convention");

    const cell = page.getByTestId("sheet-projection");
    await expect(cell).toHaveAttribute("data-projection", "third_angle");

    // The header strip carries two new cells now — it must still fit the floor.
    const strip = await clippedControls(page, "sheet-tabs");
    console.log("SHEET-STRIP-CENSUS", JSON.stringify(strip));
    expect(strip.clipped, "sheet header strip clips at 1280").toEqual([]);

    // Sheet 1 -> first angle.
    await cell.click();
    await expect(cell).toHaveAttribute("data-projection", "first_angle", {
      timeout: 30_000,
    });

    // A second sheet INHERITS the convention from the sheet in hand.
    await page.getByTestId("sheet-tab-add").click();
    await expect(page.getByTestId("sheet-tab-1")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(
      page.getByTestId("sheet-projection"),
      "a new sheet inherits the convention of the one it was made from",
    ).toHaveAttribute("data-projection", "first_angle");

    // ...and then diverges: sheet 2 goes back to third angle on its own.
    await page.getByTestId("sheet-projection").click();
    await expect(page.getByTestId("sheet-projection")).toHaveAttribute(
      "data-projection",
      "third_angle",
      { timeout: 30_000 },
    );

    // THE CASE: switching back must show SHEET ONE's convention, not the last
    // one touched. A single app-level reading would report third_angle here.
    await page.getByTestId("sheet-tab-0").click();
    await expect(page.getByTestId("sheet-tab-0")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(
      page.getByTestId("sheet-projection"),
      "the convention is per-sheet",
    ).toHaveAttribute("data-projection", "first_angle", { timeout: 30_000 });

    // And it survives a reload, both ways round.
    await page.reload();
    await expect(page.getByTestId("drawing-sheet")).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByTestId("sheet-projection")).toHaveAttribute(
      "data-projection",
      "first_angle",
    );
    await page.getByTestId("sheet-tab-1").click();
    await expect(page.getByTestId("sheet-projection")).toHaveAttribute(
      "data-projection",
      "third_angle",
      { timeout: 30_000 },
    );
  });

  test("a portrait sheet exports portrait paper", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createTallPartViaApi(page, account.token, "QA tall");
    await seedLaidOutDrawing(page, part.id, "QA portrait export");

    // The landscape sheet's PDF is the control.
    const landscapePdf = await downloadPdfBox(page);

    // Accept the portrait proposal and lay the same part out on it.
    await page.getByTestId("sheet-tab-add").click();
    await expect(page.getByTestId("sheet-orientation")).toHaveAttribute(
      "data-orientation",
      "portrait",
    );
    await page.getByTestId("drawing-part-select").selectOption(part.id);
    await page.getByTestId("drawing-autolayout").click();
    await expect(page.getByTestId("drawing-sheet")).toHaveAttribute(
      "viewBox",
      "0 0 210 297",
      { timeout: 30_000 },
    );

    const portraitPdf = await downloadPdfBox(page);
    console.log("PDF-BOXES", JSON.stringify({ landscapePdf, portraitPdf }));

    expect(
      landscapePdf.width,
      "the landscape deliverable is wider than it is tall",
    ).toBeGreaterThan(landscapePdf.height);
    expect(
      portraitPdf.height,
      "a portrait sheet must not export landscape paper",
    ).toBeGreaterThan(portraitPdf.width);
  });
});

/** Export the ACTIVE sheet to PDF and read the page box out of the bytes. */
async function downloadPdfBox(
  page: Page,
): Promise<{ width: number; height: number }> {
  const button = page.getByTestId("drawing-export-pdf");
  await expect(button).toBeEnabled({ timeout: 30_000 });
  const downloadPromise = page.waitForEvent("download");
  await button.click();
  const download = await downloadPromise;
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(chunk as Buffer);
  const text = Buffer.concat(chunks).toString("latin1");
  const match = text.match(
    /\/MediaBox\s*\[\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*\]/,
  );
  expect(match, "no /MediaBox in the exported PDF").not.toBeNull();
  const nums = (match as RegExpMatchArray).slice(1).map(Number.parseFloat);
  return {
    width: (nums[2] as number) - (nums[0] as number),
    height: (nums[3] as number) - (nums[1] as number),
  };
}

// ---------------------------------------------------------------------------
// CROSS-ITEM — do the new affordances interfere with each other?
// ---------------------------------------------------------------------------

test.describe("REACH cross-item QA — two new proposals, one 1280 frame", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("the renamed Modify verb does not push the band off the floor", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Band pressure");
    await page.goto(`/parts/${part.id}`);
    await buildPlate(page);
    await drillOffCentreHole(page);

    const idle = await clippedControls(page, "top-toolbar");
    console.log("BAND-CENSUS-IDLE", JSON.stringify(idle));

    // Arm REACH-2's proposal: the Modify verb renames to "Repeat Hole1".
    await page.getByTestId("feature-select-2").click();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("hole-editor")).toHaveCount(0);
    const proposing = await clippedControls(page, "top-toolbar");
    console.log("BAND-CENSUS-PROPOSING", JSON.stringify(proposing));
    expect(
      proposing.clipped,
      "the proposal must not cost any command its place in the frame",
    ).toEqual([]);

    // The proposal must also survive the trip through a sketch: entering and
    // leaving sketch mode is the most ordinary thing a user does next.
    const verbBefore =
      (await page.getByTestId("new-pattern").getAttribute("aria-label")) ?? "";
    await enterSketch(page, "XY");
    await expect(page.getByTestId("sketch-strip")).toBeVisible();
    await page.getByTestId("sketch-exit").click();
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
    const verbAfter =
      (await page.getByTestId("new-pattern").getAttribute("aria-label")) ?? "";
    console.log(
      "PROPOSAL-ACROSS-SKETCH",
      JSON.stringify({ verbBefore, verbAfter }),
    );
    // Either reading is defensible; a verb that names a subject the tree no
    // longer marks is not.
    const stillSelected =
      (await page
        .getByTestId("feature-select-2")
        .getAttribute("aria-pressed")) === "true";
    expect(
      { namesHole: /Hole1/.test(verbAfter), stillSelected },
      "the verb and the tree must agree about the subject",
    ).toEqual({ namesHole: stillSelected, stillSelected });
  });

  test("a pattern can be scoped to a pattern only if the kernel can build it", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Nested scope");
    await page.goto(`/parts/${part.id}`);
    await buildPlate(page);
    const drilled = await drillOffCentreHole(page);
    await addFillet(page);

    await page.getByTestId("feature-select-2").click();
    await page.keyboard.press("Escape");
    await page.getByTestId("new-pattern").click();
    await page.getByTestId("pattern-kind-circular").click();
    await page.getByTestId("pattern-count").fill("3");
    await page.getByTestId("pattern-axis-x").fill(String(drilled.centre.x));
    await page.getByTestId("pattern-axis-y").fill(String(drilled.centre.y));
    await page.getByTestId("pattern-submit").click();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    const three = await volume(page);

    // Now select the PATTERN and repeat IT — the UI offers this (a
    // features-scoped pattern is a legal subject in `REPEATABLE_FEATURE_TYPES`),
    // so the kernel has to honour it or the offer is a trap.
    await page.getByTestId("feature-select-4").click();
    await page.keyboard.press("Escape");
    await page.getByTestId("new-pattern").click();
    await expect(page.getByTestId("pattern-editor")).toBeVisible();
    const scopeName = await page
      .getByTestId("pattern-scope-features")
      .innerText();
    console.log("NESTED-SCOPE-OFFER", JSON.stringify({ scopeName }));
    expect(scopeName).toMatch(/pattern1/i);
    await page.getByTestId("pattern-kind-linear").click();
    await page.getByTestId("pattern-count").fill("2");
    await page.getByTestId("pattern-spacing").fill("6");
    await page.getByTestId("pattern-submit").click();

    // Whatever happens must be legible: either it solves and removes more
    // material, or it refuses IN THE EDITOR. A tree that goes red with a raw
    // kernel code after OK is the failure mode `scopeFeature` exists to prevent.
    const outcome = await Promise.race([
      page
        .getByTestId("eval-status")
        .filter({ hasText: "Solved" })
        .waitFor({ state: "visible", timeout: 40_000 })
        .then(() => "solved"),
      page
        .getByTestId("pattern-error")
        .waitFor({ state: "visible", timeout: 40_000 })
        .then(() => "refused-in-editor"),
    ]).catch(() => "neither");
    const status = await page.getByTestId("eval-status").innerText();
    const errorText =
      (await page.getByTestId("pattern-error").count()) > 0
        ? await page.getByTestId("pattern-error").innerText()
        : null;
    console.log(
      "NESTED-SCOPE-OUTCOME",
      JSON.stringify({ outcome, status, errorText, three }),
    );
    expect(["solved", "refused-in-editor"]).toContain(outcome);
    if (outcome === "solved") {
      expect(
        await volume(page),
        "a pattern OF a pattern must remove more material, not the same",
      ).toBeLessThan(three - 1);
    }
  });
});

// ---------------------------------------------------------------------------
// TOUCH — the same three affordances with no keyboard and no hover
// ---------------------------------------------------------------------------

test.describe("REACH on TOUCH — a keycap the user cannot press", () => {
  test.use({ viewport: { width: 1280, height: 800 }, hasTouch: true });

  test("the offer rail is operable by tap, with no keyboard to press A on", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Touch gusset");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 420, y: 520 },
      { x: 720, y: 340 },
    );
    await drawLine(page, at, { x: 0, y: 0 }, { x: 30, y: 10 });
    await drawLine(page, at, { x: 0, y: 0 }, { x: 10, y: 30 });

    // Select the two legs BY TAP — the only pointer a tablet has. The second
    // needs the additive gesture; on touch there is no Shift, so the tool has
    // to have an answer (a tap-adds mode, a long press, anything).
    const a = at({ x: 24, y: 8 });
    const b = at({ x: 8, y: 24 });
    await page.touchscreen.tap(a.x, a.y);
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    await page.keyboard.down("Shift");
    await page.touchscreen.tap(b.x, b.y);
    await page.keyboard.up("Shift");
    const readout = await page.getByTestId("selection-readout").innerText();
    console.log("TOUCH-SELECTION", JSON.stringify({ readout }));
    expect(readout, "two entities must be selectable by pointer").toContain(
      "2 ent",
    );

    // THE CASE: the rail's keycap is the only affordance a tablet user has for
    // these five verbs, because the letter it stamps has no keyboard behind it.
    const offer = page.getByTestId("verb-hint-angle");
    await expect(offer).toBeVisible();
    await offer.tap();
    await expect(
      page.getByTestId("dimension-input"),
      "tapping the offered verb must open its editor",
    ).toBeVisible({ timeout: 10_000 });
    await page.getByTestId("dimension-input").fill("30");
    await page.getByTestId("dimension-apply").tap();
    await expect(
      page.locator('[data-testid^="glyph-"][data-kind="angle"]'),
    ).toHaveCount(1, { timeout: 20_000 });
  });

  test("the scope row and the sheet cells answer a tap", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Touch scope");
    await page.goto(`/parts/${part.id}`);
    await buildPlate(page);
    await drillOffCentreHole(page);

    await page.getByTestId("feature-select-2").tap();
    await expect(page.getByTestId("hole-editor")).toBeVisible();
    // No Escape key on a tablet — the dialog's own dismiss has to work.
    await page.getByTestId("hole-cancel").tap();
    await expect(page.getByTestId("hole-editor")).toHaveCount(0);
    await page.getByTestId("new-pattern").tap();
    await expect(page.getByTestId("pattern-editor")).toBeVisible();
    await page.getByTestId("pattern-scope-body").tap();
    await expect(page.getByTestId("pattern-scope-body")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.getByTestId("pattern-scope-features").tap();
    await expect(page.getByTestId("pattern-scope-features")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.getByTestId("pattern-cancel").tap();

    // ...and REACH-3's two header cells, which are also stamped readings.
    const drawingPart = part.id;
    await seedLaidOutDrawing(page, drawingPart, "Touch convention");
    const cell = page.getByTestId("sheet-projection");
    await expect(cell).toHaveAttribute("data-projection", "third_angle");
    await cell.tap();
    await expect(cell).toHaveAttribute("data-projection", "first_angle", {
      timeout: 30_000,
    });
  });
});

test.describe("REACH on TOUCH — additive selection with no Shift key", () => {
  test.use({ viewport: { width: 1280, height: 800 }, hasTouch: true });

  test("four of the five new verbs need two entities; can a tablet select two?", async ({
    page,
  }) => {
    // QA-R3 — OPEN. A second tap REPLACES the selection and a long press does
    // the same, so a keyboardless tablet holds at most one entity.
    test.fail();
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Touch additive");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 420, y: 520 },
      { x: 720, y: 340 },
    );
    await drawLine(page, at, { x: 0, y: 0 }, { x: 30, y: 10 });
    await drawLine(page, at, { x: 0, y: 0 }, { x: 10, y: 30 });

    const a = at({ x: 24, y: 8 });
    const b = at({ x: 8, y: 24 });
    await page.touchscreen.tap(a.x, a.y);
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");

    // A plain second tap — the ONLY gesture a keyboardless tablet has.
    await page.touchscreen.tap(b.x, b.y);
    const plain = await page.getByTestId("selection-readout").innerText();

    // A long press, the usual touch stand-in for a modifier.
    await page.touchscreen.tap(a.x, a.y);
    const client = await page.context().newCDPSession(page);
    await client.send("Input.dispatchTouchEvent", {
      type: "touchStart",
      touchPoints: [{ x: b.x, y: b.y }],
    });
    await page.waitForTimeout(900);
    await client.send("Input.dispatchTouchEvent", {
      type: "touchEnd",
      touchPoints: [],
    });
    const held = await page.getByTestId("selection-readout").innerText();
    const offers = await page
      .locator('[data-testid^="verb-hint-"]')
      .evaluateAll((nodes) =>
        nodes.map((n) => n.getAttribute("data-testid") ?? "?"),
      );
    console.log("TOUCH-ADDITIVE", JSON.stringify({ plain, held, offers }));
    expect(
      { plain: /2 ent/.test(plain), held: /2 ent/.test(held) },
      "with no Shift key, a tablet must still be able to select two entities",
    ).toEqual({ plain: true, held: true });
  });
});

test.describe("REACH-1 QA — how much room does the rail need?", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("census: offers vs clipped controls, across widths", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Rail budget");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 560, y: 520 },
      { x: 860, y: 340 },
    );
    await drawLine(page, at, { x: 0, y: 0 }, { x: 30, y: 10 });
    await drawLine(page, at, { x: 0, y: 0 }, { x: 10, y: 30 });

    const table: unknown[] = [];
    for (const width of [1280, 1366, 1440, 1600]) {
      await page.setViewportSize({ width, height: 800 });
      // RECALIBRATE after every resize — the canvas is a new size, so a plane
      // mapping taken at the old width picks empty space and silently reports
      // "no offers, no clipping", which reads as a pass.
      const at = await calibratePlane(
        page,
        { x: Math.round(width * 0.42), y: 520 },
        { x: Math.round(width * 0.65), y: 340 },
      );
      const a = at({ x: 24, y: 8 });
      const b = at({ x: 8, y: 24 });
      for (const [name, pick] of [
        ["none", null],
        ["one line", [a]],
        ["two lines", [a, b]],
      ] as Array<[string, Array<{ x: number; y: number }> | null]>) {
        await page.keyboard.press("Escape");
        if (pick !== null) {
          await page.mouse.click(pick[0]!.x, pick[0]!.y);
          for (const p of pick.slice(1)) {
            await page.keyboard.down("Shift");
            await page.mouse.click(p.x, p.y);
            await page.keyboard.up("Shift");
          }
        }
        const offers = await page
          .locator('[data-testid^="verb-hint-"]')
          .evaluateAll((nodes) => nodes.length);
        const census = await clippedControls(page, "sketch-strip");
        table.push({
          width,
          selection: name,
          offers,
          clipped: census.clipped.map((c) => c.testId),
          scrollable: census.scrollable,
        });
      }
    }
    console.log("RAIL-BUDGET", JSON.stringify(table, null, 0));
    // EVERY width in the sweep, not just the ones that happened to be clean.
    // Until QA-R1 was fixed this asserted only >=1440 and the two widths that
    // actually failed were merely LOGGED — a gate that reported the defect to
    // a human instead of to CI. The whole table is the gate now, so the next
    // cell that grows on this strip cannot pass by being wide enough for a
    // developer's monitor.
    const rows = table as Array<{
      width: number;
      selection: string;
      offers: number;
      clipped: string[];
    }>;
    expect(rows.length).toBe(12);
    expect(
      rows.filter((row) => row.clipped.length > 0),
      "no width in the sweep may clip a sketch-strip control",
    ).toEqual([]);
    // …and the offers really were live while it fitted: an empty rail is a
    // trivially-fitting strip, which is how a broken pick reads as a pass.
    expect(
      rows.filter((row) => row.selection === "two lines" && row.offers < 2),
      "two selected lines must offer at least two verbs to make the fit mean anything",
    ).toEqual([]);
  });
});

test.describe("REACH-1 QA — the new verbs across a save and a re-open", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("an angle survives finish/re-open and is still editable", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Angle reopen");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 640, y: 560 },
      { x: 940, y: 380 },
    );
    await drawLine(page, at, { x: 0, y: 0 }, { x: 30, y: 10 });
    await drawLine(page, at, { x: 0, y: 0 }, { x: 10, y: 30 });
    await clickPlane(page, at, { x: 24, y: 8 });
    await addPlane(page, at, { x: 8, y: 24 });
    await expect(page.getByTestId("verb-hint-angle")).toBeVisible();
    await page.keyboard.press("a");
    await page.getByTestId("dimension-input").fill("30");
    await page.getByTestId("dimension-apply").click();
    const angleGlyph = page.locator(
      '[data-testid^="glyph-"][data-kind="angle"]',
    );
    await expect(angleGlyph).toHaveCount(1, { timeout: 20_000 });
    await expect(angleGlyph).toHaveText(/30/, { timeout: 20_000 });

    // Finish the sketch.
    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
      timeout: 30_000,
    });

    // ---- RE-OPEN: the angle has to come back, and come back EDITABLE. ----
    await page.getByTestId("feature-row").first().click({ button: "right" });
    await page.getByTestId("tree-ctx-edit").click();
    await expect(page.getByTestId("sketch-strip")).toBeVisible();
    await expect(
      page.locator('[data-testid^="glyph-"][data-kind="angle"]'),
      "the angle constraint must survive a save and re-open",
    ).toHaveCount(1, { timeout: 30_000 });
    const reopened = page.locator('[data-testid^="glyph-"][data-kind="angle"]');
    console.log(
      "ANGLE-REOPEN",
      JSON.stringify({ text: await reopened.innerText() }),
    );
    await expect(reopened).toHaveText(/30/);

    // Re-drive it to 45 through the glyph — the second edit of the same value.
    await reopened.click();
    const input = page.getByTestId("dimension-input");
    await expect(input).toBeVisible({ timeout: 10_000 });
    await expect(
      input,
      "the editor must prefill the PERSISTED angle, not a fresh measurement",
    ).toHaveValue("30");
    await input.fill("45");
    await input.press("Enter");
    await expect(
      page.locator('[data-testid^="glyph-"][data-kind="angle"]'),
      "the glyph must show the value the solver is now holding",
    ).toHaveText(/45/, { timeout: 20_000 });
  });
});

interface QaSolvedPoint {
  x: number;
  y: number;
}
interface QaSolvedEntity {
  id: string;
  kind: string;
  start?: QaSolvedPoint;
  end?: QaSolvedPoint;
}
interface QaEvaluateBody {
  features: Array<{
    data: { entities: QaSolvedEntity[] } | null;
  }>;
}

function collectEvaluations(page: Page, partId: string): QaEvaluateBody[] {
  const bodies: QaEvaluateBody[] = [];
  page.on("response", (response) => {
    if (
      response.url().includes(`/parts/${partId}/evaluate`) &&
      response.request().method() === "POST" &&
      response.status() === 200
    ) {
      void response
        .json()
        .then((body: QaEvaluateBody) => bodies.push(body))
        .catch(() => undefined);
    }
  });
  return bodies;
}

/** Degrees between the two solved lines of the latest evaluation. */
function solvedAngleDeg(bodies: QaEvaluateBody[]): number | null {
  const entities = bodies[bodies.length - 1]?.features[0]?.data?.entities ?? [];
  const lines = entities.filter(
    (e) => e.kind === "line" && e.start !== undefined && e.end !== undefined,
  );
  if (lines.length < 2) return null;
  const dir = (e: QaSolvedEntity) => ({
    x: (e.end as QaSolvedPoint).x - (e.start as QaSolvedPoint).x,
    y: (e.end as QaSolvedPoint).y - (e.start as QaSolvedPoint).y,
  });
  const u = dir(lines[0] as QaSolvedEntity);
  const v = dir(lines[1] as QaSolvedEntity);
  const scale = Math.hypot(u.x, u.y) * Math.hypot(v.x, v.y);
  if (scale === 0) return null;
  const cos = Math.min(1, Math.max(-1, (u.x * v.x + u.y * v.y) / scale));
  return (Math.acos(cos) * 180) / Math.PI;
}

test.describe("REACH-1 QA — does the angle ANNOTATION track the model?", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("an angle driven by an expression: glyph vs solved geometry", async ({
    page,
  }) => {
    // QA-R2 — was OPEN, now the regression gate. Measured 2/2 before the fix:
    // `ANGLE-EXPR {"shown":"30°","solved":45}` — the solver had moved the model
    // and the annotation had not. The assertion is deliberately made against
    // the EVALUATE payload rather than against the glyph alone: a gate that
    // only reads the glyph passes if the model stops moving too.
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Angle expr");
    const evaluations = collectEvaluations(page, part.id);
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 640, y: 560 },
      { x: 940, y: 380 },
    );
    await drawLine(page, at, { x: 0, y: 0 }, { x: 30, y: 10 });
    await drawLine(page, at, { x: 0, y: 0 }, { x: 10, y: 30 });
    await clickPlane(page, at, { x: 24, y: 8 });
    await addPlane(page, at, { x: 8, y: 24 });
    await page.keyboard.press("a");
    await page.getByTestId("dimension-input").fill("30");
    await page.getByTestId("dimension-apply").click();
    const glyph = page.locator('[data-testid^="glyph-"][data-kind="angle"]');
    await expect(glyph).toHaveText(/30/, { timeout: 20_000 });
    await expect
      .poll(() => solvedAngleDeg(evaluations), { timeout: 20_000 })
      .toBeCloseTo(30, 2);

    // Re-drive the SAME angle with an expression. The server resolves it and
    // moves the model; the annotation has to move with it.
    await glyph.click();
    const input = page.getByTestId("dimension-input");
    await expect(input).toBeVisible();
    await input.fill("15*3");
    await input.press("Enter");

    await expect
      .poll(() => solvedAngleDeg(evaluations), { timeout: 20_000 })
      .toBeCloseTo(45, 2);
    const shown = await glyph.innerText();
    const solved = solvedAngleDeg(evaluations);
    console.log("ANGLE-EXPR", JSON.stringify({ shown, solved }));
    // Captured BEFORE the assertion, so a regression leaves a picture of the
    // glyph that disagreed with the model rather than only a failure message.
    await page.screenshot({ path: "test-results/qa-reach2-angle-expr.png" });
    expect(
      shown,
      "the glyph must not contradict the geometry the solver produced",
    ).toMatch(/45/);
  });

  /**
   * The other half of QA-R2's root cause, and the one an expression test cannot
   * reach: a REFERENCE (driven) angle is MEASURED from the solved geometry, so
   * the client has no number of its own at all — it can only report what the
   * solver sends or lie. Asserted against the evaluate payload rather than a
   * literal, because the point is that the two AGREE, not what they agree on.
   */
  test("a reference angle tracks the geometry when something else moves it", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Angle ref");
    const evaluations = collectEvaluations(page, part.id);
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 640, y: 560 },
      { x: 940, y: 380 },
    );
    await drawLine(page, at, { x: 0, y: 0 }, { x: 30, y: 10 });
    await drawLine(page, at, { x: 0, y: 0 }, { x: 10, y: 30 });
    await clickPlane(page, at, { x: 24, y: 8 });
    await addPlane(page, at, { x: 8, y: 24 });

    // Author it as a REFERENCE: measured, never fed to the solver.
    await page.keyboard.press("a");
    await page.getByTestId("dimension-driven").click();
    await page.getByTestId("dimension-apply").click();
    const glyph = page.locator('[data-testid^="glyph-"][data-kind="angle"]');
    await expect(glyph).toHaveCount(1, { timeout: 20_000 });
    // Drafting convention: a measured value wears parentheses.
    await expect(glyph).toHaveText(/\(/, { timeout: 20_000 });
    const asAuthored = await glyph.innerText();

    // Now MOVE one of the lines with an unrelated constraint. The reference
    // angle has to follow the geometry it measures.
    await page.keyboard.press("Escape");
    await clickPlane(page, at, { x: 24, y: 8 });
    await page.keyboard.press("h");

    await expect
      .poll(
        async () => {
          const solvedNow = solvedAngleDeg(evaluations);
          const text = await glyph.innerText();
          if (solvedNow === null) return false;
          const shownNow = Number.parseFloat(text.replace(/[()°]/g, ""));
          return Math.abs(shownNow - solvedNow) < 0.05;
        },
        { timeout: 25_000 },
      )
      .toBe(true);

    const after = await glyph.innerText();
    console.log(
      "ANGLE-REFERENCE",
      JSON.stringify({
        asAuthored,
        after,
        solved: solvedAngleDeg(evaluations),
      }),
    );
    expect(
      after,
      "the reference reading must change when the geometry it measures does",
    ).not.toBe(asAuthored);
  });
});
