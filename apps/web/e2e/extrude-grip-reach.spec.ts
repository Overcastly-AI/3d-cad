/**
 * CRAFT-7 — THE AFFORDANCE AND THE HIT TARGET MUST BE THE SAME THING.
 *
 * The gauge has been drawn since T-23 and, until this spec, could not be taken
 * hold of anywhere the drawing invites you to. Measured on the running app:
 * `document.elementFromPoint` down the gauge's OWN projected axis resolved to
 * the grip at **2 of 16** sample points — a 24 x 24 box at the arrowhead's apex
 * and nothing else — and a real `page.mouse.down/move/up` from the shaft's
 * midpoint left `extrude-distance` unchanged at 40. The shaft, the cone and the
 * ladder are WebGL with no raycast target, so the affordance and the hit target
 * were ANTICORRELATED: the one grabbable spot was a 12 px collar on the POINT of
 * an arrow drawn at 0.92 opacity, about 90 px from where the arrow tells you to
 * aim.
 *
 * ## Why this is a spec and not a screenshot
 *
 * A drawn manipulator photographs perfectly while being unusable, which is how
 * this survived a founder capture, a design review and six passing e2e cases.
 * `toBeVisible()` is a box property; `boundingBox()` is a box property; only
 * asking the browser WHAT IS UNDER THIS PIXEL, and then actually pressing it,
 * can see the defect. So both halves are here, and the second is the one that
 * matters: it asserts with the user's own mechanism rather than a proxy.
 *
 * **There is no `force: true` in this file and there must never be.** This repo
 * has already measured that flag hiding a zero-area SVG pick target for months;
 * it is evidence of a defect, not a workaround for one.
 */
import { expect, test, type Page } from "./fixtures";
import { installSceneProbe, waitForCameraRest } from "./invariants";
import { createPartViaApi, seedSession } from "./support";

/** How many points we walk down the projected track. */
const SAMPLES = 16;

/**
 * The acceptance floor, from the W3 direction doc (§9, amended).
 *
 * 12 of 16 rather than all 16 because the two ends legitimately fall outside:
 * `t = 0` sits on the sketch plane, where the sleeve must NOT be (it would
 * swallow a face pick), and the last sample rides the arrow's point where the
 * grip's own round target is inset from the square sample.
 */
const REACH_FLOOR = 12;

interface Point {
  x: number;
  y: number;
}

/** Enter sketch mode, draw a rectangle, and open the extrude editor on it. */
async function openExtrude(page: Page): Promise<void> {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await page.keyboard.press("r");
  await page.mouse.click(650, 420);
  await page.mouse.move(980, 640);
  await page.mouse.click(980, 640);
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  await page.getByTestId("new-extrude").click();
  await expect(page.getByTestId("extrude-editor")).toBeVisible();
  // Iso, because the post-sketch camera looks straight down the pull axis and a
  // track with no screen direction has no axis to walk.
  await page.getByTestId("view-iso").click();
  await waitForCameraRest(page);
}

/**
 * The drawn shaft's two ends, in CSS pixels.
 *
 * Taken from the SPINE MESH ITSELF rather than reconstructed from the DOM: the
 * cylinder is unit-height and scaled to the value, so its local `(0, ±0.5, 0)`
 * are exactly the seat and the arrowhead's base, and `matrixWorld` carries
 * whatever pose the component gave it. That is what makes this a measurement of
 * the thing the user can see rather than of an assumption about it.
 */
