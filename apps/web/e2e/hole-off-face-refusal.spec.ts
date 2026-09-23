/**
 * THE HOLE COMMAND REFUSES A POINT ITS OWN PANEL HAS CALLED OFF THE FACE (F-6).
 *
 * The product audit of 2026-09-16 drilled `X = -45` on a face spanning X
 * 0..120. The panel already read "Off the face outline — move it onto the
 * face"; CREATE stayed enabled; the click bought 5.6 s of evaluation and came
 * back `HOLE_OFF_BODY` / `SOLVE Failed` / `STATUS Partial`. Everything
 * downstream of a knowingly-invalid commit is wasted time, and a panel whose
 * button disagrees with its own copy teaches the user to distrust both.
 *
 * Driven in the real browser rather than only in jsdom because the claim is
 * that a USER cannot commit it: the refused cell is pressed through
 * `clickRefusedControl`, which first proves a pointer at its centre resolves to
 * the cell itself, and the proof it did nothing is that the editor is still
 * open and the tree has not grown — not that a handler was not called, which a
 * synthetic click could satisfy while the product shipped a hole anyway.
 */
import { expect, test, type Page } from "./fixtures";
import { seedCube } from "./partSeed";
import { clickRefusedControl, createPartViaApi, seedSession } from "./support";

/** Click the body's TOP face node — greatest z in the pick node's own name. */
async function clickTopFace(page: Page): Promise<void> {
  const nodes = page.locator('[data-testid^="plane-pick-face-"]');
  await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
  const count = await nodes.count();
  let bestZ = -Infinity;
  let bestIndex = 0;
  for (let i = 0; i < count; i += 1) {
    const label = (await nodes.nth(i).getAttribute("aria-label")) ?? "";
    const nums = label.match(/-?\d+(?:\.\d+)?/g) ?? [];
    const z = Number.parseFloat(nums[nums.length - 1] as string);
    if (Number.isFinite(z) && z > bestZ) {
      bestZ = z;
      bestIndex = i;
    }
  }
  await nodes.nth(bestIndex).click();
}

test("CREATE refuses a drill point the panel says is off the face", async ({
  page,
}) => {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Off-face hole");
  await seedCube(page, account.token, part.id);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("prop-volume")).toContainText("8,000", {
    timeout: 60_000,
  });
  const rowsBefore = await page.getByTestId("feature-row").count();

  await expect(page.getByTestId("new-hole")).toBeEnabled({ timeout: 30_000 });
  await page.getByTestId("new-hole").click();
  await expect(page.getByTestId("hole-editor")).toBeVisible();
  await clickTopFace(page);
  await expect(page.getByTestId("hole-placement")).toBeVisible();

  // On material first — the locator CAN resolve and the gate CAN open, so the
  // refusal below is a state change rather than a control that never works.
  await page.getByTestId("hole-position-x").fill("10");
  await page.getByTestId("hole-position-y").fill("10");
  const check = page.getByTestId("hole-position-check");
  await expect(check).toHaveAttribute("data-verdict", "material");
  const submit = page.getByTestId("hole-submit");
  await expect(submit).not.toHaveAttribute("aria-disabled", "true");

  // …now off the 20 mm face's outline entirely.
  await page.getByTestId("hole-position-x").fill("50");
  await expect(check).toHaveAttribute("data-verdict", "outside");
  await expect(check).toContainText("Off the face outline");
  await expect(submit).toHaveAttribute("aria-disabled", "true");
  await expect(submit).toHaveAccessibleDescription(
    "The drill point is not on the face.",
  );

  // Aim at the refused cell the way a user would. It stays in the
  // accessibility tree (that is how it explains itself), so the sanctioned
  // helper first proves a pointer at its centre reaches IT and not a neighbour,
  // then presses — and the proof of the refusal is that nothing was written.
  await clickRefusedControl(page, submit, "the refused hole CREATE");
  await expect(page.getByTestId("hole-editor")).toBeVisible();
  await expect(page.getByTestId("feature-row")).toHaveCount(rowsBefore);

  // And it is not a dead end: move the point back and the same click commits.
  await page.getByTestId("hole-position-x").fill("10");
  await expect(check).toHaveAttribute("data-verdict", "material");
  await submit.click();
  await expect(page.getByTestId("hole-editor")).toHaveCount(0, {
    timeout: 30_000,
  });
  await expect(page.getByTestId("feature-row")).toHaveCount(rowsBefore + 1, {
    timeout: 30_000,
  });
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 60_000,
  });
});
