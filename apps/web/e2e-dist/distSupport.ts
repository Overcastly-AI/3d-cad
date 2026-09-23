import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { createPlateWithHoleViaApi } from "../e2e/assemblyFlow";
import { expect, type Page } from "../e2e/fixtures";
import { distinctCanvasColors, seedSession } from "../e2e/support";

/**
 * Plumbing shared by the built-bundle leg. See `playwright.dist.config.ts` for
 * why this leg exists at all.
 */

/** One `securitypolicyviolation` event, as the page saw it. */
export interface CspViolation {
  directive: string;
  blockedURI: string;
  sourceFile: string;
  lineNumber: number;
  sample: string;
}

interface CspWindow extends Window {
  __loftCspViolations?: CspViolation[];
}

/**
 * THE POLICY, WRITTEN DOWN ONCE, HERE.
 *
 * Duplicated from `deploy/docker/web/nginx.conf` on purpose and with eyes open:
 * an assertion that reads the value out of the thing under test can only ever
 * prove it equals itself. The nginx config is the source of truth for what is
 * SERVED; this constant is the source of truth for what we INTEND, and the
 * whole point of the comparison is that the two can disagree. `just lint` has
 * no way to diff them, so a change to one that forgets the other reddens this
 * leg — which is the correct place for it to redden, because a policy change
 * is exactly the change that needs a browser to sign it off.
 */
export const EXPECTED_CSP =
  "default-src 'self' data: blob:; script-src 'self' 'wasm-unsafe-eval' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'";

/** How many directives the policy above declares. A COUNT GUARD: a policy that
 * silently lost half its directives would still be a plausible string, and
 * `toBe(EXPECTED_CSP)` alone cannot tell a deliberate rewrite from a truncation
 * — this number has to be re-derived by a human when it changes. */
export const EXPECTED_CSP_DIRECTIVES = 11;

/**
 * Arm the violation recorder BEFORE any page script runs.
 *
 * `addInitScript` runs at document-start on every navigation, so it is attached
 * before the parser reaches the stylesheet link or the module script — which
 * matters, because a listener installed after `load` cannot see the violations
 * that a blocked stylesheet or font produced on the way there. That ordering is
 * the difference between "zero violations" meaning something and meaning
 * nothing.
 */
export async function armCspRecorder(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const w = window as CspWindow;
    const seen: CspViolation[] = [];
    w.__loftCspViolations = seen;
    document.addEventListener("securitypolicyviolation", (event) => {
      seen.push({
        directive: event.effectiveDirective || event.violatedDirective,
        blockedURI: event.blockedURI,
        sourceFile: event.sourceFile,
        lineNumber: event.lineNumber,
        sample: event.sample,
      });
    });
  });
}

/** Everything the recorder has collected on the CURRENT document. */
export async function readCspViolations(page: Page): Promise<CspViolation[]> {
  return page.evaluate(() => {
    const w = window as CspWindow;
    return w.__loftCspViolations ?? [];
  });
}

/** A violation rendered for a failure message — the blocked URI is the answer. */
export function describeViolations(violations: CspViolation[]): string {
  if (violations.length === 0) return "(none)";
  return violations
    .map(
      (v, i) =>
        `  ${i + 1}. ${v.directive} blocked ${v.blockedURI || "(inline)"}` +
        (v.sourceFile ? ` from ${v.sourceFile}:${v.lineNumber}` : "") +
        (v.sample ? ` sample=${JSON.stringify(v.sample)}` : ""),
    )
    .join("\n");
}

/**
 * Chromium's own console report of the SAME events — a second, independently
 * derived count.
 *
 * The recorder above is a DOM listener; this is the renderer's log. They are
 * produced by different code paths, so when they disagree one of them is
 * measuring something nobody named — a listener that silently detached reads as
 * "zero violations", which is the exact shape of a pass. The leg refuses on
 * disagreement rather than believing whichever number it likes.
 */
export function collectCspConsole(page: Page, sink: string[]): void {
  page.on("console", (message) => {
    const text = message.text();
    if (/Content Security Policy|Refused to /i.test(text)) sink.push(text);
  });
}

// ---------------------------------------------------------------------------
// The static bundle census.
// ---------------------------------------------------------------------------

/**
 * `three@0.185.1` ships ONE version and TWO builds
 * (`{"import": "./build/three.module.js", "require": "./build/three.cjs"}`).
 * A graph that pulls both gets two module records of the same package, two
 * distinct `PerspectiveCamera` class objects, and `instanceof` that is FALSE
 * for a perfectly good camera — silently, in the direction that looks like
 * nothing happening. That is already measured true under vitest, where
 * `@react-three/fiber` resolves to its CJS dev build.
 *
 * These two markers are what make the question answerable about the SHIPPED
 * bundle. Both live in `three.core.js`, which every build of three contains
 * exactly one copy of, so their counts scale with the number of copies:
 *
 *   `Multiple instances of Three.js being imported.`  1 per copy
 *   `__THREE__`                                       2 per copy
 *
 * (verified against the installed package: three.core.js 1/2, three.cjs 1/2,
 * three.module.js 0/0 — it re-exports core rather than inlining it.)
 *
 * Two markers rather than one on purpose: they are counted from different
 * statements, so they are a cross-check on each other, and a minifier that
 * mangles one of them shows up as a DISAGREEMENT instead of as a wrong answer.
 */
