import type { Locator } from "@playwright/test";

import { expect, test, type Page } from "./fixtures";

import { handClick } from "./hand";
import { calibratePlane, enterSketch, type PlaneMapper } from "./planeMap";
import {
  createPartViaApi,
  SCREENSHOT_DIR,
  seedSession,
  waitForFrames,
} from "./support";

/**
 * THE OTHER HALF OF THE FOUNDER'S SENTENCE — "I still cannot click dimension
 * and actually have it ASSIGN a dimension" (2026-08-14).
 *
 * `sketch-dimension-pick.spec.ts` gates the half `c449235` fixed: the Dimension
 * verb ARMS instead of dead-ending, so the click that could not select a line
 * now opens that line's editor. Until `a810524` it drove the value cell with
 * `locator.fill()` — one DOM mutation, one input event — which is the one
 * gesture no hand makes, and is exactly why the second half of the sentence
 * stayed invisible to it: typed key by key at ordinary speed, the same cell
 * DROPPED keystrokes and committed a number the user never entered (DIM-1,
 * fixed in `a810524` by letting the browser, not React, own the cell's text).
 *
 * So this file types one key at a time, and it owns the per-keystroke property
 * that `fill()` cannot see: at any rhythm a hand types at, the cell keeps every
 * character and the solver receives exactly the number that was typed. Picks
 * are `handClick`s, and the assertion of record is the SOLVED length that comes
 * back from the geometry service — never the label on the glyph, which can be
 * right while the geometry is wrong and vice versa.
 */

const SOLVE_TOLERANCE_MM = 1e-3;

/**
 * How many CONSTRAINT SLOTS the PLACEMENT fills before this spec authors
 * anything. Drawing is no longer free of constraints, and a `glyph-N` testid is
 * an index into the constraint array, so this offset is the difference between
 * addressing the dimension under test and addressing something the tool wrote.
 *
 * The founder's opening draws its rectangle FROM the origin, and two features
 * now author at placement:
 *   · RECT-1 — the rectangle's rigidity set: 4 corner coincidences + 2
 *     horizontal + 2 vertical = 8;
 *   · SNAP-3 — the coincident grounding the snapped corner to the origin, plus
 *     the `fixed` pin `groundDatums` adds behind it = 2.
 *
 * Hence 10. Note the pin is deliberately GLYPH-SUPPRESSED (the user authored
 * none of it), so its slot renders nothing: the glyph ids have a HOLE in them
 * and a wrong offset fails with `element(s) not found`, which reads like the
 * dimension was never authored rather than like an off-by-one.
 */
const PLACEMENT_SLOTS = 10;

/** The n-th constraint THIS SPEC authored (see {@link PLACEMENT_SLOTS}). */
const glyph = (page: Page, index: number) =>
  page.getByTestId(`glyph-${index + PLACEMENT_SLOTS}`);

/**
 * Wider than the measured settle window of the value cell (0.2–1.3 s of
 * main-thread work per keystroke, measured; zero network). Not a "slow test"
 * allowance — it is the separation that lets the first test blame the VERB and
 * never the field.
 */
const SAFE_KEY_GAP_MS = 2500;

/**
 * The widest gap that still counts as an ordinary typing rhythm, measured IN
 * THE PAGE rather than requested. `pressSequentially` awaits the renderer
 * between keys and each keystroke in this cell costs 0.2–1.2 s of main-thread
 * work (measured: two long tasks per key, zero network), so a requested 150 ms
 * routinely lands 400–600 ms apart. Trials slower than this are not evidence
 * about human typing and are discarded before their outcome is read.
 */
const HUMAN_GAP_CEILING_MS = 400;

/**
 * The rhythms swept by the per-keystroke gate, in ms between keys, chosen from
 * where the DIM-1 corruption was MEASURED and not from where it is convenient
 * to type. Two independent measurements of the pre-fix build disagree about
 * which band is deadly — `a810524` recorded every character lost from 0 to
 * 80 ms/key and survival from 120 ms; the QA pass that first characterised it
 * recorded corruption from ~0.2 s to ~0.7 s, widening past 1.4 s under load —
 * so the sweep spans both, and the fast end is where the pre-fix build fails
 * most reliably (ABLATION below). 60 ms/key is a fast typist on a keypad, not
 * a synthetic torture case; the driver below is what makes it a REAL 60 ms.
 */
