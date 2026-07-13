import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * Construction geometry (BACKLOG #2, 2b — the UI half). Draw a 40×25
 * rectangle plus a diagonal line, then use the keyboard-verb toggle (N,
 * selection-presence pattern) to mark the diagonal as construction. The
 * correct CAD semantics: construction geometry is reference-only — it solves
 * and renders (dashed/muted) but is EXCLUDED from the profile that gates
 * extrude. So the extrude consumes the rectangle alone (volume 10,000 mm³),
 * ignoring the diagonal, and the `construction` flag round-trips on reload.
 * Real stack: gateway + documents + geometry, no mocks.
 */

interface SketchEntityRow {
  id: string;
  kind: string;
  construction?: boolean;
}

async function enterSketch(page: Page, plane: "XY" | "XZ" | "YZ") {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId(`plane-${plane}`).click();
  await expect(page.getByTestId("sketch-step")).toHaveText(`On ${plane}`);
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
}

/**
 * Plane-mm → screen-px mapper (identical technique to constraints.spec):
 * read the DRO at two screen points with snap off, so later clicks land on
 * exact millimetre coordinates. The drawn rectangle IS 40×25, so the extrude
 * volume is exactly 10,000 mm³ and the assertion has no slop.
 */
async function calibratePlane(
  page: Page,
  s1: { x: number; y: number },
  s2: { x: number; y: number },
): Promise<(pt: { x: number; y: number }) => { x: number; y: number }> {
  await page.keyboard.press("g"); // snap off for raw readings
  {
    let last: number | null = null;
    await expect
      .poll(
        async () => {
          await page.mouse.move(s1.x + 2, s1.y);
          await page.mouse.move(s1.x, s1.y);
          const value = Number.parseFloat(
            await page.getByTestId("dro-x").innerText(),
          );
          const stable =
            last !== null && Number.isFinite(value) && value === last;
          last = value;
          return stable;
        },
        { timeout: 15_000 },
      )
      .toBe(true);
  }
  const read = async (
    sx: number,
    sy: number,
    distinctFromX?: number,
  ): Promise<{ x: number; y: number }> => {
    await page.mouse.move(sx, sy);
    await expect
      .poll(async () => {
        const value = Number.parseFloat(
          await page.getByTestId("dro-x").innerText(),
        );
        return (
          Number.isFinite(value) &&
          (distinctFromX === undefined ||
            Math.abs(value - distinctFromX) > 1e-9)
        );
      })
      .toBe(true);
    return {
      x: Number.parseFloat(await page.getByTestId("dro-x").innerText()),
      y: Number.parseFloat(await page.getByTestId("dro-y").innerText()),
    };
  };
  const p1 = await read(s1.x, s1.y);
  const p2 = await read(s2.x, s2.y, p1.x);
  await page.keyboard.press("g"); // snap back on for drawing
  const kx = (s2.x - s1.x) / (p2.x - p1.x);
  const ky = (s2.y - s1.y) / (p2.y - p1.y);
  return (pt) => ({
    x: s1.x + (pt.x - p1.x) * kx,
    y: s1.y + (pt.y - p1.y) * ky,
  });
}

async function clickPlane(
  page: Page,
  at: (pt: { x: number; y: number }) => { x: number; y: number },
  pt: { x: number; y: number },
) {
  const px = at(pt);
  await page.mouse.click(px.x, px.y);
}

/** Draw the rectangle + diagonal, toggle the diagonal to construction. */
async function drawWithConstructionDiagonal(
  page: Page,
  at: (pt: { x: number; y: number }) => { x: number; y: number },
) {
  // Rectangle (0,0)→(40,25): four CCW lines e1–e4.
  await page.keyboard.press("r");
  await clickPlane(page, at, { x: 0, y: 0 });
  await clickPlane(page, at, { x: 40, y: 25 });
  await expect(page.getByTestId("sketch-save")).toContainText("4 entities");

  // A diagonal line across it: e5.
  await page.keyboard.press("l");
  await clickPlane(page, at, { x: 0, y: 0 });
  await clickPlane(page, at, { x: 40, y: 25 });
  await expect(page.getByTestId("sketch-save")).toContainText("5 entities");
  await page.keyboard.press("Escape"); // back to the select tool

  // Select the diagonal at its midpoint (clear of every rectangle edge).
  await clickPlane(page, at, { x: 20, y: 12.5 });
  await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
  // Not construction yet — the toggle cell reads unpressed.
  await expect(page.getByTestId("sketch-construction")).toHaveAttribute(
    "aria-pressed",
    "false",
  );

  // N toggles it to construction; the verb clears the selection so the
  // diagonal reads in its dashed construction ink.
  await page.keyboard.press("n");
  await expect(page.getByTestId("selection-readout")).toContainText(
    "nothing selected",
  );

  // Re-select it: the toggle cell now reads pressed (it IS construction).
  await clickPlane(page, at, { x: 20, y: 12.5 });
  await expect(page.getByTestId("sketch-construction")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.keyboard.press("Escape"); // drop the selection
}

test.describe("construction geometry", () => {
  test("toggle a diagonal to construction; extrude uses the rectangle, flag persists", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Bracket plate");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    await drawWithConstructionDiagonal(page, at);

    // Save the sketch through the real gateway; capture the feature id.
    const featurePromise = page.waitForResponse(
      (r) =>
        r.url().includes(`/parts/${part.id}/features`) &&
        r.request().method() === "POST",
    );
    await page.getByTestId("sketch-save").click();
    const featureResponse = await featurePromise;
    expect(featureResponse.status()).toBe(201);
    const sketchId = (
      (await featureResponse.json()) as { feature: { id: string } }
    ).feature.id;

    await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
    await expect(page.getByTestId("feature-row")).toContainText("Sketch1");
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    // The persisted sketch: five entities, only the diagonal is construction.
    const readConstruction = async (): Promise<Map<string, boolean>> => {
      const treeResponse = await page.request.get(
        `/api/v1/parts/${part.id}/features`,
        { headers: { Authorization: `Bearer ${account.token}` } },
      );
      const treeBody = (await treeResponse.json()) as {
        tree_version: number;
        features: Array<{
          feature: { params: { entities: SketchEntityRow[] } };
        }>;
      };
      const entities = treeBody.features[0]?.feature.params.entities ?? [];
      return new Map(entities.map((e) => [e.id, e.construction ?? false]));
    };
    {
      const flags = await readConstruction();
      expect(flags.size).toBe(5);
      expect(flags.get("e5")).toBe(true); // the diagonal
      expect([...flags.entries()].filter(([, c]) => c)).toHaveLength(1);
      expect(flags.get("e1")).toBe(false); // a rectangle edge
    }

    // Extrude the sketch 10 mm. The kernel excludes construction geometry
    // from the profile, so the diagonal is ignored: a clean 40×25×10 solid.
    const treeVersionResponse = await page.request.get(
      `/api/v1/parts/${part.id}/features`,
      { headers: { Authorization: `Bearer ${account.token}` } },
    );
    const treeVersion = (
      (await treeVersionResponse.json()) as { tree_version: number }
    ).tree_version;
    const extrudeResponse = await page.request.post(
      `/api/v1/parts/${part.id}/features`,
      {
        data: {
          name: "Extrude1",
          feature: {
            type: "extrude",
            version: 1,
            params: {
              profile: { kind: "feature", feature_id: sketchId },
              distance_mm: 10,
              operation: "add",
              direction: "normal",
            },
          },
          expected_tree_version: treeVersion,
        },
        headers: { Authorization: `Bearer ${account.token}` },
      },
    );
    expect(extrudeResponse.status()).toBe(201);

    // Reload: the tree re-evaluates. The body renders with the rectangle's
    // volume — proof the diagonal was excluded from the profile.
    await page.reload();
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByTestId("prop-volume")).toContainText("10,000");
    await expect(page.getByTestId("prop-extents")).toContainText(
      "40 × 25 × 10",
    );
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
      .toBeGreaterThan(24);

    // The construction flag survived the round-trip.
    const flagsAfter = await readConstruction();
    expect(flagsAfter.get("e5")).toBe(true);
  });

  test("founder screenshot: construction diagonal (dashed) beside real geometry", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Bracket plate");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );
    await drawWithConstructionDiagonal(page, at);
    await page.mouse.move(1400, 900); // park the cursor off the sketch
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/construction-geometry-desktop.png`,
    });
  });
});

test.describe("construction geometry small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("toggle stays usable at laptop width; founder screenshot", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Bracket plate");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 640, y: 560 },
      { x: 940, y: 380 },
    );
    await drawWithConstructionDiagonal(page, at);

    const box = await page.getByTestId("viewport").boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(640);
    await page.mouse.move(1100, 700);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/construction-geometry-laptop.png`,
    });
  });
});
