import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, distinctCanvasColors, seedSession } from "./support";

/**
 * Adversarial QA for BACKLOG #6 (measure) + #7 (pattern), driving the REAL
 * stack in a real browser. These specs deliberately probe the EDGES the
 * happy-path specs skip: the disabled-tool guards, a rollback landing mid-
 * measure (the just-fixed 🟡), keyboard-only + touch picking, and the honest
 * pattern rebuild-error surfaces (disjoint copies, no-op counts). Nothing here
 * is a golden-geometry check (that is geometry-qa) — it verifies the user-
 * facing behaviour the shipped flows promise.
 */

interface Vec3 {
  x: number;
  y: number;
  z: number;
}

/** A 10×20 rectangle fixed at the origin on XY — solves to clean corners. */
const RECTANGLE_10x20 = {
  plane: { kind: "datum_plane", plane: "XY" },
  entities: [
    { id: "e1", kind: "line", start: { x: 0, y: 0 }, end: { x: 9.7, y: 0.4 } },
    {
      id: "e2",
      kind: "line",
      start: { x: 10, y: 0.2 },
      end: { x: 10.3, y: 19 },
    },
    {
      id: "e3",
      kind: "line",
      start: { x: 10.2, y: 20.4 },
      end: { x: -0.3, y: 19.7 },
    },
    {
      id: "e4",
      kind: "line",
      start: { x: 0.3, y: 19.5 },
      end: { x: -0.2, y: 0.5 },
    },
  ],
  constraints: [
    {
      kind: "coincident",
      a: { entity: "e1", point: "end" },
      b: { entity: "e2", point: "start" },
    },
    {
      kind: "coincident",
      a: { entity: "e2", point: "end" },
      b: { entity: "e3", point: "start" },
    },
    {
      kind: "coincident",
      a: { entity: "e3", point: "end" },
      b: { entity: "e4", point: "start" },
    },
    {
      kind: "coincident",
      a: { entity: "e4", point: "end" },
      b: { entity: "e1", point: "start" },
    },
    { kind: "horizontal", entity: "e1" },
    { kind: "vertical", entity: "e2" },
    { kind: "horizontal", entity: "e3" },
    { kind: "vertical", entity: "e4" },
    { kind: "distance", entity: "e1", value_mm: 10 },
    { kind: "distance", entity: "e2", value_mm: 20 },
    { kind: "fixed", point: { entity: "e1", point: "start" } },
  ],
};

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

/** Seed a sketch-only part (a solved rectangle, NO body). */
async function seedSketchOnlyPart(page: Page): Promise<{ id: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Sketch only");
  await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: RECTANGLE_10x20 },
    expected_tree_version: 0,
  });
  return part;
}

/** Seed a part whose body is a 10×20×30 box with a corner at the origin. */
async function seedBoxPart(page: Page): Promise<{ id: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Measured box");
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: RECTANGLE_10x20 },
    expected_tree_version: 0,
  });
  await createFeature(page, account.token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 30,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  return part;
}

function vertexIndex(vertices: Vec3[], target: Vec3): number {
  return vertices.findIndex(
    (v) => Math.hypot(v.x - target.x, v.y - target.y, v.z - target.z) < 1e-4,
  );
}