const TYPING_RHYTHMS_MS = [60, 100, 150, 200, 250, 60];

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
    data: { kind: string; status: string; entities: SolvedEntity[] } | null;
  }>;
}

/** Every solved sketch the gateway has returned for this part, newest last. */
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

/** The solved length of entity `id` in the newest evaluation, or null. */
function latestLength(bodies: EvaluateBody[], id: string): number | null {
  const sketch = bodies[bodies.length - 1]?.features[0];
  if (sketch?.data == null) return null;
  const line = sketch.data.entities.find((e) => e.id === id);
  if (line?.start === undefined || line.end === undefined) return null;
  return Math.hypot(line.end.x - line.start.x, line.end.y - line.start.y);
}

/** Timestamped keydowns seen BY THE FIELD ITSELF, with the value it then held. */
interface Keystroke {
  key: string;
  before: string;
  ms: number;
}

async function installKeyTrace(page: Page): Promise<void> {
  await page.evaluate(() => {
    const w = window as Window & { __dimKeys?: Keystroke[] };
    w.__dimKeys = [];
    const t0 = performance.now();
    document.addEventListener(
      "keydown",
      (event) => {
        const el = document.querySelector<HTMLInputElement>(
          '[data-testid="dimension-input"]',
        );
        if (el !== null && event.target === el) {
          w.__dimKeys?.push({
            key: (event as KeyboardEvent).key,
            before: el.value,
            ms: Math.round(performance.now() - t0),
          });
        }
      },
      true,
    );
  });
}

/** Drain the trace; return each keystroke with the gap that preceded it. */
async function drainKeyTrace(page: Page): Promise<Keystroke[]> {
  return page.evaluate(() => {
    const w = window as Window & { __dimKeys?: Keystroke[] };
    const seen = w.__dimKeys ?? [];
    w.__dimKeys = [];
    return seen;
  });
}

/**
 * Type on a WALL CLOCK, never waiting for the page: what a hand does.
 *
 * `pressSequentially` awaits the renderer between keys, and each keystroke in
 * this cell costs 0.2–1.2 s of main-thread work, so a requested 150 ms lands
 * 400–1300 ms apart and the STIMULUS becomes a function of machine load — which
 * is how the same assertion came back both green and red on one build. Raw CDP
 * dispatches keep the requested rhythm regardless of what the page is doing, so
 * the trial under test is the trial that was asked for. (Both drivers
 * reproduced DIM-1 pre-fix; only this one did so repeatably, which is why it is
 * still the stimulus of record now the property is asserted the other way up:
 * a gate this one can't redden is a gate the other one can't either.)
 */
async function typeOnAWallClock(
  page: Page,
  text: string,
  gapMs: number,
): Promise<void> {
  const cdp = await page.context().newCDPSession(page);
  for (const [index, character] of [...text].entries()) {
    if (index > 0) await new Promise((resolve) => setTimeout(resolve, gapMs));
    const code = `Digit${character}`;
    const vk = character.charCodeAt(0);
    for (const type of ["keyDown", "keyUp"] as const) {
      void cdp.send("Input.dispatchKeyEvent", {
        type,
        ...(type === "keyDown" ? { text: character } : {}),
        key: character,
        code,
        windowsVirtualKeyCode: vk,
        nativeVirtualKeyCode: vk,
      });
    }
  }
  await page.waitForTimeout(3000); // let the last keystroke's work drain
  await cdp.detach();
}

function gapsOf(keys: Keystroke[]): number[] {
  return keys.slice(1).map((k, i) => k.ms - keys[i]!.ms);
}

/**
 * The founder's own opening: draw a 43 x 27 rectangle with the toolbar and
 * LEAVE THE TOOL ARMED, then click a side meaning "select this line". That
 * click cannot select — the rect tool owns it — which is the state the arming
 * fix exists to rescue, so it is asserted rather than avoided.
 */
