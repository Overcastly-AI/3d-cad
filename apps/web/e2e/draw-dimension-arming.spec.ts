import { expect, test, type Page } from "./fixtures";

import { calibratePlane, enterSketch, type PlaneMapper } from "./planeMap";
import { createPartViaApi, seedSession } from "./support";

/**
 * FLOW-A1 — THE SIZE YOU TYPE IN THE FIRST FRAME MUST NOT BE THROWN AWAY.
 *
 * The flow audit (docs/design/AUDIT-FLOW-2026-09.md, P0) drew a plate and typed
 * its size at once, and got an 80 x 40 x 20 part where 100 x 50 x 20 was asked
 * for — silently, with a green UI and an "armed" strip that had been claiming
 * *"Type a size"* since the instant the shape landed. Measured on that tree,
 * sweeping only the delay between the corner click and the first digit:
 *
 *   0 / 30 / 60 ms  -> width "", height ""      (every glyph discarded)
 *   120 / 250 ms    -> width "100", height "50"
 *
 * The gap between rendering the cells and being able to RECEIVE a keystroke is
 * the defect; a promise the UI keeps only after ~100 ms is not a promise.
 *
 * WHY THIS SPEC USES RAW CDP AND NOT `page.keyboard`, and why that is the whole
 * point: every Playwright call is a round trip, so `mouse.up()` followed by
 * `keyboard.press()` already hands the page several milliseconds of main-thread
 * time it would not get from a hand that was mid-keystroke when the button came
 * up. To gate the boundary itself, the release and the digit are queued on ONE
 * CDP connection with NO await between them — the browser processes them
 * back-to-back off the same socket, which is the fastest a user can possibly
 * be and the case the acceptance names ("zero intervening round trips").
 *
 * The synchronisation is therefore stated, not inherited: nothing is awaited
 * between the release and the keystroke ON PURPOSE, and every wait AFTER the
 * burst is on an explicit condition. There is no `waitForTimeout` standing in
 * for a settle here — that is exactly the accidental settle that would make
 * this gate stop seeing its own defect.
 */

const RECT = { w: 43, h: 27 };

interface Cdp {
  send: (method: string, params?: Record<string, unknown>) => Promise<unknown>;
  detach: () => Promise<void>;
}

/** Queue one character's keydown/keyup on an open CDP session, unawaited. */
function queueDigit(cdp: Cdp, character: string): void {
  const vk = character.charCodeAt(0);
  for (const type of ["keyDown", "keyUp"] as const) {
    void cdp.send("Input.dispatchKeyEvent", {
      type,
      ...(type === "keyDown" ? { text: character } : {}),
      key: character,
      code: `Digit${character}`,
      windowsVirtualKeyCode: vk,
      nativeVirtualKeyCode: vk,
    });
  }
}

/** Queue a Tab / Enter keypress on an open CDP session, unawaited. */
function queueKey(cdp: Cdp, key: "Tab" | "Enter"): void {
  const vk = key === "Tab" ? 9 : 13;
  for (const type of ["keyDown", "keyUp"] as const) {
    void cdp.send("Input.dispatchKeyEvent", {
      type,
      key,
      code: key,
      windowsVirtualKeyCode: vk,
      nativeVirtualKeyCode: vk,
    });
  }
}

/**
 * Finish the rectangle and type `keys` with NOTHING in between.
 *
 * The press is an ordinary hand — it approaches, drifts and dwells, because
 * `clickIntent` reads travel and dwell to tell a pick from a pan and a 0 px /
 * 0 ms press is a gesture no hand makes. Only the RELEASE is special: it and
 * the keystrokes go out on the same socket in one burst.
 *
 * `delayMs`, when given, inserts real elapsed time between the release and the
 * first key — used only to characterise the failure band, never by the gate.
 */
