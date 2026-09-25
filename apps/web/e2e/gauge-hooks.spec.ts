/**
 * THE `data-gauge` HOOK — does it reach the DOM, and when does it not.
 *
 * ## Why this spec exists
 *
 * A probe reported `document.querySelector('[data-gauge="extrude-depth"]')`
 * returning **null** while `[data-testid="extrude-depth-handle"]` resolved
 * fine, and concluded the hook was broken. That conclusion would be expensive
 * if true and was not checkable from source, because source can only say what
 * the component INTENDS: `ParametricGauge` puts `data-gauge` on `<AxisGrip>`
 * immediately beside the `data-testid`, `AxisGrip` spreads `...rest` onto its
 * `div` with no allow-list, and two green specs (`revolve-gauge.spec.ts`,
 * `draft-gauge.spec.ts`) already locate bands by `[data-gauge][data-testid]`
 * together. All of which is consistent with the hook working AND with it
 * failing for some mount or some state nobody had looked at.
 *
 * ## What was measured, and what it settles
 *
 * All nine mounts, before and after the named settle: `[data-gauge="<id>"]`
 * resolved every time, on the grip and on every sleeve band (2 nodes on a
 * straight track, 3 for draft, 33 for a 120-degree revolve arc). Then the
 * extrude gauge through every live state it has:
 *
 *     rest / grabbed / typing / after a view change   ->  both resolve
 *     command closed                                  ->  NEITHER resolves
 *
 * **They are attributes on the same element, so they appear and vanish
 * together.** There is no state in which one answers and the other does not,
 * which means the reported asymmetry cannot be produced by this component's
 * lifecycle at all — the two readings were taken at different moments, not in
 * one state where the hook is broken. "Absent because the command is closed" is
 * a completely different fact from "the hook is broken", and only the second
 * one would justify changing anything.
 *
 * ## Why it is a spec and not a note
 *
 * Seven sites in `apps/web/e2e/**` resolve gauge ownership through
 * `data-gauge`, and two of them — `gaugeProbe.ts`'s `reachAlongTrack` and
 * `gaugeReach.ts`'s census — use it ALONE: `el.closest('[data-gauge="<id>"]')
 * !== null`. If that attribute ever stops reaching the DOM those helpers do not
 * fail, they return `false` and every check built on them quietly starts
 * answering a different question — the "assertion that cannot observe its
 * failure mode" family this repo keeps paying for. A green gauge spec is not
 * evidence the hook works; this is.
 */
import { expect, test, type Page } from "./fixtures";
import { MOUNTS, type Mount } from "./gaugeMounts";
import { installSceneProbe } from "./invariants";
import { centreOf, expectGaugeSettled, measureTarget } from "./touchTargets";

test.use({ viewport: { width: 1280, height: 800 } });

interface HookCensus {
  /** How many `[data-gauge="<id>"]` nodes exist. */
  mine: number;
  /** Does the single-node query a probe would write resolve? */
  queryOne: boolean;
  /** Does the grip's own test id resolve? */
  testidHandle: boolean;
  /** What `data-gauge` the GRIP carries — the two hooks on one element. */
  gripHasIt: string;
}

function census(page: Page, gaugeId: string): Promise<HookCensus> {
  return page.evaluate((id: string) => {
    const all = Array.from(document.querySelectorAll("[data-gauge]"));
    return {
      mine: all.filter((n) => n.getAttribute("data-gauge") === id).length,
      queryOne: document.querySelector(`[data-gauge="${id}"]`) !== null,
      testidHandle:
        document.querySelector(`[data-testid="${id}-handle"]`) !== null,
      gripHasIt:
        document
          .querySelector(`[data-testid="${id}-handle"]`)
          ?.getAttribute("data-gauge") ?? "ABSENT",
    };
  }, gaugeId);
}

