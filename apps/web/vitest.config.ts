/**
 * Two vitest projects, split by FILE EXTENSION so the environment is never a
 * per-file decision someone can forget:
 *
 *   `*.test.ts`  → `unit` — node, no DOM. The pure logic tier (formatters,
 *                  feature math, API envelope handling). Stays node-fast.
 *   `*.test.tsx` → `dom`  — jsdom + Testing Library. The component tier: does
 *                  this component render the VALUE/copy it was handed?
 *
 * Why projects and not a single jsdom config: flipping the whole suite to jsdom
 * would tax ~65 node-only files with a DOM they never touch. Why not a per-file
 * `// @vitest-environment jsdom` docblock: a new `.test.tsx` that forgets it
 * fails with a bare "document is not defined". The extension declares intent.
 *
 * The `dom` project exists because the tier between "pure unit test" and "40
 * minute Playwright run" was empty, and that is exactly where the 2026-07-25
 * UI defects lived (a dead `operation` field, a hardcoded `mm³` label, a
 * docstring promising focus return the code never did).
 */
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    projects: [
      {
        test: {
          name: "unit",
          environment: "node",
          include: ["src/**/*.test.ts"],
        },
      },
      {
        test: {
          name: "dom",
          environment: "jsdom",
          include: ["src/**/*.test.tsx"],
          setupFiles: ["./src/test/domSetup.ts"],
        },
      },
    ],
  },
});
