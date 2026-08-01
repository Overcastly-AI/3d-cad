import { copyFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";

import { expect, type Page } from "@playwright/test";

import { SESSION_STORAGE_KEY } from "../src/auth/session";

export const SCREENSHOT_DIR = "../../docs/screenshots";

/**
 * Copy a produced artifact (a PDF, a DXF — anything that is NOT a
 * `page.screenshot`) into the committed `docs/screenshots/` set, but ONLY on a
 * deliberate refresh.
 *
 * `fixtures.ts` gates `page.screenshot` so a routine `just e2e` never rewrites
 * the committed PNGs. That gate wraps ONE method, so these `copyFile` writes
 * sailed straight past it and every run rewrote `drawing-export.{pdf,dxf}` —
 * the exact churn the PNG gate exists to prevent, at a second address. Found
 * 2026-07-31 when a clean-window e2e left two files dirty; the committed pair
 * turned out to be 13 days stale, so nobody had noticed either half.
 *
 * Refresh deliberately with `UPDATE_SCREENSHOTS=1`, the same switch the PNGs use
 * — one env var for the whole committed set, not two conventions.
 */
export async function persistArtifact(from: string, to: string): Promise<void> {
  if (!process.env.UPDATE_SCREENSHOTS) return;
  await mkdir(dirname(to), { recursive: true });
  await copyFile(from, to);
}

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

/**
 * Both History buttons settled at the given server gates (`can_undo` /
 * `can_redo` → aria-disabled). Shared by the part and assembly undo/redo
 * specs — the two workspaces render the SAME HistoryGroup, so the assertion
 * is identical.
 */
export async function expectHistoryGates(
  page: Page,
  gates: { undo: boolean; redo: boolean },
): Promise<void> {
  const undo = page.getByTestId("undo-button");
  const redo = page.getByTestId("redo-button");
  await (gates.undo ? expect(undo).toBeEnabled() : expect(undo).toBeDisabled());
  await (gates.redo ? expect(redo).toBeEnabled() : expect(redo).toBeDisabled());
}

/**
 * A fixed, fixed-length display email substituted into the header ONLY while a
 * founder screenshot is captured (see `fixtures.ts`). The registration email is
 * still per-run unique for DB isolation; this just stabilises the pixels so
 * `just e2e` stops re-writing ~90 PNGs every run. Fixed length matters: the
 * `session-email` span lives in the right-aligned header cluster, so a variable
 * email width also reflows its neighbours — a constant string freezes the whole
 * cluster, which masking the email box alone would not.
 */
export const SCREENSHOT_SESSION_EMAIL = "engineer@example.com";

/**
 * Swap the header's session email for `SCREENSHOT_SESSION_EMAIL`, run `capture`,
 * then restore the real text. Restoring keeps functional assertions that read
 * the real email (auth/full-flow) correct — only the screenshot frame differs.
 */
export async function withStableSessionEmail<T>(
  page: Page,
  capture: () => Promise<T>,
): Promise<T> {
  const previous = await page.evaluate((stable) => {
    const el = document.querySelector<HTMLElement>(
      '[data-testid="session-email"]',
    );
    if (!el) return null;
    const prior = el.textContent;
    el.textContent = stable;
    return prior;
  }, SCREENSHOT_SESSION_EMAIL);
  try {
    return await capture();
  } finally {
    if (previous !== null) {
      await page.evaluate((prior) => {
        const el = document.querySelector<HTMLElement>(
          '[data-testid="session-email"]',
        );
        if (el) el.textContent = prior;
      }, previous);
    }
  }
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

/** Create a part via the real gateway, authorized as `token`'s account. */
export async function createPartViaApi(
  page: Page,
  token: string,
  name: string,
): Promise<{ id: string; name: string }> {
  const response = await page.request.post("/api/v1/parts", {
    data: { name },
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) {
    throw new Error(
      `e2e create part failed: ${response.status()} ${await response.text()}`,
    );
  }
  return (await response.json()) as { id: string; name: string };
}

/**
 * Count SKETCH INK on the canvas — pixels on the live or solved scribe tokens.
 *
 * REWRITTEN 2026-08-01, because the previous version was actively misleading
 * and would have blessed a broken product. It matched "bright and blue-leaning"
 * (`r > 120 && b > 140 && b >= r && g >= r`), which is also a perfect
 * description of MACHINED ALUMINUM under the studio matcap. Measured by the QA
 * pass on the sketch-on-a-face case: it returned **926 729** where a sketch on
 * a bare datum plane returned **1 881** — its number went up ~500x at exactly
 * the moment the sketch stopped being usable, because the body's face is the
 * thing it was counting. `part-visibility.spec.ts` had already worked around it
 * with a local exact-hex probe; this makes the shared helper honest instead.
 *
 * It now counts the two scribe tokens exactly (`sketch.scribe` for the sketch
 * being drawn, `sketch.scribeSolved` for a persisted one). Sketch materials
 * render un-tonemapped, so a token lands on the canvas at its literal hex and
 * nothing shaded can be mistaken for it.
 */
export async function countSketchInkPixels(page: Page): Promise<number> {
  const live = await countTokenPixels(page, "#E9F1F8");
  const solved = await countTokenPixels(page, "#C4D2DE");
  return live + solved;
}

/** A CSS-pixel rectangle of the viewport canvas to restrict a census to. */
export interface CanvasBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * Count canvas pixels that land on a design-token hex (± `tolerance` per
 * channel), optionally inside `box` (canvas coordinates).
 *
 * The primitive `countSketchInkPixels` above is built on, and the reason it
 * works: sketch, datum and measure materials all render un-tonemapped through
 * line materials, so a token lands on the canvas at its literal hex and a tight
 * match cannot be confused with a shaded surface. Anything looser — "bright and
 * blue-leaning", say — describes machined aluminum just as well as ink.
 *
 * Extracted on the third copy of the same twelve lines (`part-visibility`'s two
 * probes and the sketch-on-a-face visibility gate) — CLAUDE.md DRY rule.
 */
export async function countTokenPixels(
  page: Page,
  hex: string,
  tolerance = 6,
  box?: CanvasBox,
): Promise<number> {
  return page.evaluate(
    ({ hex, tolerance, box }) => {
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
      const rect = box ?? {
        x: 0,
        y: 0,
        width: probe.width,
        height: probe.height,
      };
      if (rect.width <= 0 || rect.height <= 0) return 0;
      const { data } = ctx.getImageData(
        rect.x,
        rect.y,
        rect.width,
        rect.height,
      );
      const value = Number.parseInt(hex.slice(1), 16);
      const target = [(value >> 16) & 255, (value >> 8) & 255, value & 255];
      let count = 0;
      for (let i = 0; i < data.length; i += 4) {
        if (
          Math.abs((data[i] ?? 0) - (target[0] as number)) <= tolerance &&
          Math.abs((data[i + 1] ?? 0) - (target[1] as number)) <= tolerance &&
          Math.abs((data[i + 2] ?? 0) - (target[2] as number)) <= tolerance
        ) {
          count += 1;
        }
      }
      return count;
    },
    { hex, tolerance, box },
  );
}

/**
 * Count canvas pixels brighter than `minLuminance` (WCAG relative-luminance
 * weights on the raw sRGB bytes — the same banding `part-visibility` uses to
 * tell a lit body from a ghosted one), optionally inside `box`.
 *
 * Used to assert the OPPOSITE of ink: that a lit machined-aluminum face has
 * been covered by the sketcher's layout bluing, so the scribe has a ground to
 * read against.
 */
export async function countLitPixels(
  page: Page,
  minLuminance: number,
  box?: CanvasBox,
): Promise<number> {
  return page.evaluate(
    ({ minLuminance, box }) => {
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
      const rect = box ?? {
        x: 0,
        y: 0,
        width: probe.width,
        height: probe.height,
      };
      if (rect.width <= 0 || rect.height <= 0) return 0;
      const { data } = ctx.getImageData(
        rect.x,
        rect.y,
        rect.width,
        rect.height,
      );
      let count = 0;
      for (let i = 0; i < data.length; i += 4) {
        const lum =
          0.2126 * (data[i] ?? 0) +
          0.7152 * (data[i + 1] ?? 0) +
          0.0722 * (data[i + 2] ?? 0);
        if (lum > minLuminance) count += 1;
      }
      return count;
    },
    { minLuminance, box },
  );
}

/**
 * Wait for the page to actually PAINT `frames` times before sampling the
 * drawing buffer — the render loop's own clock, not the wall clock.
 *
 * The specs that census canvas pixels assert on NUMBERS, and a numeric
 * `expect` does not auto-retry the way a locator assertion does (GATE-1a), so
 * whatever they wait on has to be right first time. `waitForTimeout(400)` is
 * the wrong quantity for that job: under CPU contention — four agents, or a CI
 * shard — 400 ms of wall clock can pass with no rendering opportunity at all,
 * which is precisely the load where the sample is taken early. `rAF` callbacks
 * fire on rendering opportunities, so counting them waits for the work rather
 * than for time, and returns as soon as it has happened.
 *
 * The timeout race is a safety valve, not the mechanism: a page that somehow
 * stops painting resolves late instead of hanging until the test timeout.
 */
export async function waitForFrames(page: Page, frames = 4): Promise<void> {
  await page.evaluate(async (count: number) => {
    await Promise.race([
      (async () => {
        for (let i = 0; i < count; i += 1) {
          await new Promise((resolve) => requestAnimationFrame(resolve));
        }
      })(),
      new Promise((resolve) => setTimeout(resolve, 2000)),
    ]);
  }, frames);
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
