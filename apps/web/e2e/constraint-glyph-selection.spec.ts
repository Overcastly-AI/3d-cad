/**
 * QA-SNAP4-4 — A CONSTRAINT GLYPH MUST BE SELECTABLE, AND DELETE MUST REMOVE IT.
 *
 * This is the escape hatch SNAP-4's refusal names by hand: "Already grounded on
 * the Origin — the join there holds this point" only stops being a dead end if
 * the user can reach that join, drop it, and pin the point themselves. Until
 * `ConstraintGlyphs.tsx` stopped the click, they could not: drei mounts `Html`
 * INTO the div r3f listens on, React attaches its listeners to each PORTAL
 * container (a DESCENDANT of that div), so the glyph's own handler ran FIRST and
 * the pick plane's `selectAt` then cleared `selectedConstraint` on the very same
 * click. `aria-pressed` never left `"false"` and Delete had nothing to remove.
 *
 * WHY THESE ASSERTIONS AND NOT CHEAPER ONES. The failure was invisible to every
 * spec in the repo because `constraints.spec.ts` only ever removes a DIMENSION,
 * through its editor's Remove button — a different code path entirely. So each
 * step here is measured with the USER'S mechanism and nothing that stands in for
 * it:
 *
 *  - the glyph is proved HITTABLE before it is clicked (non-zero box AND
 *    `elementFromPoint` at its centre resolving to the glyph itself), because
 *    three separate defects this repo has shipped presented as "the control is
 *    there and cannot be touched";
 *  - the click is a real `page.mouse.click` at that measured centre — never
 *    `locator.click({ force: true })`, which skips the only check that asks
 *    whether a user could have hit it;
 *  - selection is read off `aria-pressed`, the same fact a screen reader hears;
 *  - the removal is corroborated by the SOLVER's own DOF, which is derived from
 *    the constraint system rather than from the DOM that drew the glyph.
 */
import { expect, test, type Locator, type Page } from "./fixtures";

import { createPartViaApi, seedSession } from "./support";

interface Pt {
  x: number;
  y: number;
}
type Mapper = (pt: Pt) => Pt;

const SOLVE_TIMEOUT_MS = 40_000;

const glyphsOfKind = (page: Page, kind: string): Locator =>
  page.locator(`[data-testid^="glyph-"][data-kind="${kind}"]`);

async function enterSketch(page: Page): Promise<void> {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
}

/**
 * mm -> px, read off the live DRO with the grid OFF: an aim a few tenths from
 * zero must stay a few tenths from zero, or the origin snap under test is
 * indistinguishable from the grid rounding the aim there anyway.
 */
async function calibrate(page: Page, s1: Pt, s2: Pt): Promise<Mapper> {
  await page.keyboard.press("g");
  let last: number | null = null;
  await expect
    .poll(
      async () => {
        await page.mouse.move(s1.x + 3, s1.y);
        await page.mouse.move(s1.x, s1.y);
        const v = Number.parseFloat(
          await page.getByTestId("dro-x").innerText(),
        );
        const stable = last !== null && Number.isFinite(v) && v === last;
        last = v;
        return stable;
      },
      { timeout: 20_000 },
    )
    .toBe(true);
  const read = async (sx: number, sy: number, notX?: number): Promise<Pt> => {
    await page.mouse.move(sx, sy);
    await expect
      .poll(async () => {
        const v = Number.parseFloat(
          await page.getByTestId("dro-x").innerText(),
        );
        return (
          Number.isFinite(v) &&
          (notX === undefined || Math.abs(v - notX) > 1e-9)
        );
      })
      .toBe(true);
    return {
      x: Number.parseFloat(await page.getByTestId("dro-x").innerText()),
      y: Number.parseFloat(await page.getByTestId("dro-y").innerText()),
    };
  };
  const p1 = await read(s1.x, s1.y);
  const p2 = await read(s2.x, s2.y, p1.x);
  const kx = (s2.x - s1.x) / (p2.x - p1.x);
  const ky = (s2.y - s1.y) / (p2.y - p1.y);
  return (pt) => ({
    x: s1.x + (pt.x - p1.x) * kx,
    y: s1.y + (pt.y - p1.y) * ky,
  });
}

async function clickAt(page: Page, at: Mapper, pt: Pt): Promise<void> {
  const px = at(pt);
  await page.mouse.move(px.x, px.y);
  await page.mouse.click(px.x, px.y);
}

/** One line whose first click lands on the origin — SNAP-3 authors the join. */
async function drawGroundedLine(page: Page, at: Mapper): Promise<void> {
  await page.keyboard.press("l");
  await clickAt(page, at, { x: 0.3, y: -0.2 });
  await clickAt(page, at, { x: 40.4, y: 30.4 });
  await page.keyboard.press("Escape");
  await expect(glyphsOfKind(page, "coincident")).toHaveCount(1);
}

