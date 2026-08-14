import type { Page, TestInfo } from "@playwright/test";

import { distinctCanvasColors } from "./support";

/**
 * WHAT THE SHARD REFUSED TO TELL US (CI-4).
 *
 * Four consecutive e2e runs failed on three DIFFERENT single specs, and each
 * one was diagnosed by argument rather than by evidence, because a failed pixel
 * census reports one number and destroys the context that would explain it.
 * `c6b6c6d` is the case in point: `countTokenPixels(page, "#E9F1F8") === 0` is
 * consistent with three unrelated causes, and the run held nothing that could
 * separate them:
 *
 *  · ink 0 with ~300 distinct canvas colours  → the frame rendered, the INK
 *    specifically is missing (a product/depth-order regression).
 *  · ink 0 with ~1 distinct colour            → the readback is blank (lost
 *    context, zero-sized drawing buffer, a substrate failure).
 *  · ink 0 with `renderTick` 0 or null        → nothing has EVER rendered on
 *    this page (0), or there is no render probe on it at all (null); the wait
 *    returned early against a scene that never painted (the CI-4 F1(a)
 *    defect).
 *
 * THAT THIRD BULLET USED TO NAME THE WRONG FIELD, IN THE DANGEROUS DIRECTION
 * (REV-1(d)). It read "ink 0 with a ZERO render-tick DELTA", meaning
 * `rendersInProbeWindow` — which is collected at TEARDOWN, when a
 * `frameloop="demand"` scene is by definition idle. Zero is therefore the
 * HEALTHY value there, and the docstring was advertising it as the defect
 * reading: anyone following it would have diagnosed "nothing rendered at all"
 * on every correctly-working viewport in the suite. The discriminator is the
 * CUMULATIVE `renderTick` (renders since load), which is monotonic and does
 * not care when it is sampled. Both of its diagnostic values are asserted
 * today — `> 0` on a live viewport, `toBeNull()` on a page with no probe.
 *
 * So this attaches the discriminators to every non-passing test, from ONE seam
 * in `fixtures.ts` — the 85 census call sites get it without being touched.
 * The PNG is the census's OWN readback (the WebGL canvas copied through a 2D
 * canvas), not `page.screenshot`: the compositor's picture of a canvas and the
 * drawing buffer a spec reads can differ, and when they do, that difference is
 * the finding.
 *
 * EVERY FIELD BELOW IS EITHER ASSERTED IN `qa-harness.spec.ts` OR ANNOTATED
 * "informational, never asserted". There is no third category, and adding a
 * field without picking one is how a diagnostic quietly becomes decoration —
 * which is the same defect class as an `expect` that cannot fail.
 */
export interface ViewportDiagnostics {
  /**
   * False when the page has no viewport canvas (nothing else is meaningful).
   * Asserted both ways (`qa-harness`: true on the real viewport and on the
   * synthetic stage, false on a bare document).
   */
  canvasPresent: boolean;
  /**
   * `window.__loftRenderTick` — CUMULATIVE r3f renders since load. `null` = no
   * probe on the page; `0` = nothing has ever rendered. THE render
   * discriminator: monotonic, so unlike the probe window below it does not
   * depend on when it was sampled. Asserted both ways (`> 0` live, `toBeNull()`
   * on a probe-less page).
   */
  renderTick: number | null;
  /**
   * Renders during a 10-frame probe taken NOW. **0 is EXPECTED on a settled
   * `demand` scene** — read it only against `framesInProbeWindow`, and only
   * while the scene is animating; a bare 0 says nothing at all. Asserted three
   * ways: `toBeNull()` with no probe, `0` on a settled viewport, and `> 0`
   * while orbiting (REV-1(d) — until then only the null case was covered, so
   * "it counts renders" was never measured).
   */
  rendersInProbeWindow: number | null;
  /**
   * Browser animation frames across that same window (demand-loop contrast:
   * frames without renders behind them is a HEALTHY settled scene, and the
   * reason counting rAFs was unsound). Asserted `> 0` on a live viewport.
   */
  framesInProbeWindow: number;
  /** WebGL context loss/restore events, in order. Asserted empty on a live viewport. */
  glEvents: { kind: string; at: number }[];
  /** True if the context is lost AT THE MOMENT of collection. Asserted false live. */
  contextLost: boolean | null;
  /**
   * Distinct colours in the readback — ~1 means a blank frame. Asserted three
   * ways: `> 24` on a rendered viewport, exactly 1 on a flat synthetic fill,
   * `> 1` once that fill is banded.
   */
  distinctColors: number;
  /** Drawing-buffer size in device px (what a census indexes). Asserted `> 0`. */
  drawingBuffer: { width: number; height: number } | null;
  /**
   * CSS size in layout px. INFORMATIONAL, NEVER ASSERTED: it exists to make a
   * `drawingBuffer` reading legible (a 2x DPR mismatch between the two is the
   * finding), and on its own there is no value that would be wrong.
   */
  cssSize: { width: number; height: number } | null;
  /**
   * Unmasked GL renderer, e.g. the SwiftShader string on a hosted runner.
   * Asserted non-empty — a missing renderer string means the context probe
   * itself failed.
   */
  renderer: string | null;
  /**
   * V8 heap, MB (Chromium only, `null` elsewhere). INFORMATIONAL, NEVER
   * ASSERTED: no threshold here would be anything but arbitrary, and it is
   * carried for the one question it answers on a red run — whether a shard was
   * near exhaustion when the frame went blank.
   */
  heapMB: number | null;
  /**
   * Viewport-relevant DOM stamps that make a blank frame attributable.
   * INFORMATIONAL, NEVER ASSERTED: each stamp is already asserted, in its own
   * spec, by the feature that writes it; duplicating those here would couple
   * the diagnostic to every one of them.
   */
  stamps: Record<string, string>;
}

