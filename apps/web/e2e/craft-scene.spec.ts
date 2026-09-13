import {
  sketch as sketchTokens,
  viewport as viewportTokens,
} from "@loft/design/tokens";

import { expect, test, type Page } from "./fixtures";

import { installSceneProbe, namedWorldBox, type WorldBox } from "./invariants";
import { createFeature, rectangleSketch } from "./partSeed";
import {
  createPartViaApi,
  seedSession,
  waitForFrames,
  type CanvasBox,
} from "./support";

/**
 * WAVE 1 OF THE CRAFT REDESIGN — "the 3D scene reads as CAD"
 * (`docs/design/AUDIT-CRAFT-2026-09.md` §3, P1-1/P1-2; CLAUDE.md mandate 3a).
 *
 * Three defects, one fixture, one camera, so the numbers are comparable:
 *
 *  - CRAFT-1 a filleted body had ZERO drawn edges. `EdgesGeometry` is a MESH
 *    CREASE detector and a fillet is tangent by construction, so there was no
 *    crease to find. Now the edges come from the FACE PARTITION, which knows
 *    about B-rep faces rather than about dihedral angles.
 *  - CRAFT-2 the axis-aligned orthographic views were an empty field. A plane
 *    parallel to the view direction projects to a LINE under a parallel
 *    projection — no fade tuning can rescue it — so those views get a grid on
 *    the principal plane that FACES the camera instead.
 *  - CRAFT-3 the origin triad was off by default, so an axis-aligned view told
 *    you nothing about up, origin or scale.
 *
 * ## The instruments, and why these rather than the obvious ones
 *
 * **Ink is measured by ALPHA, not by luminance.** The WebGL canvas is
 * transparent (`gl: { alpha: true }`) and the atmosphere gradient is painted by
 * the DOM behind it, so a census of the canvas sees exactly what the SCENE drew
 * and nothing else. That matters twice over: a luminance threshold (what the
 * audit had to use, reading PNGs) cannot see the minor grid at all — it
 * tone-maps to within ~3 luminance units of the background — and it moves when
 * anything about the palette moves. Alpha coverage is blind to colour, so it
 * cannot be inflated by making the ink brighter, which is the cheapest way to
 * fake a win here. The audit's luminance-32 count is reported alongside it for
 * continuity with the published numbers, never asserted on.
 *
 * **The body is excluded by MEASUREMENT, not by assumption.** The audit's front
 * -ortho reading of 2 396 px was entirely the plate's own antialiased
 * silhouette — a number that looks like grid and is not. Every grid census here
 * runs in a band strictly BELOW the body's own bright footprint, the band is
 * derived from the union of the body's footprint in BOTH projections, and each
 * census asserts that no bright (body) pixel is inside its box. A census that
 * cannot say where its ink came from is not an instrument.
 */

/**
 * Where the before/after evidence frames are written. Unset (the default) skips
 * every capture, so a routine `just e2e` pays nothing and writes nothing — the
 * same posture the founder-shot gate in `fixtures.ts` takes, for the same
 * reason.
 */
const SHOT_DIR = process.env["CRAFT_SHOT_DIR"] ?? "";
const SHOT_TAG = process.env["CRAFT_SHOT_TAG"] ?? "after";

/**
 * Running the BEFORE leg — against a tree where this wave's QA hooks do not
 * exist yet, so the assertions that read them are skipped and only the
 * measurements and the frames are taken. Same posture `body-status.spec.ts`
 * takes with `SHOT_TAG=before`: a before/after pair has to be capturable by a
 * spec that predates half of what it asserts.
 */
const BEFORE = process.env["CRAFT_BEFORE"] === "1";

async function shot(page: Page, name: string): Promise<void> {
  if (SHOT_DIR === "") return;
  const width = page.viewportSize()?.width ?? 0;
  await page.screenshot({
    path: `${SHOT_DIR}/${name}-${SHOT_TAG}-${width}.png`,
  });
}

/**
 * The audit's clear canvas region, as fractions of the canvas.
 *
 * Its numbers (x 336-944, y 104-640 in page coordinates, on a 1280x652 canvas
 * seated at y=100) are the region clear of every DOM panel and overlay at
 * 1280x800. Expressed as fractions they reproduce that box exactly at 1280 and
 * stay clear of the same chrome at 1600, where the panels do not move but the
 * canvas does.
 */
const CLEAR_FRACTION = {
  left: 0.2625,
  right: 0.7375,
  top: 0.006,
  bottom: 0.828,
};

/** Luminance above which a canvas pixel is the lit BODY rather than scene ink. */
const BODY_LUMINANCE = 100;

/** Gap left under the body's footprint so its antialiased tail cannot count. */
const BODY_MARGIN_PX = 14;

/**
 * The three inks a RESTING part workspace draws into the scene, datum first —
 * the classifier in {@link datumInk} depends on that order.
 */
const DATUM_AND_GRID_INKS = [
  sketchTokens.planeEdge,
  viewportTokens.gridMajor,
  viewportTokens.gridMinor,
];

/** The audit's own threshold, reported for continuity with its numbers. */
const AUDIT_LUMINANCE = 32;

