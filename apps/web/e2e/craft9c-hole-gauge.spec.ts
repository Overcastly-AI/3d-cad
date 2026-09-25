/**
 * CRAFT-9c — A HOLE'S DIAMETER AND DEPTH ARE PULLABLE, AND THE PULL MOVES A
 * PICTURE.
 *
 * The same four criteria as CRAFT-9a/9b — a real drag moves the field AND the
 * preview, arrow keys step the same value, `elementFromPoint` reaches the drawn
 * track, and contract β holds — plus the one only a two-instrument, one-tag
 * verb can fail: the COMPANION CHECK. Dragging depth must not move the Ø
 * cell's number or the Ø instrument, and dragging Ø must not move the D cell's
 * number or the depth instrument's length.
 *
 * ## How the evidence is taken, because each rule has paid for itself here
 *
 *  · **Every pointer interaction is a real `page.mouse` press at the GRIP'S
 *    CENTRE**, read from the grip's own box. No `force: true`, no dispatched
 *    events on a gauge control. (The one dispatched click is the face pick in
 *    `openHole`, and its note says why.)
 *  · **Reach is `document.elementFromPoint`** down the drawn track, via
 *    `gaugeProbe.expectReach`, which also refuses a sample that resolves to the
 *    SIBLING instrument — the defect a two-gauge verb is newly able to have.
 *  · **Contract β is asserted on the PROPERTY, on every frame**: the grip's
 *    `data-value` against the panel field, read in the SAME synchronous turn of
 *    one `requestAnimationFrame` loop for the whole gesture and after it. A
 *    screen position cannot tell "the value sprang back" from "the camera
 *    moved"; the pair of numbers can.
 *  · **The camera settles on POSITION** (`waitForCameraStill`), never on
 *    direction alone — a re-frame keeps the direction and moves everything.
 *  · The previews are read from viewport stamps computed from the DRAWN
 *    buffers (the ring's vertex radius, the plane's distance down the axis), so
 *    a picture that stopped following reports where it was left.
 */
import { expect, test, type Page } from "./fixtures";
import { openHole } from "./gaugeMounts";
import {
  expectReach,
  gripCentre,
  projectedSpine,
  reach,
  spineLengthMm,
  viewportStamp,
  type Point,
} from "./gaugeProbe";
import { installSceneProbe, waitForCameraStill } from "./invariants";
import { SCREENSHOT_DIR } from "./support";

const DIAMETER = "hole-diameter-gauge";
const DEPTH = "hole-depth-gauge";

const numberIn = (page: Page, testId: string): Promise<number> =>
  page
    .getByTestId(testId)
    .inputValue()
    .then((v) => Number.parseFloat(v));

const diameterField = (page: Page) => numberIn(page, "hole-diameter");
const depthField = (page: Page) => numberIn(page, "hole-blind-depth");

/** Open the blind Ø8 x 12 hole and settle the camera on POSITION. */
async function open(page: Page): Promise<void> {
  await installSceneProbe(page);
  await openHole(page);
  await waitForCameraStill(page);
}

/**
 * Put KEYBOARD focus on a grip. Not a mouse click, and deliberately: the grip's
 * `pointerdown` takes pointer capture and prevents the default, so a press is
 * always the start of a drag and never a focus change — measured, a click at
 * the grip's centre leaves focus where it was. Keyboard focus is taken the
 * keyboard's way, as every other gauge spec does.
 */
async function focusGrip(page: Page, gaugeId: string): Promise<void> {
  const grip = page.getByTestId(`${gaugeId}-handle`);
  await grip.focus();
  await expect(grip).toBeFocused();
}

/** A unit screen direction along a gauge's drawn track, seat -> grip. */
async function trackDirection(page: Page, gaugeId: string): Promise<Point> {
  const { seat } = await projectedSpine(page, gaugeId);
  const grip = await gripCentre(page, gaugeId);
  const len = Math.hypot(grip.x - seat.x, grip.y - seat.y) || 1;
  return { x: (grip.x - seat.x) / len, y: (grip.y - seat.y) / len };
}

