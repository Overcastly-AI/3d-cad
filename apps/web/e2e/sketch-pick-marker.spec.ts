import { expect, test, type Locator, type Page } from "./fixtures";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * SEL-2 — the select tool names what the next click will take.
 *
 * Acceptance A3, `docs/design/pre-selection.md` §6, verbatim: *"Hovering a
 * sketch line with no closer point present shows the extended `SnapMarker`
 * naming the entity kind before the click; the click selects exactly the named
 * candidate."* The founder complaint it answers is a sketch line that *"wouldn't
 * even select"* — picking always resolved a winner and never said which one, so
 * a mis-aim stayed invisible until after the click.
 *
 * ASSERT ON THE INK, NOT ON THE ATTRIBUTE. `data-pick-kind` is convenient and
 * proves nothing a user can see: a sibling deleted the visible word while
 * keeping its attribute and every attribute-shaped case stayed green. So every
 * claim here reads the WORD — `innerText`, which excludes `display:none`, where
 * `textContent` would not — and MEASURES the chip's box, because
 * `toBeVisible()` is a box property that returns true for a node clipped to
 * `1x1 @ (-1,43)` and because a Tailwind utility outside this theme's closed
 * scale emits no rule at all and collapses the element to zero width.
 *
 * 1280x800 throughout: the smallest frame the product supports, and the width
 * the founder shots are taken at.
 */

const marker = (page: Page) => page.getByTestId("pick-marker");
const word = (page: Page) => page.getByTestId("pick-marker").locator("span");

async function enterSketch(page: Page) {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
}

type Mapper = (pt: { x: number; y: number }) => { x: number; y: number };

/**
 * Plane-mm → screen-px mapper: read the DRO at two screen points with the grid
 * off, so every later aim lands on an exact millimetre coordinate.
 */