async function founderOpening(page: Page, at: PlaneMapper): Promise<void> {
  await page.getByTestId("tool-rect").click();
  const a = at({ x: 0, y: 0 });
  const b = at({ x: 43, y: 27 });
  await handClick(page, a.x, a.y);
  await page.mouse.move(b.x, b.y);
  await handClick(page, b.x, b.y);
  await expect(page.getByTestId("draw-dimensions")).toHaveAttribute(
    "data-state",
    "armed",
  );
  const side = at({ x: 21, y: 0 });
  await handClick(page, side.x, side.y);
  await expect(page.getByTestId("selection-readout")).toContainText(
    "nothing selected",
  );
}

/** Constrain > Dimension > Distance, then pick the bottom edge. */
async function dimensionTheBottomEdge(
  page: Page,
  at: PlaneMapper,
): Promise<void> {
  await page.getByTestId("constraint-group-dimensional").click();
  await page.getByTestId("constraint-distance").click();
  await expect(page.getByTestId("constraint-hint")).toHaveText(
    "Click a line to dimension it.",
  );
  // The half-drawn second rectangle is GONE, not merely unmentioned: its live
  // size chip is that rubber band's own readout.
  await expect(page.getByTestId("draw-dimensions")).toHaveCount(0);
  const side = at({ x: 21, y: 0 });
  await handClick(page, side.x, side.y);
  await expect(page.getByTestId("dimension-editor")).toBeVisible();
  await expect(page.getByTestId("dimension-input")).toHaveValue("43");
}

/** Discard whatever is in the editor and get a fresh one on the same edge. */
async function reopenEditorOnBottomEdge(
  page: Page,
  at: PlaneMapper,
): Promise<void> {
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("dimension-editor")).toHaveCount(0);
  await dimensionTheBottomEdge(page, at);
}

/** What the field held after a trial, and the gaps its keys actually landed at. */
interface Trial {
  delay: number;
  got: string;
  gaps: number[];
}

/** One trial of the stimulus: type "125" over the "43" prefill at `delay`. */
async function typeTrial(
  page: Page,
  cell: Locator,
  delay: number,
): Promise<Trial> {
  await cell.focus();
  await drainKeyTrace(page); // discard anything the re-open left behind
  await typeOnAWallClock(page, "125", delay);
  const got = await cell.inputValue();
  return { delay, got, gaps: gapsOf(await drainKeyTrace(page)) };
}

/**
 * Did this trial actually type at a human rhythm? Measured IN THE PAGE, and
 * checked BEFORE the trial's outcome is looked at — a trial whose keys crawled
 * is no evidence about human typing either way, so it is discarded on its gaps
 * alone. That is a retried STIMULUS; no assertion is ever retried here.
 */
function isHumanRhythm(trial: Trial): boolean {
  return (
    trial.gaps.length === 2 && Math.max(...trial.gaps) <= HUMAN_GAP_CEILING_MS
  );
}

