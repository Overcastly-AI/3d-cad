import { expect, test } from "./fixtures";
import type { Locator, Page } from "./fixtures";
import { createFeature, SQUARE_20 } from "./partSeed";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * The band's next-step offer SAYS what it proposes — founder decision on the
 * 6px dot that did not explain itself.
 *
 * The dot stays the resting mark. On hover, on keyboard focus, and ONCE per new
 * step unprompted, the rest of the viewport's leader-note grammar comes up: a
 * leader from the dot to a stamp reading `NEXT <tool> <key>` over the
 * proposal's caption. This spec proves the five things that make that safe to
 * ship, each with the user's own mechanism rather than a proxy:
 *
 *   (a) a real hover shows it,
 *   (b) real keyboard focus shows it,
 *   (c) a NEW step shows it once, unprompted, and the SAME step never again,
 *   (d) a real `page.mouse.click` at the tool's centre still runs the tool
 *       while the note is up,
 *   (e) `Enter` is not stolen — from the proposed tool, or from any other.
 *
 * "SHOWN" IS MEASURED, never inferred from a class name or `toBeVisible()`
 * (which passes for an opacity-0 node): computed opacity, a non-zero box inside
 * the frame, and — for the unprompted case — a per-frame log written IN THE
 * PAGE, so "it appeared while nobody was pointing at it" is read off the frames
 * themselves rather than off a timing guess about when to look.
 */

/** Somewhere the pointer rests that is neither the band nor the model. */
const park = (page: Page) => ({
  x: Math.round((page.viewportSize()?.width ?? 1600) * 0.5),
  y: 12,
});

/** One transition of the offer as the page saw it, frame by frame. */
interface OfferFrame {
  t: number;
  tool: string;
  announced: boolean;
  opacity: number;
  hovered: boolean;
  focused: boolean;
}
interface OfferLog {
  frames: OfferFrame[];
  inputs: { t: number; type: string }[];
}

/**
 * A per-frame sampler, installed before the page loads so it can see the very
 * first frame of an announcement. It records a row only when something about
 * the offer CHANGES (tool, announced, rounded opacity, hover, focus), so a long
 * run stays small, and it logs every pointer/key/wheel input beside it — which
 * is what lets a case say "it settled with no input in between" as a fact.
 */