interface Collected {
  diagnostics: ViewportDiagnostics;
  /** Base64 PNG of the readback, or null when there is no canvas. */
  readbackPng: string | null;
}

const CANVAS_SELECTOR = '[data-testid="viewport"] canvas';
/** Animation frames sampled to measure the live render rate. Cheap by design. */
const PROBE_FRAMES = 10;
/** Nothing here may extend a failing test's teardown by more than this. */
const COLLECT_TIMEOUT_MS = 10_000;

/**
 * Read the viewport's substrate state, right now.
 *
 * Exported (and gated in `qa-harness.spec.ts`) rather than inlined in the
 * fixture, because a diagnostic that is only exercised on failure is a
 * diagnostic nobody has ever seen work — the shape that turned four CI reds
 * into four arguments.
 */
export async function collectViewportDiagnostics(
  page: Page,
): Promise<Collected> {
  const base = await page.evaluate(
    async (input: { selector: string; probeFrames: number }) => {
      const canvas = document.querySelector<HTMLCanvasElement>(input.selector);
      const w = window as {
        __loftRenderTick?: number;
        __loftGlEvents?: { kind: string; at: number }[];
        // Non-standard, Chromium-only; absent elsewhere, hence the guard below.
        performance: Performance & { memory?: { usedJSHeapSize: number } };
      };
      const tickOf = (): number | null =>
        typeof w.__loftRenderTick === "number" ? w.__loftRenderTick : null;

      const before = tickOf();
      let frames = 0;
      for (let i = 0; i < input.probeFrames; i += 1) {
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
      }
      const after = tickOf();

      const stampNames = [
        "data-camera-pos",
        "data-fit-rect",
        "data-nav-rotate-speed",
      ];
      const host = document.querySelector('[data-testid="viewport"]');
      const stamps: Record<string, string> = {};
      for (const name of stampNames) {
        const value = host?.getAttribute(name);
        if (value !== null && value !== undefined) stamps[name] = value;
      }
      for (const id of [
        "tessellation-status",
        "eval-status",
        "sketch-step",
        "viewport-error",
      ]) {
        const node = document.querySelector(`[data-testid="${id}"]`);
        if (node) stamps[id] = (node.textContent ?? "").trim().slice(0, 120);
      }

      // Everything that is true with or without a canvas, stated once.
      const common = {
        renderTick: after,
        rendersInProbeWindow:
          after === null || before === null ? null : 0, // MUTANT: always 0
        framesInProbeWindow: frames,
        glEvents: w.__loftGlEvents ?? [],
        heapMB:
          w.performance.memory === undefined
            ? null
            : Math.round(w.performance.memory.usedJSHeapSize / 1e5) / 10,
        stamps,
      };

      if (!canvas) {
        return {
          ...common,
          canvasPresent: false,
          contextLost: null,
          drawingBuffer: null,
          cssSize: null,
          renderer: null,
          readbackPng: null,
        };
      }

      const gl =
        canvas.getContext("webgl2", { preserveDrawingBuffer: true }) ??
        canvas.getContext("webgl", { preserveDrawingBuffer: true });
      let renderer: string | null = null;
      let contextLost: boolean | null = null;
      if (gl) {
        contextLost = gl.isContextLost();
        const info = gl.getExtension("WEBGL_debug_renderer_info");
        renderer = info
          ? String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL))
          : String(gl.getParameter(gl.RENDERER));
      }

      // The census's own path: WebGL canvas -> 2D canvas -> PNG.
      const probe = document.createElement("canvas");
      probe.width = canvas.width;
      probe.height = canvas.height;
      const ctx = probe.getContext("2d");
      let readbackPng: string | null = null;
      if (ctx && probe.width > 0 && probe.height > 0) {
        ctx.drawImage(canvas, 0, 0);
        readbackPng = probe.toDataURL("image/png").split(",")[1] ?? null;
      }
      const rect = canvas.getBoundingClientRect();

      return {
        ...common,
        canvasPresent: true,
        contextLost,
        drawingBuffer: { width: canvas.width, height: canvas.height },
        cssSize: { width: rect.width, height: rect.height },
        renderer,
        readbackPng,
      };
    },
    { selector: CANVAS_SELECTOR, probeFrames: PROBE_FRAMES },
  );

  const { readbackPng, ...rest } = base;
  const distinctColors = base.canvasPresent
    ? await distinctCanvasColors(page)
    : 0;
  return {
    diagnostics: { ...rest, distinctColors },
    readbackPng,
  };
}

/**
 * Attach the substrate evidence to a non-passing test. Never throws and never
 * blocks teardown for long: a diagnostic that can fail a run, or that can turn
 * a 60 s timeout into a hung shard, is a liability rather than evidence.
 */
export async function attachViewportDiagnostics(
  page: Page,
  testInfo: TestInfo,
): Promise<void> {
  if (page.isClosed()) return;
  try {
    const collected = await Promise.race([
      collectViewportDiagnostics(page),
      new Promise<null>((resolve) =>
        setTimeout(() => resolve(null), COLLECT_TIMEOUT_MS),
      ),
    ]);
    if (collected === null) return;
    await testInfo.attach("viewport-diagnostics.json", {
      body: JSON.stringify(collected.diagnostics, null, 2),
      contentType: "application/json",
    });
    if (collected.readbackPng !== null) {
      await testInfo.attach("viewport-readback.png", {
        body: Buffer.from(collected.readbackPng, "base64"),
        contentType: "image/png",
      });
    }
  } catch {
    // A page that crashed or navigated mid-teardown cannot be probed. The
    // trace and the service logs still land; swallowing here keeps the
    // ORIGINAL failure the reported one.
  }
}
