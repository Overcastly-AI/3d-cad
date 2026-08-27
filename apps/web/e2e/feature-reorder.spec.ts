import { expect, test, type Page } from "./fixtures";

import { createFeature, SQUARE_20 } from "./partSeed";
import { createPartViaApi, seedSession } from "./support";

/**
 * REORDER THE FEATURE TREE (REACH-ORDER) — driven through the real browser
 * against the real stack.
 *
 * `PUT /api/v1/parts/{part_id}/features/order` had been shipped, typed and
 * history-recorded for weeks and NOTHING in `apps/web` called it, so putting a
 * fillet after a pattern meant deleting and re-authoring every downstream
 * feature. These cases prove the endpoint is finally reachable from the
 * interface, by the two routes a modeller has (a grip, and Alt+Up), and that
 * the refusal is reachable too.
 *
 * WHAT IS ASSERTED, AND WHY IT IS THE VOLUME. A 2xx proves the request parsed,
 * not that it meant anything — this repo has had seven tests pass against a
 * silently-ignored field for exactly that reason. So the gate here is the
 * GEOMETRY: a fillet BEFORE the hole rounds only the block's own edges, and a
 * fillet AFTER it rounds the bore's rims as well, which is a different solid
 * and a different volume. Row order is checked too, but the volume is the
 * assertion that could not pass against a no-op.
 */

/** Sketch → extrude 40x40x20 → Ø8 hole through → fillet r1 on all edges. */
async function seedBlock(
  page: Page,
): Promise<{ partId: string; token: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Reorder block");
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    // The shared 20 mm square, dimensioned to 40 — one fixture, one idea of a
    // constrained rectangle (the reason `SQUARE_20` was extracted at all).
    feature: {
      type: "sketch",
      version: 1,
      params: {
        ...SQUARE_20,
        entities: [
          {
            id: "e1",
            kind: "line",
            start: { x: 0, y: 0 },
            end: { x: 40, y: 0 },
          },
          {
            id: "e2",
            kind: "line",
            start: { x: 40, y: 0 },
            end: { x: 40, y: 40 },
          },
          {
            id: "e3",
            kind: "line",
            start: { x: 40, y: 40 },
            end: { x: 0, y: 40 },
          },
          {
            id: "e4",
            kind: "line",
            start: { x: 0, y: 40 },
            end: { x: 0, y: 0 },
          },
        ],
        constraints: SQUARE_20.constraints.map((constraint) =>
          constraint.kind === "distance"
            ? { ...constraint, value_mm: 40 }
            : constraint,
        ),
      },
    },
    expected_tree_version: 0,
  });
  const extrude = await createFeature(page, account.token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 20,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  const hole = await createFeature(page, account.token, part.id, {
    name: "Hole1",
    feature: {
      type: "hole",
      version: 1,
      params: {
        // The top face of the block — the extrude's own result, named by the
        // stage-1 signature the picker would have produced.
        face: {
          kind: "subshape",
          feature_id: extrude.feature.id,
          subshape_type: "face",
          selector: {
            selector_version: 1,
            signature: {
              subshape_type: "face",
              surface: "plane",
              area_mm2: 1600,
              centroid: { x: 20, y: 20, z: 20 },
              normal: { x: 0, y: 0, z: 1 },
            },
          },
        },
        position: { x: 20, y: 20, z: 20 },
        diameter_mm: 8,
        depth: { kind: "through_all" },
      },
    },
    expected_tree_version: extrude.tree_version,
  });
  await createFeature(page, account.token, part.id, {
    name: "Fillet1",
    feature: {
      type: "fillet",
      version: 1,
      params: { edges: { kind: "all_edges" }, radius_mm: 1 },
    },
    expected_tree_version: hole.tree_version,
  });
  return { partId: part.id, token: account.token };
}

/** The body volume (mm³) parsed from the mass-properties readout. */
async function bodyVolume(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  const nums = text.replace(/,/g, "").match(/-?\d+(?:\.\d+)?/g) ?? [];
  return Number.parseFloat(nums[0] ?? "NaN");
}

