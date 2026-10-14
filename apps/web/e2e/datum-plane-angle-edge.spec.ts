import { expect, test, type Page } from "./fixtures";

import { createFeature, SQUARE_20 } from "./partSeed";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * DATUM-PLANE-ANGLE from a model EDGE (Fusion 360's Plane at Angle: click an
 * edge, type an angle). Real stack, no mocks.
 *
 * A 20 mm cube, an angle parameter A = 25. In the UI: Datum > Plane at angle >
 * Pick an edge > click the top edge along X at y = 0, z = 20 > keep XY > type
 * the angle as the formula `A`. A circle r 5 at the plane's origin (the edge's
 * point nearest the world origin, (0, 0, 20)) is extruded symmetric 20 through
 * the API. The cylinder's axis is n = (0, -+sin a, cos a), so the body's
 * bounds are the cube's grown by it:
 *
 *   y_min = -(10 sin a + 5 cos a):  a = 25 -> -8.758,  a = 40 -> -10.258
 *   z_max = 20 + 10 cos a + 5 sin a: a = 25 -> 31.176
 *
 * Both are even in the sign of n's y part, so they hold whichever way the edge
 * runs. A = 40 in the Parameters panel turns the plane, the sketch and the
 * cylinder with it.
 */

function yMin(deg: number): number {
  const a = (deg * Math.PI) / 180;
  return -(10 * Math.sin(a) + 5 * Math.cos(a));
}

function zMax(deg: number): number {
  const a = (deg * Math.PI) / 180;
  return 20 + 10 * Math.cos(a) + 5 * Math.sin(a);
}

/** The three numbers of a bounding-box readout cell. */
async function corner(page: Page, testid: string): Promise<number[]> {
  const text = await page.getByTestId(testid).innerText();
  return (text.replace(/,(?=\d{3})/g, "").match(/-?\d+(?:\.\d+)?/g) ?? []).map(
    Number,
  );
}

/** Click the offered edge whose mid-span is at `mid` (from its aria-label). */
async function clickEdgeAt(
  page: Page,
  mid: [number, number, number],
): Promise<void> {
  const nodes = page.locator('[data-testid^="edge-pick-"]');
  await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
  const count = await nodes.count();
  for (let i = 0; i < count; i += 1) {
    const label = (await nodes.nth(i).getAttribute("aria-label")) ?? "";
    const centre = label.match(/centred at (.*) millimetres/)?.[1] ?? "";
    const xyz = centre.split(",").map((s) => Number.parseFloat(s));
    if (xyz.length === 3 && xyz.every((v, k) => Math.abs(v - mid[k]!) < 1e-6)) {
      await nodes.nth(i).click();
      return;
    }
  }
  throw new Error(`no offered edge centred at ${mid.join(", ")}`);
}

test("a plane at an angle from a picked edge, driven by a parameter, carries a sketch and an extrude", async ({
  page,
}) => {
  test.slow();
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Angled boss");
  const auth = { Authorization: `Bearer ${account.token}` };
  const table = await page.request.put(`/api/v1/parts/${part.id}/parameters`, {
    data: {
      expected_tree_version: 0,
      parameters: [
        {
          id: "00000000-0000-4000-8000-0000000025a1",
          name: "A",
          expression: "25",
          unit: "angle",
        },
      ],
    },
    headers: auth,
  });
  expect(table.ok(), await table.text()).toBe(true);
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: SQUARE_20 },
    expected_tree_version: ((await table.json()) as { tree_version: number })
      .tree_version,
  });
  await createFeature(page, account.token, part.id, {
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

  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("prop-volume")).toContainText("8,000", {
    timeout: 30_000,
  });

  // Datum > Plane at angle > Pick an edge: the top front edge along X.
  await page.getByTestId("tool-datum").click();
  await expect(page.getByTestId("datum-editor")).toBeVisible();
  await page.getByTestId("datum-kind").selectOption("angle");
  await page.getByTestId("datum-angle-edge-pick").click();
  await expect(page.getByTestId("datum-angle-edge-pick")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await clickEdgeAt(page, [10, 0, 20]);
  await expect(page.getByTestId("datum-angle-edge")).toHaveText(
    "Edge at 10, 0, 20 mm",
  );
  await expect(page.getByTestId("datum-angle-edge-pick")).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  await expect(page.locator('[data-testid^="edge-pick-"]')).toHaveCount(0);
  await expect(page.getByTestId("datum-angle-reference")).toHaveValue(
    "origin:XY",
  );
  const angle = page.getByTestId("datum-angle");
  await angle.fill("A");
  await expect(angle).toHaveAttribute("data-formula", "");
  await expect(page.getByTestId("datum-angle-hint")).toHaveText("= 25°");
  await page.mouse.move(1400, 900);
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/datum-plane-angle-edge-desktop.png`,
  });
  const write = page.waitForResponse(
    (r) => r.url().includes("/features") && r.request().method() === "POST",
  );
  // Enter takes the typed name as it stands (the list offers `A` itself) and
  // commits, as the sketcher's `W` Enter does.
  await angle.press("Enter");
  const created = await write;
  expect(created.status()).toBe(201);
  const datum = (await created.json()) as {
    feature: {
      id: string;
      feature: {
        params: Record<string, unknown>;
        expressions?: Record<string, string> | null;
      };
    };
    tree_version: number;
  };
  expect(datum.feature.feature.expressions).toEqual({ "/angle_deg": "A" });
  expect(datum.feature.feature.params).toMatchObject({
    kind: "angle",
    line: { kind: "subshape", subshape_type: "edge" },
    reference: { kind: "datum_plane", plane: "XY" },
    angle_deg: 25,
  });

  // Sketch on the new plane and extrude symmetric 20.
  const boss = await createFeature(page, account.token, part.id, {
    name: "Boss sketch",
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "feature", feature_id: datum.feature.id },
        entities: [
          { id: "c", kind: "circle", center: { x: 0, y: 0 }, radius: 5 },
        ],
        constraints: [],
      },
    },
    expected_tree_version: datum.tree_version,
  });
  await createFeature(page, account.token, part.id, {
    name: "Boss",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: boss.feature.id },
        distance_mm: 20,
        operation: "add",
        extent: "symmetric",
      },
    },
    expected_tree_version: boss.tree_version,
  });
  await page.reload();
  await expect(page.getByTestId("body-inspector")).toBeVisible({
    timeout: 30_000,
  });
  await expect
    .poll(async () => (await corner(page, "prop-bbox-min"))[1], {
      timeout: 30_000,
    })
    .toBeCloseTo(yMin(25), 1);
  expect((await corner(page, "prop-bbox-max"))[2]).toBeCloseTo(zMax(25), 1);
  expect((await corner(page, "prop-bbox-min"))[0]).toBeCloseTo(-5, 1);

  // A = 40 in the Parameters panel: the plane, the sketch and the boss turn.
  await page.getByTestId("parameters-tool").click();
  const panel = page.getByTestId("parameters-panel");
  const cell = panel
    .locator('[data-testid="parameter-row"][data-name="A"]')
    .getByTestId("parameter-expression");
  await cell.fill("40");
  await cell.press("Enter");
  await expect(panel.getByTestId("parameters-saving")).toBeHidden({
    timeout: 30_000,
  });
  await expect
    .poll(async () => (await corner(page, "prop-bbox-min"))[1], {
      timeout: 45_000,
    })
    .toBeCloseTo(yMin(40), 1);
  await expect(page.getByTestId("feature-error-2")).toHaveCount(0);
});
