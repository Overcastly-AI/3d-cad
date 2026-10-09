import { describe, expect, it } from "vitest";

import { color, sketch } from "./tokens";

/** WCAG 2.x relative luminance of a `#rrggbb` colour. */
function luminance(hex: string): number {
  const n = Number.parseInt(hex.replace("#", ""), 16);
  const channel = (c: number): number => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return (
    0.2126 * channel((n >> 16) & 0xff) +
    0.7152 * channel((n >> 8) & 0xff) +
    0.0722 * channel(n & 0xff)
  );
}

/** WCAG contrast ratio between two `#rrggbb` colours. */
function contrast(a: string, b: string): number {
  const [lo, hi] = [luminance(a), luminance(b)].sort((x, y) => x - y) as [
    number,
    number,
  ];
  return (hi + 0.05) / (lo + 0.05);
}

/** `top` laid over `under` at `opacity`, per channel (sRGB, as the GPU blends). */
function over(top: string, under: string, opacity: number): string {
  const t = Number.parseInt(top.replace("#", ""), 16);
  const u = Number.parseInt(under.replace("#", ""), 16);
  const mix = (shift: number) =>
    Math.round(
      ((t >> shift) & 0xff) * opacity + ((u >> shift) & 0xff) * (1 - opacity),
    );
  return `#${[16, 8, 0].map((s) => mix(s).toString(16).padStart(2, "0")).join("")}`;
}

/** A lit machined-aluminium face under the studio matcap (tokens.ts note). */
const LIT_ALUMINIUM = "#C5C7C8";

describe("sketch.projectedInk", () => {
  const bluedFace = over(
    sketch.faceBluing,
    LIT_ALUMINIUM,
    sketch.faceBluingOpacity,
  );

  it("clears the 3:1 non-text floor on the carbide ground", () => {
    expect(contrast(sketch.projectedInk, color.carbide)).toBeGreaterThanOrEqual(
      3,
    );
  });

  it("clears the 3:1 non-text floor on the face bluing", () => {
    expect(contrast(sketch.projectedInk, bluedFace)).toBeGreaterThanOrEqual(3);
  });

  it("is its own hue, never the scribe, construction or selection ink", () => {
    for (const other of [
      sketch.scribe,
      sketch.scribeSolved,
      sketch.constructionInk,
      sketch.selectedInk,
      sketch.hoverInk,
    ]) {
      expect(sketch.projectedInk).not.toBe(other);
    }
  });
});
