import { expect, test, type Locator, type Page } from "./fixtures";

import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * PICK-SHORT — a short edge on a drawing sheet must be dimensionable.
 *
 * A vertex handle's grab is painted on top of the edge band it sits on, so
 * whatever it claims it claims OUT OF the edge. It used to claim a flat
 * +/-`pickHitMm` (2.6 mm) regardless of how long that edge was, which took
 * 5.2 sheet-mm off every straight line: a 4 mm rib edge had no reachable
 * interior AT ALL, and the failure was not an inert click but the WRONG TOOL —
 * aiming at the edge to dimension it armed the point-to-point vertex pick, and
 * the sheet then sat waiting for a second vertex with nothing on screen to say
 * why. Measured on this exact rib before the fix:
 *
 *     top / line len =  15.6 px   reachable =  0/41   centre -> pick-vertex
 *     top / line len = 156.2 px   reachable = 35/41   centre -> pick-edge
 *
 * It is not a small-parts curiosity: the budget is in SHEET mm, so the same
 * 5.2 mm is 26 mm of model at 1:5 — thin ribs, wall thicknesses and small
 * bosses on any scaled sheet.
 *
 * Every measurement here is taken with the USER'S OWN MECHANISM —
 * `elementFromPoint` for what a pointer would land on, and a literal
 * `page.mouse.click` for what happens when they press. `toBeVisible()` is a
 * box property and cannot see any of this, and `click({ force: true })` skips
 * the one check that asks whether a pointer could have reached the target
 * (CLAUDE.md). Neither appears in this file.
 */

