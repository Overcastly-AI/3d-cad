/**
 * AN UNDO THAT DID NOT RUN HAS TO SAY SO (F-10's family).
 *
 * `executeHistoryStep` has four outcomes and two of them used to render
 * nothing. The `stale` one is reachable with two windows on one part, and its
 * silence is the dangerous half: the resync that follows it PUTS A DIFFERENT
 * MODEL ON SCREEN, so the user presses Undo, sees the tree change, and has no
 * way to know their step never ran. Measured against the unfixed app here:
 * feature rows 3 -> 2 on a click that undid nothing, `history-error` absent,
 * the button still enabled, no reason text anywhere.
 *
 * The assertion is on what the USER can read — a node carrying the sentence —
 * rather than on the outcome value, because "the app knows it resynced" was
 * already true before this fix and is not the property that was missing.
 */
import { expect, test } from "./fixtures";
import { seedAllEdgeFillet, seedCube } from "./partSeed";
import { createPartViaApi, seedSession, seedStoredSession } from "./support";

test("a stale undo says the step did not run", async ({ page, context }) => {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "History resync");
  const version = await seedCube(page, account.token, part.id);
  await seedAllEdgeFillet(page, account.token, part.id, 2, version);

  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 60_000,
  });
  await expect(page.getByTestId("feature-row")).toHaveCount(3);
  // The locator CAN resolve — proved below by the notice appearing — so this
  // "absent" reading is a real before, not a typo that can never match.
  await expect(page.getByTestId("history-resynced")).toHaveCount(0);

  // A second window moves the tree underneath the first one.
  const other = await context.newPage();
  await seedStoredSession(other, account.token, account.user);
  await other.goto(`/parts/${part.id}`);
  await expect(other.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 60_000,
  });
  await other.getByTestId("undo-button").click();
  await expect(other.getByTestId("feature-row")).toHaveCount(2, {
    timeout: 30_000,
  });

  // The first window still believes it can undo, and its cached tree version
  // is now stale — so its step is refused and the app resyncs.
  await page.getByTestId("undo-button").click();
  const notice = page.getByTestId("history-resynced");
  await expect(notice).toBeVisible({ timeout: 30_000 });
  await expect(notice).toContainText("nothing was undone here");
  // A resync is not a failure and must not be dressed as one.
  await expect(page.getByTestId("history-error")).toHaveCount(0);
  await expect(notice).toHaveAttribute("role", "status");

  // And it is dismissible, like every other HUD in the viewport.
  await page.getByTestId("history-error-dismiss").click();
  await expect(notice).toHaveCount(0);
});