/**
 * Ink below this fraction of a pixel is shading, not a line. Calibrated from
 * the frame, not guessed: a fillet's own shading falls ~5 luminance units per
 * pixel at its steepest against a ground-to-token span of ~120, i.e. t ~ 0.04,
 * while a 1 px line's own pixels measure t = 0.8-1.0.
 */
const LINE_MIN_COVERAGE = 0.12;

/** Erosion radius that deletes the body's silhouette band from the census. */
const LINE_ERODE_PX = 3;

interface InkCensus {
  /** Sum of per-pixel alpha — the tone-mapping-blind reading. */
  coverage: number;
  /** Pixels with any alpha at all. */
  drawn: number;
  /** The audit's instrument: pixels above luminance 32. */
  auditLuminance: number;
  /** Pixels at BODY_LUMINANCE or above — must be 0 in a body-free box. */
  body: number;
}

/** A canvas-pixel box, and the device-pixel scale the census runs in. */
interface CanvasFrame {
  /** Canvas bounding rect in CSS px. */
  rect: { x: number; y: number; width: number; height: number };
  /** canvas.width / rect.width — the drawing buffer scale. */
  scale: number;
}

async function canvasFrame(page: Page): Promise<CanvasFrame> {
  return page.evaluate(() => {
    const canvas = document.querySelector<HTMLCanvasElement>(
      '[data-testid="viewport"] canvas',
    );
    if (!canvas) throw new Error("no viewport canvas");
    const rect = canvas.getBoundingClientRect();
    return {
      rect: {
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height,
      },
      scale: canvas.width / rect.width,
    };
  });
}

/** The audit's clear region, expressed in canvas drawing-buffer pixels. */
function clearBox(frame: CanvasFrame): CanvasBox {
  const w = frame.rect.width * frame.scale;
  const h = frame.rect.height * frame.scale;
  return {
    x: Math.round(w * CLEAR_FRACTION.left),
    y: Math.round(h * CLEAR_FRACTION.top),
    width: Math.round(w * (CLEAR_FRACTION.right - CLEAR_FRACTION.left)),
    height: Math.round(h * (CLEAR_FRACTION.bottom - CLEAR_FRACTION.top)),
  };
}

/**
 * Census a canvas box four ways in ONE readback.
 *
 * One `drawImage` + `getImageData` per call: the readback is the cost, not the
 * arithmetic, and a spec that reads the frame four times gets four different
 * frames on a demand-rendered scene.
 */
async function census(page: Page, box: CanvasBox): Promise<InkCensus> {
  return page.evaluate(
    ({ box, bodyLuminance, auditLuminance }) => {
      const canvas = document.querySelector<HTMLCanvasElement>(
        '[data-testid="viewport"] canvas',
      );
      if (!canvas) throw new Error("no viewport canvas");
      const probe = document.createElement("canvas");
      probe.width = canvas.width;
      probe.height = canvas.height;
      const ctx = probe.getContext("2d");
      if (!ctx) throw new Error("no 2d context");
      ctx.drawImage(canvas, 0, 0);
      const { data } = ctx.getImageData(box.x, box.y, box.width, box.height);
      let coverage = 0;
      let drawn = 0;
      let auditCount = 0;
      let body = 0;
      for (let i = 0; i < data.length; i += 4) {
        const alpha = data[i + 3] ?? 0;
        if (alpha === 0) continue;
        coverage += alpha / 255;
        drawn += 1;
        const lum =
          0.2126 * (data[i] ?? 0) +
          0.7152 * (data[i + 1] ?? 0) +
          0.0722 * (data[i + 2] ?? 0);
        if (lum > auditLuminance) auditCount += 1;
        if (lum >= bodyLuminance) body += 1;
      }
      return { coverage, drawn, auditLuminance: auditCount, body };
    },
    { box, bodyLuminance: BODY_LUMINANCE, auditLuminance: AUDIT_LUMINANCE },
  );
}

/** The body's own footprint: the bbox of lit pixels inside `box`, or null. */
async function bodyFootprint(
  page: Page,
  box: CanvasBox,
): Promise<{ top: number; bottom: number; pixels: number } | null> {
  return page.evaluate(
    ({ box, bodyLuminance }) => {
      const canvas = document.querySelector<HTMLCanvasElement>(
        '[data-testid="viewport"] canvas',
      );
      if (!canvas) throw new Error("no viewport canvas");
      const probe = document.createElement("canvas");
      probe.width = canvas.width;
      probe.height = canvas.height;
      const ctx = probe.getContext("2d");
      if (!ctx) throw new Error("no 2d context");
      ctx.drawImage(canvas, 0, 0);
      const { data } = ctx.getImageData(box.x, box.y, box.width, box.height);
      let top = Number.POSITIVE_INFINITY;
      let bottom = Number.NEGATIVE_INFINITY;
      let pixels = 0;
      for (let row = 0; row < box.height; row += 1) {
        for (let col = 0; col < box.width; col += 1) {
          const i = (row * box.width + col) * 4;
          if ((data[i + 3] ?? 0) === 0) continue;
          const lum =
            0.2126 * (data[i] ?? 0) +
            0.7152 * (data[i + 1] ?? 0) +
            0.0722 * (data[i + 2] ?? 0);
          if (lum < bodyLuminance) continue;
          pixels += 1;
          if (row < top) top = row;
          if (row > bottom) bottom = row;
        }
      }
      return pixels === 0
        ? null
        : { top: box.y + top, bottom: box.y + bottom, pixels };
    },
    { box, bodyLuminance: BODY_LUMINANCE },
  );
}

