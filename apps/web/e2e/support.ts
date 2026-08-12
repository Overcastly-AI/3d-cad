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

/** What {@link measureInkCoverage} measured. */
export interface InkCoverage {
  /**
   * Estimated ink AREA in canvas px — the SUM of per-pixel coverage, not a
   * count of pixels. This is the phase-invariant number: anti-aliasing splits
   * a line's coverage between neighbouring pixels but conserves the total.
   */
  coverage: number;
  /** Pixels carrying at least `minCoverage` of ink. */
  pixels: number;
  /** The ground the coverage was measured against — MEASURED, not assumed. */
  ground: [number, number, number];
  /**
   * Pixels bright enough to be ink but NOT on the ground→token axis, i.e. some
   * other colour. Non-zero means the box caught something that is not this ink;
   * it is reported so a census can say so instead of quietly counting it.
   */
  offAxis: number;
}

export interface InkCoverageOptions {
  /** Ignore pixels below this coverage — AA tails, not ink. */
  minCoverage?: number;
  /** Max distance off the ground→token axis before a pixel is foreign. */
  axisTolerance?: number;
  /** Restrict to this canvas rectangle. */
  box?: CanvasBox;
}

/** Defaults, exported so a spec can state what it calibrated against. */
export const INK_MIN_COVERAGE = 0.25;
export const INK_AXIS_TOLERANCE = 24;

/**
 * Measure ink by COVERAGE rather than by exact token equality (SPEC-4).
 *
 * WHY THIS EXISTS. `countTokenPixels(hex, 6)` asks "how many pixels are exactly
 * this token", which is the right question for an area fill and the wrong one
 * for a 1 px GL line: the line only lands on the token where it covers a WHOLE
 * pixel, and how much of it does is a sub-pixel phase lottery that changes with
 * the framing, the camera ease, and nothing at all. Measured at HEAD on
 * `sketch-visibility.spec.ts` (2026-08-11): the exact census returned 0 on 5 of
 * 10 runs with the scribe plainly drawn — its pixels sitting at (190,197,204),
 * the token blended at ~0.74 coverage over the blued face — while the count of
 * pixels within ±48 of the token was **736 on a pass and 734 on a fail**. Same
 * ink, different phase, and the exact census returns the SAME zero that a real
 * depth-order regression gives. A gate that cannot tell those apart is not an
 * instrument.
 *
 * HOW. Anti-aliasing conserves coverage, so the sum of it is stable where a
 * count of saturated pixels is not. Each pixel is projected onto the
 * ground→token axis: `t` is how much token is in it (0 = bare ground, 1 = solid
 * ink), and the perpendicular residual is how far the colour is from anything
 * that could BE this ink over this ground. Pixels off the axis are rejected and
 * reported (`offAxis`) rather than counted, which is what keeps a neighbouring
 * token out of the census — `sketch.scribeSolved` (#C4D2DE) sits within ±48 of
 * `sketch.scribe` per channel, so a fat tolerance alone would conflate the two.
 *
 * The ground is MEASURED from the frame (per-channel median of the box), not
 * passed in: the sketcher's bluing is a feathered wash over a shaded face, so
 * there is no constant to hard-code, and a census that hard-codes its own
 * ground drifts silently the day the wash changes.
 *
 * WHAT IT KEEPS. The defect this replaces a census for — coplanar ink losing
 * the depth fight — removes the ink entirely, so every pixel in the box reads
 * as ground, `t ≈ 0`, and the coverage is ~0. The headline power (hundreds vs
 * ZERO) is unchanged; only the false zero is gone.
 */
