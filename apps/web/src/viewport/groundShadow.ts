/**
 * The bench contact pool — a soft radial shadow texture drawn under the
 * body (Batch 1 makeover; UI-REVIEW 2026-07-16 P0-1 "ground contact
 * shadow"). Deliberately NOT a per-frame depth-render (drei ContactShadows
 * runs a depth pass + two blur passes every invalidated frame): a baked
 * radial pool is deterministic across runs, free in the render loop, and at
 * CAD scale reads the same — the stock sits ON the bench.
 *
 * Ink comes from `@loft/design` tokens (`viewport.groundShadow`); the
 * texture bakes pure alpha falloff and the material carries the color.
 */
import { CanvasTexture } from "three";

/** Texture edge (px) — a smooth falloff needs very little resolution. */
const SIZE = 128;

let shared: CanvasTexture | null = null;

/**
 * Shared radial-alpha pool texture (white ink, alpha falloff — the material
 * multiplies in the token shadow color). Created once, never disposed.
 */
export function groundShadowTexture(): CanvasTexture {
  if (shared !== null) return shared;
  const canvas = document.createElement("canvas");
  canvas.width = SIZE;
  canvas.height = SIZE;
  const ctx = canvas.getContext("2d");
  if (ctx !== null) {
    const c = SIZE / 2;
    const pool = ctx.createRadialGradient(c, c, 0, c, c, c);
    // Dense core under the body, feathering to nothing at the rim.
    pool.addColorStop(0, "rgba(255,255,255,1)");
    pool.addColorStop(0.55, "rgba(255,255,255,0.92)");
    pool.addColorStop(0.78, "rgba(255,255,255,0.42)");
    pool.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = pool;
    ctx.fillRect(0, 0, SIZE, SIZE);
  }
  shared = new CanvasTexture(canvas);
  return shared;
}