/** What {@link interiorLineInk} measured. */
interface LineInk {
  /** Sum of per-pixel ink coverage — anti-aliasing conserves this. */
  coverage: number;
  /** Pixels carrying any ink at all. */
  pixels: number;
  /** Size of the region the census ran in — a vacuous 0 is attributable. */
  region: number;
  /** Pixels landing exactly on the token (+/- 10) — the strict second reading. */
  exact: number;
}

/**
 * LINE WORK DRAWN ON THE BODY'S INTERIOR — the reading CRAFT-1 turns on.
 *
 * ## Why the region is eroded
 *
 * A body always has a SILHOUETTE: the shape boundary between lit surface and
 * background, which exists whether or not a single edge is drawn. Counting it
 * flatters every instrument — the audit's clay frame
 * (`06-filleted-body-no-edges.png`) still had one — so the census runs on the
 * DRAWN mask eroded by 3 px, which deletes the silhouette band and, with it,
 * every isolated grid line (a 1 px line surrounded by transparent background
 * cannot survive a 3 px erosion). What is left is the body's interior, where
 * the only dark marks are the ones the edge overlay put there. That is exactly
 * the ink the tangent-boundary defect destroyed.
 *
 * ## Why coverage rather than a token count
 *
 * A 1 px GL line lands on its literal token only where it covers a WHOLE
 * pixel, and how often that happens is a sub-pixel phase lottery (support.ts,
 * `measureInkCoverage`). Anti-aliasing conserves COVERAGE, so each pixel is
 * scored against the brightest of its four neighbours — the surface the line
 * is drawn over — as `(neighbour - pixel) / (neighbour - token)`. A pixel on a
 * shading gradient scores near zero because its neighbours are nearly as dark
 * as it is; a pixel on a line scores near one because they are not. Both
 * readings are returned: `coverage` is the instrument, `exact` is the strict
 * token count, and they are derived differently enough that agreeing is
 * evidence.
 */
async function interiorLineInk(
  page: Page,
  hex: string,
  box: CanvasBox,
): Promise<LineInk> {
  return page.evaluate(
    ({ hex, box, minCoverage, erode }) => {
      const canvas = document.querySelector<HTMLCanvasElement>(
        '[data-testid="viewport"] canvas',
      );
      if (!canvas) throw new Error("no viewport canvas");
      const probe = document.createElement("canvas");
      probe.width = canvas.width;
      probe.height = canvas.height;
      const ctx = probe.getContext("2d");
      if (!ctx) throw new Error("no 2d context");
      ctx.drawImage(canvas, 0, 0);
      const { data } = ctx.getImageData(box.x, box.y, box.width, box.height);
      const w = box.width;
      const h = box.height;
      const lum = new Float32Array(w * h);
      const opaque = new Uint8Array(w * h);
      for (let i = 0, p = 0; p < w * h; p += 1, i += 4) {
        lum[p] =
          0.2126 * (data[i] ?? 0) +
          0.7152 * (data[i + 1] ?? 0) +
          0.0722 * (data[i + 2] ?? 0);
        opaque[p] = (data[i + 3] ?? 0) === 255 ? 1 : 0;
      }
      // Erode the fully-opaque mask: a pixel survives only if every pixel
      // within `erode` of it is opaque too.
      const inside = new Uint8Array(w * h);
      for (let y = erode; y < h - erode; y += 1) {
        for (let x = erode; x < w - erode; x += 1) {
          let ok = 1;
          for (let dy = -erode; dy <= erode && ok; dy += 1) {
            for (let dx = -erode; dx <= erode; dx += 1) {
              if (opaque[(y + dy) * w + (x + dx)] === 0) {
                ok = 0;
                break;
              }
            }
          }
          inside[y * w + x] = ok as 0 | 1;
        }
      }
      const value = Number.parseInt(hex.slice(1), 16);
      const target = [(value >> 16) & 255, (value >> 8) & 255, value & 255];
      const tokenLum =
        0.2126 * (target[0] as number) +
        0.7152 * (target[1] as number) +
        0.0722 * (target[2] as number);
      let coverage = 0;
      let pixels = 0;
      let region = 0;
      let exact = 0;
      for (let y = 1; y < h - 1; y += 1) {
        for (let x = 1; x < w - 1; x += 1) {
          const p = y * w + x;
          if (inside[p] === 0) continue;
          region += 1;
          const i = p * 4;
          if (
            Math.abs((data[i] ?? 0) - (target[0] as number)) <= 10 &&
            Math.abs((data[i + 1] ?? 0) - (target[1] as number)) <= 10 &&
            Math.abs((data[i + 2] ?? 0) - (target[2] as number)) <= 10
          ) {
            exact += 1;
          }
          const ground = Math.max(
            lum[p - 1] as number,
            lum[p + 1] as number,
            lum[p - w] as number,
            lum[p + w] as number,
          );
          if (ground <= tokenLum) continue;
          const t = ((ground - (lum[p] as number)) /
            (ground - tokenLum)) as number;
          if (t < minCoverage) continue;
          coverage += Math.min(t, 1);
          pixels += 1;
        }
      }
      return { coverage, pixels, region, exact };
    },
    { hex, box, minCoverage: LINE_MIN_COVERAGE, erode: LINE_ERODE_PX },
  );
}

