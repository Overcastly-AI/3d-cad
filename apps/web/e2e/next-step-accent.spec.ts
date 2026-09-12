import { color } from "@loft/design/tokens";

import { expect, test } from "./fixtures";
import type { Page } from "./fixtures";
import { createFeature, seedCube, SQUARE_20 } from "./partSeed";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * FLOW-B3 — after a feature builds, the band proposes ONE next verb.
 *
 * Two halves, and the SECOND is the one this spec exists for. Any spec can
 * prove a dot appears; the property that will rot is the SILENCE — that a verb
 * the table has no reason for proposes nothing at all. A band that starts
 * guessing is the templated affordance the whole wave is written against, and
 * it would fail no test unless one is pointed at it, so one is.
 *
 * The dot is MEASURED, never merely located. This repo has shipped three
 * separate zero-area defects with three different causes (an SVG stroke
 * `getBoundingClientRect` ignores, an `sr-only` element clipped out of frame,
 * and a Tailwind utility the closed scale never generated), and every one of
 * them passed `toBeVisible()`. So the assertions here are a non-zero box AND a
 * count of brass pixels read back out of the composited frame — the mark has to
 * be ink on the screen, not an element in the tree.
 */

/** Every band tool currently wearing the accent. */
const accented = (page: Page) => page.locator("[data-next-step='true']");

/**
 * Brass pixels actually PAINTED inside `box`, read back from a real screenshot.
 *
 * The layout assertions above this cannot see a mark that is transparent,
 * clipped by an ancestor, or painted under something else; a screenshot can,
 * because it is what the user's eye receives. Decoded in-page (the frame goes
 * back into the browser as a bitmap) so no image dependency is needed.
 */
async function brassPixels(
  page: Page,
  box: { x: number; y: number; width: number; height: number },
): Promise<number> {
  const shot = await page.screenshot({ clip: box });
  return page.evaluate(
    async ({ base64, hex }) => {
      const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
      const bitmap = await createImageBitmap(
        new Blob([bytes], { type: "image/png" }),
      );
      const canvas = document.createElement("canvas");
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      const ctx = canvas.getContext("2d");
      if (ctx === null) return -1;
      ctx.drawImage(bitmap, 0, 0);
      const { data } = ctx.getImageData(0, 0, bitmap.width, bitmap.height);
      const value = Number.parseInt(hex.slice(1), 16);
      const target = [(value >> 16) & 255, (value >> 8) & 255, value & 255];
      let count = 0;
      for (let i = 0; i < data.length; i += 4) {
        // A generous tolerance: the mark is anti-aliased against the band, so
        // demanding the exact token value would count only the core pixels.
        const near = target.every(
          (channel, c) => Math.abs((data[i + c] ?? 0) - channel) <= 24,
        );
        if (near) count += 1;
      }
      return count;
    },
    { base64: shot.toString("base64"), hex: color.brass },
  );
}

/** A part with one extruded body, opened in the workspace. */
async function partWithBody(page: Page, name: string): Promise<string> {
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, name);
  await seedCube(page, token, part.id);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("feature-tree")).toBeVisible();
  await expect(page.getByTestId("new-fillet")).toBeEnabled({
    timeout: 30_000,
  });
  return part.id;
}

