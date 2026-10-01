/**
 * EDGE-MARK-OVERLAP, where the marks CANNOT be walked apart.
 *
 * `edge-mark-overlap.spec.ts` frames the 2 mm-wall enclosure close enough for
 * the seat pass to slide each rim mark clear of its twin. Zoomed out, as the
 * reference run's enclosure lip was, the outer and inner rims run a few pixels
 * apart along their whole length: no seat on either clears the other, the
 * 24 px discs overlap, and the browser hands a click to whichever disc is
 * stacked on top. That is how all four outer-corner marks on the lip picked
 * the wrong edges.
 *
 * The fix resolves a pointer on overlapping marks to the edge nearest the
 * pointer (Fusion 360's and SolidWorks' rule), so this pins, for all eight
 * rim marks at a framing where they do overlap:
 *
 *  1. the element at each mark's centre (`elementFromPoint`) is an edge mark,
 *     and the pointer there pre-highlights the mark's OWN edge;
 *  2. a real click there picks exactly that edge (and nothing else), and
 *     Space on the focused mark un-picks it again (keyboard access).
 */
import { expect, test, type Page } from "./fixtures";

import { waitForCameraStill } from "./invariants";
import {
  type Mark,
  openArmedEnclosure,
  readMarks,
  rimMarks,
} from "./shelledBox";
import { expectSeatsSettled, waitForFrames } from "./support";

test.use({ viewport: { width: 1280, height: 800 } });

/** Wheel notches out from `iso`, far enough that rim twins overlap. */
const ZOOM_OUT_NOTCHES = Number(process.env["EDGE_MARK_ZOOM_NOTCHES"] ?? 30);

async function zoomOut(page: Page, notches: number): Promise<void> {
  const box = await page.getByTestId("viewport").boundingBox();
  if (box === null) throw new Error("no viewport box");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  for (let n = 0; n < notches; n += 1) {
    await page.mouse.wheel(0, 120);
    await waitForFrames(page, 2);
  }
  await page.mouse.move(4, 4);
  await waitForCameraStill(page);
  await expectSeatsSettled(page, `zoomed out ${notches} notches`);
  await waitForCameraStill(page);
}

async function pressedMarks(page: Page): Promise<string[]> {
  return page.evaluate(() =>
    [
      ...document.querySelectorAll(
        '[data-testid^="edge-pick-"][aria-pressed="true"]',
      ),
    ]
      .map((el) => el.getAttribute("data-testid") ?? "")
      .sort(),
  );
}

/** The nearest other rim mark's centre, in px. */
function crowding(mark: Mark, rim: readonly Mark[]): number {
  let best = Infinity;
  for (const other of rim) {
    if (other.id === mark.id) continue;
    best = Math.min(best, Math.hypot(other.cx - mark.cx, other.cy - mark.cy));
  }
  return best;
}

/** Evidence for the founder, written only when `EDGE_MARK_SHOTS` names a file. */
async function captureEvidence(page: Page): Promise<void> {
  const path = process.env["EDGE_MARK_SHOTS"];
  if (path === undefined || path === "") return;
  await page.mouse.move(4, 4);
  await waitForFrames(page, 3);
  await page.screenshot({ path });
}

test("EDGE-MARK-OVERLAP, zoomed out: every overlapping rim mark picks its own edge", async ({
  page,
}) => {
  test.setTimeout(300_000);
  await openArmedEnclosure(page);
  await zoomOut(page, ZOOM_OUT_NOTCHES);
  const viewport = page.getByTestId("viewport");

  const first = rimMarks(await readMarks(page));
  expect(first.outer.length, "four outer rim marks").toBe(4);
  expect(first.inner.length, "four inner rim marks").toBe(4);
  const rim = [...first.outer, ...first.inner];
  for (const mark of rim) {
    console.log(
      `    [rim] ${mark.id} (${mark.mid.join(",")}) @ (${Math.round(mark.cx)},` +
        `${Math.round(mark.cy)}) nearest ${crowding(mark, rim).toFixed(1)} px` +
        ` top=${mark.top} buried=${mark.buried}`,
    );
  }
  expect(rim.filter((m) => m.buried).map((m) => m.id)).toEqual([]);
  // Not vacuous: at this framing another mark really does cover some rim
  // mark's own centre, which is the defect's exact precondition.
  expect(
    rim.filter((m) => m.top !== m.id).length,
    "a rim mark's centre is covered at this zoom (else this spec tests nothing)",
  ).toBeGreaterThan(0);

  // An outer rim whose centre another mark covers goes first, so the evidence
  // frame shows the reported case: the outer rim clicked, and what it picked.
  const lead = first.outer.filter((m) => m.top !== m.id).slice(0, 1);
  const order = [...lead, ...rim.filter((m) => !lead.includes(m))];
  const wrong: string[] = [];
  let shot = false;
  for (const target of order) {
    await page.mouse.move(4, 4);
    await expect(viewport).not.toHaveAttribute("data-edge-pick-hover", /./);
    await expectSeatsSettled(page, `before ${target.id}`);
    const now = (await readMarks(page)).find((m) => m.id === target.id);
    if (now === undefined) throw new Error(`${target.id} is not drawn`);

    // 1. The thing at the mark's centre is an edge mark, and it means THIS edge.
    expect(now.top, `an edge mark is on top at ${now.id}'s centre`).toMatch(
      /^edge-pick-\d+$/,
    );
    await page.mouse.move(now.cx, now.cy);
    await expect
      .poll(() => viewport.getAttribute("data-edge-pick-hover"), {
        timeout: 2_000,
      })
      .not.toBeNull();
    const hover = await viewport.getAttribute("data-edge-pick-hover");
    if (hover !== String(now.index)) {
      wrong.push(`${now.id} (top=${now.top}) hovers edge ${hover}`);
    }

    // 2. A real click there picks exactly this edge.
    await page.mouse.click(now.cx, now.cy);
    await waitForFrames(page, 2);
    if (!shot && first.outer.includes(target)) {
      shot = true;
      await captureEvidence(page);
    }
    const pressed = await pressedMarks(page);
    if (pressed.join() !== now.id) {
      wrong.push(`${now.id} (top=${now.top}) picked [${pressed.join(", ")}]`);
    }
    // Un-pick from the KEYBOARD (Space on the focused mark), which is the
    // other way in that this fix must keep: a key press has no pointer, so it
    // toggles the focused mark's own edge.
    for (const id of pressed) {
      await page.getByTestId(id).focus();
      await page.keyboard.press("Space");
      // Focus pre-highlights the focused edge; release it for the next check.
      await page.getByTestId(id).blur();
    }
    await expect.poll(() => pressedMarks(page)).toEqual([]);
  }
  expect(wrong, "a rim mark picked or highlighted another edge").toEqual([]);
});
