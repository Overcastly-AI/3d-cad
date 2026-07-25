/**
 * Shared setup for the `dom` vitest project (every `*.test.tsx`): jest-dom
 * matchers, automatic Testing Library unmount between cases, and the handful of
 * browser APIs jsdom does not implement that our chrome reads at render time.
 *
 * Keeping this here means a component test file is just `render(...)` +
 * assertions — no per-file boilerplate to copy (the DRY rule applied to the
 * harness itself).
 */
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(cleanup);

// jsdom ships no `matchMedia`; components that honour `prefers-reduced-motion`
// call it during render. Answer "no preference" for every query — the reduced
// motion path itself is exercised by the Playwright specs, which can actually
// emulate the media feature.
if (typeof window !== "undefined" && window.matchMedia === undefined) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: () => false,
    // jsdom has no layout engine, so a partial MediaQueryList is all any
    // component can meaningfully consume here.
  })) as unknown as typeof window.matchMedia;
}
