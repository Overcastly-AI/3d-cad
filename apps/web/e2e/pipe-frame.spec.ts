import { expect, test, type Page } from "./fixtures";

import { createFeature } from "./partSeed";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * PIPE-ALONG-PATH: a bike frame from ONE skeleton sketch, through the real
 * stack. The skeleton (docs/reference-parts/bike.md: BB at the origin, seat
 * tube 500 at 73.5 deg, head tube top at reach 390 / stack 570, head tube 150
 * at the head angle) is seeded through the API with its head angle driven by
 * the parameter HA = 73 and a down-tube parameter DT = 44. Then in the UI:
 *
 *  - Pipe > pick the skeleton's down line > OD typed as `DT`, wall 1.2 > Create;
 *  - Pipe > pick the head line > OD 50, wall 3 > Create;
 *
 * and the frame's x_max is the head tube's bottom cap, by hand:
 * 390 + 150 cos HA + 25 sin HA = 457.763 at 73 deg. HA = 72 in the
 * Parameters panel rebuilds both tubes from the moved skeleton: 460.129.
 * The seat and top tubes are added on the same skeleton (API) for the
 * four-tube shot.
 */

function line(
  id: string,
  a: [number, number],
  b: [number, number],
  construction = false,
) {
  return {
    id,
    kind: "line",
    start: { x: a[0], y: a[1] },
    end: { x: b[0], y: b[1] },
    ...(construction ? { construction: true } : {}),
  };
}

const at = (entity: string, point: string) => ({ entity, point });

function skeletonParams() {
  return {
    plane: { kind: "datum_plane", plane: "XZ" },
    entities: [
      line("h", [0, 0], [600, 0], true),
      line("seat", [0, 0], [-142, 479]),
      line("top", [-142, 479], [390, 570]),
      line("head", [390, 570], [434, 427]),
      line("down", [0, 0], [434, 427]),
    ],
    constraints: [
      { kind: "fixed", point: at("h", "start") },
      { kind: "horizontal", entity: "h" },
      { kind: "distance", entity: "h", value_mm: 600 },
      { kind: "coincident", a: at("seat", "start"), b: at("h", "start") },
      { kind: "coincident", a: at("down", "start"), b: at("h", "start") },
      { kind: "coincident", a: at("top", "start"), b: at("seat", "end") },
      { kind: "coincident", a: at("top", "end"), b: at("head", "start") },
      { kind: "coincident", a: at("down", "end"), b: at("head", "end") },
      { kind: "distance", entity: "seat", value_mm: 500 },
      { kind: "angle", a: "h", b: "seat", value_deg: 106.5 },
      {
        kind: "point_distance",
        a: at("h", "start"),
        b: at("head", "start"),
        direction: "horizontal",
        value_mm: 390,
      },
      {
        kind: "point_distance",
        a: at("h", "start"),
        b: at("head", "start"),
        direction: "vertical",
        value_mm: 570,
      },
      { kind: "distance", entity: "head", value_mm: 150 },
      { kind: "angle", a: "h", b: "head", value_deg: 73, expression: "HA" },
    ],
  };
}

/** The three numbers of a bounding-box readout cell. */
async function corner(page: Page, testid: string): Promise<number[]> {
  const text = await page.getByTestId(testid).innerText();
  return (text.replace(/,(?=\d{3})/g, "").match(/-?\d+(?:\.\d+)?/g) ?? []).map(
    Number,
  );
}

function xMax(headAngleDeg: number): number {
  const a = (headAngleDeg * Math.PI) / 180;
  return 390 + 150 * Math.cos(a) + 25 * Math.sin(a);
}

async function pipeOnSkeleton(
  page: Page,
  entity: string,
  od: string,
  wall: string,
): Promise<Record<string, unknown>> {
  await page.getByTestId("create-more").click();
  await page.getByTestId("new-pipe").click();
  await expect(page.getByTestId("pipe-editor")).toBeVisible();
  await page.getByTestId(`pipe-curve-Skeleton-${entity}`).click();
  await expect(page.getByTestId("pipe-path-count")).toHaveText("1 curve");
  await page.getByTestId("pipe-od").fill(od);
  await page.getByTestId("pipe-wall").fill(wall);
  const write = page.waitForResponse(
    (r) => r.url().includes("/features") && r.request().method() === "POST",
  );
  await page.getByTestId("pipe-submit").click();
  const created = await write;
  expect(created.status(), await created.text()).toBe(201);
  const body = (await created.json()) as {
    feature: { feature: { params: Record<string, unknown> } };
  };
  await expect(page.getByTestId("pipe-editor")).toBeHidden();
  return body.feature.feature.params;
}

