import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * SKETCH-VOCAB-1, frontend half (REACH-1): the five constraint verbs that
 * shipped in the gateway contract with **no way for a user to reach them** —
 * `angle`, `collinear`, `symmetric_lines`, `diameter`, `midpoint`.
 *
 * This spec is the reachability ORACLE, not a unit test with a browser attached:
 * `scripts/check-ui-parity.py` reads the e2e suite to decide whether a capability
 * is reachable, so every constraint below is authored the way a user authors it
 * — draw with the mouse, select with the mouse, press the letter the offer rail
 * stamped, type the number. Nothing is seeded over the API; a fixture POSTed
 * into the document would prove the SERVER can hold the constraint, which was
 * never in doubt, and would move the parity number for a capability no one can
 * actually get at.
 *
 * The mechanism under test is the OFFER RAIL (`selectionVerbHints`): the status
 * cell proposes the verbs the CURRENT selection unlocks. So each case asserts
 * the offer FIRST — the affordance a user would have seen — and only then the
 * geometry the verb produced.
 */

const ANGLE_TOLERANCE_DEG = 0.01;
const COLLINEAR_TOLERANCE_MM = 1e-3;
const SYMMETRY_TOLERANCE_MM = 1e-3;

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
      entities: SolvedEntity[];
    } | null;
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

/**
 * The perpendicular distance from `point` to the infinite line through `line` —
 * the quantity `collinear` drives to zero for BOTH of the second line's ends.
 */
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

/** Reflect `point` across the infinite line through `axis`. */
function mirrored(
  axis: SolvedEntity | undefined,
  point: SolvedPoint | undefined,
): SolvedPoint | null {
  if (axis?.start === undefined || axis.end === undefined) return null;
  if (point === undefined) return null;
  const dx = axis.end.x - axis.start.x;
  const dy = axis.end.y - axis.start.y;
  const length2 = dx * dx + dy * dy;
  if (length2 === 0) return null;
  const rx = point.x - axis.start.x;
  const ry = point.y - axis.start.y;
  const t = (rx * dx + ry * dy) / length2;
  const footX = axis.start.x + t * dx;
  const footY = axis.start.y + t * dy;
  return { x: 2 * footX - point.x, y: 2 * footY - point.y };
}

const gap = (a: SolvedPoint | null, b: SolvedPoint | undefined): number =>
  a === null || b === undefined
    ? Number.POSITIVE_INFINITY
    : Math.hypot(a.x - b.x, a.y - b.y);

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

type At = (pt: { x: number; y: number }) => { x: number; y: number };

async function clickPlane(page: Page, at: At, pt: { x: number; y: number }) {
  const px = at(pt);
  await page.mouse.click(px.x, px.y);
}

/** Shift-click: ADD to the standing selection (FB-14) — a plain click replaces. */
async function addPlane(page: Page, at: At, pt: { x: number; y: number }) {
  await page.keyboard.down("Shift");
  await clickPlane(page, at, pt);
  await page.keyboard.up("Shift");
}

/** Draw one line from `from` to `to` with the L tool, then drop back to select. */
async function drawLine(
  page: Page,
  at: At,
  from: { x: number; y: number },
  to: { x: number; y: number },
) {
  await page.keyboard.press("l");
  await clickPlane(page, at, from);
  await clickPlane(page, at, to);
  await page.keyboard.press("Escape");
}

/** Every glyph of one constraint kind, addressed without counting slots. */
const glyphsOfKind = (page: Page, kind: string) =>
  page.locator(`[data-testid^="glyph-"][data-kind="${kind}"]`);

/**
 * Where entity `id` IS, per the latest solved payload — never where it was
 * drawn. A driving angle ROTATES a leg, so a hardcoded plane coordinate for a
 * line body is a bet that the solver left it alone, and the miss is quiet: the
 * click selects nothing and the failure surfaces two steps later against
 * innocent geometry (the lesson `dimension-expressions.spec.ts` wrote down).
 */
async function bodyOf(
  evaluations: EvaluateBody[],
  id: string,
): Promise<{ x: number; y: number }> {
  await expect
    .poll(
      () => {
        const line = entityById(evaluations, id);
        return line?.start !== undefined && line.end !== undefined;
      },
      { timeout: 20_000 },
    )
    .toBe(true);
  const line = entityById(evaluations, id);
  if (line?.start === undefined || line.end === undefined) {
    throw new Error(`line ${id} is absent from the solved payload`);
  }
  return {
    x: (line.start.x + line.end.x) / 2,
    y: (line.start.y + line.end.y) / 2,
  };
}

