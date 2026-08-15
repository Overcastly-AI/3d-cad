import { expect, test, type Page } from "./fixtures";

import { angleBetween, cameraPose, installSceneProbe } from "./invariants";
import { createPartViaApi, seedSession } from "./support";

/**
 * VP-1 — orbit while sketching. Founder report: *"cannot orbit the 3D camera
 * while actively drawing a sketch."*
 *
 * The sketcher draws with a left press-drag-release and three.js binds orbit to
 * the left button, so the app resolved the conflict by switching orbit OFF for
 * the duration (`enableRotate={false}`). Fusion 360 never binds orbit to the
 * drawing button in the first place, so orbit is always available there. The
 * fix moves the gesture instead of deleting it: while drawing, LEFT is unbound
 * from the orbit rig, ROTATE takes the MIDDLE button, and RIGHT stays PAN.
 * MIDDLE was DOLLY, which the wheel already does, so nothing is lost.
 *
 * VP-1a — and then on a TRACKPAD, which is what the founder uses, there is no
 * middle button, so the complaint stood. Alt(Option)+left-drag is the second
 * path: the button map is re-derived from the `altKey` the press itself carries
 * (Viewport's `onPointerDownCapture`), so LEFT rotates for exactly that press
 * and the sketcher ignores the same event. The map is DERIVED and not tracked,
 * which is a property with a test: an Alt-orbit must not leave LEFT orbiting
 * for the plain drag that follows it.
 *
 * Driven in a real browser against the real stack. The camera is read from the
 * live three.js camera (`installSceneProbe`), NOT from `data-camera-pos`: that
 * attribute is stamped only when the programmatic rig settles a view, so it
 * does not move for a mouse gesture at all and an assertion on it would be
 * green no matter what the buttons did.
 */

/** The sketch plane the specs use, and its scene mapping. See {@link planeAt}. */
const PLANE = "XY" as const;

interface StoredPoint {
  x: number;
  y: number;
}
interface StoredEntity {
  id: string;
  kind: string;
  start?: StoredPoint;
  end?: StoredPoint;
}

/**
 * The sketch feature's PERSISTED entities, read back from the gateway after the
 * sketch is saved — plane (u,v) as the document actually stores it, not as a
 * readout renders it.
 */
async function persistedEntities(
  page: Page,
  partId: string,
  token: string,
): Promise<StoredEntity[]> {
  const response = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.status(), "feature tree fetched").toBe(200);
  const body = (await response.json()) as {
    features: Array<{ feature: { params: { entities?: StoredEntity[] } } }>;
  };
  return body.features[0]?.feature.params.entities ?? [];
}

/** Open a fresh part, enter the sketcher on XY, and land in DRAW mode. */
async function enterDrawOnXy(
  page: Page,
  name: string,
): Promise<{ partId: string; token: string }> {
  // Before `goto`: the probe hooks three.js at Scene construction.
  await installSceneProbe(page);
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, name);
  await page.goto(`/parts/${part.id}`);
  await page.getByTestId("new-sketch").click();
  await page.getByTestId(`plane-${PLANE}`).click();
  await expect(page.getByTestId("sketch-step")).toHaveText(`On ${PLANE}`);
  // The DRO is up once the sheet is live and the sketch camera has been asked
  // for its normal-on pose; `restCamera` then waits for the ease to finish.
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
  return { partId: part.id, token };
}

