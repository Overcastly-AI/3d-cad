import { readFile } from "node:fs/promises";

import { expect, test, type Page } from "./fixtures";

import { pickDispatch, waitForSolved } from "./assemblyFlow";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * ASM-A3-PATTERN — component patterns, end to end.
 *
 * Test 1, a rail stage: two grounded rails with three Ø6 holes each, and three
 * pins. Pin 1 is jointed into rail 1's first hole.
 *  1. ON HOLES (pattern-driven): pin 1 is patterned over rail 1's holes and
 *     rail 2's — six pins, the copies where the joint would put them.
 *  2. LINEAR along a straight edge picked on rail 1, typed "60 mm / 2".
 *  3. CIRCULAR about rail 1's third hole axis, picked in the viewport.
 *  4. The BOM counts every copy; the patterns and copies survive a reload;
 *     the STEP holds every copy; a pattern past the 500 bound is refused.
 *  5. The rail gains a hole: after a reload the hole pattern places eight.
 *  6. Removing a pattern removes its copies, not its seed.
 *
 * Test 2, a bike: a wheel of 32 spokes (a circular pattern in the wheel)
 * inserted twice; the indented BOM reads 32 per wheel, 64 in all.
 */

type Entity =
  | { id: string; kind: "line"; start: XY; end: XY }
  | { id: string; kind: "circle"; center: XY; radius: number };
interface XY {
  x: number;
  y: number;
}

function rectangle(x0: number, y0: number, x1: number, y1: number): Entity[] {
  const p = [
    { x: x0, y: y0 },
    { x: x1, y: y0 },
    { x: x1, y: y1 },
    { x: x0, y: y1 },
  ];
  return p.map((start, i) => ({
    id: `e${i + 1}`,
    kind: "line" as const,
    start,
    end: p[(i + 1) % 4] as XY,
  }));
}

function circles(radius: number, centres: XY[]): Entity[] {
  return centres.map((center, i) => ({
    id: `h${i + 1}`,
    kind: "circle" as const,
    center,
    radius,
  }));
}

function sketchFeature(entities: Entity[]) {
  return {
    type: "sketch",
    version: 1,
    params: {
      plane: { kind: "datum_plane", plane: "XY" },
      entities: entities.map((e) => ({ ...e, construction: false })),
      constraints: [],
    },
  };
}

/** A part from one sketch extruded `depth`, through the real gateway. */
async function partViaApi(
  page: Page,
  token: string,
  name: string,
  entities: Entity[],
  depth: number,
): Promise<string> {
  const headers = { Authorization: `Bearer ${token}` };
  const part = await page.request.post("/api/v1/parts", {
    data: { name },
    headers,
  });
  expect(part.ok(), await part.text()).toBe(true);
  const partId = ((await part.json()) as { id: string }).id;
  const sketch = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: {
      name: "Sketch1",
      feature: sketchFeature(entities),
      expected_tree_version: 0,
    },
    headers,
  });
  expect(sketch.ok(), await sketch.text()).toBe(true);
  const body = (await sketch.json()) as {
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
          profile: { kind: "feature", feature_id: body.feature.id },
          distance_mm: depth,
          operation: "add",
          direction: "normal",
        },
      },
      expected_tree_version: body.tree_version,
    },
    headers,
  });
  expect(extrude.ok(), await extrude.text()).toBe(true);
  return partId;
}

