/**
 * ORTHO-1 — named views project ORTHOGRAPHICALLY, and there is a toggle.
 *
 * Four product-audit passes reported the same thing (M18, R-11, S-31, T-20):
 * every named view was perspective, so FRONT could not be used for the job
 * people open FRONT to do. A perspective FRONT view is not a mildly worse
 * drawing — it is a WRONG one: parallel edges converge, equal features at
 * different depths measure differently (the audit measured a 25 mm flange wall
 * at ~102 px against ~70 px for the nearer hem), so the view lies about the
 * alignment you opened it to check.
 *
 * WHAT IS ASSERTED, and why it is geometry rather than a flag. A `data-`
 * attribute, a class name, an `aria-pressed` — every one of those can read
 * "orthographic" while the camera keeps projecting exactly as it did, and the
 * suite would go green on a feature that does nothing. So the oracle here is
 * the projection itself, measured through the LIVE camera matrices:
 *
 *   · PARALLEL EDGES ARE PARALLEL ON SCREEN. Four edges of a box that are
 *     parallel in the model, projected in an iso view. Under a parallel
 *     projection the angle between them is zero by definition; under
 *     perspective they converge on a vanishing point. This is the one
 *     assertion that CANNOT pass in a world where the toggle is inert.
 *   · EQUAL EDGES AT DIFFERENT DEPTHS MEASURE EQUAL. The audit's own
 *     measurement, on the front and back top edges of a box in FRONT view.
 *   · THE MODEL IS STILL IN THE FRAME AFTERWARDS. Switching projection changes
 *     what "fit" means, and a view that fits in one can clip in the other.
 *
 * The camera comes from the shared scene probe (`installSceneProbe`), which
 * reads three.js's own devtools seam — so the numbers below are the matrices
 * the GPU was handed, not a re-derivation that could agree with a bug.
 */
import { expect, test, type Page } from "./fixtures";

import { installSceneProbe, namedWorldBox } from "./invariants";
import { createFeature, rectangleSketch } from "./partSeed";
import { createPartViaApi, seedSession, waitForRenders } from "./support";

/**
 * A box with three DIFFERENT edge lengths and real depth: 60 mm across, 45 mm
 * deep, 25 mm tall. The depth matters — it is what perspective magnifies and
 * a parallel projection does not, so a cube would make the two projections
 * harder to tell apart, not easier.
 */
const BOX = { width: 60, depth: 45, height: 25 };

async function seedBoxPart(page: Page): Promise<{ id: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Projection probe");
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: {
      type: "sketch",
      version: 1,
      params: rectangleSketch(0, 0, BOX.width, BOX.depth),
    },
    expected_tree_version: 0,
  });
  await createFeature(page, account.token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: BOX.height,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  return part;
}

/** A point on the canvas, in CSS pixels relative to the canvas's top-left. */
interface ScreenPoint {
  x: number;
  y: number;
}

interface Projected {
  /** The 8 box corners, in the order `cornerIndex` documents. */
  points: ScreenPoint[];
  /** What the camera IS — read off the object, not off the DOM. */
  orthographic: boolean;
  /** The canvas's own page offset, so a spec can click what it measured. */
  canvas: { x: number; y: number; width: number; height: number };
}

/**
 * Project world points through the LIVE scene camera.
 *
 * The camera is picked exactly as `readCameraProbe` picks it — preferring the
 * one whose position matches the viewport's `data-camera-pos` stamp — so this
 * reads the same camera the rest of the suite's invariants do. The maths is
 * the standard `projectionMatrix · matrixWorldInverse · p`, with the perspective
 * divide left in: for an orthographic camera `w` comes out 1 and the divide is
 * the identity, which is precisely the difference under test.
 */
