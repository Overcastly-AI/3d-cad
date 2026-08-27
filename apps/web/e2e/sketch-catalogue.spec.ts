import { expect, test, type Page } from "./fixtures";

import { calibratePlane, clickPlane, enterSketch } from "./planeMap";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";
import type { PlaneMapper } from "./planeMap";

/**
 * SKETCH-VOCAB-1's remaining half — THE CATALOGUE.
 *
 * REACH-1 made the five late verbs authorable through the OFFER RAIL, and
 * `sketch-vocab.spec.ts` proves it: two lines surface "A angle", a circle
 * surfaces "D diameter", and each solves. That closed AUTHORABILITY and left
 * DISCOVERABILITY open, and the gap is structural rather than an oversight —
 * an offer can only appear once the selection ALREADY fits, so the rail can
 * propose a verb but can never teach you to reach one. Four verbs (angle,
 * diameter, collinear, midpoint) were consequently reachable only by pressing
 * a letter that nothing on screen named, and `midpoint` was the sharpest case:
 * bound to `m`, absent from every menu, invisible to anyone who had not read
 * the source.
 *
 * So this spec drives each verb from the CONSTRAINT FLYOUT, never from the
 * rail and never from the keyboard — the path a user takes when they do not
 * already know the answer — and asserts the SOLVED GEOMETRY the verb produced,
 * never the solver's status. It also pins the teaching state that has no
 * geometry at all: with nothing selected the rail is empty by construction, so
 * the catalogue's "needs …" line is the only thing in the product that can say
 * what to pick.
 *
 * NOTE ON PARITY: this spec deliberately does NOT move
 * `scripts/check-ui-parity.py`'s number, and should not. All five verbs already
 * count AUTHORABLE on REACH-1's spec. Reachability was the previous half of the
 * ticket; this half is about whether a user can FIND the thing that is reachable,
 * which no capability-literal count can see.
 */

const ANGLE_TOLERANCE_DEG = 0.01;
const COLLINEAR_TOLERANCE_MM = 1e-3;
const MIDPOINT_TOLERANCE_MM = 1e-3;
const DIAMETER_TOLERANCE_MM = 1e-3;

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

const solvedEntities = (bodies: EvaluateBody[]): SolvedEntity[] =>
  bodies[bodies.length - 1]?.features[0]?.data?.entities ?? [];

const entityById = (
  bodies: EvaluateBody[],
  id: string,
): SolvedEntity | undefined => solvedEntities(bodies).find((e) => e.id === id);

/** A solved line's direction, taken from `start` towards `end`. */
function direction(line: SolvedEntity | undefined): SolvedPoint | null {
  if (line?.start === undefined || line.end === undefined) return null;
  return { x: line.end.x - line.start.x, y: line.end.y - line.start.y };
}

/** Degrees between two solved lines' authored directions, unsigned. */
function angleBetween(
  bodies: EvaluateBody[],
  a: string,
  b: string,
): number | null {
  const u = direction(entityById(bodies, a));
  const v = direction(entityById(bodies, b));
  if (u === null || v === null) return null;
  const scale = Math.hypot(u.x, u.y) * Math.hypot(v.x, v.y);
  if (scale === 0) return null;
  const cos = Math.min(1, Math.max(-1, (u.x * v.x + u.y * v.y) / scale));
  return (Math.acos(cos) * 180) / Math.PI;
}

/** Perpendicular distance from `point` to the infinite line through `line`. */
function offLineDistance(
  line: SolvedEntity | undefined,
  point: SolvedPoint | undefined,
): number | null {
  if (line?.start === undefined || line.end === undefined) return null;
  if (point === undefined) return null;
  const dx = line.end.x - line.start.x;
  const dy = line.end.y - line.start.y;
  const length = Math.hypot(dx, dy);
  if (length === 0) return null;
  return (
    Math.abs(dx * (point.y - line.start.y) - dy * (point.x - line.start.x)) /
    length
  );
}