test.describe("FOUNDER: a typed dimension reaches the solver", () => {
  /**
   * GATES `c449235`. Keys are spaced well beyond the value cell's settle
   * window, so anything red here is the VERB's fault, not the field's.
   *
   * DO NOT READ THIS LEG AS "typing works". It is deliberately typed slower
   * than any hand, precisely so that it cannot fail for a keystroke-retention
   * reason; that property belongs to the second test and must stay there. Two
   * legs that both type at human speed would leave the arming verb with no
   * gate that fails for its own reason.
   *
   * MUTATION (a build of `c449235^` served from an isolated worktree): fails at
   * `Click a line to dimension it.` — received "Select one line to dimension."
   */
  test("assigns a typed value end to end, and survives a reload", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Typed dimension");
    const evaluations = collectEvaluations(page, part.id);
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 640, y: 560 },
      { x: 940, y: 380 },
    );
    await founderOpening(page, at);
    await dimensionTheBottomEdge(page, at);

    const cell = page.getByTestId("dimension-input");
    await cell.focus();
    await cell.pressSequentially("60", { delay: SAFE_KEY_GAP_MS });
    await expect(cell).toHaveValue("60");
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("dimension-editor")).toHaveCount(0);

    // "Actually ASSIGN a dimension": the label AND the geometry.
    await expect(glyph(page, 0)).toHaveText("60", {
      timeout: 15_000,
    });
    await expect
      .poll(
        () => {
          const length = latestLength(evaluations, "e1");
          return length === null
            ? null
            : Math.abs(length - 60) < SOLVE_TOLERANCE_MM;
        },
        { timeout: 30_000 },
      )
      .toBe(true);

    // CROSS-SURFACE: save, reload, re-open the saved sketch (SKETCH-1) — the
    // dimension is still 60. A glyph that only survives until the next page
    // load is not an assigned dimension.
    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
      timeout: 30_000,
    });
    await page.reload();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await page.getByTestId("feature-row").first().click({ button: "right" });
    await page.getByTestId("tree-ctx-edit").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
    await expect(
      page.locator('[data-testid^="glyph-"][data-kind="distance"]'),
    ).toHaveText(["60"]);
  });

  /**
   * THE PROPERTY, and the gate on the DIM-1 fix (`a810524`): at an ordinary
   * typing rhythm the value cell keeps every keystroke, and the number that
   * reaches the SOLVER is the number that was typed.
   *
   * What it is standing guard over: the cell used to be CONTROLLED, so React
   * restored it from a render that predated the keystroke; each character was
   * composed against the stale "43" prefill and the wrong number was committed
   * silently — no error, and a glyph that agreed with the corruption.
   *
   * WHY A SWEEP OF RHYTHMS AND NOT ONE TYPED NUMBER. The corruption was a
   * RACE, so it was never monotonic in typing speed: some rhythms beat the
   * revert and survived while their neighbours did not, and the deadly band
   * moved with machine load. One typed number therefore only ever proves the
   * field at the one rhythm it used, and a survivor is not evidence — an
   * absence of casualties across `TYPING_RHYTHMS_MS` is.
   *
   * ABLATION (2026-08-15) — these exact assertions, unchanged, against a build
   * with the `ConstraintGlyphs.tsx` + `packages/design` hunks of `a810524`
   * reverted in the worktree:
   *
   *   Error: keystrokes were dropped at an ordinary typing rhythm (DIM-1):
   *     [{"delay":60,"got":"435","gaps":[81,86]},
   *      {"delay":60,"got":"435","gaps":[81,87]}]
   *   Expected length: 0 / Received length: 2
   *
   * Both 60 ms trials lost every character but the last, to the founder's own
   * "435"; restored, all six trials read "125" and the solver returned exactly
   * 125 mm. THE FAST END IS WHAT MAKES THIS A GATE: swept at 150/200/250 ms
   * only — the band this file used while it characterised the open defect —
   * the same ablation corrupted just 1 trial of 6, i.e. a broken build would
   * have gone green roughly a third of the time. Do not narrow the band back
   * without re-running the ablation.
   *
   * The gap-fidelity check is what stops this passing for free — a trial whose
   * keys crawled is not a trial about human typing, and it is discarded on its
   * GAPS alone, before its outcome is looked at. That is a retried STIMULUS,
   * never a retried assertion.
   */
  test("an ordinary typing rhythm commits exactly the number typed (DIM-1)", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Typed fast");
    const evaluations = collectEvaluations(page, part.id);
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 640, y: 560 },
      { x: 940, y: 380 },
    );
    await founderOpening(page, at);
    await dimensionTheBottomEdge(page, at);

    const cell = page.getByTestId("dimension-input");
    await installKeyTrace(page);
    const trials: Trial[] = [];
    for (const [index, delay] of TYPING_RHYTHMS_MS.entries()) {
      if (index > 0) await reopenEditorOnBottomEdge(page, at);
      trials.push(await typeTrial(page, cell, delay));
    }
    console.log(`typing trials: ${JSON.stringify(trials)}`);

    // FIDELITY: only trials that actually typed at a human rhythm count. This
    // is what stops the test agreeing for free when load stretches the keys.
    const human = trials.filter(isHumanRhythm);
    expect(
      human.length,
      "no trial landed its keys within the human window — this run did not test human typing",
    ).toBeGreaterThanOrEqual(3);

    // EVERY human-rhythm trial keeps what was typed. Pre-fix these read "435"
    // (or bare "43"): the cell reverted to its prefill between keys, so each
    // character was composed against a stale value.
    const wrong = human.filter((t) => t.got !== "125");
    expect(
      wrong,
      `keystrokes were dropped at an ordinary typing rhythm (DIM-1): ${JSON.stringify(wrong)}`,
    ).toHaveLength(0);

    // …and the typed number is not merely displayed, it is COMMITTED: the
    // solver moves the edge to exactly the length that was typed. Re-typed on a
    // fresh editor at the fastest rhythm this run actually landed — where the
    // pre-fix build failed every time — so the committed value belongs to a
    // trial measured here rather than to whatever the last loop left behind.
    // The RETRY is of the stimulus: an attempt whose keys crawled is thrown
    // away before its value is read, and the assertions below run once.
    let commitTrial: Trial | null = null;
    for (let attempt = 0; attempt < 3 && commitTrial === null; attempt += 1) {
      await reopenEditorOnBottomEdge(page, at);
      const trial = await typeTrial(page, cell, human[0]!.delay);
      if (isHumanRhythm(trial)) commitTrial = trial;
    }
    expect(
      commitTrial,
      "the committing leg never landed its keys within the human window — this run did not test human typing",
    ).not.toBeNull();
    expect(
      commitTrial!.got,
      `the field held ${JSON.stringify(commitTrial!.got)} after typing "125" with gaps ${JSON.stringify(commitTrial!.gaps)}`,
    ).toBe("125");

    await page.keyboard.press("Enter");
    await expect(page.getByTestId("dimension-editor")).toHaveCount(0);
    await expect(glyph(page, 0)).toHaveText("125", {
      timeout: 15_000,
    });
    await expect
      .poll(
        () => {
          const length = latestLength(evaluations, "e1");
          return length === null
            ? null
            : Math.abs(length - 125) < SOLVE_TOLERANCE_MM;
        },
        { timeout: 30_000 },
      )
      .toBe(true);
    console.log(
      `committed geometry for a typed "125": solver returned ${String(
        latestLength(evaluations, "e1"),
      )} mm`,
    );
  });
});

