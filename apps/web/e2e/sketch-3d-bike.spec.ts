import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * SKETCH-3D: the bike frame skeleton built in a 3D sketch FROM THE UI, then
 * piped, with no API seeding (bike QA rounds 2 and 3). The skeleton is the
 * reference part's (docs/reference-parts/bike.md) in model space: BB at the
 * origin, X forward, Z up; seat tube 500 at 73.5 deg, head tube top at
 * reach 390 / stack 570, head tube 150 at 73 deg, rear axle 410 from the BB
 * and 70 above it with the dropouts 130 apart across Y, so the chain and seat
 * stays splay out of the frame plane.
 *
 * In the UI: Create > 3D sketch; click the origin snap for the BB; type the
 * seat top 2 mm short, the head tube top, the head bottom 2 mm short, click
 * the BB to close the down tube; type each dropout 1 mm in across Y and click
 * back through the seat top for the stays; then Fix the head top, Length 500
 * and 150 on the seat and head tubes, Along Y and Distance 130 across the
 * dropouts. The solve puts every point on the reference to 1e-9 (read back
 * from the rebuild), and six Pipes from the Pipe editor (down, seat, top,
 * head, both chain stays) make one body whose volume is the build123d twin's
 * (services/geometry/tests/test_sketch_3d.py: 324271.95 mm^3).
 */

const SEAT = (73.5 * Math.PI) / 180;
const HEAD = (73 * Math.PI) / 180;
const AXLE_X = -Math.sqrt(410 ** 2 - 70 ** 2);
const REFERENCE: Record<string, [number, number, number]> = {
  p1: [0, 0, 0],
  p2: [-500 * Math.cos(SEAT), 0, 500 * Math.sin(SEAT)],
  p3: [390, 0, 570],
  p4: [390 + 150 * Math.cos(HEAD), 0, 570 - 150 * Math.sin(HEAD)],
  p5: [AXLE_X, 65, 70],
  p6: [AXLE_X, -65, 70],
};

async function typePoint(page: Page, [x, y, z]: number[]): Promise<void> {
  // Full precision: the box reads what is typed, as the 2D draw box does.
  await page.getByTestId("sketch3d-x").fill(String(x));
  await page.getByTestId("sketch3d-y").fill(String(y));
  await page.getByTestId("sketch3d-z").fill(String(z));
  await page.getByTestId("sketch3d-z").press("Enter");
}

async function select(page: Page, ...ids: string[]): Promise<void> {
  for (const id of ids) {
    const kind = id.startsWith("p") ? "point" : "line";
    await page.getByTestId(`sketch3d-${kind}-${id}`).click();
  }
}

async function dimension(page: Page, value: string): Promise<void> {
  await page.getByTestId("sketch3d-dimension").fill(value);
  await page.getByTestId("sketch3d-add-dimension").click();
}

async function pipe(page: Page, line: string, od: string, wall: string) {
  await page.getByTestId("create-more").click();
  await page.getByTestId("new-pipe").click();
  await expect(page.getByTestId("pipe-editor")).toBeVisible();
  await page.getByTestId(`pipe-curve-3DSketch1-${line}`).click();
  await expect(page.getByTestId("pipe-path-count")).toHaveText("1 curve");
  await page.getByTestId("pipe-od").fill(od);
  await page.getByTestId("pipe-wall").fill(wall);
  const write = page.waitForResponse(
    (r) => r.url().includes("/features") && r.request().method() === "POST",
  );
  await page.getByTestId("pipe-submit").click();
  const created = await write;
  expect(created.status(), await created.text()).toBe(201);
  await expect(page.getByTestId("pipe-editor")).toBeHidden();
}

