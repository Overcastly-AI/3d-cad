import { expect, test } from "../e2e/fixtures";

import { openSeededPart } from "./distSupport";

/**
 * THE VIEWPORT IS A LIVE WebGL SURFACE IN THE BUILT BUNDLE.
 *
 * Separate from the CSP spec on purpose. A CSP that blocks a worker or a blob:
 * leaves a viewport that renders the grid and never the body, and "zero
 * violations" plus "the canvas has some pixels" would both still hold. So this
 * asserts the two things that cannot be true of a broken 3D pipeline: the
 * canvas owns a real WebGL2 context that has not been lost, and the r3f render
 * clock actually advanced — `frameloop="demand"` means `requestAnimationFrame`
 * counts BROWSER frames rather than renders, so the clock is the only number
 * that says the scene drew.
 */
test("the built bundle renders the model on a live WebGL2 context", async ({
  page,
}) => {
  await openSeededPart(page, "WebGL plate");

  const gl = await page.evaluate(() => {
    const canvas = document.querySelector("canvas");
    if (canvas === null) return { found: false } as const;
    const context = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
    return {
      found: true,
      // `getContext` hands back the EXISTING context for a canvas that already
      // has one, so this is the app's context rather than a fresh one.
      hasContext: context !== null,
      lost: context === null ? true : context.isContextLost(),
      version:
        context === null
          ? null
          : (context.getParameter(context.VERSION) as string),
      width: canvas.width,
      height: canvas.height,
    } as const;
  });

  expect(gl.found, "the viewport has no <canvas>").toBe(true);
  expect(gl.hasContext, "the viewport canvas has no WebGL context").toBe(true);
  expect(gl.lost, "the WebGL context was lost").toBe(false);
  expect(gl.version).toContain("WebGL");
  // `300x150` is the intrinsic size of an UNSTYLED canvas — a fingerprint of
  // missing CSS, not a measurement — so assert past it rather than at it.
  expect(gl.width).toBeGreaterThan(400);
  expect(gl.height).toBeGreaterThan(300);

  const ticks = await page.evaluate(
    () =>
      (window as unknown as { __loftRenderTick?: number }).__loftRenderTick ??
      0,
  );
  expect(
    ticks,
    "the r3f render clock never advanced — the scene graph exists and nothing drew it",
  ).toBeGreaterThan(0);

  const events = await page.evaluate(
    () =>
      (window as unknown as { __loftGlEvents?: { kind: string }[] })
        .__loftGlEvents ?? [],
  );
  expect(
    events.filter((event) => event.kind === "lost"),
    "the WebGL context was lost at least once during the flow",
  ).toHaveLength(0);
});
