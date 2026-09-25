import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * THE OFFSET-PLANE PANEL SAYS WHY "SKETCH HERE" IS GREY (REASON-GATE rule).
 *
 * Every feature editor follows one rule: the commit action is enabled iff there
 * is no blocker sentence, and the sentence is shown (`submitBlocker.ts`). The
 * inline "sketch at a height" panel did not. Clear its distance and "Sketch
 * here" went grey through the native `disabled` attribute: it could not be
 * hovered or focused, it dropped out of the accessibility tree, and it said
 * nothing. That is a dead control at the exact moment the user needs to be told
 * what is missing.
 *
 * Asserted as INK and with the user's own mechanisms, never as markup:
 * `toBeVisible()` passes a node clipped out of frame and `textContent` reads
 * hidden nodes. So the sentence must have a real box that `elementFromPoint`
 * resolves to the confirm cell itself, the cell must take keyboard focus (a
 * natively-disabled button cannot), and a real click on it must write nothing.
 */

async function openOffsetPanel(page: Page): Promise<string> {
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, "Offset reason");
  await page.goto(`/parts/${part.id}`);
  await page.getByTestId("new-sketch").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("Pick a plane");
  await page.getByTestId("datum-offset-plane").click();
  await expect(page.getByTestId("offset-plane-panel")).toBeVisible();
  return part.id;
}

const SIZES = [
  { label: "1280", width: 1280, height: 800 },
  { label: "1440", width: 1440, height: 900 },
] as const;

for (const size of SIZES) {
  test(`a cleared offset explains the grey "Sketch here" (${size.width}x${size.height})`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: size.width, height: size.height });
    const partId = await openOffsetPanel(page);
    const writes: string[] = [];
    page.on("request", (request) => {
      if (
        request.method() === "POST" &&
        request.url().includes(`/parts/${partId}/features`)
      ) {
        writes.push(request.url());
      }
    });

    await page.getByTestId("offset-plane-offset").fill("");
    const confirm = page.getByTestId("offset-plane-confirm");
    // Captured before the assertions, so a run against the pre-fix tree still
    // writes its frame (that run is where the "before" half comes from).
    await page.mouse.move(size.width - 40, size.height - 40);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/offset-plane-reason-after-${size.label}.png`,
    });

    // Gated the way this product gates: `aria-disabled`, which Playwright's
    // `toBeDisabled` honours, and NOT the native attribute.
    await expect(confirm).toBeDisabled();
    await expect(confirm).not.toHaveAttribute("disabled", /.*/);

    // The sentence is ink, inside the cell it explains.
    const reason = confirm.locator("[data-disabled-reason]");
    await expect(reason).toHaveText("Enter the offset.");
    const box = await reason.boundingBox();
    expect(box, "the reason has a box").not.toBeNull();
    expect(box!.width).toBeGreaterThan(20);
    expect(box!.height).toBeGreaterThan(6);
    const hit = await page.evaluate(
      ([x, y]) =>
        document
          .elementFromPoint(x as number, y as number)
          ?.closest("[data-testid]")
          ?.getAttribute("data-testid") ?? null,
      [box!.x + box!.width / 2, box!.y + box!.height / 2],
    );
    expect(hit, "the reason hit-tests to its own cell").toBe(
      "offset-plane-confirm",
    );
    // A screen reader gets the same sentence as the eye.
    await expect(confirm).toHaveAccessibleDescription("Enter the offset.");

    // Still reachable: it takes focus, and a real click writes nothing.
    await confirm.focus();
    await expect(confirm).toBeFocused();
    await page.mouse.click(box!.x + box!.width / 2, box!.y + box!.height / 2);
    await page.keyboard.press("Enter");

    // Type a distance and the sentence goes; the action is live again.
    await page.getByTestId("offset-plane-offset").fill("30");
    await expect(confirm).toBeEnabled();
    await expect(reason).toHaveCount(0);

    // And the gated presses above authored NOTHING, proved against a press that
    // does: after this one, exactly ONE datum write has ever been sent. (A bare
    // "no write yet" read right after the press would race the request.)
    const authored = page.waitForResponse(
      (r) =>
        r.url().includes(`/parts/${partId}/features`) &&
        r.request().method() === "POST",
    );
    await confirm.click();
    expect((await authored).status()).toBe(201);
    expect(writes, "only the ungated press may author a datum").toHaveLength(1);
  });
}