for (const mount of MOUNTS) {
  test(`[data-gauge] reaches the DOM — ${mount.id}`, async ({ page }) => {
    await installSceneProbe(page);
    await mount.open(page);

    // BEFORE the settle, deliberately: this is the earliest a probe could
    // reasonably look, and it is where a lifecycle explanation would show up.
    const early = await census(page, mount.id);

    // NAMED SETTLE. The sleeve bands carry `data-gauge` too and are
    // `display: none` until the first frame has measured the projection, so a
    // reading taken before it can legitimately count FEWER nodes than one taken
    // after. Both readings are printed so the difference — if there ever is one
    // — is visible rather than averaged away.
    await expectGaugeSettled(page, `${mount.id} hooks`);
    const late = await census(page, mount.id);

    console.log(
      `[hooks] ${mount.id}: early ${JSON.stringify(early)} / ` +
        `late ${JSON.stringify(late)}`,
    );

    expect(
      late.queryOne,
      `[data-gauge="${mount.id}"] does not resolve on a mounted gauge. Two ` +
        `helpers resolve ownership through this attribute ALONE ` +
        `(gaugeProbe.ts reachAlongTrack, gaugeReach.ts) and neither would ` +
        `fail — they would return false and answer a different question`,
    ).toBe(true);
    expect(
      late.gripHasIt,
      `the grip carries data-testid="${mount.id}-handle" but data-gauge=` +
        `"${late.gripHasIt}" — the two hooks are on the SAME element, so they ` +
        `cannot disagree unless one is being dropped`,
    ).toBe(mount.id);
    // Grip + at least one sleeve band.
    expect(late.mine).toBeGreaterThanOrEqual(2);
  });
}

test("the two hooks appear and vanish together, across every live state", async ({
  page,
}) => {
  await installSceneProbe(page);
  const extrude = MOUNTS.find((m) => m.id === "extrude-depth") as Mount;
  await extrude.open(page);
  await expectGaugeSettled(page, "extrude hook states");
  const id = "extrude-depth";

  const states: Record<string, HookCensus> = {};
  states["rest"] = await census(page, id);

  // GRABBED — pointer down on the grip, never released.
  const grip = await measureTarget(page, `${id}-handle`);
  const at = centreOf(grip.box as NonNullable<typeof grip.box>);
  await page.mouse.move(at.x, at.y);
  await page.mouse.down();
  await page.mouse.move(at.x, at.y - 30);
  states["grabbed"] = await census(page, id);
  await page.mouse.up();

  // TYPING — a digit opens the numeric cell, swapping the readout branch and
  // re-rendering the strip. The grip is a sibling and must be untouched.
  await page.getByTestId(`${id}-handle`).focus();
  await page.keyboard.press("7");
  await expect(page.getByTestId(`${id}-readout`).locator("input")).toHaveCount(
    1,
  );
  states["typing"] = await census(page, id);
  await page.keyboard.press("Escape");

  // AFTER A VIEW CHANGE — the gauge re-poses every frame from the camera.
  await page.getByTestId("view-front").click();
  states["after-view"] = await census(page, id);

  for (const [name, seen] of Object.entries(states)) {
    console.log(`[hooks] extrude ${name}: ${JSON.stringify(seen)}`);
    expect(seen.queryOne, `[data-gauge] must resolve while ${name}`).toBe(true);
    expect(
      seen.queryOne,
      `the two hooks disagree while ${name}: data-gauge=${seen.queryOne}, ` +
        `data-testid=${seen.testidHandle}`,
    ).toBe(seen.testidHandle);
  }

  // THE ONE STATE WHERE IT LEGITIMATELY VANISHES — and it is the companion
  // that makes every assertion above non-vacuous. Without it, `queryOne ===
  // testidHandle` would be satisfiable by a page where BOTH are always true
  // for a reason unrelated to the gauge.
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("extrude-editor")).toHaveCount(0);
  const closed = await census(page, id);
  console.log(`[hooks] extrude closed: ${JSON.stringify(closed)}`);
  expect(closed.queryOne).toBe(false);
  expect(closed.testidHandle).toBe(false);
  expect(
    closed.gripHasIt,
    `with the command closed BOTH hooks must be gone — an absent ` +
      `[data-gauge] here is the instrument being unmounted, which is a ` +
      `completely different fact from the hook being broken`,
  ).toBe("ABSENT");
});

/**
 * THE TWO SELECTORS ARE NOT COEXTENSIVE — which is what decides whether a
 * read-site's `[data-testid^=...]` fallback is a safety net or a WIDENING.
 *
 * Seven sites in `apps/web/e2e/**` resolve "is this pixel on gauge X". They
 * come in three shapes, and the shape decides what happens the day `data-gauge`
 * stops reaching the DOM:
 *
 *   ALONE   `el.closest('[data-gauge="X"]')`            -> returns false,
 *           (gaugeProbe.reachAlongTrack, gaugeReach,       silently, and every
 *            revolve-gauge's band probe, gauge-touch)      census built on it
 *                                                          answers a different
 *                                                          question
 *   AND     `[data-gauge="X"][data-testid*="sleeve"]`   -> resolves nothing,
 *           (revolve-gauge, draft-gauge)                   fails LOUDLY
 *   OR      `[data-gauge="X"], [data-testid^="X-"]`     -> keeps passing,
 *           (fillet-chamfer-gauge)                         carried by the half
 *                                                          that still works
 *
 * The OR form is the interesting one, and the reason this case MEASURES rather
 * than reasons from the selectors side by side. It is naturally described as a
 * fallback, but the two halves do not select the same nodes: `data-gauge` is on
 * the grip and the hit bands ONLY, while `data-testid^="X-"` additionally
 * matches `-readout` (the tag strip, which is a separate control) and `-steps`
 * (the `sr-only` hint). So the OR form is not a net under the same question —
 * it is a WIDER question, and it scores a pixel that landed on the number as a
 * pixel on the rod.
 */
