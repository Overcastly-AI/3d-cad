/**
 * "Machined aluminum under shop lights" — the studio matcap for solid bodies
 * (Batch 1 makeover; UI-REVIEW 2026-07-16 P0-3). A matcap bakes the whole
 * studio into one sphere image sampled by view-space normal (Plasticity's
 * signature technique): curvature reads at EVERY camera angle with zero
 * scene lights, deterministically (no time-varying input), and with no
 * external HDR/asset request (the prod CSP forbids them).
 *
 * All four stops come from `@loft/design` tokens (`viewport.matcap`) — one
 * palette, two renderers. The texture is rasterised once per session on a
 * small offscreen canvas and shared by every body material.
 */
import { viewport } from "@loft/design/tokens";
import { CanvasTexture, SRGBColorSpace } from "three";

/** Texture edge (px). Matcaps are low-frequency; 256 is crisp and cheap. */
const SIZE = 256;

let shared: CanvasTexture | null = null;

/** Compose the studio sphere: shade ground, body core, warm key, cool rim. */
function paint(ctx: CanvasRenderingContext2D): void {
  const { key, body, shade, rim } = viewport.matcap;
  const c = SIZE / 2;

  // Ground: the shadow side everywhere the lights don't reach.
  ctx.fillStyle = shade;
  ctx.fillRect(0, 0, SIZE, SIZE);

  // Body tone: centred, falling off toward the sphere's silhouette early so
  // curvature keeps a wide, legible mid-tone ramp (the Plasticity read).
  const core = ctx.createRadialGradient(c, c, 0, c, c, c);
  core.addColorStop(0, body);
  core.addColorStop(0.55, body);
  core.addColorStop(1, shade);
  ctx.fillStyle = core;
  ctx.fillRect(0, 0, SIZE, SIZE);

  // Diffuse ramp — light falls from above: upward normals lifted toward the
  // key tint, downward normals settle into shade. Canvas y grows DOWN and
  // matcap v grows UP (CanvasTexture flipY), so "up" = small canvas y.
  const ramp = ctx.createLinearGradient(0, 0, 0, SIZE);
  ramp.addColorStop(0, `${key}59`);
  ramp.addColorStop(0.45, `${key}00`);
  ramp.addColorStop(0.62, `${shade}00`);
  ramp.addColorStop(1, `${shade}CC`);
  ctx.fillStyle = ramp;
  ctx.fillRect(0, 0, SIZE, SIZE);

  // Warm key — the shop lamp, high and to the left, tight enough that a
  // face turned square to it still keeps tonal separation from its
  // neighbours (a broad key washed every upward face white).
  const keyLight = ctx.createRadialGradient(
    SIZE * 0.36,
    SIZE * 0.26,
    SIZE * 0.02,
    SIZE * 0.36,
    SIZE * 0.26,
    SIZE * 0.4,
  );
  keyLight.addColorStop(0, `${key}D9`);
  keyLight.addColorStop(0.4, `${key}59`);
  keyLight.addColorStop(1, `${key}00`);
  ctx.fillStyle = keyLight;
  ctx.fillRect(0, 0, SIZE, SIZE);

  // Cool rim — skylight bounce, low-right, wide and faint.
  const rimLight = ctx.createRadialGradient(
    SIZE * 0.8,
    SIZE * 0.78,
    SIZE * 0.05,
    SIZE * 0.8,
    SIZE * 0.78,
    SIZE * 0.42,
  );
  rimLight.addColorStop(0, `${rim}73`);
  rimLight.addColorStop(1, `${rim}00`);
  ctx.fillStyle = rimLight;
  ctx.fillRect(0, 0, SIZE, SIZE);

  // Sharp specular glint inside the key — machined metal, not clay.
  const glint = ctx.createRadialGradient(
    SIZE * 0.33,
    SIZE * 0.22,
    0,
    SIZE * 0.33,
    SIZE * 0.22,
    SIZE * 0.09,
  );
  glint.addColorStop(0, key);
  glint.addColorStop(1, `${key}00`);
  ctx.fillStyle = glint;
  ctx.fillRect(0, 0, SIZE, SIZE);
}

/**
 * The shared studio matcap texture (created on first use). Never disposed:
 * one small GPU texture for the app's lifetime, reused by every body.
 */
export function studioMatcap(): CanvasTexture {
  if (shared !== null) return shared;
  const canvas = document.createElement("canvas");
  canvas.width = SIZE;
  canvas.height = SIZE;
  const ctx = canvas.getContext("2d");
  if (ctx !== null) paint(ctx);
  const texture = new CanvasTexture(canvas);
  texture.colorSpace = SRGBColorSpace;
  shared = texture;
  return texture;
}