export async function measureInkCoverage(
  page: Page,
  hex: string,
  options: InkCoverageOptions = {},
): Promise<InkCoverage> {
  const {
    minCoverage = INK_MIN_COVERAGE,
    axisTolerance = INK_AXIS_TOLERANCE,
    box,
  } = options;
  return page.evaluate(
    ({ hex, minCoverage, axisTolerance, box }) => {
      // The annotation is erased before this function crosses into the page;
      // only the value travels.
      const empty: InkCoverage = {
        coverage: 0,
        pixels: 0,
        ground: [0, 0, 0],
        offAxis: 0,
      };
      const canvas = document.querySelector<HTMLCanvasElement>(
        '[data-testid="viewport"] canvas',
      );
      if (!canvas) return empty;
      const probe = document.createElement("canvas");
      probe.width = canvas.width;
      probe.height = canvas.height;
      const ctx = probe.getContext("2d");
      if (!ctx) return empty;
      ctx.drawImage(canvas, 0, 0);
      const rect = box ?? {
        x: 0,
        y: 0,
        width: probe.width,
        height: probe.height,
      };
      if (rect.width <= 0 || rect.height <= 0) return empty;
      const { data } = ctx.getImageData(
        rect.x,
        rect.y,
        rect.width,
        rect.height,
      );
      const total = data.length / 4;
      if (total === 0) return empty;

      // The ground: per-channel median of the box. The ink is a thin minority
      // of a box that is mostly the surface it is drawn on, so the median is
      // that surface — and unlike a mean it is untouched by the ink itself.
      const ground: [number, number, number] = [0, 0, 0];
      for (let channel = 0; channel < 3; channel += 1) {
        const histogram = new Uint32Array(256);
        for (let i = 0; i < data.length; i += 4) {
          const bin = data[i + channel] ?? 0;
          histogram[bin] = (histogram[bin] ?? 0) + 1;
        }
        let seen = 0;
        for (let value = 0; value < 256; value += 1) {
          seen += histogram[value] ?? 0;
          if (seen * 2 >= total) {
            ground[channel] = value;
            break;
          }
        }
      }

      const token = Number.parseInt(hex.slice(1), 16);
      const axis: [number, number, number] = [
        ((token >> 16) & 255) - ground[0],
        ((token >> 8) & 255) - ground[1],
        (token & 255) - ground[2],
      ];
      const axisLengthSq =
        axis[0] * axis[0] + axis[1] * axis[1] + axis[2] * axis[2];
      // Ink indistinguishable from its ground: no coverage is measurable, and
      // saying zero is honest where dividing by it would not be.
      if (axisLengthSq < 1) return { ...empty, ground };

      let coverage = 0;
      let pixels = 0;
      let offAxis = 0;
      for (let i = 0; i < data.length; i += 4) {
        const v0 = (data[i] ?? 0) - ground[0];
        const v1 = (data[i + 1] ?? 0) - ground[1];
        const v2 = (data[i + 2] ?? 0) - ground[2];
        const t = (v0 * axis[0] + v1 * axis[1] + v2 * axis[2]) / axisLengthSq;
        if (t < minCoverage) continue;
        const r0 = v0 - t * axis[0];
        const r1 = v1 - t * axis[1];
        const r2 = v2 - t * axis[2];
        if (Math.hypot(r0, r1, r2) > axisTolerance) {
          offAxis += 1;
          continue;
        }
        coverage += Math.min(t, 1);
        pixels += 1;
      }
      return {
        coverage: Math.round(coverage * 100) / 100,
        pixels,
        ground,
        offAxis,
      };
    },
    { hex, minCoverage, axisTolerance, box },
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

/** What {@link waitForRenders} actually observed. */
export interface RenderWait {
  /** r3f RENDERS observed while waiting (`window.__loftRenderTick` delta). */
  renders: number;
  /** Browser animation frames observed while waiting. */
  frames: number;
  /** True when it exited on the frame budget rather than on the render count. */
  settled: boolean;
  /** Wall clock spent, ms. */
  ms: number;
  /** `live` when the viewport's render probe is on the page. */
  probe: "live" | "missing";
}

export interface RenderWaitOptions {
  /** Give up (and THROW) after this long. */
  timeoutMs?: number;
  /** Refuse the frame-budget exit: `renders` must happen, or throw. */
  requireRenders?: boolean;
}

/** Defaults, named so the harness gate can assert against them. */
const RENDER_WAIT_TIMEOUT_MS = 15_000;
/**
 * Cap on the frame budget, so `waitForRenders(page, 1_000_000)` — the harness
 * gate's way of saying "settle, whatever that takes" — does not ask for a
 * million frames.
 */
const RENDER_WAIT_FRAME_CAP = 30;

/**
 * Wait before sampling the drawing buffer: until the scene has RENDERED
 * `renders` more times, or — for a scene that has nothing left to draw — until
 * `renders` animation frames have gone by, whichever comes first.
 *
 * WHY NOT COUNT ANIMATION FRAMES (CI-4). Its predecessor `waitForFrames`
 * counted rAF callbacks, and was wrong in two independent ways that only show
 * up on a loaded runner:
 *
 *  (a) it raced the rAF loop against `setTimeout(2000)` and RESOLVED SILENTLY
 *      when the timer won. `waitForFrames(page, 30)` therefore degrades to
 *      "wait 2 s" below ~15 fps — the census then samples an unfinished frame
 *      and nothing anywhere reports that the valve tripped. A software-GL scene
 *      on a 4-core hosted runner is exactly that regime. This function throws
 *      instead, naming the count it actually achieved.
 *  (b) the viewport is `frameloop="demand"` (`Viewport.tsx`), so rAFs measure
 *      BROWSER frames, not renders: 30 of them can pass with the scene not
 *      re-rendered once, and `preserveDrawingBuffer: true` then serves a
 *      perfectly valid STALE readback. That is the shape of "ink = 0 with the
 *      frame correctly fitted".
 *
 * So the clock is the render probe's (`window.__loftRenderTick`, incremented
 * inside the demand loop). `waitForFrames` is a thin alias over this, which is
 * how ~100 existing call sites are fixed at ONE seam rather than edited.
 *
 * THE FRAME BUDGET, and why it is exactly `n`. A settled `demand` scene will
 * never render again on its own, so waiting for N renders unconditionally would
 * hang the many call sites that wait AFTER an animation has finished. So the
 * wait also returns after `n` ANIMATION frames (capped) — precisely what
 * `waitForFrames(page, n)` waited — which makes it NEVER SLOWER THAN ITS
 * PREDECESSOR while removing both defects above: no wall-clock shortcut, and
 * nothing exits quietly.
 *
 * That budget is the difference between shipping this and reverting it, and it
 * was MEASURED, not chosen. A stricter rule — also require the scene to fall
 * silent (idle frames + a ms floor) — costs 40 ms per call where a frame costs
 * 5: `qa-sel4-verify`'s two shell tests issue **1 622 waits** (`stampAfterMove`
 * probes hundreds of pixels), which took them from 1.6-1.8 / 2.4 min to
 * 3.0 / 3.0 min against a 180 s ceiling, and both TIMED OUT. Traced, not
 * guessed: 65 s of the 168 s run was inside this function.
 *
 * What the budget gives up, stated plainly: at `n` frames with rendering still
 * in flight it returns like its predecessor did, rather than waiting for quiet.
 * It reports what it saw (`renders`, `frames`, `settled`) so a census can say
 * so, and `requireRenders` — no budget exit at all, throw instead — is there
 * for the assertions that need rendering to have HAPPENED.
 */
export async function waitForRenders(
  page: Page,
  renders = 4,
  options: RenderWaitOptions = {},
): Promise<RenderWait> {
  const { timeoutMs = RENDER_WAIT_TIMEOUT_MS, requireRenders = false } =
    options;
  const result = await page.evaluate(
    async (input: {
      want: number;
      timeoutMs: number;
      frameCap: number;
      requireRenders: boolean;
    }): Promise<RenderWait & { ok: boolean }> => {
      const read = (): number | null => {
        const tick = (window as { __loftRenderTick?: number }).__loftRenderTick;
        return typeof tick === "number" ? tick : null;
      };
      // `baseline` stays null until the probe exists, and rebases the moment it
      // appears: a page that navigates mid-wait would otherwise show the whole
      // new document's tick as "renders since I started waiting".
      let baseline = read();
      const start = performance.now();
      let last = baseline ?? 0;
      let frames = 0;
      for (;;) {
        // The setTimeout is a STARVATION valve, not a race for the answer: a
        // page that stops firing rAF (backgrounded, or a lost context) keeps
        // this loop measuring so it can report, instead of silently resolving.
        const painted = await new Promise<boolean>((resolve) => {
          let settled = false;
          const finish = (viaRaf: boolean): void => {
            if (settled) return;
            settled = true;
            resolve(viaRaf);
          };
          requestAnimationFrame(() => finish(true));
          setTimeout(() => finish(false), 250);
        });
        if (painted) frames += 1;
        const now = performance.now();
        const current = read();
        if (baseline === null && current !== null) {
          baseline = current;
          last = current;
        } else if (current !== null && current !== last) {
          last = current;
        }
        const observed = baseline === null ? 0 : last - baseline;
        const state = {
          renders: observed,
          frames,
          ms: now - start,
          probe: (baseline === null ? "missing" : "live") as "live" | "missing",
        };
        if (observed >= input.want) {
          return { ...state, settled: false, ok: true };
        }
        if (
          !input.requireRenders &&
          frames >= Math.min(input.want, input.frameCap)
        ) {
          return { ...state, settled: true, ok: true };
        }
        if (now - start >= input.timeoutMs) {
          return { ...state, settled: false, ok: false };
        }
      }
    },
    {
      want: renders,
      timeoutMs,
      frameCap: RENDER_WAIT_FRAME_CAP,
      requireRenders,
    },
  );
  if (!result.ok) {
    throw new Error(
      `waitForRenders: wanted ${renders}, achieved ${result.renders} render(s) ` +
        `in ${Math.round(result.ms)}ms (${result.frames} animation frame(s), ` +
        `render probe ${result.probe}). The scene is rendering slower than the ` +
        `wait allows, or it has stopped painting altogether — do NOT sample ` +
        `the drawing buffer on this frame.`,
    );
  }
  return result;
}

/**
 * Wait for the scene to be current before sampling the drawing buffer.
 *
 * Kept as the suite's vocabulary — ~100 call sites — but it is now an alias
 * over {@link waitForRenders}, which counts r3f RENDERS rather than browser
 * animation frames and throws rather than resolving quietly. See that
 * function for why counting frames was wrong (CI-4).
 */
export async function waitForFrames(
  page: Page,
  frames = 4,
): Promise<RenderWait> {
  return waitForRenders(page, frames);
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
