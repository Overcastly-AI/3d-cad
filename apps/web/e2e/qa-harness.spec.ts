import { expect, test, type Page } from "./fixtures";

import { collectViewportDiagnostics } from "./diagnostics";
import {
  driftPath,
  handClick,
  readPointerTrace,
  recordPointerTrace,
} from "./hand";
import {
  angleBetween,
  cameraPose,
  expectCameraStable,
  expectModelUnoccluded,
  installSceneProbe,
  measureOcclusion,
  overlapArea,
  readCameraProbe,
} from "./invariants";
import { seedCube } from "./partSeed";
import { expectInkLegible, measureInk, silhouette } from "./perception";
import {
  expectReachableFraction,
  hitTest,
  litPoints,
  measureReachability,
  testIdPrefix,
} from "./reachability";
import {
  createPartViaApi,
  distinctCanvasColors,
  INK_MIN_COVERAGE,
  INK_SEPARATION_MARGIN,
  measureInkCoverage,
  seedSession,
  waitForRenders,
} from "./support";

/**
 * THE HARNESS'S HARNESS (FB-17).
 *
 * Every helper this batch adds exists to catch a defect the suite could not
 * see. A gate for unseeable defects that is itself unverified would be an
 * unusually poor joke, and this repo has already been bitten by exactly that
 * shape twice — `countSketchInkPixels` rewarding the broken screen, and
 * `stage-doc-hunks.py`'s self-test passing in the wrong FORMAT while the tool
 * ate a colleague's entry. So each assertion below is paired with a NEGATIVE
 * CONTROL: the same measurement, applied to a deliberately worse input, must
 * come back red. Where the right answer is computable, it is compared against
 * ARITHMETIC rather than against itself.
 *
 * Most of this runs on a SYNTHETIC canvas rather than the real viewport. That
 * is deliberate: a calibration whose reference is the product under test can
 * only ever tell you the two agree. Painting known pixels and known overlays
 * makes the expected number derivable on paper, so a helper that drifts is
 * caught by the harness instead of by a founder.
 */

