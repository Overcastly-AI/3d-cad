/**
 * CRAFT-7 — THE AFFORDANCE AND THE HIT TARGET MUST BE THE SAME THING.
 *
 * The gauge has been drawn since T-23 and, until this spec, could not be taken
 * hold of anywhere the drawing invites you to. Measured on the running app:
 * `document.elementFromPoint` down the gauge's OWN projected axis resolved to
 * the grip at **2 of 16** sample points — a 24 x 24 box at the arrowhead's apex
 * and nothing else — and a real `page.mouse.down/move/up` from the shaft's
 * midpoint left `extrude-distance` unchanged at 40. The shaft, the cone and the
 * ladder are WebGL with no raycast target, so the affordance and the hit target
 * were ANTICORRELATED: the one grabbable spot was a 12 px collar on the POINT of
 * an arrow drawn at 0.92 opacity, about 90 px from where the arrow tells you to
 * aim.
 *
 * ## Why this is a spec and not a screenshot
 *
 * A drawn manipulator photographs perfectly while being unusable, which is how
 * this survived a founder capture, a design review and six passing e2e cases.
 * `toBeVisible()` is a box property; `boundingBox()` is a box property; only
 * asking the browser WHAT IS UNDER THIS PIXEL, and then actually pressing it,
 * can see the defect. So both halves are here, and the second is the one that
 * matters: it asserts with the user's own mechanism rather than a proxy.
 *
 * **There is no `force: true` in this file and there must never be.** This repo
 * has already measured that flag hiding a zero-area SVG pick target for months;
 * it is evidence of a defect, not a workaround for one.
 */
import { expect, test, type Page } from "./fixtures";
import { installSceneProbe, waitForCameraRest } from "./invariants";
import { createPartViaApi, seedSession } from "./support";
// The track-walking helpers moved to `./gaugeReach` on their SECOND real use
// (CRAFT-9a mounts the same instrument for fillet radius and chamfer distance).
// They were always parameterised by `gaugeId`; nothing about them was ever
// specific to extrude, and two copies of a measurement is two measurements.
import {
  gripCentre,
  reach,
  REACH_FLOOR,
  SAMPLES,
  shaftMidpoint,
} from "./gaugeReach";

/** Enter sketch mode, draw a rectangle, and open the extrude editor on it. */
async function openExtrude(page: Page): Promise<void> {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await page.keyboard.press("r");
  await page.mouse.click(650, 420);
  await page.mouse.move(980, 640);
  await page.mouse.click(980, 640);
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  await page.getByTestId("new-extrude").click();
  await expect(page.getByTestId("extrude-editor")).toBeVisible();
  // Iso, because the post-sketch camera looks straight down the pull axis and a
  // track with no screen direction has no axis to walk.
  await page.getByTestId("view-iso").click();
  await waitForCameraRest(page);
}

/** The distance field's value as a number. */
async function distance(page: Page): Promise<number> {
  return Number.parseFloat(
    await page.getByTestId("extrude-distance").inputValue(),
  );
}