/** An assembly with instances, through the real gateway. */
async function assemblyViaApi(
  page: Page,
  token: string,
  name: string,
  instances: {
    ref: string;
    kind?: "part" | "assembly";
    name: string;
    at: [number, number, number];
    grounded: boolean;
  }[],
): Promise<{ id: string; ids: string[] }> {
  const headers = { Authorization: `Bearer ${token}` };
  const created = await page.request.post("/api/v1/assemblies", {
    data: { name },
    headers,
  });
  expect(created.ok(), await created.text()).toBe(true);
  const id = ((await created.json()) as { id: string }).id;
  let version = 0;
  const ids: string[] = [];
  for (const instance of instances) {
    const [x, y, z] = instance.at;
    const response = await page.request.post(
      `/api/v1/assemblies/${id}/instances`,
      {
        data: {
          expected_version: version,
          ref_document_id: instance.ref,
          ref_document_kind: instance.kind ?? "part",
          name: instance.name,
          grounded: instance.grounded,
          placement: {
            position: { x, y, z },
            orientation: { x: 0, y: 0, z: 0, w: 1 },
          },
        },
        headers,
      },
    );
    expect(response.ok(), await response.text()).toBe(true);
    const body = (await response.json()) as {
      instance: { id: string };
      doc_version: number;
    };
    version = body.doc_version;
    ids.push(body.instance.id);
  }
  return { id, ids };
}

/** Click the offered edge of `instanceId` whose midpoint passes `match`. */
async function pickEdge(
  page: Page,
  instanceId: string,
  curve: "line" | "circle",
  match: (mid: [number, number, number]) => boolean,
): Promise<void> {
  const nodes = page.locator(
    `[data-testid^="mate-axis-${instanceId}-"][data-edge-curve="${curve}"]`,
  );
  await expect(nodes.first()).toBeAttached({ timeout: 20_000 });
  const mids = await nodes.evaluateAll((all) =>
    all.map((node) => ({
      id: node.getAttribute("data-testid") ?? "",
      mid: (node.getAttribute("data-edge-mid") ?? "")
        .split(",")
        .map(Number) as [number, number, number],
    })),
  );
  const hit = mids.find((m) => match(m.mid));
  if (hit === undefined) throw new Error(`no ${curve} edge matched`);
  await pickDispatch(page, `[data-testid="${hit.id}"]`);
}

const near = (a: number, b: number, tol = 1e-3) => Math.abs(a - b) <= tol;

/** Scene poses (x, y-up, z) of the copies a pattern drew for `seedId`. */
async function copyPoses(page: Page, seedId: string): Promise<number[][]> {
  return page
    .locator(`[data-group-id="${seedId}"][data-pattern-copy="true"]`)
    .evaluateAll((nodes) =>
      nodes.map((node) =>
        ["x", "y", "z"].map((k) =>
          Number(node.getAttribute(`data-solved-${k}`)),
        ),
      ),
    );
}

async function openPatternDialog(page: Page, seedId: string): Promise<void> {
  await page.getByTestId("pattern-components").click();
  await expect(page.getByTestId("pattern-dialog")).toBeVisible();
  await page.getByTestId(`pattern-seed-${seedId}`).check();
}

async function commitPattern(page: Page, rows: number): Promise<void> {
  await page.getByTestId("pattern-ok").click();
  await expect(page.getByTestId("pattern-dialog")).toBeHidden({
    timeout: 30_000,
  });
  await expect(page.getByTestId("pattern-row")).toHaveCount(rows, {
    timeout: 30_000,
  });
  await waitForSolved(page);
}

async function patternCounts(page: Page): Promise<Record<string, string>> {
  await waitForSolved(page);
  const rows = await page
    .getByTestId("pattern-row")
    .evaluateAll((all) =>
      all.map((row) => [
        row.getAttribute("data-pattern-type") ?? "",
        row.getAttribute("data-pattern-count") ?? "",
      ]),
    );
  return Object.fromEntries(rows);
}

async function bomTotals(page: Page, view: "top" | "parts") {
  await page.getByTestId("inspector-view-bom").click();
  if (view === "parts") await page.getByTestId("bom-view-parts").click();
  await expect(page.getByTestId("bom-total")).toBeVisible({ timeout: 30_000 });
  const read = {
    rows: await page.getByTestId("bom-row").count(),
    total: (await page.getByTestId("bom-total").innerText()).trim(),
  };
  // Back to the solve view, whose status cell `waitForSolved` reads.
  await page.getByTestId("inspector-view-solve").click();
  return read;
}

