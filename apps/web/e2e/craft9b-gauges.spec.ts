/**
 * CRAFT-9b — SHELL THICKNESS AND DATUM OFFSET ARE PULLABLE, AND THE PULL MOVES
 * A PICTURE.
 *
 * The direction pass sets one condition on this whole item (§8.4): *"A gauge
 * whose drag changes a number and not the model is worse than the form it
 * replaces — it promises direct manipulation and delivers a slider."* So every
 * drag case here asserts TWO things — the field moved AND the preview redrew —
 * and the preview assertion reads a stamp computed from the vertices actually
 * handed to the renderer, never from the value that produced them. A stamp of
 * the input cannot fail when the picture stops following, which is the one
 * failure this item exists to prevent.
 *
 * Both previews are route (b), geometric line-work: the shell draws the inner
 * offset outline of the picked face (the rim of the cavity the wall leaves),
 * the datum draws the offset plane at the current distance.
 *
 * The other three criteria, per verb: arrow keys step the same value;
 * `elementFromPoint` reaches the track at ≥ 12 of 16 offsets; and **contract β
 * — release the pointer and the instrument stays where you dragged it**, which
 * is the one that catches a missing echo and fires AFTER every screenshot
 * anyone would take.
 *
 * No `force: true` anywhere. Every pick is a real `page.mouse` press at a pixel
 * chosen from the drawn geometry, or an `elementFromPoint` census.
 */
import { expect, test, type Page } from "./fixtures";
import {
  dragGauge,
  expectReach,
  gripCentre,
  reach,
  spineLengthMm,
  viewportStamp,
} from "./gaugeProbe";
import { installSceneProbe, waitForCameraRest } from "./invariants";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/** A 40 x 40 square fixed at the origin on XY — extruded into a 40 mm block. */
const SQUARE_40 = {
  plane: { kind: "datum_plane", plane: "XY" },
  entities: [
    { id: "e1", kind: "line", start: { x: 0, y: 0 }, end: { x: 40, y: 0 } },
    { id: "e2", kind: "line", start: { x: 40, y: 0 }, end: { x: 40, y: 40 } },
    { id: "e3", kind: "line", start: { x: 40, y: 40 }, end: { x: 0, y: 40 } },
    { id: "e4", kind: "line", start: { x: 0, y: 40 }, end: { x: 0, y: 0 } },
  ],
  constraints: [
    {
      kind: "coincident",
      a: { entity: "e1", point: "end" },
      b: { entity: "e2", point: "start" },
    },
    {
      kind: "coincident",
      a: { entity: "e2", point: "end" },
      b: { entity: "e3", point: "start" },
    },
    {
      kind: "coincident",
      a: { entity: "e3", point: "end" },
      b: { entity: "e4", point: "start" },
    },
    {
      kind: "coincident",
      a: { entity: "e4", point: "end" },
      b: { entity: "e1", point: "start" },
    },
    { kind: "horizontal", entity: "e1" },
    { kind: "vertical", entity: "e2" },
    { kind: "horizontal", entity: "e3" },
    { kind: "vertical", entity: "e4" },
    { kind: "distance", entity: "e1", value_mm: 40 },
    { kind: "distance", entity: "e2", value_mm: 40 },
    { kind: "fixed", point: { entity: "e1", point: "start" } },
  ],
};

async function createFeature(
  page: Page,
  token: string,
  partId: string,
  body: unknown,
): Promise<{ feature: { id: string }; tree_version: number }> {
  const response = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: body,
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) {
    throw new Error(
      `e2e create feature failed: ${response.status()} ${await response.text()}`,
    );
  }
  return (await response.json()) as {
    feature: { id: string };
    tree_version: number;
  };
}

/** Seed a part whose body is a 40 mm cube at the origin, and open it. */
async function seedBlockPart(page: Page, name: string): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, name);
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: SQUARE_40 },
    expected_tree_version: 0,
  });
  await createFeature(page, account.token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 40,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  return part.id;
}

async function waitForBlock(page: Page): Promise<void> {
  await expect(page.getByTestId("prop-volume")).toContainText("64,000", {
    timeout: 60_000,
  });
}