/**
 * Helical-gear gap G2 — EXACT PLACEMENT.
 *
 * The product test placed 24 involute fit points by reading the DRO at
 * 0.024 mm/px, because there was no way to type a coordinate and the snap grid
 * was fixed at 1 mm (`setSnapStep` had no caller). The UI gear's pitch-circle
 * tooth thickness came out 0.029 mm off.
 *
 * Now, in the FB-16 idiom (type where the intent forms): with a point-placing
 * tool live, a digit (or a minus) opens X / Y cells at the cursor, Tab moves
 * between them and Enter places the point exactly there. With one point
 * selected, the same keys move that point. The grid step is a choice on the
 * sketch band. Every assertion reads the PERSISTED sketch, typed key by key.
 */
interface PersistedLine {
  id: string;
  kind: string;
  start?: { x: number; y: number };
  end?: { x: number; y: number };
}

async function typeKeys(page: Page, keys: readonly string[]): Promise<void> {
  for (const key of keys) await page.keyboard.press(key);
}

/** Finish the (new) sketch and return its persisted entities. */
async function finishAndRead(
  page: Page,
  token: string,
  partId: string,
): Promise<PersistedLine[]> {
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
  const response = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const body = (await response.json()) as {
    features: Array<{ feature: { params: { entities: PersistedLine[] } } }>;
  };
  return body.features[0]?.feature.params.entities ?? [];
}

async function openSketchXY(page: Page, name: string) {
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, name);
  await page.goto(`/parts/${part.id}`);
  await enterSketch(page, "XY");
  const at = await calibratePlane(
    page,
    { x: 700, y: 600 },
    { x: 1000, y: 400 },
  );
  return { token, partId: part.id, at };
}