/**
 * Click a glyph THE WAY A USER DOES, and prove first that a user could.
 *
 * Returns nothing and asserts plenty: a zero-area box, or a centre that
 * resolves to something else, is the whole defect class this spec exists for —
 * measured BEFORE the click, so a failure names the reason instead of leaving a
 * bare "aria-pressed was false".
 */
async function clickGlyph(page: Page, glyph: Locator): Promise<void> {
  const box = await glyph.boundingBox();
  expect(box, "the glyph must have a layout box at all").not.toBeNull();
  if (box === null) return;
  expect(box.width, "a zero-width glyph is unhittable").toBeGreaterThan(0);
  expect(box.height, "a zero-height glyph is unhittable").toBeGreaterThan(0);

  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;
  const testId = await glyph.getAttribute("data-testid");
  const atCentre = await page.evaluate(
    ({ x, y }: { x: number; y: number }) => {
      const el = document.elementFromPoint(x, y);
      return el === null ? null : el.getAttribute("data-testid");
    },
    { x: cx, y: cy },
  );
  expect(atCentre, "the glyph's own centre must resolve to the glyph").toBe(
    testId,
  );

  await page.mouse.click(cx, cy);
}

test.describe("constraint glyph selection (QA-SNAP4-4)", () => {
  test("a coincident glyph selects on click, toggles off, and Delete removes it", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "glyph select coincident");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page);
    const at = await calibrate(page, { x: 700, y: 620 }, { x: 1000, y: 420 });
    await drawGroundedLine(page, at);

    // Pin the FAR endpoint. Two reasons, and neither is decoration: it puts a
    // live DOF readout on the screen (the readout only exists once a solve has
    // run, and the draw's inferred join does not trigger one), and it leaves the
    // sketch fully determined, so the two degrees of freedom that come back
    // below can only have come from the join this test deletes.
    await clickAt(page, at, { x: 40.4, y: 30.4 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 pt");
    await page.keyboard.press("x");
    await expect(page.getByTestId("dro-solve")).toHaveText(
      "DOF 0 · CONVERGED",
      {
        timeout: SOLVE_TIMEOUT_MS,
      },
    );

    const join = glyphsOfKind(page, "coincident").first();
    await expect(join).toHaveAttribute("aria-pressed", "false");

    // (1) THE CLICK STICKS. This is the assertion the whole ticket turns on:
    // before the fix the glyph's handler ran and the pick plane undid it in the
    // same event, so this read `"false"` on a click that had landed.
    await clickGlyph(page, join);
    await expect(join).toHaveAttribute("aria-pressed", "true");

    // (2) IT IS A TOGGLE, not a latch — the same click that took it lets go.
    // Also the negative control for "something else happened to set it": a
    // handler that never ran cannot clear it either.
    await clickGlyph(page, join);
    await expect(join).toHaveAttribute("aria-pressed", "false");

    // (3) DELETE REMOVES THAT CONSTRAINT. Two independent readings: the glyph
    // goes, and the SOLVER hands back the two degrees of freedom the join was
    // holding — a fact derived from the constraint system, not from the DOM.
    await clickGlyph(page, join);
    await expect(join).toHaveAttribute("aria-pressed", "true");
    await page.keyboard.press("Delete");
    await expect(glyphsOfKind(page, "coincident")).toHaveCount(0);
    // The pin survives — Delete removed the constraint that was HELD, not
    // whatever happened to be nearest the pointer.
    await expect(glyphsOfKind(page, "fixed")).toHaveCount(1);
    await expect(page.getByTestId("dro-solve")).toHaveText(
      "DOF 2 · UNDER-CONSTRAINED",
      { timeout: SOLVE_TIMEOUT_MS },
    );
  });

  test("a fixed glyph selects on click and Delete removes it", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "glyph select fixed");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page);
    const at = await calibrate(page, { x: 700, y: 620 }, { x: 1000, y: 420 });
    await drawGroundedLine(page, at);

    // Pin the FAR endpoint — the free one, so the pin is accepted rather than
    // refused as redundant (SNAP-4). That converges the sketch.
    await clickAt(page, at, { x: 40.4, y: 30.4 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 pt");
    await page.keyboard.press("x");
    await expect(glyphsOfKind(page, "fixed")).toHaveCount(1);
    await expect(page.getByTestId("dro-solve")).toHaveText(
      "DOF 0 · CONVERGED",
      {
        timeout: SOLVE_TIMEOUT_MS,
      },
    );

    const pin = glyphsOfKind(page, "fixed").first();
    await clickGlyph(page, pin);
    await expect(pin).toHaveAttribute("aria-pressed", "true");

    await page.keyboard.press("Delete");
    await expect(glyphsOfKind(page, "fixed")).toHaveCount(0);
    // The join survives — Delete removed the constraint that was HELD, not
    // whatever happened to be nearest the pointer.
    await expect(glyphsOfKind(page, "coincident")).toHaveCount(1);
    await expect(page.getByTestId("dro-solve")).toHaveText(
      "DOF 2 · UNDER-CONSTRAINED",
      { timeout: SOLVE_TIMEOUT_MS },
    );
  });
});