/**
 * THE DRAWN ROD, READ AFTER THE ASK IT DESCRIBES HAS LANDED — the settle the
 * two contract-β cases were getting by accident.
 *
 * A gauge draws `live ?? value`: the optimistic ask while the pointer is
 * authoring, the owner's prop once it lets go. So the instant after
 * `mouse.up()` there is a window in which `live` is gone and the owner has not
 * yet echoed the LAST ask of the drag, and the scene graph holds the previous
 * step. Reading `scale.y` inside that window is reading a value that was
 * current for one commit and is not the answer to "where did the rod end up".
 * Measured: shell read `held 11` and then `10` on the frame after the release,
 * settling back to 11; datum's rod read 24 while its own field already held 25,
 * and both readings were 24 once the chain had drained. So the window catches
 * EITHER end of the drag — the held reading is no safer than the released one.
 *
 * It was filed as a base-tree intermittent, and it was never intermittent —
 * it was an UNSTATED SETTLE, the same defect class this repo has now hit five
 * times. What supplied the flush before was a mid-drag `pointerleave` firing
 * `disarmLadder`, i.e. an unrelated `setState` that happened to force React to
 * commit; the arc-drag fix moves the pointer handlers onto the sleeve wrapper
 * and that spurious boundary event correctly stops firing, so the accident
 * stops happening. **The settle was always required; only the accident that
 * hid it went away.**
 *
 * Stated here as two readings that agree, 100 ms apart, which cannot pass while
 * the value is still moving and fails loudly (by timeout) if the rod never
 * comes to rest at all. Deliberately NOT a poll toward an expected number: the
 * assertion about WHERE it settles stays at the call site, where it can fail.
 */
async function settledSpineMm(page: Page, gaugeId: string): Promise<number> {
  let previous: number | null = null;
  await expect
    .poll(
      async () => {
        const now = await spineLengthMm(page, gaugeId);
        const stable = previous !== null && Math.abs(now - previous) < 1e-6;
        previous = now;
        return stable;
      },
      {
        message:
          `the drawn ${gaugeId} rod never came to rest — two readings ` +
          `100 ms apart still disagree`,
      },
    )
    .toBe(true);
  if (previous === null) throw new Error(`no reading for gauge ${gaugeId}`);
  return previous;
}

/**
 * Click the shell face-pick node at the extreme z — the TOP face — chosen from
 * the accessible name so the pick is deterministic, exactly as `shell.spec.ts`
 * does (no reliance on screen projection or overlay index).
 */
async function pickTopFace(page: Page): Promise<void> {
  const nodes = page.locator('[data-testid^="shell-face-"]');
  await expect(nodes.first()).toBeVisible({ timeout: 30_000 });
  const count = await nodes.count();
  let bestZ = -Infinity;
  let bestIndex = 0;
  for (let i = 0; i < count; i += 1) {
    const label = (await nodes.nth(i).getAttribute("aria-label")) ?? "";
    const nums = label.match(/-?\d+(?:\.\d+)?/g) ?? [];
    const z = Number.parseFloat(nums[nums.length - 1] as string);
    if (!Number.isFinite(z)) continue;
    if (z > bestZ) {
      bestZ = z;
      bestIndex = i;
    }
  }
  await nodes.nth(bestIndex).click();
}

/** Open Shell on a seeded block, pick the top face, and set a legible wall. */
async function openShellOnTop(page: Page, thickness: string): Promise<void> {
  await page.getByTestId("new-shell").click();
  await expect(page.getByTestId("shell-editor")).toBeVisible();
  await pickTopFace(page);
  await expect(page.getByTestId("shell-open-count")).toHaveText("1 face open");
  await page.getByTestId("shell-thickness").fill(thickness);
  // Iso, because the seeded camera can look straight down a gauge's axis and a
  // track with no screen direction has no axis to walk.
  await page.getByTestId("view-iso").click();
  await waitForCameraRest(page);
  await expect(page.getByTestId("shell-thickness-handle")).toBeVisible();
}

async function openDatum(page: Page, offset: string): Promise<void> {
  await page.getByTestId("tool-datum").click();
  await expect(page.getByTestId("datum-editor")).toBeVisible();
  // The KIND is chosen explicitly rather than inherited. Datum seeds itself
  // from whatever face was selected when it was invoked (UI-W3), so after any
  // command that leaves a face picked it opens `on_face` — which is correct
  // product behaviour and makes the seat depend on test ORDER. Naming it here
  // is the difference between a spec that measures the datum gauge and one
  // that measures whatever the previous test left behind.
  await page.getByTestId("datum-kind").selectOption("offset");
  await page.getByTestId("datum-offset").fill(offset);
  await page.getByTestId("view-iso").click();
  await waitForCameraRest(page);
  await expect(page.getByTestId("datum-offset-handle")).toBeVisible();
}

const thickness = (page: Page): Promise<number> =>
  page
    .getByTestId("shell-thickness")
    .inputValue()
    .then((v) => Number.parseFloat(v));