async function projectPoints(
  page: Page,
  world: readonly (readonly [number, number, number])[],
): Promise<Projected> {
  return page.evaluate(
    (points: [number, number, number][]): Projected => {
      interface Cam {
        position: { x: number; y: number; z: number };
        isOrthographicCamera?: boolean;
        projectionMatrix: { elements: number[] };
        matrixWorldInverse: { elements: number[] };
      }
      const w = window as unknown as Record<string, unknown>;
      const order = (w["__loftSceneOrder"] ?? []) as string[];
      const cameras = (w["__loftCameras"] ?? {}) as Record<string, Cam>;
      const container = document.querySelector('[data-testid="viewport"]');
      const stamp = container?.getAttribute("data-camera-pos");
      const stamped = stamp ? stamp.split(",").map(Number) : null;
      const near = (camera: Cam): boolean =>
        stamped !== null &&
        stamped.length === 3 &&
        Math.abs(camera.position.x - (stamped[0] as number)) < 0.2 &&
        Math.abs(camera.position.y - (stamped[1] as number)) < 0.2 &&
        Math.abs(camera.position.z - (stamped[2] as number)) < 0.2;
      let picked: Cam | null = null;
      for (const uuid of order) {
        const camera = cameras[uuid];
        if (camera === undefined) continue;
        if (near(camera)) {
          picked = camera;
          break;
        }
        picked ??= camera;
      }
      const canvasEl = document.querySelector<HTMLCanvasElement>(
        '[data-testid="viewport"] canvas',
      );
      if (picked === null || canvasEl === null) {
        throw new Error("projectPoints: no scene camera or canvas");
      }
      const box = canvasEl.getBoundingClientRect();
      const p = picked.projectionMatrix.elements;
      const v = picked.matrixWorldInverse.elements;
      const at = (m: number[], i: number): number => m[i] as number;
      const projected = points.map(([x, y, z]) => {
        const vx = at(v, 0) * x + at(v, 4) * y + at(v, 8) * z + at(v, 12);
        const vy = at(v, 1) * x + at(v, 5) * y + at(v, 9) * z + at(v, 13);
        const vz = at(v, 2) * x + at(v, 6) * y + at(v, 10) * z + at(v, 14);
        const cx = at(p, 0) * vx + at(p, 4) * vy + at(p, 8) * vz + at(p, 12);
        const cy = at(p, 1) * vx + at(p, 5) * vy + at(p, 9) * vz + at(p, 13);
        const cw = at(p, 3) * vx + at(p, 7) * vy + at(p, 11) * vz + at(p, 15);
        const denominator = cw === 0 ? 1 : cw;
        return {
          x: (cx / denominator / 2 + 0.5) * box.width,
          y: (0.5 - cy / denominator / 2) * box.height,
        };
      });
      return {
        points: projected,
        orthographic: picked.isOrthographicCamera === true,
        canvas: {
          x: box.x,
          y: box.y,
          width: box.width,
          height: box.height,
        },
      };
    },
    world as [number, number, number][],
  );
}

/**
 * The 8 corners of the body's world box, indexed so a bit encodes an axis:
 * bit 0 = +x, bit 1 = +y, bit 2 = +z. An extruded rectangle IS a box, so these
 * are its real vertices and the edges below are its real edges.
 */
async function boxCorners(page: Page): Promise<[number, number, number][]> {
  const box = await namedWorldBox(page, "model-body");
  if (box === null) throw new Error("no model-body in the scene");
  const out: [number, number, number][] = [];
  for (let i = 0; i < 8; i += 1) {
    out.push([
      i & 1 ? box.max[0] : box.min[0],
      i & 2 ? box.max[1] : box.min[1],
      i & 4 ? box.max[2] : box.min[2],
    ]);
  }
  return out;
}

/** The four edges running along world X — parallel in the model, by construction. */
const X_EDGES: [number, number][] = [
  [0, 1],
  [2, 3],
  [4, 5],
  [6, 7],
];

/** Screen direction of an edge, as an angle in degrees. */
function edgeAngle(points: ScreenPoint[], [a, b]: [number, number]): number {
  const p0 = points[a] as ScreenPoint;
  const p1 = points[b] as ScreenPoint;
  return (Math.atan2(p1.y - p0.y, p1.x - p0.x) * 180) / Math.PI;
}