/** What {@link datumInk} classified in a box. */
interface InkClasses {
  /** Pixels nearer the datum ink than either grid ink. */
  datum: number;
  /** Pixels nearer a grid ink — reported so the census can say what else is here. */
  grid: number;
  /** Drawn pixels too far from any of the three to classify. */
  other: number;
}

/**
 * Classify the scene ink in a box as DATUM or GRID, by nearest token.
 *
 * WHY NOT AN EXACT-TOKEN COUNT, which is what every other census in this suite
 * uses: the resting origin mark is TRANSLUCENT, so it never lands on its own
 * token exactly — it lands on a blend of the token and whatever is behind it.
 * Measured at `preview.edgeOpacity` over the bench, its pixels read (86,102,121)
 * against a token of (90,106,126): inside a +/-8 tolerance by one unit per
 * channel. That is a knife edge, and it behaved like one — the identical scene
 * censused 248 px in one run and 0 in the next, because the blend drifted a
 * unit with the camera pose. An instrument that reports zero for a line you can
 * see is worse than no instrument.
 *
 * A CLASSIFIER has no edge to fall off. The three inks a resting part workspace
 * draws are far apart — gridMinor (35,46,60), gridMajor (62,77,97), planeEdge
 * (90,106,126) — so "which of these three is this pixel nearest" is stable
 * against several units of drift in a way "is it within 8 of this one" is not.
 * The rejected classes are returned rather than discarded, so a box that fills
 * up with something unexpected says so.
 */
async function datumInk(page: Page, box: CanvasBox): Promise<InkClasses> {
  return page.evaluate(
    ({ box, inks, limit }) => {
      const canvas = document.querySelector<HTMLCanvasElement>(
        '[data-testid="viewport"] canvas',
      );
      if (!canvas) throw new Error("no viewport canvas");
      const probe = document.createElement("canvas");
      probe.width = canvas.width;
      probe.height = canvas.height;
      const ctx = probe.getContext("2d");
      if (!ctx) throw new Error("no 2d context");
      ctx.drawImage(canvas, 0, 0);
      const { data } = ctx.getImageData(box.x, box.y, box.width, box.height);
      const rgb = inks.map((hex) => {
        const value = Number.parseInt(hex.slice(1), 16);
        return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
      });
      let datum = 0;
      let grid = 0;
      let other = 0;
      for (let i = 0; i < data.length; i += 4) {
        if ((data[i + 3] ?? 0) === 0) continue;
        let best = -1;
        let bestDistance = Number.POSITIVE_INFINITY;
        rgb.forEach((ink, index) => {
          const d = Math.hypot(
            (data[i] ?? 0) - (ink[0] as number),
            (data[i + 1] ?? 0) - (ink[1] as number),
            (data[i + 2] ?? 0) - (ink[2] as number),
          );
          if (d < bestDistance) {
            bestDistance = d;
            best = index;
          }
        });
        if (bestDistance > limit) other += 1;
        else if (best === 0) datum += 1;
        else grid += 1;
      }
      return { datum, grid, other };
    },
    // ORDER IS THE CONTRACT: index 0 is the datum ink, the rest are grid.
    { box, inks: DATUM_AND_GRID_INKS, limit: 40 },
  );
}

/**
 * An 80 x 60 x 12 plate, optionally with a 4 mm break on every edge — the
 * audit's own fixture (`06-filleted-body-no-edges.png` /
 * `07-sharp-body-edges.png`), so these numbers answer the published ones.
 */
async function seedPlate(page: Page, filletMm: number | null): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(
    page,
    account.token,
    filletMm === null ? "Plate sharp" : "Plate broken edges",
  );
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: {
      type: "sketch",
      version: 1,
      params: rectangleSketch(0, 0, 80, 60),
    },
    expected_tree_version: 0,
  });
  const extrude = await createFeature(page, account.token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 12,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  if (filletMm !== null) {
    await createFeature(page, account.token, part.id, {
      name: "Edge break",
      feature: {
        type: "fillet",
        version: 1,
        params: { edges: { kind: "all_edges" }, radius_mm: filletMm },
      },
      expected_tree_version: extrude.tree_version,
    });
  }
  return part.id;
}

