import { expect, test, type Page } from "./fixtures";

import { SESSION_STORAGE_KEY } from "../src/auth/session";
import { seedCube } from "./partSeed";
import {
  createPartViaApi,
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

  test("a stale/tampered token with a live session is renewed silently, not signed out", async ({
    page,
  }) => {
    // Registering set the HttpOnly refresh cookie in this browser context.
    const { email, token, user } = await registerViaApi(page);
    // Tamper the signature — the gateway answers 401 invalid_token to /me.
    const tampered = `${token}AAAA`;
    await seedStoredSession(page, tampered, user);

    await page.goto("/");
    // The 401 is ridden out: renewed from the cookie, /me resent, still in.
    await expect(page.getByTestId("session-email")).toHaveText(email);
    await expect
      .poll(() =>
        page.evaluate(
          (key) => window.localStorage.getItem(key),
          SESSION_STORAGE_KEY,
        ),
      )
      .not.toContain(tampered);
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByTestId("session-expired-notice")).toHaveCount(0);
  });

  test("a stale/tampered token with NO session left is caught globally: quiet 'session expired' notice, no silent failure", async ({
    page,
    context,
  }) => {
    const { token, user } = await registerViaApi(page);
    await context.clearCookies(); // no refresh cookie: renewal must fail
    const tampered = `${token}AAAA`;
    await seedStoredSession(page, tampered, user);

    await page.goto("/");
    // Global catch: session cleared, routed to sign-in, quiet notice shown.
    await expect(page).toHaveURL(/\/sign-in$/, { timeout: 15_000 });
    await expect(page.getByTestId("session-expired-notice")).toBeVisible();
    await expect(page.getByTestId("session-expired-headline")).toHaveText(
      "Session expired — sign in again.",
    );
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

/**
 * SESSIONS: a session outlives its access token (helical-gear product test,
 * G6). These live here rather than in a file of their own so the e2e shard
 * plan keeps resting on measured durations (a new spec file is an unmeasured
 * guess until someone refreshes scripts/e2e-durations.json).
 *
 * Before: the access token lived 1 h with no refresh, so a Chamfer CREATE at
 * minute ~60 was a 401, the user was thrown to sign-in, 24 edge picks were
 * lost, and signing in again landed on the parts list, not the part.
 *
 * The first two specs need an access token that expires DURING the test, i.e.
 * a stack booted with a short `JWT_TTL_S` (the TTL is config-driven; 20 s was
 * used when this landed). On a default stack they skip and SAY so. The last
 * spec needs no special stack: it revokes the session server-side.
 *
 * Sign-in goes through the UI, not `page.request`: the refresh cookie is
 * `Secure`, which Chromium honours over http://127.0.0.1 but Playwright's own
 * request context does not send over http, so only the browser path carries
 * the cookie the way a user's browser does.
 */

/** Tokens this long-lived make the expiry specs too slow to run here. */
const MAX_TTL_FOR_EXPIRY_SPECS_S = 60;

interface SignedIn {
  email: string;
  token: string;
}

async function signUpThroughUi(page: Page): Promise<SignedIn> {
  const email = uniqueEmail();
  await page.goto("/sign-in");
  await page.getByTestId("auth-mode-register").click();
  await page.getByTestId("auth-email").fill(email);
  await page.getByTestId("auth-password").fill(TEST_PASSWORD);
  await page.getByTestId("auth-password").press("Enter");
  await expect(page).toHaveURL(/\/$/);
  return { email, token: await storedToken(page) };
}

async function storedToken(page: Page): Promise<string> {
  const raw = await page.evaluate(
    (key) => window.localStorage.getItem(key),
    SESSION_STORAGE_KEY,
  );
  const token = raw === null ? null : (JSON.parse(raw) as { token?: unknown });
  if (typeof token?.token !== "string") throw new Error("no stored session");
  return token.token;
}

/** `iat`/`exp` (epoch seconds) read from a JWT's payload — not verified. */
function claims(token: string): { iat: number; exp: number } {
  const payload = token.split(".")[1] ?? "";
  return JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as {
    iat: number;
    exp: number;
  };
}

function ttlOf(token: string): number {
  const { iat, exp } = claims(token);
  return exp - iat;
}

/** Create a 20 mm cube part and open it; resolves with the part id. */
async function openCubePart(page: Page, token: string): Promise<string> {
  const part = await createPartViaApi(page, token, "Session cube");
  await seedCube(page, token, part.id);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("prop-volume")).toContainText("8,000", {
    timeout: 30_000,
  });
  await expect(page.getByTestId("feature-row")).toHaveCount(2);
  return part.id;
}

/** Open Chamfer in pick mode and pick the two top-most edges. */
async function pickTwoChamferEdges(page: Page): Promise<void> {
  await page.getByTestId("new-chamfer").click();
  await expect(page.getByTestId("chamfer-editor")).toBeVisible();
  await page.getByTestId("chamfer-distance").fill("1");
  await page.getByTestId("chamfer-mode-pick").click();
  const nodes = page.locator('[data-testid^="edge-pick-"]');
  await expect(nodes).toHaveCount(12, { timeout: 20_000 });
  const heights: { index: number; z: number }[] = [];
  for (let index = 0; index < 12; index += 1) {
    const label = (await nodes.nth(index).getAttribute("aria-label")) ?? "";
    const nums = label.match(/-?\d+(?:\.\d+)?/g) ?? [];
    heights.push({ index, z: Number.parseFloat(nums[nums.length - 1] ?? "") });
  }
  const top = heights
    .filter((h) => Number.isFinite(h.z))
    .sort((a, b) => b.z - a.z)
    .slice(0, 2);
  for (const { index } of top) await nodes.nth(index).click();
  await expect(page.getByTestId("selected-count")).toHaveText("2 edges picked");
}

/** Every response the app got from the gateway, in order. */
function recordApi(
  page: Page,
): { method: string; path: string; status: number }[] {
  const seen: { method: string; path: string; status: number }[] = [];
  page.on("response", (response) => {
    const url = new URL(response.url());
    if (!url.pathname.startsWith("/api/")) return;
    seen.push({
      method: response.request().method(),
      path: url.pathname,
      status: response.status(),
    });
  });
  return seen;
}

/** Let wall-clock time pass until *token* has expired (plus a margin). */
async function outlive(page: Page, token: string): Promise<void> {
  const remainingMs = claims(token).exp * 1000 - Date.now();
  // Time passing IS the subject here; there is no event to wait on instead.
  await page.waitForTimeout(Math.max(0, remainingMs) + 1_500);
}

test.describe("session refresh (short-TTL stack)", () => {
  test("an access token expiring mid-command: picks survive, CREATE commits", async ({
    page,
  }) => {
    const { token } = await signUpThroughUi(page);
    test.skip(
      ttlOf(token) > MAX_TTL_FOR_EXPIRY_SPECS_S,
      `needs a stack booted with JWT_TTL_S <= ${MAX_TTL_FOR_EXPIRY_SPECS_S}; this one issues ${ttlOf(token)} s tokens`,
    );
    // Setup plus one token lifetime of wall clock, with room to spare.
    test.setTimeout(60_000 + ttlOf(token) * 3_000);
    const partId = await openCubePart(page, token);
    const api = recordApi(page);
    await pickTwoChamferEdges(page);

    // Make the token REALLY expire: the keepalive's early renewal is refused
    // at the network (a closed laptop lid, a dead Wi-Fi), so nothing renews it.
    let blockedRefreshes = 0;
    await page.route("**/api/v1/auth/refresh", async (route) => {
      blockedRefreshes += 1;
      await route.abort("internetdisconnected");
    });
    const held = await storedToken(page);
    await outlive(page, held);
    expect(blockedRefreshes).toBeGreaterThan(0); // the keepalive did try
    const expired = await page.request.get("/api/v1/auth/me", {
      headers: { Authorization: `Bearer ${held}` },
    });
    expect(expired.status()).toBe(401); // truly expired, not merely old
    // A refused renewal is not a sign-out, and the command is still open.
    await expect(page).toHaveURL(new RegExp(`/parts/${partId}$`));
    await expect(page.getByTestId("selected-count")).toHaveText(
      "2 edges picked",
    );

    // The network is back. The CREATE goes out on the dead token, is refused,
    // the session renews from the cookie, and the SAME request is resent.
    await page.unroute("**/api/v1/auth/refresh");
    const committed = page.waitForResponse(
      (r) =>
        r.request().method() === "POST" &&
        r.url().endsWith(`/api/v1/parts/${partId}/features`) &&
        r.status() === 201,
    );
    const mark = api.length;
    await page.getByTestId("chamfer-submit").click();
    const created = await committed;

    await expect(page.getByTestId("feature-row")).toHaveCount(3);
    await expect(page.getByTestId("feature-row").nth(2)).toContainText(
      "chamfer",
    );
    await expect(page).toHaveURL(new RegExp(`/parts/${partId}$`));
    await expect(page.getByTestId("session-expired-notice")).toHaveCount(0);

    // The picks travelled with the retried command: the stored chamfer names
    // exactly the two picked edges. Read back from the server with the NEW
    // token (the resent request's stream body is invisible to Playwright).
    expect(created.status()).toBe(201);
    const fresh = await storedToken(page);
    const tree = await page.request.get(`/api/v1/parts/${partId}/features`, {
      headers: { Authorization: `Bearer ${fresh}` },
    });
    expect(tree.status()).toBe(200);
    const { features } = (await tree.json()) as {
      features: {
        feature: {
          type: string;
          params: { edges: { kind: string; refs?: [] } };
        };
      }[];
    };
    const chamfers = features.filter((f) => f.feature.type === "chamfer");
    expect(chamfers).toHaveLength(1); // committed once, not twice
    expect(chamfers[0]?.feature.params.edges.kind).toBe("edges");
    expect(chamfers[0]?.feature.params.edges.refs).toHaveLength(2);

    // The wire: refused on the old token, renewed, resent, created.
    const wire = api
      .slice(mark)
      .map((r) => `${r.method} ${r.path.split("/").pop()} ${r.status}`);
    const refused = wire.indexOf("POST features 401");
    const accepted = wire.indexOf("POST features 201");
    expect(refused, wire.join("\n")).toBeGreaterThanOrEqual(0);
    expect(accepted, wire.join("\n")).toBeGreaterThan(refused);
    const gap = wire.slice(refused + 1, accepted);
    expect(gap, wire.join("\n")).toContain("POST refresh 200");
    // …and the resend was the TRANSPORT's, invisible to the command: the page
    // has its own catch-all "re-read the tree, send again" path, and a tree
    // read inside the gap would mean the refusal reached it. (Seen: with the
    // transport retry removed, the gap is `refresh, me, GET features`.)
    expect(
      gap.filter((r) => r.startsWith("GET features")),
      wire.join("\n"),
    ).toEqual([]);
    expect(wire.filter((r) => r.startsWith("POST features"))).toEqual([
      "POST features 401",
      "POST features 201",
    ]);
    expect(await storedToken(page)).not.toBe(held);
  });

  test("the keepalive renews ahead of expiry: no 401 at all across several token lifetimes", async ({
    page,
  }) => {
    const { token } = await signUpThroughUi(page);
    const ttl = ttlOf(token);
    test.skip(
      ttl > MAX_TTL_FOR_EXPIRY_SPECS_S,
      `needs a stack booted with JWT_TTL_S <= ${MAX_TTL_FOR_EXPIRY_SPECS_S}; this one issues ${ttl} s tokens`,
    );
    // Setup plus 2.5 token lifetimes of wall clock, with room to spare.
    test.setTimeout(60_000 + ttl * 4_000);
    const partId = await openCubePart(page, token);
    const api = recordApi(page);
    await pickTwoChamferEdges(page);
    const held = await storedToken(page);

    // Idle mid-command for 2.5 lifetimes of the token.
    await page.waitForTimeout(ttl * 2_500);

    const renewals = api.filter(
      (r) => r.path === "/api/v1/auth/refresh" && r.status === 200,
    );
    expect(renewals.length).toBeGreaterThanOrEqual(2);
    expect(await storedToken(page)).not.toBe(held);
    await expect(page.getByTestId("selected-count")).toHaveText(
      "2 edges picked",
    );

    await page.getByTestId("chamfer-submit").click();
    await expect(page.getByTestId("feature-row")).toHaveCount(3);
    await expect(page).toHaveURL(new RegExp(`/parts/${partId}$`));
    // Renewal happened AHEAD of expiry: nothing the app sent was refused.
    expect(api.filter((r) => r.status === 401)).toEqual([]);
  });
});

/**
 * Sign-in brought the user back to the cube part, not the parts list, and the
 * part is really there. ONE assertion for every route back to a page:
 * an expiry mid-session and a first signed-out visit (DEEPLINK-SIGNIN-RETURN-1).
 */
async function expectBackOnCubePart(page: Page, partId: string): Promise<void> {
  await expect(page).toHaveURL(new RegExp(`/parts/${partId}$`));
  await expect(page.getByTestId("feature-row")).toHaveCount(2, {
    timeout: 30_000,
  });
  await expect(page.getByTestId("prop-volume")).toContainText("8,000", {
    timeout: 30_000,
  });
}

test.describe("session refresh (any stack)", () => {
  test("a first visit to a part while signed out: sign-in lands on the part", async ({
    page,
  }) => {
    const { email, token } = await registerViaApi(page);
    const part = await createPartViaApi(page, token, "Deep-linked cube");
    await seedCube(page, token, part.id);

    // No session in this browser: the link goes to sign-in first...
    await page.goto(`/parts/${part.id}`);
    await expect(page).toHaveURL(/\/sign-in$/);
    // ...quietly: nothing expired, there was never a session here.
    await expect(page.getByTestId("session-expired-notice")).toHaveCount(0);

    await page.getByTestId("auth-email").fill(email);
    await page.getByTestId("auth-password").fill(TEST_PASSWORD);
    await page.getByTestId("auth-password").press("Enter");

    await expectBackOnCubePart(page, part.id);
  });

  test("when renewal truly fails: sign-in says so, then returns to the part", async ({
    page,
  }) => {
    const { email, token } = await signUpThroughUi(page);
    const partId = await openCubePart(page, token);

    // End the session server-side, as a sign-out on another device would:
    // the access token AND the refresh cookie stop working together.
    const revoked = await page.request.post("/api/v1/auth/logout", {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(revoked.status()).toBe(204);

    // Mid-command: the CREATE is refused, the renewal is refused, and only
    // now does the app give up on the session.
    await page.getByTestId("new-chamfer").click();
    await expect(page.getByTestId("chamfer-editor")).toBeVisible();
    await page.getByTestId("chamfer-distance").fill("1");
    await page.getByTestId("chamfer-distance").press("Enter");

    await expect(page).toHaveURL(/\/sign-in$/, { timeout: 15_000 });
    await expect(page.getByTestId("session-expired-headline")).toHaveText(
      "Session expired — sign in again.",
    );
    await expect(page.getByTestId("session-expired-return")).toContainText(
      "You will go back to the page you were on.",
    );

    await page.getByTestId("auth-email").fill(email);
    await page.getByTestId("auth-password").fill(TEST_PASSWORD);
    await page.getByTestId("auth-password").press("Enter");

    await expectBackOnCubePart(page, partId);

    // The return path is used once: a later deliberate sign-out and sign-in
    // lands on the parts home as it always did.
    await page.getByTestId("sign-out").click();
    await expect(page).toHaveURL(/\/sign-in$/);
    await expect(page.getByTestId("session-expired-notice")).toHaveCount(0);
    await page.getByTestId("auth-email").fill(email);
    await page.getByTestId("auth-password").fill(TEST_PASSWORD);
    await page.getByTestId("auth-password").press("Enter");
    await expect(page).toHaveURL(/\/$/);
  });

  test("a shared browser: X's old tab is never renewed into Y's sign-in", async ({
    page,
    context,
  }) => {
    // Tab A: X signs in, and X's parts list is in tab A's query cache.
    const x = await signUpThroughUi(page);
    const xPart = `X private part ${Date.now()}`;
    await createPartViaApi(page, x.token, xPart);
    await page.goto("/");
    await expect(
      page.getByTestId("part-open").filter({ hasText: xPart }),
    ).toBeVisible();

    // Tab B, same browser: X signs out there (ending X's session), and Y
    // signs in, so the one cookie jar now holds Y's refresh cookie.
    const tabB = await context.newPage();
    await tabB.goto("/");
    await expect(tabB.getByTestId("session-email")).toHaveText(x.email);
    await tabB.getByTestId("sign-out").click();
    await expect(tabB).toHaveURL(/\/sign-in$/);
    const yEmail = uniqueEmail();
    await tabB.getByTestId("auth-mode-register").click();
    await tabB.getByTestId("auth-email").fill(yEmail);
    await tabB.getByTestId("auth-password").fill(TEST_PASSWORD);
    await tabB.getByTestId("auth-password").press("Enter");
    await expect(tabB.getByTestId("session-email")).toHaveText(yEmail);

    // Tab A still shows X. Its next request is refused (X's session ended);
    // renewing with Y's cookie must NOT make tab A Y.
    await page.bringToFront();
    await page.getByTestId("nav-assemblies").click();
    await expect(page).toHaveURL(/\/sign-in$/, { timeout: 15_000 });
    await expect(page.getByTestId("session-expired-headline")).toBeVisible();
    await expect(page.getByTestId("session-email")).toHaveCount(0);

    // And Y is untouched: still signed in, across a reload.
    await tabB.reload();
    await expect(tabB.getByTestId("session-email")).toHaveText(yEmail);

    // Y now signs in in tab A. Nothing X's session cached is shown to Y
    // (QUERY-CACHE-USER-SWITCH-1). Y's parts list is HELD in flight, so a
    // cached copy, which would render at once (30 s staleTime), has the stage.
    let release = () => {};
    const held = new Promise<void>((resolve) => (release = resolve));
    await page.route("**/api/v1/parts", async (route) => {
      if (route.request().method() === "GET") await held;
      await route.continue();
    });
    const listed = page.waitForResponse(
      (r) =>
        new URL(r.url()).pathname === "/api/v1/parts" &&
        r.request().method() === "GET",
    );
    await page.getByTestId("auth-email").fill(yEmail);
    await page.getByTestId("auth-password").fill(TEST_PASSWORD);
    await page.getByTestId("auth-password").press("Enter");
    await expect(page.getByTestId("session-email")).toHaveText(yEmail);
    await expect(page.getByText(xPart)).toHaveCount(0);
    release();
    expect((await listed).status()).toBe(200);
    await expect(page.getByText(xPart)).toHaveCount(0);
  });
});