const offset = (page: Page): Promise<number> =>
  page
    .getByTestId("datum-offset")
    .inputValue()
    .then((v) => Number.parseFloat(v));

test.describe("CRAFT-9b — the shell thickness gauge", () => {
  test("a real drag from the shaft moves the field AND redraws the wall", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const partId = await seedBlockPart(page, "Shelled housing");
    await page.goto(`/parts/${partId}`);
    await waitForBlock(page);
    await openShellOnTop(page, "4");

    // The rim is 40 x 40, so a 4 mm wall leaves a 32 x 32 cavity: perimeter 128.
    const before = await viewportStamp(page, "shell-preview-perimeter-mm");
    expect(
      before,
      "the inner offset outline must be drawn before anything is dragged",
    ).toBeCloseTo(128, 1);

    // Pull the wall thicker. No locator and no `force` — the raw mouse at the
    // midpoint of the drawn shaft, which is where the arrow tells you to aim
    // and exactly where CRAFT-7 measured nothing listening.
    await dragGauge(page, "shell-thickness", { dy: 90 });

    await expect
      .poll(() => thickness(page), {
        message:
          "a drag from the middle of the drawn shaft must move the value",
      })
      .toBeGreaterThan(4);

    // AND THE MODEL. A thicker wall is a smaller cavity, so the drawn outline's
    // perimeter must FALL — read from the vertices handed to the renderer, not
    // from the thickness that produced them. And it must be the RIGHT picture
    // rather than merely a different one: a square rim inset by t has perimeter
    // 4 × (40 − 2t).
    //
    // POLLED, and the wait is STATED rather than inherited. The field is DOM
    // and the stamp is published by an effect one commit further down the echo
    // (gauge → override → editor form → page → preview), so a bare read after
    // the pointer-up lands one value early about one run in two. An accidental
    // settle is a latent flake whether or not anyone has tripped it; this spec
    // tripped it on its first run.
    const pulled = await thickness(page);
    await expect
      .poll(() => viewportStamp(page, "shell-preview-perimeter-mm"), {
        message:
          "the preview must redraw with the drag — a number that moves alone is a slider",
      })
      .toBeCloseTo(4 * (40 - 2 * pulled), 1);
    const after = await viewportStamp(page, "shell-preview-perimeter-mm");
    console.log(
      `CRAFT-9b shell: t 4 -> ${pulled} mm, inner perimeter ${before} -> ${after} mm`,
    );
    expect(after).toBeLessThan(before as number);
  });

  test("contract β — release the pointer and the instrument stays", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const partId = await seedBlockPart(page, "Echoed housing");
    await page.goto(`/parts/${partId}`);
    await waitForBlock(page);
    await openShellOnTop(page, "4");

    const atRest = await spineLengthMm(page, "shell-thickness");
    expect(atRest).toBeCloseTo(4, 3);

    // Hold the drag open and read the DRAWN rod, then release and read it
    // again. Without the editor's echo the gauge drops its own optimistic value
    // on pointer-up and the rod springs back to 4 while the panel keeps the
    // number you dragged to — correct for the whole gesture, broken after it.
    await dragGauge(page, "shell-thickness", { dy: 70 }, { release: false });
    const held = await settledSpineMm(page, "shell-thickness");
    await page.mouse.up();
    // The release has been COMMITTED before the rod is read — `data-grabbed` is
    // the grip's own witness for it, and `settledSpineMm` then waits out the
    // owner's echo. See that helper: without both, this case reads the frame
    // between "the optimistic value is gone" and "the prop caught up".
    await expect(page.getByTestId("shell-thickness-handle")).toHaveAttribute(
      "data-grabbed",
      "false",
    );
    const released = await settledSpineMm(page, "shell-thickness");
    console.log(
      `CRAFT-9b shell β: rest ${atRest} → held ${held} → released ${released} mm`,
    );

    expect(held).toBeGreaterThan(atRest);
    expect(
      released,
      "the drawn rod must stay where the pointer left it (contract β)",
    ).toBeCloseTo(held, 3);
    expect(await thickness(page)).toBeCloseTo(released, 2);
  });

  test("elementFromPoint down the projected track resolves to the gauge", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const partId = await seedBlockPart(page, "Reachable housing");
    await page.goto(`/parts/${partId}`);
    await waitForBlock(page);
    await openShellOnTop(page, "8");
    expectReach(await reach(page, "shell-thickness"), "shell-thickness");
  });

  test("arrow keys step the same value the drag does", async ({ page }) => {
    await installSceneProbe(page);
    const partId = await seedBlockPart(page, "Keyed housing");
    await page.goto(`/parts/${partId}`);
    await waitForBlock(page);
    await openShellOnTop(page, "4");

    const grip = page.getByTestId("shell-thickness-handle");
    await grip.focus();
    const start = await thickness(page);
    await page.keyboard.press("ArrowUp");
    await expect.poll(() => thickness(page)).toBeGreaterThan(start);
    const stepped = await thickness(page);
    await page.keyboard.press("ArrowDown");
    await expect.poll(() => thickness(page)).toBeLessThan(stepped);

    // The ANNOUNCED step is the APPLIED step — the attribute a screen reader's
    // sentence is built from, checked against what the key actually did.
    const announced = await page
      .getByTestId("shell-thickness-handle")
      .getAttribute("data-step");
    expect(Number.parseFloat(announced ?? "0")).toBeCloseTo(stepped - start, 3);

    // And the preview followed the KEY, not only the pointer.
    const settled = await thickness(page);
    await expect
      .poll(() => viewportStamp(page, "shell-preview-perimeter-mm"))
      .toBeCloseTo(4 * (40 - 2 * settled), 1);
  });

  test("the instrument leaves with its command", async ({ page }) => {
    // A transparent band across the viewport that outlived its editor would
    // swallow face picks — the one way this fix could make the product worse.
    await installSceneProbe(page);
    const partId = await seedBlockPart(page, "Closed housing");
    await page.goto(`/parts/${partId}`);
    await waitForBlock(page);
    await openShellOnTop(page, "4");
    await expect(page.getByTestId("shell-thickness-sleeve")).toHaveCount(1);
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("shell-editor")).toHaveCount(0);
    await expect(page.getByTestId("shell-thickness-sleeve")).toHaveCount(0);
    await expect(page.getByTestId("viewport")).not.toHaveAttribute(
      "data-shell-preview-perimeter-mm",
      /.*/,
    );
  });
});