async function calibratePlane(
  page: Page,
  s1: { x: number; y: number },
  s2: { x: number; y: number },
): Promise<Mapper> {
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

/** A 40x25 rectangle (e1..e4) and a circle centred (20,12.5) r 6 (e5). */
async function drawFixture(page: Page, at: Mapper) {
  await page.keyboard.press("r");
  await clickPlane(page, at, { x: 0, y: 0 });
  await clickPlane(page, at, { x: 40, y: 25 });
  await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
  await page.keyboard.press("c");
  await clickPlane(page, at, { x: 20, y: 12.5 });
  await clickPlane(page, at, { x: 26, y: 12.5 });
  await expect(page.getByTestId("sketch-save")).toContainText("5 entities");
  await page.keyboard.press("Escape"); // back to select
  await expect(page.getByTestId("selection-readout")).toContainText(
    "nothing selected",
  );
}

/**
 * The chip is REAL INK: it has area, it sits inside the frame, and the word it
 * carries is the word a user reads. Returns the measured box so a caller can say
 * where it landed.
 */
async function measuredWord(
  page: Page,
  chip: Locator,
): Promise<{ text: string; width: number; height: number }> {
  const box = await chip.boundingBox();
  expect(box, "the marker's word has no box at all").not.toBeNull();
  const b = box as { x: number; y: number; width: number; height: number };
  expect(
    b.width * b.height,
    `the word has no area (${b.width.toFixed(1)} x ${b.height.toFixed(1)}) — nobody can read it`,
  ).toBeGreaterThan(0);
  const frame = page.viewportSize() as { width: number; height: number };
  expect(b.x, "the word starts off the left edge").toBeGreaterThanOrEqual(0);
  expect(b.y, "the word starts above the top edge").toBeGreaterThanOrEqual(0);
  expect(b.x + b.width, "the word runs off the right edge").toBeLessThanOrEqual(
    frame.width,
  );
  expect(
    b.y + b.height,
    "the word runs off the bottom edge",
  ).toBeLessThanOrEqual(frame.height);
  return {
    // innerText, not textContent: a `display:none` node has textContent and no
    // ink, and this whole spec is about what the user can actually read. The
    // expectations below are UPPERCASE for the same reason — innerText applies
    // `text-transform`, so "LINE" is the rendered ink where textContent would
    // have answered the DOM's "Line". That difference is the evidence.
    text: (await chip.innerText()).trim(),
    width: b.width,
    height: b.height,
  };
}

test.describe("SEL-2 — a sketch pick names itself before the click", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
  });

  test("A3: hovering a line names the entity kind, and the click takes exactly it", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Pick plate");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page);
    const at = await calibratePlane(
      page,
      { x: 560, y: 520 },
      { x: 800, y: 360 },
    );
    await drawFixture(page, at);

    // (30, 0) is on the bottom edge and 10 mm from either corner — "no closer
    // point present", exactly the A3 condition.
    await hoverPlane(page, at, { x: 30, y: 0 });
    await expect(marker(page)).toHaveAttribute("data-pick-kind", "on-curve");
    const line = await measuredWord(page, word(page));
    expect(line.text).toBe("LINE");
    const lineId = await marker(page).getAttribute("data-pick-entity");
    expect(lineId).toMatch(/^e\d+$/);

    // …and the click takes THAT: one entity, and the verbs a LINE unlocks.
    await clickPlane(page, at, { x: 30, y: 0 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    // The offer rail only proposes verbs this exact selection unlocks, so it is
    // an independent witness to WHAT is held: a line offers a distance
    // dimension and can never offer a radius.
    const lineVerbs = (
      await page.getByTestId("dimension-hint").innerText()
    ).toLowerCase();
    expect(lineVerbs).toContain("dimension");
    expect(lineVerbs).not.toContain("radius");
    expect(lineVerbs).not.toContain("diameter");

    // The same aim over the CIRCLE names the circle — the word changes with the
    // subject, which is what makes it information rather than decoration.
    await hoverPlane(page, at, { x: 26, y: 12.5 });
    await expect(marker(page)).toHaveAttribute("data-pick-kind", "on-curve");
    expect((await measuredWord(page, word(page))).text).toBe("CIRCLE");
    expect(await marker(page).getAttribute("data-pick-entity")).not.toBe(
      lineId,
    );

    // The click takes the CIRCLE and not the line it replaced: a circle offers
    // radius/diameter, a line never does. Kind-level identity, from the app's
    // own state rather than from the marker restating itself.
    await clickPlane(page, at, { x: 26, y: 12.5 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    const circleVerbs = (
      await page.getByTestId("dimension-hint").innerText()
    ).toLowerCase();
    expect(circleVerbs).toMatch(/radius|diameter/);
    expect(circleVerbs).not.toContain("dimension");
  });

  test("points reuse the drawing vocabulary — endpoint and centre, by name", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Pick plate");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page);
    const at = await calibratePlane(
      page,
      { x: 560, y: 520 },
      { x: 800, y: 360 },
    );
    await drawFixture(page, at);

    // A corner: two endpoints stack there, and a point outranks the curves.
    await hoverPlane(page, at, { x: 40, y: 25 }, { x: -3, y: 3 });
    await expect(marker(page)).toHaveAttribute("data-pick-kind", "endpoint");
    expect((await measuredWord(page, word(page))).text).toBe("ENDPOINT");
    await page.mouse.down();
    await page.mouse.up();
    await expect(page.getByTestId("selection-readout")).toContainText("1 pt");

    // The circle's centre — a point with no ink of its own, which is precisely
    // the kind of target a user cannot confirm they have hit without the word.
    await page.keyboard.press("Escape");
    await hoverPlane(page, at, { x: 20, y: 12.5 }, { x: 3, y: 3 });
    await expect(marker(page)).toHaveAttribute("data-pick-kind", "center");
    expect((await measuredWord(page, word(page))).text).toBe("CENTRE");
    await page.mouse.down();
    await page.mouse.up();
    await expect(page.getByTestId("selection-readout")).toContainText("1 pt");
  });

  test("the frame is called by its own name, on a sketch with nothing drawn", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Pick plate");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page);
    const at = await calibratePlane(
      page,
      { x: 560, y: 520 },
      { x: 800, y: 360 },
    );

    // The origin and the axes are pickable before anything is drawn, so an
    // EMPTY sketch is exactly where a nameless pick hurts most.
    await hoverPlane(page, at, { x: 0, y: 0 }, { x: 3, y: -2 });
    await expect(marker(page)).toHaveAttribute("data-pick-kind", "origin");
    expect((await measuredWord(page, word(page))).text).toBe("ORIGIN");

    await hoverPlane(page, at, { x: 25, y: 0 });
    await expect(marker(page)).toHaveAttribute("data-pick-kind", "x-axis");
    expect((await measuredWord(page, word(page))).text).toBe("X AXIS");
  });

  test("the word names what the CYCLE will take, not the head of the list", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Pick plate");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page);
    const at = await calibratePlane(
      page,
      { x: 560, y: 520 },
      { x: 800, y: 360 },
    );
    await drawFixture(page, at);

    // A rectangle corner stacks four candidates: two endpoints and two edges.
    // Repeat clicks WALK them (`applyPick`, unchanged) — so a mark reading the
    // head of the list would promise a pick the second click does not make.
    const corner = { x: 0, y: 0 };
    const seen: string[] = [];
    for (let i = 0; i < 4; i += 1) {
      await hoverPlane(page, at, corner, { x: 2, y: 2 });
      await expect(marker(page)).toHaveCount(1);
      const named = `${await marker(page).getAttribute("data-pick-kind")} ${await marker(page).getAttribute("data-pick-entity")}`;
      const wordSeen = (await measuredWord(page, word(page))).text;
      const readout = ["endpoint", "center", "origin"].includes(
        named.split(" ")[0] as string,
      )
        ? "1 pt"
        : "1 ent";
      await page.mouse.down();
      await page.mouse.up();
      // What the word promised is what the selection now holds, every step of
      // the walk — the cycle is narrated instead of silent.
      await expect(page.getByTestId("selection-readout")).toContainText(
        readout,
      );
      seen.push(`${named} · ${wordSeen}`);
    }
    // The walk actually moved: a marker frozen on candidates[0] would repeat.
    expect(new Set(seen).size, seen.join(" | ")).toBeGreaterThan(1);
    expect(seen[0]).not.toBe(seen[1]);
  });

  test("no word chases the cursor while a drag is in flight", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Pick plate");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page);
    const at = await calibratePlane(
      page,
      { x: 560, y: 520 },
      { x: 800, y: 360 },
    );
    await drawFixture(page, at);

    await hoverPlane(page, at, { x: 30, y: 0 });
    await expect(marker(page)).toHaveCount(1);

    // A held pointer is the camera's gesture or nothing's; either way no click
    // is being aimed, so the word steps out of the way instead of sliding
    // across the frame.
    const from = at({ x: 30, y: 0 });
    await page.mouse.down();
    await page.mouse.move(from.x + 40, from.y - 30);
    await expect(marker(page)).toHaveCount(0);
    await page.mouse.move(from.x, from.y);
    await expect(marker(page)).toHaveCount(0);
    await page.mouse.up();
    // …and it comes back on the release, with no further pointer movement:
    // a mark that needed a twitch to reappear would be a dead end of its own.
    await expect(marker(page)).toHaveCount(1);
    expect((await measuredWord(page, word(page))).text).toBe("LINE");
  });
});

/**
 * Founder shots (1280x800). `SEL2_SHOT=before` captures the same hover on the
 * PRE-change tree, where nothing names the pick — the block asserts nothing
 * about the marker so it runs on either tree.
 */
const BEFORE = process.env.SEL2_SHOT === "before";

test.describe("SEL-2 — founder shots", () => {
  test("hovering a line, an endpoint and the origin", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Pick plate");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page);
    const at = await calibratePlane(
      page,
      { x: 560, y: 520 },
      { x: 800, y: 360 },
    );
    await drawFixture(page, at);

    const hovers = [
      ["line", { x: 30, y: 0 }, { x: 0, y: 0 }],
      ["endpoint", { x: 40, y: 25 }, { x: -3, y: 3 }],
      ["circle", { x: 26, y: 12.5 }, { x: 0, y: 0 }],
    ] as const;
    for (const [name, point, nudge] of hovers) {
      await hoverPlane(page, at, point, nudge);
      await page.waitForTimeout(300);
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/sel2-pick-marker-${BEFORE ? "before" : "after"}-${name}-1280.png`,
      });
    }
  });
});