test("the bike skeleton is a 3D sketch built in the UI and piped", async ({
  page,
}) => {
  test.slow();
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Bike 3D");
  const auth = { Authorization: `Bearer ${account.token}` };
  await page.goto(`/parts/${part.id}`);

  await page.getByTestId("create-more").click();
  await page.getByTestId("new-sketch-3d").click();
  const editor = page.getByTestId("sketch3d-editor");
  await expect(editor).toBeVisible();

  // The BB: snapped to the origin in the viewport.
  await page.getByTestId("sketch3d-snap-origin").click();
  await expect(page.getByTestId("sketch3d-point-p1")).toContainText(
    "on origin",
  );
  // Main triangle: seat top and head bottom typed 2 mm short of the reference.
  const short = (r: number, angle: number) => [
    -r * Math.cos(angle),
    0,
    r * Math.sin(angle),
  ];
  await typePoint(page, short(498, SEAT));
  await typePoint(page, [390, 0, 570]);
  await typePoint(page, [
    390 + 148 * Math.cos(HEAD),
    0,
    570 - 148 * Math.sin(HEAD),
  ]);
  // Back to the BB: the down tube, by its mark in the viewport.
  await page.getByTestId("sketch3d-own-p1").click();
  // Rear triangle: chain stay left, then from the BB again the right one,
  // then through the seat top for both seat stays, and the axle.
  await typePoint(page, [AXLE_X, 64, 70]);
  // Joints out of view are joined from the point list (Join).
  await page.getByTestId("sketch3d-end-chain").click();
  await page.getByTestId("sketch3d-continue-p1").click();
  await typePoint(page, [AXLE_X, -64, 70]);
  await page.getByTestId("sketch3d-continue-p2").click();
  await page.getByTestId("sketch3d-continue-p5").click();
  await page.getByTestId("sketch3d-continue-p6").click();
  await page.getByTestId("sketch3d-construction-l9").click();
  await expect(page.getByTestId("sketch3d-lines")).toContainText(
    "l9: p5 → p6 (construction)",
  );

  // Relations: Fix, two lengths, Along Y and the hub spacing.
  await select(page, "p3");
  await page.getByTestId("sketch3d-fix").click();
  await select(page, "l1");
  await dimension(page, "500");
  await select(page, "l3");
  await dimension(page, "150");
  await select(page, "l9");
  await page.getByTestId("sketch3d-along-y").click();
  await select(page, "p5", "p6");
  await dimension(page, "130");
  await expect(page.getByTestId("sketch3d-constraints")).toContainText(
    "Distance p5 p6 = 130",
  );

  const write = page.waitForResponse(
    (r) => r.url().includes("/features") && r.request().method() === "POST",
  );
  await page.getByTestId("sketch3d-submit").click();
  const created = await write;
  expect(created.status(), await created.text()).toBe(201);
  const body = (await created.json()) as {
    feature: { id: string; feature: { type: string; params: unknown } };
  };
  expect(body.feature.feature.type).toBe("sketch_3d");
  await expect(editor).toBeHidden();
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });

  // The solve, read back from the rebuild: every joint on the reference.
  const evaluated = await page.request.post(
    `/api/v1/parts/${part.id}/evaluate`,
    { data: {}, headers: auth },
  );
  expect(evaluated.ok(), await evaluated.text()).toBe(true);
  const result = (await evaluated.json()) as {
    features: {
      feature_id: string;
      data?: {
        kind: string;
        dof: number;
        points: { id: string; position: { x: number; y: number; z: number } }[];
      };
    }[];
  };
  const solved = result.features.find(
    (f) => f.feature_id === body.feature.id,
  )?.data;
  expect(solved?.kind).toBe("solved_sketch_3d");
  expect(solved?.dof).toBe(7);
  for (const p of solved?.points ?? []) {
    const want = REFERENCE[p.id];
    expect(want, p.id).toBeDefined();
    const got = [p.position.x, p.position.y, p.position.z];
    for (let i = 0; i < 3; i++) {
      expect(
        Math.abs((got[i] as number) - (want as number[])[i]!),
      ).toBeLessThan(1e-9);
    }
  }

  // Six Pipes from the Pipe editor on the 3D sketch's lines.
  await pipe(page, "l4", "44", "1.2"); // down
  await pipe(page, "l1", "31.8", "1"); // seat
  await pipe(page, "l2", "35", "1"); // top
  await pipe(page, "l3", "50", "3"); // head
  await pipe(page, "l5", "22", "1"); // chain stay, left
  await pipe(page, "l6", "22", "1"); // chain stay, right
  await expect
    .poll(
      async () => {
        const response = await page.request.post(
          `/api/v1/parts/${part.id}/evaluate`,
          { data: {}, headers: auth },
        );
        const data = (await response.json()) as {
          properties: { volume: number } | null;
          bodies: unknown[];
        };
        return [data.bodies.length, data.properties?.volume ?? 0];
      },
      { timeout: 60_000 },
    )
    .toEqual([1, expect.closeTo(324271.95, 1)]);
  // The splayed stays set y by hand: 65 + 11 sqrt(1 - (65/|dropout|)^2).
  const reach = Math.hypot(AXLE_X, 65, 70);
  const yMax = 65 + 11 * Math.sqrt(1 - (65 / reach) ** 2);
  await expect
    .poll(
      async () => {
        const text = await page.getByTestId("prop-bbox-max").innerText();
        const values = (
          text.replace(/,(?=\d{3})/g, "").match(/-?\d+(?:\.\d+)?/g) ?? []
        ).map(Number);
        return values[1] ?? 0;
      },
      { timeout: 45_000 },
    )
    .toBeCloseTo(yMax, 1);

  await page.keyboard.press("0");
  await page.mouse.move(1500, 950);
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${SCREENSHOT_DIR}/sketch-3d-bike.png` });
});