test.describe("the extrude gauge is grabbable where it is drawn", () => {
  test("elementFromPoint down the projected track resolves to the gauge", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Reachable boss");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);
    await page.getByTestId("extrude-distance").fill("40");
    await expect(page.getByTestId("extrude-preview-active")).toHaveAttribute(
      "data-distance-mm",
      "40",
    );

    const walked = await reach(page, "extrude-depth");
    console.log(
      `CRAFT-7 reach: ${walked.hits}/${SAMPLES} — ${walked.resolved.join(", ")}`,
    );
    expect(
      walked.hits,
      `the drawn track must BE the target: ${walked.hits}/${SAMPLES} sample ` +
        `points resolved to the gauge (${walked.resolved.join(", ")})`,
    ).toBeGreaterThanOrEqual(REACH_FLOOR);
  });

  test("a real pointer drag from the shaft midpoint moves the value", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Midshaft boss");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);
    await page.getByTestId("extrude-distance").fill("40");
    await expect(page.getByTestId("extrude-preview-active")).toHaveAttribute(
      "data-distance-mm",
      "40",
    );

    const mid = await shaftMidpoint(page, "extrude-depth");

    // No `force`, no locator: the raw mouse, at a pixel chosen from the drawn
    // geometry. If nothing is listening there, nothing happens — which is
    // exactly what happened before this item, and the field stayed at 40.
    await page.mouse.move(mid.x, mid.y);
    await page.mouse.down();
    for (let step = 1; step <= 5; step += 1) {
      await page.mouse.move(mid.x, mid.y + step * 12);
    }
    await page.mouse.up();

    await expect
      .poll(() => distance(page), {
        message:
          "a drag from the middle of the drawn shaft must move the value",
      })
      .toBeLessThan(40);
  });

  test("the tag is TIED to the grip, and the tie flips at the frame edge", async ({
    page,
  }) => {
    // MEASURED before this item: the tag was placed by a bare CSS offset
    // (`-translate-y-8 translate-x-4`) and floated unattached — `D 10 mm`
    // hanging in space with no tie to the arrow it describes. At that point it
    // is a HUD chip that happens to be near some geometry, and anything else on
    // screen could equally be its subject. The leader makes the claim.
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Tied");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);

    const leader = page.getByTestId("gauge-tag-leader");
    await expect(leader).toHaveCount(1);

    // The leader's anchor is ON the grip and its far end is ON the strip, which
    // is the only thing that makes it a tie rather than a stray hairline. Both
    // are read as real geometry rather than from the props that drew them.
    const strip = page.getByTestId("extrude-depth-readout");
    const gripBox = await gripCentre(page, "extrude-depth");
    // READ THE LINE'S OWN ENDPOINTS, not its bounding box.
    // `getBoundingClientRect` on an SVG `<line>` ignores stroke AND loses the
    // direction: for a leader running up-and-right the box corners are
    // `(0, -28)` and `(14, 0)` and NEITHER is an endpoint, so a nearest-corner
    // reading reported the anchor 14 px from a grip it is sitting on. This repo
    // has already paid for the stroke half of that trap (the 118.1 x 0.0 px
    // dimension pick); this is the other half. The SVG is 1x1 anchored at the
    // grip, so its own rect is the origin the attributes are relative to.
    const leaderBox = await leader.evaluate((el) => {
      const line = el.querySelector("line");
      if (line === null) return null;
      const origin = el.getBoundingClientRect();
      const at = (name: string): number =>
        Number(line.getAttribute(name) ?? "0");
      return {
        x1: origin.left + at("x1"),
        y1: origin.top + at("y1"),
        x2: origin.left + at("x2"),
        y2: origin.top + at("y2"),
      };
    });
    if (leaderBox === null) throw new Error("no leader line");
    const stripBox = await strip.boundingBox();
    if (stripBox === null) throw new Error("no strip box");

    // One end within the grip's own 24 px target…
    const nearGrip = Math.hypot(
      leaderBox.x1 - gripBox.x,
      leaderBox.y1 - gripBox.y,
    );
    expect(nearGrip, "the leader must start ON the grip").toBeLessThanOrEqual(
      12,
    );
    // …and the other inside the strip it carries.
    const inStrip =
      leaderBox.x2 >= stripBox.x - 2 &&
      leaderBox.x2 <= stripBox.x + stripBox.width + 2 &&
      leaderBox.y2 >= stripBox.y - 2 &&
      leaderBox.y2 <= stripBox.y + stripBox.height + 2;
    expect(inStrip, "the leader must reach the strip it ties").toBe(true);

    // The side is STAMPED, which is the only externally checkable evidence a
    // flip can ever happen — a placement test that only asserts "inside the
    // frame" passes just as well when the tag is clamped onto the grip.
    await expect(page.locator("[data-gauge-tag-side]")).toHaveCount(1);
  });

  test("the sleeve exists only while the command is open", async ({ page }) => {
    // A transparent band across the viewport that outlived its command would
    // swallow face picks — the one way this fix could make the product worse.
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Closed boss");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);
    await expect(page.getByTestId("extrude-depth-sleeve")).toHaveCount(1);
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("extrude-editor")).toHaveCount(0);
    await expect(page.getByTestId("extrude-depth-sleeve")).toHaveCount(0);
  });
});