test.describe("CRAFT-9b — the datum offset gauge", () => {
  test("a real drag moves the field AND slides the drawn plane", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const partId = await seedBlockPart(page, "Datum block");
    await page.goto(`/parts/${partId}`);
    await waitForBlock(page);
    await openDatum(page, "30");

    const before = await viewportStamp(page, "datum-preview-offset-mm");
    expect(
      before,
      "the offset plane must be drawn where the form says it is",
    ).toBeCloseTo(30, 1);

    await dragGauge(page, "datum-offset", { dy: 80 });

    const pulled = await offset(page);
    expect(pulled).not.toBeCloseTo(30, 2);
    await expect
      .poll(() => viewportStamp(page, "datum-preview-offset-mm"), {
        message: "the drawn sheet must stand at the offset the field now holds",
      })
      .toBeCloseTo(Math.abs(pulled), 1);
    const after = await viewportStamp(page, "datum-preview-offset-mm");
    console.log(
      `CRAFT-9b datum: offset 30 -> ${pulled} mm, drawn sheet ${before} -> ${after} mm`,
    );
  });

  test("contract β — release the pointer and the instrument stays", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const partId = await seedBlockPart(page, "Echoed datum");
    await page.goto(`/parts/${partId}`);
    await waitForBlock(page);
    await openDatum(page, "30");

    const atRest = await spineLengthMm(page, "datum-offset");
    expect(atRest).toBeCloseTo(30, 3);
    await dragGauge(page, "datum-offset", { dy: 60 }, { release: false });
    const held = await settledSpineMm(page, "datum-offset");
    await page.mouse.up();
    // Same settle as the shell case, same reason — see `settledSpineMm`.
    await expect(page.getByTestId("datum-offset-handle")).toHaveAttribute(
      "data-grabbed",
      "false",
    );
    const released = await settledSpineMm(page, "datum-offset");
    console.log(
      `CRAFT-9b datum β: rest ${atRest} → held ${held} → released ${released} mm`,
    );
    expect(Math.abs(held - atRest)).toBeGreaterThan(0.5);
    expect(
      released,
      "the drawn rod must stay where the pointer left it (contract β)",
    ).toBeCloseTo(held, 3);
    expect(Math.abs(await offset(page))).toBeCloseTo(released, 2);
  });

  test("elementFromPoint down the projected track resolves to the gauge", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const partId = await seedBlockPart(page, "Reachable datum");
    await page.goto(`/parts/${partId}`);
    await waitForBlock(page);
    await openDatum(page, "30");
    expectReach(await reach(page, "datum-offset"), "datum-offset");
  });

  test("arrow keys step the same value the drag does", async ({ page }) => {
    await installSceneProbe(page);
    const partId = await seedBlockPart(page, "Keyed datum");
    await page.goto(`/parts/${partId}`);
    await waitForBlock(page);
    await openDatum(page, "30");

    await page.getByTestId("datum-offset-handle").focus();
    const start = await offset(page);
    await page.keyboard.press("ArrowUp");
    await expect.poll(() => offset(page)).toBeGreaterThan(start);
    const stepped = await offset(page);

    const announced = await page
      .getByTestId("datum-offset-handle")
      .getAttribute("data-step");
    expect(Number.parseFloat(announced ?? "0")).toBeCloseTo(stepped - start, 3);
    await expect
      .poll(() => viewportStamp(page, "datum-preview-offset-mm"))
      .toBeCloseTo(stepped, 1);
  });

  test("the sheet and the instrument leave with the command", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const partId = await seedBlockPart(page, "Closed datum");
    await page.goto(`/parts/${partId}`);
    await waitForBlock(page);
    await openDatum(page, "30");
    await expect(page.getByTestId("datum-offset-sleeve")).toHaveCount(1);
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("datum-editor")).toHaveCount(0);
    await expect(page.getByTestId("datum-offset-sleeve")).toHaveCount(0);
    await expect(page.getByTestId("viewport")).not.toHaveAttribute(
      "data-datum-preview-offset-mm",
      /.*/,
    );
  });

  test("a reopened command starts from its own default, not the last drag", async ({
    page,
  }) => {
    // ANCHOR B, the line everyone forgets: without the override reset the next
    // Datum opens seeded from the previous gesture, corrupting a value the user
    // never touched this time round.
    await installSceneProbe(page);
    const partId = await seedBlockPart(page, "Reopened datum");
    await page.goto(`/parts/${partId}`);
    await waitForBlock(page);
    await openDatum(page, "30");
    await dragGauge(page, "datum-offset", { dy: 70 });
    expect(await offset(page)).not.toBeCloseTo(30, 2);

    await page.keyboard.press("Escape");
    await expect(page.getByTestId("datum-editor")).toHaveCount(0);
    await page.getByTestId("tool-datum").click();
    await expect(page.getByTestId("datum-editor")).toBeVisible();
    expect(
      await offset(page),
      "a new datum opens at its own default (30 mm above XY)",
    ).toBeCloseTo(30, 6);
  });
});

