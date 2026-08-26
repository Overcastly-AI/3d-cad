/**
 * FB-9 — "the extruded is not on the same plane" (founder photo: a base-plane
 * sketch, ADD, NORMAL, 10 mm).
 *
 * THE GATE THE TICKET ASKED FOR, AND NEVER HAD. The report is a claim about
 * PLACEMENT — where the swept solid is drawn relative to the plane it was drawn
 * on — and every gate that existed answered a different question: the geometry
 * suite proves the kernel's volume and extents (exact, and never in doubt here),
 * `plane.test.ts` and `extrudeGhost.test.ts` pin the two pure seams the fix
 * touched, and the pixel specs count lit colours, which cannot tell a body in
 * the wrong place from a camera pointed somewhere else. Nothing asserted the
 * composition: sketch plane, live ghost and committed body, all in one frame,
 * in the frame the user is looking at.
 *
 * The mechanism the founder photographed was a frame mismatch, closed by FB-7c
 * (`528a078`): `resolveSpecBasis` handed the renderer a basis stated in the
 * kernel's Z-up world for three of its four branches and a scene-frame one for
 * the fourth, so the ink, the datum sheet and the ghost stood 90 degrees away
 * from the body the same sketch produced. Measured then: body at scene
 * y in [0,10], its own ghost at z in [0,10].
 *
 * So the assertion is the founder's sentence, made numeric:
 *
 *   1. the ghost sits ON the sketch plane and grows the way the body will;
 *   2. the committed body occupies the SAME box as the ghost that promised it;
 *   3. both are seated on the plane the sketch was drawn on (scene y = 0 for
 *      XY), not merely 10 mm tall SOMEWHERE.
 *
 * (3) is what makes it a real gate rather than a tautology: a solid rotated
 * into the wrong frame still measures 10 mm along its own sweep, which is
 * exactly why the defect survived a suite that only ever asked for extents.
 */
import { expect, test, type Page } from "./fixtures";
import { installSceneProbe, namedWorldBox, type WorldBox } from "./invariants";
import { createPartViaApi, seedSession } from "./support";

/** Sweep distance under test, mm — the founder's own 10. */
const DISTANCE_MM = 10;

/**
 * Placement tolerance, mm. The ghost is a three.js `ExtrudeGeometry` over the
 * solved profile; the body is an OCCT prism tessellated to GLB. Both are planar
 * and share their profile exactly, so the only slack is float32 in the mesh
 * buffer — this is three orders of magnitude above that and still ~1/500 of the
 * distance being measured, so a frame error (which is 90 degrees, not microns)
 * cannot hide under it.
 */
const PLACE_TOL_MM = 0.05;

/** Enter sketch mode on a datum plane. */
async function enterSketch(page: Page, plane: "XY" | "XZ" | "YZ") {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId(`plane-${plane}`).click();
  await expect(page.getByTestId("sketch-step")).toHaveText(`On ${plane}`);
}

/** Draw a rectangle (two clicks) and persist it as Sketch1. */
async function sketchRectangle(page: Page): Promise<void> {
  await page.keyboard.press("r");
  await expect(page.getByTestId("tool-rect")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.mouse.click(650, 420);
  await page.mouse.move(980, 640);
  await page.mouse.click(980, 640);
  await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
}

/** A box's extent on one axis. */
function span(box: WorldBox, axis: 0 | 1 | 2): number {
  return box.max[axis] - box.min[axis];
}

/** A corner, printed to 3 dp — the evidence tail this spec exists to produce. */
function fmt(v: readonly [number, number, number]): string {
  return `[${v.map((n) => n.toFixed(3)).join(", ")}]`;
}

test.describe("FB-9 — the extrude lands on the plane it was drawn on", () => {
  test("ghost, body and sketch plane are one solid in one frame", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "FB-9 plate");
    await page.goto(`/parts/${part.id}`);

    await enterSketch(page, "XY");
    await sketchRectangle(page);

    // Open the extrude editor. The seeded form is 10 mm / add / normal, and
    // the live ghost is on screen before anything is saved.
    await page.getByTestId("new-extrude").click();
    await expect(page.getByTestId("extrude-distance")).toHaveValue("10");
    await expect(page.getByTestId("extrude-preview-active")).toHaveAttribute(
      "data-distance-mm",
      String(DISTANCE_MM),
    );

    const ghost = await namedWorldBox(page, "extrude-ghost");
    expect(
      ghost,
      "the live ghost has a node in the scene graph",
    ).not.toBeNull();
    const ghostBox = ghost as WorldBox;
    expect(ghostBox.vertices).toBeGreaterThan(0);

    // (1) The ghost is SEATED on the sketch plane and grows away from it.
    // An XY sketch is the ground plane in a Y-up scene, so the sweep runs up
    // scene +Y from y=0. THIS is the assertion the old defect failed: it put
    // the ghost's 10 mm along scene +Z and left it lying through the grid.
    expect(ghostBox.min[1]).toBeCloseTo(0, 2);
    expect(ghostBox.max[1]).toBeCloseTo(DISTANCE_MM, 2);
    // …and the profile itself is FLAT in that plane, i.e. the other two axes
    // carry the rectangle, not the sweep.
    expect(span(ghostBox, 0)).toBeGreaterThan(1);
    expect(span(ghostBox, 2)).toBeGreaterThan(1);

    // Commit it.
    await page.getByTestId("extrude-distance").press("Enter");
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("prop-extents")).toContainText("×");

    // The GLB arrives, is parsed and is mounted a few frames after the tree
    // reports Solved, so poll rather than sample once.
    await expect
      .poll(
        async () => (await namedWorldBox(page, "model-body"))?.vertices ?? 0,
        {
          timeout: 30_000,
        },
      )
      .toBeGreaterThan(0);
    const bodyBox = (await namedWorldBox(page, "model-body")) as WorldBox;

    // The measurement, printed. A gate that only says pass/fail leaves the next
    // reader re-deriving what "on the same plane" came to numerically — and the
    // ticket was filed from a photograph, so the numbers are the answer to it.
    console.log(
      [
        `FB-9 scene boxes (mm, three.js Y-up):`,
        `  ghost min ${fmt(ghostBox.min)}  max ${fmt(ghostBox.max)}`,
        `  body  min ${fmt(bodyBox.min)}  max ${fmt(bodyBox.max)}`,
      ].join("\n"),
    );
    expect(bodyBox.vertices).toBeGreaterThan(0);

    // (3) The BODY is seated on the same plane, growing the same way.
    expect(bodyBox.min[1]).toBeCloseTo(0, 2);
    expect(bodyBox.max[1]).toBeCloseTo(DISTANCE_MM, 2);

    // (2) …and it is the solid the ghost promised, in the place it promised —
    // all three axes, both ends. The founder's sentence, as six numbers.
    for (const axis of [0, 1, 2] as const) {
      expect(
        Math.abs(bodyBox.min[axis] - ghostBox.min[axis]),
        `body/ghost min disagree on axis ${axis}: ${bodyBox.min[axis]} vs ${ghostBox.min[axis]}`,
      ).toBeLessThan(PLACE_TOL_MM);
      expect(
        Math.abs(bodyBox.max[axis] - ghostBox.max[axis]),
        `body/ghost max disagree on axis ${axis}: ${bodyBox.max[axis]} vs ${ghostBox.max[axis]}`,
      ).toBeLessThan(PLACE_TOL_MM);
    }
  });
});