/** Open a part, wait for the solve, the auto-fit and a real body in the graph. */
async function openPart(page: Page, partId: string): Promise<void> {
  await page.goto(`/parts/${partId}`);
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  await expect(page.getByTestId("viewport")).toHaveAttribute(
    "data-view",
    "fit-auto",
    { timeout: 30_000 },
  );
  await expect
    .poll(
      async () => (await namedWorldBox(page, "model-body"))?.vertices ?? 0,
      {
        timeout: 30_000,
      },
    )
    .toBeGreaterThan(0);
  // The body is in the graph; the frame it is drawn in is a separate event on a
  // demand-rendered scene, so the canvas census waits for RENDERS explicitly
  // rather than inheriting an incidental settle from the DOM waits above.
  await waitForFrames(page, 3);
}

/** Fire a named view and wait for the rig to report it settled. */
async function snapTo(page: Page, testId: string, view: string): Promise<void> {
  await page.evaluate(() => {
    document
      .querySelector('[data-testid="viewport"]')
      ?.removeAttribute("data-view");
  });
  await page.getByTestId(testId).click();
  await expect(page.getByTestId("viewport")).toHaveAttribute(
    "data-view",
    view,
    {
      timeout: 20_000,
    },
  );
  await waitForFrames(page, 3);
}

async function setProjection(
  page: Page,
  want: "orthographic" | "perspective",
): Promise<void> {
  const viewport = page.getByTestId("viewport");
  const now = await viewport.getAttribute("data-projection");
  if (now !== want) {
    await page.getByTestId("view-projection").click();
    await expect(viewport).toHaveAttribute("data-projection", want, {
      timeout: 10_000,
    });
  }
  await waitForFrames(page, 3);
}

/**
 * Wait until the DRAWN FRAME stops changing, before sampling it.
 *
 * WRITTEN DOWN rather than inherited, and this is the third instrument in this
 * file to be replaced because it could not observe its own subject:
 *
 *  - `data-view` / `data-projection` are stamps that land when a command is
 *    ACCEPTED, while the rig then eases the pose over many frames. Deleting
 *    three unrelated DOM assertions — each quietly costing ~100 ms of polling —
 *    took the resting triad's census from 248 px to 0 on identical sources.
 *  - `data-camera-pos` looks like the fix and is not: it is stamped on SETTLE,
 *    so during an ease it holds a CONSTANT — measured 40.0,2.0,127.4 while the
 *    live camera sat at 39.99,1.96,131.79. A rest check built on it compares a
 *    stale value with itself and returns immediately, every time.
 *
 * `invariants.waitForCameraRest` reads the LIVE camera and is the right helper
 * for a camera question. The question here is narrower and one step closer to
 * the subject: these censuses read PIXELS, so what has to be still is the
 * frame. Two cheap whole-canvas readings that agree, twice over, and the ease
 * is over by the only definition this file cares about.
 */
async function waitForFrameRest(page: Page): Promise<void> {
  const signature = async (): Promise<string> =>
    page.evaluate(() => {
      const canvas = document.querySelector<HTMLCanvasElement>(
        '[data-testid="viewport"] canvas',
      );
      if (!canvas) return "";
      const probe = document.createElement("canvas");
      probe.width = canvas.width;
      probe.height = canvas.height;
      const ctx = probe.getContext("2d");
      if (!ctx) return "";
      ctx.drawImage(canvas, 0, 0);
      const { data } = ctx.getImageData(0, 0, probe.width, probe.height);
      let drawn = 0;
      let sum = 0;
      for (let i = 0; i < data.length; i += 4) {
        const alpha = data[i + 3] ?? 0;
        if (alpha === 0) continue;
        drawn += 1;
        sum += (data[i] ?? 0) + (data[i + 1] ?? 0) + (data[i + 2] ?? 0) + alpha;
      }
      return `${drawn}:${sum}`;
    });
  let previous = await signature();
  let agreements = 0;
  for (let attempt = 0; attempt < 60; attempt += 1) {
    await waitForFrames(page, 2);
    const now = await signature();
    if (now !== "" && now === previous) {
      agreements += 1;
      if (agreements === 2) return;
    } else {
      agreements = 0;
    }
    previous = now;
  }
  throw new Error(
    `the frame never came to rest (last signature ${previous}) — do NOT ` +
      `sample the drawing buffer on this frame`,
  );
}

/** Park the pointer off the model so no hover state colours the census. */
async function parkPointer(page: Page): Promise<void> {
  await page.mouse.move(8, HEIGHT - 20);
  await waitForFrames(page, 2);
  await waitForFrameRest(page);
}

/**
 * The frame width under test. 1280x800 is the small-laptop floor the design
 * mandate names and the width every audit number was taken at; `CRAFT_WIDTH`
 * re-runs the identical measurements at 1600 for the second half of the
 * before/after pair.
 */
const WIDTH = Number.parseInt(process.env["CRAFT_WIDTH"] ?? "1280", 10);
const HEIGHT = WIDTH >= 1600 ? 1000 : 800;

