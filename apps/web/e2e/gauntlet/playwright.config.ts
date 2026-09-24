import { defineConfig } from "@playwright/test";

import base from "../../playwright.config";

/**
 * The gauntlet's browser leg (`face-pick.gauntlet.ts`) — NOT part of the
 * sharded suite, which collects only `*.spec.ts` from `e2e/`. See the spec's
 * docblock for why, and for how to run it against a live stack. No
 * `webServer`: it measures whatever stack `GAUNTLET_WEB_ORIGIN` points at, so
 * it can be aimed at a dev server or a built bundle alike.
 */
export default defineConfig({
  ...base,
  testDir: ".",
  testMatch: /\.gauntlet\.ts$/,
  webServer: undefined,
  retries: 0,
  use: {
    ...base.use,
    baseURL: process.env["GAUNTLET_WEB_ORIGIN"] ?? "http://127.0.0.1:5173",
    // The gauntlet's resolution (docs/GEOMETRY-QA.md, browser leg).
    viewport: { width: 1280, height: 800 },
    // A trace of a 10 MB mesh session is itself a load on the thing measured.
    trace: "off",
  },
});
