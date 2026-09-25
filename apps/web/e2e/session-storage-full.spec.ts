import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";

import {
  SESSION_NOT_PERSISTED_MESSAGE,
  SESSION_STORAGE_KEY,
  SIGN_IN_WILL_NOT_PERSIST_MESSAGE,
} from "../src/auth/session";
import { SKETCH_DRAFT_KEY_PREFIX } from "../src/routes/sketchDraft";
import { registerViaApi, SCREENSHOT_DIR, TEST_PASSWORD } from "./support";

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
    // Eviction made the room, so there is nothing to warn about.
    await expect(page.getByTestId("session-persist-notice")).toHaveCount(0);
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

/**
 * Where eviction CANNOT help — the quota is full of data that is not ours —
 * the session will not survive a reload, and the user must be told so on
 * screen, not only in the store and the console. Before sign-in (the sign-in
 * page probes) and after it (the top bar), because a successful sign-in
 * leaves the sign-in page at once.
 */
test.describe("a sign-in the browser will not store is said out loud (W0REV-3)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("both surfaces show a reachable, announced, dismissible notice that covers nothing", async ({
    page,
  }) => {
    const { email } = await registerViaApi(page);
    await page.goto("/sign-in");
    await expect(page.getByTestId("auth-panel")).toBeVisible();
    // With room to spare there is nothing to say.
    await expect(page.getByTestId("sign-in-storage-notice")).toHaveCount(0);

    // Fill the quota with keys that are NOT drafts, so no eviction can help.
    const full = await page.evaluate(() => {
      let index = 0;
      for (const chars of [1 << 19, 1 << 14, 1 << 9, 16]) {
        for (;;) {
          try {
            window.localStorage.setItem(
              `e2e-other-app-${index}`,
              "y".repeat(chars),
            );
            index += 1;
          } catch {
            break;
          }
        }
      }
      try {
        window.localStorage.setItem("e2e-probe", "x".repeat(400));
        window.localStorage.removeItem("e2e-probe");
        return false;
      } catch {
        return true;
      }
    });
    expect(full).toBe(true);

    // Before sign-in: the page probes on arrival and warns up front.
    await page.reload();
    const warning = page.getByTestId("sign-in-storage-notice");
    await expect(warning).toBeVisible();
    await expect(
      page
        .getByRole("status")
        .filter({ hasText: SIGN_IN_WILL_NOT_PERSIST_MESSAGE }),
    ).toHaveCount(1);
    expect(await hitTest(page, "sign-in-storage-notice")).toBe(true);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/session-storage-notice-sign-in-1280.png`,
    });

    await page.getByTestId("auth-email").fill(email);
    await page.getByTestId("auth-password").fill(TEST_PASSWORD);
    await page.getByTestId("auth-password").press("Enter");
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByTestId("session-email")).toHaveText(email);

    // After sign-in: the top bar says it, as an alert, in flow under the band.
    const notice = page.getByTestId("session-persist-notice");
    await expect(notice).toBeVisible();
    await expect(
      page
        .getByRole("alert")
        .filter({ hasText: SESSION_NOT_PERSISTED_MESSAGE }),
    ).toHaveCount(1);
    expect(await hitTest(page, "session-persist-notice")).toBe(true);
    const layout = await page.evaluate(() => {
      const bar = document.querySelector('[data-testid="topbar"]');
      const strip = document.querySelector(
        '[data-testid="session-persist-notice"]',
      );
      const next = strip?.nextElementSibling;
      if (!bar || !strip || !next) return null;
      const b = bar.getBoundingClientRect();
      const s = strip.getBoundingClientRect();
      const n = next.getBoundingClientRect();
      // In flow: below the band, and the page content starts below IT, so the
      // strip overlays nothing (a toast or an overlay would fail the second).
      return {
        belowBar: s.top >= b.bottom - 0.5,
        contentBelow: n.top >= s.bottom - 0.5,
      };
    });
    expect(layout).toEqual({ belowBar: true, contentBelow: true });
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/session-storage-notice-topbar-1280.png`,
    });

    // It stays until the user dismisses it: a real click on the control.
    const dismiss = page.getByTestId("session-persist-notice-dismiss");
    const box = await dismiss.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    }
    await expect(notice).toHaveCount(0);
    // Dismissing is not signing out.
    await expect(page.getByTestId("session-email")).toHaveText(email);
  });
});

/** Whether the element's own centre resolves to it (or a child) for a pointer. */
async function hitTest(page: Page, testId: string): Promise<boolean> {
  return page.evaluate((id) => {
    const element = document.querySelector(`[data-testid="${id}"]`);
    if (!element) return false;
    const r = element.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return false;
    const hit = document.elementFromPoint(
      r.left + r.width / 2,
      r.top + r.height / 2,
    );
    return hit !== null && element.contains(hit);
  }, testId);
}