test.describe("CRAFT wave 1 — the scene reads as CAD", () => {
  test.use({ viewport: { width: WIDTH, height: HEIGHT } });

  test("CRAFT-1: a filleted body keeps its B-rep edges", async ({ page }) => {
    await installSceneProbe(page);

    // THE CONTROL — a sharp plate, whose edges the crease detector already
    // found. Without it the subject's number cannot be read: "line work on the
    // body" means nothing unless a body that was never broken measures the
    // same.
    const sharpId = await seedPlate(page, null);
    await openPart(page, sharpId);
    await parkPointer(page);
    const frame = await canvasFrame(page);
    const box = clearBox(frame);
    const sharp = await interiorLineInk(page, viewportTokens.modelEdge, box);
    await shot(page, "craft1-sharp-plate");

    // THE SUBJECT — the same plate with a 4 mm break on every edge. Every
    // boundary is now TANGENT, which is exactly what a crease detector cannot
    // see.
    const filletId = await seedPlate(page, 4);
    await openPart(page, filletId);
    await parkPointer(page);
    const filleted = await interiorLineInk(page, viewportTokens.modelEdge, box);
    await shot(page, "craft1-filleted-plate");

    console.log(
      `    [CRAFT-1] interior line ink — sharp ${sharp.coverage.toFixed(0)} ` +
        `(${sharp.pixels} px, exact ${sharp.exact}, region ${sharp.region}) · ` +
        `filleted ${filleted.coverage.toFixed(0)} (${filleted.pixels} px, ` +
        `exact ${filleted.exact}, region ${filleted.region})`,
    );

    // The census ran on a real body, not on an empty frame — a coverage of 0
    // over a region of 0 is not a measurement, and it is the shape a broken
    // fixture takes.
    expect(sharp.region).toBeGreaterThan(20_000);
    expect(filleted.region).toBeGreaterThan(20_000);
    // The audit's floor: more than 2 000 px of edge ink on the filleted plate,
    // where it measured zero.
    expect(filleted.pixels).toBeGreaterThan(2000);
    // The control must be non-trivial FIRST. A ratio assertion over two zeroes
    // passes, and that is precisely the shape the original defect had. The
    // sharp plate carries LESS interior line work than the filleted one by
    // topology — 6 faces against 26 — so its floor is its own, not a copy.
    expect(sharp.pixels).toBeGreaterThan(600);
    // The second instrument must agree there is ink. `exact` counts only
    // whole-pixel hits on the literal token, so it is a fraction of the
    // coverage — but it is derived from COLOUR alone where the coverage is
    // derived from local CONTRAST alone, and a defect that fools both is not
    // an anti-aliasing artefact.
    expect(filleted.exact).toBeGreaterThan(300);
    expect(sharp.exact).toBeGreaterThan(100);
    expect(filleted.coverage).toBeGreaterThan(1200);
    // THE ASSERTION THAT WOULD HAVE CAUGHT THE DEFECT: adding a fillet to a
    // body that already had edges must not collapse its line work.
    expect(filleted.pixels).toBeGreaterThan(sharp.pixels * 0.8);
    expect(filleted.coverage).toBeGreaterThan(sharp.coverage * 0.8);
  });

  test("CRAFT-2: the grid survives an axis-aligned orthographic camera", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const partId = await seedPlate(page, 4);
    await openPart(page, partId);
    const frame = await canvasFrame(page);
    const clear = clearBox(frame);
    const viewportEl = page.getByTestId("viewport");

    // THE CONTROL, measured FIRST and before anything has been perturbed: the
    // same camera direction under a perspective projection, where the ground
    // plane shows the receding wedge that makes a front view readable.
    await snapTo(page, "view-front", "front");
    await setProjection(page, "perspective");
    await parkPointer(page);
    const body = await bodyFootprint(page, clear);
    expect(body).not.toBeNull();

    // One box for every reading: the strip below the body's own footprint,
    // clear of its antialiased tail. The audit's front-ortho number (2 396 px)
    // was ENTIRELY that tail, so every census below also asserts that no body
    // pixel is inside its box.
    const floor =
      (body?.bottom ?? 0) + Math.round(BODY_MARGIN_PX * frame.scale);
    const band: CanvasBox = {
      x: clear.x,
      y: floor,
      width: clear.width,
      height: clear.y + clear.height - floor,
    };
    expect(band.height).toBeGreaterThan(60 * frame.scale);
    await shot(page, "craft2-front-perspective");
    const before = await census(page, band);

    // THE SUBJECT. Projection is the only variable.
    await setProjection(page, "orthographic");
    await parkPointer(page);
    if (!BEFORE) {
      // WHICH MECHANISM DREW IT. A pixel count cannot tell a drafting board
      // from a floor, and that is the whole distinction CRAFT-2 turns on, so
      // the census states the scene state it was taken in.
      await expect(viewportEl).toHaveAttribute("data-bench-backdrop", "z-");
    }
    await shot(page, "craft2-front-ortho");
    const ortho = await census(page, band);

    // AND BACK. The sheet belongs to the parallel view and must leave with it
    // — this is a demand-rendered scene, so an unmount that does not ask for a
    // frame leaves the board on screen over a graph that no longer has one.
    await setProjection(page, "perspective");
    await parkPointer(page);
    if (!BEFORE) {
      await expect(viewportEl).toHaveAttribute("data-bench-backdrop", "none");
      expect(await namedWorldBox(page, "bench-backdrop")).toBeNull();
    }
    const after = await census(page, band);

    console.log(
      `    [CRAFT-2] band ${band.width}x${band.height} at y=${band.y} — ` +
        `persp ${before.coverage.toFixed(0)} ` +
        `(drawn ${before.drawn}, lum>32 ${before.auditLuminance}) · ` +
        `ortho ${ortho.coverage.toFixed(0)} ` +
        `(drawn ${ortho.drawn}, lum>32 ${ortho.auditLuminance}) · ` +
        `back to persp ${after.coverage.toFixed(0)} (drawn ${after.drawn})`,
    );

    // No body in the box, in any of the three readings.
    expect(before.body).toBe(0);
    expect(ortho.body).toBe(0);
    expect(after.body).toBe(0);
    // A ratio needs a non-trivial denominator to mean anything.
    expect(before.coverage).toBeGreaterThan(1500);
    // THE AUDIT'S GATE, at the audit's width: the axis-aligned parallel view
    // carries at least half the ink its perspective control does. It measured
    // ZERO. Held to 1280 deliberately, because the ratio is a width-specific
    // number and pretending otherwise would be a gate that fails on correct
    // behaviour: a perspective ground grid compresses toward its horizon, so
    // its density RISES with frame size, while a fixed-pitch parallel grid's
    // falls as the zoom grows. Measured on the same tree, same scene —
    //
    //     1280x800    ortho 2431 / persp 2932   ratio 0.87
    //     1600x1000   ortho 2407 / persp 4930   ratio 0.49
    //
    // — where the ortho FRAME is equally full at both. So the width-blind
    // statement is the DENSITY floor below, and the ratio is asserted where
    // the audit measured it.
    if (WIDTH === 1280) {
      expect(ortho.coverage).toBeGreaterThan(before.coverage * 0.5);
    }
    // THE WIDTH-INDEPENDENT GATE: ink per 1 000 canvas px of the band.
    // Measured 21.2 at 1280 and 13.5 at 1600, against 0.0 before this landed.
    const density = (ortho.coverage / (band.width * band.height)) * 1000;
    console.log(
      `    [CRAFT-2] ortho ink density ${density.toFixed(1)} per 1k px`,
    );
    expect(density).toBeGreaterThan(8);
    // The board does not linger once the view stops being parallel. Note what
    // this can and cannot catch, because a named view SETS the projection
    // (`viewCommands`: "the first named view the modeler asks for switches
    // it"), so the control above is itself taken on the way BACK from a
    // parallel view. A lingering board therefore inflates BOTH readings, and
    // the ratio assertion above is what fires — measured on that mutant, 7 043
    // for a view that has 2 815, against a required 3 521. Which is the safe
    // direction: a stale board can only make the gate harder to pass.
    expect(Math.abs(after.coverage - before.coverage)).toBeLessThan(
      before.coverage * 0.25,
    );
  });

  test("CRAFT-3: the origin triad is drawn at rest and the toggles still promote it", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const partId = await seedPlate(page, 4);
    await openPart(page, partId);
    const frame = await canvasFrame(page);
    const box = clearBox(frame);

    // 1. IN THE GRAPH, at rest, with every ORIGIN row still off. This is the
    //    reading a pixel census cannot give: the resting mark lies ON the
    //    grid's own section lines at world zero, so "there is ink at x = 0" is
    //    ambiguous by construction and "the axis object is drawn, here, this
    //    long" is not.
    for (const axis of ["X", "Y", "Z"] as const) {
      await expect(page.getByTestId(`origin-axis-${axis}`)).toHaveAttribute(
        "aria-pressed",
        "false",
      );
      if (BEFORE) continue; // the triad does not exist yet on that tree
      const drawn = await namedWorldBox(page, `origin-axis-${axis}`);
      expect(drawn, `origin-axis-${axis} at rest`).not.toBeNull();
      expect(drawn?.vertices ?? 0).toBeGreaterThan(0);
    }
    // Each mark runs FROM the origin ALONG its own axis — the scene-frame
    // convention `AXIS_DIRECTION` derives (kernel Z is scene +Y), asserted on
    // the drawn object rather than on the constant it came from.
    const marks = BEFORE
      ? null
      : {
          X: (await namedWorldBox(page, "origin-axis-X")) as WorldBox,
          Y: (await namedWorldBox(page, "origin-axis-Y")) as WorldBox,
          Z: (await namedWorldBox(page, "origin-axis-Z")) as WorldBox,
        };
    const length = marks?.X.max[0] ?? 0;
    if (marks !== null) {
      expect(length).toBeGreaterThan(10);
      expect(marks.X.min).toEqual([0, 0, 0]);
      // FB-21's convention, asserted on the DRAWN objects rather than on the
      // constant they were built from: the glyph labelled Z runs up the SCENE
      // (kernel +Z is scene +Y) and the one labelled Y runs into it.
      expect(marks.Z.max[1]).toBeCloseTo(length, 3);
      expect(marks.Y.min[2]).toBeCloseTo(-length, 3);
    }

    // 2. ON SCREEN, in the view the audit found empty. The census box is the
    //    clear region ABOVE the body's own footprint: `sketch.planeEdge` is
    //    the datum ink and nothing else in a resting part workspace draws in
    //    it, but the studio matcap's cool rim passes through that colour on
    //    the body itself — measured, 738 px of it — so a census that includes
    //    the body counts the body. The grid's two inks are far enough away
    //    (#3E4D61 / #232E3C) that they cannot be confused with it.
    await snapTo(page, "view-front", "front");
    await setProjection(page, "orthographic");
    await parkPointer(page);
    // The resting mark carries no engraved letter — that belongs to the datum.
    await expect(page.getByTestId(/^origin-axis-label-/)).toHaveCount(0);
    const footprint = await bodyFootprint(page, box);
    expect(footprint).not.toBeNull();
    const above: CanvasBox = {
      x: box.x,
      y: box.y,
      width: box.width,
      height:
        (footprint?.top ?? 0) -
        Math.round(BODY_MARGIN_PX * frame.scale) -
        box.y,
    };
    // BELOW the body is where the DATUM's phantom half goes and the resting
    // mark never does: a mark is the POSITIVE half only, so the negative
    // halves running down and left from the origin exist in exactly one of the
    // two states. That makes this box the discriminator, and it is a
    // structural difference rather than a difference of degree.
    const belowTop =
      (footprint?.bottom ?? 0) + Math.round(BODY_MARGIN_PX * frame.scale);
    const below: CanvasBox = {
      x: box.x,
      y: belowTop,
      width: box.width,
      height: box.y + box.height - belowTop,
    };
    expect(above.height).toBeGreaterThan(60 * frame.scale);
    expect(below.height).toBeGreaterThan(60 * frame.scale);
    expect((await census(page, above)).body).toBe(0);
    expect((await census(page, below)).body).toBe(0);
    await shot(page, "craft3-front-ortho-rest");
    const rest = await datumInk(page, above);
    const restBelow = await datumInk(page, below);
    // 3. THE CONTROL THE TICKET NAMES: the ORIGIN rows must still promote the
    //    mark to the full datum, or a default-on triad has broken a control
    //    that already existed.
    for (const axis of ["X", "Y", "Z"] as const) {
      await page.getByTestId(`origin-axis-${axis}`).click();
      await expect(page.getByTestId(`origin-axis-${axis}`)).toHaveAttribute(
        "aria-pressed",
        "true",
      );
    }
    await waitForFrames(page, 3);
    await shot(page, "craft3-front-ortho-enabled");
    const enabledBelow = await datumInk(page, below);
    const datumZ = (await namedWorldBox(page, "origin-axis-Z")) as WorldBox;

    // 4. AND BACK OFF — the rest state is a state, not a one-way door.
    for (const axis of ["X", "Y", "Z"] as const) {
      await page.getByTestId(`origin-axis-${axis}`).click();
    }
    await waitForFrames(page, 3);
    const offBelow = await datumInk(page, below);
    const restoredZ = (await namedWorldBox(page, "origin-axis-Z")) as WorldBox;

    console.log(
      `    [CRAFT-3] datum ink — at rest ${rest.datum} px above the body ` +
        `(grid ${rest.grid}, unclassified ${rest.other}); below the body ` +
        `${restBelow.datum} at rest -> ${enabledBelow.datum} enabled -> ` +
        `${offBelow.datum} off again · Z span ` +
        `${marks?.Z.min[1].toFixed(1)}..${marks?.Z.max[1].toFixed(1)} -> ` +
        `${datumZ.min[1].toFixed(1)}..${datumZ.max[1].toFixed(1)}`,
    );

    // PRESENT AT REST, in the frame that had nothing in it, measured where the
    // body cannot contribute.
    expect(rest.datum).toBeGreaterThan(40);
    // ENABLING IS A VISIBLE PROMOTION, and not by a subtlety: the datum gains
    // the PHANTOM negative half the mark does not have — measured below the
    // body, where a resting triad draws nothing at all — and it gains the
    // engraved letter. An off-state that looked like its on-state would be the
    // defect this ticket warns about.
    // Stated as two absolutes, not as a ratio: the resting reading is ZERO,
    // and `enabled > rest * 3` is vacuously true of zero — the assertion that
    // passes whatever the product does is the one this suite keeps catching.
    // The phantom is DASHED, so 105 px of it is the whole negative half; the
    // floor sits below that and infinitely above the control.
    expect(restBelow.datum).toBeLessThan(20);
    expect(enabledBelow.datum).toBeGreaterThan(60);
    expect(marks?.Z.min[1]).toBeCloseTo(0, 3); // the mark is a HALF axis
    expect(datumZ.min[1]).toBeLessThan(-length * 0.9); // the datum is a whole one

    // AND IT IS REVERSIBLE — back to the mark, not to nothing and not to the
    // datum.
    expect(offBelow.datum).toBeLessThan(20);
    expect(restoredZ.min[1]).toBeCloseTo(0, 3);
  });
});
