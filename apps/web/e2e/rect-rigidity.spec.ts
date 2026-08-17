import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, seedSession } from "./support";

/**
 * RECT-1 — a rectangle drawn WITHOUT typing a size is still a rectangle.
 *
 * THE DEFECT, in the user's terms. `rectangleRigidity` — the only thing that
 * authors a rectangle's four corner coincidences and its 2H/2V — used to ride
 * with the first TYPED draw-time dimension. Draw a rectangle, don't type a
 * size, dismiss the cell, and you had four numerically-coincident but
 * topologically DISCONNECTED lines. Dimension one edge later and that edge
 * moved alone: the rectangle tore open at the corners, the profile no longer
 * closed, and the extrude died. This is the most common closed-profile gesture
 * in the sketcher, and until DIM-1 (`a810524`, the day before this landed)
 * draw-time keystrokes did not register at all — so essentially every
 * rectangle ever drawn against this build took the untyped path.
 *
 * WHY THIS SPEC EXISTS RATHER THAN A UNIT TEST. The store tests can prove the
 * constraints are in the buffer, which is what they do. They cannot prove the
 * SOLVER honours them — that the rigidity set survives persistence, reaches
 * planegcs, and actually drags the other three edges. That round trip is the
 * whole claim, so the assertion below reads the solved evaluate payload and
 * nothing else. A rigidity set the server never sees would pass every unit
 * test in the repo.
 *
 * THE SECOND TEST is not a duplicate of the first: it reads the constraints
 * back off the PERSISTED feature tree. A client-side-only rigidity set would
 * satisfy the first test's solve (the buffer is what gets sent) and still lose
 * the rectangle the moment the sketch was re-opened from disk.
 *
 * Both were checked by mutation rather than assumed — reverting `placeAt` to
 * author nothing reddens each of them. Worth recording HOW, because the first
 * reading of that result was too generous: with the mutant in, this file fails
 * at the rigidity-set readout, several lines ABOVE the tear. That guard is
 * cheap and it fires first, which would have left the assertion that actually
 * matters never once seen to fail. So the count guard was disabled and the
 * mutant re-run to drive the solve assertion itself, and it reports exactly
 * the defect this ticket describes:
 *
 *     { bottom: true, sidesHeld: true, topFollowed: false }
 *
 * — the dimensioned edge reaches 60, the sides hold at 25, and the opposite
 * edge stays where it was. That is the tear, measured. An assertion never seen
 * to fail is not a gate, and "something in the file went red" is not evidence
 * that the right thing did.
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

/** Solver agreement band. The kernel works to 1e-7 m; this is generous. */
const SOLVE_TOLERANCE_MM = 0.01;

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

const latestSketch = (bodies: EvaluateBody[]) =>
  bodies.length > 0 ? (bodies[bodies.length - 1]?.features[0] ?? null) : null;

const lineLength = (entities: SolvedEntity[], id: string): number | null => {
  const line = entities.find((e) => e.id === id);
  if (line?.start === undefined || line.end === undefined) return null;
  return Math.hypot(line.end.x - line.start.x, line.end.y - line.start.y);
};

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

const clickPlane = async (
  page: Page,
  at: (pt: { x: number; y: number }) => { x: number; y: number },
  pt: { x: number; y: number },
) => {
  const px = at(pt);
  await page.mouse.click(px.x, px.y);
};

/**
 * Draw a 40x25 rectangle from the origin and DISMISS the draw-time size cell
 * without typing anything — the exact gesture the defect was about. Returns the
 * plane→screen mapper.
 */
async function drawUndimensionedRect(page: Page) {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
  const at = await calibratePlane(
    page,
    { x: 700, y: 620 },
    { x: 1000, y: 420 },
  );

  await page.keyboard.press("r");
  await clickPlane(page, at, { x: 0, y: 0 });
  await clickPlane(page, at, { x: 40, y: 25 });
  await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
  // Nothing typed. Escape dismisses the size cells and drops the tool — the
  // "I'll dimension it later" path, which is what most people actually do.
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("draw-dimensions")).toHaveCount(0);
  return at;
}

