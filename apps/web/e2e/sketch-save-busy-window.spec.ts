import { expect, test, type Page } from "./fixtures";

import { clickPlane, calibratePlane, enterSketch } from "./planeMap";
import { createPartViaApi, seedSession } from "./support";

/**
 * THE ~280 ms IN WHICH SAVE DID NOTHING.
 *
 * `sketch-save` carried `disabled={saving || …}`, where `saving` is
 * `syncPending` — raised by the DEBOUNCED AUTOSAVE for the length of a write.
 * Independent QA measured the button going `aria-disabled="true"` 208 / 236 /
 * 244 ms after an edit settles and clearing at 481 / 513 / 526 ms, three runs
 * for three runs. A real `page.mouse.click` at the button's own centre inside
 * that window resolved to `sketch-save` — the event reached the button, with no
 * overlay in the way — and the strip was still mounted thirty seconds later.
 * `ToolButton` renders `disabled` as `aria-disabled` plus a handler that
 * returns early, so the intent was dropped on the floor: no queue, no re-arm,
 * no message.
 *
 * That is a flow defect, not a cosmetic one. The design mandate names this exact
 * class: "No dead ends, no ambiguous exits. A key that sometimes saves and
 * sometimes discards does more than risk work: it makes people hesitate at every
 * step, which is what actually destroys flow." A Save that works nine times in
 * ten and silently does nothing the tenth teaches distrust of every click.
 *
 * TWO INDEPENDENT ASSERTIONS, because they fail for different reasons.
 *
 * (1) THE INVARIANT — sampled every frame for the whole save cycle, so it cannot
 *     miss the window the way a poll from Node can: while a save is in flight,
 *     Save is never `aria-disabled`. This is the race-free half. The old build
 *     produced a run of disabled frames ~280 ms long and this reports their
 *     count and duration rather than a bare boolean.
 *
 * (2) THE USER'S OWN MECHANISM — a real `page.mouse.click` at the button's
 *     centre, dispatched while `aria-busy="true"`, must close the strip. Not
 *     `locator.click()`: that waits out the very window under test and would
 *     turn this gate into a tautology (CLAUDE.md's "an assertion that cannot
 *     observe the failure mode" family). Not a retry loop either — two specs
 *     already carry one as a WORKAROUND for this defect, and a retry is exactly
 *     what makes a dead end invisible.
 *
 * WHY THE SAVE IS DELIBERATELY SLOWED. The real window is ~280 ms, and a CDP
 * round trip here costs 101-189 ms, so aiming at it from Node is a coin flip —
 * a flaky gate is a muted gate. Holding the PATCH open for
 * {@link HELD_SAVE_MS} makes the busy window deterministic WITHOUT weakening
 * the claim: a slow network is an ordinary user condition, and it makes the old
 * defect strictly WORSE (a multi-second dead Save instead of a quarter second).
 * The gate is harder to pass after the slowdown, not easier, which is the only
 * direction a test fixture is allowed to move.
 *
 * The bound-sketch path is the one under test because it is the one the field
 * reports came from: a bound sketch saves live, so every edit arms the autosave
 * and the hole reopens continuously. See the retry helpers in
 * `sketch-origin-constraint.spec.ts` and `sketch-snap-coincident.spec.ts`.
 */

/**
 * How long the feature write is held open. Long enough that the busy window
 * cannot be missed across a CDP round trip (~190 ms worst case measured here),
 * short enough to leave the 60 s per-test budget intact.
 */
const HELD_SAVE_MS = 2_500;

/** One sample of the Save button's gate state, taken in the page. */
interface GateSample {
  ms: number;
  disabled: boolean;
  busy: boolean;
}

declare global {
  interface Window {
    __saveGate?: GateSample[];
  }
}

/**
 * Sample `sketch-save`'s gate attributes every animation frame, recording only
 * transitions. A `MutationObserver` would miss a React re-render that replaces
 * the node; re-reading the selector each frame cannot.
 */
