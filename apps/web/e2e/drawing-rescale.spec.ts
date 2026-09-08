// The pick band's width, from the design token rather than a literal — the
// bound below is derived from it.
import { drawing } from "@loft/design/tokens";

import { expect, test, type Page } from "./fixtures";

import { seedSession } from "./support";

/**
 * SHEET-RESCALE-1 + SHEET-RESCALE-2 — a laid-out sheet can be re-scaled, and a
 * person can do it.
 *
 * Before this verb the scale a sheet was drafted at was PERMANENT, and not for
 * want of a control: documents' H2 invariant ("one sheet, one source, one
 * scale") compares an incoming per-view scale against `siblings[0]`, which
 * still holds the OLD scale whichever view a client writes first — so the FIRST
 * write of any view-by-view re-scale is refused, in every ordering. There was
 * no legal sequence, so the only way to re-scale a drawing was to delete the
 * sheet and draft it again.
 *
 * `SheetUpdate.scale` rewrites every view in ONE documents transaction, which
 * satisfies the invariant instead of relaxing it. This spec drives that through
 * the real stack and asserts on what a drafter actually sees: the composed
 * sheet is re-projected at the new scale, the TITLE BLOCK — composed
 * server-side from `views[0].scale` — states it, and every view is drawn
 * smaller by the ratio asked for. A status code would prove only that the
 * request parsed (the DTOs are `extra="ignore"`, so a mis-spelled field returns
 * 200 and re-scales nothing); the geometry on the page is the claim.
 *
 * The two refusals are asserted here too, in the same place as the capability:
 * a capability that quietly widened a guard is a regression wearing a feature's
 * clothes, so the spec that adds the verb is the right place to prove the guard
 * still bites.
 *
 * SHEET-RESCALE-2: the first case is DRIVEN BY THE PICKER. It used to be called
 * "re-picking the scale re-draws every view" and re-picked nothing — it issued
 * `page.request.patch` — which is precisely how the missing gesture stayed
 * invisible: the verb had no mouse path for a week and the spec named after
 * that path was green throughout. A case that claims a gesture makes it; the
 * two that remain API-driven below are refusals, and say so in their titles.
 */

/** A 60 x 40 x 30 mm block via the real gateway. The scale the four standard
 * views land at is the FIT's business, not this spec's — every case below reads
 * it back rather than assuming it (measured today: 1:2), because a spec that
 * hard-codes the fit goes red for the fit model changing, not for the verb
 * under test breaking. */
async function createBlockViaApi(
  page: Page,
  token: string,
  name: string,
): Promise<{ id: string }> {
  const auth = { Authorization: `Bearer ${token}` };
  const part = await page.request.post("/api/v1/parts", {
    data: { name },
    headers: auth,
  });
  if (!part.ok()) {
    throw new Error(
      `create part failed: ${part.status()} ${await part.text()}`,
    );
  }
  const partId = ((await part.json()) as { id: string }).id;

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
              end: { x: 60, y: 0 },
            },
            {
              id: "e2",
              kind: "line",
              start: { x: 60, y: 0 },
              end: { x: 60, y: 40 },
            },
            {
              id: "e3",
              kind: "line",
              start: { x: 60, y: 40 },
              end: { x: 0, y: 40 },
            },
            {
              id: "e4",
              kind: "line",
              start: { x: 0, y: 40 },
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
  if (!sketch.ok()) {
    throw new Error(`sketch failed: ${sketch.status()} ${await sketch.text()}`);
  }
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
          distance_mm: 30,
          operation: "add",
          direction: "normal",
        },
      },
      expected_tree_version: sketchBody.tree_version,
    },
    headers: auth,
  });
  if (!extrude.ok()) {
    throw new Error(
      `extrude failed: ${extrude.status()} ${await extrude.text()}`,
    );
  }
  return { id: partId };
}

/** Open a fresh drawing on the empty bench and lay out the standard views. */
async function seedLaidOutDrawing(
  page: Page,
  partId: string,
  name: string,
): Promise<string> {
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
  return new URL(page.url()).pathname.split("/").pop() ?? "";
}

/** The drawing's tree, straight off the gateway — the ids + version a sheet
 * write needs, read the way the app reads them. */