/** How far `point` sits from the midpoint of `line` — what `midpoint` zeroes. */
function offMidpointDistance(
  line: SolvedEntity | undefined,
  point: SolvedPoint | undefined,
): number | null {
  if (line?.start === undefined || line.end === undefined) return null;
  if (point === undefined) return null;
  return Math.hypot(
    point.x - (line.start.x + line.end.x) / 2,
    point.y - (line.start.y + line.end.y) / 2,
  );
}

/** Shift-click ADDS to the standing selection; a plain click replaces it. */
async function addPlane(
  page: Page,
  at: PlaneMapper,
  pt: { x: number; y: number },
) {
  await page.keyboard.down("Shift");
  await clickPlane(page, at, pt);
  await page.keyboard.up("Shift");
}

async function drawLine(
  page: Page,
  at: PlaneMapper,
  from: { x: number; y: number },
  to: { x: number; y: number },
) {
  await page.keyboard.press("l");
  await clickPlane(page, at, from);
  await clickPlane(page, at, to);
  await page.keyboard.press("Escape");
}

const glyphsOfKind = (page: Page, kind: string) =>
  page.locator(`[data-testid^="glyph-"][data-kind="${kind}"]`);

/**
 * Author a verb THE WAY SOMEONE WHO DOES NOT KNOW THE KEY WOULD: open the
 * family's flyout and click the row. This is the whole point of the spec — the
 * keyboard and the rail are both already covered by `sketch-vocab.spec.ts`, and
 * neither of them helps a user who has not yet learned the verb exists.
 */
async function applyFromCatalogue(
  page: Page,
  group: "geometric" | "dimensional" | "relational",
  action: string,
) {
  await page.getByTestId(`constraint-group-${group}`).click();
  const row = page.getByTestId(`constraint-${action}`);
  await expect(row).toBeVisible();
  await expect(row).toHaveAttribute("data-available", "true");
  await row.click();
}

