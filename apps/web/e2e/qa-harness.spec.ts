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
   * Settle the scene the only way a `demand` loop can be settled: demand a
   * render and keep demanding until one FAILS to arrive. The rejection is the
   * measurement — it carries the frames that went by with nothing behind them —
   * so this returns it rather than throwing it away.
   *
   * Written as a loop deliberately. A single strict demand right after an orbit
   * is a coin flip on whether OrbitControls is still damping, which is exactly
   * how this gate first went red (2026-08-11): it read "the wait did not throw"
   * as a broken instrument when the scene was simply still moving.
   */
  async function waitForQuiet(page: Page, deadlineMs = 20_000): Promise<Error> {
    const until = Date.now() + deadlineMs;
    for (;;) {
      const outcome = await waitForRenders(page, 1, {
        requireRenders: true,
        timeoutMs: 1_000,
      }).catch((error: Error) => error);
      if (outcome instanceof Error) return outcome;
      if (Date.now() > until) {
        throw new Error(
          `waitForQuiet: the scene never stopped rendering in ${deadlineMs}ms`,
        );
      }
    }
  }

  test("it counts RENDERS not animation frames, and reports what it achieved", async ({
    page,
  }) => {
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
    const [moving] = await Promise.all([
      waitForRenders(page, 5, { requireRenders: true, timeoutMs: 20_000 }),
      orbit(page),
    ]);
    expect(moving.probe).toBe("live");
    expect(moving.renders).toBeGreaterThanOrEqual(5);
    expect(moving.settled).toBe(false);

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
    // The discriminator: a rendered frame is hundreds of colours. This is the
    // reading that separates "the ink is missing" from "the readback is blank".
    expect(live.diagnostics.distinctColors).toBeGreaterThan(24);
    expect(live.diagnostics.renderer ?? "").not.toBe("");
    expect((live.readbackPng ?? "").length).toBeGreaterThan(1_000);
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