async function closeShapeAndType(
  page: Page,
  at: PlaneMapper,
  keys: (string | "Tab" | "Enter")[],
  delayMs = 0,
): Promise<void> {
  const b = at({ x: RECT.w, y: RECT.h });
  const cdp = (await page.context().newCDPSession(page)) as unknown as Cdp;
  const mouse = (type: string, extra = {}) => ({
    type,
    x: b.x,
    y: b.y,
    button: "left",
    buttons: type === "mouseReleased" ? 0 : 1,
    clickCount: 1,
    pointerType: "mouse",
    ...extra,
  });
  // Approach first, awaited: hover handlers run exactly as they do for a hand
  // arriving at the corner, and none of this is part of the measured window.
  await cdp.send(
    "Input.dispatchMouseEvent",
    mouse("mouseMoved", {
      buttons: 0,
      button: "none",
      x: b.x - 12,
      y: b.y - 8,
    }),
  );
  await cdp.send(
    "Input.dispatchMouseEvent",
    mouse("mouseMoved", { buttons: 0, button: "none" }),
  );
  // THE BURST. For a drag-draw tool the PRESS is what places the second corner
  // and arms the strip (`SketchScene` onPointerDown -> placeAt), so the press —
  // not the release — is the instant the clock starts. Everything from here is
  // queued on one socket with NO await between, which is why this measures the
  // commit boundary rather than four CDP round trips of accidental settle.
  void cdp.send("Input.dispatchMouseEvent", mouse("mousePressed"));
  void cdp.send("Input.dispatchMouseEvent", mouse("mouseReleased"));
  if (delayMs > 0) await page.waitForTimeout(delayMs);
  for (const key of keys) {
    if (key === "Tab" || key === "Enter") queueKey(cdp, key);
    else queueDigit(cdp, key);
  }
  await cdp.send("Runtime.evaluate", { expression: "1" }); // flush the queue
  await cdp.detach();
}

async function openRectGesture(page: Page): Promise<PlaneMapper> {
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, "FLOW-A1 plate");
  await page.goto(`/parts/${part.id}`);
  await enterSketch(page, "XY");
  const at = await calibratePlane(
    page,
    { x: 700, y: 600 },
    { x: 1000, y: 400 },
  );
  await page.getByTestId("tool-rect").click();
  const a = at({ x: 0, y: 0 });
  await page.mouse.move(a.x, a.y);
  await page.mouse.down();
  await page.waitForTimeout(90);
  await page.mouse.up();
  await page.mouse.move(
    at({ x: RECT.w, y: RECT.h }).x,
    at({ x: RECT.w, y: RECT.h }).y,
  );
  await expect(page.getByTestId("draw-dimensions")).toHaveAttribute(
    "data-state",
    "live",
  );
  return at;
}

test("a digit typed in the same instant the shape lands is kept (FLOW-A1)", async ({
  page,
}) => {
  const at = await openRectGesture(page);
  await closeShapeAndType(page, at, ["1"]);

  const width = page.getByTestId("draw-dimension-width");
  // The strip claims it is taking typing; that claim is the thing under test.
  await expect(page.getByTestId("draw-dimensions")).toHaveAttribute(
    "data-state",
    "armed",
  );
  await expect(width).toHaveValue("1");
  await expect(width).toBeFocused();
});

test("the audit's plate: 100 x 50 typed with no pause authors 100 x 50 (FLOW-A1)", async ({
  page,
}) => {
  const at = await openRectGesture(page);
  await closeShapeAndType(page, at, ["1", "0", "0", "Tab", "5", "0", "Enter"]);

  // The CELLS are the proxy; the DIMENSIONS are the product. The audit's plate
  // came out 80 x 40 with a green UI, so the assertion of record is what the
  // sketch ended up CONSTRAINED to — a cell that reads "100" over a rectangle
  // that is still 43 wide would be the same defect wearing a better mask.
  await expect(page.getByTestId("draw-dimensions")).toHaveCount(0);
  await expect
    .poll(
      async () =>
        (
          await page
            .locator('[data-testid^="glyph-"][data-kind="distance"]')
            .allInnerTexts()
        )
          .map((text) => text.trim())
          .sort(),
      { timeout: 30_000 },
    )
    .toEqual(["100", "50"]);
});

/**
 * The audit's own sweep, kept as a gate (its acceptance: "parameterise the
 * existing race sweep at 0/30/60/120 ms — all four must pass"). Re-measured on
 * this tree BEFORE the fix, every rung discarded every glyph:
 *
 *   0 / 0 / 30 / 60 / 120 ms -> width "", height ""   ← all five wrong
 *   250 / 500 ms             -> width "100", height "50"
 *
 * The band is wider here than in the audit (which had 120 ms surviving) because
 * this harness starts the clock at the PRESS, where the shape is actually
 * placed, instead of at the release a dwell later. Any rung that regresses is
 * the same silently-wrong-model defect, so they are gated rather than recorded.
 */
for (const delayMs of [0, 30, 60, 120]) {
  test(`a size typed ${delayMs} ms after the shape lands is kept (FLOW-A1)`, async ({
    page,
  }) => {
    const at = await openRectGesture(page);
    await closeShapeAndType(
      page,
      at,
      ["1", "0", "0", "Tab", "5", "0"],
      delayMs,
    );

    await expect(page.getByTestId("draw-dimension-width")).toHaveValue("100");
    await expect(page.getByTestId("draw-dimension-height")).toHaveValue("50");
  });
}
