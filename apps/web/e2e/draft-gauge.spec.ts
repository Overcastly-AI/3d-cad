/**
 * CRAFT-10 — THE DRAFT TAPER GAUGE.
 *
 * The revolve gauge's twin on a different verb, and the same three claims: the
 * PIVOT is drawn (it was not — the neutral plane was a control with nothing on
 * screen answering to it), the drag moves the MODEL and not only the number,
 * and the instrument stays where you let go of it.
 *
 * Two things here are specific to a draft and worth naming, because both were
 * found by mounting the gauge rather than by reading the code:
 *
 *  · **A face PARALLEL to the neutral plane has no pivot**, so a cube's top
 *    face against XY cannot be drafted about it and gets no gauge. That is a
 *    real modelling answer, not an error state, and this file asserts it as a
 *    NEGATIVE CONTROL — without one, "the gauge appeared" is satisfied by a
 *    component that renders unconditionally.
 *  · **The taper's SIGN rides on the axis, not on the value.** The track's value
 *    is the magnitude, so a drag can never walk through zero — which is the one
 *    value the form refuses — while the readout still says the signed angle.
 *
 * No `force: true`, here or anywhere: every press is a real `page.mouse` at a
 * point whose occupant has been asked for.
 */
import { expect, test, type Page } from "./fixtures";
import { installSceneProbe, waitForCameraRest } from "./invariants";
import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
  waitForFrames,
} from "./support";

/** A 20 mm square on XY — the seed profile for the cube. */
const SQUARE_20 = {
  plane: { kind: "datum_plane", plane: "XY" },
  entities: [
    {
      kind: "line",
      id: "e1",
      start: { x: 0, y: 0 },
      end: { x: 20, y: 0 },
      construction: false,
    },
    {
      kind: "line",
      id: "e2",
      start: { x: 20, y: 0 },
      end: { x: 20, y: 20 },
      construction: false,
    },
    {
      kind: "line",
      id: "e3",
      start: { x: 20, y: 20 },
      end: { x: 0, y: 20 },
      construction: false,
    },
    {
      kind: "line",
      id: "e4",
      start: { x: 0, y: 20 },
      end: { x: 0, y: 0 },
      construction: false,
    },
  ],
  constraints: [
    { kind: "horizontal", entity: "e1" },
    { kind: "vertical", entity: "e2" },
    { kind: "horizontal", entity: "e3" },
    { kind: "vertical", entity: "e4" },
    { kind: "distance", entity: "e1", value_mm: 20 },
    { kind: "distance", entity: "e2", value_mm: 20 },
    { kind: "fixed", point: { entity: "e1", point: "start" } },
  ],
};

async function createFeature(
  page: Page,
  token: string,
  partId: string,
  body: unknown,
): Promise<{ feature: { id: string }; tree_version: number }> {
  const response = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: body,
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) {
    throw new Error(
      `e2e create feature failed: ${response.status()} ${await response.text()}`,
    );
  }
  return (await response.json()) as {
    feature: { id: string };
    tree_version: number;
  };
}

/** Seed a part whose body is a 20 mm cube at the origin. */
async function seedCubePart(page: Page): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Draft cube");
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: SQUARE_20 },
    expected_tree_version: 0,
  });
  await createFeature(page, account.token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 20,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  return part.id;
}

async function waitForCube(page: Page): Promise<void> {
  await expect(page.getByTestId("prop-volume")).toContainText("8,000", {
    timeout: 30_000,
  });
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
}

/**
 * Click ONE face-pick node whose centroid z matches `z`, read off the
 * accessible name so the pick is deterministic rather than projection-dependent.
 * Dispatched straight to the node because several faces project UNDER the
 * top-left editor panel (the same reason `draft.spec.ts` does it).
 */
async function pickFaceAtZ(page: Page, z: number): Promise<void> {
  const nodes = page.locator('[data-testid^="draft-face-"]');
  await expect(nodes).toHaveCount(6, { timeout: 20_000 });
  const count = await nodes.count();
  for (let i = 0; i < count; i += 1) {
    const label = (await nodes.nth(i).getAttribute("aria-label")) ?? "";
    const nums = label.match(/-?\d+(?:\.\d+)?/g) ?? [];
    const got = Number.parseFloat(nums[nums.length - 1] as string);
    if (Number.isFinite(got) && Math.abs(got - z) < 0.5) {
      await nodes.nth(i).dispatchEvent("click");
      return;
    }
  }
  throw new Error(`no pickable face with centroid z ≈ ${z}`);
}

