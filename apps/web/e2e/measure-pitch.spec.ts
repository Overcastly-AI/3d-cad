/**
 * MEASURE-LABEL-PITCH-1 — two picked holes read their PITCH, labelled as such.
 *
 * `docs/AUDIT-PRODUCT.md` F-7 (2026-09-16): picking two adjacent Ø8 holes whose
 * centre-to-centre pitch is 25 mm by construction read back `DISTANCE 17 mm`
 * (25 - 8, the minimum rim-to-rim distance), with no word saying "minimum", no
 * centre-to-centre reading, and edge labels (`Edge 5, circle`) that could not
 * say WHICH two holes had been measured. Hole pitch is the most common
 * measurement taken on a plate; an engineer acts on that 17 and gets it wrong.
 *
 * The fixture is the audit's case with a deliberately diagonal pitch: two Ø8
 * through-holes at (-12, -3.5) and (12, 3.5) on a 6 mm plate, so the pitch is
 * hypot(24, 7) = 25 exactly and every delta is non-trivial. The EXPECTED
 * numbers are derived here from the drawn sketch parameters, never read back
 * from the overlay or the readout, so the check cannot be self-consistent with
 * a wrong implementation (CLAUDE.md "Derive the EXPECTED set independently").
 *
 * Both picks are REAL pointer clicks at the mark's own centre, after proving
 * `elementFromPoint` resolves to the mark — never `dispatchEvent` or `force`.
 */
import { expect, test, type Page } from "./fixtures";

import { createFeature } from "./partSeed";
import {
  createPartViaApi,
  distinctCanvasColors,
  expectSeatsSettled,
  SCREENSHOT_DIR,
  seedSession,
  waitForFrames,
} from "./support";

interface Vec3 {
  x: number;
  y: number;
  z: number;
}

interface OverlayEdgeJson {
  kind: string;
  polyline: Vec3[];
  signature: { curve: string };
}

/** The drawn geometry — the single source of every expected number below. */
const PLATE_THICKNESS = 6;
const HOLE_DIAMETER = 8;
const HOLE_A = { x: -12, y: -3.5 };
const HOLE_B = { x: 12, y: 3.5 };
const PITCH = Math.hypot(HOLE_B.x - HOLE_A.x, HOLE_B.y - HOLE_A.y); // 25
const MINIMUM = PITCH - HOLE_DIAMETER; // 17 — two equal radii off the pitch

async function seedTwoHolePlate(
  page: Page,
  token: string,
  partId: string,
): Promise<void> {
  const line = (
    id: string,
    sx: number,
    sy: number,
    ex: number,
    ey: number,
  ) => ({
    id,
    kind: "line",
    start: { x: sx, y: sy },
    end: { x: ex, y: ey },
  });
  const outline = await createFeature(page, token, partId, {
    name: "Outline",
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "datum_plane", plane: "XY" },
        entities: [
          line("b", -30, -15, 30, -15),
          line("r", 30, -15, 30, 15),
          line("t", 30, 15, -30, 15),
          line("l", -30, 15, -30, -15),
        ],
        constraints: [],
      },
    },
    expected_tree_version: 0,
  });
  const plate = await createFeature(page, token, partId, {
    name: "Plate",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: outline.feature.id },
        distance_mm: PLATE_THICKNESS,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: outline.tree_version,
  });
  const holes = await createFeature(page, token, partId, {
    name: "Holes",
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "datum_plane", plane: "XY" },
        entities: [
          {
            id: "ha",
            kind: "circle",
            center: HOLE_A,
            radius: HOLE_DIAMETER / 2,
          },
          {
            id: "hb",
            kind: "circle",
            center: HOLE_B,
            radius: HOLE_DIAMETER / 2,
          },
        ],
        constraints: [],
      },
    },
    expected_tree_version: plate.tree_version,
  });
  await createFeature(page, token, partId, {
    name: "Through",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: holes.feature.id },
        distance_mm: PLATE_THICKNESS,
        operation: "cut",
        direction: "normal",
      },
    },
    expected_tree_version: holes.tree_version,
  });
}

/**
 * The overlay index of a hole's TOP rim, located by the spec's own geometry:
 * a circle-curve edge every sample of which sits on the top face at the hole's
 * drawn radius from its drawn centre. Identification only — no expected value
 * is read from here.
 */
function topRimIndex(
  edges: OverlayEdgeJson[],
  centre: { x: number; y: number },
): number {
  const matches = edges.flatMap((edge, index) => {
    if (edge.signature.curve !== "circle") return [];
    const onRim = edge.polyline.every(
      (p) =>
        Math.abs(p.z - PLATE_THICKNESS) < 1e-6 &&
        Math.abs(
          Math.hypot(p.x - centre.x, p.y - centre.y) - HOLE_DIAMETER / 2,
        ) < 1e-6,
    );
    return onRim ? [index] : [];
  });
  expect(
    matches,
    `exactly one top rim at ${JSON.stringify(centre)}`,
  ).toHaveLength(1);
  return matches[0] as number;
}

/** A REAL click at the mark's own centre, after proving the mark is on top. */
async function pickMark(page: Page, testid: string): Promise<void> {
  const mark = page.getByTestId(testid);
  await expect(mark).toHaveAttribute("data-buried", "false");
  const probe = await mark.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const cx = (r.left + r.right) / 2;
    const cy = (r.top + r.bottom) / 2;
    const hit = document.elementFromPoint(cx, cy);
    return {
      cx,
      cy,
      area: r.width * r.height,
      self: hit !== null && (hit === el || el.contains(hit)),
    };
  });
  expect(probe.area, `${testid} has a real hit box`).toBeGreaterThan(0);
  expect(probe.self, `${testid}'s own centre reaches ${testid}`).toBe(true);
  await page.mouse.click(probe.cx, probe.cy);
}

