import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * FB-15 + FB-16 — one interaction, driven end to end against the real stack.
 *
 * **FB-15, drag to draw.** Every tool was click-then-click. Press-drag-release
 * is what a hand trained on any other CAD does first, so it draws now — and
 * click-then-click still does, because it is the better gesture for precision
 * and the only sane one on touch.
 *
 * **FB-16, dimension while drawing.** Founder: *"usually dimensions are applied
 * automatically with text boxes."* The size cells appear ON the shape as it is
 * made, Tab walks them, Enter applies. That is the path the founder's very
 * first report was actually asking for; select-then-D is the fallback.
 *
 * The geometric assertions read the SOLVED evaluate payload, not the readout:
 * a typed 50 has to come back as a 50 mm edge from the solver, or the cells are
 * theatre.
 */

interface SolvedPoint {
  x: number;
  y: number;
}
interface SolvedEntity {
  id: string;
  kind: string;
  start?: SolvedPoint;
  end?: SolvedPoint;
  center?: SolvedPoint;
  radius?: number;
}
interface EvaluateBody {
  features: Array<{
    feature_id: string;
    status: string;
    data: {
      kind: string;
      status: string;
      dof: number | null;
      entities: SolvedEntity[];
    } | null;
  }>;
}

/** Collect every evaluate response body for the part, newest last. */
function collectEvaluations(page: Page, partId: string): EvaluateBody[] {
  const bodies: EvaluateBody[] = [];
  page.on("response", (response) => {
    if (
      response.url().includes(`/parts/${partId}/evaluate`) &&
      response.request().method() === "POST" &&
      response.status() === 200
    ) {
      void response
        .json()
        .then((body: EvaluateBody) => bodies.push(body))
        .catch(() => undefined);
    }
  });
  return bodies;
}

const lineLength = (entities: SolvedEntity[], id: string): number | null => {
  const line = entities.find((e) => e.id === id);
  if (line?.start === undefined || line.end === undefined) return null;
  return Math.hypot(line.end.x - line.start.x, line.end.y - line.start.y);
};

/** Open a fresh part and enter the sketcher on the XY datum. */
async function openSketchOnXy(
  page: Page,
  name: string,
): Promise<{ partId: string }> {
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, name);
  await page.goto(`/parts/${part.id}`);
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  return { partId: part.id };
}

/** Press, travel in steps, release — the gesture a hand actually makes. */
async function dragDraw(
  page: Page,
  a: [number, number],
  b: [number, number],
): Promise<void> {
  await page.mouse.move(a[0], a[1]);
  await page.mouse.down();
  await page.mouse.move(a[0] + (b[0] - a[0]) / 2, a[1] + (b[1] - a[1]) / 2);
  await page.mouse.move(b[0], b[1]);
  await page.mouse.up();
}