/** A rectangle painted into the synthetic canvas. */
interface Patch {
  color: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

/** A DOM pick target laid over the synthetic canvas. */
interface Marker {
  testId: string;
  x: number;
  y: number;
  size: number;
}

const SYNTHETIC_CANVAS = "#synthetic";
const SYNTHETIC_WIDTH = 800;
const SYNTHETIC_HEIGHT = 500;

/** Design tokens, copied deliberately: the harness must not follow a rename. */
const INK = "#E9F1F8"; // sketch.scribe
const BENCH = "#0B0E11"; // a dark bench pixel
const ALUMINIUM = "#A9B6C2"; // a lit matcap body pixel

/**
 * Paint a frame with known pixels and known DOM targets over it.
 *
 * `page.setContent` rather than the app: this fixture has no camera, no
 * renderer and no timing, so a number that moves here moved because a helper
 * changed.
 */
async function paintSynthetic(
  page: Page,
  patches: Patch[],
  markers: Marker[] = [],
): Promise<void> {
  await page.setContent(`<!doctype html>
<html><body style="margin:0;background:#000">
  <div id="stage" style="position:relative;width:${SYNTHETIC_WIDTH}px;height:${SYNTHETIC_HEIGHT}px">
    <canvas id="synthetic" width="${SYNTHETIC_WIDTH}" height="${SYNTHETIC_HEIGHT}"
            style="position:absolute;left:0;top:0;width:${SYNTHETIC_WIDTH}px;height:${SYNTHETIC_HEIGHT}px"></canvas>
  </div>
</body></html>`);
  await page.evaluate(
    ({ patches, markers }: { patches: Patch[]; markers: Marker[] }) => {
      const canvas = document.querySelector<HTMLCanvasElement>("#synthetic");
      const stage = document.querySelector<HTMLElement>("#stage");
      if (!canvas || !stage) throw new Error("synthetic stage missing");
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("no 2d context");
      for (const patch of patches) {
        ctx.fillStyle = patch.color;
        ctx.fillRect(patch.x, patch.y, patch.w, patch.h);
      }
      for (const marker of markers) {
        const node = document.createElement("div");
        node.setAttribute("data-testid", marker.testId);
        node.style.cssText = `position:absolute;left:${marker.x}px;top:${marker.y}px;width:${marker.size}px;height:${marker.size}px;background:transparent`;
        stage.append(node);
      }
    },
    { patches, markers },
  );
}

/** Fill the whole synthetic frame with one colour. */
function fill(color: string): Patch {
  return { color, x: 0, y: 0, w: SYNTHETIC_WIDTH, h: SYNTHETIC_HEIGHT };
}

/** Point the ink census at the synthetic canvas rather than the viewport. */
const SYNTH_INK = { hex: INK, selector: SYNTHETIC_CANVAS } as const;

/**
 * Ink drawn as thin lines, the way a scribe actually lands: a few thousand
 * pixels of 2 px stroke, not a solid block.
 */
function inkLines(color: string, count = 24): Patch[] {
  const lines: Patch[] = [];
  for (let i = 0; i < count; i += 1) {
    lines.push({ color, x: 120, y: 80 + i * 12, w: 360, h: 2 });
  }
  return lines;
}

/**
 * Something else in frame — the "context" half of perceptibility. Placed clear
 * of the ink so it never becomes the ink's ground: this patch answers "is the
 * rest of the scene still on screen", not "what is the sketch drawn over".
 */
const CONTEXT_PATCH: Patch = {
  color: ALUMINIUM,
  x: 520,
  y: 380,
  w: 240,
  h: 100,
};

test.describe("harness: input fidelity (hand.ts)", () => {
  test("driftPath lands exactly `drift` away and does not inflate travel", () => {
    for (const drift of [0, 2, 4, 6, 10, 24]) {
      const path = driftPath(drift, 4, 0.6);
      const last = path.at(-1);
      expect(last).toBeDefined();
      const landed = Math.hypot(last?.dx ?? 0, last?.dy ?? 0);
      expect(landed, `drift ${drift}: release point`).toBeCloseTo(drift, 5);

      let travel = 0;
      let px = 0;
      let py = 0;
      for (const point of path) {
        travel += Math.hypot(point.dx - px, point.dy - py);
        px = point.dx;
        py = point.dy;
      }
      // The bow must cost only a few percent. This is the assertion that stops
      // a "more realistic" jitter from silently turning ordinary clicks into
      // drags: `isClick()` sums travel, and CLICK_SLOP_PX is 12.
      expect(travel, `drift ${drift}: accumulated travel`).toBeLessThanOrEqual(
        drift * 1.3 + 1.5,
      );
    }
  });

  test("handClick really moves and really dwells; mouse.click does neither", async ({
    page,
  }) => {
    await paintSynthetic(page, [fill(BENCH)]);

    await recordPointerTrace(page);
    await handClick(page, 400, 250, { drift: 6, dwell: 90 });
    const hand = await readPointerTrace(page);
    expect(hand.downs).toBe(1);
    expect(hand.ups).toBe(1);
    expect(hand.clicked, "a drifting press still produces a DOM click").toBe(
      true,
    );
    expect(
      hand.movesWhileDown,
      "pointermoves between press and release",
    ).toBeGreaterThanOrEqual(4);
    expect(hand.displacementPx, "press → release displacement").toBeGreaterThan(
      5.5,
    );
    expect(hand.travelPx, "accumulated travel").toBeGreaterThan(6);
    expect(hand.travelPx, "…but not a drag").toBeLessThan(12);
    expect(hand.pressMs, "press duration").toBeGreaterThanOrEqual(85);

    // NEGATIVE CONTROL — the input every existing spec drives. Each number
    // above collapses, which is the proof that those assertions are load-
    // bearing and not decoration: a helper quietly reduced to `mouse.click`
    // fails them all.
    await recordPointerTrace(page);
    await page.mouse.click(400, 250);
    const machine = await readPointerTrace(page);
    expect(machine.movesWhileDown, "mouse.click dispatches no movement").toBe(
      0,
    );
    expect(machine.travelPx).toBe(0);
    expect(machine.displacementPx).toBe(0);
    expect(machine.pressMs, "and holds for ~0 ms").toBeLessThan(85);
  });
});

test.describe("harness: perceptibility (perception.ts)", () => {
  test("contrast collapses when the ink's ground brightens", async ({
    page,
  }) => {
    // A working screen: scribe on the dark bench, with the body still in frame.
    await paintSynthetic(page, [fill(BENCH), CONTEXT_PATCH, ...inkLines(INK)]);
    const onBench = await measureInk(page, SYNTH_INK);
    expect(onBench.inkPixels).toBeGreaterThan(1000);
    expect(onBench.contrast).toBeGreaterThan(10);
    // The DEFAULT gate — no thresholds relaxed — passes on this frame.
    await expectInkLegible(page, SYNTH_INK);

    // The SAME ink, the same pixel count, now drawn on a lit face: FB-1b's
    // screen, where the sketch was in the buffer and invisible to a human. A
    // count-based gate cannot tell these two frames apart. Contrast can, and
    // the rejection is pinned to the contrast assertion by its message, not
    // merely to "something threw".
    await paintSynthetic(page, [
      fill(BENCH),
      { color: ALUMINIUM, x: 100, y: 60, w: 400, h: 320 },
      CONTEXT_PATCH,
      ...inkLines(INK),
    ]);
    const onFace = await measureInk(page, SYNTH_INK);
    expect(onFace.inkPixels, "identical ink census").toBe(onBench.inkPixels);
    // Measured: 18.4:1 on the bench → 1.81:1 on the face, from identical ink.
    // Both numbers are asserted rather than just their order, so a helper that
    // stopped sampling the ground (returning a constant) fails here.
    expect(
      onFace.contrast,
      `ink ${onFace.inkLuminance.toFixed(3)} vs ground ${onFace.groundLuminance.toFixed(3)}`,
    ).toBeLessThan(3); // the WCAG 1.4.11 floor the gate enforces
    expect(
      onBench.contrast / onFace.contrast,
      "the same ink must read ~10x worse on the face",
    ).toBeGreaterThan(5);
    await expect(expectInkLegible(page, SYNTH_INK)).rejects.toThrow(
      /vs ground/,
    );
  });

  test("context leaving the frame is a failure even at perfect contrast", async ({
    page,
  }) => {
    // Ink at 18:1 on a bench with NOTHING else on screen — a camera that has
    // flown into the geometry, or a scene that failed to load. Every count and
    // every contrast number looks excellent; the screen is useless.
    await paintSynthetic(page, [fill(BENCH), ...inkLines(INK)]);
    const report = await measureInk(page, SYNTH_INK);
    expect(report.contrast).toBeGreaterThan(10);
    expect(report.contextPixels, "nothing but ink and void").toBe(0);
    await expect(expectInkLegible(page, SYNTH_INK)).rejects.toThrow(/context/);
  });

  test("a frame flooded with ink fails instead of scoring highest", async ({
    page,
  }) => {
    await paintSynthetic(page, [fill(INK)]);
    const flooded = await measureInk(page, SYNTH_INK);
    expect(flooded.inkPixels).toBe(SYNTHETIC_WIDTH * SYNTHETIC_HEIGHT);
    expect(flooded.inkFraction).toBe(1);
    // The old census's number went UP ~500x at the moment the product broke.
    // Under this gate the maximal count is a FAILURE, which is the whole point.
    await expect(expectInkLegible(page, SYNTH_INK)).rejects.toThrow();
  });

  test("a lit face is not counted as ink (the 926 729 px lie)", async ({
    page,
  }) => {
    await paintSynthetic(page, [fill(ALUMINIUM)]);
    const report = await measureInk(page, SYNTH_INK);

    // The predicate the suite used until 2026-08-01, run on the same buffer.
    const legacy = await page.evaluate((selector: string) => {
      const canvas = document.querySelector<HTMLCanvasElement>(selector);
      if (!canvas) return -1;
      const probe = document.createElement("canvas");
      probe.width = canvas.width;
      probe.height = canvas.height;
      const ctx = probe.getContext("2d");
      if (!ctx) return -1;
      ctx.drawImage(canvas, 0, 0);
      const { data } = ctx.getImageData(0, 0, probe.width, probe.height);
      let count = 0;
      for (let i = 0; i < data.length; i += 4) {
        const r = data[i] ?? 0;
        const g = data[i + 1] ?? 0;
        const b = data[i + 2] ?? 0;
        if (r > 120 && b > 140 && b >= r && g >= r) count += 1;
      }
      return count;
    }, SYNTHETIC_CANVAS);

    expect(legacy, "the old predicate calls machined aluminium 'ink'").toBe(
      SYNTHETIC_WIDTH * SYNTHETIC_HEIGHT,
    );
    expect(report.inkPixels, "the token census does not").toBe(0);
  });

  test("silhouette reports the painted body's box, in page coordinates", async ({
    page,
  }) => {
    await paintSynthetic(page, [
      fill(BENCH),
      { color: ALUMINIUM, x: 100, y: 60, w: 400, h: 300 },
    ]);
    const measured = await silhouette(page, { selector: SYNTHETIC_CANVAS });
    // ±1 px: the span is inclusive of the last covered column/row.
    expect(measured.box.left).toBeCloseTo(100, 0);
    expect(measured.box.top).toBeCloseTo(60, 0);
    expect(measured.box.right).toBeCloseTo(499, 0);
    expect(measured.box.bottom).toBeCloseTo(359, 0);
    expect(measured.pixels).toBe(400 * 300);
  });
});

test.describe("harness: the coverage census (support.ts measureInkCoverage)", () => {
  /** The sketcher's layout bluing — the ground the scribe is meant to have. */
  const BLUED: [number, number, number] = [72, 75, 78];
  /** A lit machined-aluminium face — the ground it has when the bluing fails. */
  const LIT: [number, number, number] = [197, 199, 200];
  /** Shading noise amplitude, per the measured frames: ±25 on all channels. */
  const SHADE = 25;

  /**
   * Paint a SHADED surface: a base colour plus deterministic per-pixel noise,
   * which is what a lit face actually is in the buffer — a flat fill is the one
   * frame this census can never get wrong. Luminance noise (the same offset on
   * all three channels) because that is what shading is.
   *
   * Seeded xorshift, so every number asserted below is reproducible on any
   * machine rather than being whatever this run happened to draw.
   */
  async function paintShaded(
    page: Page,
    base: [number, number, number],
    ink: string | null,
  ): Promise<void> {
    await paintSynthetic(page, []);
    await page.evaluate(
      ({
        base,
        amplitude,
        ink,
        w,
        h,
      }: {
        base: [number, number, number];
        amplitude: number;
        ink: string | null;
        w: number;
        h: number;
      }) => {
        const canvas = document.querySelector<HTMLCanvasElement>("#synthetic");
        const ctx = canvas?.getContext("2d");
        if (!ctx) throw new Error("no 2d context");
        let seed = 0x2545f491;
        const next = (): number => {
          seed ^= seed << 13;
          seed ^= seed >>> 17;
          seed ^= seed << 5;
          return (seed >>> 0) / 0x1_0000_0000;
        };
        const clamp = (v: number): number => Math.max(0, Math.min(255, v));
        const image = ctx.createImageData(w, h);
        for (let p = 0; p < w * h; p += 1) {
          const shade = Math.round((next() * 2 - 1) * amplitude);
          image.data[p * 4] = clamp(base[0] + shade);
          image.data[p * 4 + 1] = clamp(base[1] + shade);
          image.data[p * 4 + 2] = clamp(base[2] + shade);
          image.data[p * 4 + 3] = 255;
        }
        ctx.putImageData(image, 0, 0);
        if (ink !== null) {
          ctx.fillStyle = ink;
          for (let i = 0; i < 24; i += 1)
            ctx.fillRect(120, 80 + i * 12, 360, 2);
        }
      },
      { base, amplitude: SHADE, ink, w: SYNTHETIC_WIDTH, h: SYNTHETIC_HEIGHT },
    );
  }

  /**
   * The census AS IT WAS before the separation floor (REV-1(a)): identical
   * arithmetic, guarded only by `axisLengthSq < 1`. Copied rather than imported
   * on purpose — this is the negative control, and a control that follows the
   * code under test controls nothing.
   */
  async function legacyCoverage(page: Page, hex: string): Promise<number> {
    return page.evaluate(
      ({
        hex,
        selector,
        minCoverage,
        axisTolerance,
      }: {
        hex: string;
        selector: string;
        minCoverage: number;
        axisTolerance: number;
      }) => {
        const canvas = document.querySelector<HTMLCanvasElement>(selector);
        const probe = document.createElement("canvas");
        probe.width = canvas?.width ?? 0;
        probe.height = canvas?.height ?? 0;
        const ctx = probe.getContext("2d");
        if (!canvas || !ctx) return -1;
        ctx.drawImage(canvas, 0, 0);
        const { data } = ctx.getImageData(0, 0, probe.width, probe.height);
        const total = data.length / 4;
        const ground: number[] = [0, 0, 0];
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
        const axis = [
          ((token >> 16) & 255) - (ground[0] ?? 0),
          ((token >> 8) & 255) - (ground[1] ?? 0),
          (token & 255) - (ground[2] ?? 0),
        ];
        const axisLengthSq =
          (axis[0] ?? 0) ** 2 + (axis[1] ?? 0) ** 2 + (axis[2] ?? 0) ** 2;
        if (axisLengthSq < 1) return 0;
        let coverage = 0;
        for (let i = 0; i < data.length; i += 4) {
          const v0 = (data[i] ?? 0) - (ground[0] ?? 0);
          const v1 = (data[i + 1] ?? 0) - (ground[1] ?? 0);
          const v2 = (data[i + 2] ?? 0) - (ground[2] ?? 0);
          const t =
            (v0 * (axis[0] ?? 0) + v1 * (axis[1] ?? 0) + v2 * (axis[2] ?? 0)) /
            axisLengthSq;
          if (t < minCoverage) continue;
          const r0 = v0 - t * (axis[0] ?? 0);
          const r1 = v1 - t * (axis[1] ?? 0);
          const r2 = v2 - t * (axis[2] ?? 0);
          if (Math.hypot(r0, r1, r2) > axisTolerance) continue;
          coverage += Math.min(t, 1);
        }
        return Math.round(coverage * 100) / 100;
      },
      {
        hex: hex,
        selector: SYNTHETIC_CANVAS,
        minCoverage: INK_MIN_COVERAGE,
        axisTolerance: 24,
      },
    );
  }

  test("ink over its own bluing is measured, and the ground's noise is reported", async ({
    page,
  }) => {
    await paintShaded(page, BLUED, INK);
    const scribe = await measureInkCoverage(page, INK, {
      selector: SYNTHETIC_CANVAS,
    });

    // The frame is derivable on paper: 24 lines × 360 × 2 px of solid token, so
    // the coverage sum is the painted area to within the noise the ground adds.
    expect(scribe.pixels).toBeGreaterThan(17_000);
    expect(scribe.coverage).toBeGreaterThan(16_000);
    // Nothing foreign is in frame, so nothing may be reported as foreign.
    expect(scribe.offAxis).toBe(0);
    // The ground is FOUND, not assumed — the median of a ±25 shaded face is the
    // face. ±1 for the integer histogram bin.
    expect(scribe.ground[0]).toBeGreaterThan(BLUED[0] - 2);
    expect(scribe.ground[0]).toBeLessThan(BLUED[0] + 2);

    // THE SEPARATION READING, which is what the floor gates on. Measured on
    // this fixture: axis 285.28, noise 22.52, noiseT **0.0789** — i.e. bare
    // ground manufactures 0.08 of coverage per pixel where real ink is 1.0, so
    // the floor (0.125) clears it by 1.6x. The REAL blued frame measures
    // 0.0060; ±25 uniform noise on every channel is deliberately harsher than
    // the shipped wash, so this fixture is the PESSIMISTIC end of "healthy".
    expect(scribe.axisLength).toBeGreaterThan(280);
    expect(scribe.noise).toBeGreaterThan(15);
    expect(scribe.noiseT).toBeLessThan(
      INK_MIN_COVERAGE / INK_SEPARATION_MARGIN,
    );
  });

  test("a lit face with NO ink on it throws instead of reading thousands", async ({
    page,
  }) => {
    // THE REV-1(a) DEFECT, painted. This is the founder's screen — the layout
    // bluing never landed, so the scribe box is bare shaded aluminium — and
    // there is not one pixel of ink in it.
    await paintShaded(page, LIT, null);

    // The census as it shipped: 73.2 of axis, ±25 of shading, and a +25 pixel
    // projects to t = 0.59 (past `INK_MIN_COVERAGE`) with a residual of 5.05,
    // comfortably inside the ±24 tolerance — so it is COUNTED, at 0.59 weight.
    // Measured on this fixture: coverage **48 462.74** against the 400 floor
    // `sketch-visibility` asserts. THAT is what this gate exists to make
    // impossible: the missing-bluing defect reading 121x green on bare metal.
    const legacy = await legacyCoverage(page, INK);
    expect(
      legacy,
      "the pre-REV-1 census counts bare aluminium as ink",
    ).toBeGreaterThan(400);

    // The census now: it refuses the frame, and says why in the units it
    // decided in. A silent 0 was rejected as a fix — the failure direction is
    // false-HIGH, so returning zero only moves the lie.
    await expect(
      measureInkCoverage(page, INK, { selector: SYNTHETIC_CANVAS }),
    ).rejects.toThrow(/separation floor/);
    await expect(
      measureInkCoverage(page, INK, { selector: SYNTHETIC_CANVAS }),
    ).rejects.toThrow(/rgb\(19[5-9],19[7-9],\d+\)/);
  });

  test("the floor is about SEPARATION, not about a short axis", async ({
    page,
  }) => {
    // The distinction the first draft of this guard got wrong, and the reason
    // the floor is a RATIO. A dim construction line over the bench has an axis
    // of 60.9 — SHORTER than the 73.2 that made the lit face degenerate — and
    // it is perfectly measurable, because the bench is smooth: noise 0, so
    // noiseT 0. A length-only guard would have to reject this frame to reject
    // that one.
    await paintSynthetic(page, [
      fill(BENCH),
      ...inkLines("#2A3138"), // a dim construction line over #0B0E11
    ]);
    const dim = await measureInkCoverage(page, "#2A3138", {
      selector: SYNTHETIC_CANVAS,
    });
    expect(dim.axisLength).toBeLessThan(73.2);
    expect(dim.noise).toBe(0);
    expect(dim.noiseT).toBe(0);
    expect(dim.coverage).toBe(24 * 360 * 2);
  });
});

test.describe("harness: reachability (reachability.ts)", () => {
  /** A 400×300 lit face carrying two 24 px pick dots — the shipped affordance. */
  async function faceWithTwoDots(page: Page): Promise<void> {
    await paintSynthetic(
      page,
      [fill(BENCH), { color: ALUMINIUM, x: 100, y: 60, w: 400, h: 300 }],
      [
        { testId: "pick-face-0", x: 180, y: 140, size: 24 },
        { testId: "pick-face-1", x: 360, y: 240, size: 24 },
      ],
    );
  }

  test("the fraction matches arithmetic, and both controls pin it", async ({
    page,
  }) => {
    await faceWithTwoDots(page);
    const points = await litPoints(page, {
      step: 8,
      selector: SYNTHETIC_CANVAS,
    });
    // 400×300 of lit face on an 8 px grid whose samples sit at 4 + 8k: 50
    // columns (100…492) × 38 rows (60…356). Spelled out because a denominator
    // nobody can derive is a denominator nobody can check.
    expect(points.length).toBe(50 * 38);

    const measured = await measureReachability(page, {
      points,
      accept: testIdPrefix("pick-face-"),
    });
    // Two 24 px dots on an 8 px grid cover 3×3 sample points each.
    expect(measured.reachable).toBe(18);
    const analytic = (2 * 24 * 24) / (400 * 300);
    expect(measured.fraction).toBeCloseTo(analytic, 3);
    expect(measured.byTarget).toEqual({ "pick-face-0": 9, "pick-face-1": 9 });

    // CONTROLS. A census that cannot reach 0 or 1 is measuring nothing: the
    // floor proves it is not counting DOM that is not a target, the ceiling
    // proves the denominator is the visible entity and not a subset of it.
    const none = await measureReachability(page, {
      points,
      accept: testIdPrefix("nothing-here-"),
    });
    expect(none.fraction).toBe(0);
    const all = await measureReachability(page, { points, accept: () => true });
    expect(all.fraction).toBe(1);
  });

  test("the gate is red just above the measured affordance and green just below", async ({
    page,
  }) => {
    await faceWithTwoDots(page);
    const options = {
      step: 8,
      selector: SYNTHETIC_CANVAS,
      accept: testIdPrefix("pick-face-"),
    };
    const measured = await measureReachability(page, options);
    await expectReachableFraction(page, {
      ...options,
      min: measured.fraction - 0.001,
    });
    await expect(
      expectReachableFraction(page, { ...options, min: measured.fraction * 2 }),
    ).rejects.toThrow(/clickable/);
  });

  test("a coordinate over the face is NOT a target, though a testid click is", async ({
    page,
  }) => {
    await faceWithTwoDots(page);
    // The distinction the whole module exists for: `getByTestId` resolves to a
    // dot's centre and hits it every time; a point on the face the user is
    // looking at hits the canvas, which is not a pick target at all.
    const dot = await hitTest(page, [{ x: 192, y: 152 }]);
    expect(dot[0]?.testId).toBe("pick-face-0");
    const face = await hitTest(page, [{ x: 300, y: 100 }]);
    expect(face[0]?.testId).toBeNull();
    expect(face[0]?.tag).toBe("canvas");
  });
});

test.describe("harness: occlusion (invariants.ts)", () => {
  test("overlapArea is arithmetic, not vibes", () => {
    const a = { left: 0, top: 0, right: 100, bottom: 100 };
    expect(overlapArea(a, { left: 50, top: 50, right: 150, bottom: 150 })).toBe(
      2500,
    );
    expect(overlapArea(a, { left: 100, top: 0, right: 200, bottom: 100 })).toBe(
      0,
    );
  });

  test("chrome laid over the body is caught; chrome beside it is not", async ({
    page,
  }) => {
    await paintSynthetic(page, [
      fill(BENCH),
      { color: ALUMINIUM, x: 100, y: 60, w: 400, h: 300 },
    ]);
    const place = async (left: number): Promise<void> => {
      await page.evaluate((left: number) => {
        document.querySelector("#chrome")?.remove();
        const node = document.createElement("div");
        node.id = "chrome";
        node.setAttribute("data-viewport-chrome", "panel-editor");
        node.style.cssText = `position:absolute;left:${left}px;top:60px;width:200px;height:300px;background:#101418`;
        document.querySelector("#stage")?.append(node);
      }, left);
    };

    await place(300); // 200 px of the 400 px-wide body, full height
    const covered = await measureOcclusion(page, {
      selector: SYNTHETIC_CANVAS,
    });
    expect(covered.chromeCount).toBe(1);
    expect(covered.offenders[0]?.name).toBe("panel-editor");
    // 200 × 300 of a 400 × 300 box.
    expect(covered.worstFraction).toBeCloseTo(0.5, 2);
    await expect(
      expectModelUnoccluded(page, { selector: SYNTHETIC_CANVAS }),
    ).rejects.toThrow(/chrome over the model/);

    await place(560); // clear of the body's right edge (499)
    const clear = await expectModelUnoccluded(page, {
      selector: SYNTHETIC_CANVAS,
    });
    expect(clear.worstFraction).toBe(0);
    expect(clear.chromeCount, "…and it still SAW the chrome").toBe(1);
  });

  test("a panel that never declared itself as chrome can still be gated", async ({
    page,
  }) => {
    // The escape hatch, kept CALIBRATED rather than kept in use. It was written
    // for FB-7, when the feature editors floated over the viewport carrying no
    // `data-viewport-chrome` at all — the app's own free-rect fit was blind to
    // them and so, by default, was this gate. That is fixed: the editors dock
    // into a `ChromeRail`, which declares itself, so `founder-picking.spec.ts`
    // no longer passes `extraSelectors` for them. This synthetic case stays,
    // because the NEXT undeclared panel is a question of when, not whether, and
    // a gate whose escape hatch has gone untested is a gate that will be wrong
    // about it.
    await paintSynthetic(page, [
      fill(BENCH),
      { color: ALUMINIUM, x: 100, y: 60, w: 400, h: 300 },
    ]);
    await page.evaluate(() => {
      const declared = document.createElement("div");
      declared.setAttribute("data-viewport-chrome", "panel-tree");
      declared.style.cssText =
        "position:absolute;left:600px;top:60px;width:100px;height:300px";
      const undeclared = document.createElement("div");
      undeclared.setAttribute("data-testid", "extrude-editor");
      undeclared.style.cssText =
        "position:absolute;left:300px;top:60px;width:200px;height:300px;background:#101418";
      document.querySelector("#stage")?.append(declared, undeclared);
    });

    // Blind by default — and this is a PASS, which is the danger.
    const blind = await expectModelUnoccluded(page, {
      selector: SYNTHETIC_CANVAS,
    });
    expect(blind.offenders).toEqual([]);

    // Named, the same frame is red.
    await expect(
      expectModelUnoccluded(page, {
        selector: SYNTHETIC_CANVAS,
        extraSelectors: ['[data-testid="extrude-editor"]'],
      }),
    ).rejects.toThrow(/undeclared/);
  });

  test("the gate refuses to pass vacuously with no chrome in the document", async ({
    page,
  }) => {
    await paintSynthetic(page, [
      fill(BENCH),
      { color: ALUMINIUM, x: 100, y: 60, w: 400, h: 300 },
    ]);
    // Nothing overlaps, because nothing is there — which is exactly how a
    // dropped `data-viewport-chrome` contract would look. It must not read as
    // health.
    await expect(
      expectModelUnoccluded(page, { selector: SYNTHETIC_CANVAS }),
    ).rejects.toThrow(/vacuously/);
  });

  test("the gate refuses to pass vacuously with no body on the canvas", async ({
    page,
  }) => {
    // The OTHER degenerate input, and the dangerous one, because it is the
    // shape a broken measurement takes: if the silhouette query ever stops
    // finding the body — a selector rename, a luminance threshold above the
    // matcap, a canvas read that lands before the first paint — the model box
    // collapses to 0×0, overlaps ALL become zero, and an occlusion gate with
    // no floor reports "nothing covers the model" forever while a panel sits
    // squarely on top of it. Verified by mutation as well as asserted here:
    // raising `minLuminance` to 250 (above every pixel in frame) against the
    // FULLY OCCLUDED fixture turns the red assertion green without this guard,
    // and turns it red with it.
    await paintSynthetic(page, [fill(BENCH)]); // bench only: nothing lit
    await page.evaluate(() => {
      const node = document.createElement("div");
      node.setAttribute("data-viewport-chrome", "panel-editor");
      node.style.cssText =
        "position:absolute;left:0;top:0;width:800px;height:500px;background:#101418";
      document.querySelector("#stage")?.append(node);
    });
    await expect(
      expectModelUnoccluded(page, { selector: SYNTHETIC_CANVAS }),
    ).rejects.toThrow(/no lit body/);

    // …and the same thing done to a frame that DOES have a body: a silhouette
    // query that finds nothing must fail rather than report zero overlap.
    await paintSynthetic(page, [
      fill(BENCH),
      { color: ALUMINIUM, x: 100, y: 60, w: 400, h: 300 },
    ]);
    await expect(
      expectModelUnoccluded(page, {
        selector: SYNTHETIC_CANVAS,
        minLuminance: 250,
      }),
    ).rejects.toThrow(/no lit body/);
  });
});

test.describe("harness: camera probe (invariants.ts)", () => {
  test("angleBetween is arithmetic", () => {
    expect(angleBetween([0, 0, -1], [0, 0, -1])).toBeCloseTo(0, 6);
    expect(angleBetween([0, 0, -1], [0, 1, 0])).toBeCloseTo(90, 4);
    expect(angleBetween([0, 0, -1], [0, 0, 1])).toBeCloseTo(180, 4);
  });

  test("the probe reads the MODEL camera, and a real view change fails the gate", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Camera probe");
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("viewport")).toBeVisible();

    /** Click a view snap and wait for the rig's own settle stamp. */
    const snapTo = async (testId: string): Promise<void> => {
      const viewport = page.getByTestId("viewport");
      await viewport.evaluate((node) => {
        node.dataset["fitRect"] = "";
      });
      await page.getByTestId(testId).click();
      await expect(viewport).not.toHaveAttribute("data-fit-rect", "", {
        timeout: 20_000,
      });
    };

    await snapTo("view-iso");
    const iso = await cameraPose(page);
    // The disambiguation is checked, not assumed: two scenes render into this
    // canvas (the model's and the reference cube's Hud), and a probe that
    // silently latched onto the cube's orthographic camera would report a
    // rock-steady direction forever — a gate that can never fail.
    expect(
      iso.agreesWithStamp,
      "probe camera must match the viewport's own data-camera-pos",
    ).toBe(true);

    // A no-op action leaves the direction exactly where it was.
    const still = await expectCameraStable(page, async () => {
      await page.getByTestId("viewport").hover();
    });
    expect(still).toBeLessThan(0.01);

    // NEGATIVE CONTROL: a deliberate view change is a ~50° move, so the gate
    // that will guard "an extrude must not steal the viewpoint" demonstrably
    // goes red when the viewpoint is stolen.
    await expect(
      expectCameraStable(page, () => snapTo("view-front")),
    ).rejects.toThrow(/camera direction moved/);
    const front = await cameraPose(page);
    expect(angleBetween(iso.direction, front.direction)).toBeGreaterThan(20);
  });

