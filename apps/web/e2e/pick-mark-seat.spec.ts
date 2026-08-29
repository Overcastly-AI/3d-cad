/**
 * PICKMARK-OCCLUDE-1 — A PICK DIAMOND SITS WHERE ITS EDGE ANSWERS, OR IT IS NOT
 * DRAWN THERE.
 *
 * ## What was measured, and what this pins
 *
 * `docs/AUDIT-PRODUCT.md` R-8's other sentence — "several sitting mid-FACE
 * rather than on any visible edge" — is a different defect from the missing
 * hover highlight SEL-8 closed, with a different cause. Measured on the same
 * coupling with every mark's `pointer-events` disabled so the BAND answers at
 * each mark's own centre: **8 of 21 agreed**, 8 read nothing at all (the mark
 * floats over material that hides its edge) and 5 resolved to a DIFFERENT edge
 * — click the mark and you pick edge 1, click one pixel outside it and you pick
 * edge 6. Two hit-tests for one entity, disagreeing about reachability.
 *
 * After: **every mark that is DRAWN agrees, 10 of 10**, and the eleven that
 * cannot be made to agree anywhere along their edge are not drawn there at all.
 * So the assertion below is deliberately two-sided, because either half alone
 * is satisfiable by cheating: hiding every mark would pass a "drawn marks
 * agree" test, and leaving them all at their mid-span would pass a "the marks
 * are all still here" test.
 *
 * ## Why the mute needs the WRAPPER too
 *
 * The census asks what the BAND answers under each mark, so the marks must be
 * out of the way — and drei's `Html` portals into the SAME container that holds
 * the canvas, so muting an ancestor too far up kills the band as well. The
 * first run of this measurement reported 0/21 for exactly that reason. The
 * helper stops at the first ancestor that also contains the canvas, and the
 * spec proves the mute did not break the band before it trusts a single reading.
 */
import { expect, test, type Page } from "./fixtures";

import { seedShaftCoupling } from "./partSeed";
import {
  createPartViaApi,
  distinctCanvasColors,
  expectSeatsSettled,
  SCREENSHOT_DIR,
  seedSession,
  waitForFrames,
} from "./support";

/**
 * The agreement floor. Measured before: 8 of 21 marks agreed with the band at
 * their own centre. Anything at or below that is not an improvement, so the
 * gate is "more than the defect scored" rather than a tuned number.
 */
const AGREEMENT_BEFORE = 8;

/**
 * How much more main-thread blocking one orbit may cost with 21 marks mounted
 * and their seats being recomputed, relative to the SAME orbit with no marks.
 *
 * A ratio and not a millisecond figure: see the A/B comment in the perf test.
 * Measured here at 1.0-1.2x; 2.0 leaves room for a loaded CI shard while still
 * failing a per-frame raycast per mark, which is what the budget prevents.
 */
const ORBIT_COST_CEILING = 2.0;

interface MarkBox {
  id: string;
  index: number;
  label: string;
  buried: boolean;
  cx: number;
  cy: number;
}

async function markBoxes(page: Page, prefix: string): Promise<MarkBox[]> {
  return page.evaluate(
    (p) =>
      [...document.querySelectorAll(`[data-testid^="${p}"]`)].map((el) => {
        const r = el.getBoundingClientRect();
        const id = el.getAttribute("data-testid") ?? "?";
        return {
          id,
          index: Number(id.replace(p, "")),
          label: el.getAttribute("aria-label") ?? "",
          buried: el.getAttribute("data-buried") === "true",
          cx: Math.round((r.left + r.right) / 2),
          cy: Math.round((r.top + r.bottom) / 2),
        };
      }),
    prefix,
  );
}

/**
 * Take every mark out of the pointer's path — the mark itself AND the drei
 * `Html` wrappers around it, stopping BEFORE the ancestor that also contains
 * the canvas, which is the r3f container and would take the band down with it.
 */
async function muteMarks(page: Page, prefix: string): Promise<number> {
  return page.evaluate((p) => {
    const canvas = document.querySelector('[data-testid="viewport"] canvas');
    let muted = 0;
    for (const el of document.querySelectorAll(`[data-testid^="${p}"]`)) {
      let node: HTMLElement | null = el as HTMLElement;
      while (node !== null && !node.contains(canvas)) {
        node.style.pointerEvents = "none";
        muted += 1;
        node = node.parentElement;
      }
    }
    return muted;
  }, prefix);
}