async function armRect(page: Page): Promise<void> {
  await page.keyboard.press("r");
  await expect(page.getByTestId("tool-rect")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
}

type Button = "left" | "middle" | "right";

/** Press, travel in steps, release — the gesture a hand actually makes. */
async function drag(
  page: Page,
  button: Button,
  from: { x: number; y: number },
  dx: number,
  dy: number,
): Promise<void> {
  await page.mouse.move(from.x, from.y);
  await page.mouse.down({ button });
  await page.mouse.move(from.x + dx / 2, from.y + dy / 2, { steps: 6 });
  await page.mouse.move(from.x + dx, from.y + dy, { steps: 6 });
  await page.mouse.up({ button });
}

interface Rest {
  direction: [number, number, number];
  position: [number, number, number];
}

/** How still is still: the largest change tolerated between two samples. */
interface Stillness {
  mm: number;
  deg: number;
}

/**
 * Rest tight enough for the RAYCAST test, whose projection maths is only as
 * good as the camera standing still.
 *
 * Derived from what that test's strictest assertion tolerates: entity ends are
 * compared within 2 screen px, which at the orbit radius here is ~0.25 mm of
 * plane travel, so residual drift is held five times tighter than the thing it
 * could corrupt. (It was 0.02 mm, which no run ever reached inside the old 15 s
 * deadline — the test was red on an idle box before this spec had ever been
 * executed. Two samples at the moment of that timeout were 0.041 mm apart and
 * shrinking: the camera was fine, the predicate was asking for stillness no
 * assertion needed.)
 */
const REST_EXACT: Stillness = { mm: 0.05, deg: 0.05 };

/**
 * Rest for the tests that only ask "did the view TURN, or not?".
 *
 * Damping decays the orbit velocity per FRAME, not per second, so the tail of a
 * coast is unbounded in wall-clock terms on a `frameloop="demand"` scene under
 * software GL: with three Playwright suites sharing this box (load average 16)
 * the coast had NOT reached 0.05 mm after 30 s of polling, and five of seven
 * tests here failed on the wait rather than on an assertion. Exact rest is
 * therefore not something a contended runner can be asked for.
 *
 * These assertions do not need it. They separate ~72 deg from ~0 deg with a
 * 10 deg threshold, and a coasting sample can only understate the turn (the
 * coast continues in the direction of the drag), so a loose sample can fail
 * this class of assertion but never pass it falsely.
 *
 * THE ARGUMENT IS DIRECTIONAL, SO READ IT BEFORE REACHING FOR THIS. It licenses
 * a loose sample only where an unsettled camera moves the measurement TOWARDS
 * failure. That holds at every site below: the orbit tests bound the turn from
 * BELOW while the coast is still adding to it; the pan test bounds the travel
 * from below while the coast is still adding to that; and the "plain drag did
 * not orbit" test bounds the change from ABOVE, where a coast can only inflate
 * what it measures. It does NOT hold where the rig is easing the camera back
 * toward the reference direction — there an unsettled sample OVERSTATES the
 * angle, and a lower bound on that angle could pass for the reason it is meant
 * to catch. The one assertion of that shape in this file (step 3 of the raycast
 * test, "the camera stayed orbited across the draw") therefore takes
 * {@link REST_EXACT}, which costs it nothing: the gesture before it is a DRAW,
 * so there is no orbit coast left to wait out.
 *
 * HOW MUCH TURN IS STILL COMING when a sample is accepted here — measured, not
 * asserted, because the number decides whether the bounds below have any room.
 * Instrumenting this predicate through one orbit coast (idle container, ~8
 * renders per 120 ms sample window) gave the tail:
 *
 *     6.094  4.391  2.497  1.647  1.089  0.720  0.477  0.316  0.210  0.139
 *     0.092  0.061  0.041  0.027  0.018  0.012 deg per window
 *
 * i.e. the velocity decays ~0.66x per window, so ~0.949x per rendered FRAME.
 * Summing the tail from the 0.5 deg threshold: **~0.95 deg of turn still to
 * come**. That is the number the "well under a degree" claim below now rests
 * on. Its load sensitivity is the part worth knowing: damping decays per FRAME,
 * so a contended box that renders only ~2 frames per window has moved 0.25 deg
 * PER FRAME to show the same 0.5 deg window, and the same sum gives ~4.5 deg —
 * against a 5 deg bound. The direction is still safe (an unsettled sample can
 * only push that assertion towards failure, never towards a false pass), but if
 * "the plain drag drew and did not orbit" ever flakes under load, this is why,
 * and ~10 deg is the bound the derivation supports.
 */
const REST_COARSE: Stillness = { mm: 1, deg: 0.5 };

/**
 * Wait until the camera stops moving and return its pose.
 *
 * `invariants.waitForCameraRest` watches the view DIRECTION, which never
 * changes under a pan — so it returns instantly mid-pan and a position read
 * afterwards is a coasting sample. This one settles on position AND direction,
 * which is what a spec comparing a pan against an orbit needs. Damping is on
 * (`enableDamping={!reducedMotion}`), so both gestures coast after mouse-up.
 *
 * KNOWN HOLE, AND WHY THE OBVIOUS PATCH IS WRONG. "Two samples agree" is also
 * what a STALL looks like: the canvas is `frameloop="demand"`, so a window in
 * which nothing rendered has a delta of exactly 0 and this returns mid-motion,
 * at any tolerance — tightening {@link REST_EXACT} cannot close it. The
 * tempting fix is to also require `window.__loftRenderTick` (the render clock,
 * `Viewport.tsx`) to have advanced between the two samples. MEASURED, and it
 * does not work: a camera that is genuinely at rest renders ZERO frames on a
 * demand loop, which is exactly what the two calls that matter here observed
 * (`renders=0, dDeg=0.0000` for both the opening sample of a test and the
 * post-draw sample in step 3 of the raycast test). A render-delta requirement
 * would therefore hang on precisely the still cameras it was added to certify.
 * The probe cannot separate "nothing moved" from "nothing ran"; only DEMANDING
 * a render and observing that the camera did not move can, which is the shape
 * `qa-harness.spec.ts`'s `waitForQuiet` already uses. Left alone deliberately:
 * that belongs with the render-clock work, not bolted on here.
 *
 * (The same instrumentation showed the render clock ticking 8-9 times per
 * 120 ms window all the way down a coast in this scene, so it is alive here.)
 */
async function restCamera(
  page: Page,
  still: Stillness = REST_EXACT,
  timeoutMs = 60_000,
): Promise<Rest> {
  const deadline = Date.now() + timeoutMs;
  let previous = await cameraPose(page);
  for (;;) {
    await page.waitForTimeout(120);
    const current = await cameraPose(page);
    const settled =
      angleBetween(previous.direction, current.direction) <= still.deg &&
      distance(previous.position, current.position) <= still.mm;
    if (settled) {
      return { direction: current.direction, position: current.position };
    }
    previous = current;
    if (Date.now() > deadline) {
      throw new Error(
        `restCamera: still moving after ${timeoutMs}ms (position ` +
          `${current.position.map((v) => v.toFixed(2)).join(",")})`,
      );
    }
  }
}

function distance(
  a: readonly [number, number, number],
  b: readonly [number, number, number],
): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

interface PlaneHit {
  /** Plane coordinates (mm) the pixel addresses. */
  u: number;
  v: number;
  /** One screen pixel in plane mm at that depth — the spec's own tolerance. */
  mmPerPx: number;
}
interface ScreenHit {
  /** Viewport pixel the plane point projects to. */
  x: number;
  y: number;
  mmPerPx: number;
  /** The point is on screen and in front of the camera. */
  visible: boolean;
}

/**
 * The screen <-> plane map, derived from the LIVE camera in one round trip.
 *
 * Deliberately NOT the app's answer: `PointerCatcher` reads r3f's raycast hit
 * against a mesh, this unprojects (and projects) through the camera that just
 * rendered and intersects the datum's scene plane itself. The two agree only if
 * the sketcher's screen-to-plane mapping is still correct for where the camera
 * actually IS — which is the property an orbit mid-sketch puts at risk, and the
 * reason this spec does not simply read the DRO (the DRO is the same raycast).
 *
 * The XY datum in scene coordinates: `occtToSceneTuple` maps the kernel's
 * (u=+X, v=+Y, n=+Z) to (u=+X, v=-Z, n=+Y), i.e. the ground plane y = 0 with
 * scene point (x, 0, z) = (u, -v) in plane terms.
 *
 * The camera is picked exactly as `invariants.cameraPose` picks it (the stamp
 * if it matches, else the first observed scene). It is duplicated rather than
 * exported because that helper returns a serialized pose and (un)projection
 * needs the live object.
 */
async function viewProbe(
  page: Page,
  pixels: ReadonlyArray<readonly [number, number]>,
  planePoints: ReadonlyArray<readonly [number, number]>,
): Promise<{ hits: (PlaneHit | null)[]; screens: (ScreenHit | null)[] }> {
  const probe = await page.evaluate(
    (input: {
      pixels: [number, number][];
      planePoints: [number, number][];
    }) => {
      interface Vec {
        x: number;
        y: number;
        z: number;
        clone: () => Vec;
        set: (x: number, y: number, z: number) => Vec;
        sub: (v: Vec) => Vec;
        unproject: (camera: unknown) => Vec;
        project: (camera: unknown) => Vec;
      }
      interface Cam {
        position: Vec;
        fov?: number;
      }
      const w = window as unknown as Record<string, unknown>;
      const order = (w["__loftSceneOrder"] ?? []) as string[];
      const cameras = (w["__loftCameras"] ?? {}) as Record<string, Cam>;
      const stamp = document
        .querySelector('[data-testid="viewport"]')
        ?.getAttribute("data-camera-pos");
      const stamped = stamp ? stamp.split(",").map(Number) : null;
      const near = (camera: Cam): boolean =>
        stamped !== null &&
        stamped.length === 3 &&
        Math.abs(camera.position.x - (stamped[0] as number)) < 0.2 &&
        Math.abs(camera.position.y - (stamped[1] as number)) < 0.2 &&
        Math.abs(camera.position.z - (stamped[2] as number)) < 0.2;
      let cam: Cam | null = null;
      for (const uuid of order) {
        const candidate = cameras[uuid];
        if (candidate === undefined) continue;
        if (near(candidate)) {
          cam = candidate;
          break;
        }
        cam ??= candidate;
      }
      const canvas = document.querySelector<HTMLCanvasElement>(
        '[data-testid="viewport"] canvas',
      );
      if (cam === null || canvas === null) return null;
      const camera = cam;
      const rect = canvas.getBoundingClientRect();
      const eye = camera.position;
      const fov = typeof camera.fov === "number" ? camera.fov : 40;
      /** Plane mm subtended by one screen pixel at `depth` from the eye. */
      const scale = (depth: number): number =>
        (2 * depth * Math.tan((fov * Math.PI) / 360)) / rect.height;

      const hits = input.pixels.map(([px, py]) => {
        const ndcX = ((px - rect.left) / rect.width) * 2 - 1;
        const ndcY = -(((py - rect.top) / rect.height) * 2 - 1);
        const dir = eye.clone().set(ndcX, ndcY, 0.5).unproject(camera).sub(eye);
        if (Math.abs(dir.y) < 1e-9) return null; // ray parallel to the plane
        const t = -eye.y / dir.y;
        if (t <= 0) return null; // the plane is behind the camera
        const hx = eye.x + dir.x * t;
        const hy = eye.y + dir.y * t;
        const hz = eye.z + dir.z * t;
        return {
          u: hx,
          v: -hz,
          mmPerPx: scale(Math.hypot(hx - eye.x, hy - eye.y, hz - eye.z)),
        };
      });

      const screens = input.planePoints.map(([u, v]) => {
        const world = eye.clone().set(u, 0, -v);
        const depth = Math.hypot(
          world.x - eye.x,
          world.y - eye.y,
          world.z - eye.z,
        );
        const ndc = world.project(camera);
        return {
          x: rect.left + (ndc.x * 0.5 + 0.5) * rect.width,
          y: rect.top + (-ndc.y * 0.5 + 0.5) * rect.height,
          mmPerPx: scale(depth),
          visible:
            Math.abs(ndc.x) <= 0.9 && Math.abs(ndc.y) <= 0.9 && ndc.z < 1,
        };
      });
      return { hits, screens };
    },
    {
      pixels: pixels.map(([x, y]) => [x, y] as [number, number]),
      planePoints: planePoints.map(([u, v]) => [u, v] as [number, number]),
    },
  );
  if (probe === null) {
    throw new Error("viewProbe: no live camera or canvas on the page");
  }
  return probe;
}

/** The plane point a pixel addresses. Throws if the ray misses the plane. */
async function planeAt(page: Page, x: number, y: number): Promise<PlaneHit> {
  const { hits } = await viewProbe(page, [[x, y]], []);
  const hit = hits[0];
  if (hit === undefined || hit === null) {
    throw new Error(`planeAt(${x},${y}): the pixel does not meet the plane`);
  }
  return hit;
}

/** The pixel a plane point projects to. Throws if it is off screen. */
async function screenAt(page: Page, u: number, v: number): Promise<ScreenHit> {
  const { screens } = await viewProbe(page, [], [[u, v]]);
  const screen = screens[0];
  if (screen === undefined || screen === null || !screen.visible) {
    throw new Error(
      `screenAt(${u.toFixed(1)},${v.toFixed(1)}): off screen ` +
        `(${screen?.x.toFixed(0) ?? "?"},${screen?.y.toFixed(0) ?? "?"})`,
    );
  }
  return screen;
}

/**
 * Orbit with the middle button and return the angle the view turned through.
 * The drag carries both axes: the sketch camera parks normal-on, so a purely
 * horizontal drag would be a small motion about the view axis.
 */
async function middleOrbit(
  page: Page,
  from: { x: number; y: number } = { x: 800, y: 500 },
  delta: { dx: number; dy: number } = { dx: 150, dy: -110 },
  still: Stillness = REST_COARSE,
): Promise<{ before: Rest; after: Rest; turnedDeg: number }> {
  const before = await restCamera(page);
  await drag(page, "middle", from, delta.dx, delta.dy);
  const after = await restCamera(page, still);
  return {
    before,
    after,
    turnedDeg: angleBetween(before.direction, after.direction),
  };
}

/**
 * Orbit with Alt(Option)+left-drag — VP-1a, the gesture a one-button trackpad
 * can actually produce — and return the angle the view turned through.
 *
 * Playwright stamps the modifier state established by `keyboard.down` onto
 * every mouse event it dispatches afterwards, so the `pointerdown` the rig sees
 * really carries `altKey: true`; that flag is the whole input to the button-map
 * override under test. Alt is released in a `finally` so a failed assertion
 * cannot leak a held modifier into the rest of the test.
 */
async function altOrbit(
  page: Page,
  from: { x: number; y: number } = { x: 800, y: 500 },
  delta: { dx: number; dy: number } = { dx: 150, dy: -110 },
  still: Stillness = REST_COARSE,
): Promise<{ before: Rest; after: Rest; turnedDeg: number }> {
  const before = await restCamera(page);
  await page.keyboard.down("Alt");
  try {
    await drag(page, "left", from, delta.dx, delta.dy);
  } finally {
    await page.keyboard.up("Alt");
  }
  const after = await restCamera(page, still);
  return {
    before,
    after,
    turnedDeg: angleBetween(before.direction, after.direction),
  };
}

/** Absolute-tolerance comparison — `toBeCloseTo` counts digits, not mm. */
function expectNear(
  actual: number | undefined,
  expected: number,
  toleranceMm: number,
  what: string,
): void {
  expect(actual, `${what}: no value`).toBeDefined();
  expect(
    Math.abs((actual as number) - expected),
    `${what}: ${String(actual)} vs ${expected.toFixed(4)} mm`,
  ).toBeLessThan(toleranceMm);
}

/**
 * How far the view must turn for a middle-drag to count as an orbit.
 *
 * Measured at 1600x1000 with the default navigation sensitivity, three
 * consecutive runs: the (150, -110) drag turned 72.01 / 72.01 / 72.02 deg and
 * the gentler (90, -60) drag turned 44.60 deg every time. The pre-fix build
 * turns 0.00 deg on both (see the mutation note in the ticket). 10 sits an
 * order of magnitude away from either side, so it separates them without being
 * a raster-tight number.
 */
const ORBITED_DEG = 10;

test.describe("VP-1 — the camera moves while the sketch is being drawn", () => {
  /**
   * Every test here drives a REAL orbit and then waits out the damping coast it
   * leaves behind, and that coast decays per rendered FRAME — so its wall-clock
   * length is set by how much CPU the box has, not by anything the spec does.
   * Measured on this container: 21-45 s per test idle, and 1.0-1.5 min with two
   * other Playwright suites sharing the machine (load average 15), where the
   * default 60 s budget turned working tests into opaque `mouse.down: Test
   * timeout` failures. `test.slow()` (x3) is Playwright's own way to state that;
   * a test that finishes in 30 s still finishes in 30 s.
   */
  test.beforeEach(() => {
    test.slow();
  });

  test("the left button still draws, and does not move the camera", async ({
    page,
  }) => {
    await enterDrawOnXy(page, "Sketch orbit: left draws");
    const before = await restCamera(page);
    await armRect(page);

    await drag(page, "left", { x: 660, y: 400 }, 300, 200);
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");

    // The drawing gesture is the sketcher's alone: unbinding LEFT from the
    // orbit rig must not have handed it BACK to the camera.
    const after = await restCamera(page);
    expect(angleBetween(before.direction, after.direction)).toBeLessThan(0.5);
    expect(distance(before.position, after.position)).toBeLessThan(0.5);
  });

  test("the middle button orbits, mid-draw, without drawing anything", async ({
    page,
  }) => {
    await enterDrawOnXy(page, "Sketch orbit: middle orbits");
    await armRect(page); // the exact state that used to lock the camera

    const { turnedDeg } = await middleOrbit(page);
    expect(turnedDeg).toBeGreaterThan(ORBITED_DEG);

    // The orbit is a camera gesture only — no stray geometry, tool still armed,
    // still on the plane.
    await expect(page.getByTestId("sketch-save")).toContainText("0 entities");
    await expect(page.getByTestId("tool-rect")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("sketch-step")).toHaveText(`On ${PLANE}`);
  });

  test("Alt+left-drag orbits, mid-draw, without drawing anything", async ({
    page,
  }) => {
    // VP-1a — the trackpad path. Same state as the middle-button test above;
    // the only difference is the gesture, which is the one a machine with a
    // single button can make.
    await enterDrawOnXy(page, "Sketch orbit: alt orbits");
    await armRect(page);

    const { turnedDeg } = await altOrbit(page);
    expect(turnedDeg).toBeGreaterThan(ORBITED_DEG);

    // A camera gesture only: the press that orbited must not also have placed
    // the rectangle's first corner, which is what makes this different from
    // simply binding LEFT to ROTATE.
    await expect(page.getByTestId("sketch-save")).toContainText("0 entities");
    await expect(page.getByTestId("tool-rect")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("sketch-step")).toHaveText(`On ${PLANE}`);

    // AND ONE PLAIN CLICK AFTERWARDS — which is what pins the PRESS guard
    // rather than the pair. There are two alt guards in `PointerCatcher`, one
    // on press and one on click, and every assertion above survives removing
    // EITHER one alone (measured, both ablations): with the press guard gone
    // the click guard still swallows the release, so nothing is drawn and the
    // entity count stays 0 — while the press has quietly left the rectangle's
    // first corner sitting in `pending`. The modeller's next click then closes
    // a rectangle from wherever they happened to start looking around, which is
    // exactly the defect the press guard's own comment in `SketchScene.tsx`
    // names — "placing a point from it would draw a stray entity every time the
    // modeller looked around". One more click is the whole difference between
    // testing the pair and testing each member of it.
    //
    // `planeAt` first because the pixel has to still MEAN something after a
    // ~72 deg turn: it throws when the ray misses the sketch plane, so this
    // cannot decay into a click that lands nowhere and asserts nothing.
    await planeAt(page, 600, 620);
    await page.mouse.click(600, 620, { button: "left" });
    await expect(
      page.getByTestId("sketch-save"),
      "the Alt press left no anchor for the next click to close on",
    ).toContainText("0 entities");
  });

  test("an Alt click picks nothing, with the select tool live", async ({
    page,
  }) => {
    // The CLICK guard, alone. Its failure mode is not the press guard's: with
    // `select` armed `dragDraws` is false, so the press handler returns before
    // it ever reads `altKey` and the press guard is not in the path at all.
    // Everything here therefore rests on the single line at the top of
    // `onClick` — and an Alt release that reached the picker would select the
    // curve the modeller merely orbited across.
    await enterDrawOnXy(page, "Sketch orbit: alt does not pick");

    // Something to pick, and its extent in PLANE coordinates: the alt gesture
    // below turns the camera, so the pixel that addresses this line afterwards
    // is not the pixel that addresses it now.
    await armRect(page);
    const corner = { x: 660, y: 400 };
    const opposite = { x: 960, y: 600 };
    const rectA = await planeAt(page, corner.x, corner.y);
    const rectB = await planeAt(page, opposite.x, opposite.y);
    await drag(
      page,
      "left",
      corner,
      opposite.x - corner.x,
      opposite.y - corner.y,
    );
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");

    // Escape closes the size cells AND drops the tool, landing on `select` —
    // the resting tool, which has no button of its own. The wait on the cells
    // is load-bearing for the same reason as in the raycast test below: while
    // armed they take pointer events and would eat the press.
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("tool-rect")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    await expect(page.getByTestId("draw-dimensions")).toHaveCount(0);
    await expect(page.getByTestId("selection-readout")).toContainText(
      "nothing selected",
    );

    // The midpoint of one of the rectangle's two edges of constant v, in plane
    // terms — an edge midpoint is the same target `click-drift.spec.ts` picks
    // at for FB-12, and it is as far from a corner (and from the corner's
    // point-grain pick) as the curve gets.
    const mid = {
      u: (rectA.u + rectB.u) / 2,
      v: Math.min(rectA.v, rectB.v),
    };
    const onTheLine = await screenAt(page, mid.u, mid.v);
    const pixel = { x: Math.round(onTheLine.x), y: Math.round(onTheLine.y) };

    // (a) Alt with no travel at all — an Option-tap on a trackpad, and the
    //     limiting case of the short alt-drag: `isClick` is unarguably true, so
    //     nothing but the guard stands between this release and `selectAt`.
    await page.keyboard.down("Alt");
    try {
      await page.mouse.click(pixel.x, pixel.y, { button: "left" });
    } finally {
      await page.keyboard.up("Alt");
    }
    await expect(
      page.getByTestId("selection-readout"),
      "an Alt tap picked the curve under it",
    ).toContainText("nothing selected");

    // (b) And with real travel, under CLICK_SLOP_PX (12) — the gesture the
    //     founder's trackpad actually makes when a tumble barely moves. The
    //     view turns a little, which is the point: the camera took this
    //     gesture, so the model must not have.
    await page.keyboard.down("Alt");
    try {
      await drag(page, "left", pixel, 6, 5);
    } finally {
      await page.keyboard.up("Alt");
    }
    await expect(
      page.getByTestId("selection-readout"),
      "a short Alt drag picked the curve it orbited across",
    ).toContainText("nothing selected");

    // The positive control, and the reason neither assertion above can pass
    // vacuously: WITHOUT Alt the very same target does select. Re-projected
    // through the settled camera rather than re-used as a pixel — (b) turned
    // the view, and a stale pixel would make this fail for the wrong reason.
    await restCamera(page, REST_COARSE);
    const stillThere = await screenAt(page, mid.u, mid.v);
    await page.mouse.click(Math.round(stillThere.x), Math.round(stillThere.y), {
      button: "left",
    });
    await expect(
      page.getByTestId("selection-readout"),
      "the target was pickable all along",
    ).toContainText("1 ent");
  });

  test("a plain left-drag after an Alt-orbit still draws, and does not orbit", async ({
    page,
  }) => {
    // The property that makes VP-1a safe: the button map is DERIVED at each
    // press from that press's own modifier, never tracked across presses. The
    // classic keydown/keyup implementation fails exactly here — an Alt released
    // outside the window, or a missed keyup, leaves LEFT bound to ROTATE and
    // the next drawing stroke silently spins the view instead of drawing.
    await enterDrawOnXy(page, "Sketch orbit: alt does not stick");
    await armRect(page);

    const orbit = await altOrbit(page);
    expect(orbit.turnedDeg).toBeGreaterThan(ORBITED_DEG);

    const before = await restCamera(page, REST_COARSE);
    await drag(page, "left", { x: 660, y: 400 }, 300, 200);
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");

    // The bounds sit between what a stuck LEFT binding would produce and the
    // residual of the coarse rest above: the Alt-orbit that precedes this turns
    // ~72 deg and carries the camera ~172 mm, while a coast accepted at the
    // coarse threshold has ~0.95 deg still to come on an idle box — measured,
    // with the decay tail and the load sensitivity written out in
    // {@link REST_COARSE}. Read that before touching either number: the margin
    // here is ~5x on an idle box and thinner under contention, and it is the
    // derivation, not the constant, that says so.
    const after = await restCamera(page, REST_COARSE);
    expect(
      angleBetween(before.direction, after.direction),
      "the plain drag drew and did not orbit",
    ).toBeLessThan(5);
    expect(distance(before.position, after.position)).toBeLessThan(25);
  });

  test("the right button still pans, and still opens no menu", async ({
    page,
  }) => {
    await enterDrawOnXy(page, "Sketch orbit: right pans");
    await armRect(page);
    const before = await restCamera(page);

    await drag(page, "right", { x: 800, y: 500 }, 170, 110);
    // Coarse rest: both assertions below survive a coasting sample. A pan does
    // not rotate at all, so the angle bound holds at any point of the coast,
    // and the distance bound is a LOWER one that a coast can only inflate.
    const after = await restCamera(page, REST_COARSE);

    // A pan translates the camera and leaves the view direction alone — the
    // signature that separates it from the orbit above.
    expect(distance(before.position, after.position)).toBeGreaterThan(1);
    expect(angleBetween(before.direction, after.direction)).toBeLessThan(0.5);
    await expect(page.getByTestId("viewport-context-menu")).toHaveCount(0);
    await expect(page.getByTestId("sketch-save")).toContainText("0 entities");
  });

  test("after orbiting, the next entity lands where it was drawn", async ({
    page,
  }) => {
    // The heavy one: it draws, orbits, re-projects and draws again, so it waits
    // out four separate damping coasts on the only scene in this file with
    // entities in it (each coast is slower for having more to render), and it
    // is the only test that needs EXACT rest. Measured 45.5 s end to end on an
    // idle box — see the `test.slow()` note on the describe block.
    const { partId, token } = await enterDrawOnXy(
      page,
      "Sketch orbit: raycast",
    );

    // 1 — a first entity from the parked, normal-on view, and the plane extent
    //     it occupies (measured, so the second entity can be placed clear of
    //     it rather than at a guessed offset).
    await armRect(page);
    const corner = { x: 560, y: 380 };
    const opposite = { x: 780, y: 550 };
    const rectA = await planeAt(page, corner.x, corner.y);
    const rectB = await planeAt(page, opposite.x, opposite.y);
    await drag(
      page,
      "left",
      corner,
      opposite.x - corner.x,
      opposite.y - corner.y,
    );
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
    await page.keyboard.press("Escape"); // close the size cells, drop the tool
    // Load-bearing wait, not tidiness: the armed size cells are DOM seated on
    // the shape's far corner and they take pointer events
    // (`DrawDimensions`: `pointerEvents: armed ? "auto" : "none"`), so a middle
    // press dispatched before they unmount can land on an input instead of the
    // canvas. One run without this wait measured a 0.00 deg "orbit".
    await expect(page.getByTestId("draw-dimensions")).toHaveCount(0);

    // 2 — orbit away from the plane's normal. A gentler turn than the other
    //     tests use: the sheet has to stay square enough to the camera that a
    //     point beside the rectangle is still on screen to draw at.
    //     This is the ONE place that needs exact rest: step 3 projects plane
    //     points through this camera and then dispatches the pointer at those
    //     pixels, so a camera still coasting between the projection and the
    //     press would move the target out from under it.
    const orbit = await middleOrbit(
      page,
      { x: 1100, y: 320 },
      { dx: 90, dy: -60 },
      REST_EXACT,
    );
    expect(orbit.turnedDeg).toBeGreaterThan(ORBITED_DEG);

    // 3 — draw a SECOND entity from the new angle. The two ends are chosen in
    //     PLANE space, one rectangle-width clear of the first entity, then
    //     projected to pixels through the orbited camera — so the pointer
    //     cannot wander off into the horizon the way a fixed pixel does once
    //     the sheet is foreshortened. Ctrl is held throughout: `resolveSnap`
    //     returns the raw point under Ctrl (no grid, no entity snap), so what
    //     is persisted is exactly what the raycast produced.
    const width = Math.abs(rectB.u - rectA.u);
    const height = Math.abs(rectB.v - rectA.v);
    const from = {
      u: Math.max(rectA.u, rectB.u) + width * 0.6,
      v: Math.min(rectA.v, rectB.v) - height * 0.6,
    };
    const to = { u: from.u + width * 0.5, v: from.v - height * 0.5 };
    const a = await screenAt(page, from.u, from.v);
    const b = await screenAt(page, to.u, to.v);

    await page.keyboard.press("l");
    await expect(page.getByTestId("tool-line")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.keyboard.down("Control");
    await drag(
      page,
      "left",
      { x: Math.round(a.x), y: Math.round(a.y) },
      Math.round(b.x) - Math.round(a.x),
      Math.round(b.y) - Math.round(a.y),
    );
    await page.keyboard.up("Control");
    await expect(page.getByTestId("sketch-save")).toContainText("5 entities");

    // The camera really was off-axis for that draw — if the sketch rig had
    // snapped back to normal-on when the entity synced, the assertions below
    // would pass for the wrong reason (the old mapping would be correct again).
    //
    // EXACT rest, unlike every other lower-bound assertion in this file, and
    // the reason is in {@link REST_COARSE}'s docblock: this is the one place
    // where an unsettled camera moves the measurement the WRONG way. The
    // failure being watched for is precisely a rig easing the view BACK toward
    // normal-on, so a mid-ease sample reads FURTHER from the reference than the
    // settled one does and a coarse rest could bless the snap-back it exists to
    // catch. It is also nearly free here: the gesture before it is a draw, not
    // an orbit, so the camera is already still and the first pair of samples
    // agrees.
    const held = await restCamera(page, REST_EXACT);
    expect(
      angleBetween(orbit.before.direction, held.direction),
      "the camera stayed orbited across the draw",
    ).toBeGreaterThan(ORBITED_DEG);

    // 4 — save, and read what the document actually stored. The rectangle
    //     minted e1..e4, so the line drawn from the orbited view is e5.
    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
    const stored = await persistedEntities(page, partId, token);
    expect(stored.map((e) => e.id)).toEqual(["e1", "e2", "e3", "e4", "e5"]);
    const drawn = stored.find((e) => e.id === "e5");
    expect(drawn?.kind).toBe("line");

    // Two screen pixels' worth of plane mm at the depth each end was drawn at:
    // the pointer is dispatched at an integer pixel and the target came from a
    // float projection, so a sub-pixel difference is expected and anything
    // larger is a broken mapping. Both are measurements off the live camera,
    // not a hand-picked epsilon.
    expect(a.mmPerPx, "the tolerance is a real measurement").toBeGreaterThan(0);
    expectNear(drawn?.start?.x, from.u, 2 * a.mmPerPx, "start u");
    expectNear(drawn?.start?.y, from.v, 2 * a.mmPerPx, "start v");
    expectNear(drawn?.end?.x, to.u, 2 * b.mmPerPx, "end u");
    expectNear(drawn?.end?.y, to.v, 2 * b.mmPerPx, "end v");
  });

  test("outside the sketcher the left button still orbits", async ({
    page,
  }) => {
    // The other half of the contract: with no sketch open, `rotateEnabled` is
    // true and the map is three-stdlib's own default, so 3D navigation is
    // exactly what it was.
    await installSceneProbe(page);
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Sketch orbit: 3D left");
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("viewport").locator("canvas")).toBeVisible();

    const before = await restCamera(page);
    await drag(page, "left", { x: 800, y: 500 }, 150, -110);
    const after = await restCamera(page, REST_COARSE);
    expect(angleBetween(before.direction, after.direction)).toBeGreaterThan(
      ORBITED_DEG,
    );
  });
});