test.describe("CRAFT-9b — founder captures", () => {
  test("shell and datum, before and after the pull", async ({ page }) => {
    await installSceneProbe(page);
    const partId = await seedBlockPart(page, "Gauge capture");
    await page.goto(`/parts/${partId}`);
    await waitForBlock(page);

    await openShellOnTop(page, "4");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/craft9b-shell-before-1280.png`,
    });
    await dragGauge(page, "shell-thickness", { dy: 90 });
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/craft9b-shell-after-1280.png`,
    });
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("shell-editor")).toHaveCount(0);

    await openDatum(page, "30");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/craft9b-datum-before-1280.png`,
    });
    await dragGauge(page, "datum-offset", { dy: 80 });
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/craft9b-datum-after-1280.png`,
    });
    // THE CAPTURE IS A GATE, NOT A COURTESY — and this assertion is the gate,
    // so it may not be a box property.
    //
    // The first version of this line was `toBeVisible()` on the grip, and it
    // PASSED while the grip sat at y = -87.7, i.e. eighty-eight pixels above
    // the top of the frame with its tag and its number entirely off screen.
    // Playwright calls an element outside the viewport visible — it has a box
    // and it is not `display: none` — which is the same family as the `sr-only`
    // control clipped out of frame that this repo has already paid for. A
    // screenshot gate that cannot fail when the subject is off the picture is
    // not a gate. So: the grip's centre must be INSIDE the viewport's own rect.
    const frame = await page.getByTestId("viewport").boundingBox();
    if (frame === null) throw new Error("no viewport box");
    const grip = await gripCentre(page, "datum-offset");
    console.log(
      `CRAFT-9b capture: datum grip at ${JSON.stringify(grip)} in ${JSON.stringify(frame)}`,
    );
    expect(
      grip.x >= frame.x &&
        grip.x <= frame.x + frame.width &&
        grip.y >= frame.y &&
        grip.y <= frame.y + frame.height,
      "the instrument must be IN the picture the founder is sent",
    ).toBe(true);
  });
});
