/**
 * THE HOLE COMMAND'S COMMIT CONTROL SAYS WHAT ITS PANEL SAYS (F-6).
 *
 * The product audit of 2026-09-16 drilled `X = -45` on a face spanning X
 * 0..120. The placement line read "Off the face outline — move it onto the
 * face" while CREATE carried a bare "Enter"; the click bought 5.6 s of
 * evaluation and came back `HOLE_OFF_BODY`. The panel knew and the button did
 * not say.
 *
 * The button now says it — in its caption and, for a screen reader, by taking
 * the placement line as its description — and it STAYS A LIVE CONTROL. The
 * client's verdict reads the outline off overlay edges within 1e-3 mm of the
 * face plane, so a file sewn looser than that can make a point on material
 * read `outside` (pinned in `HoleEditor.test.tsx`); refusing on it would make a
 * legal hole a dead end, while letting it through costs a named, recoverable
 * `hole_off_body` from the kernel. That honest-failure path is asserted by
 * `import-remix.spec.ts` ("still fails HONESTLY") and `repick-face.spec.ts`;
 * this spec asserts the half they do not: that the warning is ON the control a
 * user is about to press, and leaves it the moment the point is fixed.
 */
import { expect, test, type Page } from "./fixtures";
import { seedCube } from "./partSeed";
import { createPartViaApi, seedSession } from "./support";

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

test("CREATE carries the off-the-face warning and drops it once the point is fixed", async ({
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

  const check = page.getByTestId("hole-position-check");
  const submit = page.getByTestId("hole-submit");

  // Off the 20 mm face's outline entirely: the placement line says so, and so
  // does the control the user is about to press — which stays pressable.
  await page.getByTestId("hole-position-x").fill("50");
  await page.getByTestId("hole-position-y").fill("10");
  await expect(check).toHaveAttribute("data-verdict", "outside");
  await expect(check).toContainText("Off the face outline");
  await expect(submit).toContainText("off the face");
  await expect(submit).toHaveAccessibleDescription(/Off the face outline/);
  await expect(submit).not.toHaveAttribute("aria-disabled", "true");

  // Back on material: the warning leaves the button with the verdict, and the
  // same control commits a real hole.
  await page.getByTestId("hole-position-x").fill("10");
  await expect(check).toHaveAttribute("data-verdict", "material");
  await expect(submit).not.toContainText("off the face");
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