/** Arm Measure and return the loaded overlay (vertices+edges). */
async function armMeasure(page: Page): Promise<{ vertices: Vec3[] }> {
  const overlayResponse = page.waitForResponse(
    (r) =>
      r.url().includes("/api/v1/geometry/overlay") &&
      r.request().method() === "POST",
  );
  await page.getByTestId("measure-tool").click();
  await expect(page.getByTestId("measure-tool")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  return (await (await overlayResponse).json()) as { vertices: Vec3[] };
}

async function waitForBox(page: Page): Promise<void> {
  await expect(page.getByTestId("prop-volume")).toContainText("6,000", {
    timeout: 30_000,
  });
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
}

// ---------------------------------------------------------------------------
// MEASURE — guards, rollback-mid-measure, keyboard, edge-edge angle
// ---------------------------------------------------------------------------
test.describe("measure — edges & guards", () => {
  test("no body → Measure tool is disabled and M is a no-op (never crashes)", async ({
    page,
  }) => {
    const part = await seedSketchOnlyPart(page);
    await page.goto(`/parts/${part.id}`);
    // The tree loads (a sketch feature) but there is no solid.
    await expect(page.getByTestId("feature-row")).toHaveCount(1);

    const measure = page.getByTestId("measure-tool");
    await expect(measure).toBeDisabled();

    // The M accelerator must not arm the tool without a body.
    await page.keyboard.press("m");
    await expect(page.getByTestId("measure-readout")).toHaveCount(0);
    // The app is still alive and coherent.
    await expect(measure).toBeVisible();
  });

  test("rollback landing mid-measure disarms the tool and drops the picks (no stale reading)", async ({
    page,
  }) => {
    const part = await seedBoxPart(page);
    await page.goto(`/parts/${part.id}`);
    await waitForBox(page);

    const overlay = await armMeasure(page);
    const a = vertexIndex(overlay.vertices, { x: 0, y: 0, z: 0 });
    expect(a).toBeGreaterThanOrEqual(0);

    // Pick the FIRST target, then leave the measure mid-flight.
    await page.getByTestId(`measure-vertex-${a}`).dispatchEvent("click");
    await expect(page.getByTestId("measure-prompt")).toContainText(
      "Pick the second point or edge",
    );

    // Roll the build back to before the extrude (slot 0 = after Sketch1).
    await page.getByTestId("rollback-slot-0").click();

    // The measure tool must disarm — the readout is gone, no orphan result,
    // and the tool button is no longer pressed. A stale pick index can never
    // resolve against the rebuilt (now body-less) tree.
    await expect(page.getByTestId("measure-readout")).toHaveCount(0);
    await expect(page.getByTestId("measure-tool")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    // The body is gone (rolled back before the extrude) → Measure re-disables.
    await expect(page.getByTestId("measure-tool")).toBeDisabled();
  });

  test("keyboard-only pick (focus a pick node + Enter) reads the golden distance", async ({
    page,
  }) => {
    const part = await seedBoxPart(page);
    await page.goto(`/parts/${part.id}`);
    await waitForBox(page);

    const overlay = await armMeasure(page);
    const a = vertexIndex(overlay.vertices, { x: 0, y: 0, z: 0 });
    const b = vertexIndex(overlay.vertices, { x: 10, y: 20, z: 30 });
    expect(a).toBeGreaterThanOrEqual(0);
    expect(b).toBeGreaterThanOrEqual(0);

    // The claimed a11y path: the pick nodes are real buttons — focus and
    // activate them by keyboard alone.
    const nodeA = page.getByTestId(`measure-vertex-${a}`);
    await nodeA.focus();
    await expect(nodeA).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("measure-prompt")).toContainText(
      "Pick the second point or edge",
    );

    const nodeB = page.getByTestId(`measure-vertex-${b}`);
    await nodeB.focus();
    await page.keyboard.press("Enter");

    // √1400 mm via `formatLength` (units convention: doc unit + 4 max fraction
    // digits, trailing zeros trimmed) → exactly "37.4166 mm"; whole-mm deltas
    // render without fraction digits. Exact match, tied to the geometry golden.
    await expect(page.getByTestId("measure-readout-distance")).toHaveText(
      "37.4166 mm",
    );
    await expect(page.getByTestId("measure-readout-dx")).toHaveText("10 mm");
    await expect(page.getByTestId("measure-readout-dz")).toHaveText("30 mm");
  });

  test("edge-edge measure shows an angle for two straight edges", async ({
    page,
  }) => {
    const part = await seedBoxPart(page);
    await page.goto(`/parts/${part.id}`);
    await waitForBox(page);
    await armMeasure(page);

    // Pick two edge marks; a box's edges are all straight lines, so the
    // readout must include the angle cell (0° for parallel edges).
    const measureResponse = page.waitForResponse(
      (r) =>
        r.url().includes("/api/v1/geometry/measure") &&
        r.request().method() === "POST",
    );
    await page.getByTestId("measure-edge-0").dispatchEvent("click");
    await expect(page.getByTestId("measure-prompt")).toContainText(
      "Pick the second point or edge",
    );
    await page.getByTestId("measure-edge-1").dispatchEvent("click");
    expect((await measureResponse).status()).toBe(200);

    await expect(page.getByTestId("measure-readout-distance")).toBeVisible();
    // Two straight edges → an angle IS reported (per the acceptance criteria).
    await expect(page.getByTestId("measure-readout-angle")).toBeVisible();
  });
});

/**
 * DEFECT REGRESSION (BACKLOG #6, P1): real pointer/touch picking of a vertex is
 * broken. Every STRAIGHT edge's overlay polyline is [start, end] (2 points), so
 * `polylineMidpoint` returns polyline[floor(2/2)] = polyline[1] = the edge's END
 * VERTEX, not its midpoint. Every edge pick-mark thus renders at the SAME screen
 * point as a vertex mark, and because edges paint AFTER vertices in the DOM the
 * edge node sits on top and intercepts the click. A real `.click()` / `.tap()`
 * on any corner selects an edge instead of the vertex — so a user cannot perform
 * the headline "two corners → 37.42" flow. The shipped measure.spec only passes
 * because it uses `dispatchEvent("click")`, which bypasses hit-testing.
 *
 * These two tests SHOULD pass once the overlap/mark-placement is fixed; they are
 * red today by design, documenting the defect.
 */
test.describe("measure — real pointer picking (P1 regression)", () => {
  test("desktop: a REAL click on a corner selects the vertex (not an occluding edge)", async ({
    page,
  }) => {
    const part = await seedBoxPart(page);
    await page.goto(`/parts/${part.id}`);
    await waitForBox(page);
    const overlay = await armMeasure(page);
    const a = vertexIndex(overlay.vertices, { x: 0, y: 0, z: 0 });

    // A real pointer click (NOT dispatchEvent) — what a user actually does.
    await page.getByTestId(`measure-vertex-${a}`).click({ timeout: 8000 });
    await expect(page.getByTestId(`measure-vertex-${a}`)).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  test.describe("touch", () => {
    test.use({ hasTouch: true, viewport: { width: 1280, height: 800 } });

    test("tap two vertices on a touch viewport reads the distance", async ({
      page,
    }) => {
      const part = await seedBoxPart(page);
      await page.goto(`/parts/${part.id}`);
      await waitForBox(page);
      const overlay = await armMeasure(page);
      const a = vertexIndex(overlay.vertices, { x: 0, y: 0, z: 0 });
      const b = vertexIndex(overlay.vertices, { x: 10, y: 20, z: 30 });

      // A genuine tap (touch), not a synthetic click — the CAD-on-touch path.
      await page.getByTestId(`measure-vertex-${a}`).tap({ timeout: 8000 });
      await expect(page.getByTestId("measure-prompt")).toContainText(
        "Pick the second point or edge",
      );
      await page.getByTestId(`measure-vertex-${b}`).tap({ timeout: 8000 });
      // √1400 mm → "37.4166 mm" (formatLength, units convention). Exact match.
      await expect(page.getByTestId("measure-readout-distance")).toHaveText(
        "37.4166 mm",
      );
    });
  });
});

// ---------------------------------------------------------------------------
// PATTERN — guards, honest rebuild errors, edit, rollback
// ---------------------------------------------------------------------------
test.describe("pattern — guards & error paths", () => {
  test("no body → Pattern tool is disabled and P is a no-op", async ({
    page,
  }) => {
    const part = await seedSketchOnlyPart(page);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("feature-row")).toHaveCount(1);

    await expect(page.getByTestId("new-pattern")).toBeDisabled();
    await page.keyboard.press("p");
    await expect(page.getByTestId("pattern-editor")).toHaveCount(0);
  });

  test("the form guards a no-op count: count 1 keeps Create disabled", async ({
    page,
  }) => {
    const part = await seedBoxPart(page);
    await page.goto(`/parts/${part.id}`);
    await waitForBox(page);

    await page.getByTestId("new-pattern").click();
    await expect(page.getByTestId("pattern-editor")).toBeVisible();

    const count = page.getByTestId("pattern-count");
    await count.fill("1");
    // "Includes the seed — enter a whole number of 2 or more." + disabled submit.
    await expect(page.getByTestId("pattern-submit")).toBeDisabled();

    // Zero spacing is likewise blocked at the form (never reaches the kernel).
    await count.fill("3");
    await page.getByTestId("pattern-spacing").fill("0");
    await expect(page.getByTestId("pattern-submit")).toBeDisabled();
  });

  test("disjoint linear pattern surfaces a legible rebuild error and preserves the last-good body", async ({
    page,
  }) => {
    const part = await seedBoxPart(page);
    await page.goto(`/parts/${part.id}`);
    await waitForBox(page);

    await page.getByTestId("new-pattern").click();
    await expect(page.getByTestId("pattern-editor")).toBeVisible();

    // Spacing 100 mm on a 10 mm-wide box → 3 disjoint lumps: the v1 single-
    // body-chain rule must reject this as a per-feature `pattern_disjoint`
    // error, NOT a 500 / white screen.
    await page.getByTestId("pattern-count").fill("3");
    await page.getByTestId("pattern-spacing").fill("100");
    await page.getByTestId("pattern-spacing").press("Enter");

    // The pattern lands in the tree (3 features) but evaluates to an error.
    await expect(page.getByTestId("feature-row")).toHaveCount(3);
    const err = page.getByTestId("feature-error-2");
    await expect(err).toBeVisible();
    await expect(err).toContainText("pattern_disjoint");
    await expect(err).toContainText(/disjoint|connected solid|single/i);
    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 30_000,
    });

    // The last-good body (the box) is preserved and still renders.
    await expect(page.getByTestId("prop-volume")).toContainText("6,000");
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 10_000 })
      .toBeGreaterThan(24);

    // No white-screen: the app chrome is intact.
    await expect(page.getByTestId("feature-tree")).toBeVisible();
    await expect(page.getByTestId("measure-tool")).toBeVisible();
  });

  test("edit a pattern: change the count and the body re-renders wider", async ({
    page,
  }) => {
    const part = await seedBoxPart(page);
    await page.goto(`/parts/${part.id}`);
    await waitForBox(page);

    // Create a linear pattern, count 3 spacing 6 (unions to a 22 mm-wide bar).
    await page.getByTestId("new-pattern").click();
    await page.getByTestId("pattern-count").fill("3");
    await page.getByTestId("pattern-spacing").fill("6");
    await page.getByTestId("pattern-spacing").press("Enter");
    await expect(page.getByTestId("feature-row")).toHaveCount(3);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    const extentsText = () => page.getByTestId("prop-extents").innerText();
    await expect
      .poll(async () => {
        const nums =
          (await extentsText()).replace(/,/g, "").match(/-?\d+(?:\.\d+)?/g) ??
          [];
        return Number.parseFloat(nums[0] ?? "NaN");
      })
      .toBeGreaterThan(20); // ~22 mm

    // Edit: select the pattern row, bump count to 5 (unions to ~34 mm wide).
    await page.getByTestId("feature-select-2").click();
    await expect(page.getByTestId("pattern-editor")).toBeVisible();
    await page.getByTestId("pattern-count").fill("5");
    await page.getByTestId("pattern-count").press("Enter");
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect
      .poll(
        async () => {
          const nums =
            (await extentsText()).replace(/,/g, "").match(/-?\d+(?:\.\d+)?/g) ??
            [];
          return Number.parseFloat(nums[0] ?? "NaN");
        },
        { timeout: 30_000 },
      )
      .toBeGreaterThan(30); // ~34 mm — the edit took
  });

  test("rollback before a pattern returns the seed body; roll forward restores it", async ({
    page,
  }) => {
    const part = await seedBoxPart(page);
    await page.goto(`/parts/${part.id}`);
    await waitForBox(page);

    await page.getByTestId("new-pattern").click();
    await page.getByTestId("pattern-count").fill("3");
    await page.getByTestId("pattern-spacing").fill("6");
    await page.getByTestId("pattern-spacing").press("Enter");
    await expect(page.getByTestId("feature-row")).toHaveCount(3);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    // Wider bar volume (13,200 mm³).
    await expect(page.getByTestId("prop-volume")).toContainText("13,200", {
      timeout: 30_000,
    });

    // Roll back to after the extrude (slot 1) → the seed box returns (6,000).
    await page.getByTestId("rollback-slot-1").click();
    await expect(page.getByTestId("prop-volume")).toContainText("6,000", {
      timeout: 30_000,
    });

    // Roll forward to the tip → the pattern's wider bar comes back.
    await page.getByTestId("rollback-slot-2").click();
    await expect(page.getByTestId("prop-volume")).toContainText("13,200", {
      timeout: 30_000,
    });
  });
});