/** Every world-space vertex of a NAMED object's line geometry. */
async function namedLinePointCount(page: Page, name: string): Promise<number> {
  return page.evaluate((wanted: string) => {
    interface Attr {
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
    for (const uuid of order) {
      const scene = scenes[uuid];
      if (scene === undefined) continue;
      let total = 0;
      scene.traverse((node) => {
        if (node.name !== wanted) return;
        node.traverse((child) => {
          total += child.geometry?.attributes?.position?.count ?? 0;
        });
      });
      if (total > 0) return total;
    }
    return 0;
  }, name);
}

async function angleField(page: Page): Promise<number> {
  return Number.parseFloat(await page.getByTestId("draft-angle").inputValue());
}

/** Open the draft editor on the seeded cube, framed in iso. */
async function openDraft(page: Page): Promise<void> {
  await page.getByTestId("new-draft").click();
  await expect(page.getByTestId("draft-editor")).toBeVisible();
  await page.getByTestId("view-iso").click();
  await waitForCameraRest(page);
}

test.describe("CRAFT-10 — the draft taper gauge", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("a picked SIDE face grows a pivot and an arc; the TOP face does not", async ({
    page,
  }) => {
    const partId = await seedCubePart(page);
    await installSceneProbe(page);
    await page.goto(`/parts/${partId}`);
    await waitForCube(page);
    await openDraft(page);

    // NEGATIVE CONTROL FIRST, so "the gauge appeared" cannot be satisfied by a
    // component that renders unconditionally. The cube's TOP face (z = 20) is
    // parallel to the XY neutral plane, so there is no line where the two meet
    // and no draft to dimension — the honest picture is no instrument at all.
    await pickFaceAtZ(page, 20);
    await expect(page.getByTestId("draft-taper-count")).toHaveText(
      "1 face tapered",
    );
    await waitForFrames(page, 3);
    expect(await namedLinePointCount(page, "revolve-axis-line")).toBe(0);
    await expect(page.getByTestId("draft-angle-handle")).toHaveCount(0);

    // Now a SIDE face (centroid at mid-height), which DOES meet the neutral
    // plane — along its own bottom edge, which is the line the taper pivots on.
    await page.getByTestId("draft-pick-clear").click();
    await pickFaceAtZ(page, 10);
    await expect(page.getByTestId("draft-taper-count")).toHaveText(
      "1 face tapered",
    );
    await waitForFrames(page, 3);

    // The founder pair; `CRAFT10_SHOT` names the side. Taken HERE, before the
    // assertions, and deliberately: the BEFORE side of the pair is this same
    // flow against a tree with the gauge removed, where the assertions below
    // cannot pass — so a capture placed after them would never be written on
    // the side it is most needed.
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/craft10-draft-gauge-${process.env["CRAFT10_SHOT"] ?? "after"}-1280.png`,
    });

    expect(
      await namedLinePointCount(page, "revolve-axis-line"),
    ).toBeGreaterThan(6);
    await expect(page.getByTestId("draft-angle-handle")).toHaveCount(1);

    // The grip is a real slider that speaks the DEGREE grid, and its spoken
    // value is the SIGNED angle even though its `aria-valuenow` is a magnitude.
    const grip = page.getByTestId("draft-angle-handle");
    await expect(grip).toHaveAttribute("data-step", "1");
    await expect(grip).toHaveAttribute("aria-valuetext", "3°");
    // …and at 3 degrees it honestly draws NO ladder: see the drag case for the
    // other half of this pair, where the graduations appear as the taper grows.
    await expect(grip).toHaveAttribute("data-snap", "0");
  });

  test("dragging the taper grip moves the field and the drafted edge", async ({
    page,
  }) => {
    const partId = await seedCubePart(page);
    await installSceneProbe(page);
    await page.goto(`/parts/${partId}`);
    await waitForCube(page);
    await openDraft(page);
    await pickFaceAtZ(page, 10);
    await waitForFrames(page, 3);

    const grip = page.getByTestId("draft-angle-handle");
    const box = await grip.boundingBox();
    if (box === null) throw new Error("the draft grip has no box");
    const at = { x: box.x + box.width / 2, y: box.y + box.height / 2 };

    const before = await angleField(page);
    expect(before).toBeCloseTo(3, 6);

    await page.mouse.move(at.x, at.y);
    await page.mouse.down();
    await page.mouse.move(at.x + 80, at.y + 40, { steps: 12 });
    await page.mouse.move(at.x + 150, at.y + 75, { steps: 12 });
    await page.mouse.up();
    await waitForFrames(page, 3);

    const after = await angleField(page);
    expect(Math.abs(after - before)).toBeGreaterThan(1);
    // Never through zero, and never outside the kernel's open interval — the
    // sign is the Pull control's business and the field's, not the drag's.
    expect(Math.abs(after)).toBeGreaterThan(0);
    expect(Math.abs(after)).toBeLessThan(90);
    expect(Math.sign(after)).toBe(Math.sign(before));

    // THE LADDER APPEARS AS THE TAPER GROWS, and is honestly ABSENT at the
    // 3-degree default. `data-snap` carries what a drag will snap to — 0 when
    // no ladder is legible. At 3 degrees an arc on a 10 mm wall is under half a
    // millimetre long and there is genuinely nothing to rule against, so the
    // instrument degrades to the leader-and-number a drawing uses for exactly
    // that case; past ~15 degrees the graduations earn their room. Asserted as
    // a PAIR because either half alone is satisfied by a gauge that never
    // draws a ladder at all.
    const snap = Number(await grip.getAttribute("data-snap"));
    expect(Math.abs(after)).toBeGreaterThan(15);
    expect(snap).toBeGreaterThan(0);
    expect([1, 5, 10, 15, 30, 45, 90]).toContain(snap);

    // CONTRACT beta: released, the instrument stays where the drag left it.
    // A missing echo springs it back here and only here.
    await waitForFrames(page, 6);
    expect(await angleField(page)).toBeCloseTo(after, 6);
    const rest = await grip.boundingBox();
    if (rest === null) throw new Error("the draft grip lost its box");
    expect(Math.hypot(rest.x - box.x, rest.y - box.y)).toBeGreaterThan(8);
  });

  /**
   * DRAFT IS IN THE SAME FAMILY AS REVOLVE, and this case is here to say so.
   *
   * Both angular verbs build their spine with `angularTrack`, whose
   * tessellation is `ceil(|value| / 360 * 96)` segments — so the hit sleeve's
   * band list has a LENGTH that is a function of the value being dragged, and
   * shrinking the taper unmounts the bands at the seat end. That is the
   * mechanism behind the P0 fixed in `ParametricGauge`: capture taken on a band
   * dies when the arc re-tessellates past it, silently, with no
   * `lostpointercapture` to recover on.
   *
   * The GATE for that lives in `revolve-gauge.spec.ts` — one case, on the
   * shared component both verbs mount, rather than the same 60-second drag run
   * twice. What is asserted HERE is the thing that makes the revolve gate stand
   * for draft at all: that draft's band list really does shrink with its value.
   * If a future change makes draft's spine fixed-length, this fails, and the
   * honest response is to notice that the revolve case no longer covers it —
   * not to delete this.
   *
   * Measured: 22 bands at 80 degrees, 12 at 45, 3 at 10, 2 at 1.
   */
  test("the taper's hit sleeve re-tessellates with the angle", async ({
    page,
  }) => {
    const partId = await seedCubePart(page);
    await installSceneProbe(page);
    await page.goto(`/parts/${partId}`);
    await waitForCube(page);
    await openDraft(page);
    await pickFaceAtZ(page, 10);
    await waitForFrames(page, 3);

    const bands = page.locator(
      '[data-gauge="draft-angle"][data-testid*="sleeve"]',
    );
    const field = page.getByTestId("draft-angle");
    const countAt = async (deg: string): Promise<number> => {
      await field.fill(deg);
      await field.blur();
      await waitForFrames(page, 3);
      return bands.count();
    };

    const wide = await countAt("80");
    const narrow = await countAt("10");
    console.log(`[DRAFT-SLEEVE] 80 deg -> ${wide} bands, 10 deg -> ${narrow}`);
    // The band at index `narrow` and above have UNMOUNTED between these two
    // readings. A grab held on one of them is a grab whose capture host is
    // gone, which is the whole defect.
    expect(
      wide,
      "a wide taper must lay several bands, or the sleeve is a single chord " +
        "again and the arc is only grabbable at its point",
    ).toBeGreaterThan(8);
    expect(
      narrow,
      `the band list must shrink with the taper (80 deg: ${wide}, ` +
        `10 deg: ${narrow}) — that is why the revolve gate covers this mount`,
    ).toBeLessThan(wide);
  });
});
