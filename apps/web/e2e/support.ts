import { expect, type Page } from "@playwright/test";

import { SESSION_STORAGE_KEY } from "../src/auth/session";

export const SCREENSHOT_DIR = "../../docs/screenshots";

/** Meets the gateway's 8–256 char policy; not a secret (test-only). */
export const TEST_PASSWORD = "loft-e2e-passw0rd";

/**
 * A unique throwaway address per call — registrations never collide.
 * example.com because pydantic's email-validator rejects special-use TLDs
 * like `.test` ("reserved name") with a 422.
 */
export function uniqueEmail(): string {
  return `e2e-${Date.now()}-${Math.floor(Math.random() * 1e9)}@example.com`;
}

export interface RegisteredAccount {
  email: string;
  token: string;
  user: unknown;
}

/** Register a fresh account via the real gateway (through the Vite proxy). */
export async function registerViaApi(page: Page): Promise<RegisteredAccount> {
  const email = uniqueEmail();
  const response = await page.request.post("/api/v1/auth/register", {
    data: { email, password: TEST_PASSWORD },
  });
  if (!response.ok()) {
    throw new Error(
      `e2e register failed: ${response.status()} ${await response.text()}`,
    );
  }
  const body = (await response.json()) as {
    access_token: string;
    user: unknown;
  };
  return { email, token: body.access_token, user: body.user };
}

/** Write a session into localStorage before every page load in this page. */
export async function seedStoredSession(
  page: Page,
  token: string,
  user: unknown,
): Promise<void> {
  await page.addInitScript(
    ({ key, value }) => {
      window.localStorage.setItem(key, value);
    },
    { key: SESSION_STORAGE_KEY, value: JSON.stringify({ token, user }) },
  );
}

/**
 * Register + seed the session — the fast path for specs that test the
 * modeler, not the sign-in flow itself.
 */
export async function seedSession(page: Page): Promise<RegisteredAccount> {
  const account = await registerViaApi(page);
  await seedStoredSession(page, account.token, account.user);
  return account;
}

/** Count distinct colors on the WebGL canvas — proves a real render. */
export async function distinctCanvasColors(page: Page): Promise<number> {
  return page.evaluate(() => {
    const canvas = document.querySelector<HTMLCanvasElement>(
      '[data-testid="viewport"] canvas',
    );
    if (!canvas) return 0;
    const probe = document.createElement("canvas");
    probe.width = canvas.width;
    probe.height = canvas.height;
    const ctx = probe.getContext("2d");
    if (!ctx) return 0;
    ctx.drawImage(canvas, 0, 0);
    const { data } = ctx.getImageData(0, 0, probe.width, probe.height);
    const colors = new Set<number>();
    for (let i = 0; i < data.length; i += 64) {
      const r = data[i] ?? 0;
      const g = data[i + 1] ?? 0;
      const b = data[i + 2] ?? 0;
      colors.add((r << 16) | (g << 8) | b);
    }
    return colors.size;
  });
}

/** Wait until the tessellation is applied AND visibly rendered on canvas. */
export async function expectRenderedModel(page: Page): Promise<void> {
  await expect(page.getByTestId("tessellation-status")).toHaveText(
    "Up to date",
    {
      timeout: 30_000,
    },
  );
  // Grid + lit aluminum model produce far more shades than an empty ground.
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 15_000 })
    .toBeGreaterThan(24);
}