test("a two-tube frame from one skeleton follows a head-angle edit", async ({
  page,
}) => {
  test.slow();
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Bike frame");
  const auth = { Authorization: `Bearer ${account.token}` };
  const table = await page.request.put(`/api/v1/parts/${part.id}/parameters`, {
    data: {
      expected_tree_version: 0,
      parameters: [
        {
          id: "00000000-0000-4000-8000-0000000b1ea1",
          name: "HA",
          expression: "73",
          unit: "angle",
        },
        {
          id: "00000000-0000-4000-8000-0000000b1ea2",
          name: "DT",
          expression: "44",
          unit: "length",
        },
      ],
    },
    headers: auth,
  });
  expect(table.ok(), await table.text()).toBe(true);
  await createFeature(page, account.token, part.id, {
    name: "Skeleton",
    feature: { type: "sketch", version: 1, params: skeletonParams() },
    expected_tree_version: ((await table.json()) as { tree_version: number })
      .tree_version,
  });

  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });

  // Two Pipes on the one skeleton, through the editor.
  const down = await pipeOnSkeleton(page, "down", "DT", "1.2");
  expect(down).toMatchObject({
    path: [{ kind: "sketch_curve", entity: "down" }],
    outer_diameter_mm: 44,
    wall_thickness_mm: 1.2,
    operation: "add",
    merge: true,
  });
  await pipeOnSkeleton(page, "head", "50", "3");
  await expect
    .poll(async () => (await corner(page, "prop-bbox-max"))[0], {
      timeout: 45_000,
    })
    .toBeCloseTo(xMax(73), 1);

  // HA 73 -> 72: the skeleton re-solves and both tubes rebuild on it.
  await page.getByTestId("parameters-tool").click();
  const panel = page.getByTestId("parameters-panel");
  await expect(panel).toBeVisible();
  const cell = panel
    .locator('[data-testid="parameter-row"][data-name="HA"]')
    .getByTestId("parameter-expression");
  await cell.fill("72");
  await cell.press("Enter");
  await expect(panel.getByTestId("parameters-saving")).toBeHidden({
    timeout: 30_000,
  });
  await page.getByTestId("parameters-close").click();
  await expect
    .poll(async () => (await corner(page, "prop-bbox-max"))[0], {
      timeout: 45_000,
    })
    .toBeCloseTo(xMax(72), 1);

  // The seat and top tubes on the same skeleton: the four-tube frame.
  const tree = (await (
    await page.request.get(`/api/v1/parts/${part.id}/features`, {
      headers: auth,
    })
  ).json()) as {
    tree_version: number;
    features: { id: string; name: string }[];
  };
  const skeleton = tree.features.find((f) => f.name === "Skeleton");
  expect(skeleton).toBeDefined();
  let version = tree.tree_version;
  for (const [entity, od, wall] of [
    ["seat", 31.8, 1.0],
    ["top", 35.0, 1.0],
  ] as const) {
    const made = await createFeature(page, account.token, part.id, {
      name: `Pipe ${entity}`,
      feature: {
        type: "pipe",
        version: 1,
        params: {
          path: [
            {
              kind: "sketch_curve",
              sketch: { kind: "feature", feature_id: skeleton!.id },
              entity,
            },
          ],
          outer_diameter_mm: od,
          wall_thickness_mm: wall,
          operation: "add",
        },
      },
      expected_tree_version: version,
    });
    version = made.tree_version;
  }
  await page.reload();
  await expect(page.getByTestId("body-inspector")).toBeVisible({
    timeout: 30_000,
  });
  // The seat tube's top cap now sets x_min: -500 cos 73.5 - 15.9 sin 73.5.
  await expect
    .poll(async () => (await corner(page, "prop-bbox-min"))[0], {
      timeout: 45_000,
    })
    .toBeCloseTo(-157.253, 1);
  await page.keyboard.press("0");
  await page.mouse.move(1500, 950);
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${SCREENSHOT_DIR}/pipe-frame.png` });
});