test.describe("helical-gear G2: exact placement", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("typed X / Y places a line's two points exactly, off every grid", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const { token, partId, at } = await openSketchXY(page, "Typed points");
    await page.keyboard.press("l");
    const somewhere = at({ x: 5, y: 5 });
    await page.mouse.move(somewhere.x, somewhere.y);

    // The first digit opens the cells at the cursor and lands in X. Typed at
    // once, as a hand types a number it already knows.
    await typeKeys(page, ["1", "2", ".", "5", "Tab", "-", "3", ".", "2", "5"]);
    // Founder pair (UPDATE_SCREENSHOTS only), before any assertion so the
    // pre-fix tree produces its half; a named settle of painted frames.
    await waitForFrames(page, 6);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-gear-fix-g2-after.png`,
    });
    const x = page.getByTestId("point-entry-x");
    const y = page.getByTestId("point-entry-y");
    await expect(x).toHaveValue("12.5");
    await expect(y).toHaveValue("-3.25");
    await page.keyboard.press("Enter");
    await expect(x).toHaveCount(0);

    // The line's second point, typed the same way.
    await typeKeys(page, ["4", "0", ".", "1", "2", "3", "Tab", "7"]);
    await page.keyboard.press("Enter");
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");

    const entities = await finishAndRead(page, token, partId);
    const lines = entities.filter((e) => e.kind === "line");
    expect(lines, JSON.stringify(entities)).toHaveLength(1);
    expect(lines[0]?.start).toEqual({ x: 12.5, y: -3.25 });
    expect(lines[0]?.end).toEqual({ x: 40.123, y: 7 });
  });

  test("with one point selected, typed X / Y moves that point", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const { token, partId, at } = await openSketchXY(page, "Typed move");
    // A slanted line, so nothing is inferred that would fight the move. Drawn
    // with zero-drift clicks on purpose: this test is about WHERE the points
    // land, and a hand's 6 px drift crosses a grid cell at this zoom (the
    // gesture itself is click-drift.spec.ts's subject).
    await page.keyboard.press("l");
    const a = at({ x: 22, y: 11 });
    const b = at({ x: 32, y: 16 });
    await page.mouse.click(a.x, a.y);
    await page.mouse.move(b.x, b.y);
    await page.mouse.click(b.x, b.y);
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");

    await handClick(page, b.x, b.y); // the END point
    await expect(page.getByTestId("selection-readout")).toContainText("1 pt");
    await typeKeys(page, ["4", "0", ".", "5", "Tab", "1", "9", ".", "7", "5"]);
    await expect(page.getByTestId("point-entry-x")).toHaveValue("40.5");
    await page.keyboard.press("Enter");

    const entities = await finishAndRead(page, token, partId);
    const line = entities.find((e) => e.kind === "line");
    expect(line?.start).toEqual({ x: 22, y: 11 });
    expect(line?.end).toEqual({ x: 40.5, y: 19.75 });
  });

  test("the grid step is a choice: 0.5 mm puts a click on the half millimetre", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const { token, partId, at } = await openSketchXY(page, "Grid step");
    const step = page.getByTestId("sketch-grid-step");
    await expect(step).toBeVisible();
    await step.selectOption({ label: "0.5 mm" });
    await expect(page.getByTestId("dro-snap")).toContainText("0.5 mm");

    // (7.3, 4.2) is 0.3 mm from the 1 mm grid's (7, 4) and 0.2 mm from the
    // half-millimetre grid's (7.5, 4): only a 0.5 mm step lands on 7.5.
    await page.keyboard.press("l");
    const a = at({ x: 7.3, y: 4.2 });
    const b = at({ x: 21.3, y: 12.2 });
    await page.mouse.click(a.x, a.y);
    await page.mouse.move(b.x, b.y);
    await page.mouse.click(b.x, b.y);
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");

    const entities = await finishAndRead(page, token, partId);
    const line = entities.find((e) => e.kind === "line");
    expect(line?.start).toEqual({ x: 7.5, y: 4 });
    expect(line?.end).toEqual({ x: 21.5, y: 12 });
  });
});
