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

/** `color.brass` as the browser reports a resolved colour. */
const brassRgb = (() => {
  const v = Number.parseInt(color.brass.slice(1), 16);
  return `rgb(${(v >> 16) & 255}, ${(v >> 8) & 255}, ${v & 255})`;
})();

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
  /**
   * A rect (page coords) whose pixels are NOT counted — how one mark's reading
   * is kept out of another's. The glyph's 16px box and the dot's 6px corner
   * overlap by 2x2px on this band, so "measure them in different places" is not
   * something adjacency gives you for free; subtracting makes the two readings
   * disjoint by construction instead of by luck, which is the whole reason
   * there are two of them.
   */
  exclude?: { x: number; y: number; width: number; height: number },
): Promise<number> {
  const shot = await page.screenshot({ clip: box });
  // Into the clip's own coordinates, inflated a pixel so an anti-aliased edge
  // of the excluded mark cannot leak into the count.
  const cut =
    exclude === undefined
      ? null
      : {
          x0: exclude.x - box.x - 1,
          y0: exclude.y - box.y - 1,
          x1: exclude.x - box.x + exclude.width + 1,
          y1: exclude.y - box.y + exclude.height + 1,
        };
  return page.evaluate(
    async ({ base64, hex, cut }) => {
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
        if (cut !== null) {
          const px = (i / 4) % bitmap.width;
          const py = Math.floor(i / 4 / bitmap.width);
          if (px >= cut.x0 && px < cut.x1 && py >= cut.y0 && py < cut.y1) {
            continue;
          }
        }
        // A generous tolerance: the mark is anti-aliased against the band, so
        // demanding the exact token value would count only the core pixels.
        const near = target.every(
          (channel, c) => Math.abs((data[i + c] ?? 0) - channel) <= 24,
        );
        if (near) count += 1;
      }
      return count;
    },
    { base64: shot.toString("base64"), hex: color.brass, cut },
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
    // Counted before it is measured: `boundingBox()` on a missing element waits
    // out the timeout and then reports a null deref, so deleting the dot would
    // redden this spec with a message naming neither the dot nor the reason.
    await expect(dot).toHaveCount(1);
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

    // THE GLYPH — the escalation, and it needs a SECOND, differently-derived
    // check rather than a bigger number on the one above. An ink count over the
    // whole tool could be satisfied by either half alone, so it could not fail
    // for its own reason: delete the dot and the brass glyph still clears it;
    // drop the brass and the dot still clears it. The two regions are disjoint
    // on screen — the glyph is centred in the 32px cell and the dot sits in its
    // top-right corner — so measuring the glyph's OWN box is a genuinely
    // independent reading of different pixels, not a re-count of the same ones.
    const glyph = fillet.locator("svg:not([data-testid='next-step-dot'])");
    await expect(glyph).toHaveCount(1);
    const glyphBox = (await glyph.boundingBox())!;
    expect(glyphBox).not.toBeNull();
    // The dot's pixels SUBTRACTED — measured, the two boxes overlap by a 2x2px
    // corner (glyph 342..358, dot 356..362 on the x axis), so without this the
    // glyph reading would quietly include up to four of the dot's pixels and
    // the "independent" claim would be false by exactly the amount that
    // matters. Everything counted below is glyph ink and nothing else.
    expect(await brassPixels(page, glyphBox, box!)).toBeGreaterThanOrEqual(8);

    // …and a THIRD derivation from the DOM rather than from pixels: the stroke
    // the glyph actually resolves `currentColor` to. This is what catches the
    // colour arriving from the wrong place — the wrapper is `display: contents`
    // and works purely by inheritance, so a stylesheet-order change could take
    // the ink away while every pixel count still passed on some other mark.
    const stroke = await glyph.evaluate((el) => getComputedStyle(el).stroke);
    expect(stroke).toBe(brassRgb);

    // It is a PROPOSAL, not a state: the active scribe and `aria-pressed`
    // already mean "this tool is on" and must not be borrowed for this.
    await expect(fillet).not.toHaveAttribute("aria-pressed", "true");
    expect(await fillet.locator("[data-scribe]").count()).toBe(0);
  });

  test("an accented tool and an ACTIVE tool are tellable apart on screen", async ({
    page,
  }) => {
    // The escalation's one real risk, stated as a test rather than as a note.
    // Brass on the glyph is what `active` already means, so once a proposal
    // borrows it the two states share their loudest signal and the difference
    // rests entirely on the bottom scribe. An absence-only assertion ("the
    // accented tool has no scribe") cannot show that the difference is
    // VISIBLE — it would pass just as happily if nothing on the band ever drew
    // a scribe at all. So this puts both states on screen at once and reads
    // each of them.
    await partWithBody(page, "Accent vs active");

    // Measure is a MODE toggle, not a command, so it does not lock the band or
    // retire the proposal — which is what lets both states coexist here.
    await page.getByTestId("measure-tool").click();
    const active = page.getByTestId("measure-tool");
    await expect(active).toHaveAttribute("aria-pressed", "true");
    const accentedTool = page.getByTestId("new-fillet");
    await expect(accentedTool).toHaveAttribute("data-next-step", "true");

    const glyphOf = (tool: typeof active) =>
      tool.locator("svg:not([data-testid='next-step-dot'])");
    // Both glyphs are brass — the honest statement of the risk, asserted rather
    // than hoped. If this ever stops being true the test below is measuring a
    // difference that was never in doubt.
    expect(
      await glyphOf(active).evaluate((el) => getComputedStyle(el).stroke),
    ).toBe(brassRgb);
    expect(
      await glyphOf(accentedTool).evaluate((el) => getComputedStyle(el).stroke),
    ).toBe(brassRgb);

    // The scribe is the difference, and it is REAL INK on the active one: a
    // 0x0 scribe would make the two states identical on screen while passing
    // every count-based assertion (this band shipped exactly that defect for
    // months — `inset-x-1.5`/`h-px` were missing from the closed scale).
    const scribe = active.locator("[data-scribe]");
    await expect(scribe).toHaveCount(1);
    const scribeBox = (await scribe.boundingBox())!;
    expect(scribeBox.width).toBeGreaterThan(8);
    expect(scribeBox.height).toBeGreaterThan(0);
    expect(await brassPixels(page, scribeBox)).toBeGreaterThanOrEqual(8);

    // …and the accented one has none of it, while carrying the dot the active
    // one does not. Two marks, two directions — neither state is a subset of
    // the other, so neither can be mistaken for it.
    expect(await accentedTool.locator("[data-scribe]").count()).toBe(0);
    await expect(accentedTool).not.toHaveAttribute("aria-pressed", "true");
    await expect(
      accentedTool.locator("[data-testid='next-step-dot']"),
    ).toHaveCount(1);
    await expect(active.locator("[data-testid='next-step-dot']")).toHaveCount(
      0,
    );
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
