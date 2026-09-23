import { defineConfig } from "@playwright/test";

/**
 * THE BUILT-BUNDLE LEG — Playwright against `vite build` output, served by the
 * REAL production nginx config.
 *
 * Every other spec in this repo drives the Vite DEV server. That leaves two
 * things untested that only ship to users:
 *
 *  1. THE CONTENT-SECURITY-POLICY. `deploy/docker/web/nginx.conf` emits one;
 *     the dev server emits nothing of the kind. A CSP that blocks a worker, a
 *     blob: URL or an inlined font is a TOTAL failure that ships green — the
 *     page still renders, so every status-code probe and every "did the app
 *     mount" assertion agrees it is fine. Measured on this leg's first run: the
 *     policy the config's own comment proposed (`font-src 'self'`) produced
 *     EIGHT font-src violations, because Vite inlines eight @fontsource faces
 *     into the CSS as `data:font/woff` URLs.
 *  2. THE BUNDLE ITSELF. Rollup's module graph is not Vite's dev graph — most
 *     sharply for `three@0.185.1`, which ships a dual ESM/CJS build, so
 *     `instanceof PerspectiveCamera` is false for a real camera whenever two
 *     module records of the same package end up in one graph. That is already
 *     measured TRUE under vitest. Nothing could say what the shipped bundle
 *     does until something loaded it.
 *
 * The stack behind it is the same native boot `scripts/e2e.sh` uses, so this
 * config assumes the server is ALREADY UP and deliberately declares no
 * `webServer`: `scripts/dist-leg.sh` owns nginx's lifecycle (it builds the
 * bundle, renders the config, starts nginx, probes BOTH loopback families and
 * kills it from a pid file). Playwright starting it would hide the probe, and
 * the probe is the thing that makes a dual-stack CI runner diagnosable.
 */
const origin = process.env["DIST_WEB_ORIGIN"] ?? "http://127.0.0.1:5290";

export default defineConfig({
  testDir: "./e2e-dist",
  // Its own directory, not `e2e/`: `playwright.config.ts` globs everything in
  // there into the sharded dev-server suite, where these specs would run
  // against :5173 and assert production properties of a dev bundle.
  fullyParallel: false,
  workers: 1,
  timeout: 120_000,
  // No retries. This leg exists to answer questions about the artefact; a
  // retry turns "the bundle violates its own CSP intermittently" into a pass.
  retries: 0,
  use: {
    baseURL: origin,
    viewport: { width: 1600, height: 1000 },
    deviceScaleFactor: 1,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    launchOptions: {
      args: [
        "--disable-gpu",
        "--force-color-profile=srgb",
        "--font-render-hinting=none",
        "--disable-lcd-text",
        "--disable-skia-runtime-opts",
      ],
    },
  },
});