async function watchSaveGate(page: Page): Promise<void> {
  await page.evaluate(() => {
    window.__saveGate = [];
    const t0 = performance.now();
    let last = "";
    const tick = () => {
      const el = document.querySelector('[data-testid="sketch-save"]');
      if (el !== null) {
        const disabled = el.getAttribute("aria-disabled") === "true";
        const busy = el.getAttribute("aria-busy") === "true";
        const key = `${String(disabled)}|${String(busy)}`;
        if (key !== last) {
          last = key;
          window.__saveGate?.push({
            ms: performance.now() - t0,
            disabled,
            busy,
          });
        }
      }
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

/** Total ms spent `aria-disabled` across the recorded samples. */
function disabledMs(samples: GateSample[]): number {
  let total = 0;
  for (let i = 0; i < samples.length; i += 1) {
    const sample = samples[i];
    if (sample === undefined || !sample.disabled) continue;
    const next = samples[i + 1];
    if (next !== undefined) total += next.ms - sample.ms;
  }
  return total;
}

test.describe("SAVE-CLICK — a click during the autosave is not discarded", () => {
  test("a real click inside the busy window finishes the sketch", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Save click");
    await page.goto(`/parts/${part.id}`);

    // ---- A sketch that is BOUND, so every later edit arms the autosave ----
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 640, y: 560 },
      { x: 940, y: 380 },
    );
    await page.keyboard.press("r");
    await clickPlane(page, at, { x: 0, y: 0 });
    await clickPlane(page, at, { x: 40, y: 25 });
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
    await expect(page.getByTestId("feature-row")).toHaveCount(1);

    // ---- Reopen it: now `featureId !== null` and edits save live ----
    await page.getByTestId("feature-row").first().click({ button: "right" });
    await page.getByTestId("tree-ctx-edit").click();
    await expect(page.getByTestId("sketch-strip")).toBeVisible();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY");

    // Hold the write open so the busy window is deterministic (see the header).
    await page.route(
      `**/api/v1/parts/${part.id}/features/**`,
      async (route) => {
        if (route.request().method() !== "PATCH") {
          await route.fallback();
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, HELD_SAVE_MS));
        await route.fallback();
      },
    );

    await watchSaveGate(page);

    // One more edit arms the debounced autosave.
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 60, y: 0 });
    await clickPlane(page, at, { x: 60, y: 25 });
    await page.keyboard.press("Escape");

    // ---- Wait for the window to OPEN (not to close) ----
    await expect
      .poll(
        async () =>
          await page
            .getByTestId("sketch-save")
            .getAttribute("aria-busy")
            .catch(() => null),
        {
          message:
            "the autosave never reported itself busy, so this run never entered the window under test — the gate measured nothing",
          timeout: 30_000,
        },
      )
      .toBe("true");

    // ---- The user's own mechanism, inside the window ----
    //
    // The dispatch-time state is captured in the SAME evaluate that computes
    // the hit point, so the failure message can answer the one question a red
    // run here actually raises: was the button disabled at the instant the
    // click was dispatched, or had the window already closed underneath us?
    // That residue costs nothing on a green run and turns the next red into an
    // answer instead of an investigation.
    const handle = await page.getByTestId("sketch-save").elementHandle();
    const dispatch = await page.evaluate((el) => {
      const target = el as Element;
      const r = target.getBoundingClientRect();
      const cx = r.x + r.width / 2;
      const cy = r.y + r.height / 2;
      const hit = document.elementFromPoint(cx, cy);
      const name = (x: Element | null): string => {
        if (x === null) return "nothing";
        const tagged = x.closest("[data-testid]");
        return `${x.tagName.toLowerCase()}${
          tagged === null ? "" : `[${tagged.getAttribute("data-testid")}]`
        }`;
      };
      return {
        cx,
        cy,
        width: r.width,
        height: r.height,
        ariaDisabled: target.getAttribute("aria-disabled"),
        ariaBusy: target.getAttribute("aria-busy"),
        reached: hit !== null && target.contains(hit),
        resolvesTo: name(hit),
      };
    }, handle);
    await handle?.dispose();

    const where = `aria-disabled=${String(dispatch.ariaDisabled)} aria-busy=${String(
      dispatch.ariaBusy,
    )} box=${dispatch.width.toFixed(1)}x${dispatch.height.toFixed(1)} hit=${dispatch.resolvesTo}`;

    // The click must reach the button itself, or a pass would prove nothing
    // about Save (CLAUDE.md's zero-area / occluded-target family).
    expect(
      dispatch.width * dispatch.height,
      `sketch-save has no area at dispatch — ${where}`,
    ).toBeGreaterThan(0);
    expect(
      dispatch.reached,
      `a pointer aimed at sketch-save's centre lands elsewhere — ${where}`,
    ).toBe(true);

    await page.mouse.click(dispatch.cx, dispatch.cy);

    // THE DEFECT, IN ONE ASSERTION: the strip stayed mounted forever.
    await expect(
      page.getByTestId("sketch-strip"),
      `the click was delivered to sketch-save inside the autosave's busy window and the strip did not close (${where}). A click that lands on the control and changes nothing is the silent dead end SAVE-CLICK fixed.`,
    ).toHaveCount(0, { timeout: 30_000 });

    // ---- The invariant, sampled every frame ----
    const samples = await page.evaluate(() => window.__saveGate ?? []);
    const sawBusy = samples.some((s) => s.busy);
    expect(
      sawBusy,
      "no busy frame was ever sampled, so the invariant below is vacuous",
    ).toBe(true);
    const disabledFrames = samples.filter((s) => s.disabled);
    expect(
      disabledFrames.length,
      `Save went aria-disabled for ${disabledMs(samples).toFixed(0)} ms across ${
        disabledFrames.length
      } transition(s) while a save was in flight. A debounce is an implementation detail the user cannot see; gating the one control that ends a sketch on it is the dead end this spec exists to catch. Samples: ${JSON.stringify(samples)}`,
    ).toBe(0);

    // And the work is really in the part: one sketch, still one sketch.
    await expect(page.getByTestId("feature-row")).toHaveCount(1);
  });
});