export const THREE_MARKERS = {
  multiInstanceWarning: {
    literal: "Multiple instances of Three.js being imported.",
    perCopy: 1,
  },
  globalFlag: { literal: "__THREE__", perCopy: 2 },
} as const;

export interface BundleCensus {
  /** Absolute paths of every JS file walked. */
  files: string[];
  /** Total bytes of JS walked — the non-vacuity guard. */
  bytes: number;
  /** Raw occurrence count per marker. */
  counts: Record<keyof typeof THREE_MARKERS, number>;
  /** Copies of `three` implied by each marker independently. */
  copies: Record<keyof typeof THREE_MARKERS, number>;
}

/** Where the built bundle is. Set by `scripts/dist-leg.sh`; `dist` otherwise. */
export function distRoot(): string {
  return process.env["DIST_ROOT"] ?? "dist";
}

/**
 * Census every JS file the build emitted.
 *
 * It REFUSES (throws) on an empty walk rather than reporting zero copies. A
 * gate that examines nothing and reports success is the defect this repo has
 * shipped four times — including `check-build-context.py` printing
 * `0 COPY source(s) reach the build context` and exiting 0 — and "zero copies
 * of three" is exactly the shape that reads like a clean answer.
 */
export function censusBundle(root: string = distRoot()): BundleCensus {
  const assets = join(root, "assets");
  let names: string[];
  try {
    names = readdirSync(assets);
  } catch (cause) {
    throw new Error(
      `the built bundle is not at ${assets} — this leg must run against ` +
        `\`vite build\` output, not the dev server (cause: ${String(cause)})`,
    );
  }
  const files = names
    .filter((name) => name.endsWith(".js"))
    .map((name) => join(assets, name));
  if (files.length === 0) {
    throw new Error(
      `REFUSED: ${assets} contains no .js file. A census that walks nothing ` +
        `makes every "exactly one copy" answer vacuously true.`,
    );
  }

  const counts = { multiInstanceWarning: 0, globalFlag: 0 };
  let bytes = 0;
  for (const file of files) {
    bytes += statSync(file).size;
    const text = readFileSync(file, "utf8");
    for (const key of Object.keys(
      THREE_MARKERS,
    ) as (keyof typeof THREE_MARKERS)[]) {
      counts[key] += occurrences(text, THREE_MARKERS[key].literal);
    }
  }
  // 1 MB is far below the measured 2.13 MB entry chunk and far above anything
  // a broken build could plausibly emit, so it discriminates "we censused the
  // app" from "we censused a stub" without becoming a size assertion that
  // churns.
  if (bytes < 1_000_000) {
    throw new Error(
      `REFUSED: only ${bytes} bytes of JS under ${assets}. The app bundle ` +
        `measures ~2.1 MB; this is not it.`,
    );
  }

  return {
    files,
    bytes,
    counts,
    copies: {
      multiInstanceWarning:
        counts.multiInstanceWarning /
        THREE_MARKERS.multiInstanceWarning.perCopy,
      globalFlag: counts.globalFlag / THREE_MARKERS.globalFlag.perCopy,
    },
  };
}

function occurrences(haystack: string, needle: string): number {
  let count = 0;
  let index = haystack.indexOf(needle);
  while (index !== -1) {
    count += 1;
    index = haystack.indexOf(needle, index + needle.length);
  }
  return count;
}

// ---------------------------------------------------------------------------
// The flow every browser test in this leg shares.
// ---------------------------------------------------------------------------

/**
 * A part with a real OCCT body on screen, built through the real gateway.
 *
 * Chosen for the CSP surfaces it touches rather than for feature coverage: the
 * boot pulls the module script, the stylesheet and eight `data:` fonts; the
 * body pulls a GLB through the proxy and hands it to WebGL; the export below
 * goes through `URL.createObjectURL`. Those are the three things a policy can
 * break while leaving a page that looks perfectly fine.
 *
 * The readiness signal is `body-inspector` PLUS a colour census, not the
 * inspector alone: the panel mounts as soon as the tree has a body, which is
 * before anything is drawn, and "the DOM says there is a body" is exactly the
 * stand-in a blocked blob: would satisfy.
 */
export async function openSeededPart(
  page: Page,
  name: string,
): Promise<string> {
  const account = await seedSession(page);
  const part = await createPlateWithHoleViaApi(page, account.token, name);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("body-inspector")).toBeVisible({
    timeout: 60_000,
  });
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
    .toBeGreaterThan(24);
  return part.id;
}
