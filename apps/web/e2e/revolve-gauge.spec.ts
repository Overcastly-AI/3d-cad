/**
 * CRAFT-10 — THE REVOLVE SWEEP GAUGE, AND THE AXIS IT HANGS ON.
 *
 * Three claims, and every one of them is a claim a screenshot cannot settle:
 *
 *  1. **The axis is drawn.** Before this item it was not — the user chose the
 *     single most consequential property of a turned part from a dropdown
 *     reading "Z axis · through the origin" and the scene showed nothing. This
 *     is asserted as a PIXEL CENSUS along the axis's own projected run, before
 *     the gauge is armed, because "the mesh exists in the scene graph" is the
 *     assertion that has already let a ladder ship invisible in this repo.
 *
 *  2. **The drag moves the MODEL, not just the number.** The direction pass is
 *     blunt about this: *"a gauge whose drag changes a number and not the model
 *     is worse than the form it replaces — it promises direct manipulation and
 *     delivers a slider."* So the drag case reads the sweep preview's own
 *     vertex buffer before and after, which is the only way to tell a redraw
 *     from a camera nudge.
 *
 *  3. **The instrument stays where you left it.** CONTRACT beta. The gauge
 *     draws its own last ask until the pointer is released and then falls back
 *     to the `value` prop, so if the editor does not echo the override the arc
 *     springs back the instant you let go — AFTER every screenshot anyone would
 *     take, which is exactly why it needs a case rather than an eye.
 *
 * **There is no `force: true` in this file and there must never be.** Every
 * pick here is a real `page.mouse` press at a point `elementFromPoint` has been
 * asked about, because this repo has measured that flag hiding a zero-area
 * target four separate times.
 */
import { expect, test, type Page } from "./fixtures";
import {
  gripCentre,
  projectedTrack,
  reachAlongTrack,
  REACH_FLOOR,
  REACH_SAMPLES,
  type Point,
} from "./gaugeProbe";
import { installSceneProbe, waitForCameraRest } from "./invariants";
import {
  countTokenPixels,
  createPartViaApi,
  SCREENSHOT_DIR,
  seedSession,
  waitForFrames,
} from "./support";

/** The working brass — `viewport.manipulator.axis`, one palette, two renderers. */
const BRASS = "#C8A567";

/** Profile: a 20 x 10 mm section on XZ, 20 mm clear of the Z axis. */
const NEAR_MM = 20;
const FAR_MM = 40;
const BOTTOM_MM = 5;
const TOP_MM = 15;

/**
 * Build a plane-mm -> screen-px mapper by reading the DRO at two points with
 * snap off, so the clicks afterwards land on exact millimetres. (Four specs
 * carry this calibrator; the sketcher has no seam that would let one own it.)
 */
async function calibratePlane(
  page: Page,
  s1: Point,
  s2: Point,
): Promise<(pt: Point) => Point> {
  await page.keyboard.press("g");
  let last: number | null = null;
  await expect
    .poll(
      async () => {
        await page.mouse.move(s1.x + 2, s1.y);
        await page.mouse.move(s1.x, s1.y);
        const value = Number.parseFloat(
          await page.getByTestId("dro-x").innerText(),
        );
        const stable =
          last !== null && Number.isFinite(value) && value === last;
        last = value;
        return stable;
      },
      { timeout: 15_000 },
    )
    .toBe(true);
  const read = async (
    sx: number,
    sy: number,
    distinctFromX?: number,
  ): Promise<Point> => {
    await page.mouse.move(sx, sy);
    await expect
      .poll(async () => {
        const value = Number.parseFloat(
          await page.getByTestId("dro-x").innerText(),
        );
        return (
          Number.isFinite(value) &&
          (distinctFromX === undefined ||
            Math.abs(value - distinctFromX) > 1e-9)
        );
      })
      .toBe(true);
    return {
      x: Number.parseFloat(await page.getByTestId("dro-x").innerText()),
      y: Number.parseFloat(await page.getByTestId("dro-y").innerText()),
    };
  };
  const p1 = await read(s1.x, s1.y);
  const p2 = await read(s2.x, s2.y, p1.x);
  await page.keyboard.press("g");
  const kx = (s2.x - s1.x) / (p2.x - p1.x);
  const ky = (s2.y - s1.y) / (p2.y - p1.y);
  return (pt) => ({
    x: s1.x + (pt.x - p1.x) * kx,
    y: s1.y + (pt.y - p1.y) * ky,
  });
}