const NAUO = /NEXT_ASSEMBLY_USAGE_OCCURRENCE\s*\(/g;
const RAIL_HOLES = [20, 50, 80].map((x) => ({ x, y: 10 }));

test.describe("Assemblies — component patterns", () => {
  test("linear, circular and on-holes patterns: place, bill, reload, follow the part", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const { token } = await seedSession(page);
    const headers = { Authorization: `Bearer ${token}` };
    const rail = await partViaApi(
      page,
      token,
      "Rail",
      [...rectangle(0, 0, 100, 20), ...circles(3, RAIL_HOLES)],
      8,
    );
    const pin = await partViaApi(
      page,
      token,
      "Pin",
      circles(3, [{ x: 0, y: 0 }]),
      12,
    );
    const stage = await assemblyViaApi(page, token, "Rail stage", [
      { ref: rail, name: "Rail <1>", at: [0, 0, 0], grounded: true },
      { ref: rail, name: "Rail <2>", at: [0, 40, 0], grounded: true },
      { ref: pin, name: "Pin <1>", at: [0, 0, 40], grounded: false },
      { ref: pin, name: "Pin <2>", at: [0, -30, 0], grounded: true },
      { ref: pin, name: "Pin <3>", at: [80, 30, 0], grounded: true },
    ]);
    const [rail1, rail2, pin1, pin2, pin3] = stage.ids as [
      string,
      string,
      string,
      string,
      string,
    ];
    await page.goto(`/assemblies/${stage.id}`);
    await waitForSolved(page);

    // Seat pin 1 in rail 1's first hole with a rigid joint.
    await page.keyboard.press("j");
    await pickDispatch(
      page,
      `[data-testid^="joint-origin-${rail1}-circle-"][aria-label$="at 20, 10, 8 millimetres"]`,
    );
    await pickDispatch(
      page,
      `[data-testid^="joint-origin-${pin1}-circle-"][aria-label$="at 0, 0, 0 millimetres"]`,
    );
    await page.getByTestId("joint-motion-rigid").click();
    await page.getByTestId("joint-ok").click();
    await expect(page.getByTestId("mate-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    await waitForSolved(page);
    await page.keyboard.press("Escape");

    // ——— 1. On holes: rail 1's three and rail 2's three ———————————————
    await openPatternDialog(page, pin1);
    await page.getByTestId("pattern-kind-hole").click();
    await page.getByTestId("pattern-pick-hole").click();
    await pickEdge(
      page,
      rail1,
      "circle",
      ([x, y, z]) => near(z, 8) && near(y, 10, 3.5) && near(x, 20, 3.5),
    );
    await expect(page.getByTestId("pattern-hole")).toContainText("Rail <1>");
    await page.getByTestId(`pattern-also-on-${rail2}`).check();
    await commitPattern(page, 1);
    expect(await patternCounts(page)).toEqual({ hole: "6" });
    const holeCopies = await copyPoses(page, pin1);
    // Scene is Y-up: (x, y, z) kernel -> (x, z, -y). Pins stand on z = 8.
    expect(holeCopies).toHaveLength(5);
    const seats = holeCopies
      .map(
        ([x, y, z]) =>
          `${Math.round(x ?? NaN)},${Math.round(y ?? NaN)},${Math.round(-(z ?? NaN))}`,
      )
      .sort();
    expect(seats).toEqual(
      ["20,8,50", "50,8,10", "50,8,50", "80,8,10", "80,8,50"].sort(),
    );

    // ——— 2. Linear along rail 1's front bottom edge, typed ————————————
    await openPatternDialog(page, pin2);
    await page.getByTestId("pattern-axis").selectOption("edge");
    await page.getByTestId("pattern-pick-axis").click();
    await pickEdge(
      page,
      rail1,
      "line",
      ([x, y, z]) => near(x, 50) && near(y, 0) && near(z, 0),
    );
    await page.getByTestId("pattern-count").fill("4");
    await page.getByTestId("pattern-spacing").fill("60 mm / 2");
    await expect(page.getByTestId("pattern-spacing-reading")).toHaveText(
      "= 30 mm",
    );
    await commitPattern(page, 2);
    const rowCopies = await copyPoses(page, pin2);
    expect(rowCopies.map(([x]) => Math.round(x ?? NaN)).sort()).toEqual([
      30, 60, 90,
    ]);

    // ——— 3. Circular about rail 1's third hole, picked ————————————————
    await openPatternDialog(page, pin3);
    await page.getByTestId("pattern-kind-circular").click();
    await page.getByTestId("pattern-axis").selectOption("edge");
    await page.getByTestId("pattern-pick-axis").click();
    await pickEdge(
      page,
      rail1,
      "circle",
      ([x, y, z]) => near(z, 8) && near(x, 80, 3.5) && near(y, 10, 3.5),
    );
    await page.getByTestId("pattern-count").fill("4");
    await page.getByTestId("pattern-angle").fill("360 deg");
    await commitPattern(page, 3);
    const ring = await copyPoses(page, pin3);
    expect(
      ring
        .map(([x, , z]) => `${Math.round(x ?? NaN)},${Math.round(-(z ?? NaN))}`)
        .sort(),
    ).toEqual(["100,10", "60,10", "80,-10"].sort());
    expect(await patternCounts(page)).toEqual({
      hole: "6",
      linear: "4",
      circular: "4",
    });

    // ——— 4. The BOM, a reload, the STEP, the bound ————————————————————
    expect(await bomTotals(page, "top")).toEqual({ rows: 2, total: "16" });
    await page.reload();
    await waitForSolved(page);
    await expect(page.getByTestId("pattern-row")).toHaveCount(3);
    await expect.poll(async () => (await copyPoses(page, pin1)).length).toBe(5);
    expect(await bomTotals(page, "parts")).toEqual({ rows: 2, total: "16" });

    const step = page.getByTestId("assembly-export-band-step");
    await expect(step).toBeEnabled({ timeout: 30_000 });
    const download = page.waitForEvent("download");
    await step.click();
    const text = (await readFile(await (await download).path())).toString(
      "utf-8",
    );
    expect(text.match(NAUO)).toHaveLength(16);

    await openPatternDialog(page, pin2);
    await page.getByTestId("pattern-count").fill("490");
    await page.getByTestId("pattern-ok").click();
    await expect(page.getByTestId("pattern-error")).toContainText("500");
    await page.getByTestId("pattern-cancel").click();
    await expect(page.getByTestId("pattern-row")).toHaveCount(3);

    // ——— 5. The rail gains a fourth hole: the hole pattern follows ————
    const tree = (await (
      await page.request.get(`/api/v1/parts/${rail}/features`, { headers })
    ).json()) as { tree_version: number; features: { id: string }[] };
    const sketchId = tree.features[0]?.id ?? "";
    const edit = await page.request.patch(
      `/api/v1/parts/${rail}/features/${sketchId}`,
      {
        data: {
          expected_tree_version: tree.tree_version,
          feature: sketchFeature([
            ...rectangle(0, 0, 100, 20),
            ...circles(3, [...RAIL_HOLES, { x: 95, y: 10 }]),
          ]),
        },
        headers,
      },
    );
    expect(edit.ok(), await edit.text()).toBe(true);
    await page.reload();
    expect(await patternCounts(page)).toEqual({
      hole: "8",
      linear: "4",
      circular: "4",
    });
    await expect.poll(async () => (await copyPoses(page, pin1)).length).toBe(7);
    expect(await bomTotals(page, "parts")).toEqual({ rows: 2, total: "18" });

    // ——— 6. Removing a pattern removes its copies, not its seed ————————
    const linearRow = page
      .getByTestId("pattern-row")
      .filter({ hasText: "Linear pattern 1" });
    const linearId = (await linearRow.getAttribute("data-pattern-id")) ?? "";
    await page.getByTestId(`pattern-delete-${linearId}`).click();
    await expect(page.getByTestId("pattern-row")).toHaveCount(2, {
      timeout: 30_000,
    });
    await waitForSolved(page);
    await expect.poll(async () => (await copyPoses(page, pin2)).length).toBe(0);
    await expect(page.getByTestId(`assembly-balloon-${pin2}`)).toBeAttached();
  });

  test("a wheel of 32 spokes, twice in a bike: the indented BOM", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const { token } = await seedSession(page);
    const hub = await partViaApi(
      page,
      token,
      "Hub",
      [
        { id: "o", kind: "circle", center: { x: 0, y: 0 }, radius: 15 },
        { id: "i", kind: "circle", center: { x: 0, y: 0 }, radius: 4 },
      ],
      20,
    );
    const spoke = await partViaApi(
      page,
      token,
      "Spoke",
      rectangle(14, -1, 119, 1),
      2,
    );
    const rim = await partViaApi(
      page,
      token,
      "Rim",
      [
        { id: "o", kind: "circle", center: { x: 0, y: 0 }, radius: 128 },
        { id: "i", kind: "circle", center: { x: 0, y: 0 }, radius: 118 },
      ],
      20,
    );
    const frame = await partViaApi(
      page,
      token,
      "Frame tube",
      rectangle(0, -6, 330, 6),
      12,
    );
    const wheel = await assemblyViaApi(page, token, "Wheel", [
      { ref: hub, name: "Hub <1>", at: [0, 0, 0], grounded: true },
      { ref: rim, name: "Rim <1>", at: [0, 0, 0], grounded: true },
      { ref: spoke, name: "Spoke <1>", at: [0, 0, 9], grounded: true },
    ]);
    const spokeSeed = wheel.ids[2] ?? "";

    // The wheel's 32 spokes: a full circular pattern about the Z axis.
    await page.goto(`/assemblies/${wheel.id}`);
    await waitForSolved(page);
    await openPatternDialog(page, spokeSeed);
    await page.getByTestId("pattern-kind-circular").click();
    await page.getByTestId("pattern-axis").selectOption("z");
    await page.getByTestId("pattern-count").fill("32");
    await page.getByTestId("pattern-angle").fill("360 deg");
    await commitPattern(page, 1);
    expect(await patternCounts(page)).toEqual({ circular: "32" });
    await expect
      .poll(async () => (await copyPoses(page, spokeSeed)).length)
      .toBe(31);

    const bike = await assemblyViaApi(page, token, "Bike", [
      { ref: frame, name: "Frame tube <1>", at: [-15, -6, 0], grounded: true },
      {
        ref: wheel.id,
        kind: "assembly",
        name: "Wheel <1>",
        at: [-140, 0, 0],
        grounded: true,
      },
      {
        ref: wheel.id,
        kind: "assembly",
        name: "Wheel <2>",
        at: [300, 0, 0],
        grounded: true,
      },
    ]);
    await page.goto(`/assemblies/${bike.id}`);
    await waitForSolved(page);
    // Every spoke is drawn: 32 per wheel, as parts of their wheel.
    const wheelOne = bike.ids[1] ?? "";
    await expect
      .poll(() => page.locator(`[data-group-id="${wheelOne}"]`).count(), {
        timeout: 30_000,
      })
      .toBe(34);

    await page.getByTestId("inspector-view-bom").click();
    await page.getByTestId("bom-view-indented").click();
    const rows = page.getByTestId("bom-row");
    await expect(rows).toHaveCount(5);
    const read = await rows.evaluateAll((all) =>
      all.map((r) => [
        (r as HTMLElement).dataset.item,
        r.querySelector('[data-testid="bom-name"]')?.textContent,
        r.querySelector('[data-testid="bom-quantity"]')?.textContent,
        r.querySelector('[data-testid="bom-total-quantity"]')?.textContent,
      ]),
    );
    expect(read).toContainEqual(["2.3", "Spoke", "32", "64"]);
    expect(read).toContainEqual(["2", "Wheel", "2", "2"]);
    await page.mouse.move(1400, 900);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/asm-pattern.png` });
    await page.getByTestId("bom-view-parts").click();
    await expect(page.getByTestId("bom-total")).toHaveText("69");
  });
});
