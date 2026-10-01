import { expect, test, type Page } from "./fixtures";

import {
  calibratePlane,
  clickPlane,
  enterSketch,
  type PlaneMapper,
} from "./planeMap";
import { createPartViaApi, seedSession } from "./support";

/**
 * SKETCH-FILLET-UNTRIM (HARD-PARTS run 2026-10-01, found on the enclosure's
 * lip sketch): round the corners of a rectangle whose size was typed as it
 * was drawn (so it carries W and H dimensions) one after another with the
 * sketch Fillet tool, as every engineer does for a rounded-rectangle profile.
 * The first fillet trims its two legs. Once the sketch re-solves, the trimmed
 * leg that holds the H dimension is pulled back to full length, so the SECOND
 * fillet, on the next corner, puts the first corner's trims back: the shared
 * leg runs to the sharp corner again, the first arc is left dangling, and the
 * sketch reads "open ends". Measured on ab31825 with a 118 x 78 rectangle and
 * r7: after the top-right then bottom-right fillets the right leg was
 * (59,-32)-(59,39) and the top leg (59,39)-(-59,39), so the profile no longer
 * closes and every feature built on it fails
 * (`hard-parts-2026-10-01/sketch-fillet-second-corner-untrims-first.png`).
 * Without the pause for the re-solve, or with a rectangle drawn by pointer
 * only (no dimensions), both corners come out right.
 *
 * Fusion and SolidWorks keep every earlier trim: N fillets on N corners give
 * a closed rounded rectangle.
 */

interface Pt {
  x: number;
  y: number;
}
interface PersistedEntity {
  id: string;
  kind: string;
  construction?: boolean;
  start?: Pt;
  end?: Pt;
  center?: Pt;
}

const HALF_W = 40;
const HALF_H = 25;
const R = 5;

async function filletCorner(page: Page, at: PlaneMapper, a: Pt, b: Pt) {
  await page.getByTestId("tool-fillet").click();
  await clickPlane(page, at, a);
  await clickPlane(page, at, b);
  await expect(page.getByTestId("corner-editor")).toBeVisible();
  // As typed by hand: select the cell's text, type the radius, Enter.
  await page.keyboard.press("Control+A");
  await page.keyboard.type(String(R));
  const done = page.waitForResponse(
    (r) =>
      r.url().includes("/geometry/sketch/fillet") &&
      r.request().method() === "POST",
  );
  await page.keyboard.press("Enter");
  expect((await done).status()).toBe(200);
  // Let the sketch re-solve before the next corner, as a person's pause does.
  await expect(page.getByTestId("dro-solve")).not.toHaveText(/SOLVING/);
  await page.waitForTimeout(1500);
}

test.use({ viewport: { width: 1280, height: 800 } });

test("a second sketch fillet keeps the first corner's trims", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, "Rounded rectangle");
  await page.goto(`/parts/${part.id}`);
  await enterSketch(page, "XY");
  const at = await calibratePlane(page, { x: 600, y: 300 }, { x: 800, y: 500 });

  await page.keyboard.press("r");
  await clickPlane(page, at, { x: -HALF_W, y: -HALF_H });
  await clickPlane(page, at, { x: HALF_W - 7, y: HALF_H - 4 });
  // Size typed as it is drawn (FB-16): the rectangle carries W and H dimensions.
  await expect(page.getByTestId("draw-dimension-width")).toBeVisible();
  await page.keyboard.type(String(2 * HALF_W));
  await page.keyboard.press("Tab");
  await page.keyboard.type(String(2 * HALF_H));
  await page.keyboard.press("Enter");
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("draw-dimensions")).toHaveCount(0);
  await expect(page.getByTestId("sketch-save")).toHaveAttribute(
    "aria-busy",
    "false",
  );

  // Top-right, then bottom-right: the right leg is shared by both corners.
  await filletCorner(page, at, { x: 0, y: HALF_H }, { x: HALF_W, y: 0 });
  await filletCorner(page, at, { x: 0, y: -HALF_H }, { x: HALF_W, y: 0 });
  // The re-homed corners solve cleanly: nothing reads redundant or in conflict.
  await expect(page.getByTestId("dro-solve")).not.toHaveText(/OVER|CONFLICT/i);

  await page.keyboard.press("Escape");
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
  const response = await page.request.get(`/api/v1/parts/${part.id}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const body = (await response.json()) as {
    features: Array<{ feature: { params: { entities: PersistedEntity[] } } }>;
  };
  const drawn = (body.features[0]?.feature.params.entities ?? []).filter(
    (e) => e.construction !== true,
  );
  const dump = JSON.stringify(drawn);
  expect(
    drawn.filter((e) => e.kind === "arc"),
    dump,
  ).toHaveLength(2);

  // No line may still reach either filleted corner.
  for (const corner of [
    { x: HALF_W, y: HALF_H },
    { x: HALF_W, y: -HALF_H },
  ]) {
    for (const line of drawn.filter((e) => e.kind === "line")) {
      for (const end of [line.start as Pt, line.end as Pt]) {
        expect(
          Math.hypot(end.x - corner.x, end.y - corner.y),
          dump,
        ).toBeGreaterThan(R - 0.01);
      }
    }
  }
  // And the profile closes: the part's first extrude can use it.
  await expect(page.getByTestId("eval-status")).toHaveText("Solved");
});