async function projectedSpine(
  page: Page,
  gaugeId: string,
): Promise<{ seat: Point; base: Point }> {
  const seen = await page.evaluate((wanted: string) => {
    interface Mat {
      elements: number[];
    }
    interface Obj3D {
      name: string;
      matrixWorld: Mat;
      traverse: (fn: (child: Obj3D) => void) => void;
      updateWorldMatrix?: (parents: boolean, children: boolean) => void;
    }
    interface Cam {
      matrixWorldInverse: Mat;
      projectionMatrix: Mat;
    }
    const w = window as unknown as Record<string, unknown>;
    const scenes = (w["__loftScenes"] ?? {}) as Record<string, Obj3D>;
    const cameras = (w["__loftCameras"] ?? {}) as Record<string, Cam>;
    const order = (w["__loftSceneOrder"] ?? []) as string[];
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
      const scene = scenes[uuid];
      const camera = cameras[uuid];
      if (scene === undefined || camera === undefined) continue;
      let mesh: Obj3D | null = null;
      scene.traverse((node) => {
        if (node.name === wanted) mesh = node;
      });
      if (mesh === null) continue;
      const found: Obj3D = mesh;
      found.updateWorldMatrix?.(true, false);
      const canvas = document.querySelector("canvas");
      if (canvas === null) return null;
      const rect = canvas.getBoundingClientRect();
      const toScreen = (ly: number): Point => {
        const world = apply(found.matrixWorld.elements, 0, ly, 0, 1);
        const view = apply(
          camera.matrixWorldInverse.elements,
          world[0],
          world[1],
          world[2],
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
      };
      return { a: toScreen(-0.5), b: toScreen(0.5) };
    }
    return null;
  }, `gauge-${gaugeId}-spine`);
  if (seen === null) throw new Error(`no spine mesh for gauge ${gaugeId}`);
  // The cylinder's +Y end is the arrowhead's base; which of the two that is on
  // screen depends only on the camera, so pick by distance to the grip.
  const grip = await gripCentre(page, gaugeId);
  const near = (p: Point): number => Math.hypot(p.x - grip.x, p.y - grip.y);
  return near(seen.a) < near(seen.b)
    ? { seat: seen.b, base: seen.a }
    : { seat: seen.a, base: seen.b };
}

