import { expect, test } from "./fixtures";

import { SESSION_STORAGE_KEY } from "../src/auth/session";
import {
  registerViaApi,
  SCREENSHOT_DIR,
  seedStoredSession,
  TEST_PASSWORD,
  uniqueEmail,
} from "./support";

test.describe("auth v1 — sign-in sheet", () => {
  test("register → land in the modeler → refresh keeps session → sign out → sign back in", async ({
    page,
  }) => {
    const email = uniqueEmail();

    // Unauthenticated: the modeler route routes to the sign-in sheet.
    await page.goto("/");
    await expect(page).toHaveURL(/\/sign-in$/);
    await expect(page.getByTestId("auth-panel")).toBeVisible();
    // Founder shot: the un-issued sheet, desktop width.
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/auth-sign-in-desktop.png`,
    });

    // Keyboard-first registration: the email cell is focused on load.
    await expect(page.getByTestId("auth-email")).toBeFocused();
    await page.getByTestId("auth-mode-register").click();
    await expect(page.getByTestId("auth-mode-register")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.getByTestId("auth-email").fill(email);
    await page.keyboard.press("Tab");
    await expect(page.getByTestId("auth-password")).toBeFocused();
    await page.getByTestId("auth-password").fill(TEST_PASSWORD);
    await page.keyboard.press("Enter");

    // Landed on the parts home: a fresh account's register is empty and
    // invites the first part (not the box demo — that moved to /first-light).
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByTestId("session-email")).toHaveText(email);
    await expect(page.getByTestId("parts-register")).toBeVisible();
    await expect(page.getByTestId("parts-empty")).toBeVisible();

    // Refresh keeps the session (localStorage persistence).
    await page.reload();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByTestId("session-email")).toHaveText(email);
    await expect(page.getByTestId("parts-register")).toBeVisible();

    // Sign out: back to the sheet, session gone (no expired notice — this
    // was deliberate), and a reload stays signed out.
    await page.getByTestId("sign-out").click();
    await expect(page).toHaveURL(/\/sign-in$/);
    await expect(page.getByTestId("session-expired-notice")).toHaveCount(0);
    expect(
      await page.evaluate(
        (key) => window.localStorage.getItem(key),
        SESSION_STORAGE_KEY,
      ),
    ).toBeNull();
    await page.reload();
    await expect(page).toHaveURL(/\/sign-in$/);

    // Sign back in with the same credentials (default mode is Sign in).
    await page.getByTestId("auth-email").fill(email);
    await page.getByTestId("auth-password").fill(TEST_PASSWORD);
    await page.getByTestId("auth-password").press("Enter");
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByTestId("session-email")).toHaveText(email);
  });

  test("wrong password surfaces the gateway's uniform message", async ({
    page,
  }) => {
    const { email } = await registerViaApi(page); // account exists; storage stays clean
    await page.goto("/sign-in");

    await page.getByTestId("auth-email").fill(email);
    await page.getByTestId("auth-password").fill("wrong-password-123");
    await page.getByTestId("auth-password").press("Enter");
    await expect(page.getByTestId("auth-error")).toHaveText(
      "Invalid email or password.",
    );
    await expect(page).toHaveURL(/\/sign-in$/);
  });

  test("registering an existing email surfaces the 409 message", async ({
    page,
  }) => {
    const { email } = await registerViaApi(page);
    await page.goto("/sign-in");

    await page.getByTestId("auth-mode-register").click();
    await page.getByTestId("auth-email").fill(email);
    await page.getByTestId("auth-password").fill(TEST_PASSWORD);
    await page.getByTestId("auth-submit").click();
    await expect(page.getByTestId("auth-error")).toHaveText(
      "An account with this email already exists.",
    );
  });

  test("a stale/tampered token is caught globally: quiet 'session expired' notice, no silent failure", async ({
    page,
  }) => {
    const { token, user } = await registerViaApi(page);
    // Tamper the signature — the gateway answers 401 invalid_token to /me.
    const tampered = `${token}AAAA`;
    await seedStoredSession(page, tampered, user);

    await page.goto("/");
    // Global catch: session cleared, routed to sign-in, quiet notice shown.
    await expect(page).toHaveURL(/\/sign-in$/, { timeout: 15_000 });
    const notice = page.getByTestId("session-expired-notice");
    await expect(notice).toBeVisible();
    await expect(notice).toHaveText("Session expired — sign in again.");
    expect(
      await page.evaluate(
        (key) => window.localStorage.getItem(key),
        SESSION_STORAGE_KEY,
      ),
    ).toBeNull();
  });

  test("client-side field errors are specific and visible", async ({
    page,
  }) => {
    await page.goto("/sign-in");
    await page.getByTestId("auth-email").fill("not-an-email");
    await page.getByTestId("auth-submit").click();
    await expect(page.getByRole("alert").first()).toHaveText(
      "Enter a valid email address.",
    );
    await expect(page.getByRole("alert").nth(1)).toHaveText(
      "Enter your password.",
    );
  });
});

test.describe("small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("sign-in sheet holds at 1280×800 (founder shot)", async ({ page }) => {
    await page.goto("/sign-in");
    await expect(page.getByTestId("auth-panel")).toBeVisible();
    await expect(page.getByTestId("auth-email")).toBeFocused();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/auth-sign-in-laptop.png`,
    });
  });
});