/**
 * Press the grip AT ITS CENTRE with the real mouse and pull it `px` pixels
 * along its own drawn track (negative pulls it back toward the seat).
 */
async function pullGrip(
  page: Page,
  gaugeId: string,
  px: number,
  options: { release?: boolean; steps?: number } = {},
): Promise<void> {
  const dir = await trackDirection(page, gaugeId);
  const from = await gripCentre(page, gaugeId);
  const steps = options.steps ?? 8;
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  for (let i = 1; i <= steps; i += 1) {
    await page.mouse.move(
      from.x + (dir.x * px * i) / steps,
      from.y + (dir.y * px * i) / steps,
    );
  }
  if (options.release !== false) await page.mouse.up();
}

/** One animation frame's reading of everything the hole gauges assert. */
interface Frame {
  frame: number;
  diameterGrabbed: boolean;
  depthGrabbed: boolean;
  /** Each grip's `data-value` — what the instrument is DRAWN at. */
  diameterValue: number | null;
  depthValue: number | null;
  /** Each panel field — the owner's committed number. */
  diameterField: number | null;
  depthField: number | null;
  /** The shared tag's two cells, as displayed. */
  diameterCell: string | null;
  depthCell: string | null;
}

/**
 * Start a per-frame watch of the grips, the fields and the tag cells, read in
 * ONE synchronous turn per frame (an `await` between two reads would be the
 * very skew under measurement). Returns a function that stops it and hands
 * back every frame.
 */
