import { expect, test, type Page } from "./fixtures";

import { handClick } from "./hand";
import { calibratePlane, enterSketch, type PlaneMapper } from "./planeMap";
import { createPartViaApi, seedSession } from "./support";

/**
 * THE OTHER HALF OF THE FOUNDER'S SENTENCE — "I still cannot click dimension
 * and actually have it ASSIGN a dimension" (2026-08-14).
 *
 * `sketch-dimension-pick.spec.ts` gates the half `c449235` fixed: the Dimension
 * verb ARMS instead of dead-ending, so the click that could not select a line
 * now opens that line's editor. It then drives the value cell with
 * `locator.fill()` — one DOM mutation, one input event — which is the one
 * gesture no hand makes, and is exactly why the second half of the sentence
 * stayed invisible to it. Typed key by key at ordinary speed, the same cell
 * drops keystrokes and COMMITS a number the user never entered (DIM-1).
 *
 * So this file types with `pressSequentially`. Picks are `handClick`s, and the
 * assertion of record is the SOLVED length that comes back from the geometry
 * service — never the label on the glyph, which can be right while the geometry
 * is wrong and vice versa.
 */

const SOLVE_TOLERANCE_MM = 1e-3;

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
 * the trial under test is the trial that was asked for. (Both drivers reproduce
 * DIM-1; only this one reproduces it *repeatably*.)
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

test.describe("FOUNDER: a typed dimension reaches the solver", () => {
  /**
   * GATES `c449235`. Keys are spaced well beyond the value cell's settle
   * window, so anything red here is the VERB's fault, not the field's.
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
    await expect(page.getByTestId("glyph-0")).toHaveText("60", {
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
   * CHARACTERISES DIM-1 (P0, open): the value cell reverts to its prefill
   * between keystrokes, so a number typed at an ordinary rhythm is composed
   * against a stale value and the WRONG number reaches the solver — silently,
   * with no error and a glyph that agrees with the corruption.
   *
   * WHY REPEATED TRIALS AND A COUNT, NOT ONE ASSERTION. The corruption is a
   * RACE, and measurement showed it is not monotonic in typing speed: keys
   * landing ~155 ms apart beat the revert and survive, keys ~0.2-0.7 s apart
   * land after the revert but before the real update and are corrupted, and
   * keys ~0.8 s+ apart survive again (the window widens under load, where gaps
   * of 1.4 s still corrupted). A single-shot assertion on a race is flaky in
   * whichever direction it is written; a count over trials spanning the window
   * is not. Measured on this build: 5 of 8 trials at a 150 ms nominal rhythm
   * mis-committed, so "at least one of six" carries a ~0.3 % false-green risk.
   *
   * Written to pass TODAY and to go RED the day the field is fixed, which is
   * the signal to flip the assertion to `expect(wrong).toHaveLength(0)`.
   * Deliberately NOT `test.fail()`: that marker swallows an earlier breakage (a
   * regression in arming would read as "expected failure"), whereas every
   * assertion here fails for its own reason. The gap-fidelity assertion is what
   * stops it passing for free — a trial whose keys crawled is not a trial about
   * human typing, and it is discarded on its GAPS alone, before its outcome is
   * looked at. That is a retried STIMULUS, never a retried assertion.
   */
  test("OPEN DEFECT (DIM-1): an ordinary typing rhythm commits a number nobody typed", async ({
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
    const trials: { delay: number; got: string; gaps: number[] }[] = [];
    for (const [index, delay] of [150, 200, 250, 150, 200, 250].entries()) {
      if (index > 0) {
        await page.keyboard.press("Escape");
        await expect(page.getByTestId("dimension-editor")).toHaveCount(0);
        await dimensionTheBottomEdge(page, at);
      }
      await cell.focus();
      await drainKeyTrace(page); // discard anything the re-open left behind
      await typeOnAWallClock(page, "125", delay);
      const got = await cell.inputValue();
      const keys = await drainKeyTrace(page);
      trials.push({ delay, got, gaps: gapsOf(keys) });
    }
    console.log(`DIM-1 trials: ${JSON.stringify(trials)}`);

    // FIDELITY: only trials that actually typed at a human rhythm count. This
    // is what stops the test agreeing for free when load stretches the keys.
    const human = trials.filter(
      (t) => t.gaps.length === 2 && Math.max(...t.gaps) <= HUMAN_GAP_CEILING_MS,
    );
    expect(
      human.length,
      "no trial landed its keys within the human window — this run did not test human typing",
    ).toBeGreaterThanOrEqual(3);

    // TODAY: most trials read "435" — the cell reverts to its "43" prefill, so
    // each character is composed against a stale value and only the last
    // survives. WHEN FIXED: this reddens; assert `wrong` is empty.
    const wrong = human.filter((t) => t.got !== "125");
    expect(
      wrong.length,
      `DIM-1 appears fixed — every human-rhythm trial kept its keystrokes: ${JSON.stringify(human)}`,
    ).toBeGreaterThan(0);

    // …and the wrong number is not merely displayed, it is COMMITTED: the
    // solver moves the edge to a length nobody asked for. Re-typed here on a
    // fresh editor so the committed value belongs to a known trial.
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("dimension-editor")).toHaveCount(0);
    await dimensionTheBottomEdge(page, at);
    await cell.focus();
    await drainKeyTrace(page);
    await typeOnAWallClock(page, "125", wrong[0]!.delay);
    const committed = await cell.inputValue();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("dimension-editor")).toHaveCount(0);
    test.skip(
      committed === "125",
      "this trial happened to win the race — the committed-geometry leg needs a corrupted one",
    );
    await expect
      .poll(
        () => {
          const length = latestLength(evaluations, "e1");
          return length === null ? null : Math.abs(length - 125) > 1;
        },
        { timeout: 30_000 },
      )
      .toBe(true);
    console.log(
      `DIM-1 committed geometry for a typed "125": field held "${committed}", solver returned ${String(
        latestLength(evaluations, "e1"),
      )} mm`,
    );
  });
});
