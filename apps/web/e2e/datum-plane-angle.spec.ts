import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * DATUM-PLANE-ANGLE: Fusion 360's Plane at Angle, through the real stack (no
 * mocks). The moto frame's steering head: a construction line along -Y through
 * the front apex (on an XY datum at the apex height), and the front cross tube
 * through the apex, are seeded through the API. Then, in the UI, the engineer
 * opens Datum, picks "At an angle about a line", chooses that sketch line,
 * keeps XY as the reference and types 25. The 50/32 head annulus is sketched on
 * the new plane and extruded symmetric 160 (API), and the body's bounds are the
 * head's, raked 25 deg back:
 *
 *   x_max = apex.x + 80 sin25 + 25 cos25 = 24.083   (the frame golden's x_max)
 *   z_min = apex.z - 80 cos25 - 25 sin25 = 412.397
 *
 * Editing the angle to 30 in the editor moves the plane, the sketch on it and
 * the tube with it: x_max = apex.x + 80 sin30 + 25 cos30 = 29.267.
 */

const APEX_X = -32.38409359864937;
const APEX_Z = 495.46749033400226;

function circle(id: string, x: number, y: number, radius: number) {
  return { id, kind: "circle", center: { x, y }, radius };
}

async function createFeature(
  page: Page,
  token: string,
  partId: string,
  body: unknown,
): Promise<{ feature: { id: string }; tree_version: number }> {
  const response = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: body,
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) {
    throw new Error(
      `e2e create feature failed: ${response.status()} ${await response.text()}`,
    );
  }
  return (await response.json()) as {
    feature: { id: string };
    tree_version: number;
  };
}

/** The head-height datum, the axis sketch, and the front cross tube. */
async function seedFrameFront(
  page: Page,
): Promise<{ token: string; partId: string; axisId: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Steering head");
  const height = await createFeature(page, account.token, part.id, {
    name: "Head height",
    feature: {
      type: "datum",
      version: 1,
      params: { kind: "offset", base: "XY", offset_mm: APEX_Z, flip: false },
    },
    expected_tree_version: 0,
  });
  const axis = await createFeature(page, account.token, part.id, {
    name: "Head axis",
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "feature", feature_id: height.feature.id },
        entities: [
          {
            id: "head",
            kind: "line",
            construction: true,
            start: { x: APEX_X, y: 10 },
            end: { x: APEX_X, y: -10 },
          },
        ],
        constraints: [],
      },
    },
    expected_tree_version: height.tree_version,
  });
  const cross = await createFeature(page, account.token, part.id, {
    name: "Cross tube",
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "datum_plane", plane: "XZ" },
        entities: [
          circle("o", APEX_X, APEX_Z, 12.7),
          circle("i", APEX_X, APEX_Z, 11.1),
        ],
        constraints: [],
      },
    },
    expected_tree_version: axis.tree_version,
  });
  const tube = await createFeature(page, account.token, part.id, {
    name: "Cross tube",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: cross.feature.id },
        distance_mm: 208,
        operation: "add",
        extent: "symmetric",
      },
    },
    expected_tree_version: cross.tree_version,
  });
  expect(tube.tree_version).toBeGreaterThan(0);
  return { token: account.token, partId: part.id, axisId: axis.feature.id };
}

/** The three numbers of a bounding-box readout cell. */
async function corner(page: Page, testid: string): Promise<number[]> {
  const text = await page.getByTestId(testid).innerText();
  return (text.replace(/,(?=\d{3})/g, "").match(/-?\d+(?:\.\d+)?/g) ?? []).map(
    Number,
  );
}

test.describe("datum plane at an angle", () => {
  test("a plane at 25 deg about a sketch line carries the raked steering head, and follows an edit to 30", async ({
    page,
  }) => {
    const seeded = await seedFrameFront(page);
    await page.goto(`/parts/${seeded.partId}`);
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });

    // Datum > At an angle about a line: the sketch line, XY, 25.
    await page.getByTestId("tool-datum").click();
    await expect(page.getByTestId("datum-editor")).toBeVisible();
    await page.getByTestId("datum-kind").selectOption("angle");
    await page
      .getByTestId("datum-angle-line")
      .selectOption({ label: "Head axis · construction line head" });
    await expect(page.getByTestId("datum-angle-reference")).toHaveValue(
      "origin:XY",
    );
    await page.getByTestId("datum-angle").fill("25");
    const write = page.waitForResponse(
      (r) => r.url().includes("/features") && r.request().method() === "POST",
    );
    await page.getByTestId("datum-submit").click();
    const created = await write;
    expect(created.status()).toBe(201);
    const datum = (await created.json()) as {
      feature: { id: string; feature: { params: Record<string, unknown> } };
      tree_version: number;
    };
    expect(datum.feature.feature.params).toMatchObject({
      kind: "angle",
      line: { kind: "sketch_line", entity: "head" },
      reference: { kind: "datum_plane", plane: "XY" },
      angle_deg: 25,
      flip: false,
    });

    // The head: the 50/32 annulus at the plane's origin (the apex), extruded
    // symmetric 160.
    const head = await createFeature(page, seeded.token, seeded.partId, {
      name: "Head sketch",
      feature: {
        type: "sketch",
        version: 1,
        params: {
          plane: { kind: "feature", feature_id: datum.feature.id },
          entities: [circle("o", 0, 0, 25), circle("i", 0, 0, 16)],
          constraints: [],
        },
      },
      expected_tree_version: datum.tree_version,
    });
    await createFeature(page, seeded.token, seeded.partId, {
      name: "Steering head",
      feature: {
        type: "extrude",
        version: 1,
        params: {
          profile: { kind: "feature", feature_id: head.feature.id },
          distance_mm: 160,
          operation: "add",
          extent: "symmetric",
        },
      },
      expected_tree_version: head.tree_version,
    });
    await page.reload();
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    await expect
      .poll(async () => (await corner(page, "prop-bbox-max"))[0], {
        timeout: 30_000,
      })
      .toBeCloseTo(24.083, 1);
    expect((await corner(page, "prop-bbox-min"))[2]).toBeCloseTo(412.397, 1);
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
      .toBeGreaterThan(24);

    // Re-open the plane: the editor seeds 25 and the viewport draws the plane
    // it resolves to, through the apex, square to the raked head (the
    // founder's shot). Then edit the angle to 30: the plane, the sketch on it
    // and the tube follow.
    await page.getByTestId("feature-select-4").click();
    await expect(page.getByTestId("datum-editor")).toBeVisible();
    await expect(page.getByTestId("datum-angle")).toHaveValue("25");
    await expect(page.getByTestId("datum-angle-line")).toHaveValue(
      `sketch:${seeded.axisId}:head`,
    );
    await page.mouse.move(1400, 900);
    await page.waitForTimeout(500);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/datum-plane-angle-steering-head-desktop.png`,
    });
    await page.getByTestId("datum-angle").fill("30");
    await page.getByTestId("datum-submit").click();
    await expect
      .poll(async () => (await corner(page, "prop-bbox-max"))[0], {
        timeout: 30_000,
      })
      .toBeCloseTo(29.267, 1);
  });
});