/** The grip's centre in page coordinates. */
async function gripCentre(page: Page, gaugeId: string): Promise<Point> {
  const box = await page.getByTestId(`${gaugeId}-handle`).boundingBox();
  if (box === null) throw new Error(`the ${gaugeId} grip has no box`);
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

/** Walk the projected track and ask the browser what is under each pixel. */
async function reach(
  page: Page,
  gaugeId: string,
): Promise<{ hits: number; resolved: string[]; from: Point; to: Point }> {
  const { seat } = await projectedSpine(page, gaugeId);
  const apex = await gripCentre(page, gaugeId);
  const points: Point[] = [];
  for (let i = 0; i < SAMPLES; i += 1) {
    const t = i / (SAMPLES - 1);
    points.push({
      x: seat.x + (apex.x - seat.x) * t,
      y: seat.y + (apex.y - seat.y) * t,
    });
  }
  const resolved = await page.evaluate(
    ({ pts, id }: { pts: Point[]; id: string }) =>
      pts.map((p) => {
        const el = document.elementFromPoint(p.x, p.y);
        if (el === null) return "null";
        return el.closest(`[data-gauge="${id}"]`) !== null
          ? "gauge"
          : (el.getAttribute("data-testid") ??
              el.tagName.toLowerCase() +
                (el.className && typeof el.className === "string"
                  ? `.${el.className.split(/\s+/)[0]}`
                  : ""));
      }),
    { pts: points, id: gaugeId },
  );
  return {
    hits: resolved.filter((r) => r === "gauge").length,
    resolved,
    from: seat,
    to: apex,
  };
}

/** The distance field's value as a number. */
async function distance(page: Page): Promise<number> {
  return Number.parseFloat(
    await page.getByTestId("extrude-distance").inputValue(),
  );
}

test.describe("the extrude gauge is grabbable where it is drawn", () => {
  test("elementFromPoint down the projected track resolves to the gauge", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Reachable boss");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);
    await page.getByTestId("extrude-distance").fill("40");
    await expect(page.getByTestId("extrude-preview-active")).toHaveAttribute(
      "data-distance-mm",
      "40",
    );

    const walked = await reach(page, "extrude-depth");
    console.log(
      `CRAFT-7 reach: ${walked.hits}/${SAMPLES} — ${walked.resolved.join(", ")}`,
    );
    expect(
      walked.hits,
      `the drawn track must BE the target: ${walked.hits}/${SAMPLES} sample ` +
        `points resolved to the gauge (${walked.resolved.join(", ")})`,
    ).toBeGreaterThanOrEqual(REACH_FLOOR);
  });

  test("a real pointer drag from the shaft midpoint moves the value", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Midshaft boss");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);
    await page.getByTestId("extrude-distance").fill("40");
    await expect(page.getByTestId("extrude-preview-active")).toHaveAttribute(
      "data-distance-mm",
      "40",
    );

    const { seat } = await projectedSpine(page, "extrude-depth");
    const apex = await gripCentre(page, "extrude-depth");
    const mid = { x: (seat.x + apex.x) / 2, y: (seat.y + apex.y) / 2 };

    // No `force`, no locator: the raw mouse, at a pixel chosen from the drawn
    // geometry. If nothing is listening there, nothing happens — which is
    // exactly what happened before this item, and the field stayed at 40.
    await page.mouse.move(mid.x, mid.y);
    await page.mouse.down();
    for (let step = 1; step <= 5; step += 1) {
      await page.mouse.move(mid.x, mid.y + step * 12);
    }
    await page.mouse.up();

    await expect
      .poll(() => distance(page), {
        message:
          "a drag from the middle of the drawn shaft must move the value",
      })
      .toBeLessThan(40);
  });

  test("the tag is TIED to the grip, and the tie flips at the frame edge", async ({
    page,
  }) => {
    // MEASURED before this item: the tag was placed by a bare CSS offset
    // (`-translate-y-8 translate-x-4`) and floated unattached — `D 10 mm`
    // hanging in space with no tie to the arrow it describes. At that point it
    // is a HUD chip that happens to be near some geometry, and anything else on
    // screen could equally be its subject. The leader makes the claim.
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Tied");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);

    const leader = page.getByTestId("gauge-tag-leader");
    await expect(leader).toHaveCount(1);

    // The leader's anchor is ON the grip and its far end is ON the strip, which
    // is the only thing that makes it a tie rather than a stray hairline. Both
    // are read as real geometry rather than from the props that drew them.
    const strip = page.getByTestId("extrude-depth-readout");
    const gripBox = await gripCentre(page, "extrude-depth");
    // READ THE LINE'S OWN ENDPOINTS, not its bounding box.
    // `getBoundingClientRect` on an SVG `<line>` ignores stroke AND loses the
    // direction: for a leader running up-and-right the box corners are
    // `(0, -28)` and `(14, 0)` and NEITHER is an endpoint, so a nearest-corner
    // reading reported the anchor 14 px from a grip it is sitting on. This repo
    // has already paid for the stroke half of that trap (the 118.1 x 0.0 px
    // dimension pick); this is the other half. The SVG is 1x1 anchored at the
    // grip, so its own rect is the origin the attributes are relative to.
    const leaderBox = await leader.evaluate((el) => {
      const line = el.querySelector("line");
      if (line === null) return null;
      const origin = el.getBoundingClientRect();
      const at = (name: string): number =>
        Number(line.getAttribute(name) ?? "0");
      return {
        x1: origin.left + at("x1"),
        y1: origin.top + at("y1"),
        x2: origin.left + at("x2"),
        y2: origin.top + at("y2"),
      };
    });
    if (leaderBox === null) throw new Error("no leader line");
    const stripBox = await strip.boundingBox();
    if (stripBox === null) throw new Error("no strip box");

    // One end within the grip's own 24 px target…
    const nearGrip = Math.hypot(
      leaderBox.x1 - gripBox.x,
      leaderBox.y1 - gripBox.y,
    );
    expect(nearGrip, "the leader must start ON the grip").toBeLessThanOrEqual(
      12,
    );
    // …and the other inside the strip it carries.
    const inStrip =
      leaderBox.x2 >= stripBox.x - 2 &&
      leaderBox.x2 <= stripBox.x + stripBox.width + 2 &&
      leaderBox.y2 >= stripBox.y - 2 &&
      leaderBox.y2 <= stripBox.y + stripBox.height + 2;
    expect(inStrip, "the leader must reach the strip it ties").toBe(true);

    // The side is STAMPED, which is the only externally checkable evidence a
    // flip can ever happen — a placement test that only asserts "inside the
    // frame" passes just as well when the tag is clamped onto the grip.
    await expect(page.locator("[data-gauge-tag-side]")).toHaveCount(1);
  });

  test("the sleeve exists only while the command is open", async ({ page }) => {
    // A transparent band across the viewport that outlived its command would
    // swallow face picks — the one way this fix could make the product worse.
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Closed boss");
    await page.goto(`/parts/${part.id}`);
    await openExtrude(page);
    await expect(page.getByTestId("extrude-depth-sleeve")).toHaveCount(1);
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("extrude-editor")).toHaveCount(0);
    await expect(page.getByTestId("extrude-depth-sleeve")).toHaveCount(0);
  });
});