async function armRect(page: Page): Promise<void> {
  await page.keyboard.press("r");
  await expect(page.getByTestId("tool-rect")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
}

test.describe("FB-15 — press-drag-release draws, and two clicks still do", () => {
  test("a drag draws the rectangle, showing its size as it forms", async ({
    page,
  }) => {
    await openSketchOnXy(page, "Drag to draw");
    await armRect(page);

    // Mid-gesture: the shape is rubber-banding and its SIZE is on screen —
    // the DRO says where the cursor is, nothing said how big the thing was.
    await page.mouse.move(700, 420);
    await page.mouse.down();
    await page.mouse.move(900, 560);
    await page.mouse.move(1000, 640);
    const tag = page.getByTestId("draw-dimensions");
    await expect(tag).toHaveAttribute("data-state", "live");
    await page.mouse.up();

    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
    // The same numbers, in the same place, now take typing.
    await expect(tag).toHaveAttribute("data-state", "armed");
    await expect(page.getByTestId("draw-dimension-width")).toBeVisible();
    await expect(page.getByTestId("draw-dimension-height")).toBeVisible();
  });

  test("click-then-click still draws — the precision fallback survives", async ({
    page,
  }) => {
    await openSketchOnXy(page, "Two clicks");
    await armRect(page);
    await page.mouse.click(700, 420);
    // Nothing is committed after one click: the sequence is open, the size
    // cells are a readout only.
    await expect(page.getByTestId("sketch-save")).not.toContainText(
      "4 entities",
    );
    await page.mouse.move(1000, 640);
    await expect(page.getByTestId("draw-dimensions")).toHaveAttribute(
      "data-state",
      "live",
    );
    await page.mouse.click(1000, 640);
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
    await expect(page.getByTestId("draw-dimensions")).toHaveAttribute(
      "data-state",
      "armed",
    );
  });

  test("a drag with the select tool draws nothing — the camera keeps its gesture", async ({
    page,
  }) => {
    await openSketchOnXy(page, "Drag is not draw");
    // Select is the resting tool; a long drag across the plane must not
    // produce geometry, or orbiting would scribble on every sketch.
    await dragDraw(page, [700, 420], [1000, 640]);
    await expect(page.getByTestId("sketch-save")).toContainText("0 entities");
    await expect(page.getByTestId("draw-dimensions")).toHaveCount(0);
  });

  test("Escape mid-drag cancels the placement, not the sketch", async ({
    page,
  }) => {
    await openSketchOnXy(page, "Escape mid-drag");
    await armRect(page);
    await page.mouse.move(700, 420);
    await page.mouse.down();
    await page.mouse.move(1000, 640);
    await page.keyboard.press("Escape"); // the placement, one rung
    await page.mouse.up(); // …and the release must not resurrect it

    await expect(page.getByTestId("sketch-save")).toContainText("0 entities");
    await expect(page.getByTestId("draw-dimensions")).toHaveCount(0);
    // Still sketching, still on the plane — Escape unwound one level.
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  });
});

test.describe("FB-16 — the size is typed while you draw", () => {
  test("typed width and height drive the solved geometry", async ({ page }) => {
    const { partId } = await openSketchOnXy(page, "Typed size");
    const evaluations = collectEvaluations(page, partId);
    await armRect(page);
    await dragDraw(page, [700, 420], [1000, 640]);
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");

    // No click into the cell first: typing a digit anywhere starts the width.
    await page.keyboard.type("50");
    await expect(page.getByTestId("draw-dimension-width")).toHaveValue("50");
    await page.keyboard.press("Tab");
    await page.keyboard.type("30");
    await expect(page.getByTestId("draw-dimension-height")).toHaveValue("30");
    await page.keyboard.press("Enter");

    // The cells close, and the sketch carries its dimensions.
    await expect(page.getByTestId("draw-dimensions")).toHaveCount(0);
    await expect(page.getByTestId("selection-readout")).toContainText(
      "10 applied",
    );

    // The SOLVER agrees: bottom edge 50, right edge 30, still a rectangle.
    await expect
      .poll(
        () => {
          const solved = evaluations[evaluations.length - 1]?.features[0]?.data;
          if (solved === undefined || solved === null) return null;
          return lineLength(solved.entities, "e1");
        },
        { timeout: 30_000 },
      )
      .toBeCloseTo(50, 3);
    const solved = evaluations[evaluations.length - 1]?.features[0]?.data;
    expect(lineLength(solved?.entities ?? [], "e2")).toBeCloseTo(30, 3);
  });

  test("Tab walks the cells and wraps — a dimension pair is a loop", async ({
    page,
  }) => {
    await openSketchOnXy(page, "Tab order");
    await armRect(page);
    await dragDraw(page, [700, 420], [1000, 640]);
    await page.keyboard.press("Tab"); // into the first cell
    await expect(page.getByTestId("draw-dimension-width")).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByTestId("draw-dimension-height")).toBeFocused();
    await page.keyboard.press("Tab"); // wraps, never out of the viewport
    await expect(page.getByTestId("draw-dimension-width")).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(page.getByTestId("draw-dimension-height")).toBeFocused();
  });

  test("drawing without typing leaves an undimensioned rectangle, not a refusal", async ({
    page,
  }) => {
    await openSketchOnXy(page, "No size typed");
    await armRect(page);
    await dragDraw(page, [700, 420], [1000, 640]);
    await page.keyboard.press("Escape");

    // The shape is kept — Escape ends the command, it is not an undo.
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
    await expect(page.getByTestId("draw-dimensions")).toHaveCount(0);
    // RECT-1 — "undimensioned" is not "unconstrained". The draw authors the
    // rectangle's rigidity set (4 coincidences + 2 H + 2 V) whether or not a
    // size was typed, so the readout reports eight. What must still be absent
    // is a DIMENSION: nothing was typed, so nothing was measured, and the
    // glyph strip carries no number.
    await expect(page.getByTestId("selection-readout")).toContainText(
      "8 applied",
    );
    for (const i of [0, 1, 2, 3, 4, 5, 6, 7]) {
      await expect(page.getByTestId(`glyph-${i}`)).not.toHaveText(/[0-9]/);
    }
    await expect(page.getByTestId("glyph-8")).toHaveCount(0);
    // …and the same Escape dropped the tool, exactly as it did before.
    await expect(page.getByTestId("tool-rect")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  test("a circle is dimensioned by radius as it is dragged", async ({
    page,
  }) => {
    const { partId } = await openSketchOnXy(page, "Circle radius");
    const evaluations = collectEvaluations(page, partId);
    await page.keyboard.press("c");
    await dragDraw(page, [850, 520], [1000, 520]);
    await expect(page.getByTestId("sketch-save")).toContainText("1 entity");
    await expect(page.getByTestId("draw-dimension-radius")).toBeVisible();
    await page.keyboard.type("18");
    await page.keyboard.press("Enter");

    await expect
      .poll(
        () => {
          const solved = evaluations[evaluations.length - 1]?.features[0]?.data;
          return solved?.entities.find((e) => e.id === "e1")?.radius ?? null;
        },
        { timeout: 30_000 },
      )
      .toBeCloseTo(18, 3);
  });
});

/**
 * Founder shots. The BEFORE pair is captured from the same script run against
 * the pre-change tree (a throwaway worktree at the parent commit), so the two
 * frames differ only by the feature: same part, same plane, same corners.
 */
for (const size of [
  { label: "1600", width: 1600, height: 1000, a: [700, 420], b: [1000, 640] },
  { label: "1280", width: 1280, height: 800, a: [560, 340], b: [880, 560] },
] as const) {
  test(`founder shot ${size.label}: size forming under the drag, then typed`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: size.width, height: size.height });
    await openSketchOnXy(page, `Founder ${size.label}`);
    await armRect(page);

    // 1 — mid-gesture: the rectangle is rubber-banding under a held button and
    //     its SIZE is on screen as it forms.
    await page.mouse.move(size.a[0], size.a[1]);
    await page.mouse.down();
    await page.mouse.move(
      (size.a[0] + size.b[0]) / 2,
      (size.a[1] + size.b[1]) / 2,
    );
    await page.mouse.move(size.b[0], size.b[1]);
    await expect(page.getByTestId("draw-dimensions")).toHaveAttribute(
      "data-state",
      "live",
    );
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-drag-draw-after-${size.label}.png`,
    });

    // 2 — released and typed: the same numbers, now driving the geometry, with
    //     the focused cell's dimension called out on the edge it drives.
    await page.mouse.up();
    await page.keyboard.type("60");
    await page.keyboard.press("Tab");
    await page.keyboard.type("40");
    await expect(page.getByTestId("draw-dimension-height")).toHaveValue("40");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-draw-dimensions-after-${size.label}.png`,
    });
  });
}