async function installOfferLog(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const log: OfferLog = { frames: [], inputs: [] };
    (window as unknown as { __offerLog: OfferLog }).__offerLog = log;
    for (const type of ["pointerdown", "keydown", "wheel"]) {
      window.addEventListener(
        type,
        () => log.inputs.push({ t: performance.now(), type }),
        { capture: true, passive: true },
      );
    }
    let last = "";
    const tick = () => {
      const label = document.querySelector<HTMLElement>(
        "[data-testid='next-step-label']",
      );
      const button = label?.closest("button") ?? null;
      const row =
        label === null || button === null
          ? null
          : {
              tool: button.dataset.testid ?? "?",
              announced: label.dataset.announced === "true",
              opacity:
                Math.round(Number(getComputedStyle(label).opacity) * 100) / 100,
              hovered: button.matches(":hover"),
              focused: button.matches(":focus-visible"),
            };
      const key = JSON.stringify(row);
      if (key !== last) {
        last = key;
        if (row !== null) log.frames.push({ t: performance.now(), ...row });
      }
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

const readLog = (page: Page): Promise<OfferLog> =>
  page.evaluate(
    () => (window as unknown as { __offerLog: OfferLog }).__offerLog,
  );

const clearLog = (page: Page): Promise<void> =>
  page.evaluate(() => {
    const log = (window as unknown as { __offerLog: OfferLog }).__offerLog;
    log.frames.length = 0;
    log.inputs.length = 0;
  });

/** The offer's stamp on a tool, and the leader that ties it to the dot. */
const labelOf = (tool: Locator) =>
  tool.locator("[data-testid='next-step-label']");
const leaderOf = (tool: Locator) => tool.locator("[data-next-step-leader]");

const opacityOf = (el: Locator): Promise<number> =>
  el.evaluate((node) => Number(getComputedStyle(node).opacity));

/**
 * The stamp is ON SCREEN — the property, not a stand-in. Opacity settles past
 * the fade, and the box is real, non-zero, and inside the frame (an offer drawn
 * off-screen or collapsed to zero area is the zero-area family again).
 */
async function expectShown(page: Page, tool: Locator): Promise<void> {
  const label = labelOf(tool);
  await expect(label).toHaveCount(1);
  await expect.poll(() => opacityOf(label)).toBeGreaterThan(0.95);
  await expect.poll(() => opacityOf(leaderOf(tool))).toBeGreaterThan(0.95);
  const box = (await label.boundingBox())!;
  const frame = page.viewportSize()!;
  expect(box.width).toBeGreaterThan(60);
  expect(box.height).toBeGreaterThan(14);
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(frame.width);
  expect(box.y + box.height).toBeLessThanOrEqual(frame.height);
}

async function expectHidden(tool: Locator): Promise<void> {
  await expect.poll(() => opacityOf(labelOf(tool))).toBeLessThan(0.05);
  await expect.poll(() => opacityOf(leaderOf(tool))).toBeLessThan(0.05);
}

/** Wait out the once-per-step announcement, with nobody touching anything. */
async function waitSettled(tool: Locator): Promise<void> {
  await expect(labelOf(tool)).toHaveAttribute("data-announced", "false", {
    timeout: 15_000,
  });
}

/** Extrude the default profile through the editor, pointer parked AWAY. */
async function buildExtrude(page: Page, distanceMm: string): Promise<void> {
  await expect(page.getByTestId("new-extrude")).toBeEnabled({
    timeout: 30_000,
  });
  await page.getByTestId("new-extrude").click();
  await expect(page.getByTestId("extrude-editor")).toBeVisible();
  // Off the band before the build lands, so the tool the offer arrives on is
  // not under the pointer — otherwise "unprompted" could be a hover.
  const rest = park(page);
  await page.mouse.move(rest.x, rest.y);
  await page.getByTestId("extrude-distance").fill(distanceMm);
  await page.getByTestId("extrude-distance").press("Enter");
  await expect(page.getByTestId("extrude-editor")).toHaveCount(0, {
    timeout: 30_000,
  });
}

/**
 * A part whose first body is extruded HERE, in this session — the build gate
 * (`useNextStep.ts`) proposes only about work it watched arrive.
 */
async function partWithBody(page: Page, name: string): Promise<Locator> {
  await installOfferLog(page);
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, name);
  await createFeature(page, token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: SQUARE_20 },
    expected_tree_version: 0,
  });
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("feature-tree")).toBeVisible();
  await buildExtrude(page, "20");
  const fillet = page.getByTestId("new-fillet");
  await expect(fillet).toHaveAttribute("data-next-step", "true", {
    timeout: 30_000,
  });
  return fillet;
}

/** Real keyboard focus on `tool`: focus its right-hand neighbour, Shift+Tab. */
async function keyboardFocus(neighbour: Locator, tool: Locator): Promise<void> {
  await neighbour.focus();
  await neighbour.page().keyboard.press("Shift+Tab");
  await expect(tool).toBeFocused();
  expect(await tool.evaluate((el) => el.matches(":focus-visible"))).toBe(true);
}

