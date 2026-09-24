import { expect, test } from "./fixtures";

import { SESSION_STORAGE_KEY } from "../src/auth/session";
import { SKETCH_DRAFT_KEY_PREFIX } from "../src/routes/sketchDraft";
import { registerViaApi, TEST_PASSWORD } from "./support";

/**
 * W0REV-3 — a browser whose storage is full of sketch drafts must still keep
 * the user signed in across a reload.
 *
 * Before: drafts were never swept, so they could fill the origin's quota; the
 * session write on sign-in then failed, the failure was swallowed, and the
 * user met it as "logged out on reload" with nothing pointing at the cause.
 * Now a full storage evicts drafts (oldest first) to make room for the
 * session, and touches nothing that is not a draft.
 */
test.describe("session persistence with a full storage (W0REV-3)", () => {
  test("signing in with storage full of drafts evicts drafts, not the session", async ({
    page,
  }) => {
    const { email } = await registerViaApi(page);
    await page.goto("/sign-in");
    await expect(page.getByTestId("auth-panel")).toBeVisible();

    // Fill the REAL quota after app start (the start-up sweep only trims the
    // drafts to their budget; it never promises room), with draft-shaped
    // entries, oldest first, plus one neighbour that is not ours.
    const filled = await page.evaluate((prefix) => {
      window.localStorage.setItem("e2e-foreign-key", "keep-me");
      const draft = (chars: number, index: number) =>
        JSON.stringify({
          version: 1,
          savedAt: Date.now() - 60_000 + index,
          plane: { kind: "origin", base: "XY" },
          entities: [{ kind: "point", id: "x".repeat(chars) }],
          constraints: [],
          featureId: null,
          nextIdIndex: 2,
          revision: 1,
          userConstrained: false,
        });
      let index = 0;
      for (const chars of [1 << 19, 1 << 14, 1 << 9, 16]) {
        for (;;) {
          try {
            window.localStorage.setItem(
              `${prefix}fill-${index}`,
              draft(chars, index),
            );
            index += 1;
          } catch {
            break;
          }
        }
      }
      // The precondition, measured rather than assumed: a session-sized write
      // must now be refused, or this test proves nothing.
      let full = false;
      try {
        window.localStorage.setItem("e2e-probe", "x".repeat(400));
        window.localStorage.removeItem("e2e-probe");
      } catch {
        full = true;
      }
      return { drafts: index, full };
    }, SKETCH_DRAFT_KEY_PREFIX);
    expect(filled.full).toBe(true);
    expect(filled.drafts).toBeGreaterThan(1);

    await page.getByTestId("auth-email").fill(email);
    await page.getByTestId("auth-password").fill(TEST_PASSWORD);
    await page.getByTestId("auth-password").press("Enter");
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByTestId("session-email")).toHaveText(email);

    const after = await page.evaluate(
      ({ prefix, sessionKey }) => {
        const keys = Object.keys(window.localStorage);
        return {
          session: window.localStorage.getItem(sessionKey) !== null,
          drafts: keys.filter((key) => key.startsWith(prefix)),
          foreign: window.localStorage.getItem("e2e-foreign-key"),
        };
      },
      { prefix: SKETCH_DRAFT_KEY_PREFIX, sessionKey: SESSION_STORAGE_KEY },
    );
    expect(after.session).toBe(true);
    // Drafts made the room, oldest first; the neighbour was never touched.
    expect(after.drafts.length).toBeLessThan(filled.drafts);
    expect(after.drafts).not.toContain(`${SKETCH_DRAFT_KEY_PREFIX}fill-0`);
    expect(after.foreign).toBe("keep-me");

    // The user-visible half: a reload keeps them signed in.
    await page.reload();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByTestId("session-email")).toHaveText(email);
  });
});