/** Draw the washer's section on XZ and save it — every step real browser input. */
async function drawSectionOnXZ(page: Page): Promise<void> {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XZ").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XZ");
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
  const at = await calibratePlane(page, { x: 560, y: 520 }, { x: 840, y: 360 });
  const click = async (pt: Point) => {
    const px = at(pt);
    await page.mouse.click(px.x, px.y);
  };
  await page.keyboard.press("r");
  await click({ x: NEAR_MM, y: BOTTOM_MM });
  await click({ x: FAR_MM, y: TOP_MM });
  await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
  await page.keyboard.press("Escape");
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
    timeout: 30_000,
  });
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
}

/** Draw the section, then open the revolve editor on it, framed in iso. */
async function openRevolve(page: Page): Promise<void> {
  await drawSectionOnXZ(page);
  const action = page.getByTestId("new-revolve");
  await expect(action).toBeEnabled({ timeout: 30_000 });
  await action.click();
  await expect(page.getByTestId("revolve-editor")).toBeVisible();
  // Iso: the post-sketch camera looks straight down the sketch normal, and an
  // arc seen edge-on has no readable direction on screen — which is the case
  // the gauge's own screen-travel fallback exists for, not the case to probe
  // reachability in.
  await page.getByTestId("view-iso").click();
  await waitForCameraRest(page);
}

/** Every world-space vertex of a NAMED `lineSegments`, via the scene probe. */
async function namedLinePoints(
  page: Page,
  name: string,
): Promise<[number, number, number][]> {
  return page.evaluate((wanted: string) => {
    interface Attr {
      array: ArrayLike<number>;
      count: number;
    }
    interface Obj3D {
      name: string;
      geometry?: { attributes?: { position?: Attr } };
      traverse: (fn: (child: Obj3D) => void) => void;
    }
    const w = window as unknown as Record<string, unknown>;
    const scenes = (w["__loftScenes"] ?? {}) as Record<string, Obj3D>;
    const order = (w["__loftSceneOrder"] ?? []) as string[];
    const out: [number, number, number][] = [];
    for (const uuid of order) {
      const scene = scenes[uuid];
      if (scene === undefined) continue;
      scene.traverse((node) => {
        if (node.name !== wanted) return;
        node.traverse((child) => {
          const attr = child.geometry?.attributes?.position;
          if (attr === undefined) return;
          for (let i = 0; i < attr.count; i += 1) {
            out.push([
              attr.array[i * 3] as number,
              attr.array[i * 3 + 1] as number,
              attr.array[i * 3 + 2] as number,
            ]);
          }
        });
      });
      if (out.length > 0) return out;
    }
    return out;
  }, name);
}

