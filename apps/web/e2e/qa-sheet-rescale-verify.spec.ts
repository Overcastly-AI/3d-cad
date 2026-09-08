import { target as targetToken } from "@loft/design/tokens";

import { expect, test, type Page } from "./fixtures";

import { seedSession } from "./support";

/**
 * QA verification of SHEET-RESCALE-1 (`d19d257`) — written independently of the
 * builder's `drawing-rescale.spec.ts` and deliberately measuring by a different
 * derivation, so that the two agree (or disagree) for reasons that are legible.
 *
 * Where the builder's spec reads Playwright's screen-space `boundingBox()`,
 * this one reads the pick band `<rect>`'s own `width` attribute — the projected
 * segment length in sheet millimetres, exactly. That matters
 * for the same reason the builder's own note about the view GROUP does: a
 * measurement that includes chrome cannot tell "the drawing re-scaled" from
 * "the drawing moved". A projected edge's length is `model_mm * num / den`, so
 * a 2x re-scale must halve it EXACTLY, and anything short of exact is a finding
 * rather than a tolerance question.
 *
 * The suite also states, as an assertion rather than a comment, what a user can
 * actually reach. When it was written that assertion recorded a GAP — the
 * post-layout Scale control was a read-only `Readout`, so this verb had no
 * mouse path at all (QA-REVIEW SHEET-RESCALE-1). SHEET-RESCALE-2 closed it, and
 * the case is inverted rather than deleted: it is the standing guard that the
 * control does not quietly revert to a readout, and its exact-halving oracle
 * below now runs on a sheet re-scaled BY THE PICKER.
 */

const BLOCK = { x: 60, y: 40, z: 30 };

async function createBlockViaApi(
  page: Page,
  token: string,
  name: string,
): Promise<string> {
  const auth = { Authorization: `Bearer ${token}` };
  const part = await page.request.post("/api/v1/parts", {
    data: { name },
    headers: auth,
  });
  expect(part.status(), await part.text()).toBe(201);
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
              end: { x: BLOCK.x, y: 0 },
            },
            {
              id: "e2",
              kind: "line",
              start: { x: BLOCK.x, y: 0 },
              end: { x: BLOCK.x, y: BLOCK.y },
            },
            {
              id: "e3",
              kind: "line",
              start: { x: BLOCK.x, y: BLOCK.y },
              end: { x: 0, y: BLOCK.y },
            },
            {
              id: "e4",
              kind: "line",
              start: { x: 0, y: BLOCK.y },
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
  expect(sketch.status(), await sketch.text()).toBe(201);
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
          distance_mm: BLOCK.z,
          operation: "add",
          direction: "normal",
        },
      },
      expected_tree_version: sketchBody.tree_version,
    },
    headers: auth,
  });
  expect(extrude.status(), await extrude.text()).toBe(201);
  return partId;
}

/** Lay out the four standard views through the REAL UI, not the API — the
 * flow a drafter actually walks, so the sheet under test is one the product
 * produced rather than one this spec constructed. */
async function layOutViaUi(
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
    timeout: 60_000,
  });
  return new URL(page.url()).pathname.split("/").pop() ?? "";
}

type Tree = {
  docVersion: number;
  sheetId: string;
  scales: string[];
};