/** What the band answers at one point, with the pointer really there. */
async function bandAt(
  page: Page,
  x: number,
  y: number,
): Promise<string | null> {
  await page.mouse.move(x, y);
  await waitForFrames(page, 2);
  return page.getByTestId("viewport").getAttribute("data-edge-pick-hover");
}

async function openCouplingWithFilletArmed(page: Page): Promise<void> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Shaft coupling");
  await seedShaftCoupling(page, account.token, part.id);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 60_000,
  });
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
    .toBeGreaterThan(16);

  const viewport = page.getByTestId("viewport");
  await viewport.evaluate((node) => {
    node.dataset["fitRect"] = "";
  });
  await page.getByTestId("view-fit").click();
  await expect(viewport).not.toHaveAttribute("data-fit-rect", "", {
    timeout: 20_000,
  });
  await waitForFrames(page, 6);

  await expect(page.getByTestId("new-fillet")).toBeEnabled({ timeout: 30_000 });
  await page.getByTestId("new-fillet").click();
  await expect(page.getByTestId("fillet-editor")).toBeVisible();
  await page.getByTestId("fillet-mode-pick").click();
  await expect(
    page.locator('[data-testid^="edge-pick-"]').first(),
  ).toBeAttached({ timeout: 20_000 });
  // The seats are placed over several frames under a fixed per-frame hit-test
  // budget, so a fixed number of frames would census a half-drained pass.
  await expectSeatsSettled(page, "fillet armed");
}

