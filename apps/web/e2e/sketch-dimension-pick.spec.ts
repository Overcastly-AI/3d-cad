import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * THE FOUNDER'S "I still cannot click dimension and actually have it assign a
 * dimension" (2026-08-14), reproduced and gated.
 *
 * It was never a wrong VALUE — it was a dead end. The dimension verbs were
 * selection-first only, and a draw tool stays armed after it draws (as it does
 * in Fusion), so the click a user makes to "select the line first" is consumed
 * as the next shape's first corner. Measured on the pre-fix build, mouse only:
 * draw a rectangle, click a side, Constrain > Dimension > Distance ->
 * selection readout "nothing selected", dimension editor count **0**, hint
 * "Select one line to dimension." — an instruction that cannot be carried out
 * from where it appears.
 *
 * The verb now ARMS when it has nothing to work with: the draw tool is
 * dropped, the next entity click opens that entity's editor, Escape disarms
 * (and must NOT exit the sketch). Both entry points are gated here — the
 * toolbar menu (mouse) and `D` (keyboard) — and the last assertion is the
 * founder's own words: the geometry actually moves to the typed value.
 */

const SOLVE_TOLERANCE_MM = 1e-3;

interface SolvedPoint {
  x: number;
  y: number;
}
interface SolvedEntity {
  id: string;
  kind: string;
  start?: SolvedPoint;
  end?: SolvedPoint;
}
interface EvaluateBody {
  features: Array<{
    data: { kind: string; status: string; entities: SolvedEntity[] } | null;
  }>;
}

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

function lineLength(entities: SolvedEntity[], id: string): number | null {
  const line = entities.find((e) => e.id === id);
  if (line?.start === undefined || line.end === undefined) return null;
  return Math.hypot(line.end.x - line.start.x, line.end.y - line.start.y);
}

async function enterSketch(page: Page, plane: "XY" | "XZ" | "YZ") {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId(`plane-${plane}`).click();
  await expect(page.getByTestId("sketch-step")).toHaveText(`On ${plane}`);
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
}

/** Plane-mm → screen-px mapper, read from the DRO with snap off. */
async function calibratePlane(
  page: Page,
  s1: { x: number; y: number },
  s2: { x: number; y: number },
): Promise<(pt: { x: number; y: number }) => { x: number; y: number }> {
  await page.keyboard.press("g");
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
  await page.keyboard.press("g");
  const kx = (s2.x - s1.x) / (p2.x - p1.x);
  const ky = (s2.y - s1.y) / (p2.y - p1.y);
  return (pt) => ({
    x: s1.x + (pt.x - p1.x) * kx,
    y: s1.y + (pt.y - p1.y) * ky,
  });
}

test.describe("dimension a just-drawn shape (desktop 1440)", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("the Dimension verb arms and takes the next click, mouse only", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Dim pick");
    const evaluations = collectEvaluations(page, part.id);
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 640, y: 560 },
      { x: 940, y: 380 },
    );

    // Draw a 43 x 27 rectangle with the toolbar, then leave everything exactly
    // as a user does: the Rectangle tool is STILL ARMED. e1 is the bottom edge.
    await page.getByTestId("tool-rect").click();
    await page.mouse.click(at({ x: 0, y: 0 }).x, at({ x: 0, y: 0 }).y);
    await page.mouse.move(at({ x: 43, y: 27 }).x, at({ x: 43, y: 27 }).y);
    await page.mouse.click(at({ x: 43, y: 27 }).x, at({ x: 43, y: 27 }).y);
    await expect(page.getByTestId("draw-dimensions")).toHaveAttribute(
      "data-state",
      "armed",
    );

    // THE FOUNDER'S GESTURE: reach straight for Dimension > Distance, with
    // nothing selected (and no way to select — the tool owns the clicks).
    await page.getByTestId("constraint-group-dimensional").click();
    await page.getByTestId("constraint-distance").click();

    // Armed, not refused. Pre-fix this read "Select one line to dimension."
    const hint = page.getByTestId("constraint-hint");
    await expect(hint).toHaveText("Click a line to dimension it.");
    await page.mouse.move(1360, 840);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/dimension-pick-armed-desktop.png`,
    });

    // The next click on a curve opens ITS editor. Pre-fix this click started
    // the next rectangle and the editor never appeared.
    const bottom = at({ x: 21, y: 0 });
    await page.mouse.click(bottom.x, bottom.y);
    const editor = page.getByTestId("dimension-editor");
    await expect(editor).toBeVisible();
    await page.mouse.move(1360, 840);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/dimension-pick-editor-desktop.png`,
    });

    const value = page.getByTestId("dimension-input");
    await expect(value).toHaveValue("43");
    await value.fill("60");
    await value.press("Enter");
    await expect(editor).toHaveCount(0);

    // "Actually have it assign a dimension": the glyph reads 60 AND the solver
    // moved the edge to 60 mm. A label without geometry would be the same bug
    // wearing a different mask.
    await expect(page.getByTestId("glyph-0")).toHaveText("60", {
      timeout: 15_000,
    });
    await expect
      .poll(
        () => {
          const sketch = evaluations[evaluations.length - 1]?.features[0];
          if (sketch?.data == null) return null;
          const length = lineLength(sketch.data.entities, "e1");
          return length === null
            ? null
            : Math.abs(length - 60) < SOLVE_TOLERANCE_MM;
        },
        { timeout: 20_000 },
      )
      .toBe(true);
  });

  test("D arms with nothing selected, and Escape disarms without exiting", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Dim key");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 640, y: 560 },
      { x: 940, y: 380 },
    );

    await page.keyboard.press("l");
    await page.mouse.click(at({ x: 0, y: 0 }).x, at({ x: 0, y: 0 }).y);
    await page.mouse.click(at({ x: 43, y: 0 }).x, at({ x: 43, y: 0 }).y);
    await expect(page.getByTestId("selection-readout")).toContainText(
      "nothing selected",
    );

    // D with an EMPTY selection used to resolve to nothing at all.
    await page.keyboard.press("d");
    const hint = page.getByTestId("constraint-hint");
    await expect(hint).toHaveText("Click a line to dimension it.");

    // Escape gives the click back — and must not take the sketch with it.
    await page.keyboard.press("Escape");
    await expect(hint).toHaveCount(0);
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY");

    // Re-arm and finish the job, to prove disarming left nothing broken.
    await page.keyboard.press("d");
    await expect(hint).toBeVisible();
    const mid = at({ x: 21, y: 0 });
    await page.mouse.click(mid.x, mid.y);
    await expect(page.getByTestId("dimension-editor")).toBeVisible();
    const value = page.getByTestId("dimension-input");
    await value.fill("25");
    await value.press("Enter");
    await expect(page.getByTestId("glyph-0")).toHaveText("25", {
      timeout: 15_000,
    });
  });
});