async function watchFrames(page: Page): Promise<() => Promise<Frame[]>> {
  await page.evaluate(
    ({ dia, dep }: { dia: string; dep: string }) => {
      const w = window as unknown as Record<string, unknown>;
      const state = { frames: [] as unknown[], stop: false, n: 0 };
      w["__c9cWatch"] = state;
      const num = (raw: string | null | undefined): number | null => {
        if (raw === null || raw === undefined) return null;
        const v = Number.parseFloat(raw);
        return Number.isFinite(v) ? v : null;
      };
      const cell = (label: string): string | null => {
        const strip = document.querySelector(`[data-testid="${dia}-readout"]`);
        if (strip === null) return null;
        for (const node of Array.from(strip.children)) {
          const parts = node.children;
          if (parts.length < 2) continue;
          if ((parts[0]?.textContent ?? "").trim() !== label) continue;
          const input = node.querySelector("input");
          return input !== null ? input.value : (parts[1]?.textContent ?? "");
        }
        return null;
      };
      const step = () => {
        if (state.stop) return;
        const dh = document.querySelector(`[data-testid="${dia}-handle"]`);
        const eh = document.querySelector(`[data-testid="${dep}-handle"]`);
        const df = document.querySelector<HTMLInputElement>(
          '[data-testid="hole-diameter"]',
        );
        const ef = document.querySelector<HTMLInputElement>(
          '[data-testid="hole-blind-depth"]',
        );
        state.frames.push({
          frame: state.n,
          diameterGrabbed: dh?.getAttribute("data-grabbed") === "true",
          depthGrabbed: eh?.getAttribute("data-grabbed") === "true",
          diameterValue: num(dh?.getAttribute("data-value")),
          depthValue: num(eh?.getAttribute("data-value")),
          diameterField: num(df?.value),
          depthField: num(ef?.value),
          diameterCell: cell("Ø"),
          depthCell: cell("D"),
        });
        state.n += 1;
        requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    },
    { dia: DIAMETER, dep: DEPTH },
  );
  return async () =>
    page.evaluate(() => {
      const w = window as unknown as Record<string, unknown>;
      const state = w["__c9cWatch"] as { frames: unknown[]; stop: boolean };
      state.stop = true;
      return state.frames as Frame[];
    });
}

/** Let the page render `n` more frames — a NAMED settle, not a sleep. */
async function frames(page: Page, n: number): Promise<void> {
  await page.evaluate(
    (count: number) =>
      new Promise<void>((resolve) => {
        let left = count;
        const tick = () => {
          left -= 1;
          if (left <= 0) resolve();
          else requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      }),
    n,
  );
}

/** The longest run of consecutive frames on which `bad` holds. */
function longestRun(readings: Frame[], bad: (f: Frame) => boolean): number {
  let best = 0;
  let run = 0;
  for (const r of readings) {
    run = bad(r) ? run + 1 : 0;
    best = Math.max(best, run);
  }
  return best;
}

const TOL = 1e-3;
const differs = (a: number | null, b: number | null): boolean =>
  a === null || b === null || Math.abs(a - b) > TOL;

/**
 * CONTRACT β, on the property: across the whole gesture AND the frames after
 * the release, the drawn value and the field agree. The gate is a RUN LENGTH
 * below 3 rather than a bare zero for the reason `gauge-release-sync.spec.ts`
 * gives: the grip lives in drei's `Html` root and the field in the page's, so
 * one frame of commit skew is a transition, while a missing echo is a
 * disagreement that PERSISTS — the arrow sprung back and stays sprung.
 */
function expectContractBeta(
  readings: Frame[],
  which: "diameter" | "depth",
): { held: number; released: number } {
  const value = (f: Frame) =>
    which === "diameter" ? f.diameterValue : f.depthValue;
  const field = (f: Frame) =>
    which === "diameter" ? f.diameterField : f.depthField;
  const grabbed = (f: Frame) =>
    which === "diameter" ? f.diameterGrabbed : f.depthGrabbed;

  const lastHeld = [...readings].reverse().find(grabbed);
  const after = readings.slice(readings.lastIndexOf(lastHeld as Frame) + 1);
  expect(lastHeld, `the ${which} grip was never grabbed`).toBeDefined();
  expect(
    after.length,
    `the watch saw no frames after the ${which} release`,
  ).toBeGreaterThan(20);

  const held = value(lastHeld as Frame) as number;
  const final = after[after.length - 1] as Frame;
  const released = value(final) as number;
  const bad = readings.filter((f) => differs(value(f), field(f)));
  const run = longestRun(readings, (f) => differs(value(f), field(f)));
  console.log(
    `[β ${which}] ${readings.length} frames, held ${held} -> released ` +
      `${released}, field ${field(final)}; ${bad.length} disagreeing, ` +
      `longest run ${run}` +
      (bad[0] === undefined
        ? ""
        : ` (first: frame ${bad[0].frame} value=${value(bad[0])} ` +
          `field=${field(bad[0])})`),
  );
  expect(
    released,
    `release the ${which} grip and the instrument must STAY where the drag ` +
      `put it (held ${held}, drawn at ${released} afterwards)`,
  ).toBeCloseTo(held, 3);
  // THE STEADY STATE: the last twenty frames, not the last one — a single
  // final frame cannot tell "settled" from "passing through".
  const unsettled = after.slice(-20).filter((f) => differs(value(f), field(f)));
  expect(
    unsettled.length,
    `after the release the ${which} field never came to hold the value the ` +
      `instrument is drawn at (last frame: drawn ${released}, field ` +
      `${field(final)})`,
  ).toBe(0);
  expect(
    run,
    `the drawn ${which} value and its field disagreed for ${run} consecutive ` +
      `frames — the echo is missing or late`,
  ).toBeLessThan(3);
  return { held, released };
}

test.describe("CRAFT-9c — the Ø gauge", () => {
  test("a real drag at the grip moves the field AND redraws the bore circle", async ({
    page,
  }) => {
    await open(page);
    expect(await viewportStamp(page, "hole-bore-diameter-mm")).toBeCloseTo(
      8,
      2,
    );
    const depthPlaneBefore = await viewportStamp(page, "hole-depth-plane-mm");

    await pullGrip(page, DIAMETER, 45);

    await expect
      .poll(() => diameterField(page), {
        message: "a drag at the Ø grip must move the diameter field",
      })
      .toBeGreaterThan(8);
    const pulled = await diameterField(page);
    await expect
      .poll(() => viewportStamp(page, "hole-bore-diameter-mm"), {
        message:
          "the bore circle must redraw at the dragged Ø — a number that moves alone is a slider",
      })
      .toBeCloseTo(pulled, 1);
    // The Ø drag did not touch the depth plane.
    expect(await viewportStamp(page, "hole-depth-plane-mm")).toBe(
      depthPlaneBefore,
    );
    console.log(`CRAFT-9c Ø: 8 -> ${pulled} mm`);
  });

  test("contract β — data-value and the field agree on every frame", async ({
    page,
  }) => {
    await open(page);
    const stop = await watchFrames(page);
    await pullGrip(page, DIAMETER, 40);
    await frames(page, 60);
    const readings = await stop();
    const { released } = expectContractBeta(readings, "diameter");
    expect(released).toBeGreaterThan(8);
  });

  test("elementFromPoint down the projected track resolves to the Ø gauge", async ({
    page,
  }) => {
    await open(page);
    expectReach(await reach(page, DIAMETER), DIAMETER);
  });

  test("arrow keys step the same value, and the bore follows the key", async ({
    page,
  }) => {
    await open(page);
    await focusGrip(page, DIAMETER);
    const start = await diameterField(page);
    await page.keyboard.press("ArrowUp");
    await expect.poll(() => diameterField(page)).toBeGreaterThan(start);
    const stepped = await diameterField(page);
    const announced = await page
      .getByTestId(`${DIAMETER}-handle`)
      .getAttribute("data-step");
    expect(
      Number.parseFloat(announced ?? "0"),
      "the ANNOUNCED step is the APPLIED step",
    ).toBeCloseTo(stepped - start, 3);
    await expect
      .poll(() => viewportStamp(page, "hole-bore-diameter-mm"))
      .toBeCloseTo(stepped, 2);
    await page.keyboard.press("ArrowDown");
    await expect.poll(() => diameterField(page)).toBeCloseTo(start, 3);
  });
});

test.describe("CRAFT-9c — the depth gauge", () => {
  test("a real drag at the grip moves the field AND slides the depth plane", async ({
    page,
  }) => {
    await open(page);
    expect(await viewportStamp(page, "hole-depth-plane-mm")).toBeCloseTo(12, 2);
    await pullGrip(page, DEPTH, 40);
    await expect
      .poll(() => depthField(page), {
        message: "a drag at the depth grip must move the blind-depth field",
      })
      .toBeGreaterThan(12);
    const pulled = await depthField(page);
    await expect
      .poll(() => viewportStamp(page, "hole-depth-plane-mm"), {
        message: "the depth plane must stand at the dragged depth",
      })
      .toBeCloseTo(pulled, 1);
    // The depth drag did not touch the mouth.
    expect(await viewportStamp(page, "hole-bore-diameter-mm")).toBeCloseTo(
      8,
      2,
    );
    console.log(`CRAFT-9c depth: 12 -> ${pulled} mm`);
  });

  test("contract β — data-value and the field agree on every frame", async ({
    page,
  }) => {
    await open(page);
    const stop = await watchFrames(page);
    await pullGrip(page, DEPTH, 40);
    await frames(page, 60);
    const readings = await stop();
    const { released } = expectContractBeta(readings, "depth");
    expect(released).toBeGreaterThan(12);
  });

  test("elementFromPoint down the projected track resolves to the depth gauge", async ({
    page,
  }) => {
    await open(page);
    expectReach(await reach(page, DEPTH), DEPTH);
  });

  test("arrow keys step the same value, and the plane follows the key", async ({
    page,
  }) => {
    await open(page);
    await focusGrip(page, DEPTH);
    const start = await depthField(page);
    await page.keyboard.press("ArrowUp");
    await expect.poll(() => depthField(page)).toBeGreaterThan(start);
    const stepped = await depthField(page);
    const announced = await page
      .getByTestId(`${DEPTH}-handle`)
      .getAttribute("data-step");
    expect(Number.parseFloat(announced ?? "0")).toBeCloseTo(stepped - start, 3);
    await expect
      .poll(() => viewportStamp(page, "hole-depth-plane-mm"))
      .toBeCloseTo(stepped, 2);
  });
});

test.describe("CRAFT-9c — the companion cell", () => {
  test("dragging depth moves the D cell and never the Ø cell or instrument", async ({
    page,
  }) => {
    await open(page);
    const diameterRod = await spineLengthMm(page, DIAMETER);
    const stop = await watchFrames(page);
    await pullGrip(page, DEPTH, 40);
    await frames(page, 40);
    const readings = await stop();

    const first = readings[0] as Frame;
    const last = readings[readings.length - 1] as Frame;
    const moved = readings.filter(
      (f) =>
        f.diameterCell !== first.diameterCell ||
        differs(f.diameterValue, first.diameterValue) ||
        differs(f.diameterField, first.diameterField),
    );
    console.log(
      `[companion depth] ${readings.length} frames; D cell ` +
        `${first.depthCell} -> ${last.depthCell}; Ø cell ` +
        `${first.diameterCell} throughout (${moved.length} frames moved it)`,
    );
    expect(first.diameterCell, "the Ø cell must be on the tag").toBe("8");
    expect(
      moved.length,
      `a depth drag moved the Ø cell or the Ø instrument on ${moved.length} ` +
        `frames (first: ${JSON.stringify(moved[0])})`,
    ).toBe(0);
    // AND THE D CELL FOLLOWED — the companion is a live cell, not a label.
    expect(last.depthCell).not.toBe(first.depthCell);
    expect(Number.parseFloat(last.depthCell ?? "NaN")).toBeCloseTo(
      last.depthField as number,
      3,
    );
    expect(await spineLengthMm(page, DIAMETER)).toBeCloseTo(diameterRod, 6);
  });

  test("dragging Ø moves the Ø cell and never the D cell or the depth rod", async ({
    page,
  }) => {
    await open(page);
    const depthRod = await spineLengthMm(page, DEPTH);
    const stop = await watchFrames(page);
    await pullGrip(page, DIAMETER, 40);
    await frames(page, 40);
    const readings = await stop();

    const first = readings[0] as Frame;
    const last = readings[readings.length - 1] as Frame;
    const moved = readings.filter(
      (f) =>
        f.depthCell !== first.depthCell ||
        differs(f.depthValue, first.depthValue) ||
        differs(f.depthField, first.depthField),
    );
    console.log(
      `[companion Ø] ${readings.length} frames; Ø cell ` +
        `${first.diameterCell} -> ${last.diameterCell}; D cell ` +
        `${first.depthCell} throughout (${moved.length} frames moved it)`,
    );
    expect(first.depthCell, "the D cell must be on the tag").toBe("12");
    expect(
      moved.length,
      `a Ø drag moved the D cell or the depth value on ${moved.length} ` +
        `frames (first: ${JSON.stringify(moved[0])})`,
    ).toBe(0);
    expect(last.diameterCell).not.toBe(first.diameterCell);
    // The depth arrow stands on the wall, so a Ø drag slides it sideways —
    // stated in `holeAnchor.ts` — but its LENGTH is the depth and must hold.
    expect(await spineLengthMm(page, DEPTH)).toBeCloseTo(depthRod, 6);
  });

  test("Tab walks Ø grip -> Ø cell -> D cell, and a typed depth lands", async ({
    page,
  }) => {
    await open(page);
    await focusGrip(page, DIAMETER);
    await page.keyboard.press("Tab");
    const cells = page.getByTestId(`${DIAMETER}-readout`).locator("input");
    await expect(cells).toHaveCount(1);
    await expect(cells.first()).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(cells.first()).toBeFocused();
    await expect(cells.first()).toHaveValue("12");
    // THE CELL MUST NEVER REWIND UNDER THE TYPIST (DIM-1, the gauge's instance).
    // While the cell was controlled, react-dom put the pre-keystroke text back
    // after every keystroke. The new text lived in r3f's reconciler and reached
    // the `Html` root one macrotask later. Over a selected `12`, `1` was rewound
    // to `12` on every run. A `5` that landed in that window gave `125` and a
    // 125 mm hole: intermittent in CI, and one run in three here at 4x CPU
    // throttle. The depth assertion below catches the lost key only when the
    // key loses the race. This check catches the rewind itself, one task after
    // each keystroke, whichever way the race goes: with the cell controlled it
    // failed 5/5 unthrottled.
    //
    // It watches THIS input node. If the cell remounted, the listener would
    // sit on a detached node, hear nothing, and report no rewinds: a vacuous
    // pass (review S3 on 4b18b93). So it also counts the input events it heard,
    // and that count must be one per typed character before its silence means
    // anything.
    await cells.first().evaluate((input: HTMLInputElement) => {
      const w = window as unknown as {
        __cellRewinds: string[];
        __cellInputs: number;
      };
      const rewinds: string[] = [];
      w.__cellRewinds = rewinds;
      w.__cellInputs = 0;
      let latest = input.value;
      input.addEventListener("input", () => {
        w.__cellInputs += 1;
        latest = input.value;
        setTimeout(() => {
          if (input.value !== latest)
            rewinds.push(`${latest} -> ${input.value}`);
        }, 0);
      });
    });
    await page.keyboard.press("Control+a");
    await page.keyboard.type("15");
    await expect.poll(() => depthField(page)).toBeCloseTo(15, 3);
    const heard = await page.evaluate(() => {
      const w = window as unknown as {
        __cellRewinds: string[];
        __cellInputs: number;
      };
      return { rewinds: w.__cellRewinds, inputs: w.__cellInputs };
    });
    expect(
      heard.inputs,
      "the rewind watch heard one input event per typed character",
    ).toBe(2);
    expect(
      heard.rewinds,
      "the D cell rewound to text older than the last keystroke",
    ).toEqual([]);
    await expect
      .poll(() => viewportStamp(page, "hole-depth-plane-mm"))
      .toBeCloseTo(15, 2);
    expect(await diameterField(page)).toBeCloseTo(8, 3);
  });

  test("Tab on the silent depth grip opens nothing, so Escape still cancels", async ({
    page,
  }) => {
    // The depth gauge carries no tag. Before CRAFT-9c a silent gauge still
    // took Tab and opened an INVISIBLE cell, so the next Escape was spent
    // closing it instead of cancelling the command.
    await open(page);
    await focusGrip(page, DEPTH);
    await page.keyboard.press("Tab");
    await expect(page.getByTestId(`${DEPTH}-handle`)).not.toBeFocused();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("hole-editor")).toHaveCount(0);
  });
});

test.describe("CRAFT-9c — the instruments follow the command", () => {
  test("a through-all hole has a bore and no bottom to pull", async ({
    page,
  }) => {
    await open(page);
    await page.getByTestId("hole-depth-through").click();
    await expect(page.getByTestId(`${DEPTH}-handle`)).toHaveCount(0);
    await expect(page.getByTestId(`${DIAMETER}-handle`)).toHaveCount(1);
    await expect(page.getByTestId("viewport")).not.toHaveAttribute(
      "data-hole-depth-plane-mm",
      /.*/,
    );
    // One cell, and it is the bore.
    await expect(
      page.getByTestId(`${DIAMETER}-readout`).locator(":scope > span"),
    ).toHaveCount(2); // the Ø cell + the unit
    await page.getByTestId("hole-depth-blind").click();
    await expect(page.getByTestId(`${DEPTH}-handle`)).toHaveCount(1);
  });

  test("an armed pick stands the instruments down until it lands", async ({
    page,
  }) => {
    await open(page);
    await page.getByTestId("hole-point-pick").click();
    await expect(page.getByTestId("hole-point-pick")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId(`${DIAMETER}-sleeve`)).toHaveCount(0);
    await expect(page.getByTestId(`${DEPTH}-sleeve`)).toHaveCount(0);
    await page.getByTestId("hole-point-pick").click();
    await expect(page.getByTestId(`${DIAMETER}-handle`)).toHaveCount(1);
  });

  test("the instruments and the preview leave with the command", async ({
    page,
  }) => {
    await open(page);
    await expect(page.getByTestId(`${DIAMETER}-sleeve`)).toHaveCount(1);
    await page.getByTestId("hole-cancel").click();
    await expect(page.getByTestId("hole-editor")).toHaveCount(0);
    await expect(page.getByTestId(`${DIAMETER}-sleeve`)).toHaveCount(0);
    await expect(page.getByTestId(`${DEPTH}-sleeve`)).toHaveCount(0);
    await expect(page.getByTestId("viewport")).not.toHaveAttribute(
      "data-hole-bore-diameter-mm",
      /.*/,
    );
  });

  test("a reopened hole starts from its own default, not the last drag", async ({
    page,
  }) => {
    // ANCHOR B — without the reset the next Hole opens at the dragged Ø.
    await open(page);
    await pullGrip(page, DIAMETER, 40);
    await expect.poll(() => diameterField(page)).toBeGreaterThan(8);
    await page.getByTestId("hole-cancel").click();
    await expect(page.getByTestId("hole-editor")).toHaveCount(0);
    await page.getByTestId("new-hole").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();
    expect(
      await diameterField(page),
      "a new hole opens at its own default Ø6",
    ).toBeCloseTo(6, 6);
  });
});

test.describe("CRAFT-9c — founder captures", () => {
  for (const size of [
    { width: 1280, height: 800 },
    { width: 1440, height: 900 },
  ]) {
    test(`the hole instruments at ${size.width}x${size.height}`, async ({
      page,
    }) => {
      // THE SAME STATE AS THE `craft9c-before-*` PAIR: the same block, part
      // name, Ø8 blind 12 mm hole, iso view, camera settled on POSITION. The
      // before half was taken on the tree without this item, so the only thing
      // that differs between the two pictures is the instruments.
      //
      // There is deliberately no "grip inside the frame" assertion here, unlike
      // the CRAFT-9b capture: it could not be made to fail. Displacing the
      // instruments 70 mm off the part left both grips in frame, because the
      // CRAFT-12 re-fit keeps a live proposal in view; 400 mm hid them, which
      // `openHole`'s own visibility check catches first. A gate nobody can
      // redden is not a gate, so the pair is judged by eye, which is the gate
      // the design mandate names.
      await page.setViewportSize(size);
      await installSceneProbe(page);
      await openHole(page, { name: "Drilled block" });
      await waitForCameraStill(page);
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/craft9c-after-${size.width}.png`,
      });
      // Mid-pull, pointer held: the ladder is the signature and it only shows
      // while the instrument is addressed.
      await pullGrip(page, DEPTH, 30, { release: false });
      await frames(page, 4);
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/craft9c-after-drag-${size.width}.png`,
      });
      await page.mouse.up();
      await expect(page.getByTestId(`${DEPTH}-handle`)).toHaveAttribute(
        "data-grabbed",
        "false",
      );
    });
  }
});