test.describe("PICKMARK-OCCLUDE-1 — the diamond and the band agree", () => {
  test("every drawn mark addresses its own edge, and the rest are not drawn there", async ({
    page,
  }) => {
    // 21 settled pointer moves plus the orbit leg; the config's default is one
    // slow shard away from a false red.
    test.setTimeout(300_000);
    await openCouplingWithFilletArmed(page);
    const viewport = page.getByTestId("viewport");

    // The fixture, asserted — if this count moves the part changed and none of
    // the numbers below are comparable with the audit's.
    await expect(page.locator('[data-testid^="edge-pick-"]')).toHaveCount(21);

    // NON-VACUITY, FIRST HALF: the marks must still all be there. A fix that
    // deleted them would pass every agreement assertion below.
    const before = await markBoxes(page, "edge-pick-");
    expect(before.length).toBe(21);
    for (const mark of before) {
      expect(mark.label).toMatch(/^Edge \d+, /);
    }

    const muted = await muteMarks(page, "edge-pick-");
    expect(muted).toBeGreaterThan(0);

    // NON-VACUITY, SECOND HALF: prove the mute left the BAND alive. Without
    // this, "no mark disagrees" is satisfied by a hit-test that answers
    // nothing anywhere — which is precisely what an over-broad mute produces,
    // and what made the first run of this measurement read 0/21.
    const box = await viewport.boundingBox();
    const columnX = Math.round((box?.x ?? 0) + (box?.width ?? 0) / 2);
    const live: string[] = [];
    for (
      let y = Math.round((box?.y ?? 0) + (box?.height ?? 0) * 0.12);
      y <= Math.round((box?.y ?? 0) + (box?.height ?? 0) * 0.92);
      y += 10
    ) {
      const answer = await bandAt(page, columnX, y);
      if (answer !== null) live.push(answer);
    }
    expect(
      live.length,
      "the mute must leave the band answering — an over-broad mute reads 0/21 for the wrong reason",
    ).toBeGreaterThan(0);

    // THE CENSUS. Read the seats AFTER settling, with a real mouse at each
    // mark's own centre.
    const marks = await markBoxes(page, "edge-pick-");
    const drawn = marks.filter((m) => !m.buried);
    const buried = marks.filter((m) => m.buried);
    let agree = 0;
    let agreeDrawn = 0;
    const disagreed: string[] = [];
    for (const mark of marks) {
      const answer = await bandAt(page, mark.cx, mark.cy);
      if (answer === String(mark.index)) {
        agree += 1;
        if (!mark.buried) agreeDrawn += 1;
      } else {
        disagreed.push(
          `${mark.id}${mark.buried ? "(buried)" : ""}->${answer ?? "none"}`,
        );
      }
    }
    console.log(
      `    [PICKMARK] census ${agree}/${marks.length} agree ` +
        `(drawn ${agreeDrawn}/${drawn.length}, buried ${buried.length}); ` +
        `disagreements: ${disagreed.join(",") || "none"}`,
    );

    // THE CLAIM, both halves. Every mark the user can see and click addresses
    // its OWN edge...
    expect(
      agreeDrawn,
      `a DRAWN mark must address its own edge: ${disagreed.join(",")}`,
    ).toBe(drawn.length);
    // ...and enough marks are still drawn for that to mean something.
    expect(
      drawn.length,
      "hiding the marks is not a fix — most of the offered edges must still carry one",
    ).toBeGreaterThan(AGREEMENT_BEFORE);
    // ...and the whole-population census has risen off the defect's 8/21.
    expect(agree).toBeGreaterThan(AGREEMENT_BEFORE);

    // A BURIED MARK IS STILL A CONTROL. It keeps its accessible name, stays in
    // the tab order, and focus brings it back — `visibility:hidden` or
    // `display:none` would take all three away, which is why neither is used.
    expect(buried.length).toBeGreaterThan(0);
    const hidden = buried[0] as MarkBox;
    const node = page.getByTestId(hidden.id);
    const rest = await node.evaluate((el) => {
      const cs = getComputedStyle(el);
      return {
        opacity: cs.opacity,
        visibility: cs.visibility,
        display: cs.display,
        pointerEvents: cs.pointerEvents,
        name: el.getAttribute("aria-label") ?? "",
      };
    });
    expect(rest.visibility).not.toBe("hidden");
    expect(rest.display).not.toBe("none");
    expect(rest.opacity).toBe("0");
    expect(rest.pointerEvents).toBe("none");
    expect(rest.name).toMatch(/^Edge \d+, /);

    await node.focus();
    const focused = await node.evaluate((el) => ({
      opacity: getComputedStyle(el).opacity,
      isActive: document.activeElement === el,
    }));
    expect(focused.isActive).toBe(true);
    expect(
      focused.opacity,
      "a buried mark must come back the moment a keyboard reaches it",
    ).toBe("1");
    // And reaching it addresses its edge, so the keyboard route to a hidden
    // edge is exactly as long as it was.
    await expect(viewport).toHaveAttribute(
      "data-edge-pick-hover",
      String(hidden.index),
    );
  });

  test("the seats hold the orbit budget with 21 marks mounted", async ({
    page,
  }) => {
    // 420 s, raised from 300 s, so that the assertion which fires on a slow
    // machine NAMES something. Measured on a 4-core box: 86 s quiet, 133-150 s
    // under 1.5x CPU oversubscription — 300 s was 2.0-3.5x the observation
    // here, which is under 2x on any runner half this speed, and a harness
    // timeout tells a reader nothing about which of two orbits, one reseat and
    // eleven waits it ran out of patience during.
    test.setTimeout(420_000);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Shaft coupling");
    await seedShaftCoupling(page, account.token, part.id);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
      .toBeGreaterThan(16);
    const viewport = page.getByTestId("viewport");
    await viewport.evaluate((node) => {
      node.dataset["fitRect"] = "";
    });
    await page.getByTestId("view-fit").click();
    await expect(viewport).not.toHaveAttribute("data-fit-rect", "", {
      timeout: 20_000,
    });
    await waitForFrames(page, 6);
    const box = await viewport.boundingBox();
    const cx = Math.round((box?.x ?? 0) + (box?.width ?? 0) / 2);
    const cy = Math.round((box?.y ?? 0) + (box?.height ?? 0) / 2);

    /*
      AN A/B IN ONE RUN, NOT AN ABSOLUTE CEILING — and that distinction is the
      whole value of this test. The first draft asserted "no long task over
      50 ms" and would have been a lie: measured with the fix DISABLED, the same
      orbit produces 332 long tasks and a 179 ms worst case, because these specs
      run on `--disable-gpu` software rasterisation and the renderer owns the
      main thread. An absolute number there measures Chromium's SwiftShader, not
      this ticket's code. So the orbit is run twice on the same part in the same
      process — once with no edge marks at all, once with 21 mounted and their
      seats being recomputed — and the claim is about the DIFFERENCE, which is
      the only part either fix can move.
    */
    const orbit = async (label: string) => {
      await page.evaluate(() => {
        const w = window as unknown as {
          __longTasks?: number[];
          __obs?: PerformanceObserver;
        };
        w.__longTasks = [];
        w.__obs?.disconnect();
        const observer = new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            w.__longTasks?.push(entry.duration);
          }
        });
        observer.observe({ entryTypes: ["longtask"] });
        w.__obs = observer;
      });
      await page.mouse.move(cx, cy);
      await page.mouse.down();
      for (let i = 1; i <= 40; i += 1) {
        await page.mouse.move(
          cx + i * 4,
          cy + Math.round(Math.sin(i / 5) * 24),
        );
      }
      await page.mouse.up();
      await waitForFrames(page, 12);
      const tasks = await page.evaluate(
        () => (window as unknown as { __longTasks: number[] }).__longTasks,
      );
      const total = tasks.reduce((a, b) => a + b, 0);
      console.log(
        `    [PICKMARK] orbit ${label}: ${tasks.length} long tasks, ` +
          `${total.toFixed(0)}ms blocked, worst ${(tasks.length === 0 ? 0 : Math.max(...tasks)).toFixed(1)}ms`,
      );
      return total;
    };

    const bare = await orbit("no marks");

    await expect(page.getByTestId("new-fillet")).toBeEnabled({
      timeout: 30_000,
    });
    await page.getByTestId("new-fillet").click();
    await expect(page.getByTestId("fillet-editor")).toBeVisible();
    await page.getByTestId("fillet-mode-pick").click();
    await expect(page.locator('[data-testid^="edge-pick-"]')).toHaveCount(21);
    // The FIRST drain, with 21 marks freshly mounted and the camera at the fit
    // pose. Its own 30 s ceiling took shard 3/4 red under load before the orbit
    // below had even run — same mechanism as the reseat, same fix.
    await expectSeatsSettled(page, "21 marks mounted");
    const armed = await orbit("21 marks + seats");

    console.log(
      `    [PICKMARK] marks cost ${(armed - bare).toFixed(0)}ms of blocking ` +
        `over 40 drag steps (${(bare === 0 ? 0 : (armed / bare - 1) * 100).toFixed(0)}%)`,
    );
    expect(
      armed,
      "mounting the marks and reseating them must not multiply the orbit's cost",
    ).toBeLessThan(bare * ORBIT_COST_CEILING);

    /*
      And the orbit left the seats CORRECT, not merely cheap — a recompute that
      gave up under load would pass every timing assertion above.

      THE CEILING IS NOT THE CLAIM, and conflating the two is what made this
      the second-most-likely red on shard 3/4. What is asserted here is that
      the seats CONVERGE; how many wall-clock seconds that takes on a starved
      software-rasterising runner is a different question, and it is the same
      question the A/B comment above refuses to answer with an absolute number.
      Convergence is frame-driven — `OrbitControls` damping decays per UPDATE,
      and the seat pass drains a fixed per-frame budget — so the wall time to
      settle scales with FRAME time, i.e. with how busy the machine is, while
      the number of frames does not change at all.

      MEASURED (CI-4 pass, 2026-08-29). Quiet, this reseat is far inside the
      old 30 s. Under two CPU spinners on a 4-core box it exceeded it: shard
      3/4 loaded rep 2 died here with `pending` after the full 30 s, having
      passed the ratio assertion above at 1.18x — i.e. the perf claim held and
      the WAIT is what broke. The elapsed time is printed below so the number
      is in the shard log rather than in somebody's memory, and the ceiling is
      set where a 4x-slower machine than this one still converges inside it.
    */
    await expectSeatsSettled(page, "reseat after the armed orbit");
    const marks = await markBoxes(page, "edge-pick-");
    expect(marks.length).toBe(21);
    expect(marks.filter((m) => !m.buried).length).toBeGreaterThan(0);
  });

  test("founder shot: the marks that remain are on edges you can see", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    await openCouplingWithFilletArmed(page);
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.getByTestId("view-fit").click();
    await expectSeatsSettled(page, "founder shot at 1280");
    await waitForFrames(page, 6);
    // `fixtures.ts` gates the write: a routine run exercises the render and
    // leaves the committed PNG alone (UPDATE_SCREENSHOTS=1 refreshes it).
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/pickmark-seats-after-1280.png`,
    });
  });
});