test.describe("RECT-1 — a rectangle drawn without a typed size is still a rectangle", () => {
  test("re-driving ONE edge moves the other three with it, through the solver", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Untyped rect");
    const evaluations = collectEvaluations(page, part.id);
    await page.goto(`/parts/${part.id}`);
    const at = await drawUndimensionedRect(page);

    // The draw alone authored the rigidity set — before the user has typed
    // anything at all: four corner coincidences, 2H, 2V.
    //
    // Counted BY KIND, not by grand total. The total is not this test's claim
    // and it has already moved once under it: SNAP-3 later made the first
    // corner's snap to the origin author a further coincident, which is
    // correct and has nothing to do with rigidity. A test that pins a total
    // reddens every time a NEIGHBOURING feature authors anything, and when it
    // does it says nothing about the thing it is named for. The 2H/2V are
    // exact because only the rectangle can author them; coincidences are a
    // floor because the frame legitimately adds more.
    const glyph = (kind: string) =>
      page.locator(`[data-testid^="glyph-"][data-kind="${kind}"]`);
    await expect(glyph("horizontal")).toHaveCount(2);
    await expect(glyph("vertical")).toHaveCount(2);
    expect(await glyph("coincident").count()).toBeGreaterThanOrEqual(4);

    // Now the LATER dimension, the one that used to tear the shape apart:
    // 40 -> 60 on the bottom edge only.
    await clickPlane(page, at, { x: 20, y: 0 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    await page.keyboard.press("d");
    const input = page.getByTestId("dimension-input");
    await expect(input).toBeVisible();
    await input.fill("60");
    await input.press("Enter");

    // THE ASSERTION, read from the SOLVED payload rather than the readout.
    // e1 (bottom) is the dimensioned edge. e3 (top) is the one that had to
    // follow: with the corners disconnected it stayed at 40 while e1 grew to
    // 60, which is precisely the tear. e2/e4 (the sides) stay 25 and stay
    // vertical, which is what makes it a rectangle rather than a trapezium.
    await expect
      .poll(
        () => {
          const sketch = latestSketch(evaluations);
          if (sketch?.data == null) return null;
          const es = sketch.data.entities;
          const bottom = lineLength(es, "e1");
          const top = lineLength(es, "e3");
          if (bottom === null || top === null) return null;
          return {
            bottom: Math.abs(bottom - 60) < SOLVE_TOLERANCE_MM,
            topFollowed: Math.abs(top - 60) < SOLVE_TOLERANCE_MM,
            sidesHeld:
              Math.abs((lineLength(es, "e2") ?? 0) - 25) < SOLVE_TOLERANCE_MM &&
              Math.abs((lineLength(es, "e4") ?? 0) - 25) < SOLVE_TOLERANCE_MM,
          };
        },
        { timeout: 30_000 },
      )
      .toEqual({ bottom: true, topFollowed: true, sidesHeld: true });

    // …and the corners are still corners: every endpoint meets its neighbour.
    const es = latestSketch(evaluations)?.data?.entities ?? [];
    const loop: Array<[string, string]> = [
      ["e1", "e2"],
      ["e2", "e3"],
      ["e3", "e4"],
      ["e4", "e1"],
    ];
    for (const [a, b] of loop) {
      const end = es.find((e) => e.id === a)?.end;
      const start = es.find((e) => e.id === b)?.start;
      expect(end).toBeDefined();
      expect(start).toBeDefined();
      expect(
        Math.hypot(
          (end?.x ?? 0) - (start?.x ?? 0),
          (end?.y ?? 0) - (start?.y ?? 0),
        ),
      ).toBeLessThan(SOLVE_TOLERANCE_MM);
    }
  });

  test("the rigidity set reaches the SERVER, not just the local buffer", async ({
    page,
  }) => {
    // A client-side-only rigidity set would satisfy every store test and every
    // readout in the app, and would still lose the rectangle the moment the
    // sketch was re-opened. So read it back off the persisted feature tree.
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Persisted rect");
    await page.goto(`/parts/${part.id}`);
    const at = await drawUndimensionedRect(page);
    const glyphs = page.locator('[data-testid^="glyph-"]');
    const beforeDimension = await glyphs.count();

    // The draw deliberately does NOT bind the sketch (see `userConstrained` in
    // the sketch store — binding on the automatic set would have removed the
    // unsaved-exit confirm for rectangles only). A dimension is a USER edit, so
    // it persists, and the rigidity set rides along with it.
    await clickPlane(page, at, { x: 20, y: 0 });
    await page.keyboard.press("d");
    const input = page.getByTestId("dimension-input");
    await expect(input).toBeVisible();
    await input.fill("40");
    await input.press("Enter");
    // Exactly ONE more than the draw left behind — the dimension just typed,
    // and nothing smuggled in beside it. A DELTA rather than a total, so it
    // survives the next feature that authors something at draw time; a pinned
    // total here is what SNAP-3 broke.
    await expect(glyphs).toHaveCount(beforeDimension + 1);
    await expect(
      page.locator('[data-testid^="glyph-"][data-kind="distance"]'),
    ).toHaveCount(1);

    // Finish the sketch so the feature is committed, then read it straight off
    // the API — not off the store, which is the thing under test.
    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
    const response = await page.request.get(
      `/api/v1/parts/${part.id}/features`,
      { headers: { Authorization: `Bearer ${account.token}` } },
    );
    expect(response.ok()).toBe(true);
    const body = (await response.json()) as {
      features: Array<{
        feature: { params: { constraints?: Array<{ kind: string }> } };
      }>;
    };
    // BY KIND COUNT, not as an ordered list. The claim is "the rigidity set
    // reached the server", and an exact array also pins the ORDER and the
    // presence of every neighbouring feature's work — SNAP-3's origin
    // coincident and the `fixed` pin that materialising the origin brings with
    // it both land here legitimately. 2H/2V are exact because only the
    // rectangle authors them; coincidences are a floor for the same reason.
    const kinds = body.features[0]?.feature.params.constraints?.map(
      (c) => c.kind,
    );
    expect(kinds).toBeDefined();
    const count = (k: string) => (kinds ?? []).filter((x) => x === k).length;
    expect(count("horizontal")).toBe(2);
    expect(count("vertical")).toBe(2);
    expect(count("coincident")).toBeGreaterThanOrEqual(4);
    expect(count("distance")).toBe(1);
  });
});
