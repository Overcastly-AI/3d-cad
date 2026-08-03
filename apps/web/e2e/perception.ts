import { expect, type Page } from "@playwright/test";

/**
 * PERCEPTIBILITY — can the user SEE it, not merely "is it in the buffer".
 *
 * FB-17(d). The suite's old ink census returned **926 729** on the screen where
 * a sketch on a face was invisible and **1 881** on the screen where it worked:
 * it matched "bright and blue-leaning", which is also a perfect description of
 * machined aluminium under the studio matcap, so its number went UP ~500x at
 * exactly the moment the product broke. A gate that is satisfied by making the
 * product worse is worse than no gate — it converts a defect into evidence of
 * health. `support.countTokenPixels` closed the mis-identification half
 * (an exact token hex cannot be confused with a shaded surface). This module
 * closes the rest, because "there are N ink pixels" is still not "you can see
 * the sketch":
 *
 *  · CONTRAST — the ink is measured against the surface immediately BEHIND it.
 *    Ink rendered at 1.2:1 against its ground is present in the buffer and
 *    invisible to a human, and WCAG's own floor for a graphical object is 3:1.
 *  · CONTEXT — the frame must still contain the model/bench around the ink.
 *    Ink at 21:1 filling the entire viewport is a camera that has fallen into
 *    the geometry, which is a defect that raises every count-based number.
 *
 * Both are properties of the RENDERED FRAME, so they hold whatever the cause —
 * depth fighting, a material change, a camera bug, a token regression.
 *
 * Every function accepts a `selector`, which exists so the harness can point
 * these at a SYNTHETIC canvas with known values and prove the numbers move the
 * right way (`qa-harness.spec.ts`). A measurement nobody has calibrated is an
 * opinion.
 */

/** Default canvas under test: the WebGL viewport. */
export const VIEWPORT_CANVAS = '[data-testid="viewport"] canvas';

