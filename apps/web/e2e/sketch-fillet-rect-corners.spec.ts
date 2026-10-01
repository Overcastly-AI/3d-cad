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
 *
 * SKETCH-ENDPOINT-TANGENT (review of c6475cf): the fillet's joins were plain
 * coincidents, so editing R afterwards left the arc off tangent — R5 -> R10
 * on a 40 x 25 rectangle put the centre 9.114 mm from both legs, a kink in the
 * extrude, with no warning. The joins are endpoint tangents now; the second
 * test edits R after the fillets and checks the extrude against the analytic
 * rounded-rectangle volume.
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

/** A typed 80 x 50 rectangle with its top-right then bottom-right corners rounded R5. */
async function filletedRectangle(page: Page) {
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
  return { token, part };
}

/** Leave the sketch and read back what was persisted. */
async function saveAndRead(page: Page, token: string, partId: string) {
  await page.keyboard.press("Escape");
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
  const response = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const body = (await response.json()) as {
    tree_version: number;
    features: Array<{
      id: string;
      feature: { params: { entities: PersistedEntity[] } };
    }>;
  };
  const sketch = body.features[0];
  const drawn = (sketch?.feature.params.entities ?? []).filter(
    (e) => e.construction !== true,
  );
  return { drawn, sketchId: sketch?.id ?? "", treeVersion: body.tree_version };
}

test("a second sketch fillet keeps the first corner's trims", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const { token, part } = await filletedRectangle(page);
  const { drawn } = await saveAndRead(page, token, part.id);
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

test("editing R after the fillets keeps them tangent; the extrude is the rounded rectangle", async ({
  page,
}) => {
  test.setTimeout(150_000);
  const { token, part } = await filletedRectangle(page);
  // Edit the FIRST fillet's radius, R5 -> R10, on its glyph, as a user does.
  const radii = page.locator('[data-testid^="glyph-"][data-kind="radius"]');
  await expect(radii).toHaveCount(2);
  await page.keyboard.press("Escape"); // leave Fillet: the glyphs take clicks
  await radii.first().click();
  const input = page.getByTestId("dimension-input");
  await expect(input).toBeVisible();
  await input.fill("10");
  await input.press("Enter");
  await expect(radii.filter({ hasText: /^R10$/ })).toHaveCount(1);
  await expect(page.getByTestId("dro-solve")).not.toHaveText(/SOLVING/);
  await page.waitForTimeout(1500);
  // The edit solves cleanly: the endpoint tangents are not redundant.
  await expect(page.getByTestId("dro-solve")).not.toHaveText(/OVER|CONFLICT/i);
  const { sketchId, treeVersion } = await saveAndRead(page, token, part.id);

  // Extrude 10 mm; the evaluation re-solves the sketch (the persisted
  // coordinates are only its starting guess) and reports the kernel's volume.
  const extrude = await page.request.post(`/api/v1/parts/${part.id}/features`, {
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
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(extrude.status(), await extrude.text()).toBe(201);
  const evaluated = await page.request.post(
    `/api/v1/parts/${part.id}/evaluate`,
    { data: {}, headers: { Authorization: `Bearer ${token}` } },
  );
  expect(evaluated.ok(), await evaluated.text()).toBe(true);
  const body = (await evaluated.json()) as {
    features: Array<{
      status: string;
      data?: { entities?: PersistedEntity[] };
    }>;
    properties: { volume: number } | null;
  };
  expect(body.features.map((f) => f.status)).toEqual(["ok", "ok"]);
  const solved = (body.features[0]?.data?.entities ?? []).filter(
    (e) => e.construction !== true,
  );
  const dump = JSON.stringify(solved);
  const lines = solved.filter((e) => e.kind === "line");
  const arcs = solved.filter((e) => e.kind === "arc");
  expect(arcs, dump).toHaveLength(2);
  // The outline: two vertical and two horizontal legs.
  const xs = lines
    .filter((l) => Math.abs((l.start as Pt).x - (l.end as Pt).x) < 1e-9)
    .map((l) => (l.start as Pt).x);
  const ys = lines
    .filter((l) => Math.abs((l.start as Pt).y - (l.end as Pt).y) < 1e-9)
    .map((l) => (l.start as Pt).y);
  expect(xs, dump).toHaveLength(2);
  expect(ys, dump).toHaveLength(2);
  const [left, right] = [Math.min(...xs), Math.max(...xs)];
  const [bottom, top] = [Math.min(...ys), Math.max(...ys)];
  // Every arc is TANGENT to both legs it joins: its centre sits r inside the
  // right leg and r inside the top or bottom leg. Before the fix the edited
  // arc's centre sat 9.1 mm from legs it should have been 10 mm from.
  const radiusOf = (a: PersistedEntity) =>
    Math.hypot(
      (a.start as Pt).x - (a.center as Pt).x,
      (a.start as Pt).y - (a.center as Pt).y,
    );
  const rs = arcs.map(radiusOf).sort((a, b) => a - b);
  expect(rs[0], dump).toBeCloseTo(R, 6);
  expect(rs[1], dump).toBeCloseTo(10, 6);
  for (const arc of arcs) {
    const r = radiusOf(arc);
    const c = arc.center as Pt;
    expect(right - c.x, dump).toBeCloseTo(r, 6);
    const toEdge = c.y > (top + bottom) / 2 ? top - c.y : c.y - bottom;
    expect(toEdge, dump).toBeCloseTo(r, 6);
  }
  // A rounded corner of radius r removes r^2 (1 - pi/4) from the rectangle.
  const corner = (r: number) => r * r * (1 - Math.PI / 4);
  const area = (right - left) * (top - bottom) - corner(R) - corner(10);
  expect(body.properties?.volume ?? NaN, dump).toBeCloseTo(area * 10, 4);
});