test.describe("the band proposes one next verb", () => {
  test("a built extrude accents exactly one tool, and it is real ink", async ({
    page,
  }) => {
    await partWithBody(page, "Next step");

    // EXACTLY one. Two marks for one moment is the "three dialects" failure
    // drawn on screen, and it is the cheapest thing in the world to regress.
    await expect(accented(page)).toHaveCount(1);

    // …and it is the right one: the part's FIRST body is the instant the whole
    // MODIFY group stops being disabled, so the proposal is Fillet.
    const fillet = page.getByTestId("new-fillet");
    await expect(fillet).toHaveAttribute("data-next-step", "true");
    // A proposal on a tool you cannot press would be a dead end.
    await expect(fillet).toBeEnabled();
    // The words, for whoever is not looking at the dot.
    await expect(fillet).toHaveAccessibleDescription(
      "Round the new body's edges",
    );

    const dot = fillet.locator("[data-testid='next-step-dot']");
    const box = await dot.boundingBox();
    expect(box).not.toBeNull();
    // NON-ZERO IN BOTH AXES. Not `toBeVisible()` — a 6x0 element passes that.
    expect(box!.width).toBeGreaterThan(0);
    expect(box!.height).toBeGreaterThan(0);
    // The size the component asks for, so a silently-dropped style cannot pass
    // by leaving a 1px sliver behind.
    expect(box!.width).toBeGreaterThanOrEqual(5);
    expect(box!.height).toBeGreaterThanOrEqual(5);

    // …and it is PAINTED. A 6x6 disc of r=2.5 covers ~19.6 device px; anything
    // under ten and the mark is not on screen whatever the layout says.
    const painted = await brassPixels(page, {
      x: box!.x - 2,
      y: box!.y - 2,
      width: box!.width + 4,
      height: box!.height + 4,
    });
    expect(painted).toBeGreaterThanOrEqual(10);

    // It is a PROPOSAL, not a state: the active scribe and `aria-pressed`
    // already mean "this tool is on" and must not be borrowed for this.
    await expect(fillet).not.toHaveAttribute("aria-pressed", "true");
    expect(await fillet.locator("[data-scribe]").count()).toBe(0);
  });

  test("opening any command retires the accent, and it does not come back", async ({
    page,
  }) => {
    await partWithBody(page, "Next step dismiss");
    await expect(accented(page)).toHaveCount(1);

    await page.getByTestId("new-fillet").click();
    await expect(page.getByTestId("in-command")).toBeVisible();
    await expect(accented(page)).toHaveCount(0);

    // Backing out must not re-arm it: the user has already said what they were
    // doing next, and a mark that returns is a nag rather than a proposal.
    await page.getByTestId("in-command-cancel").click();
    await expect(page.getByTestId("in-command")).toHaveCount(0);
    await expect(accented(page)).toHaveCount(0);
  });

  test("proposes NOTHING after a feature the table has no reason for", async ({
    page,
  }) => {
    // The half that rots. A datum is body-affecting in no sense and follows
    // nothing in particular, so the honest answer is silence — the band must
    // not reach for the nearest plausible verb.
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "No proposal");
    const version = await seedCube(page, token, part.id);
    await createFeature(page, token, part.id, {
      name: "Datum1",
      feature: {
        type: "datum",
        version: 1,
        params: { kind: "offset", base: "XY", offset_mm: 5 },
      },
      expected_tree_version: version,
    });

    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("feature-tree")).toBeVisible();
    await expect(page.getByTestId("new-fillet")).toBeEnabled({
      timeout: 30_000,
    });

    // The body is still there and MODIFY is still unlocked — this is silence,
    // not an absent band.
    await expect(page.getByTestId("new-hole")).toBeEnabled();
    await expect(accented(page)).toHaveCount(0);
  });

  test("a second body of the same verb proposes that verb again", async ({
    page,
  }) => {
    // The repeat row, end to end: boss-then-cut is the common pair, so once a
    // body exists an extrude proposes another extrude rather than the
    // first-body Fillet.
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Repeat row");
    let version = await seedCube(page, token, part.id);
    const sketch = await createFeature(page, token, part.id, {
      name: "Sketch2",
      // The same 20mm square, extruded as a CUT this time: the second body-
      // affecting extrude is all this case needs, and reusing the shared
      // fixture keeps it from drifting from every other seeded part.
      feature: { type: "sketch", version: 1, params: SQUARE_20 },
      expected_tree_version: version,
    });
    version = sketch.tree_version;
    await createFeature(page, token, part.id, {
      name: "Extrude2",
      feature: {
        type: "extrude",
        version: 1,
        params: {
          profile: { kind: "feature", feature_id: sketch.feature.id },
          distance_mm: 30,
          operation: "cut",
          direction: "normal",
        },
      },
      expected_tree_version: version,
    });

    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("feature-tree")).toBeVisible();
    await expect(page.getByTestId("new-extrude")).toBeEnabled({
      timeout: 30_000,
    });

    await expect(accented(page)).toHaveCount(1);
    await expect(page.getByTestId("new-extrude")).toHaveAttribute(
      "data-next-step",
      "true",
    );
    await expect(page.getByTestId("new-extrude")).toHaveAccessibleDescription(
      "Another extrude on this body",
    );
  });

  test("founder frame — the band after a body builds", async ({ page }) => {
    await partWithBody(page, "Bracket plate");
    await expect(accented(page)).toHaveCount(1);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/next-step-accent-${page.viewportSize()?.width ?? 0}.png`,
    });
  });
});