async function readTree(
  page: Page,
  token: string,
  drawingId: string,
): Promise<{
  docVersion: number;
  sheetId: string;
  viewIds: string[];
  scales: string[];
}> {
  const response = await page.request.get(`/api/v1/drawings/${drawingId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) {
    throw new Error(`read tree failed: ${response.status()}`);
  }
  const body = (await response.json()) as {
    doc_version: number;
    sheets: {
      sheet: { id: string };
      views: {
        id: string;
        scale: { numerator: number; denominator: number };
      }[];
    }[];
  };
  const content = body.sheets[0];
  if (content === undefined) {
    throw new Error(`drawing ${drawingId} has no sheet to read`);
  }
  return {
    docVersion: body.doc_version,
    sheetId: content.sheet.id,
    viewIds: content.views.map((v) => v.id),
    scales: content.views.map(
      (v) => `${v.scale.numerator}:${v.scale.denominator}`,
    ),
  };
}

/** The ONE scale a laid-out sheet is drafted at, read rather than assumed.
 *
 * Checked instead of indexed on purpose: under `noUncheckedIndexedAccess` a bare
 * `scales[0]` is `string | undefined`, and quietly comparing against `undefined`
 * is how a spec goes green while measuring nothing. A sheet with no views has no
 * scale, and that is a broken fixture, so it fails here by name.
 */
function draftedScale(scales: string[]): {
  label: string;
  denominator: number;
} {
  const label = scales[0];
  if (label === undefined) {
    throw new Error("the sheet has no views, so it has no scale to read");
  }
  const denominator = Number(label.split(":")[1]);
  if (!Number.isFinite(denominator) || denominator < 1) {
    throw new Error(`unreadable sheet scale ${label}`);
  }
  return { label, denominator };
}

const STRAIGHT_EDGE =
  '[data-testid="drawing-pick-edge"][data-primitive="line"]';

/** The longest drawn EDGE in each standard view, in SHEET MILLIMETRES.
 *
 * Three measurements were available here and only one of them can carry an
 * exact claim.
 *
 * - The `drawing-view` GROUP's box is wrong: it includes the view LABEL and the
 *   placement frame, which are chrome and do not scale with the model —
 *   measured, the group shrinks by 0.69 across a 2x re-scale, which turns an
 *   exact assertion into a vague "it got somewhat smaller".
 * - An edge's screen `boundingBox()` is nearly right and quietly is not: the
 *   pick band is `drawing.pickHitMm` (2.6 mm) wide in SHEET space, so it does
 *   NOT scale with the model and `hypot(w, h)` therefore carries a constant
 *   term. Across 1:2 -> 1:5 on the 60 mm edge that reads ~0.408 where 0.400 is
 *   the truth — small enough to wave through as tolerance, and it is not
 *   tolerance. It is still a fine COARSE check, and the case below uses it as
 *   one, beside the exact reading.
 * - The band `<rect>`'s own `width` IS the projected segment length in sheet
 *   millimetres, with no chrome in it. That is what this returns, and it is why
 *   the ratios below are asserted to five places instead of inside a band.
 *
 * STRAIGHT edges only, in both readers, because the screen-side bound below is
 * derived for a rotated BAND and a circle is not one: a disc's box diagonal is
 * `2r*sqrt(2)`, which for r = 5 mm exceeds the `L + t` ceiling that derivation
 * relies on. Scoping both to `data-primitive="line"` keeps the two readings
 * about the same class of thing instead of leaving a branch that is unreachable
 * on this fixture and wrong on the first one with a hole in it. (The QA spec's
 * `edgeMetrics` does measure circles — it carries no screen-side bound.)
 *
 * The composer produces these lengths, so the numbers are the server's, not the
 * browser's arithmetic.
 */
async function longestEdges(page: Page): Promise<Record<string, number>> {
  for (const projection of ["front", "top", "right", "iso"]) {
    await expect(
      page.locator(`${STRAIGHT_EDGE}[data-view="${projection}"]`).first(),
    ).toBeAttached({ timeout: 30_000 });
  }
  const sizes = await page.evaluate((selector) => {
    const out: Record<string, number> = {};
    for (const group of document.querySelectorAll<SVGGElement>(selector)) {
      const view = group.getAttribute("data-view") ?? "?";
      let longest = out[view] ?? 0;
      for (const band of group.querySelectorAll<SVGRectElement>("rect")) {
        longest = Math.max(longest, band.width.baseVal.value);
      }
      out[view] = longest;
    }
    return out;
  }, STRAIGHT_EDGE);
  for (const projection of ["front", "top", "right", "iso"]) {
    if (!sizes[projection]) {
      throw new Error(`no measurable straight edge in the ${projection} view`);
    }
  }
  return sizes;
}

/** The same views measured the way the SCREEN shows them — a second, coarser
 * derivation (page pixels, chrome and all) so the exact reading above is not the
 * only witness that the drawing actually redrew. */
async function longestEdgesOnScreen(
  page: Page,
): Promise<Record<string, number>> {
  const sizes: Record<string, number> = {};
  for (const projection of ["front", "top", "right", "iso"]) {
    const edges = page.locator(`${STRAIGHT_EDGE}[data-view="${projection}"]`);
    await expect(edges.first()).toBeAttached({ timeout: 30_000 });
    const count = await edges.count();
    let longest = 0;
    for (let i = 0; i < count; i += 1) {
      const box = await edges.nth(i).boundingBox();
      if (!box) continue;
      longest = Math.max(longest, Math.hypot(box.width, box.height));
    }
    if (longest === 0) {
      throw new Error(`no measurable edge in the ${projection} view`);
    }
    sizes[projection] = longest;
  }
  return sizes;
}

/**
 * The scales the picker actually offers, largest ratio first — read from THE
 * CONTROL, so this cannot drift from the product's own ladder.
 *
 * A gesture can only choose from this list, which an API-driven case is free to
 * ignore: doubling a denominator names 1:4, a scale the server accepts happily
 * and no control can express. That gap is the whole reason case 1 below could
 * claim to re-pick while issuing a PATCH.
 *
 * Importing `SCALE_OPTIONS` is the obvious DRY move and does not work:
 * `apps/web/src/drawing/layout.ts` imports the ROOT of `@loft/design`, whose
 * index pulls in the Tailwind preset, and Node — which transforms specs itself,
 * without Vite — cannot resolve that file's extensionless `tailwindcss/plugin`
 * (measured: "No tests found", before any test runs). Reading the DOM is not a
 * workaround for that, though: it is the better oracle either way, because the
 * question this spec asks is what the USER can pick, and the answer is in the
 * control rather than in a constant that feeds it.
 */
async function offeredScales(
  page: Page,
): Promise<{ value: string; ratio: number }[]> {
  const values = await page
    .getByTestId("drawing-scale-select")
    .locator("option:not([disabled])")
    .evaluateAll((options) =>
      options.map((option) => (option as HTMLOptionElement).value),
    );
  if (values.length < 2) {
    throw new Error(`the picker offers nothing to change to: ${values}`);
  }
  return values
    .map((value) => {
      const [numerator, denominator] = value.split(":").map(Number);
      if (!numerator || !denominator) {
        throw new Error(`unreadable scale ${value}`);
      }
      return { value, ratio: numerator / denominator };
    })
    .sort((a, b) => b.ratio - a.ratio);
}

/** The next scale DOWN the ladder from the one the sheet was drafted at — a
 * reduction, so the re-scaled sheet cannot overflow its paper and turn this
 * case into a test of the layout-issue banner instead. Carries the exact factor
 * every projected edge must then move by. */
async function nextSmallerScale(
  page: Page,
  drafted: string,
): Promise<{ value: string; ratioFrom: number }> {
  const ladder = await offeredScales(page);
  const index = ladder.findIndex((option) => option.value === drafted);
  if (index < 0) {
    throw new Error(`the fit chose ${drafted}, which the picker cannot offer`);
  }
  const from = ladder[index];
  const target = ladder[index + 1];
  if (from === undefined || target === undefined) {
    throw new Error(`${drafted} is the bottom of the ladder; nothing to pick`);
  }
  return { value: target.value, ratioFrom: target.ratio / from.ratio };
}

test.describe("drawings — re-scaling a laid-out sheet", () => {
  test("re-picking the scale re-draws every view, and the title block agrees", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createBlockViaApi(page, account.token, "Rescale block");
    const drawingId = await seedLaidOutDrawing(
      page,
      part.id,
      "Rescale block drawing",
    );

    // The scale the layout CHOSE is read, never assumed: `fitScale` reduces the
    // picked scale until the four views fit their cells, so hard-coding it here
    // would make this spec fail the day the fit model or the cell padding
    // changes — a false red about the thing under test.
    const tree = await readTree(page, account.token, drawingId);
    expect(tree.viewIds).toHaveLength(4);
    expect(new Set(tree.scales).size, "the sheet must start at ONE scale").toBe(
      1,
    );
    const drafted = draftedScale(tree.scales);
    const picked = await nextSmallerScale(page, drafted.label);
    const target = picked.value;
    const expected = picked.ratioFrom;

    // The CONTROL, not a readout of it. Until SHEET-RESCALE-2 this cell was a
    // `Readout` post-layout, so `onSelectScale` had one call site in a branch
    // that never rendered and the verb below had no gesture at all — the whole
    // point of this case, and the reason it drives the picker instead of
    // issuing the PATCH itself (which is what it used to do while its title
    // claimed otherwise).
    const picker = page.getByTestId("drawing-scale-select");
    await expect(picker).toBeVisible();
    await expect(picker).toBeEnabled();
    await expect(picker).toHaveValue(drafted.label);
    await expect(page.getByTestId("title-block-scale")).toHaveText(
      drafted.label,
    );
    // `toBeVisible` is a box property and passes on a control clipped out of
    // the frame, so the question is asked the user's way: does a click at the
    // centre of this cell land on this cell?
    const reachable = await picker.evaluate((el) => {
      const r = el.getBoundingClientRect();
      const hit = document.elementFromPoint(
        r.left + r.width / 2,
        r.top + r.height / 2,
      );
      return hit === el || el.contains(hit);
    });
    expect(reachable, "the Scale picker must be clickable").toBe(true);

    const before = await longestEdges(page);
    const beforeOnScreen = await longestEdgesOnScreen(page);
    const sheetBefore = await page.getByTestId("drawing-sheet").boundingBox();

    // THE GESTURE. A real pick on the real control — no request from the spec.
    await picker.selectOption(target);

    // The title block is composed SERVER-side from `views[0].scale`, so waiting
    // on it is waiting for the round trip: the sheet on screen is the one the
    // server re-composed, not an optimistic local redraw.
    await expect(page.getByTestId("title-block-scale")).toHaveText(target, {
      timeout: 30_000,
    });
    await expect(picker).toHaveValue(target);
    await expect(page.getByTestId("drawing-sheet")).toHaveAccessibleName(
      new RegExp(`at ${target}`),
    );

    // Every stored view moved together — the state H2 requires, reached in one
    // hop from a state no per-view sequence could have left. One write against
    // the SHEET, not four against its views: `doc_version` advances by exactly
    // one.
    const after = await readTree(page, account.token, drawingId);
    expect(new Set(after.scales)).toEqual(new Set([target]));
    expect(after.viewIds.sort()).toEqual(tree.viewIds.sort());
    expect(after.docVersion).toBe(tree.docVersion + 1);

    // The GEOMETRY, not just the label. These are projected EDGE lengths in
    // sheet millimetres, so the re-scale must move them by EXACTLY the ratio of
    // the two scales; a band wide enough to admit "somewhat smaller" would also
    // admit a partial re-scale, which is the failure this verb exists to make
    // impossible. The sheet's own box is checked first, because a mm reading is
    // only comparable across the two measurements while the paper on screen is
    // the same size.
    const sheetAfter = await page.getByTestId("drawing-sheet").boundingBox();
    expect(sheetBefore, "the sheet must be measurable").not.toBeNull();
    expect(sheetAfter?.width ?? 0).toBeCloseTo(sheetBefore?.width ?? -1, 1);
    expect(sheetAfter?.height ?? 0).toBeCloseTo(sheetBefore?.height ?? -1, 1);

    const shrunk = await longestEdges(page);
    const shrunkOnScreen = await longestEdgesOnScreen(page);
    for (const projection of ["front", "top", "right", "iso"]) {
      const now = shrunk[projection];
      const was = before[projection];
      if (now === undefined || was === undefined) {
        throw new Error(`the ${projection} view was not measured`);
      }
      expect(
        now / was,
        `${projection} must be drawn at ${target} (${now} mm from ${was} mm)`,
      ).toBeCloseTo(expected, 5);

      // ...and the second derivation agrees, inside a bound DERIVED rather than
      // guessed. A band of length L and thickness t rotated by theta has a
      // bounding box of `L·c + t·s` by `L·s + t·c`, so the diagonal measured
      // above is `sqrt(L² + t² + 4Ltcs)` — between `hypot(L, t)` and `L + t`
      // for every edge and every angle. That holds per edge, so it holds for
      // the longest one whichever edge that turns out to be, in mm or in px.
      //
      // A flat ±0.05 was the first attempt and it was WRONG, not merely loose:
      // the iso view's longest edge is short enough that the constant band
      // dominates, and it measured 0.4526 against an expected 0.4000 — a real
      // number the assertion had no business rejecting. The bound below admits
      // it and still refuses a view that failed to redraw (ratio 1.0) or one
      // drawn at the wrong scale.
      const nowPx = shrunkOnScreen[projection];
      const wasPx = beforeOnScreen[projection];
      if (nowPx === undefined || wasPx === undefined) {
        throw new Error(`the ${projection} view was not measured on screen`);
      }
      const t = drawing.pickHitMm;
      expect(nowPx, `${projection} must shrink on screen`).toBeLessThan(wasPx);
      expect(
        nowPx / wasPx,
        `${projection} on-screen ratio (${nowPx} px from ${wasPx} px)`,
      ).toBeGreaterThanOrEqual(Math.hypot(now, t) / (was + t) - 1e-9);
      expect(
        nowPx / wasPx,
        `${projection} on-screen ratio (${nowPx} px from ${wasPx} px)`,
      ).toBeLessThanOrEqual((now + t) / Math.hypot(was, t) + 1e-9);
    }
  });

  test("the picked scale survives a reload — the write, not a local redraw", async ({
    page,
  }) => {
    // The case above proves the gesture reaches the server. This one proves
    // what it left behind: nothing below reads a value the client held in
    // memory.
    const account = await seedSession(page);
    const part = await createBlockViaApi(page, account.token, "Reload block");
    const drawingId = await seedLaidOutDrawing(
      page,
      part.id,
      "Reload block drawing",
    );
    const tree = await readTree(page, account.token, drawingId);
    const drafted = draftedScale(tree.scales);
    const target = (await nextSmallerScale(page, drafted.label)).value;

    await page.getByTestId("drawing-scale-select").selectOption(target);
    await expect(page.getByTestId("title-block-scale")).toHaveText(target, {
      timeout: 30_000,
    });

    await page.reload();
    await expect(page.getByTestId("drawing-sheet")).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByTestId("drawing-scale-select")).toHaveValue(target);
    await expect(page.getByTestId("title-block-scale")).toHaveText(target);
  });

  test("a KEYBOARD user can re-scale, and still has the cell afterwards", async ({
    page,
  }) => {
    // Two things this case exists for, and neither can be read off the cell's
    // displayed value.
    //
    // (1) THE DISCRIMINATOR IS THE REQUEST, NOT THE READOUT. The picker is a
    // controlled select whose value derives from the server, so reading it one
    // tick after a keystroke returns the OLD scale whether the gesture landed
    // or was ignored — identical output for "it worked" and "it did nothing".
    // A vanilla <select> on the same page moves on the same keystroke, so the
    // obvious negative control points the WRONG WAY and invites filing a defect
    // that is not there (independent QA nearly did). The PATCH is the fact.
    //
    // (2) FOCUS SURVIVES THE WRITE. The first version of this fix disabled the
    // cell natively while the write was in flight, which drops it from the tab
    // order: focus went to <body> at the instant of the pick and one Tab landed
    // somewhere else entirely, so a keyboard user was thrown out of the band
    // mid-task. That is not latency-dependent and does not shrink on a fast
    // connection, which is why it is asserted here rather than eyeballed.
    const account = await seedSession(page);
    const part = await createBlockViaApi(page, account.token, "Keyboard block");
    // The id is not needed: this case asserts on the REQUEST the browser makes
    // and on the composed sheet, never on a tree read of its own.
    await seedLaidOutDrawing(page, part.id, "Keyboard block drawing");

    const picker = page.getByTestId("drawing-scale-select");
    await picker.focus();
    await expect(picker).toBeFocused();

    // Where ArrowDown actually goes, read from the DOM rather than assumed:
    // the next option in document order, which is the ladder's own order.
    const step = await picker.evaluate((el) => {
      const select = el as HTMLSelectElement;
      const next = select.options[select.selectedIndex + 1];
      return next === undefined
        ? null
        : { from: select.value, to: next.value, disabled: next.disabled };
    });
    if (step === null || step.disabled) {
      throw new Error(
        "the fixture left the picker with no next option to arrow onto",
      );
    }
    const [numerator, denominator] = step.to.split(":").map(Number);

    const patch = page.waitForRequest(
      (request) =>
        request.method() === "PATCH" &&
        /\/sheets\/[0-9a-f-]+$/.test(request.url()),
    );
    await page.keyboard.press("ArrowDown");

    // THE FACT: the gesture reached the server, carrying the scale the keyboard
    // moved onto.
    const request = await patch;
    expect(JSON.parse(request.postData() ?? "{}")).toMatchObject({
      scale: { numerator, denominator },
    });

    // ...and the drawing follows, server-composed.
    await expect(page.getByTestId("title-block-scale")).toHaveText(step.to, {
      timeout: 30_000,
    });
    await expect(picker).toHaveValue(step.to);

    // THE REGRESSION: the cell is still where the user left it, after the whole
    // round trip — including the busy window, which marks itself with
    // `aria-disabled` precisely so the control never leaves the tab order.
    await expect(picker).toBeFocused();
    const stillThere = await picker.evaluate(
      (el) => el === document.activeElement,
    );
    expect(stillThere, "the picker must keep focus across the write").toBe(
      true,
    );
  });

  test("the per-view scale guard still refuses a divergent write", async ({
    page,
  }) => {
    // The new verb must not have widened H2. A sheet-level re-scale is legal
    // because it leaves the sheet one-scale; a single view going its own way is
    // still the thing that would compose a silently wrong drawing.
    const account = await seedSession(page);
    const part = await createBlockViaApi(page, account.token, "Guard block");
    const drawingId = await seedLaidOutDrawing(
      page,
      part.id,
      "Guard block drawing",
    );
    const tree = await readTree(page, account.token, drawingId);
    const drafted = draftedScale(tree.scales);
    // Divergent BY CONSTRUCTION, whatever the fit chose: doubling the
    // denominator is guaranteed to differ from the sheet's own scale, where a
    // literal 1:4 could silently coincide with it and assert nothing.
    const divergentDen = drafted.denominator * 2;

    const divergent = await page.request.patch(
      `/api/v1/drawings/${drawingId}/views/${tree.viewIds[0]}`,
      {
        data: {
          expected_version: tree.docVersion,
          scale: { numerator: 1, denominator: divergentDen },
        },
        headers: { Authorization: `Bearer ${account.token}` },
      },
    );
    expect(divergent.status()).toBe(422);
    const body = (await divergent.json()) as { error: { code: string } };
    expect(body.error.code).toBe("sheet_view_scale_mismatch");

    // Refused means unchanged, not partially applied.
    const after = await readTree(page, account.token, drawingId);
    expect(new Set(after.scales)).toEqual(new Set([drafted.label]));
  });

  test("re-scaling a sheet with no views is refused, not silently accepted", async ({
    page,
  }) => {
    // A sheet's scale IS its views' scale, so there is nothing to change here.
    // Answering 200 would be the success-shaped failure: a control that reports
    // it did the thing and did nothing.
    const account = await seedSession(page);
    const auth = { Authorization: `Bearer ${account.token}` };
    const created = await page.request.post("/api/v1/drawings", {
      data: { name: "Empty sheet drawing" },
      headers: auth,
    });
    expect(created.status()).toBe(201);
    const drawingId = ((await created.json()) as { id: string }).id;

    const sheet = await page.request.post(
      `/api/v1/drawings/${drawingId}/sheets`,
      { data: { expected_version: 0, name: "Sheet 1" }, headers: auth },
    );
    expect(sheet.status()).toBe(201);
    const sheetId = ((await sheet.json()) as { sheet: { id: string } }).sheet
      .id;

    const response = await page.request.patch(
      `/api/v1/drawings/${drawingId}/sheets/${sheetId}`,
      {
        data: {
          expected_version: 1,
          scale: { numerator: 1, denominator: 2 },
        },
        headers: auth,
      },
    );
    expect(response.status()).toBe(422);
    const body = (await response.json()) as {
      error: { code: string; message: string };
    };
    expect(body.error.code).toBe("sheet_rescale_without_views");
    // The refusal names where the scale actually lives, so the message is
    // actionable rather than merely correct.
    expect(body.error.message).toMatch(/scale of its views/i);
  });
});