/** One readout cell: its visible eyebrow names the value it groups. */
function cell(page: Page, name: string) {
  return page
    .getByTestId("measure-readout")
    .getByRole("group", { name, exact: true });
}

async function measureTwoHoles(page: Page): Promise<{
  kernelDistance: number;
}> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Two-hole plate");
  await seedTwoHolePlate(page, account.token, part.id);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 60_000,
  });
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
    .toBeGreaterThan(16);

  const overlayResponse = page.waitForResponse(
    (r) =>
      r.url().includes("/api/v1/geometry/overlay") &&
      r.request().method() === "POST",
  );
  await page.getByTestId("measure-tool").click();
  const overlay = (await (await overlayResponse).json()) as {
    edges: OverlayEdgeJson[];
  };
  const rimA = topRimIndex(overlay.edges, HOLE_A);
  const rimB = topRimIndex(overlay.edges, HOLE_B);
  await expect(page.getByTestId(`measure-edge-${rimA}`)).toBeAttached({
    timeout: 20_000,
  });
  // Named settle: the edge marks seat over a per-frame budget, so a mark read
  // mid-pass sits wherever the pass had got to.
  await expectSeatsSettled(page, "measure marks");
  await waitForFrames(page, 4);

  const prompt = page.getByTestId("measure-prompt");
  await pickMark(page, `measure-edge-${rimA}`);
  await expect(prompt).toContainText("Pick the second point or edge");

  const measureResponse = page.waitForResponse(
    (r) =>
      r.url().includes("/api/v1/geometry/measure") &&
      r.request().method() === "POST",
  );
  await pickMark(page, `measure-edge-${rimB}`);
  const response = await measureResponse;
  expect(response.status()).toBe(200);
  const body = (await response.json()) as { distance: number };

  // The kernel's reading is the MINIMUM (rim to rim) — pinned here so the
  // label under test is checked against what the number actually is.
  expect(Math.abs(body.distance - MINIMUM)).toBeLessThan(1e-6);
  await expect(page.getByTestId("measure-readout-distance")).toHaveText(
    `${MINIMUM} mm`,
  );
  await waitForFrames(page, 4);
  return { kernelDistance: body.distance };
}

async function expectPitchReading(page: Page): Promise<void> {
  // THE HEADLINE: a centre-to-centre reading, labelled as such, equal to the
  // drawn pitch at display precision (formatLength: 4 fraction digits).
  const centre = cell(page, "Centre to centre");
  await expect(centre).toBeVisible();
  await expect(centre.getByTestId("measure-readout-centre")).toHaveText(
    `${PITCH} mm`,
  );

  // Its components are the centre offsets, B - A, from the drawn centres.
  await expect(page.getByTestId("measure-readout-dx")).toHaveText(
    `${HOLE_B.x - HOLE_A.x} mm`,
  );
  await expect(page.getByTestId("measure-readout-dy")).toHaveText(
    `${HOLE_B.y - HOLE_A.y} mm`,
  );
  await expect(page.getByTestId("measure-readout-dz")).toHaveText("0 mm");

  // The raw kernel reading stays, DISTINCT and labelled as the minimum — never
  // a bare "Distance" beside two circles.
  const minimum = cell(page, "Min distance");
  await expect(minimum.getByTestId("measure-readout-distance")).toHaveText(
    `${MINIMUM} mm`,
  );
  await expect(
    page.getByTestId("measure-readout").getByRole("group", {
      name: "Distance",
      exact: true,
    }),
  ).toHaveCount(0);

  // IDENTITY: the readout alone says which two holes were measured — diameter
  // and centre of each, in pick order.
  const targets = page.getByTestId("measure-targets");
  await expect(targets.getByTestId("measure-target-a")).toContainText(
    `Ø${HOLE_DIAMETER} circle`,
  );
  await expect(targets.getByTestId("measure-target-a")).toContainText(
    `centre ${HOLE_A.x}, ${HOLE_A.y}, ${PLATE_THICKNESS} mm`,
  );
  await expect(targets.getByTestId("measure-target-b")).toContainText(
    `Ø${HOLE_DIAMETER} circle`,
  );
  await expect(targets.getByTestId("measure-target-b")).toContainText(
    `centre ${HOLE_B.x}, ${HOLE_B.y}, ${PLATE_THICKNESS} mm`,
  );
}

test.describe("MEASURE-LABEL-PITCH-1 — two holes read their pitch", () => {
  test("desktop 1440x900: centre-to-centre, labelled, beside the minimum", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    await page.setViewportSize({ width: 1440, height: 900 });
    await measureTwoHoles(page);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/measure-pitch-after-1440x900.png`,
    });
    await expectPitchReading(page);
  });

  test("small laptop 1280x800: the same reading fits the frame", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    await page.setViewportSize({ width: 1280, height: 800 });
    await measureTwoHoles(page);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/measure-pitch-after-1280x800.png`,
    });
    await expectPitchReading(page);

    // The readout must sit wholly inside the viewport at this width.
    const readout = await page.getByTestId("measure-readout").boundingBox();
    const viewport = await page.getByTestId("viewport").boundingBox();
    expect(readout).not.toBeNull();
    expect(viewport).not.toBeNull();
    const r = readout as NonNullable<typeof readout>;
    const v = viewport as NonNullable<typeof viewport>;
    expect(r.x).toBeGreaterThanOrEqual(v.x);
    expect(r.x + r.width).toBeLessThanOrEqual(v.x + v.width);
  });
});