/** A rectangle in CSS pixels, in page/client coordinates. */
export interface ScreenBox {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export interface InkReport {
  /** Pixels sampled (drawing-buffer pixels). */
  framePixels: number;
  /** Pixels matching the ink token within tolerance. */
  inkPixels: number;
  inkFraction: number;
  /** Mean WCAG relative luminance (0–1) of the ink pixels. */
  inkLuminance: number;
  /** Mean relative luminance of the non-ink surface immediately around it. */
  groundLuminance: number;
  /** WCAG contrast ratio between the two (1–21). */
  contrast: number;
  /** Non-ink pixels that are not the modal backdrop colour — the context. */
  contextPixels: number;
  contextFraction: number;
  /** The modal (most common) colour in frame, as `#rrggbb` — the backdrop. */
  backdropHex: string;
  backdropFraction: number;
}

export interface InkOptions {
  /** Design-token hex of the ink, e.g. `#E9F1F8` (`sketch.scribe`). */
  hex: string;
  /** Per-channel match tolerance. */
  tolerance?: number;
  /**
   * Distance (buffer px) at which the ground behind the ink is sampled. 3 px
   * clears a 1–2 px line plus its antialiasing without wandering onto a
   * neighbouring feature.
   */
  ring?: number;
  selector?: string;
}

/**
 * Measure ink against the surface behind it, plus how much context shares the
 * frame with it.
 *
 * "The surface behind it" is sampled, not assumed: for every ink pixel the four
 * points at ±`ring` are inspected and the non-ink ones averaged. That is what
 * makes this robust to the actual FB-1b failure — ink coplanar with a lit face
 * has a bright ground and low contrast; the same ink over the dark bench has a
 * high one — without the test needing to know which surface it landed on.
 */
export async function measureInk(
  page: Page,
  options: InkOptions,
): Promise<InkReport> {
  const { hex, tolerance = 6, ring = 3, selector = VIEWPORT_CANVAS } = options;
  return page.evaluate(
    ({
      hex,
      tolerance,
      ring,
      selector,
    }: {
      hex: string;
      tolerance: number;
      ring: number;
      selector: string;
    }): InkReport => {
      const empty: InkReport = {
        framePixels: 0,
        inkPixels: 0,
        inkFraction: 0,
        inkLuminance: 0,
        groundLuminance: 0,
        contrast: 1,
        contextPixels: 0,
        contextFraction: 0,
        backdropHex: "#000000",
        backdropFraction: 0,
      };
      const canvas = document.querySelector<HTMLCanvasElement>(selector);
      if (!canvas) return empty;
      const probe = document.createElement("canvas");
      probe.width = canvas.width;
      probe.height = canvas.height;
      const ctx = probe.getContext("2d");
      if (!ctx) return empty;
      ctx.drawImage(canvas, 0, 0);
      const { width, height } = probe;
      const { data } = ctx.getImageData(0, 0, width, height);
      const total = width * height;

      const value = Number.parseInt(hex.slice(1), 16);
      const tr = (value >> 16) & 255;
      const tg = (value >> 8) & 255;
      const tb = value & 255;

      // WCAG relative luminance: sRGB channels linearised, then weighted.
      const channel = (c: number): number => {
        const s = c / 255;
        return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
      };
      const luminance = (r: number, g: number, b: number): number =>
        0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);

      const isInk = new Uint8Array(total);
      // 5 bits per channel: enough to separate materials, coarse enough that
      // gradient/dither noise still lands in one bucket.
      const histogram = new Uint32Array(32 * 32 * 32);
      let inkPixels = 0;
      let inkLumSum = 0;
      for (let p = 0; p < total; p += 1) {
        const i = p * 4;
        const r = data[i] ?? 0;
        const g = data[i + 1] ?? 0;
        const b = data[i + 2] ?? 0;
        histogram[((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3)] =
          (histogram[((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3)] ?? 0) + 1;
        if (
          Math.abs(r - tr) <= tolerance &&
          Math.abs(g - tg) <= tolerance &&
          Math.abs(b - tb) <= tolerance
        ) {
          isInk[p] = 1;
          inkPixels += 1;
          inkLumSum += luminance(r, g, b);
        }
      }

      let groundSamples = 0;
      let groundLumSum = 0;
      if (inkPixels > 0) {
        const offsets: [number, number][] = [
          [ring, 0],
          [-ring, 0],
          [0, ring],
          [0, -ring],
        ];
        for (let p = 0; p < total; p += 1) {
          if (isInk[p] !== 1) continue;
          const x = p % width;
          const y = (p - x) / width;
          for (const [dx, dy] of offsets) {
            const nx = x + dx;
            const ny = y + dy;
            if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
            const np = ny * width + nx;
            if (isInk[np] === 1) continue;
            const ni = np * 4;
            groundLumSum += luminance(
              data[ni] ?? 0,
              data[ni + 1] ?? 0,
              data[ni + 2] ?? 0,
            );
            groundSamples += 1;
          }
        }
      }

      let modalIndex = 0;
      let modalCount = 0;
      for (let i = 0; i < histogram.length; i += 1) {
        const count = histogram[i] ?? 0;
        if (count > modalCount) {
          modalCount = count;
          modalIndex = i;
        }
      }
      const br = ((modalIndex >> 10) & 31) << 3;
      const bg = ((modalIndex >> 5) & 31) << 3;
      const bb = (modalIndex & 31) << 3;
      let contextPixels = 0;
      for (let p = 0; p < total; p += 1) {
        if (isInk[p] === 1) continue;
        const i = p * 4;
        if (
          Math.abs((data[i] ?? 0) - br) <= 8 &&
          Math.abs((data[i + 1] ?? 0) - bg) <= 8 &&
          Math.abs((data[i + 2] ?? 0) - bb) <= 8
        ) {
          continue;
        }
        contextPixels += 1;
      }

      const inkLuminance = inkPixels > 0 ? inkLumSum / inkPixels : 0;
      const groundLuminance =
        groundSamples > 0 ? groundLumSum / groundSamples : 0;
      const lighter = Math.max(inkLuminance, groundLuminance);
      const darker = Math.min(inkLuminance, groundLuminance);
      const hexOf = (r: number, g: number, b: number): string =>
        `#${[r, g, b].map((c) => c.toString(16).padStart(2, "0")).join("")}`;
      return {
        framePixels: total,
        inkPixels,
        inkFraction: inkPixels / total,
        inkLuminance,
        groundLuminance,
        contrast:
          inkPixels === 0 || groundSamples === 0
            ? 1
            : (lighter + 0.05) / (darker + 0.05),
        contextPixels,
        contextFraction: contextPixels / total,
        backdropHex: hexOf(br, bg, bb),
        backdropFraction: modalCount / total,
      };
    },
    { hex, tolerance, ring, selector },
  );
}

export interface LegibilityGate extends InkOptions {
  /**
   * WCAG 2.1 SC 1.4.11 (non-text contrast) floor for a graphical object. A
   * sketch line IS the information here, so 3:1 is the floor, not a target.
   */
  minContrast?: number;
  /** The ink has to actually be drawn. */
  minInkPixels?: number;
  /**
   * …and must not be the whole screen. The FB-1b census hit 926 729 px of
   * "ink" (~58 % of a 1600×1000 frame) while the sketch was invisible; any
   * gate that can be satisfied by flooding the frame is the same defect.
   */
  maxInkFraction?: number;
  /** Non-ink, non-backdrop pixels that must share the frame — the context. */
  minContextPixels?: number;
}

/**
 * Assert the ink is visible AND situated: enough of it, not all of it, at
 * readable contrast against whatever it is drawn over, with the rest of the
 * scene still in frame.
 *
 * Returns the report so a spec can log the measured numbers — a gate whose
 * numbers are never printed drifts into superstition.
 */
export async function expectInkLegible(
  page: Page,
  gate: LegibilityGate,
): Promise<InkReport> {
  const report = await measureInk(page, gate);
  const {
    minContrast = 3,
    minInkPixels = 200,
    maxInkFraction = 0.25,
    minContextPixels = 20_000,
  } = gate;
  expect(
    report.inkPixels,
    `ink pixels at ${gate.hex} (frame ${report.framePixels})`,
  ).toBeGreaterThanOrEqual(minInkPixels);
  expect(report.inkFraction, "ink must not flood the frame").toBeLessThan(
    maxInkFraction,
  );
  expect(
    report.contrast,
    `ink ${report.inkLuminance.toFixed(3)} vs ground ${report.groundLuminance.toFixed(3)}`,
  ).toBeGreaterThanOrEqual(minContrast);
  expect(
    report.contextPixels,
    `context in frame (backdrop ${report.backdropHex} covers ${(report.backdropFraction * 100).toFixed(1)}%)`,
  ).toBeGreaterThanOrEqual(minContextPixels);
  return report;
}

export interface Silhouette {
  /** Projected bounding box of the lit body, CSS px in page coordinates. */
  box: ScreenBox;
  /** Lit pixels found (drawing-buffer pixels). */
  pixels: number;
}

export interface SilhouetteOptions {
  /**
   * Luminance (raw 0–255 weighting, matching `view-fit.spec.ts`) above which a
   * pixel counts as body rather than bench: the studio matcap's body tone is
   * ~163, the major grid tops out at ~76.
   */
  minLuminance?: number;
  /**
   * Bottom-right square to ignore — the drei reference cube renders INTO the
   * same canvas and its engraved labels are bright, so without this every
   * measurement of "where the body is" reports the cube's edge.
   */
  maskCornerPx?: number;
  /** A column/row needs this many lit pixels to count (an AA speck is not a body). */
  minCoverage?: number;
  selector?: string;
}

interface RawSilhouette {
  left: number;
  top: number;
  right: number;
  bottom: number;
  pixels: number;
  originX: number;
  originY: number;
}

/**
 * Where the body IS on screen, measured from the pixels rather than from the
 * arithmetic that positioned the camera.
 *
 * Reading the canvas (not the scene graph) is the point: a body running under
 * an opaque floating panel is still measured here, which is exactly what the
 * occlusion gate needs to see. Coordinates come back in PAGE space, ready for
 * `page.mouse`, `document.elementFromPoint` and `getBoundingClientRect`
 * comparisons — the three things a reachability or occlusion assertion needs.
 */
export async function silhouette(
  page: Page,
  options: SilhouetteOptions = {},
): Promise<Silhouette> {
  const {
    minLuminance = 110,
    maskCornerPx = 170,
    minCoverage = 4,
    selector = VIEWPORT_CANVAS,
  } = options;
  const raw = await page.evaluate(
    ({
      minLuminance,
      maskCornerPx,
      minCoverage,
      selector,
    }: {
      minLuminance: number;
      maskCornerPx: number;
      minCoverage: number;
      selector: string;
    }): RawSilhouette => {
      const empty: RawSilhouette = {
        left: 0,
        top: 0,
        right: 0,
        bottom: 0,
        pixels: 0,
        originX: 0,
        originY: 0,
      };
      const canvas = document.querySelector<HTMLCanvasElement>(selector);
      if (!canvas) return empty;
      const probe = document.createElement("canvas");
      probe.width = canvas.width;
      probe.height = canvas.height;
      const ctx = probe.getContext("2d");
      if (!ctx) return empty;
      ctx.drawImage(canvas, 0, 0);
      const { data } = ctx.getImageData(0, 0, probe.width, probe.height);
      const columns = new Uint32Array(probe.width);
      const rows = new Uint32Array(probe.height);
      const maskX =
        probe.width - maskCornerPx * (probe.width / (canvas.clientWidth || 1));
      const maskY =
        probe.height -
        maskCornerPx * (probe.height / (canvas.clientHeight || 1));
      let pixels = 0;
      for (let i = 0; i < data.length; i += 4) {
        const r = data[i] ?? 0;
        const g = data[i + 1] ?? 0;
        const b = data[i + 2] ?? 0;
        if (0.2126 * r + 0.7152 * g + 0.0722 * b <= minLuminance) continue;
        const pixel = i / 4;
        const x = pixel % probe.width;
        const y = (pixel - x) / probe.width;
        if (x > maskX && y > maskY) continue;
        columns[x] = (columns[x] ?? 0) + 1;
        rows[y] = (rows[y] ?? 0) + 1;
        pixels += 1;
      }
      const span = (counts: Uint32Array): [number, number] | null => {
        let lo = -1;
        let hi = -1;
        for (let i = 0; i < counts.length; i += 1) {
          if ((counts[i] ?? 0) < minCoverage) continue;
          if (lo < 0) lo = i;
          hi = i;
        }
        return lo < 0 ? null : [lo, hi];
      };
      const xs = span(columns);
      const ys = span(rows);
      if (xs === null || ys === null) return empty;
      const rect = canvas.getBoundingClientRect();
      const sx = (canvas.clientWidth || probe.width) / probe.width;
      const sy = (canvas.clientHeight || probe.height) / probe.height;
      return {
        left: rect.left + xs[0] * sx,
        top: rect.top + ys[0] * sy,
        right: rect.left + xs[1] * sx,
        bottom: rect.top + ys[1] * sy,
        pixels,
        originX: rect.left,
        originY: rect.top,
      };
    },
    { minLuminance, maskCornerPx, minCoverage, selector },
  );
  return {
    box: {
      left: raw.left,
      top: raw.top,
      right: raw.right,
      bottom: raw.bottom,
    },
    pixels: raw.pixels,
  };
}