test.describe("the catalogue is browsable and live (desktop 1440)", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("Midpoint centres a point on a line — clicked from the menu, not typed", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Midpoint rib");
    const evaluations = collectEvaluations(page, part.id);
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 640, y: 560 },
      { x: 940, y: 380 },
    );

    // A rail centred on the origin, and a boss whose centre starts well OFF
    // the rail's middle — 18.97 mm off, so the solve has real work to do and
    // the assertion below cannot pass vacuously. The boss's CENTRE is the
    // point pick: a circle centre is unambiguously a point, where a click near
    // a line's endpoint resolves to the line body as often as to its end.
    const BOSS_CENTRE = { x: 18, y: 6 };
    await drawLine(page, at, { x: -30, y: 0 }, { x: 30, y: 0 }); // e1
    await page.keyboard.press("c");
    await clickPlane(page, at, BOSS_CENTRE); // e2 centre
    await clickPlane(page, at, { x: 26, y: 6 }); // 8 mm radius
    await page.keyboard.press("Escape");

    // The boss's centre, then the rail. A point pick plus an entity pick.
    await clickPlane(page, at, BOSS_CENTRE);
    await addPlane(page, at, { x: -20, y: 0 });

    // THE AFFORDANCE UNDER TEST: Midpoint has a home in Relational now. Before
    // this it was bound to `m` and named nowhere — the one verb of the five
    // that even the offer rail could not rescue for a user who never made the
    // exact point+line selection that summons it.
    await applyFromCatalogue(page, "relational", "midpoint");

    // THE ACCEPTANCE: the solver puts the foot at the rail's middle.
    await expect(glyphsOfKind(page, "midpoint")).toHaveCount(1, {
      timeout: 15_000,
    });
    await expect
      .poll(
        () =>
          offMidpointDistance(
            entityById(evaluations, "e1"),
            entityById(evaluations, "e2")?.center,
          ),
        { timeout: 20_000 },
      )
      .toBeLessThan(MIDPOINT_TOLERANCE_MM);

    // …and the boss actually MOVED to get there. Satisfaction alone would be
    // reported by a solve that never ran on geometry drawn already-correct;
    // the displacement from where the user drew it is what proves the verb
    // did the work. (No "before" snapshot is possible here: nothing POSTs an
    // evaluate until the first constraint lands, so the pre-state exists only
    // as the coordinates the spec itself drew.)
    const centre = entityById(evaluations, "e2")?.center;
    expect(centre).toBeDefined();
    expect(
      Math.hypot(
        (centre?.x ?? 0) - BOSS_CENTRE.x,
        (centre?.y ?? 0) - BOSS_CENTRE.y,
      ),
    ).toBeGreaterThan(5);
  });

  test("Collinear closes a step — clicked from the Geometric menu", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Stepped flange");
    const evaluations = collectEvaluations(page, part.id);
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 640, y: 560 },
      { x: 940, y: 380 },
    );

    // Two segments with a 3 mm step between them — the thing Collinear closes.
    // The step is the non-vacuity: a solve that did nothing leaves e2 at y = 3,
    // which fails the tolerance below by three orders of magnitude. (Nothing
    // POSTs an evaluate until the first constraint lands, so the pre-state is
    // the coordinates this spec drew, not a snapshot it can read back.)
    const STEP_MM = 3;
    await drawLine(page, at, { x: -34, y: 0 }, { x: -6, y: 0 }); // e1
    await drawLine(page, at, { x: 6, y: STEP_MM }, { x: 34, y: STEP_MM }); // e2

    await clickPlane(page, at, { x: -20, y: 0 });
    await addPlane(page, at, { x: 20, y: STEP_MM });
    await applyFromCatalogue(page, "geometric", "collinear");

    await expect(glyphsOfKind(page, "collinear")).toHaveCount(1, {
      timeout: 15_000,
    });
    for (const end of ["start", "end"] as const) {
      await expect
        .poll(
          () =>
            offLineDistance(
              entityById(evaluations, "e1"),
              entityById(evaluations, "e2")?.[end],
            ),
          { timeout: 20_000 },
        )
        .toBeLessThan(COLLINEAR_TOLERANCE_MM);
    }
  });

  test("Angle drives a corner to 30 deg — chosen from the Dimension menu", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Menu gusset");
    const evaluations = collectEvaluations(page, part.id);
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 640, y: 560 },
      { x: 940, y: 380 },
    );

    // Two legs off a shared corner, neither axis-aligned (so the draw infers
    // no H/V that would fight the angle). They open at 53.13 deg as drawn, so
    // driving them to 30 is real motion, not a restatement.
    await drawLine(page, at, { x: 0, y: 0 }, { x: 30, y: 10 }); // e1, 18.43
    await drawLine(page, at, { x: 0, y: 0 }, { x: 10, y: 30 }); // e2, 71.57
    await clickPlane(page, at, { x: 24, y: 8 });
    await addPlane(page, at, { x: 8, y: 24 });
    await expect(page.getByTestId("selection-readout")).toContainText("2 ent");

    await applyFromCatalogue(page, "dimensional", "angle");

    const value = page.getByTestId("dimension-input");
    await expect(value).toBeVisible();
    await expect(page.getByTestId("dimension-editor")).toContainText("Angle");
    await value.fill("30");
    await page.getByTestId("dimension-apply").click();

    await expect(glyphsOfKind(page, "angle")).toHaveText(["30°"], {
      timeout: 15_000,
    });
    await expect
      .poll(() => angleBetween(evaluations, "e1", "e2"), { timeout: 20_000 })
      .toBeCloseTo(30, 2);
    expect(
      Math.abs((angleBetween(evaluations, "e1", "e2") ?? 0) - 30),
    ).toBeLessThan(ANGLE_TOLERANCE_DEG);
  });

  test("Diameter is a NAMED row, and drives the circle it is clicked on", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Bore plate");
    const evaluations = collectEvaluations(page, part.id);
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 640, y: 560 },
      { x: 940, y: 380 },
    );

    await page.keyboard.press("c");
    await clickPlane(page, at, { x: 0, y: 0 });
    await clickPlane(page, at, { x: 11, y: 0 });
    await page.keyboard.press("Escape");

    await clickPlane(page, at, { x: 11, y: 0 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");

    // D IS "DIMENSION" and the selection routes it — so diameter has no key of
    // its own and could not be discovered by pressing anything. The catalogue
    // row is the ONLY place the product says the verb exists by name.
    await applyFromCatalogue(page, "dimensional", "diameter");

    const value = page.getByTestId("dimension-input");
    await expect(value).toBeVisible();
    await value.fill("16");
    await page.getByTestId("dimension-apply").click();

    await expect(glyphsOfKind(page, "diameter")).toHaveText(["⌀16"], {
      timeout: 15_000,
    });
    await expect
      .poll(() => entityById(evaluations, "e1")?.radius, { timeout: 20_000 })
      .toBeCloseTo(8, 3);
    expect(
      Math.abs((entityById(evaluations, "e1")?.radius ?? 0) - 8),
    ).toBeLessThan(DIAMETER_TOLERANCE_MM);
  });

  /**
   * The teaching state, which has no geometry to assert and is the entire
   * reason the catalogue exists alongside the rail. With nothing selected the
   * rail is empty BY CONSTRUCTION (it only proposes verbs a fitting selection
   * unlocks), so these lines are the only thing in the running product that can
   * tell a user what to pick.
   */
  test("with nothing selected, every verb says what it needs", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Cold start");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 640, y: 560 },
      { x: 940, y: 380 },
    );
    await drawLine(page, at, { x: -20, y: 0 }, { x: 20, y: 0 });
    await page.keyboard.press("Escape");

    await expect(page.getByTestId("dimension-hint")).toHaveCount(0);

    await page.getByTestId("constraint-group-dimensional").click();
    const angle = page.getByTestId("constraint-angle");
    await expect(angle).toBeVisible();
    await expect(angle).toHaveAttribute("data-available", "false");
    await expect(angle).toHaveAccessibleName(/needs 2 non-parallel lines$/);
    // The row is CLICKABLE while unavailable, on purpose: refusing the click
    // would be the dead end this surface exists to remove. It answers with the
    // verb's own sentence instead.
    await angle.click();
    await expect(page.getByTestId("constraint-hint")).toContainText(
      /select two lines/i,
    );

    await page.getByTestId("constraint-group-relational").click();
    await expect(page.getByTestId("constraint-midpoint")).toHaveAccessibleName(
      /needs a point \+ a line$/,
    );
  });
});