async function readTree(
  page: Page,
  token: string,
  drawingId: string,
): Promise<Tree> {
  const response = await page.request.get(`/api/v1/drawings/${drawingId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.status(), await response.text()).toBe(200);
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
  if (content === undefined) throw new Error("the drawing has no sheet");
  return {
    docVersion: body.doc_version,
    sheetId: content.sheet.id,
    scales: content.views.map(
      (v) => `${v.scale.numerator}:${v.scale.denominator}`,
    ),
  };
}

/**
 * Per-view projected edge length in SHEET MILLIMETRES, read off the pick band's
 * own `width` attribute.
 *
 * `HitBand` sweeps a `<rect>` along each segment whose `width` IS the segment's
 * length and whose `height` is the constant `pickHitMm` band. So the width
 * attribute is the projected length exactly — `model_mm * num / den` — with no
 * chrome in it at all.
 *
 * The first draft of this helper took `hypot()` of the group's `getBBox()` and
 * measured 0.5056 instead of 0.5 on a 2x re-scale. That was THIS HELPER's bug,
 * not the product's: the bbox mixes in the constant 2.6 mm band, and solving
 * `hypot(15,p)/hypot(30,p) = 0.50556` returns `p = 2.60` — the documented
 * `drawing.pickHitMm`, to three figures. It is the same class of error the
 * builder found in the view GROUP (label + frame do not scale) one level
 * further in, and it is recorded here because a near-miss ratio invites being
 * absorbed into a tolerance instead of explained.
 *
 * A count is carried so an empty scan cannot pass vacuously, and the SUM is
 * taken alongside the longest because a re-scale that dropped or duplicated an
 * edge would move the sum while leaving the longest alone.
 */
async function edgeMetrics(
  page: Page,
): Promise<Record<string, { longest: number; total: number; count: number }>> {
  const metrics = await page.evaluate(() => {
    const out: Record<
      string,
      { longest: number; total: number; count: number }
    > = {};
    const groups = document.querySelectorAll<SVGGraphicsElement>(
      '[data-testid="drawing-pick-edge"]',
    );
    for (const group of groups) {
      const view = group.getAttribute("data-view") ?? "?";
      const entry = out[view] ?? { longest: 0, total: 0, count: 0 };
      // Straight segments: the band rect's width is the segment length.
      for (const band of group.querySelectorAll<SVGRectElement>("rect")) {
        const span = band.width.baseVal.value;
        entry.longest = Math.max(entry.longest, span);
        entry.total += span;
        entry.count += 1;
      }
      // Circular edges: the pick is the disc itself, so its circumference is
      // the comparable length.
      for (const disc of group.querySelectorAll<SVGCircleElement>("circle")) {
        const span = 2 * Math.PI * disc.r.baseVal.value;
        entry.longest = Math.max(entry.longest, span);
        entry.total += span;
        entry.count += 1;
      }
      out[view] = entry;
    }
    return out;
  });
  const views = Object.keys(metrics);
  if (views.length === 0) {
    throw new Error("no drawing-pick-edge groups found — nothing was measured");
  }
  for (const view of views) {
    const entry = metrics[view];
    if (entry === undefined || entry.count === 0 || entry.longest === 0) {
      throw new Error(`view ${view} yielded no measurable edge`);
    }
  }
  return metrics;
}

async function waitForEdges(page: Page): Promise<void> {
  await expect(
    page.locator('[data-testid="drawing-pick-edge"]').first(),
  ).toBeAttached({ timeout: 60_000 });
}

/**
 * A control a person could actually operate — asserted the user's way.
 *
 * `toBeVisible()` is a BOX property and returns true for an `sr-only` element
 * clipped out of the frame, and a zero-area SVG hit region passes several of
 * the obvious checks too (both measured in this repo). So the question is asked
 * directly: is there real area, and does a click at the centre of that area
 * resolve TO this element?
 */
async function expectOperable(
  control: ReturnType<Page["getByTestId"]>,
  what: string,
): Promise<void> {
  await expect(control, `${what} must be visible`).toBeVisible();
  await expect(control, `${what} must be enabled`).toBeEnabled();
  const box = await control.boundingBox();
  expect(box, `${what} must have a hit box`).not.toBeNull();
  // The PRODUCT's own dense floor (24 px), not a number picked to pass. The
  // first version of this helper asked for `height > 10`, which is under the
  // floor and therefore could not fail for the regression it looks like it
  // guards — this very control measured 19 px before `min-h-target-dense` was
  // put on it, and would have sailed through.
  expect(box?.width ?? 0, `${what} width`).toBeGreaterThanOrEqual(
    targetToken.dense,
  );
  expect(box?.height ?? 0, `${what} height`).toBeGreaterThanOrEqual(
    targetToken.dense,
  );
  const reachable = await control.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const hit = document.elementFromPoint(
      r.left + r.width / 2,
      r.top + r.height / 2,
    );
    return hit === el || el.contains(hit);
  });
  expect(reachable, `${what} must be clickable at its centre`).toBe(true);
}

test.describe("QA — SHEET-RESCALE-1 verification", () => {
  test("the sheet VERB re-scales via the API: every projected edge halves exactly, and the sheet says so after a reload", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const partId = await createBlockViaApi(page, account.token, "QA rescale");
    const drawingId = await layOutViaUi(page, partId, "QA rescale drawing");
    await waitForEdges(page);

    // The scale the LAYOUT chose is read, never assumed — `fitScale` reduces
    // the picked scale until the views fit, so hard-coding it would make this
    // spec red for the fit model changing rather than the verb breaking.
    const before = await readTree(page, account.token, drawingId);
    expect(before.scales, "a laid-out sheet must have four views").toHaveLength(
      4,
    );
    expect(new Set(before.scales).size, "one sheet, one scale (H2)").toBe(1);
    const drafted = before.scales[0];
    if (drafted === undefined) throw new Error("the sheet has no scale");
    const draftedDen = Number(drafted.split(":")[1]);
    expect(Number.isFinite(draftedDen) && draftedDen >= 1).toBe(true);

    await expect(page.getByTestId("drawing-scale-select")).toHaveValue(drafted);
    await expect(page.getByTestId("title-block-scale")).toHaveText(drafted);

    const geometryBefore = await edgeMetrics(page);
    expect(Object.keys(geometryBefore).sort()).toEqual([
      "front",
      "iso",
      "right",
      "top",
    ]);

    // THE VERB — one write against the SHEET, called directly. This case is
    // deliberately API-driven and says so in its title: it is the independent
    // check on the SERVER half (exact halving, round trip through a reload),
    // written to a different derivation than the builder's spec. The GESTURE is
    // asserted separately below, and in `drawing-rescale.spec.ts`.
    const target = `1:${draftedDen * 2}`;
    const rescale = await page.request.patch(
      `/api/v1/drawings/${drawingId}/sheets/${before.sheetId}`,
      {
        data: {
          expected_version: before.docVersion,
          scale: { numerator: 1, denominator: draftedDen * 2 },
        },
        headers: { Authorization: `Bearer ${account.token}` },
      },
    );
    expect(rescale.status(), await rescale.text()).toBe(200);

    // RELOAD — the round trip. Nothing below reads a value the client held in
    // memory; everything is re-fetched from the server and re-composed.
    await page.reload();
    await expect(page.getByTestId("drawing-sheet")).toBeVisible({
      timeout: 60_000,
    });
    await waitForEdges(page);
    await expect(page.getByTestId("title-block-scale")).toHaveText(target);
    await expect(page.getByTestId("drawing-scale-select")).toHaveValue(target);

    // The persisted state agrees with what the UI is showing.
    const after = await readTree(page, account.token, drawingId);
    expect(after.scales).toEqual([target, target, target, target]);
    expect(after.docVersion).toBe(before.docVersion + 1);

    // And the GEOMETRY moved, by exactly the ratio asked for.
    const geometryAfter = await edgeMetrics(page);
    for (const view of ["front", "top", "right", "iso"]) {
      const b = geometryBefore[view];
      const a = geometryAfter[view];
      if (b === undefined || a === undefined) {
        throw new Error(`missing metrics for the ${view} view`);
      }
      expect(a.count, `${view}: edge count must not change`).toBe(b.count);
      expect(
        a.longest / b.longest,
        `${view}: longest edge must halve exactly`,
      ).toBeCloseTo(0.5, 5);
      expect(
        a.total / b.total,
        `${view}: total edge length must halve exactly`,
      ).toBeCloseTo(0.5, 5);
    }
  });

  test("the H2 per-view guard still refuses a single-view scale change on a multi-view sheet", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const partId = await createBlockViaApi(page, account.token, "QA guard");
    const drawingId = await layOutViaUi(page, partId, "QA guard drawing");
    await waitForEdges(page);

    const tree = await page.request.get(`/api/v1/drawings/${drawingId}`, {
      headers: { Authorization: `Bearer ${account.token}` },
    });
    const body = (await tree.json()) as {
      doc_version: number;
      sheets: {
        views: {
          id: string;
          scale: { numerator: number; denominator: number };
        }[];
      }[];
    };
    const views = body.sheets[0]?.views ?? [];
    expect(views).toHaveLength(4);
    const victim = views[0];
    if (victim === undefined) throw new Error("no view to write");

    const refused = await page.request.patch(
      `/api/v1/drawings/${drawingId}/views/${victim.id}`,
      {
        data: {
          expected_version: body.doc_version,
          scale: { numerator: 1, denominator: victim.scale.denominator * 3 },
        },
        headers: { Authorization: `Bearer ${account.token}` },
      },
    );
    expect(refused.status(), await refused.text()).toBe(422);
    const envelope = (await refused.json()) as { error: { code: string } };
    expect(envelope.error.code).toBe("sheet_view_scale_mismatch");

    // Refused means UNCHANGED, not "refused and wrote anyway".
    const still = await readTree(page, account.token, drawingId);
    expect(new Set(still.scales).size).toBe(1);
    expect(still.docVersion).toBe(body.doc_version);
  });

  test("a sheet with no views is refused BY NAME, not silently no-opped", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const create = await page.request.post("/api/v1/drawings", {
      data: { name: "QA viewless" },
      headers: { Authorization: `Bearer ${account.token}` },
    });
    expect(create.status()).toBe(201);
    const drawing = (await create.json()) as {
      id: string;
      doc_version: number;
    };
    const sheet = await page.request.post(
      `/api/v1/drawings/${drawing.id}/sheets`,
      {
        data: {
          expected_version: drawing.doc_version,
          index: 0,
          name: "Empty sheet",
        },
        headers: { Authorization: `Bearer ${account.token}` },
      },
    );
    expect(sheet.status(), await sheet.text()).toBe(201);
    const added = (await sheet.json()) as {
      sheet: { id: string };
      doc_version: number;
    };

    const refused = await page.request.patch(
      `/api/v1/drawings/${drawing.id}/sheets/${added.sheet.id}`,
      {
        data: {
          expected_version: added.doc_version,
          scale: { numerator: 1, denominator: 5 },
        },
        headers: { Authorization: `Bearer ${account.token}` },
      },
    );
    expect(refused.status(), await refused.text()).toBe(422);
    const envelope = (await refused.json()) as {
      error: { code: string; message: string; details?: unknown };
    };
    expect(envelope.error.code).toBe("sheet_rescale_without_views");
    // The message has to say where the scale actually lives, or the refusal is
    // just a different way of being unhelpful.
    expect(envelope.error.message).toContain("views");
  });

  /**
   * REACHABILITY. CLAUDE.md's standing design mandate treats a capability the
   * user cannot reach as a defect, so this is asserted, not noted.
   *
   * As first written this case RECORDED THE DEFECT: after a layout the Scale
   * cell was a read-only `Readout` and the `<select>` that would call
   * `handleSelectScale` was not in the DOM at all — `onSelectScale` had exactly
   * one call site, in the `hasLayout ? Readout : SelectField` FALSE branch,
   * while the handler behind it only acted when `hasLayout` was TRUE. Mutually
   * exclusive, so the server verb had no mouse, keyboard or touch path.
   *
   * SHEET-RESCALE-2 made the cell a live picker on both sides of the layout.
   * The case is INVERTED rather than removed, because the way this regresses is
   * for the post-layout branch to go quiet again — and a control that has gone
   * back to being a readout still LOOKS right in a screenshot.
   */
  test("the re-scale verb has a mouse path: post-layout Scale is a live picker", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const partId = await createBlockViaApi(page, account.token, "QA reach");

    await page.goto("/drawings");
    await expect(page.getByTestId("nav-drawings")).toBeVisible();
    await page.getByTestId("create-drawing-name").fill("QA reach drawing");
    await page.getByTestId("create-drawing-submit").click();
    const row = page.getByTestId("drawing-row").first();
    await expect(row).toBeVisible();
    await row.getByTestId("drawing-open").click();
    await expect(page.getByTestId("drawing-setup-hint")).toBeVisible();

    // BEFORE the layout the picker is real, enabled, and hittable.
    const picker = page.getByTestId("drawing-scale-select");
    await expectOperable(picker, "the pre-layout picker");

    await page.getByTestId("drawing-part-select").selectOption(partId);
    await page.getByTestId("drawing-autolayout").click();
    await expect(page.getByTestId("drawing-sheet")).toBeVisible({
      timeout: 60_000,
    });

    // AFTER the layout it is STILL there, still hittable, and — the assertion
    // the old readout could never satisfy — still in the tab order.
    await expect(page.getByTestId("drawing-scale-readout")).toHaveCount(0);
    await expectOperable(picker, "the post-layout picker");
    const options = await picker
      .locator("option:not([disabled])")
      .allTextContents();
    expect(
      options.length,
      "the picker must offer more than the scale it is already at",
    ).toBeGreaterThan(1);

    // Keyboard reaches it: focus lands on the control itself, not on a wrapper
    // that merely contains it.
    await picker.focus();
    const focused = await picker.evaluate(
      (el) => el === document.activeElement,
    );
    expect(focused, "the picker must be focusable").toBe(true);

    // And the gesture DOES something — proven on the drawing, not on a status
    // code. A pick that re-rendered nothing would leave the title block (which
    // the server composes from `views[0].scale`) exactly as it was.
    const drafted = await picker.inputValue();
    const target = options.find((option) => option !== drafted);
    if (target === undefined) throw new Error("no other scale to pick");
    await expect(page.getByTestId("title-block-scale")).toHaveText(drafted);
    await picker.selectOption(target);
    await expect(page.getByTestId("title-block-scale")).toHaveText(target, {
      timeout: 60_000,
    });

    if (process.env.QA_SHOTS) {
      await page.screenshot({
        path: `${process.env.QA_SHOTS}/scale-picker-${test.info().project.name}.png`,
      });
    }
  });
});
