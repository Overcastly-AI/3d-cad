/**
 * Shared setup for the design system's `dom` vitest project (every
 * `*.test.tsx`): jest-dom matchers and automatic unmount between cases, so a
 * primitive test is just `render(...)` + assertions.
 *
 * Mirrors `apps/web/src/test/domSetup.ts` — one harness pattern for both TS
 * packages.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(cleanup);
