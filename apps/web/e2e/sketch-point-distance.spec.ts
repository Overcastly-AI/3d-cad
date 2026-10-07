import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * SKETCH-POINT-DISTANCE — the QA rerun's inset lip, dimensioned the way an
 * engineer does it in Fusion 360: a pocket held 1 mm inside a rim by two
 * point-to-line dimensions, its width by a two-point dimension whose label is
 * dropped BELOW the pair (so it is horizontal), then the rim's width edited.
 *
 * The edit shrinks the rim PAST the pocket's corner (60 -> 50 with the corner
 * at x = 59). planegcs's own point-to-line distance is unsigned and would
 * settle the corner 1 mm OUTSIDE the rim; the solver holds the drawn side, so
 * the corner lands at 49. Every number is read from the SOLVED sketch the
 * evaluate call returns, never from a label.
 */

const TOL_MM = 1e-3;

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

/** The latest solved sketch's point `end` of `id`, or null before a solve. */
function solved(
  evaluations: EvaluateBody[],
  id: string,
  end: "start" | "end",
): SolvedPoint | null {
  const sketch = evaluations[evaluations.length - 1]?.features[0]?.data;
  return sketch?.entities.find((e) => e.id === id)?.[end] ?? null;
}

async function enterSketch(page: Page) {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
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

test.describe("point dimensions (desktop 1440)", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("a pocket inset 1 mm from a rim holds 1 mm when the rim is edited", async ({
    page,
  }) => {
    // Six dimensions authored by mouse, each waiting on its own solve: ~40 s
    // on a quiet machine, so the default 60 s leaves no room for a busy one.
    test.setTimeout(120_000);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Inset lip");
    const evaluations = collectEvaluations(page, part.id);
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page);
    const at = await calibratePlane(
      page,
      { x: 520, y: 640 },
      { x: 940, y: 340 },
    );
    const click = async (pt: { x: number; y: number }) => {
      const px = at(pt);
      await page.mouse.click(px.x, px.y);
    };
    /**
     * Click wherever the latest solve put `id`'s `end`, once the sketch has
     * ADOPTED that solve: the pick marker under the pointer names a point, not
     * the rim edge 1 mm away (the response lands a frame before the store has
     * the geometry, and a click in that frame would take the edge).
     */
    const clickSolved = async (id: string, end: "start" | "end") => {
      await expect
        .poll(() => solved(evaluations, id, end), { timeout: 20_000 })
        .not.toBeNull();
      const where = at(solved(evaluations, id, end) ?? { x: 0, y: 0 });
      const marker = page.getByTestId("pick-marker");
      await expect
        .poll(
          async () => {
            await page.mouse.move(where.x + 3, where.y);
            await page.mouse.move(where.x, where.y);
            return marker.getAttribute("data-pick-kind");
          },
          { timeout: 20_000 },
        )
        .not.toBe("on-curve");
      await page.mouse.click(where.x, where.y);
    };
    const editor = page.getByTestId("dimension-editor");
    const typeValue = async (value: string) => {
      await expect(editor).toBeVisible();
      await page.getByTestId("dimension-input").pressSequentially(value);
      await page.getByTestId("dimension-input").press("Enter");
      await expect(editor).toHaveCount(0);
    };
    const settled = (check: () => boolean) =>
      expect.poll(check, { timeout: 20_000 }).toBe(true);

    // The rim, 60 x 40 at the origin (e1 bottom, e2 right, e3 top, e4 left),
    // and a 10 x 6 pocket drawn 5 mm inside its top-right corner (e5..e8).
    await page.keyboard.press("r");
    await click({ x: 0, y: 0 });
    await click({ x: 60, y: 40 });
    await page.keyboard.press("r");
    await click({ x: 45, y: 29 });
    await click({ x: 55, y: 35 });
    await page.keyboard.press("Escape");

    // The rim's own size: D, click an edge, type.
    await page.keyboard.press("d");
    await click({ x: 30, y: 0 });
    await typeValue("60");
    await page.keyboard.press("d");
    await click({ x: 0, y: 20 });
    await typeValue("40");

    // Point to line, twice: D, the pocket's corner, then the rim edge.
    await page.keyboard.press("d");
    await clickSolved("e6", "end");
    await expect(page.getByTestId("constraint-hint")).toHaveText(
      "Click a second point, or a line, to dimension to.",
    );
    await click({ x: 60, y: 10 });
    await expect(page.getByTestId("dimension-input")).toHaveValue("5");
    await typeValue("1");
    await settled(
      () => Math.abs((solved(evaluations, "e6", "end")?.x ?? 0) - 59) < TOL_MM,
    );
    await page.keyboard.press("d");
    await clickSolved("e6", "end");
    await click({ x: 10, y: 40 });
    await typeValue("1");
    await settled(
      () => Math.abs((solved(evaluations, "e6", "end")?.y ?? 0) - 39) < TOL_MM,
    );

    // Point to point, the label dropped BELOW the pair: horizontal.
    await page.keyboard.press("d");
    await clickSolved("e5", "start");
    await clickSolved("e5", "end");
    const bottomLeft = solved(evaluations, "e5", "start") as SolvedPoint;
    const bottomRight = solved(evaluations, "e5", "end") as SolvedPoint;
    const below = at({
      x: (bottomLeft.x + bottomRight.x) / 2,
      y: bottomLeft.y - 8,
    });
    await page.mouse.move(below.x, below.y);
    await expect(page.getByTestId("dimension-place")).toHaveAttribute(
      "data-direction",
      "horizontal",
    );
    await page.mouse.click(below.x, below.y);
    await typeValue("10");
    await settled(() => {
      const a = solved(evaluations, "e5", "start");
      const b = solved(evaluations, "e5", "end");
      return a !== null && b !== null && Math.abs(b.x - a.x - 10) < TOL_MM;
    });

    // Edit the rim's width 60 -> 50, past the pocket's corner at x = 59.
    const width = page
      .locator('[data-testid^="glyph-"][data-kind="distance"]')
      .filter({ hasText: /^60$/ });
    await width.click();
    await typeValue("50");
    await settled(() => {
      const rim = solved(evaluations, "e2", "start");
      const corner = solved(evaluations, "e6", "end");
      const left = solved(evaluations, "e5", "start");
      return (
        rim !== null &&
        corner !== null &&
        left !== null &&
        Math.abs(rim.x - 50) < TOL_MM &&
        Math.abs(corner.x - 49) < TOL_MM && // 1 mm INSIDE, not outside
        Math.abs(corner.y - 39) < TOL_MM &&
        Math.abs(corner.x - left.x - 10) < TOL_MM
      );
    });

    // Both inset glyphs still read 1, and the pocket width 10.
    const pointGlyphs = page.locator(
      '[data-testid^="glyph-"][data-kind="point_line_distance"]',
    );
    await expect(pointGlyphs).toHaveText(["1", "1"]);
    await expect(
      page.locator('[data-testid^="glyph-"][data-kind="point_distance"]'),
    ).toHaveText(["10"]);
    await page.mouse.move(1360, 840);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-point-distance-inset.png`,
    });
  });
});
