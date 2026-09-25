import { expect, test, type Page } from "./fixtures";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * THE DRO HOLDS STILL. The sketch readout sits over the canvas, so any change
 * in its size moves chrome over geometry while the user draws.
 *
 * Measured before this spec existed, at 1280x800. The DRO ran 12..593 px, and
 * the SOLVE cell MOUNTED on the sketch's first save, widening it to 687 px
 * while it read "SOLVING…". It then widened to 834 px when the status became
 * "DOF 3 · UNDER-CONSTRAINED". That is a 241 px swing across the centre line,
 * where the sketch origin sits in the normal-on framing. A click aimed there
 * could land on chrome or on the canvas depending on the solver's timing,
 * which is what made `constraints.spec.ts:1112` intermittent (`8c55183`). The
 * snap caption changed width with the grid state too.
 *
 * So this watches the DRO's box EVERY FRAME, through each thing that used to
 * resize it: the first save and its solve, the snap toggle, and a new grid
 * step. It asserts one box for the whole session, left of the canvas centre
 * line, at both laptop widths.
 *
 * `SHOT_TAG=before` names the screenshots for a capture against the old tree.
 * They are taken BEFORE the assertions, so a red run still leaves its picture.
 */
const SHOT_TAG = process.env["SHOT_TAG"] ?? "after";

/** The chrome keeps this much clear of the canvas centre line, in px. */
const CENTRE_CLEARANCE_PX = 24;

interface Rect {
  x: number;
  y: number;
  right: number;
  bottom: number;
}

async function watchDro(page: Page): Promise<void> {
  await page.evaluate(() => {
    const w = window as unknown as {
      __dro: { rects: string[]; solves: string[] };
    };
    w.__dro = { rects: [], solves: [] };
    const step = () => {
      const dro = document.querySelector('[data-testid="sketch-dro"]');
      if (dro !== null) {
        const r = dro.getBoundingClientRect();
        const rect = [r.x, r.y, r.right, r.bottom]
          .map((v) => v.toFixed(1))
          .join(",");
        if (w.__dro.rects.at(-1) !== rect) w.__dro.rects.push(rect);
        const solve =
          document.querySelector('[data-testid="dro-solve"]')?.textContent ??
          "(no solve cell)";
        if (w.__dro.solves.at(-1) !== solve) w.__dro.solves.push(solve);
      }
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}

/** The GRID cell holds its select, whatever the select lists. */
async function expectGridHolds(page: Page, what: string): Promise<void> {
  const spill = await page
    .getByTestId("sketch-grid-step")
    .evaluate((select) => {
      // select -> the InlineSelect pill -> the DRO's GRID cell.
      const cell = select.parentElement?.parentElement;
      if (!cell) throw new Error("the GRID select has no cell");
      return cell.scrollWidth - cell.clientWidth;
    });
  expect(
    spill,
    `the GRID step overflows its column (${what})`,
  ).toBeLessThanOrEqual(0);
}

async function watched(
  page: Page,
): Promise<{ rects: Rect[]; solves: string[] }> {
  const raw = await page.evaluate(
    () =>
      (window as unknown as { __dro: { rects: string[]; solves: string[] } })
        .__dro,
  );
  return {
    solves: raw.solves,
    rects: raw.rects.map((s) => {
      const [x, y, right, bottom] = s.split(",").map(Number) as [
        number,
        number,
        number,
        number,
      ];
      return { x, y, right, bottom };
    }),
  };
}

for (const size of [
  { width: 1280, height: 800 },
  { width: 1440, height: 900 },
]) {
  test(`the DRO keeps one footprint, clear of the centre, at ${size.width}`, async ({
    page,
  }) => {
    await page.setViewportSize(size);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "DRO footprint");
    await page.goto(`/parts/${part.id}`);
    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XY").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
    await expect(page.getByTestId("sketch-dro")).toBeVisible();
    await watchDro(page);

    // The snap toggle, both ways, and a different grid step.
    const snap = page.getByTestId("dro-snap");
    await page.keyboard.press("g");
    await expect(snap).toHaveAttribute("aria-pressed", "false");
    // The longest caption ("points · no grid · G") fits its fixed column: a
    // cell that cannot grow must not spill into its neighbour either.
    const spill = await snap.evaluate((el) => el.scrollWidth - el.clientWidth);
    expect(spill, "the SNAP caption overflows its column").toBeLessThanOrEqual(
      0,
    );
    await page.keyboard.press("g");
    await expect(snap).toHaveAttribute("aria-pressed", "true");
    await page.getByTestId("sketch-grid-step").selectOption("0.1");
    await page.getByTestId("sketch-grid-step").selectOption("1");
    // The grid's step labels follow the document unit. In an inch or foot
    // document the step in use (1 mm by default) is listed as itself, which
    // is the longest label the GRID column has to hold, and the finest step
    // (0.01 mm) is longer still. A fixed column must hold them all: the panel
    // does not clip, so a label that did not fit spilled over the canvas while
    // the DRO's own box stayed put (review B1 on `e3bd6aa`).
    const units = page.getByTestId("document-unit-select");
    const step = page.getByTestId("sketch-grid-step");
    for (const [unit, mm] of [
      ["in", "1"],
      ["ft", "1"],
      ["ft", "0.01"],
      ["in", "0.01"],
    ] as const) {
      await units.selectOption("mm");
      await expect(step).toContainText("mm");
      await step.selectOption(mm);
      await units.selectOption(unit);
      await expect(step).toContainText(unit);
      if (unit === "in" && mm === "1") {
        await page.screenshot({
          path: `${SCREENSHOT_DIR}/sketch-dro-footprint-${size.width}-inch-${SHOT_TAG}.png`,
        });
      }
      await expectGridHolds(page, `${mm} mm in a ${unit} document`);
    }
    await units.selectOption("mm");
    await expect(step).toContainText("mm");
    await step.selectOption("1");

    // A constrained line: the first save, a solve, a DOF readout.
    const viewport = await page.getByTestId("viewport").boundingBox();
    if (viewport === null) throw new Error("no viewport box");
    const cx = viewport.x + viewport.width / 2;
    const cy = viewport.y + viewport.height / 2;
    await page.keyboard.press("l");
    await page.mouse.click(cx - 80, cy - 90);
    await page.mouse.click(cx + 80, cy - 80);
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await page.mouse.click(cx, cy - 85);
    await page.keyboard.press("h");
    await expect(page.getByTestId("dro-solve")).toContainText("DOF", {
      timeout: 15_000,
    });
    await page.mouse.move(cx + 200, cy + 150);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-dro-footprint-${size.width}-${SHOT_TAG}.png`,
    });

    const { rects, solves } = await watched(page);
    console.log(
      `[dro ${size.width}] ${rects.length} box(es): ` +
        rects
          .map((r) => `${r.x}..${r.right} x ${r.y}..${r.bottom}`)
          .join(" | ") +
        `; solve readouts: ${solves.join(" -> ")}`,
    );
    expect(
      rects.length,
      `the DRO changed size or place ${rects.length - 1} time(s) while ` +
        `sketching (solve readouts seen: ${solves.join(" -> ")})`,
    ).toBe(1);
    const [only] = rects as [Rect];
    expect(
      only.right,
      `the DRO's right edge (${only.right}) must stay ` +
        `${CENTRE_CLEARANCE_PX} px left of the canvas centre line (${cx})`,
    ).toBeLessThanOrEqual(cx - CENTRE_CLEARANCE_PX);
  });
}