/** The persisted sketch's constraint list, read back from the feature tree. */
async function persistedConstraints(
  page: Page,
  partId: string,
  token: string,
): Promise<Array<{ kind: string; [key: string]: unknown }>> {
  const response = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok()).toBe(true);
  const body = (await response.json()) as {
    features: Array<{
      feature: {
        params: { constraints?: Array<{ kind: string }> };
      };
    }>;
  };
  return (body.features[0]?.feature.params.constraints ?? []) as Array<{
    kind: string;
  }>;
}

test.describe("the selection offers the verbs that apply to it (desktop 1440)", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("two lines offer Angle — typing 30 then 45 DRIVES the corner", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Angle gusset");
    const evaluations = collectEvaluations(page, part.id);
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 640, y: 560 },
      { x: 940, y: 380 },
    );

    // A gusset corner at the origin: two legs, neither axis-aligned (so the
    // draw infers no H/V that would fight the angle), both drawn OUTWARD from
    // the shared corner so the interior angle is unambiguous.
    await drawLine(page, at, { x: 0, y: 0 }, { x: 30, y: 10 }); // e1, 18.43 deg
    await drawLine(page, at, { x: 0, y: 0 }, { x: 10, y: 30 }); // e2, 71.57 deg

    // THE AFFORDANCE. Two lines selected, and the status cell proposes the verb
    // the pair unlocks — before this, nothing on screen mentioned angle at all.
    await clickPlane(page, at, { x: 24, y: 8 });
    await addPlane(page, at, { x: 8, y: 24 });
    await expect(page.getByTestId("selection-readout")).toContainText("2 ent");
    const rail = page.getByTestId("dimension-hint");
    await expect(rail).toBeVisible();
    await expect(rail).toContainText("angle");
    const angleOffer = page.getByTestId("verb-hint-angle");
    await expect(angleOffer).toBeVisible();
    await expect(angleOffer).toHaveAccessibleName("angle — press A");
    // The pair also unlocks collinear — the second contract verb with no home.
    await expect(page.getByTestId("verb-hint-collinear")).toBeVisible();

    // Press the key the rail stamped; the pair is already bound to the verb.
    await page.keyboard.press("a");
    const value = page.getByTestId("dimension-input");
    await expect(value).toBeVisible();
    await expect(page.getByTestId("dimension-editor")).toContainText("Angle");
    await expect(page.getByTestId("dimension-editor")).toContainText("deg");
    await value.fill("30");
    await page.getByTestId("dimension-apply").click();

    // THE ACCEPTANCE: the solver holds the corner at 30 degrees, and the glyph
    // says so in the drawing's own notation.
    await expect(glyphsOfKind(page, "angle")).toHaveText(["30°"], {
      timeout: 15_000,
    });
    await expect
      .poll(() => angleBetween(evaluations, "e1", "e2"), { timeout: 20_000 })
      .toBeCloseTo(30, 2);
    expect(
      Math.abs((angleBetween(evaluations, "e1", "e2") ?? 0) - 30),
    ).toBeLessThan(ANGLE_TOLERANCE_DEG);

    // DRIVING, not measuring: retype 45 and the geometry has to move.
    const before = {
      e1: entityById(evaluations, "e1")?.end,
      e2: entityById(evaluations, "e2")?.end,
    };
    // Re-select from the SOLVED positions: the 30-degree solve rotated a leg,
    // so the coordinates the lines were drawn at no longer name them.
    await clickPlane(page, at, await bodyOf(evaluations, "e1"));
    await addPlane(page, at, await bodyOf(evaluations, "e2"));
    await expect(page.getByTestId("selection-readout")).toContainText("2 ent");
    await page.keyboard.press("a");
    await expect(value).toBeVisible();
    // Pressing the verb on a pair that already carries one EDITS it rather than
    // stacking a redundant second angle on the same corner.
    await expect(value).toHaveValue("30");
    await value.fill("45");
    await page.getByTestId("dimension-apply").click();

    await expect(glyphsOfKind(page, "angle")).toHaveText(["45°"], {
      timeout: 15_000,
    });
    await expect
      .poll(() => angleBetween(evaluations, "e1", "e2"), { timeout: 20_000 })
      .toBeCloseTo(45, 2);
    expect(
      Math.abs((angleBetween(evaluations, "e1", "e2") ?? 0) - 45),
    ).toBeLessThan(ANGLE_TOLERANCE_DEG);
    const moved = Math.max(
      gap(before.e1 ?? null, entityById(evaluations, "e1")?.end),
      gap(before.e2 ?? null, entityById(evaluations, "e2")?.end),
    );
    expect(moved).toBeGreaterThan(0.5);

    // Exactly one angle constraint on the pair, not two.
    const persisted = await persistedConstraints(page, part.id, account.token);
    expect(persisted.filter((c) => c.kind === "angle")).toHaveLength(1);
  });

  test("a 2 mm step closes to one straight line under Collinear", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Stepped rail");
    const evaluations = collectEvaluations(page, part.id);
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 640, y: 560 },
      { x: 940, y: 380 },
    );

    // Two near-parallel segments of one intended rail, stepped ~2 mm apart —
    // the "I drew it in two goes and they don't line up" case.
    await drawLine(page, at, { x: 0, y: 0 }, { x: 30, y: 12 }); // e1
    await drawLine(page, at, { x: 39, y: 18 }, { x: 69, y: 31 }); // e2, stepped

    await clickPlane(page, at, { x: 15, y: 6 });
    await addPlane(page, at, { x: 54, y: 24.5 });
    await expect(page.getByTestId("selection-readout")).toContainText("2 ent");
    const offer = page.getByTestId("verb-hint-collinear");
    await expect(offer).toBeVisible();
    await expect(offer).toHaveAccessibleName("collinear — press I");

    // Click the keycap rather than pressing it: the rail serves the pointer too.
    await offer.click();

    // THE ACCEPTANCE: both ends of e2 land on e1's infinite line, and exactly
    // one collinear mark is drawn — one relation, one glyph.
    await expect(glyphsOfKind(page, "collinear")).toHaveCount(1, {
      timeout: 15_000,
    });
    await expect
      .poll(
        () => {
          const e1 = entityById(evaluations, "e1");
          const e2 = entityById(evaluations, "e2");
          const a = offLineDistance(e1, e2?.start);
          const b = offLineDistance(e1, e2?.end);
          if (a === null || b === null) return null;
          return Math.max(a, b);
        },
        { timeout: 20_000 },
      )
      .toBeLessThan(COLLINEAR_TOLERANCE_MM);
    expect(
      (await persistedConstraints(page, part.id, account.token)).filter(
        (c) => c.kind === "collinear",
      ),
    ).toHaveLength(1);
  });

  test("two lines about a centerline offer Symmetric — no 'select two points'", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Symmetric web");
    const evaluations = collectEvaluations(page, part.id);
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 640, y: 560 },
      { x: 940, y: 380 },
    );

    // Two flanks that should mirror about a vertical centerline at x = 20,
    // drawn deliberately UNEQUAL so the solver has work to do.
    await drawLine(page, at, { x: 6, y: 0 }, { x: 12, y: 30 }); // e1
    await drawLine(page, at, { x: 34, y: 0 }, { x: 31, y: 30 }); // e2
    await drawLine(page, at, { x: 20, y: -6 }, { x: 20, y: 36 }); // e3, the axis

    // Mark e3 as construction — a centerline, not profile geometry.
    await clickPlane(page, at, { x: 20, y: 15 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    await page.keyboard.press("n");

    await clickPlane(page, at, { x: 9, y: 15 });
    await addPlane(page, at, { x: 32.5, y: 15 });
    await addPlane(page, at, { x: 20, y: 15 });
    await expect(page.getByTestId("selection-readout")).toContainText("3 ent");
    const offer = page.getByTestId("verb-hint-symmetric");
    await expect(offer).toBeVisible();

    await page.keyboard.press("s");

    // THE ACCEPTANCE (first half): the verb no longer answers this exact
    // selection with "Select two points and a line" — the refusal the audit
    // filed, aimed at a user holding precisely the right picks. Asserted on the
    // TEXT rather than with `not.toContainText`, which passes vacuously when
    // the hint element is absent and so could not fail for the right reason.
    const hintText = async () => {
      const hint = page.getByTestId("constraint-hint");
      return (await hint.count()) === 0 ? "" : await hint.innerText();
    };
    expect(await hintText()).not.toContain("Select two points");

    // …and the persisted sketch carries the contract's own kind.
    await expect
      .poll(
        async () =>
          (await persistedConstraints(page, part.id, account.token)).filter(
            (c) => c.kind === "symmetric_lines",
          ).length,
        { timeout: 20_000 },
      )
      .toBe(1);
    await expect(glyphsOfKind(page, "symmetric_lines")).toHaveCount(1);

    // …and the geometry actually mirrors: each end of e2 lands on the
    // reflection of e1's matching end across the centerline.
    await expect
      .poll(
        () => {
          const axis = entityById(evaluations, "e3");
          const e1 = entityById(evaluations, "e1");
          const e2 = entityById(evaluations, "e2");
          if (axis === undefined || e1 === undefined || e2 === undefined) {
            return null;
          }
          return Math.max(
            gap(mirrored(axis, e1.start), e2.start),
            gap(mirrored(axis, e1.end), e2.end),
          );
        },
        { timeout: 20_000 },
      )
      .toBeLessThan(SYMMETRY_TOLERANCE_MM);
  });

  test("a circle offers its DIAMETER on D, and a point offers Midpoint", async ({
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

    await drawLine(page, at, { x: 0, y: 0 }, { x: 40, y: 14 }); // e1
    await page.keyboard.press("c");
    await clickPlane(page, at, { x: 20, y: 30 }); // e2 centre
    await clickPlane(page, at, { x: 31, y: 30 }); // 11 mm radius
    await page.keyboard.press("Escape");

    // A round selected: D is the DIAMETER, R is still the radius.
    await clickPlane(page, at, { x: 31, y: 30 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    const diameterOffer = page.getByTestId("verb-hint-diameter");
    await expect(diameterOffer).toBeVisible();
    await expect(diameterOffer).toHaveAccessibleName("diameter — press D");
    await expect(page.getByTestId("verb-hint-radius")).toBeVisible();

    await page.keyboard.press("d");
    const value = page.getByTestId("dimension-input");
    await expect(value).toBeVisible();
    await expect(page.getByTestId("dimension-editor")).toContainText(
      "Diameter",
    );
    await value.fill("16");
    await page.getByTestId("dimension-apply").click();

    await expect(glyphsOfKind(page, "diameter")).toHaveText(["⌀16"], {
      timeout: 15_000,
    });
    await expect
      .poll(() => entityById(evaluations, "e2")?.radius ?? null, {
        timeout: 20_000,
      })
      .toBeCloseTo(8, 3);

    // A point held against a line offers Midpoint — the circle's own centre,
    // centred on the line.
    await clickPlane(page, at, { x: 20, y: 30 }); // the centre point
    await addPlane(page, at, { x: 20, y: 7 }); // the line body
    const midpointOffer = page.getByTestId("verb-hint-midpoint");
    await expect(midpointOffer).toBeVisible();
    await midpointOffer.click();

    await expect(glyphsOfKind(page, "midpoint")).toHaveCount(1, {
      timeout: 15_000,
    });
    await expect
      .poll(
        () => {
          const line = entityById(evaluations, "e1");
          const circle = entityById(evaluations, "e2");
          if (line?.start === undefined || line.end === undefined) return null;
          if (circle?.center === undefined) return null;
          return Math.hypot(
            circle.center.x - (line.start.x + line.end.x) / 2,
            circle.center.y - (line.start.y + line.end.y) / 2,
          );
        },
        { timeout: 20_000 },
      )
      .toBeLessThan(COLLINEAR_TOLERANCE_MM);
  });
});

test.describe("founder screenshot — the offer rail (small laptop 1280)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("two selected lines surface Angle and Collinear in the status cell", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Gusset");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 560, y: 520 },
      { x: 860, y: 340 },
    );

    await drawLine(page, at, { x: 0, y: 0 }, { x: 30, y: 10 });
    await drawLine(page, at, { x: 0, y: 0 }, { x: 10, y: 30 });
    await clickPlane(page, at, { x: 24, y: 8 });
    await addPlane(page, at, { x: 8, y: 24 });
    await expect(page.getByTestId("verb-hint-angle")).toBeVisible();

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-vocab-offer-rail-1280.png`,
    });
  });
});
