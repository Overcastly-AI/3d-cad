import { test as base, expect } from "@playwright/test";
import type { Page } from "@playwright/test";

import { attachViewportDiagnostics } from "./diagnostics";
import { withStableSessionEmail } from "./support";

/** Committed founder screenshots live here (see support.SCREENSHOT_DIR). */
const FOUNDER_SHOT_DIR = "docs/screenshots/";

/**
 * Founder screenshots are a COMMITTED artifact, refreshed deliberately — never
 * a per-run output. Set this to persist them; unset (the default for routine
 * `just e2e`) captures the frame but skips the file write, so a batch-end e2e
 * never rewrites the PNGs and never dirties the tree.
 *
 * Why gate writes instead of relying on byte-determinism alone: Chromium's
 * screenshot pixels are not byte-identical across a long run even with software
 * GL — sub-pixel raster/camera state flips a handful of AA pixels (and, over a
 * dense sketch grid, thousands) purely from browser-process state. The content
 * fixes below (email, reduced-motion, animations, fonts) kill the *deterministic*
 * churn and keep a deliberate refresh's diff minimal; this gate kills the rest.
 */
const shouldPersist = Boolean(process.env.UPDATE_SCREENSHOTS);

function targetsFounderShot(path: unknown): boolean {
  return typeof path === "string" && path.includes(FOUNDER_SHOT_DIR);
}

/**
 * The shared e2e `test`. It overrides the `page` fixture so that every
 * `page.screenshot(...)`:
 *
 *  1. Normalises the volatile header session email to a fixed value for the
 *     duration of the capture, then restores it (functional assertions that read
 *     the real email are unaffected — it is restored the instant the frame is
 *     taken).
 *  2. Defaults `animations: "disabled"` + `caret: "hide"` so CSS animations/
 *     transitions (e.g. the active-tool toolbar state) and the caret are frozen
 *     at capture rather than sampled at a random phase. Callers may override.
 *  3. Waits for web fonts before the frame, so a fallback→self-hosted swap never
 *     races the capture and re-rasterises glyph edges.
 *  4. Drops the `path` for committed founder shots unless UPDATE_SCREENSHOTS is
 *     set, so routine runs capture (still exercising the render) but do not
 *     overwrite the committed PNGs. This gate — not byte-determinism — is what
 *     guarantees a routine `just e2e` leaves the tree clean.
 *
 * Centralising here (rather than at ~90 call sites) is one seam that also covers
 * future screenshots. Specs import `test`/`expect` from this module.
 *
 * The same seam attaches the VIEWPORT SUBSTRATE state when a test ends
 * non-passing (CI-4). A failed pixel census reports one number and destroys the
 * context that would explain it, which is how four consecutive CI reds were
 * each settled by argument rather than evidence; `diagnostics.ts` documents
 * exactly which reading separates which cause.
 */
export const test = base.extend({
  page: async ({ page }, use, testInfo) => {
    const original = page.screenshot.bind(page);
    // Preserve Playwright's overload signature; the wrapper interposes the
    // header-normalisation + stable-capture defaults + write-gate.
    page.screenshot = ((options?: Parameters<Page["screenshot"]>[0]) =>
      withStableSessionEmail(page, async () => {
        await page.evaluate(() => document.fonts.ready);
        const gated =
          !shouldPersist && targetsFounderShot(options?.path)
            ? { ...options, path: undefined }
            : options;
        return original({ animations: "disabled", caret: "hide", ...gated });
      })) as Page["screenshot"];
    await use(page);
    if (testInfo.status !== testInfo.expectedStatus) {
      await attachViewportDiagnostics(page, testInfo);
    }
  },
});

export { expect };
export type { Page } from "@playwright/test";