/** A 40 x 4 x 10 rib: the top view is a 40 mm edge and a 4 mm edge. */
async function createRibViaApi(
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

  const corners = [
    { x: 0, y: 0 },
    { x: 40, y: 0 },
    { x: 40, y: 4 },
    { x: 0, y: 4 },
  ];
  const sketch = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: {
      name: "Rib profile",
      feature: {
        type: "sketch",
        version: 1,
        params: {
          plane: { kind: "datum_plane", plane: "XY" },
          entities: corners.map((start, i) => ({
            id: `e${i + 1}`,
            kind: "line",
            start,
            end: corners[(i + 1) % corners.length]!,
          })),
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
      name: "Rib",
      feature: {
        type: "extrude",
        version: 1,
        params: {
          profile: { kind: "feature", feature_id: sketchBody.feature.id },
          distance_mm: 10,
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

/** Lay the standard views out for a fresh rib drawing. */
async function layOutRibDrawing(page: Page, token: string): Promise<void> {
  const part = await createRibViaApi(page, token, "Rib 40x4x10");
  await page.goto("/drawings");
  await expect(page.getByTestId("nav-drawings")).toBeVisible();
  await page.getByTestId("create-drawing-name").fill("Rib — short edge");
  await page.getByTestId("create-drawing-submit").click();
  const row = page.getByTestId("drawing-row").first();
  await expect(row).toBeVisible();
  await row.getByTestId("drawing-open").click();
  await expect(page.getByTestId("drawing-setup-hint")).toBeVisible();
  await page.getByTestId("drawing-part-select").selectOption(part.id);
  await page.getByTestId("drawing-autolayout").click();
  await expect(page.getByTestId("drawing-sheet")).toBeVisible({
    timeout: 30_000,
  });
}

interface EdgePick {
  locator: Locator;
  /** The pick band's length in px — its long bbox axis. */
  lengthPx: number;
}

/**
 * The shortest and longest straight pick targets in a view, by band length.
 * On the rib's top view these are the 4 mm and the 40 mm edge.
 */
async function shortAndLongEdges(
  page: Page,
  view: string,
): Promise<{ short: EdgePick; long: EdgePick }> {
  const edges = page.locator(
    `[data-testid="drawing-pick-edge"][data-view="${view}"][data-primitive="line"]`,
  );
  const count = await edges.count();
  let short: EdgePick | null = null;
  let long: EdgePick | null = null;
  for (let i = 0; i < count; i += 1) {
    const box = await edges.nth(i).boundingBox();
    if (!box) continue;
    const lengthPx = Math.max(box.width, box.height);
    const pick = { locator: edges.nth(i), lengthPx };
    if (short === null || lengthPx < short.lengthPx) short = pick;
    if (long === null || lengthPx > long.lengthPx) long = pick;
  }
  if (!short || !long) throw new Error(`no straight pick targets in ${view}`);
  return { short, long };
}

interface Reach {
  /** How many of the sampled points along the edge land on THIS edge target. */
  reachable: number;
  samples: number;
  /** What a pointer aimed at the edge's midpoint actually lands on. */
  centre: string;
  /** Compact evidence line, carried into the assertion messages. */
  summary: string;
}

/**
 * Walk the centre line of an edge's pick band and ask the BROWSER what a click
 * at each point would hit — the same question Playwright's actionability check
 * asks, and the one `force: true` skips.
 */
async function reachAlongEdge(
  page: Page,
  pick: EdgePick,
  label: string,
  samples = 41,
): Promise<Reach> {
  const box = await pick.locator.boundingBox();
  if (!box) throw new Error(`${label}: pick target has no box`);
  const vertical = box.height > box.width;
  const handle = await pick.locator.elementHandle();
  const probe = await page.evaluate(
    ({ rect, vertical: down, samples: n }) => {
      const name = (el: Element | null): string => {
        if (el === null) return "nothing";
        const tagged = el.closest("[data-testid]");
        return tagged === null
          ? `INK:${el.tagName}`
          : (tagged.getAttribute("data-testid") ?? "?");
      };
      const at = (i: number): { x: number; y: number } => {
        const t = (i + 0.5) / n;
        return down
          ? { x: rect.x + rect.width / 2, y: rect.y + rect.height * t }
          : { x: rect.x + rect.width * t, y: rect.y + rect.height / 2 };
      };
      const hits: string[] = [];
      for (let i = 0; i < n; i += 1) {
        const p = at(i);
        hits.push(name(document.elementFromPoint(p.x, p.y)));
      }
      const centre = document.elementFromPoint(
        rect.x + rect.width / 2,
        rect.y + rect.height / 2,
      );
      return { hits, centre: name(centre) };
    },
    { rect: box, vertical, samples },
  );
  await handle?.dispose();

  const reachable = probe.hits.filter((h) => h === "drawing-pick-edge").length;
  const tally = new Map<string, number>();
  for (const h of probe.hits) tally.set(h, (tally.get(h) ?? 0) + 1);
  const breakdown = [...tally.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([k, n]) => `${k}=${n}`)
    .join(" ");
  return {
    reachable,
    samples,
    centre: probe.centre,
    summary: `${label}: len=${pick.lengthPx.toFixed(1)}px reachable=${reachable}/${samples} centre->${probe.centre} [${breakdown}]`,
  };
}

/** The viewport-pixel centre of an edge's pick band. */
async function centreOf(pick: EdgePick, label: string) {
  const box = await pick.locator.boundingBox();
  if (!box) throw new Error(`${label}: pick target has no box`);
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

test("a 4 mm edge can be dimensioned — the vertex owns the ends, not the middle", async ({
  page,
}) => {
  const account = await seedSession(page);
  await layOutRibDrawing(page, account.token);

  const { short, long } = await shortAndLongEdges(page, "top");
  // NON-VACUITY: the two edges of a 40 x 4 rib really are an order of
  // magnitude apart, so this case is about a SHORT edge and not two similar
  // ones that happen to differ.
  expect(long.lengthPx / short.lengthPx).toBeGreaterThan(5);

  const shortReach = await reachAlongEdge(page, short, "short");
  const longReach = await reachAlongEdge(page, long, "long");

  // THE USER'S OWN MECHANISM, and it happens FIRST so that a run against the
  // old behaviour still leaves the founder shot showing what the user got:
  // a real press at the 4 mm edge's midpoint used to arm the point-to-point
  // pick instead of opening the author menu — the wrong tool, unexplained.
  const centre = await centreOf(short, "short");
  await page.mouse.click(centre.x, centre.y);
  await page.screenshot({
    // The AFTER half of the founder pair. `-before.png` beside it was taken by
    // this same spec against the pre-fix component and shows the sheet waiting
    // for a second vertex; it does not regenerate, which is what "before" means.
    path: `${SCREENSHOT_DIR}/drawings-short-edge-pick-after.png`,
  });

  // The long edge was never the problem and must not become one: two 2.6 mm
  // ends off a 40 mm line still leave most of it.
  expect(longReach.reachable, longReach.summary).toBeGreaterThan(
    longReach.samples / 2,
  );
  expect(longReach.centre, longReach.summary).toBe("drawing-pick-edge");

  // The short edge: 0/41 before the budget, because +/-2.6 mm at each end is
  // more than the whole 4 mm line. A third of it is reachable now, and the
  // midpoint — where a user aims — is the edge, not the vertex.
  expect(shortReach.reachable, shortReach.summary).toBeGreaterThan(0);
  expect(shortReach.centre, shortReach.summary).toBe("drawing-pick-edge");

  // What the press produced: the dimension author menu, and NOT the silently
  // armed point-to-point hint.
  await expect(page.getByTestId("dimension-author-menu")).toBeVisible();
  await expect(page.getByTestId("dimension-pick-hint")).toHaveCount(0);

  // It is the SHORT edge that got picked, not a neighbour: the author menu
  // offers a linear dimension and the selected target is the one measured.
  await expect(
    page.locator('[data-testid="drawing-pick-edge"][data-selected="true"]'),
  ).toHaveCount(1);
  await expect(page.getByTestId("dimension-type-linear")).toBeVisible();
});

test("the long edge and the vertex pick both survive the budget", async ({
  page,
}) => {
  const account = await seedSession(page);
  await layOutRibDrawing(page, account.token);

  // --- The long edge, by hand. ---------------------------------------------
  const { long } = await shortAndLongEdges(page, "top");
  const longCentre = await centreOf(long, "long");
  await page.mouse.click(longCentre.x, longCentre.y);
  await expect(page.getByTestId("dimension-author-menu")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("dimension-author-menu")).toHaveCount(0);

  // --- The vertex, by hand. ------------------------------------------------
  // Fixing one pick by breaking the other would be no fix at all, so the
  // corner handle is exercised the same way: aim a real pointer at its centre,
  // check the browser agrees that is where it lands, and click.
  const vertices = page.locator(
    '[data-testid="drawing-pick-vertex"][data-view="top"]',
  );
  await expect(vertices.first()).toBeAttached();

  // The budget itself, read off the real DOM rather than inferred from the
  // pure function's unit test. Every TOP-view corner of a 40 x 4 rib
  // terminates the 4 mm edge, so each grab is that edge's third (1.333 mm);
  // every FRONT-view corner terminates a 10 mm edge instead, where the budget
  // never binds and the full 2.600 mm pick radius stands.
  const grabs = async (view: string) =>
    page
      .locator(
        `[data-testid="drawing-pick-vertex"][data-view="${view}"] rect[data-grab-mm]`,
      )
      .evaluateAll((els) =>
        els.map((el) => el.getAttribute("data-grab-mm") ?? "?"),
      );
  const topGrabs = await grabs("top");
  expect(topGrabs.length).toBeGreaterThan(0);
  expect(new Set(topGrabs)).toEqual(new Set(["1.333"]));
  expect(new Set(await grabs("front"))).toEqual(new Set(["2.600"]));

  const reachable: number[] = [];
  const count = await vertices.count();
  for (let i = 0; i < count; i += 1) {
    const handle = await vertices.nth(i).elementHandle();
    const hit = await page.evaluate((el) => {
      const target = el as Element;
      const r = target.getBoundingClientRect();
      const found = document.elementFromPoint(
        r.x + r.width / 2,
        r.y + r.height / 2,
      );
      return {
        area: r.width * r.height,
        mine: found !== null && target.contains(found),
      };
    }, handle);
    await handle?.dispose();
    // Every handle has real area — a grab budgeted down to a third of a short
    // edge is still a box, never the zero-area target an SVG stroke gives you.
    expect(hit.area, `vertex ${i} has no area`).toBeGreaterThan(0);
    if (hit.mine) reachable.push(i);
  }
  expect(
    reachable.length,
    `no vertex handle is reachable at its own centre (${count} handles)`,
  ).toBeGreaterThan(1);

  // Two distinct reachable corners → the point-to-point dimension, authored
  // entirely with real mouse clicks.
  const first = reachable[0]!;
  const second = reachable[reachable.length - 1]!;
  for (const [order, index] of [first, second].entries()) {
    const box = await vertices.nth(index).boundingBox();
    if (!box) throw new Error(`vertex ${index} has no box`);
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    if (order === 0) {
      // ONE vertex is a half-made pick, and it says so on the sheet.
      await expect(page.getByTestId("dimension-pick-hint")).toBeVisible();
    }
  }
  await expect(page.getByTestId("dimension-author-menu")).toBeVisible();
  await expect(page.getByTestId("dimension-type-point_to_point")).toBeVisible();
});
