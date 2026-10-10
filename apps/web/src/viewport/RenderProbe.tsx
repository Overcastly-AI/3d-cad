import { useFrame, useThree } from "@react-three/fiber";
import { useEffect } from "react";

/** What the render probe publishes to the page (QA hook — see RenderProbe). */
interface RenderProbeWindow extends Window {
  /** Monotonic count of r3f RENDERS since load. */
  __loftRenderTick?: number;
  /** WebGL context loss/restore, in order, with `performance.now()` stamps. */
  __loftGlEvents?: { kind: "lost" | "restored"; at: number }[];
}

/**
 * THE RENDER CLOCK — the one number the browser does not already expose, and
 * the reason CI-4 could not be diagnosed.
 *
 * The canvas is `frameloop="demand"`, so `requestAnimationFrame` counts BROWSER
 * frames, not renders: the page can tick 30 rAFs while this scene has not
 * re-rendered once. Every e2e pixel census waited on rAFs and then read the
 * drawing buffer, which `preserveDrawingBuffer` happily serves from the LAST
 * render — a perfectly valid STALE frame. That is the exact shape of the CI red
 * on `c6b6c6d` (sketch ink = 0 with the frame correctly fitted), and no
 * evidence in the run could distinguish it from a rendering regression.
 *
 * `useFrame` runs inside the demand loop, so incrementing here counts renders
 * and nothing else. Default priority deliberately: a positive priority takes
 * over rendering from r3f. One integer write per rendered frame, no allocation.
 *
 * The context listeners are not only instrumentation. three's own handler
 * preventDefaults the loss (so the browser restores) and reinitialises on
 * restore — but under `demand` nothing invalidates afterwards, so a restored
 * context would sit on an empty canvas until the user happened to orbit.
 * `invalidate()` repaints it. Loss was entirely silent before this: nothing in
 * `apps/web/src` listened, so "the viewport went blank" had no signal at all,
 * in CI or in front of a user.
 */
export function RenderProbe(): null {
  const gl = useThree((state) => state.gl);
  const invalidate = useThree((state) => state.invalidate);
  useFrame(() => {
    const w = window as RenderProbeWindow;
    w.__loftRenderTick = (w.__loftRenderTick ?? 0) + 1;
  });
  useEffect(() => {
    const w = window as RenderProbeWindow;
    const events = (w.__loftGlEvents ??= []);
    const canvas = gl.domElement;
    const onLost = (): void => {
      events.push({ kind: "lost", at: performance.now() });
    };
    const onRestored = (): void => {
      events.push({ kind: "restored", at: performance.now() });
      invalidate();
    };
    canvas.addEventListener("webglcontextlost", onLost);
    canvas.addEventListener("webglcontextrestored", onRestored);
    return () => {
      canvas.removeEventListener("webglcontextlost", onLost);
      canvas.removeEventListener("webglcontextrestored", onRestored);
    };
  }, [gl, invalidate]);
  return null;
}