function edgeLength(points: ScreenPoint[], [a, b]: [number, number]): number {
  const p0 = points[a] as ScreenPoint;
  const p1 = points[b] as ScreenPoint;
  return Math.hypot(p1.x - p0.x, p1.y - p0.y);
}

/**
 * The widest disagreement, in degrees, between four screen directions that the
 * model says are parallel. Folded to [0, 90) so an edge drawn in the opposite
 * winding does not read as 180 degrees of error.
 */
function maxParallelError(points: ScreenPoint[]): number {
  const angles = X_EDGES.map((edge) => edgeAngle(points, edge));
  let worst = 0;
  for (let i = 0; i < angles.length; i += 1) {
    for (let j = i + 1; j < angles.length; j += 1) {
      const raw = Math.abs((angles[i] as number) - (angles[j] as number));
      const folded = Math.min(raw % 180, 180 - (raw % 180));
      worst = Math.max(worst, folded);
    }
  }
  return worst;
}

/** Open a seeded part with the scene probe armed, and wait for the body. */
async function openPart(page: Page): Promise<void> {
  await installSceneProbe(page);
  const part = await seedBoxPart(page);
  await page.goto(`/parts/${part.id}`);
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
}

/**
 * Fire a named view and wait for the rig to report it settled. `data-view` is
 * blanked first so the wait cannot be satisfied by the PREVIOUS settle — the
 * assertion-that-was-already-true trap.
 */
async function snapTo(page: Page, testId: string, view: string): Promise<void> {
  const viewport = page.getByTestId("viewport");
  await page.evaluate(() => {
    document
      .querySelector('[data-testid="viewport"]')
      ?.removeAttribute("data-view");
  });
  await page.getByTestId(testId).click();
  await expect(viewport).toHaveAttribute("data-view", view, {
    timeout: 20_000,
  });
  await waitForRenders(page, 3);
}