  /**
   * THE GAP THE PROBE USED TO FALL INTO (CI-4).
   *
   * `cameraPose` captures the camera inside `onBeforeRender`, so it does not
   * exist until the scene has rendered once — and on a `frameloop="demand"`
   * canvas neither `goto` resolving nor the canvas being visible implies that.
   * The old version read the probe ONCE and threw, so a loaded runner turned
   * that gap into "no camera captured — call installSceneProbe(page) BEFORE
   * page.goto", naming the one cause the probe's own contents ruled out.
   *
   * This drives the gap deliberately rather than waiting for a slow runner to
   * find it: no canvas wait at all, the read taken the instant `goto` returns.
   */
  test("it waits out the first render instead of throwing into the gap", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Camera probe race");
    await page.goto(`/parts/${part.id}`);

    // Deliberately NO `expect(canvas).toBeVisible()` here.
    const atGoto = await readCameraProbe(page);
    const pose = await cameraPose(page);

    expect(
      Math.hypot(...pose.direction),
      "a real unit view direction, not a zero vector",
    ).toBeCloseTo(1, 6);
    // The probe was installed the whole time, which is exactly why the old
    // message was wrong; asserted rather than merely described.
    expect(atGoto.state.installed).toBe(true);
    // And the pose came from the probe filling in, not from somewhere else: a
    // camera exists NOW that may well not have existed at the read above.
    const after = await readCameraProbe(page);
    expect(after.state.captured).toBeGreaterThan(0);
  });

  /**
   * The three causes of a null pose, each one driven into existence, because a
   * diagnostic message nobody has produced is a message nobody has checked.
   */
  test("a missing camera says WHICH of the three causes it is", async ({
    page,
  }) => {
    // (1) No init script: the probe globals are absent.
    await page.setContent("<!doctype html><html><body></body></html>");
    const bare = await readCameraProbe(page);
    expect(bare.state.installed).toBe(false);
    await expect(cameraPose(page, { timeoutMs: 500 })).rejects.toThrow(
      /the scene probe is not on this page/,
    );

    // (2) Installed, but nothing ever constructed a Scene.
    await installSceneProbe(page);
    await page.goto("about:blank");
    const installed = await readCameraProbe(page);
    expect(installed.state.installed).toBe(true);
    expect(installed.state.scenes).toBe(0);
    await expect(cameraPose(page, { timeoutMs: 500 })).rejects.toThrow(
      /never constructed a\s+Scene/,
    );

    // (3) A Scene exists and has never rendered — the measured CI case. Faked
    //     at the devtools seam the probe hooks, so no renderer is needed: what
    //     is under test is the reading, not three.js.
    await page.evaluate(() => {
      const w = window as unknown as Record<string, unknown>;
      const scene = { isScene: true, uuid: "never-rendered" };
      w["__fakeScene"] = scene;
      (w["__THREE_DEVTOOLS__"] as EventTarget).dispatchEvent(
        new CustomEvent("observe", { detail: scene }),
      );
    });
    const unrendered = await readCameraProbe(page);
    expect(unrendered.state.scenes).toBe(1);
    expect(unrendered.state.captured).toBe(0);
    await expect(cameraPose(page, { timeoutMs: 500 })).rejects.toThrow(
      /none has RENDERED/,
    );

    // `captured: 0` is a MEASUREMENT, not a constant: the probe wrapped that
    // scene's `onBeforeRender`, so calling it the way `WebGLRenderer.render`
    // does — with the camera as its third argument — makes a camera appear and
    // the very same call returns a pose. Without this control, a probe that had
    // stopped capturing entirely would pass the three cases above.
    await page.evaluate(() => {
      const scene = (
        window as unknown as Record<
          string,
          { onBeforeRender?: (...args: unknown[]) => void }
        >
      )["__fakeScene"];
      const camera = {
        position: { x: 0, y: 0, z: 4 },
        up: { x: 0, y: 1, z: 0 },
        // Identity: forward is -Z, which is what the pose must report.
        matrixWorld: {
          elements: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
        },
      };
      scene?.onBeforeRender?.(null, scene, camera);
    });
    const rendered = await readCameraProbe(page);
    expect(rendered.state.captured).toBe(1);
    expect(rendered.pose?.direction).toEqual([-0, -0, -1]);
  });
});