/** Project a world point to page pixels through the live camera. */
async function projectAll(
  page: Page,
  points: readonly [number, number, number][],
): Promise<Point[]> {
  return page.evaluate(
    (pts: [number, number, number][]) => {
      interface Mat {
        elements: number[];
      }
      interface Cam {
        matrixWorldInverse: Mat;
        projectionMatrix: Mat;
      }
      const w = window as unknown as Record<string, unknown>;
      const cameras = (w["__loftCameras"] ?? {}) as Record<string, Cam>;
      const order = (w["__loftSceneOrder"] ?? []) as string[];
      const canvas = document.querySelector<HTMLCanvasElement>(
        '[data-testid="viewport"] canvas',
      );
      if (canvas === null) return [];
      const rect = canvas.getBoundingClientRect();
      const apply = (
        m: number[],
        x: number,
        y: number,
        z: number,
        h: number,
      ): [number, number, number, number] => [
        (m[0] as number) * x +
          (m[4] as number) * y +
          (m[8] as number) * z +
          (m[12] as number) * h,
        (m[1] as number) * x +
          (m[5] as number) * y +
          (m[9] as number) * z +
          (m[13] as number) * h,
        (m[2] as number) * x +
          (m[6] as number) * y +
          (m[10] as number) * z +
          (m[14] as number) * h,
        (m[3] as number) * x +
          (m[7] as number) * y +
          (m[11] as number) * z +
          (m[15] as number) * h,
      ];
      for (const uuid of order) {
        const camera = cameras[uuid];
        if (camera === undefined) continue;
        return pts.map((p) => {
          const view = apply(
            camera.matrixWorldInverse.elements,
            p[0],
            p[1],
            p[2],
            1,
          );
          const clip = apply(
            camera.projectionMatrix.elements,
            view[0],
            view[1],
            view[2],
            view[3],
          );
          return {
            x: rect.left + ((clip[0] / clip[3] + 1) / 2) * rect.width,
            y: rect.top + ((1 - clip[1] / clip[3]) / 2) * rect.height,
          };
        });
      }
      return [];
    },
    points as [number, number, number][],
  );
}

/** The field's current number. */
async function angleField(page: Page): Promise<number> {
  return Number.parseFloat(
    await page.getByTestId("revolve-angle").inputValue(),
  );
}

/** A coarse fingerprint of the sweep preview's drawn geometry. */
async function previewFingerprint(page: Page): Promise<string> {
  const pts = await namedLinePoints(page, "revolve-sweep-preview");
  if (pts.length === 0) return "empty";
  let sx = 0;
  let sy = 0;
  let sz = 0;
  for (const p of pts) {
    sx += p[0];
    sy += p[1];
    sz += p[2];
  }
  const n = pts.length;
  return `${n}:${(sx / n).toFixed(3)},${(sy / n).toFixed(3)},${(sz / n).toFixed(3)}`;
}

/**
 * The preview's fingerprint once it has stopped moving.
 *
 * STATED, not inherited from timing. The angle reaches the DOM before it
 * reaches the scene — the editor projects the form in an effect, `PartPage`
 * takes it as state, and only then does the sweep's vertex buffer rebuild — so
 * a canvas-side read taken at the moment the FIELD settles can catch the
 * previous frame's geometry. Measured: `29.813,10.000,-2.900` on the first read
 * and `29.953,10.000,-1.453` a beat later, with the field identical across
 * both. Waiting a fixed number of frames would be the accidental settle this
 * repo has already been bitten by; two agreeing reads is the property actually
 * wanted.
 */
async function settledFingerprint(page: Page): Promise<string> {
  let previous = await previewFingerprint(page);
  await expect
    .poll(
      async () => {
        const current = await previewFingerprint(page);
        const agreed = current === previous;
        previous = current;
        return agreed;
      },
      { timeout: 15_000 },
    )
    .toBe(true);
  return previous;
}