/** The row names, top to bottom — the build order as the user reads it. */
async function rowNames(page: Page): Promise<string[]> {
  return page
    .getByTestId("feature-row")
    .evaluateAll((rows) =>
      rows.map(
        (row) =>
          row.querySelector(
            '[data-testid^="feature-select-"] span:nth-child(1)',
          )?.textContent ?? "",
      ),
    );
}

/**
 * The order the DOCUMENT holds, read straight from the gateway — a second
 * derivation of the same fact, so the rows can be checked against something
 * other than themselves.
 *
 * This is the guard for the family of defect this repo has hit repeatedly: a
 * readout that confidently reports a number derived from a source that has not
 * learned the thing moved. Asserting the rows alone would pass against a client
 * that reordered its own array and never refetched.
 */
async function storedOrder(
  page: Page,
  token: string,
  partId: string,
): Promise<string[]> {
  const response = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const body = (await response.json()) as { features: { name: string }[] };
  return body.features.map((feature) => feature.name);
}

async function waitForSolved(page: Page): Promise<void> {
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 40_000,
  });
}

test.describe("feature tree reorder", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("Alt+Up moves the fillet ahead of the hole and the SOLID changes", async ({
    page,
  }) => {
    const { partId, token } = await seedBlock(page);
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("feature-row")).toHaveCount(4);
    await waitForSolved(page);

    expect(await rowNames(page)).toEqual([
      "Sketch1",
      "Extrude1",
      "Hole1",
      "Fillet1",
    ]);
    const before = await bodyVolume(page);
    expect(before).toBeGreaterThan(0);

    // Select the fillet: its ordinal becomes the grip, and it is a control a
    // real pointer can land on — `toBeVisible()` is a box property and has
    // passed a control shoved outside the frame, so this is a HIT TEST.
    await page.getByTestId("feature-select-3").click();
    const grip = page.getByTestId("feature-grip-3");
    await expect(grip).toBeVisible();
    const box = await grip.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeGreaterThanOrEqual(24);
    expect(box!.height).toBeGreaterThanOrEqual(24);
    const hit = await page.evaluate(
      ({ x, y }: { x: number; y: number }) =>
        document
          .elementFromPoint(x, y)
          ?.closest("[data-testid]")
          ?.getAttribute("data-testid") ?? null,
      { x: box!.x + box!.width / 2, y: box!.y + box!.height / 2 },
    );
    expect(hit).toBe("feature-grip-3");

    // THE MUTATION. Watch the wire: the route takes the full permutation, so
    // the request body is the evidence that the UI asked the right question.
    const [request] = await Promise.all([
      page.waitForRequest(
        (r) => r.method() === "PUT" && r.url().includes("/features/order"),
        { timeout: 20_000 },
      ),
      page.keyboard.press("Alt+ArrowUp"),
    ]);
    const sent = request.postDataJSON() as { order: string[] };
    expect(sent.order).toHaveLength(4);

    await expect
      .poll(() => rowNames(page), { timeout: 40_000 })
      .toEqual(["Sketch1", "Extrude1", "Fillet1", "Hole1"]);
    await waitForSolved(page);

    // WHAT IS ON SCREEN IS WHAT LANDED. The rows are checked against an
    // independent read of the document, not against themselves — a client that
    // reordered its own array and never refetched would agree with itself here
    // and disagree with this.
    expect(await rowNames(page)).toEqual(
      await storedOrder(page, token, partId),
    );

    // A fillet that runs BEFORE the bore never touches the bore's rims, so the
    // same three features describe a different solid. This is the assertion a
    // silently-ignored payload could not pass.
    await expect
      .poll(() => bodyVolume(page), { timeout: 40_000 })
      .not.toBeCloseTo(before, 2);
  });

  test("dragging the grip reorders, and Escape mid-drag restores the order", async ({
    page,
  }) => {
    const { partId } = await seedBlock(page);
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("feature-row")).toHaveCount(4);
    await waitForSolved(page);
    const before = await bodyVolume(page);

    await page.getByTestId("feature-select-3").click();
    const grip = page.getByTestId("feature-grip-3");
    const gripBox = (await grip.boundingBox())!;
    const holeRow = (await page
      .getByTestId("feature-row")
      .nth(2)
      .boundingBox())!;

    // 1) A drag that is ABANDONED changes nothing — the seat is painted, then
    //    Escape puts the gesture down and no write is ever issued.
    let orderWrites = 0;
    page.on("request", (r) => {
      if (r.method() === "PUT" && r.url().includes("/features/order")) {
        orderWrites += 1;
      }
    });
    await page.mouse.move(
      gripBox.x + gripBox.width / 2,
      gripBox.y + gripBox.height / 2,
    );
    await page.mouse.down();
    await page.mouse.move(
      gripBox.x + gripBox.width / 2,
      holeRow.y + holeRow.height / 2,
      { steps: 6 },
    );
    await expect(page.getByTestId("reorder-seat")).toHaveAttribute(
      "data-legal",
      "true",
    );
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("reorder-seat")).toHaveCount(0);
    await page.mouse.up();
    expect(orderWrites).toBe(0);
    expect(await rowNames(page)).toEqual([
      "Sketch1",
      "Extrude1",
      "Hole1",
      "Fillet1",
    ]);

    // 2) The same drag, carried through, moves the row and rebuilds the body.
    await page.mouse.move(
      gripBox.x + gripBox.width / 2,
      gripBox.y + gripBox.height / 2,
    );
    await page.mouse.down();
    await page.mouse.move(
      gripBox.x + gripBox.width / 2,
      holeRow.y + holeRow.height / 2,
      { steps: 6 },
    );
    await page.mouse.up();

    await expect
      .poll(() => rowNames(page), { timeout: 40_000 })
      .toEqual(["Sketch1", "Extrude1", "Fillet1", "Hole1"]);
    await waitForSolved(page);
    expect(orderWrites).toBe(1);
    await expect
      .poll(() => bodyVolume(page), { timeout: 40_000 })
      .not.toBeCloseTo(before, 2);
  });

  test("moving the hole above the extrude it is drilled into is refused, in words, by keyboard alone", async ({
    page,
  }) => {
    const { partId } = await seedBlock(page);
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("feature-row")).toHaveCount(4);
    await waitForSolved(page);
    const before = await bodyVolume(page);

    let orderWrites = 0;
    page.on("request", (r) => {
      if (r.method() === "PUT" && r.url().includes("/features/order")) {
        orderWrites += 1;
      }
    });

    // Hole1 sits at 03, on the extrude at 02. Alt+Up aims it at the extrude's
    // seat — a move the tree cannot take.
    await page.getByTestId("feature-select-2").click();
    await page.keyboard.press("Alt+ArrowUp");

    const refusal = page.getByTestId("reorder-refusal");
    await expect(refusal).toHaveText(
      /Hole1 is built on Extrude1, so Extrude1 has to stay above it\./,
    );

    // READABLE AFTER TAB-FOCUS ALONE. Not a hover tooltip, not a `title`
    // attribute — a real tab stop whose own text names the feature it refused
    // for. Walked from the top of the tree with nothing but Tab, so what is
    // asserted is the thing a keyboard user actually does.
    const readAt = () =>
      page.evaluate(() => {
        const el = document.activeElement;
        return {
          testId: el?.getAttribute("data-testid") ?? null,
          text: el?.textContent ?? "",
          label: el?.getAttribute("aria-label") ?? "",
        };
      });
    await page.getByTestId("feature-select-0").focus();
    let focused = await readAt();
    for (
      let step = 0;
      step < 8 && focused.testId !== "reorder-refusal";
      ++step
    ) {
      await page.keyboard.press("Tab");
      focused = await readAt();
    }
    expect(focused.testId).toBe("reorder-refusal");
    expect(focused.text).toContain("Extrude1");
    expect(focused.label).toContain("Extrude1");

    // Nothing was sent, nothing moved, and the part is still solved.
    expect(orderWrites).toBe(0);
    expect(await rowNames(page)).toEqual([
      "Sketch1",
      "Extrude1",
      "Hole1",
      "Fillet1",
    ]);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved");
    expect(await bodyVolume(page)).toBeCloseTo(before, 2);
  });
});
