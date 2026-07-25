/**
 * Same two-project split as `apps/web` (one harness pattern across the two TS
 * packages): `*.test.ts` runs in node, `*.test.tsx` runs in jsdom with Testing
 * Library wired up by {@link ./src/test/domSetup}. The environment follows the
 * file extension, so a new primitive test cannot forget to opt in.
 *
 * The existing `// @vitest-environment jsdom` docblocks in the primitive tests
 * are now redundant but harmless; they stay as documentation of intent.
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