/**
 * FOUNDER SCREENSHOT — the catalogue with one line selected, at the 1280 floor.
 *
 * Deliberately captured at the width the strip has historically failed at, and
 * with a selection that makes BOTH states visible in one frame: Distance and
 * Equal are live (brass glyph, no second line), while Angle and Diameter say
 * what they would need. Written only under UPDATE_SCREENSHOTS=1 (see
 * `e2e/fixtures.ts`), so a routine run exercises the render without dirtying
 * the tree.
 */
test.describe("founder screenshot — the live catalogue (small laptop 1280)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("the Dimension menu shows what is live and what each verb needs", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Catalogue shot");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 640, y: 560 },
      { x: 940, y: 380 },
    );
    await drawLine(page, at, { x: -24, y: -6 }, { x: 24, y: 10 });
    await clickPlane(page, at, { x: 0, y: 2 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");

    await page.getByTestId("constraint-group-dimensional").click();
    await expect(page.getByTestId("constraint-diameter")).toBeVisible();

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-catalogue-live-1280.png`,
    });
  });
});

/**
 * WIDTH — the QA-R1 failure mode, re-gated for the four rows this change adds.
 *
 * QA-R1: the strip ran to 1419.4 px in a 1280 px window and SAVE became
 * genuinely unclickable, with `scrollWidth === clientWidth` so nothing reported
 * an overflow — and `toBeVisible()` could not see it either, because visibility
 * is a box property and the box was fine. The only assertion that catches it is
 * a real HIT TEST: ask the document what is actually at the control's centre.
 *
 * The rows added here live INSIDE the flyout popovers, which are absolutely
 * positioned and cannot widen the strip. That is the expectation, not the
 * evidence — this test is the evidence, at both widths the band's label ladder
 * is tuned for.
 */
for (const width of [1280, 1366]) {
  test.describe(`the sketch strip stays clickable at ${width}`, () => {
    test.use({ viewport: { width, height: 800 } });

    test("SAVE, EXIT and every constraint group answer a real click", async ({
      page,
    }) => {
      const account = await seedSession(page);
      const part = await createPartViaApi(page, account.token, `Fit ${width}`);
      await page.goto(`/parts/${part.id}`);
      await enterSketch(page, "XY");
      const at = await calibratePlane(
        page,
        { x: width / 2, y: 560 },
        { x: width / 2 + 240, y: 380 },
      );
      // Two lines selected is the WORST case for the strip: it is the state
      // that fills the offer rail with three verbs, which is what pushed the
      // strip past the frame in QA-R1.
      await drawLine(page, at, { x: 0, y: 0 }, { x: 30, y: 10 });
      await drawLine(page, at, { x: 0, y: 0 }, { x: 10, y: 30 });
      await clickPlane(page, at, { x: 24, y: 8 });
      await addPlane(page, at, { x: 8, y: 24 });
      await expect(page.getByTestId("dimension-hint")).toBeVisible();

      const controls = [
        "constraint-group-geometric",
        "constraint-group-dimensional",
        "constraint-group-relational",
        "sketch-construction",
        "sketch-save",
      ];

      for (const id of controls) {
        const target = page.getByTestId(id);
        const box = await target.boundingBox();
        expect(box, `${id} has no box`).not.toBeNull();
        if (box === null) continue;

        // Inside the frame at all.
        expect(box.x, `${id} starts left of the frame`).toBeGreaterThanOrEqual(
          0,
        );
        expect(
          box.x + box.width,
          `${id} runs past the ${width}px frame`,
        ).toBeLessThanOrEqual(width);

        // THE HIT TEST. `toBeVisible()` passes for a control that is inside a
        // clipped overflow — the box exists, so visibility is satisfied — and
        // QA-R1 is precisely that case. Ask what the document would actually
        // deliver the click to.
        const cx = box.x + box.width / 2;
        const cy = box.y + box.height / 2;
        const hit = await page.evaluate(
          ([x, y, testid]) => {
            const el = document.elementFromPoint(x as number, y as number);
            return el?.closest(`[data-testid="${testid as string}"]`) !== null;
          },
          [cx, cy, id] as const,
        );
        expect(hit, `${id} is not what a click at its own centre reaches`).toBe(
          true,
        );
      }

      // And the catalogue rows themselves are reachable at this width — a menu
      // that opens off-frame would be the same defect one level down.
      await page.getByTestId("constraint-group-dimensional").click();
      for (const action of ["distance", "radius", "diameter", "angle"]) {
        const row = page.getByTestId(`constraint-${action}`);
        const box = await row.boundingBox();
        expect(box, `${action} row has no box`).not.toBeNull();
        if (box === null) continue;
        expect(
          box.x + box.width,
          `the ${action} row runs past the ${width}px frame`,
        ).toBeLessThanOrEqual(width);
        expect(
          box.y + box.height,
          `the ${action} row is below the fold`,
        ).toBeLessThanOrEqual(800);
      }
    });
  });
}
