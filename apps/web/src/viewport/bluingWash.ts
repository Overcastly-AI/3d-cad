/**
 * The layout-bluing wash texture — a soft-edged alpha ramp for the dark ground
 * laid on the model face an active sketch is seated on (`sketch.faceBluing`;
 * placement lives in `SketchScene.tsx`).
 *
 * Why a ramp rather than a hard-edged card: the only thing the client knows
 * about the picked face is its AREA (`PlanarFaceSignature` carries area,
 * centroid and normal — no outline, no bounds), so the wash can only ever be
 * sized by an equal-area guess. A hard square gets that guess visibly wrong on
 * an elongated face: measured on the real stack with a 40 x 10 mm side face,
 * a square card under-covered the length and hung ~6 mm off both long edges as
 * an obvious dark rectangle floating in the void. A feathered patch is wrong
 * gracefully in both directions — it reaches further along a long face, and
 * what spills past a short edge fades out instead of drawing a border.
 *
 * It is also the truer read: bluing is SPRAYED on the stock, so it has a soft
 * edge, not a die-cut one.
 *
 * Rasterised once per session on a small offscreen canvas (the same technique
 * `studioMatcap.ts` uses — deterministic, no external asset request, which the
 * production CSP forbids) and shared by every sketch, so entering and leaving
 * the sketcher allocates no GPU memory.
 */
import { CanvasTexture } from "three";

/** Texture edge (px). A pure radial ramp is low-frequency; 128 is plenty. */
const SIZE = 128;

/**
 * Fraction of the patch radius that stays at FULL bluing before the feather
 * starts. Deliberately high: the feather exists to kill the hard edge, not to
 * make a halo. Measured at 0.5 (feather = half the patch) a 20 mm face wore a
 * visible dark blob half again its own size; at 0.8 the wash reaches ~3.6 mm
 * past the face's corners and reads as a soft edge on the stock.
 */
const CORE_STOP = 0.8;

let shared: CanvasTexture | null = null;

/**
 * The shared wash texture (created on first use). Greyscale: `MeshBasicMaterial`
 * samples an `alphaMap`'s GREEN channel, so white = full bluing, black = none.
 * Left in the default (non-sRGB) colour space — it is a ramp, not a colour, and
 * an sRGB decode would bend the falloff.
 *
 * Never disposed: one 128 px single-channel texture for the app's lifetime,
 * exactly like the studio matcap.
 */
export function bluingWash(): CanvasTexture {
  if (shared !== null) return shared;
  const canvas = document.createElement("canvas");
  canvas.width = SIZE;
  canvas.height = SIZE;
  const ctx = canvas.getContext("2d");
  if (ctx !== null) {
    const c = SIZE / 2;
    ctx.fillStyle = "#000000";
    ctx.fillRect(0, 0, SIZE, SIZE);
    const ramp = ctx.createRadialGradient(c, c, 0, c, c, c);
    ramp.addColorStop(0, "#FFFFFF");
    ramp.addColorStop(CORE_STOP, "#FFFFFF");
    ramp.addColorStop(1, "#000000");
    ctx.fillStyle = ramp;
    ctx.fillRect(0, 0, SIZE, SIZE);
  }
  shared = new CanvasTexture(canvas);
  return shared;
}

/** Floor (mm) so scribing on a tiny face still gets a usable ground. */
const MIN_RADIUS_MM = 12;

/**
 * Patch radius (mm) — half the quad's edge — for a face of the given area.
 *
 * The FULL-bluing core is the circle that circumscribes the equal-area square
 * (side `sqrt(area)`, half-diagonal `sqrt(area)/√2`), so a square-ish face is
 * blued corner to corner at full strength. A circle over a square must either
 * miss the corners or overrun the edges; overrunning by the ~41% a
 * circumscribed circle costs is the cheaper error, because the overrun lands on
 * the ramp. The patch itself is that core divided by {@link CORE_STOP} — the
 * feather and nothing more.
 */
export function bluingRadiusMm(areaMm2: number): number {
  const core = Math.sqrt(Math.max(areaMm2, 0)) * Math.SQRT1_2;
  return Math.max(MIN_RADIUS_MM, core / CORE_STOP);
}
