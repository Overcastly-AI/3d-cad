import { expect, test, type Page } from "./fixtures";

import { createFeature, SQUARE_20 } from "./partSeed";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * SKETCH-1 — A SAVED SKETCH RE-OPENS, AND THE RE-SAVE IS AN UPDATE.
 *
 * `selectFeature` had a branch per feature type and none for `sketch`, so
 * selecting (or right-click → Edit-ing) a sketch fell through to
 * `setEditor(null)`: a silent no-op, no toast, no request. Every driving
 * dimension in a part was therefore write-once — the solver, the dimension
 * expressions and the topological-naming survival were reachable on the FIRST
 * pass through a sketch only.
 *
 * This spec drives the whole repair against the real stack:
 *   (1) the sketcher opens PAST the plane pick, on the saved plane, carrying
 *       the saved ink and every one of the saved constraints;
 *   (2) editing a driving dimension PATCHes the SAME feature — no second
 *       "Sketch2" — and the downstream extrude rebuilds against the new
 *       profile, which the body's volume proves.
 *
 * The hydration assertions are deliberately about CONTENT (which glyphs, whose
 * entities, the dimension's own value, the rebuilt volume), not about "a
 * sketcher appeared": reverting the `beginEdit` hydration to a plain `begin()`
 * must redden this file, and a "the strip is visible" assertion would sail
 * straight through it.
 *
 * WHY NOT A CANVAS-INK CENSUS. The first draft polled
 * `countTokenPixels(page, "#E9F1F8")` for live scribe ink and measured **0** on
 * a frame whose attached screenshot showed the sketch fully re-opened —
 * profile, glyphs, DOF 0 CONVERGED. That is the exact-token failure mode
 * `sketch-visibility.spec.ts` documents at length (a 1 px GL line lands on its
 * literal token only where it happens to cover a whole pixel; 0 on 5 of 10
 * HEALTHY runs there), and the coverage instrument that replaces it needs a
 * calibrated ground box that this frame — sketch ink over a lit body face —
 * does not offer. Hydration is asserted in the DOM here, where it is exact, and
 * the ENTITY GEOMETRY is proven where it actually matters: by the volume the
 * downstream extrude rebuilds to.
 */

/** The bottom edge's driving 20 mm distance in {@link SQUARE_20}. */
const WIDTH_GLYPH = "glyph-8";

/** Seed a 20 mm cube via the API and hand back its sketch feature id. */
async function seedCubeReturningSketchId(
  page: Page,
  token: string,
  partId: string,
): Promise<string> {
  const sketch = await createFeature(page, token, partId, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: SQUARE_20 },
    expected_tree_version: 0,
  });
  await createFeature(page, token, partId, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 20,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  return sketch.feature.id;
}

/** The body volume (mm³) — the cell carries its label + unit, so parse. */
async function bodyVolume(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  const match = text.match(/[\d,]+(?:\.\d+)?/);
  return match ? Number.parseFloat(match[0].replace(/,/g, "")) : Number.NaN;
}

test.describe("SKETCH-1 — re-opening a saved sketch", () => {
  test("hydrates the saved sketch and re-saves it as an UPDATE, rebuilding the extrude", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Reopen");
    const sketchId = await seedCubeReturningSketchId(page, token, part.id);

    // Every feature write the BROWSER makes from here on. The seeding above
    // went through `page.request` (a separate context that fires no page
    // events), so this list is exactly what the re-open flow itself sends.
    const writes: { method: string; path: string }[] = [];
    page.on("request", (request) => {
      const { pathname } = new URL(request.url());
      if (!pathname.startsWith(`/api/v1/parts/${part.id}/features`)) return;
      if (request.method() === "GET") return;
      writes.push({ method: request.method(), path: pathname });
    });

    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    expect(await bodyVolume(page)).toBeCloseTo(8_000, 1); // 20 x 20 x 20
    await expect(page.getByTestId("feature-row")).toHaveCount(2);

    // Founder BEFORE shot: the part as it stands with the sketch saved. In the
    // build this spec fixes, this frame is ALSO the "after" — Edit on the
    // Sketch1 row left the user looking at exactly this, with no toast, no
    // request, and no way in.
    await page.mouse.move(1400, 900); // park the cursor off the model
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-reopen-before-desktop.png`,
    });

    // ---- (1) Re-open through the tree row's right-click Edit --------------
    await page.getByTestId("feature-row").first().click({ button: "right" });
    await page.getByTestId("tree-ctx-edit").click();

    // Straight to the DRAW step on the saved plane: there is no plane to pick,
    // so a re-open that stopped at the plane picker would be a dead end.
    await expect(page.getByTestId("sketch-strip")).toBeVisible();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY");

    // EVERY constraint came back — one glyph each.
    await expect(page.locator('[data-testid^="glyph-"]')).toHaveCount(
      SQUARE_20.constraints.length,
    );
    await expect(page.getByTestId(WIDTH_GLYPH)).toHaveText("20");

    // …AND THE ENTITIES CAME BACK WITH THEM, which is a separate claim and is
    // asserted separately. `constraintGlyphs` anchors a horizontal / vertical /
    // distance mark ON ITS ENTITY and SKIPS the constraint outright when that
    // entity is absent, so these six are exactly the glyphs an entity-less
    // hydration cannot paint: constraints alone would leave only the four
    // coincidents and the fix.
    for (const [kind, count] of [
      ["horizontal", 2],
      ["vertical", 2],
      ["distance", 2],
    ] as const) {
      await expect(
        page.locator(`[data-testid^="glyph-"][data-kind="${kind}"]`),
        `${kind} glyphs anchor on entities — a count of 0 means the entities did not hydrate`,
      ).toHaveCount(count);
    }

    // Founder AFTER shot: the same click now lands in the sketcher, normal-on
    // the saved plane, every entity and constraint back and the solve green.
    await page.mouse.move(1400, 900);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-reopen-after-desktop.png`,
    });

    // ---- (2) Change a driving dimension and finish ------------------------
    await page.getByTestId(WIDTH_GLYPH).click();
    const input = page.getByTestId("dimension-input");
    await expect(input).toBeVisible();
    await expect(input).toHaveValue("20"); // the PERSISTED value, re-editable
    await input.fill("30");
    await input.press("Enter");
    await expect(page.getByTestId(WIDTH_GLYPH)).toHaveText("30");

    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    // The write was an UPDATE of the same feature — never a create. A POST here
    // is the old "Sketch2" defect: a second sketch nothing extrudes.
    await expect
      .poll(() => writes.filter((w) => w.method === "PATCH").length, {
        timeout: 15_000,
      })
      .toBeGreaterThan(0);
    expect(writes.filter((w) => w.method === "POST")).toEqual([]);
    for (const write of writes) {
      expect(write).toEqual({
        method: "PATCH",
        path: `/api/v1/parts/${part.id}/features/${sketchId}`,
      });
    }
    // …and the tree agrees: still two features, still one sketch.
    await expect(page.getByTestId("feature-row")).toHaveCount(2);

    // The DOWNSTREAM extrude rebuilt against the new profile: 30 x 20 x 20.
    await expect
      .poll(() => bodyVolume(page), { timeout: 30_000 })
      .toBeCloseTo(12_000, 1);
  });
});
