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

/**
 * Wait until the camera stops moving and return its pose.
 *
 * `invariants.waitForCameraRest` watches the view DIRECTION, which never
 * changes under a pan — so it returns instantly mid-pan and a position read
 * afterwards is a coasting sample. This one settles on position AND direction,
 * which is what a spec comparing a pan against an orbit needs. Damping is on
 * (`enableDamping={!reducedMotion}`), so both gestures coast after mouse-up.
 */
async function restCamera(page: Page, timeoutMs = 15_000): Promise<Rest> {
  const deadline = Date.now() + timeoutMs;
  let previous = await cameraPose(page);
  for (;;) {
    await page.waitForTimeout(120);
    const current = await cameraPose(page);
    const still =
      angleBetween(previous.direction, current.direction) <= 0.02 &&
      distance(previous.position, current.position) <= 0.02;
    if (still) {
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
): Promise<{ before: Rest; after: Rest; turnedDeg: number }> {
  const before = await restCamera(page);
  await drag(page, "middle", from, delta.dx, delta.dy);
  const after = await restCamera(page);
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

  test("the right button still pans, and still opens no menu", async ({
    page,
  }) => {
    await enterDrawOnXy(page, "Sketch orbit: right pans");
    await armRect(page);
    const before = await restCamera(page);

    await drag(page, "right", { x: 800, y: 500 }, 170, 110);
    const after = await restCamera(page);

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
    const orbit = await middleOrbit(
      page,
      { x: 1100, y: 320 },
      { dx: 90, dy: -60 },
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
    const held = await restCamera(page);
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
    const after = await restCamera(page);
    expect(angleBetween(before.direction, after.direction)).toBeGreaterThan(
      ORBITED_DEG,
    );
  });
});
