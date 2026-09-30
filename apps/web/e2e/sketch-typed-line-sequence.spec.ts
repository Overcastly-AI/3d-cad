import { expect, test, type Page } from "./fixtures";

import { enterSketch } from "./planeMap";
import { createPartViaApi, seedSession } from "./support";

/**
 * TYPED-COORD-HIJACK (REFERENCE-RUN 2026-09-30, found modelling the helical
 * gear's keyway): typing the coordinates of consecutive lines silently resizes
 * the line before.
 *
 * With the Line tool live, `10 Tab 0 Enter`, `10 Tab 20 Enter` draws the line
 * (10,0)-(10,20) exactly (G2 typed placement). The line tool does not chain,
 * so the engineer types the next line's first point, `-10 Tab 20 Enter`. But
 * the finished line has just armed its draw-time length cell (FB-16), and a
 * digit focuses that cell: the keystrokes meant for the next point become the
 * previous line's LENGTH. Measured on 9767a90: the stored line is
 * (10,0)-(10,1020), a 1020 mm line nobody asked for, and the next line is
 * never drawn. Nothing on screen says so until the user zooms out.
 *
 * The invariant is plain: typed coordinates never change a committed line.
 *
 * `test.fail()` marks the defect as KNOWN so the suite stays green; the fix
 * flips this to a plain `test` (Playwright then fails the run if the fix is
 * real and the marker is left behind).
 */

interface PersistedEntity {
  kind: string;
  start?: { x: number; y: number };
  end?: { x: number; y: number };
}

/** One key at a time, as a hand types a number it already knows. */
async function typePoint(page: Page, x: string, y: string): Promise<void> {
  for (const key of x) await page.keyboard.press(key);
  await page.keyboard.press("Tab");
  for (const key of y) await page.keyboard.press(key);
  await page.keyboard.press("Enter");
}

test.use({ viewport: { width: 1280, height: 800 } });

test("typed coordinates for the next line never resize the line before", async ({
  page,
}) => {
  test.fail(true, "TYPED-COORD-HIJACK: remove when the fix lands");
  test.setTimeout(120_000);
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, "Typed line sequence");
  await page.goto(`/parts/${part.id}`);
  await enterSketch(page, "XY");
  await page.keyboard.press("l");
  await page.mouse.move(1000, 250);

  // Two lines of a keyway-style profile, every point typed.
  await typePoint(page, "10", "0");
  await expect(page.getByTestId("point-entry")).toHaveCount(0);
  await typePoint(page, "10", "20");
  await expect(page.getByTestId("point-entry")).toHaveCount(0);
  // What the engineer sees before typing on: the line is drawn and its length
  // cell has armed. Waiting for it makes the hijack deterministic.
  await expect(page.getByTestId("draw-dimensions")).toHaveAttribute(
    "data-state",
    "armed",
  );
  await typePoint(page, "-10", "20");
  await typePoint(page, "-10", "0");
  await page.keyboard.press("Escape");
  await page.keyboard.press("Escape");

  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
  const response = await page.request.get(`/api/v1/parts/${part.id}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const body = (await response.json()) as {
    features: Array<{ feature: { params: { entities: PersistedEntity[] } } }>;
  };
  const lines = (body.features[0]?.feature.params.entities ?? []).filter(
    (e) => e.kind === "line",
  );

  // The first line is exactly what was typed, and the second line exists.
  expect(lines[0]?.start, JSON.stringify(lines)).toEqual({ x: 10, y: 0 });
  expect(lines[0]?.end, JSON.stringify(lines)).toEqual({ x: 10, y: 20 });
  expect(lines, JSON.stringify(lines)).toHaveLength(2);
  expect(lines[1]?.start).toEqual({ x: -10, y: 20 });
  expect(lines[1]?.end).toEqual({ x: -10, y: 0 });
});