test.describe("CRAFT-10 — the revolve sweep gauge", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("the axis is drawn in the viewport before the gauge is armed", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Washer");
    await installSceneProbe(page);
    await page.goto(`/parts/${part.id}`);
    await openRevolve(page);
    await waitForFrames(page, 3);

    // THE CLAIM: brass ink lies along the axis's own projected run. Asserted as
    // a pixel census rather than as "the mesh is in the scene", because this
    // repo has already shipped a ladder that was present in the scene graph,
    // correctly sized by its own rule, and invisible.
    const world = await namedLinePoints(page, "revolve-axis-line");
    expect(world.length).toBeGreaterThan(6);
    const drawn = await projectAll(page, world);
    const xs = drawn.map((p) => p.x);
    const ys = drawn.map((p) => p.y);
    // `.first()`: the ViewCube renders its own 108 px canvas inside the same
    // viewport, and `countTokenPixels` samples the FIRST one — so this must
    // measure the same element, or the box would be in another canvas's frame.
    const canvas = await page
      .getByTestId("viewport")
      .locator("canvas")
      .first()
      .boundingBox();
    if (canvas === null) throw new Error("no canvas");
    const box = {
      x: Math.max(0, Math.round(Math.min(...xs) - canvas.x) - 6),
      y: Math.max(0, Math.round(Math.min(...ys) - canvas.y) - 6),
      width: Math.round(Math.max(...xs) - Math.min(...xs)) + 12,
      height: Math.round(Math.max(...ys) - Math.min(...ys)) + 12,
    };
    const brass = await countTokenPixels(page, BRASS, 26, box);
    expect(brass).toBeGreaterThan(40);

    // NEGATIVE CONTROL, and it is the assertion that makes the census mean
    // something: the same census in a band of empty scene the axis does NOT
    // cross must be essentially bare. Without it, "there is brass in this box"
    // is satisfied by the gauge, the tag's leader, or a warm-lit body face.
    const away = {
      x: 8,
      y: 8,
      width: Math.max(8, box.x - 24),
      height: 120,
    };
    const control = await countTokenPixels(page, BRASS, 26, away);
    expect(control).toBeLessThan(brass / 4);
  });

  test("dragging the grip moves the field AND redraws the preview", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Washer");
    await installSceneProbe(page);
    await page.goto(`/parts/${part.id}`);
    await openRevolve(page);

    // Start from a partial turn: a 360-degree sweep has nowhere further to go
    // and its arc closes on itself, so it is the one value that cannot show a
    // drag moving anything.
    const field = page.getByTestId("revolve-angle");
    await field.fill("120");
    await field.blur();
    await waitForFrames(page, 3);

    const before = await angleField(page);
    const beforePreview = await settledFingerprint(page);
    expect(beforePreview).not.toBe("empty");

    const grip = await gripCentre(page, "revolve-angle");
    // A REAL press, at the grip's own centre, with no `force`.
    await page.mouse.move(grip.x, grip.y);
    await page.mouse.down();
    await page.mouse.move(grip.x + 60, grip.y + 30, { steps: 12 });
    await page.mouse.move(grip.x + 120, grip.y + 60, { steps: 12 });
    await page.mouse.up();
    await waitForFrames(page, 3);

    const after = await angleField(page);
    const afterPreview = await settledFingerprint(page);

    // (1) the number moved…
    expect(Number.isFinite(after)).toBe(true);
    expect(Math.abs(after - before)).toBeGreaterThan(1);
    // (2) …and so did the MODEL. This is the assertion that separates a gauge
    // from a slider, and nothing else in the suite can make it: a pixel diff
    // cannot tell a redraw from a camera nudge, and the field is the thing
    // already known to have changed.
    expect(afterPreview).not.toBe(beforePreview);
    expect(afterPreview).not.toBe("empty");

    // (3) CONTRACT beta — the instrument STAYS where the drag left it. The
    // gauge draws its own last ask until pointerup and then falls back to its
    // `value` prop, so a missing echo springs BOTH the field and the arc back
    // to where the gesture started. Asserted against the PRE-DRAG state rather
    // than against the instant of release: "did it spring back" is a question
    // about the starting value, and comparing two post-release samples would
    // instead be asserting the absence of a transient.
    await waitForFrames(page, 6);
    expect(await angleField(page)).toBeCloseTo(after, 6);
    expect(await settledFingerprint(page)).not.toBe(beforePreview);
    const restGrip = await gripCentre(page, "revolve-angle");
    expect(
      Math.hypot(restGrip.x - grip.x, restGrip.y - grip.y),
    ).toBeGreaterThan(8);
  });

  test("arrow keys step the angle on the same grid the ladder draws", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Washer");
    await installSceneProbe(page);
    await page.goto(`/parts/${part.id}`);
    await openRevolve(page);

    const field = page.getByTestId("revolve-angle");
    await field.fill("120");
    await field.blur();
    await waitForFrames(page, 2);

    const grip = page.getByTestId("revolve-angle-handle");
    await grip.focus();
    await expect(grip).toBeFocused();

    await grip.press("ArrowUp");
    await expect
      .poll(() => angleField(page), { timeout: 10_000 })
      .toBeCloseTo(121, 6);
    await grip.press("ArrowDown");
    await expect
      .poll(() => angleField(page), { timeout: 10_000 })
      .toBeCloseTo(120, 6);
    // Coarse takes ten, landing on its own grid.
    await grip.press("Shift+ArrowUp");
    await expect
      .poll(() => angleField(page), { timeout: 10_000 })
      .toBeCloseTo(130, 6);

    // THE SPOKEN STEP IS THE APPLIED STEP. `data-step` is what the
    // `aria-describedby` sentence is built from, so a drift between them is a
    // lie told only to a screen-reader user.
    await expect(grip).toHaveAttribute("data-step", "1");
    await expect(grip).toHaveAttribute("data-coarse-step", "10");
    await expect(page.getByTestId("revolve-angle-steps")).toContainText("1");

    // THE LADDER IS THE ANGULAR ONE — 15 and 5, never a decade. `data-snap`
    // carries what a drag will actually snap to, so the claim "the rungs ARE
    // the stops" is checkable rather than merely stated.
    const snap = await grip.getAttribute("data-snap");
    expect(snap).not.toBeNull();
    expect([1, 5, 10, 15, 30, 45, 90]).toContain(Number(snap));
    expect([20, 50]).not.toContain(Number(snap));
  });

  /**
   * THE SLEEVE FOLLOWS THE ARC, NOT ITS CHORD — and this case used to be a
   * `test.fail()` saying it did not.
   *
   * CRAFT-10 measured the gap and wrote the fix without committing it, the file
   * being another item's territory at the time: `<ParametricGauge>` laid ONE
   * straight DOM band from the arrowhead's apex back to `spine[0]`, which is
   * exact for a straight track — a two-point spine's chord is itself — and
   * wrong for an arc by the quantity the shell's own chord defect was wrong by,
   * 5.86 world units at radius 20 over a 90-degree sweep, 29 % of the radius.
   * A census along the DRAWN track found the shipped band under 1 of 16 sample
   * points: worse than the 2 of 16 CRAFT-7 was raised to fix, because a chord
   * across a wide sweep leaves the arc almost everywhere.
   *
   * The annotation retired itself exactly as it promised: the sleeve is now one
   * band per projected spine segment, this case passes, and the modifier — which
   * Playwright would now report as an unexpected pass, i.e. a red shard — is
   * gone with the defect. The floor stands where it always did; it was never
   * lowered to bless the gap.
   */
  test("the drawn arc can be grabbed along its length, not only at its point", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Washer");
    await installSceneProbe(page);
    await page.goto(`/parts/${part.id}`);
    await openRevolve(page);

    const field = page.getByTestId("revolve-angle");
    await field.fill("120");
    await field.blur();
    await waitForFrames(page, 3);

    // Arm the instrument the way a user does — the pointer on it — so the
    // sleeve is measured in the state it is used in.
    const grip = await gripCentre(page, "revolve-angle");
    await page.mouse.move(grip.x, grip.y);
    await waitForFrames(page, 2);

    const walked = await reachAlongTrack(page, "revolve-angle");
    console.log(
      `[CRAFT-10] arc reach ${walked.hits}/${REACH_SAMPLES}: ${walked.resolved.join(",")}`,
    );
    expect(walked.hits).toBeGreaterThanOrEqual(REACH_FLOOR);

    // …and the reachable band is a CONTROL, not merely an element: pressing at
    // a sample the probe called "gauge" must actually drive the value.
    const index = walked.resolved.findIndex((r) => r === "gauge");
    expect(index).toBeGreaterThanOrEqual(0);
    const at = walked.points[index] as Point;
    const before = await angleField(page);
    await page.mouse.move(at.x, at.y);
    await page.mouse.down();
    await page.mouse.move(at.x + 70, at.y + 35, { steps: 10 });
    await page.mouse.up();
    await waitForFrames(page, 3);
    expect(Math.abs((await angleField(page)) - before)).toBeGreaterThan(0.5);
  });

  /**
   * THE GESTURE OUTLIVES THE BAND IT WAS TAKEN ON — the arc's P0.
   *
   * The hit sleeve is one DOM band per projected spine segment, and the NUMBER
   * of those segments is a function of the value being dragged: an angular
   * track lays `ceil(|value| / 360 * 96)` of them, so a sweep carries 32 bands
   * at 120 degrees and 24 at 90. The list is keyed by index, so shrinking the
   * sweep unmounts the high-index bands — the ones at the SEAT, which is the
   * half of the arc `894c6f3` exists to make grabbable. Capture taken on the
   * band you grabbed therefore dies the moment the arc re-tessellates past it,
   * and in Chromium a REMOVED capture host emits no `lostpointercapture` at
   * all: there is not even an event to recover on.
   *
   * ## Why this case and not the one that was already here
   *
   * The only other arc-drag case asserts `|after - before| > 0.5` degrees. That
   * is satisfied by the FIRST pointermove, before any band can unmount, so it
   * is green against a gauge that dies one move later — another assertion that
   * cannot observe its own failure mode. This one watches the value at four
   * points ACROSS the re-tessellation and then asks the two questions a frozen
   * gesture answers wrongly: did the release land, and does the value now
   * follow a mouse with no button on it.
   *
   * Measured against the tree before the fix, on the stack this spec runs on:
   * the value froze at **90** for the last three waypoints, `data-grabbed` read
   * **"true"** after `mouse.up`, and moving the bare mouse afterwards carried it
   * from **90 to 165**. All four assertions below fail there, in that order.
   *
   * ## Why the drag looks like this
   *
   * A real one. Press the drawn arc near its seat, pull wide — the first
   * waypoint drops the sweep past the grabbed band's index and the rest of the
   * gesture happens off the instrument, which is where a drag normally is.
   * Every waypoint is asserted to be off every band, because "the value kept
   * tracking" is only a claim about capture if nothing under the pointer could
   * have been listening.
   */
  test("the arc drag survives the sweep re-tessellating under the pointer", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Washer");
    await installSceneProbe(page);
    await page.goto(`/parts/${part.id}`);
    await openRevolve(page);

    const field = page.getByTestId("revolve-angle");
    const grip = page.getByTestId("revolve-angle-handle");
    await field.fill("120");
    await field.blur();
    await waitForFrames(page, 3);

    /** What `elementFromPoint` finds at a pixel: this gauge's band id, or null. */
    const bandAt = async (at: Point): Promise<string | null> =>
      page.evaluate(
        (p: Point) =>
          document
            .elementFromPoint(p.x, p.y)
            ?.closest('[data-gauge="revolve-angle"]')
            ?.getAttribute("data-testid") ?? null,
        at,
      );

    // A press point on the DRAWN arc near the seat — sampled off the projected
    // polyline rather than guessed, so it is on the instrument the eye sees.
    const track = await projectedTrack(page, "revolve-angle", 17);
    const grab = track[3] as Point;
    await page.mouse.move(grab.x, grab.y);
    await waitForFrames(page, 2);
    const held = await bandAt(grab);
    expect(
      held,
      "the press point must be on a hit band, or this case proves nothing",
    ).not.toBeNull();
    const bands = page.locator(
      '[data-gauge="revolve-angle"][data-testid*="sleeve"]',
    );
    const bandsBefore = await bands.count();
    expect(bandsBefore).toBeGreaterThan(8);

    // Waypoints, relative to the press: the first shrinks the sweep far enough
    // to drop the grabbed band, the rest swing back out. All three are clear of
    // the instrument.
    // MEASURED, not guessed: with capture held throughout, these three pixels
    // read 90 / 165 / 225 degrees and 24 / 44 / 60 bands, and `elementFromPoint`
    // finds no band at any of them. The first is the only quadrant that shrinks
    // the sweep rather than running it past the zero ray into the 360 clamp —
    // which is why this is a measured triple and not an arbitrary flourish.
    const away: Point[] = [
      { x: grab.x + 240, y: grab.y + 80 },
      { x: grab.x + 140, y: grab.y - 80 },
      { x: grab.x - 140, y: grab.y - 80 },
    ];

    await page.mouse.down();
    const seen: number[] = [];
    for (const [i, point] of away.entries()) {
      await page.mouse.move(point.x, point.y, { steps: 6 });
      expect(
        await bandAt(point),
        `waypoint ${point.x},${point.y} must be clear of every band`,
      ).toBeNull();
      seen.push(await angleField(page));
      if (i === 0) {
        // THE PRECONDITION, asserted rather than assumed, AND ASSERTED HERE —
        // at the one moment both trees agree on. The first waypoint is still
        // delivered whatever the capture host is, so the sweep has shrunk and
        // the grabbed band is gone in BOTH; from the second waypoint on the two
        // diverge, and a fixed gauge has grown its bands back, which would make
        // this check fail for the opposite reason if it were left to the end.
        // Without it the case could pass because nothing re-tessellated — a
        // gate that cannot reach its own defect, which this file documents
        // twice already.
        await expect(
          page.locator(`[data-testid="${held ?? ""}"]`),
          `${held} must have unmounted on the first waypoint — that is the ` +
            `defect's mechanism, and this case is vacuous without it`,
        ).toHaveCount(0);
      }
    }

    // THE DRAG KEEPS TRACKING. The first waypoint is what kills the band; the
    // second is the one a lost capture can no longer see.
    const [first, second] = seen as [number, number, number];
    console.log(
      `[ARCDRAG] held=${held} bands ${bandsBefore} -> ${await bands.count()}, ` +
        `value ${seen.map((v) => v.toFixed(1)).join(" -> ")}`,
    );
    expect(
      Math.abs(second - first),
      `the value must follow the pointer after the arc re-tessellated ` +
        `(waypoints read ${seen.join(", ")})`,
    ).toBeGreaterThan(20);

    // THE RELEASE LANDS, off-band. A `pointerup` that reaches nobody leaves the
    // grab record set and the ask-queue held, which is invisible until the next
    // pointer move — hence the third assertion.
    await page.mouse.up();
    await waitForFrames(page, 2);
    await expect(grip).toHaveAttribute("data-grabbed", "false");

    // AND THE VALUE DOES NOT FOLLOW AN UNPRESSED MOUSE. Walk the bare pointer
    // back across the instrument, which is exactly where a stuck gesture keeps
    // authoring from.
    const settled = await angleField(page);
    const after = await projectedTrack(page, "revolve-angle", 9);
    await page.mouse.move((after[3] as Point).x, (after[3] as Point).y);
    await page.mouse.move((after[6] as Point).x, (after[6] as Point).y, {
      steps: 6,
    });
    await waitForFrames(page, 2);
    expect(
      await angleField(page),
      "with no button held the gauge is a readout, not a control",
    ).toBeCloseTo(settled, 6);
  });

  /**
   * The founder capture, and it is a GATE rather than a courtesy: a screenshot
   * is the only check we own that asks "is this legible?" rather than "is this
   * present and correctly computed", and an arc's graduations crowd near the
   * ends of a foreshortened sweep in a way no assertion here would notice.
   *
   * `CRAFT10_SHOT` names the side of the pair. It exists because the BEFORE of
   * this change is the same flow against a tree with the gauge removed, so the
   * two shots must come from one spec or they are not comparable — a second
   * spec would differ in camera, angle and timing, and the difference would
   * read as the change.
   */
  test("founder capture — the axis, the arc and the swept preview", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Washer");
    await installSceneProbe(page);
    await page.goto(`/parts/${part.id}`);
    await openRevolve(page);
    const field = page.getByTestId("revolve-angle");
    await field.fill("135");
    await field.blur();
    const side = process.env["CRAFT10_SHOT"] ?? "after";
    if (side === "after") {
      // Arm the ladder: it is drawn only once the instrument is addressed,
      // which is the state the shot needs to show.
      const grip = await gripCentre(page, "revolve-angle");
      await page.mouse.move(grip.x, grip.y);
    }
    await waitForFrames(page, 6);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/craft10-revolve-gauge-${side}-1280.png`,
    });
  });
});