test.describe("orthographic projection (ORTHO-1)", () => {
  test("a named view draws parallel edges parallel; perspective does not", async ({
    page,
  }) => {
    await openPart(page);
    const viewport = page.getByTestId("viewport");

    // THE CONTROL. Perspective first, at the same iso attitude, so the two
    // numbers below differ by the projection and by nothing else.
    await page.getByTestId("view-iso").click();
    await expect(viewport).toHaveAttribute("data-view", "iso", {
      timeout: 20_000,
    });
    await page.getByTestId("view-projection").click();
    await expect(viewport).toHaveAttribute("data-projection", "perspective", {
      timeout: 10_000,
    });
    await waitForRenders(page, 3);
    const corners = await boxCorners(page);
    const perspective = await projectPoints(page, corners);
    expect(perspective.orthographic).toBe(false);
    const converging = maxParallelError(perspective.points);

    // THE SUBJECT. Back to orthographic through the same control.
    await page.getByTestId("view-projection").click();
    await expect(viewport).toHaveAttribute("data-projection", "orthographic", {
      timeout: 10_000,
    });
    await waitForRenders(page, 3);
    const parallel = await projectPoints(page, corners);
    expect(parallel.orthographic).toBe(true);
    const parallelError = maxParallelError(parallel.points);

    // MEASURED on a 60x45x25 box at 1600x1000: orthographic 0.00000 deg,
    // perspective 15.240 deg. The gap is three orders of magnitude, so the
    // thresholds below are nowhere near either measurement.
    //
    // Parallel projection means EXACTLY parallel. The tolerance is float noise
    // in a 4x4 matrix product, not a fudge for a nearly-right camera.
    expect(
      parallelError,
      `orthographic iso should draw the four X edges parallel (got ${parallelError.toFixed(4)} deg)`,
    ).toBeLessThan(0.05);

    // …and perspective genuinely converges at this attitude, so the assertion
    // above is measuring something. Without this half, a camera stuck in ortho
    // would pass the whole test.
    expect(
      converging,
      `perspective iso should converge (got ${converging.toFixed(3)} deg)`,
    ).toBeGreaterThan(1);
    expect(converging / Math.max(parallelError, 1e-4)).toBeGreaterThan(20);
  });

  test("FRONT measures equal edges equal, whatever their depth", async ({
    page,
  }) => {
    await openPart(page);
    const viewport = page.getByTestId("viewport");
    const corners = await boxCorners(page);

    // The two TOP edges along X (both `+y`): one on the near face (`+z`, the
    // side FRONT looks at), one on the far face. Both are 60 mm in the model
    // and both lie parallel to the image plane, so the ONLY thing that can make
    // them measure differently on screen is the perspective divide — which is
    // the audit's flange-vs-hem measurement, on a shape of known dimensions.
    //
    // NB the corner index is a bit field (see `boxCorners`), and getting it
    // wrong is silent: the first draft of this case picked two edges that
    // happened to share a depth and measured a ratio of 1.0000 under
    // PERSPECTIVE — a green-looking number that proved nothing at all.
    const NEAR: [number, number] = [6, 7];
    const FAR: [number, number] = [2, 3];

    await snapTo(page, "view-front", "front");
    await expect(viewport).toHaveAttribute("data-projection", "orthographic");
    const parallel = await projectPoints(page, corners);
    expect(parallel.orthographic).toBe(true);
    const orthoRatio =
      edgeLength(parallel.points, NEAR) / edgeLength(parallel.points, FAR);

    await page.getByTestId("view-projection").click();
    await expect(viewport).toHaveAttribute("data-projection", "perspective", {
      timeout: 10_000,
    });
    await waitForRenders(page, 3);
    const perspective = await projectPoints(page, corners);
    const perspectiveRatio =
      edgeLength(perspective.points, NEAR) /
      edgeLength(perspective.points, FAR);

    // MEASURED on the same box at 1600x1000. Orthographic: 657.4 px and
    // 657.4 px — one number for one dimension, which is what makes the view
    // readable. Perspective: 832.9 px and 543.0 px for the SAME 60 mm, a ratio
    // of 1.5337. That second pair is the defect in one line.
    expect(
      orthoRatio,
      `orthographic FRONT should measure both 60 mm edges the same (got ${orthoRatio.toFixed(5)})`,
    ).toBeCloseTo(1, 3);
    expect(
      perspectiveRatio,
      `perspective FRONT should magnify the near edge (got ${perspectiveRatio.toFixed(4)})`,
    ).toBeGreaterThan(1.05);
  });

  test("the reference cube lands you in an orthographic view of a face", async ({
    page,
  }) => {
    // The same defect from the other direction (the ticket's words): a cube
    // facet click is the same act as pressing FRONT, by another instrument.
    await openPart(page);
    const viewport = page.getByTestId("viewport");
    // A part opens PERSPECTIVE, so this starts from the state the ticket
    // describes: no click has armed anything, and the cube is about to.
    await expect(viewport).toHaveAttribute("data-projection", "perspective");

    const cube = page.getByTestId("view-cube");
    const rect = await cube.boundingBox();
    expect(rect).not.toBeNull();
    const seat = rect as NonNullable<typeof rect>;
    await page.mouse.click(
      seat.x + seat.width * 0.34,
      seat.y + seat.height * 0.62,
    );

    await expect(viewport).toHaveAttribute("data-view", "direction", {
      timeout: 20_000,
    });
    await expect(viewport).toHaveAttribute("data-projection", "orthographic");
    await waitForRenders(page, 3);
    const corners = await boxCorners(page);
    const projected = await projectPoints(page, corners);
    expect(projected.orthographic).toBe(true);
    expect(maxParallelError(projected.points)).toBeLessThan(0.05);
  });

  test("the model stays inside the framed rect across a projection change", async ({
    page,
  }) => {
    // The framing interaction: a view that fits under one projection can clip
    // under the other, so the invariant is asserted AFTER the swap, not after
    // the fit. `data-fit-rect` is the rect the rig framed into — the
    // unobstructed viewport, not the canvas (`fitFraming.ts`).
    await openPart(page);
    const viewport = page.getByTestId("viewport");
    await snapTo(page, "view-front", "front");
    const corners = await boxCorners(page);

    const raw = await viewport.getAttribute("data-fit-rect");
    const parts = (raw ?? "").split(",").map(Number);
    expect(parts).toHaveLength(4);
    const [rx, ry, rw, rh] = parts as [number, number, number, number];

    for (const expected of ["perspective", "orthographic"] as const) {
      await page.getByTestId("view-projection").click();
      await expect(viewport).toHaveAttribute("data-projection", expected, {
        timeout: 10_000,
      });
      await waitForRenders(page, 3);
      const projected = await projectPoints(page, corners);
      // Containment alone is satisfied by a camera that never changed, so the
      // camera's own class is asserted here too — otherwise this case would sit
      // out the exact regression it is guarding against.
      expect(projected.orthographic).toBe(expected === "orthographic");
      for (const [index, point] of projected.points.entries()) {
        expect(
          point.x,
          `${expected} corner ${index} left of the frame`,
        ).toBeGreaterThanOrEqual(rx);
        expect(
          point.x,
          `${expected} corner ${index} right of the frame`,
        ).toBeLessThanOrEqual(rx + rw);
        expect(
          point.y,
          `${expected} corner ${index} above the frame`,
        ).toBeGreaterThanOrEqual(ry);
        expect(
          point.y,
          `${expected} corner ${index} below the frame`,
        ).toBeLessThanOrEqual(ry + rh);
      }
    }
  });

  test.describe("at the 1280x800 responsive floor", () => {
    test.use({ viewport: { width: 1280, height: 800 } });

    test("the projection cell is where a real mouse can hit it", async ({
      page,
    }) => {
      // `toBeVisible()` is a BOX property and has passed controls shoved out of
      // frame; `force: true` skips the only check that asks whether a user
      // could have clicked. So: resolve `elementFromPoint` at the cell's centre
      // and drive it with a real mouse click.
      await openPart(page);
      const cell = page.getByTestId("view-projection");
      const rect = await cell.boundingBox();
      expect(rect).not.toBeNull();
      const seat = rect as NonNullable<typeof rect>;
      const centre = {
        x: seat.x + seat.width / 2,
        y: seat.y + seat.height / 2,
      };

      expect(seat.x).toBeGreaterThanOrEqual(0);
      expect(seat.y).toBeGreaterThanOrEqual(0);
      expect(seat.x + seat.width).toBeLessThanOrEqual(1280);
      expect(seat.y + seat.height).toBeLessThanOrEqual(800);
      // The 24px target floor (SC 2.5.8) the toolbar primitives promise.
      expect(seat.width).toBeGreaterThanOrEqual(24);
      expect(seat.height).toBeGreaterThanOrEqual(24);

      const owner = await page.evaluate(
        (at: { x: number; y: number }) =>
          document
            .elementFromPoint(at.x, at.y)
            ?.closest("[data-testid]")
            ?.getAttribute("data-testid") ?? null,
        centre,
      );
      expect(
        owner,
        "something else owns the pixels at the projection cell's centre",
      ).toBe("view-projection");

      const viewport = page.getByTestId("viewport");
      await expect(viewport).toHaveAttribute("data-projection", "perspective");
      await page.mouse.click(centre.x, centre.y);
      await expect(viewport).toHaveAttribute(
        "data-projection",
        "orthographic",
        {
          timeout: 10_000,
        },
      );
      // The cell is a readout as well as a control: its state must follow.
      await expect(cell).toHaveAttribute("aria-pressed", "true");
      await expect(cell).toHaveAccessibleName("Projection: orthographic");
    });

    test("the keyboard reaches it too", async ({ page }) => {
      await openPart(page);
      const viewport = page.getByTestId("viewport");
      await page.keyboard.press("5");
      await expect(viewport).toHaveAttribute(
        "data-projection",
        "orthographic",
        {
          timeout: 10_000,
        },
      );
      await page.keyboard.press("5");
      await expect(viewport).toHaveAttribute("data-projection", "perspective", {
        timeout: 10_000,
      });
    });
  });
});