test("the data-gauge and data-testid node sets differ, by how much", async ({
  page,
}) => {
  await installSceneProbe(page);
  const extrude = MOUNTS.find((m) => m.id === "extrude-depth") as Mount;
  await extrude.open(page);
  await expectGaugeSettled(page, "selector sets");
  const id = "extrude-depth";

  const sets = await page.evaluate((gaugeId: string) => {
    const name = (n: Element) => n.getAttribute("data-testid") ?? n.tagName;
    const byGauge = Array.from(
      document.querySelectorAll(`[data-gauge="${gaugeId}"]`),
    );
    const byTestId = Array.from(
      document.querySelectorAll(`[data-testid^="${gaugeId}-"]`),
    );
    return {
      gauge: byGauge.map(name).sort(),
      testid: byTestId.map(name).sort(),
      onlyTestId: byTestId
        .filter((n) => !byGauge.includes(n))
        .map(name)
        .sort(),
      onlyGauge: byGauge
        .filter((n) => !byTestId.includes(n))
        .map(name)
        .sort(),
    };
  }, id);

  console.log(
    `[hooks] ${id} selector sets:\n` +
      `  [data-gauge="${id}"]         -> ${sets.gauge.join(", ")}\n` +
      `  [data-testid^="${id}-"]      -> ${sets.testid.join(", ")}\n` +
      `  only the testid selector     -> ${sets.onlyTestId.join(", ") || "(none)"}\n` +
      `  only the data-gauge selector -> ${sets.onlyGauge.join(", ") || "(none)"}`,
  );

  // Nothing is data-gauge-ONLY: the grip and its bands carry both hooks. If
  // this ever fails, an OR-form read-site has stopped being a superset and the
  // widening argument below no longer holds.
  expect(
    sets.onlyGauge,
    `nodes carrying data-gauge but no matching data-testid: an OR-form ` +
      `read-site would MISS these`,
  ).toEqual([]);

  // THE WIDENING, asserted rather than described. The tag strip and the
  // sr-only step hint are matched by the testid half and are NOT part of the
  // instrument's track, so an OR-form ownership check counts a press on the
  // number as a press on the rod.
  expect(
    sets.onlyTestId,
    `the testid half must be strictly WIDER — if it is not, the OR form is a ` +
      `true fallback and this case's reasoning is wrong`,
  ).toContain(`${id}-readout`);
  expect(sets.onlyTestId).toContain(`${id}-steps`);

  // NEGATIVE CONTROL for the `onlyGauge` assertion, which passed from its first
  // run and is therefore not yet a gate. Inject a node carrying `data-gauge`
  // and NO matching `data-testid` — exactly the shape that would make an
  // OR-form read-site miss a real part of the instrument — and confirm the
  // census names it. (The resolution assertions above already have their
  // control built in: the `closed` state in the previous case reads
  // `queryOne: false`, so that one has been seen both ways.)
  const withOrphan = await page.evaluate((gaugeId: string) => {
    const orphan = document.createElement("div");
    orphan.setAttribute("data-gauge", gaugeId);
    document.body.appendChild(orphan);
    const name = (n: Element) => n.getAttribute("data-testid") ?? n.tagName;
    const byGauge = Array.from(
      document.querySelectorAll(`[data-gauge="${gaugeId}"]`),
    );
    const byTestId = Array.from(
      document.querySelectorAll(`[data-testid^="${gaugeId}-"]`),
    );
    const onlyGauge = byGauge
      .filter((n) => !byTestId.includes(n))
      .map(name)
      .sort();
    orphan.remove();
    return onlyGauge;
  }, id);
  console.log(`[control] with an orphan data-gauge node: ${withOrphan}`);
  expect(
    withOrphan,
    "the onlyGauge assertion cannot observe a data-gauge node with no testid",
  ).not.toEqual([]);
});