test.describe("the band's next-step offer says what it proposes", () => {
  test("(c) a NEW step says it once, unprompted — the same step never again", async ({
    page,
  }) => {
    const fillet = await partWithBody(page, "Once per step");

    // UNPROMPTED: read off the page's own frames. The first frame the stamp was
    // fully up, nobody was pointing at the tool or focused on it.
    await expect
      .poll(async () =>
        (await readLog(page)).frames.some(
          (f) => f.tool === "new-fillet" && f.announced && f.opacity > 0.95,
        ),
      )
      .toBe(true);
    const up = (await readLog(page)).frames.filter(
      (f) => f.tool === "new-fillet" && f.announced && f.opacity > 0.95,
    );
    expect(up[0]!.hovered, "announced while hovered is not unprompted").toBe(
      false,
    );
    expect(up[0]!.focused, "announced while focused is not unprompted").toBe(
      false,
    );
    // …and it is ON SCREEN, not merely flagged.
    await expectShown(page, fillet);

    // Zero width: the band measured itself BEFORE the stamp came up and must
    // read the same with it up. A note that widened a tool would push a group
    // into the icon tier at the 1280 floor.
    const band = page.locator("[data-band-tier]").first();
    const tierUp = await band.getAttribute("data-band-tier");
    const widthUp = (await fillet.boundingBox())!.width;

    // It SETTLES on its own — no input between the first announced frame and
    // the frame it went quiet.
    await waitSettled(fillet);
    await expectHidden(fillet);
    const log = await readLog(page);
    const start = up[0]!.t;
    const end = log.frames.find(
      (f) => f.tool === "new-fillet" && !f.announced && f.t > start,
    )!.t;
    expect(
      log.inputs.filter((i) => i.t > start && i.t < end),
      "something touched the page while the offer was being said",
    ).toEqual([]);
    // A deliberate hold, not a flash.
    expect(end - start).toBeGreaterThan(3000);
    // The dot stays: settling is back to the resting mark, not a retirement.
    await expect(fillet.getByTestId("next-step-dot")).toHaveCount(1);
    expect(await band.getAttribute("data-band-tier")).toBe(tierUp);
    expect((await fillet.boundingBox())!.width).toBe(widthUp);

    // THE SAME STEP COMING BACK. Suppress the extrude and the part has no body,
    // so the proposal drops; un-suppress and it returns for the SAME feature.
    // It must come back as the bare dot.
    await page.getByTestId("feature-suppress-1").click();
    await expect(page.getByTestId("next-step-dot")).toHaveCount(0, {
      timeout: 30_000,
    });
    await clearLog(page);
    await page.getByTestId("feature-suppress-1").click();
    await expect(fillet.getByTestId("next-step-dot")).toHaveCount(1, {
      timeout: 30_000,
    });
    // A named settle long enough that an announcement would certainly have
    // been written: it is state-driven and lands in the same render as the dot.
    await page.waitForTimeout(1500);
    const again = (await readLog(page)).frames.filter((f) => f.announced);
    expect(again, "the same step was announced twice").toEqual([]);
    await expectHidden(fillet);

    // A NEW STEP: a second extrude is a new build, so its offer is said.
    await buildExtrude(page, "30");
    const extrude = page.getByTestId("new-extrude");
    await expect(extrude).toHaveAttribute("data-next-step", "true", {
      timeout: 30_000,
    });
    await expect(labelOf(extrude)).toHaveAttribute("data-announced", "true");
    await expectShown(page, extrude);
    await expect(labelOf(extrude)).toContainText(
      "Another extrude on this body",
    );
  });

  test("(a) a hover shows the offer, and it is one leader note", async ({
    page,
  }) => {
    const fillet = await partWithBody(page, "Hover");
    await waitSettled(fillet);
    await expectHidden(fillet);

    const box = (await fillet.boundingBox())!;
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await expectShown(page, fillet);
    // Shown BY THE HOVER: the announcement is over.
    await expect(labelOf(fillet)).toHaveAttribute("data-announced", "false");

    // The words: NEXT + the tool's own name + its key, over the proposal.
    const label = labelOf(fillet);
    await expect(label).toContainText("Next");
    await expect(label).toContainText("Fillet");
    await expect(label).toContainText("Round the new body's edges");
    // …and it REPLACES the tooltip rather than stacking a second stamp.
    await expect(fillet.locator("[data-tooltip]")).toHaveCount(1);

    // ONE MARK: the leader starts at the dot and lands on the stamp's corner.
    const dot = (await fillet.getByTestId("next-step-dot").boundingBox())!;
    const leader = (await leaderOf(fillet).boundingBox())!;
    const stamp = (await label.boundingBox())!;
    const dotCx = dot.x + dot.width / 2;
    const dotCy = dot.y + dot.height / 2;
    expect(Math.abs(leader.x + leader.width / 2 - dotCx)).toBeLessThanOrEqual(
      1,
    );
    expect(Math.abs(leader.y - dotCy)).toBeLessThanOrEqual(1);
    expect(Math.abs(leader.y + leader.height - stamp.y)).toBeLessThanOrEqual(1);
    expect(Math.abs(stamp.x - dotCx)).toBeLessThanOrEqual(2);

    // Off the tool, and it goes.
    const rest = park(page);
    await page.mouse.move(rest.x, rest.y);
    await expectHidden(fillet);
  });

  test("(b) keyboard focus shows the offer", async ({ page }) => {
    const fillet = await partWithBody(page, "Keyboard");
    await waitSettled(fillet);
    await expectHidden(fillet);

    await keyboardFocus(page.getByTestId("new-chamfer"), fillet);
    // Nobody is pointing at it: this is the focus path, not the hover path.
    expect(await fillet.evaluate((el) => el.matches(":hover"))).toBe(false);
    await expectShown(page, fillet);
    await expect(labelOf(fillet)).toHaveAttribute("data-announced", "false");
  });

  test("(d) a real click at the tool's centre runs the tool while the offer is up", async ({
    page,
  }) => {
    const fillet = await partWithBody(page, "Click through");
    // UP UNPROMPTED — the case where the note is on screen without the user
    // having gone to the tool, so a click is the first thing they do to it.
    await expect(labelOf(fillet)).toHaveAttribute("data-announced", "true");
    await expectShown(page, fillet);

    const box = (await fillet.boundingBox())!;
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    // What a pointer at the centre actually lands on: the tool, never the note.
    const hit = await page.evaluate(
      ({ x, y }) => {
        const el = document.elementFromPoint(x, y);
        return {
          tool: el?.closest("button")?.getAttribute("data-testid") ?? null,
          note:
            el?.closest(
              "[data-testid='next-step-label'], [data-next-step-leader]",
            ) != null,
        };
      },
      { x: cx, y: cy },
    );
    // SOFT, both attribution checks: they explain a failure, but the verdict
    // that matters is the real click below, and it must always be reached —
    // a note that swallowed the press would otherwise be reported only as
    // "the note is on top", never as "the tool did not run".
    expect.soft(hit).toEqual({ tool: "new-fillet", note: false });
    // …and the stamp itself takes nothing: a click on it reaches what is under.
    const stamp = (await labelOf(fillet).boundingBox())!;
    const under = await page.evaluate(
      ({ x, y }) =>
        document
          .elementFromPoint(x, y)
          ?.closest("[data-testid='next-step-label'], [data-next-step]") !=
        null,
      { x: stamp.x + stamp.width / 2, y: stamp.y + stamp.height / 2 },
    );
    expect.soft(under, "the offer's stamp is a pointer target").toBe(false);

    await page.mouse.click(cx, cy);
    await expect(page.getByTestId("fillet-editor")).toBeVisible();
  });

  test("(e) Enter is not stolen — from the proposed tool or any other", async ({
    page,
  }) => {
    const fillet = await partWithBody(page, "Enter");
    const chamfer = page.getByTestId("new-chamfer");

    // While the offer is being SAID, Enter on a DIFFERENT focused tool runs
    // that tool. This is the W2 shape exactly: a proposal note once accepted
    // itself on Enter and cancelled the focused button's own activation.
    await expect(labelOf(fillet)).toHaveAttribute("data-announced", "true");
    await chamfer.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("chamfer-editor")).toBeVisible();
    await expect(page.getByTestId("fillet-editor")).toHaveCount(0);
    await page.getByTestId("in-command-cancel").click();
    await expect(page.getByTestId("in-command")).toHaveCount(0);
  });

  test("(e) Enter on the focused proposed tool runs it, note up", async ({
    page,
  }) => {
    const fillet = await partWithBody(page, "Enter on offer");
    await waitSettled(fillet);
    await keyboardFocus(page.getByTestId("new-chamfer"), fillet);
    await expectShown(page, fillet);
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("fillet-editor")).toBeVisible();
  });

  test.describe("reduced motion", () => {
    test.use({ contextOptions: { reducedMotion: "reduce" } });

    test("the offer appears without a fade", async ({ page }) => {
      const fillet = await partWithBody(page, "Reduced motion");
      for (const el of [labelOf(fillet), leaderOf(fillet)]) {
        expect(
          await el.evaluate(
            (node) => getComputedStyle(node).transitionDuration,
          ),
        ).toBe("0s");
      }
    });
  });
});

for (const size of [
  { width: 1280, height: 800 },
  { width: 1440, height: 900 },
]) {
  test.describe(`founder frames @ ${size.width}x${size.height}`, () => {
    test.use({ viewport: size });

    test("said once on a new step, then on hover", async ({ page }) => {
      const fillet = await partWithBody(page, "Bracket plate");
      await expect(labelOf(fillet)).toHaveAttribute("data-announced", "true");
      await expectShown(page, fillet);
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/next-step-label-after-announced-${size.width}.png`,
      });

      await waitSettled(fillet);
      await expectHidden(fillet);
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/next-step-label-after-rest-${size.width}.png`,
      });

      const box = (await fillet.boundingBox())!;
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await expectShown(page, fillet);
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/next-step-label-after-hover-${size.width}.png`,
      });
    });
  });
}