test.describe("harness: the render clock (support.ts + Viewport RenderProbe)", () => {
  /**
   * Orbit the scene for real, so renders are being produced WHILE the wait
   * runs. Deliberately not "click a view snap and hope the ease is still
   * going": the point of the assertion is that the wait observes work, and a
   * wait that started after the work finished would prove nothing either way.
   */
  async function orbit(page: Page): Promise<void> {
    const box = await page
      .locator('[data-testid="viewport"] canvas')
      .boundingBox();
    if (box === null) throw new Error("no viewport canvas to orbit");
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    await page.mouse.move(cx, cy);
    await page.mouse.down();
    for (let i = 1; i <= 12; i += 1) {
      await page.mouse.move(cx + i * 6, cy + i * 2);
    }
    await page.mouse.up();
  }

  /**
   * The render clock read from OUTSIDE the code under test (REV-1(c)).
   *
   * `window.__loftRenderTick` is the product's own cumulative counter, and it
   * is the only number in this test that `waitForRenders` does not compute. A
   * wait that miscounts, exits early, or reports work it never observed can
   * satisfy its own return value; it cannot satisfy this one.
   */
  async function readRenderTick(page: Page): Promise<number> {
    return page.evaluate(
      () => (window as { __loftRenderTick?: number }).__loftRenderTick ?? -1,
    );
  }

  /** A window of wall time, measured two ways at once. */
  interface QuietWindow {
    /** Browser animation frames that arrived in it. */
    frames: number;
    /** `__loftRenderTick` movement across the SAME window. */
    tickDelta: number;
  }

  /**
   * Measure frames and renders over one window, IN ONE MESSAGE (REV-1(c)).
   *
   * Deliberately independent of `waitForRenders`: it re-derives the two numbers
   * the demand-loop claim rests on, so a wait that miscounts cannot make this
   * agree with it. Atomic on purpose — bracketing a wait with two `evaluate`
   * round trips from Node measures the gaps as well as the window, which is not
   * the same claim (measured: it reported a tick delta of 3 across a window the
   * wait correctly called quiet, because damping renders landed in the gap).
   */
  async function measureWindow(
    page: Page,
    windowMs = 1_000,
  ): Promise<QuietWindow> {
    return page.evaluate(async (ms: number) => {
      const read = (): number => {
        const tick = (window as { __loftRenderTick?: number }).__loftRenderTick;
        return typeof tick === "number" ? tick : -1;
      };
      const before = read();
      const start = performance.now();
      let frames = 0;
      while (performance.now() - start < ms) {
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
      return { frames, tickDelta: read() - before };
    }, windowMs);
  }

  /**
   * Settle the scene the only way a `demand` loop can be settled: demand a
   * render and keep demanding until one FAILS to arrive. The rejection is the
   * measurement — it carries the frames that went by with nothing behind them —
   * so this returns it rather than throwing it away.
   *
   * Written as a loop deliberately. A single strict demand right after an orbit
   * is a coin flip on whether OrbitControls is still damping, which is exactly
   * how this gate first went red (2026-08-11): it read "the wait did not throw"
   * as a broken instrument when the scene was simply still moving.
   *
   * THE BUDGET IS RENDERS, NOT WALL TIME (QAH-1, 2026-08-15). It was 20_000 ms,
   * and that is a load-dependent bound for a load-independent claim: damping is
   * a fixed amount of WORK (OrbitControls decays the delta per FRAME, ~120
   * renders from a 12-step drag), so its wall-clock tail is that work divided by
   * the frame rate. Measured here on the real stack, orbit then sample the
   * product's own clock once a second:
   *
   *   loaded box  4,4,5,5,4,3,3,3,3,4,3,5,4,5,5,3,5,5,5,4,5,6,6,7,5,6,3,0,0,…
   *                                                       first quiet second: 28 s
   *
   * i.e. under a loaded container (load average 11.6 on 4 cores, software GL at
   * ~4 renders/s) the tail is 28 s and a 20 s budget fails DETERMINISTICALLY —
   * four runs, four failures, and it fails identically with this commit's
   * collector fix reverted, so it is not that fix. At 60 fps the same 120
   * renders settle in ~2 s, which is why the bound held on a quiet runner and
   * why raising the number alone would only move the load at which it breaks.
   *
   * So the loop now spends a RENDER budget, which does not drift with CPU, and
   * keeps a wall-clock only as a hang guard (a scene that stopped painting
   * altogether would otherwise never reach either bound). Note this LOOSENS
   * nothing: the claim being gated is the rejection this returns, plus the
   * `/achieved 0 render\(s\)/`, `painted > 5` and `tickDelta === 0` assertions at
   * the call site — all unchanged. The budget only decides whether a still-
   * damping scene is reported as a failure or waited out.
   */
  async function waitForQuiet(
    page: Page,
    renderBudget = 600,
    hangGuardMs = 180_000,
  ): Promise<Error> {
    const until = Date.now() + hangGuardMs;
    let spent = 0;
    for (;;) {
      const outcome = await waitForRenders(page, 1, {
        requireRenders: true,
        timeoutMs: 1_000,
      }).catch((error: Error) => error);
      if (outcome instanceof Error) return outcome;
      spent += outcome.renders;
      if (spent > renderBudget) {
        throw new Error(
          `waitForQuiet: the scene rendered ${spent} times without going quiet ` +
            `(budget ${renderBudget}). Damping settles in ~120; this many means ` +
            `the loop is not on demand, or something is invalidating forever.`,
        );
      }
      if (Date.now() > until) {
        throw new Error(
          `waitForQuiet: the scene never stopped PAINTING in ${hangGuardMs}ms ` +
            `(${spent} render(s) seen). This is the hang guard, not the budget.`,
        );
      }
    }
  }

  test("it counts RENDERS not animation frames, and reports what it achieved", async ({
    page,
  }) => {
    // This test is a stack of REAL waiting: a seeded part, an orbit, a settle
    // loop, a 1.5 s unreachable demand, a 1 s quiet window and two orbit+probe
    // windows. It measured ~45 s in a quiet container and timed out at the 60 s
    // default once under sibling load — a budget, not a hang, so it gets one
    // rather than losing a measurement. Raised again for QAH-1: the settle loop
    // above now waits out a damping tail that measures 28 s on a loaded box
    // instead of failing at 20 s, and 150 s left no room for that plus the 30 s
    // poll below.
    test.setTimeout(240_000);
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Render clock");
    await seedCube(page, token, part.id);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 60_000,
    });
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
      .toBeGreaterThan(24);

    // (0) The product hook exists. Without it every wait below silently falls
    // back to its frame budget — i.e. the whole instrument degrades to the
    // predecessor and reports health while doing it. That is the CI-4 failure
    // mode wearing a different hat, so it is asserted rather than assumed.
    const tick = await page.evaluate(
      () => (window as { __loftRenderTick?: number }).__loftRenderTick ?? null,
    );
    expect(
      tick,
      "Viewport's RenderProbe must publish window.__loftRenderTick",
    ).not.toBeNull();
    expect(tick as number).toBeGreaterThan(0);

    // (1) SATISFIED: renders happening while the wait runs are counted, and
    // the wait returns on the RENDER count, not on a clock.
    //
    // MEASURED FROM OUTSIDE (REV-1(c)). The three assertions this replaces —
    // `probe === "live"`, `renders >= 5`, `settled === false` — were all
    // guaranteed by construction: with `requireRenders: true` the ONLY
    // non-throwing return in `waitForRenders` is the `observed >= want` branch,
    // which forces all three (a non-zero `observed` implies `baseline !== null`,
    // hence a live probe). They could not fail after a call that did not throw,
    // so they asserted the type, not the behaviour.
    //
    // The product's own cumulative tick is read either side of the whole
    // orbit-and-wait instead. Two claims that the code under test cannot
    // manufacture: the scene really rendered at least the 5 renders that were
    // demanded, and the wait did not report renders it never observed — its
    // window is nested inside this one, so `renders <= outerDelta` always,
    // unless it is counting something other than this clock (frames, or a
    // budget exit dressed up as a render count).
    const tickBefore = await readRenderTick(page);
    const [moving] = await Promise.all([
      waitForRenders(page, 5, { requireRenders: true, timeoutMs: 20_000 }),
      orbit(page),
    ]);
    const outerDelta = (await readRenderTick(page)) - tickBefore;
    expect(
      outerDelta,
      `the orbit must actually render: ${JSON.stringify(moving)}`,
    ).toBeGreaterThanOrEqual(5);
    expect(
      moving.renders,
      `the wait may not report renders it did not observe: ${outerDelta} outside, ${moving.renders} reported`,
    ).toBeLessThanOrEqual(outerDelta);

    // (2) THE FRAME BUDGET: ask for more renders than a settled scene will
    // ever produce, and the wait must still return — on frames, capped —
    // because otherwise every one of the ~100 call sites that waits AFTER an
    // animation has finished would hang.
    const idle = await waitForRenders(page, 1_000_000, { timeoutMs: 20_000 });
    expect(idle.settled).toBe(true);
    expect(idle.frames).toBeGreaterThan(0);

    // (2b) THE DEMAND LOOP (F1(b)), as a measurement rather than a comment:
    // this settled scene keeps producing ANIMATION FRAMES with NO render
    // behind them. That divergence is the whole reason counting rAFs was
    // unsound — `preserveDrawingBuffer` then serves a valid STALE readback —
    // and the two numbers come out of one message, so they cannot disagree.
    //
    // The obvious mutation (`frameloop="always"`) is NOT the control it looks
    // like, measured rather than assumed: under software GL the always-loop
    // renders at ~9 fps for ~13 s and then stops on its own (110 renders in
    // 116 frames, then zero renders in the next second), so it passes both
    // this assertion and the budget one. The falsification here is the
    // arithmetic — 0 renders against several frames — plus mutation (3),
    // which is what actually catches a wait that stops reporting.
    //
    // AND THE LOAD-BEARING CLAIM IS NOW THE OUTER ONE (REV-1(c)). Matching
    // `/achieved 0 render\(s\)/` against the message is tautological: that
    // message only EXISTS on the `requireRenders` path with `want = 1`, so
    // `achieved` can only ever be 0 in it. The match is kept — a `waitForQuiet`
    // that stopped rejecting would be a real regression, and the match pins
    // WHICH failure arrived — but the claim now rests on `measureWindow`
    // below, which re-derives both numbers in ONE message without consulting
    // `waitForRenders` at all.
    const report = String(await waitForQuiet(page));
    expect(report).toMatch(/achieved 0 render\(s\)/);
    const painted = Number(/(\d+) animation frame/.exec(report)?.[1] ?? 0);
    // >5, not >50: a loaded shard paints slower, and the CLAIM is the
    // divergence, not the frame rate. 92 frames in 1.5 s here; 15 fps on a
    // contended runner still clears this comfortably.
    expect(
      painted,
      `the page must keep painting while the scene does not render: ${report}`,
    ).toBeGreaterThan(5);

    // The divergence itself, measured independently over a fresh second: the
    // page keeps painting and the product's own CUMULATIVE render counter does
    // not move. This is what makes `preserveDrawingBuffer` able to serve a
    // valid STALE readback, i.e. why counting rAFs was unsound (F1(b)).
    const quiet = await measureWindow(page);
    expect(
      quiet.frames,
      `a settled scene must still paint: ${JSON.stringify(quiet)}`,
    ).toBeGreaterThan(5);
    expect(
      quiet.tickDelta,
      `__loftRenderTick moved in a window with no demand: ${JSON.stringify(quiet)}`,
    ).toBe(0);

    // (The same instrument over a MOVING window reports a non-zero delta —
    // asserted in (5), which has to come last because everything between here
    // and there requires a SETTLED scene.)

    // (3) NEGATIVE CONTROL — the CI-4 F1(a) defect itself. The predecessor
    // raced the frame loop against `setTimeout(2000)` and RESOLVED SILENTLY
    // when the timer won, so a census on a loaded runner sampled an unfinished
    // frame and nothing said so. An unreachable demand must FAIL, naming the
    // count it got.
    await expect(
      waitForRenders(page, 1_000_000, {
        requireRenders: true,
        timeoutMs: 1_500,
      }),
    ).rejects.toThrow(/achieved \d+ render\(s\)/);

    // (4) …and the failure evidence a red census will now carry.
    const live = await collectViewportDiagnostics(page);
    expect(live.diagnostics.canvasPresent).toBe(true);
    expect(live.diagnostics.contextLost).toBe(false);
    expect(live.diagnostics.glEvents).toEqual([]);
    expect(live.diagnostics.drawingBuffer?.width ?? 0).toBeGreaterThan(0);
    expect(live.diagnostics.drawingBuffer?.height ?? 0).toBeGreaterThan(0);
    expect(live.diagnostics.renderTick ?? 0).toBeGreaterThan(0);
    expect(live.diagnostics.framesInProbeWindow).toBeGreaterThan(0);
    // A SETTLED demand scene renders zero times in the probe window, and that
    // is the HEALTHY reading — see the next block, and `diagnostics.ts`, whose
    // docstring advertised the opposite until REV-1(d).
    expect(live.diagnostics.rendersInProbeWindow).toBe(0);
    // The discriminator: a rendered frame is hundreds of colours. This is the
    // reading that separates "the ink is missing" from "the readback is blank".
    expect(live.diagnostics.distinctColors).toBeGreaterThan(24);
    expect(live.diagnostics.renderer ?? "").not.toBe("");
    expect((live.readbackPng ?? "").length).toBeGreaterThan(1_000);

    // (5) `rendersInProbeWindow` ON A MOVING SCENE (REV-1(d)). Until this
    // landed the field was asserted exactly once in the repo — `toBeNull()`,
    // on a page with no probe — so "it counts renders" was never measured at
    // all, and a collector that returned a constant 0 would have satisfied
    // every gate we had while reading identically to a dead scene.
    //
    // Collected CONCURRENTLY with an orbit, because the probe is a 10-frame
    // window taken NOW: on a settled scene the honest answer is 0 (asserted
    // above), so the only frame that can falsify a broken collector is one
    // where the scene is demonstrably rendering. Polled rather than asserted
    // once — the orbit and the probe window are two independent clocks under
    // software GL, and their overlap is not guaranteed on a contended runner.
    await expect
      .poll(
        async () => {
          const [collected] = await Promise.all([
            collectViewportDiagnostics(page),
            orbit(page),
          ]);
          return collected.diagnostics.rendersInProbeWindow ?? -1;
        },
        {
          timeout: 30_000,
          message:
            "the probe window must see renders while the scene is orbiting",
        },
      )
      .toBeGreaterThan(0);

    // …and `measureWindow`'s own zero from (2b) is a measurement rather than a
    // constant: the SAME instrument over a moving window reports movement. A
    // render probe that stopped incrementing, or a helper that returned 0
    // unconditionally, would have read as perfect health up there.
    const [busy] = await Promise.all([measureWindow(page, 700), orbit(page)]);
    expect(
      busy.tickDelta,
      `the same window must move while the scene orbits: ${JSON.stringify(busy)}`,
    ).toBeGreaterThan(0);
  });

  test("the diagnostics separate a blank readback from a missing render", async ({
    page,
  }) => {
    // The other half of the discriminator, on a frame whose answer is known on
    // paper. A viewport-shaped canvas with ONE colour in it and no render probe
    // is precisely the substrate failure `c6b6c6d` could not be distinguished
    // from — so the collector must report it as such rather than as a canvas
    // that merely lacks ink.
    await page.setContent(`<!doctype html>
<html><body style="margin:0;background:#000">
  <div data-testid="viewport" style="position:relative;width:400px;height:300px">
    <canvas id="synthetic" width="400" height="300"
            style="position:absolute;inset:0;width:400px;height:300px"></canvas>
  </div>
</body></html>`);
    /** Fill the whole frame with `colors` as equal vertical bands. */
    const paint = async (colors: string[]): Promise<void> => {
      await page.evaluate((fills: string[]) => {
        const canvas = document.querySelector<HTMLCanvasElement>("#synthetic");
        const ctx = canvas?.getContext("2d");
        if (!ctx) throw new Error("no 2d context");
        const band = 400 / fills.length;
        fills.forEach((color, index) => {
          ctx.fillStyle = color;
          ctx.fillRect(index * band, 0, band, 300);
        });
      }, colors);
    };

    await paint([BENCH]);
    const blank = await collectViewportDiagnostics(page);
    expect(blank.diagnostics.canvasPresent).toBe(true);
    expect(blank.diagnostics.distinctColors).toBe(1);
    // No `<Canvas>` on this page, so no probe — reported, never faked.
    expect(blank.diagnostics.renderTick).toBeNull();
    expect(blank.diagnostics.rendersInProbeWindow).toBeNull();
    expect((blank.readbackPng ?? "").length).toBeGreaterThan(100);

    // The same instrument on a frame with content moves, so `1` above is a
    // measurement and not a constant.
    await paint([BENCH, ALUMINIUM, INK, "#3B82F6", "#8B5CF6"]);
    const painted = await collectViewportDiagnostics(page);
    expect(painted.diagnostics.distinctColors).toBeGreaterThan(1);

    // A page with no viewport at all must not throw during a failing test's
    // teardown — the original failure stays the reported one.
    await page.setContent("<!doctype html><html><body></body></html>");
    const bare = await collectViewportDiagnostics(page);
    expect(bare.diagnostics.canvasPresent).toBe(false);
    expect(bare.readbackPng).toBeNull();
  });
});
