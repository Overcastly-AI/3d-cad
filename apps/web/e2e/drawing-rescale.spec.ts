import { expect, test, type Page } from "./fixtures";

import { seedSession } from "./support";

/**
 * SHEET-RESCALE-1 — a laid-out sheet can be re-scaled.
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

/** The longest drawn EDGE in each standard view, in page pixels.
 *
 * Deliberately not the `drawing-view` group's own box: that includes the view
 * LABEL and the placement frame, which are chrome and do not scale with the
 * model — measured, the group shrinks by only 0.69 across a 2x re-scale, which
 * would make the assertion a weak "it got somewhat smaller". An edge is pure
 * projected geometry, so its length is `model_mm * numerator / denominator` and
 * halving the scale halves it exactly. The composer produces these, so the
 * numbers are the server's, not the browser's arithmetic.
 */
async function longestEdges(page: Page): Promise<Record<string, number>> {
  const sizes: Record<string, number> = {};
  for (const projection of ["front", "top", "right", "iso"]) {
    const edges = page.locator(
      `[data-testid="drawing-pick-edge"][data-view="${projection}"]`,
    );
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
    const targetDen = drafted.denominator * 2;
    const target = `1:${targetDen}`;
    await expect(page.getByTestId("drawing-scale-readout")).toHaveText(
      drafted.label,
    );
    await expect(page.getByTestId("title-block-scale")).toHaveText(
      drafted.label,
    );
    const before = await longestEdges(page);

    // THE VERB. One write against the SHEET, not four against its views.
    const rescale = await page.request.patch(
      `/api/v1/drawings/${drawingId}/sheets/${tree.sheetId}`,
      {
        data: {
          expected_version: tree.docVersion,
          scale: { numerator: 1, denominator: targetDen },
        },
        headers: { Authorization: `Bearer ${account.token}` },
      },
    );
    expect(rescale.status(), await rescale.text()).toBe(200);

    // Every stored view moved together — the state H2 requires, reached in one
    // hop from a state no per-view sequence could have left.
    const after = await readTree(page, account.token, drawingId);
    expect(new Set(after.scales)).toEqual(new Set([target]));
    expect(after.viewIds.sort()).toEqual(tree.viewIds.sort());

    // ...and the drafter sees it: the sheet re-composes at the new scale.
    await page.reload();
    await expect(page.getByTestId("drawing-sheet")).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByTestId("drawing-scale-readout")).toHaveText(target);
    // The title block is composed SERVER-side from `views[0].scale`, so this is
    // the assertion that the print and the screen now say the same thing —
    // the failure mode this ticket exists to close is a sheet re-scaled on
    // screen and stamped at its old scale.
    await expect(page.getByTestId("title-block-scale")).toHaveText(target);
    await expect(page.getByTestId("drawing-sheet")).toHaveAccessibleName(
      new RegExp(`at ${target}`),
    );

    // The GEOMETRY, not just the label: each view is drawn half size. The
    // bounds are tight on purpose: these are projected EDGES, so a 2x re-scale
    // must halve them exactly (measured 0.50 across all four). A band wide
    // enough to admit "somewhat smaller" would also admit a partial re-scale,
    // which is the failure this whole verb exists to make impossible.
    const shrunk = await longestEdges(page);
    for (const projection of ["front", "top", "right", "iso"]) {
      const now = shrunk[projection];
      const was = before[projection];
      if (now === undefined || was === undefined) {
        throw new Error(`the ${projection} view was not measured`);
      }
      expect(
        now,
        `${projection} must be drawn smaller at ${target}`,
      ).toBeLessThan(was);
      const ratio = now / was;
      expect(ratio, `${projection} ratio ${ratio}`).toBeGreaterThan(0.46);
      expect(ratio, `${projection} ratio ${ratio}`).toBeLessThan(0.56);
    }
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
