/**
 * CRAFT-12 — THE DATUM SHEETS STAY CLICKABLE ON A LARGE BODY.
 *
 * The three plane sheets are what you aim at to start a sketch. On a 1600 mm
 * column their projected minor dimensions measured **8 / 13 / 10 px** before
 * the fix and **197 / 308 / 231 px** after — i.e. the affordance for the most
 * common action in the product had collapsed to a hairline on exactly the parts
 * that are hardest to model.
 *
 * ## Why the fixture has to be big, stated because it is the whole test
 *
 * On a 30 mm box the two legs are **byte-identical**: the small case hits the
 * size floor, so the fix changes nothing there. A spec written against a
 * convenient small fixture would therefore have passed before and after, which
 * is how this regression survived in the first place. The large body is not
 * incidental — it is the only fixture in which the assertion can fail.
 *
 * ## And why this does not reuse `plane-pick-framing.spec.ts`
 *
 * That spec is structurally blind here: it clicks `plane-pick-face` before
 * censusing, and the sheets render only while `!facePicking`, so it exercises
 * the one sub-state in which no sheet exists at all. Its greenness says nothing
 * about sheet size. This one never touches that control.
 *
 * ## What is measured
 *
 * The sheets are raycast meshes with NO DOM presence — `elementFromPoint` and
 * `boundingBox()` are both blind to them — so the scene-graph name
 * (`datum-sheet-<plane>`) is the only way to ask how big the thing you have to
 * click is. `sceneProject.ts` projects the named group's world box through the
 * live camera and reports the minor screen dimension.
 */
import { expect, test, type Page } from "./fixtures";
import { installSceneProbe, waitForCameraStill } from "./invariants";
import { createFeature, rectangleSketch } from "./partSeed";
import { createPartViaApi, seedSession, waitForFrames } from "./support";
import { describeProjected, expectProjected } from "./sceneProject";

test.use({ viewport: { width: 1280, height: 800 } });

const PLANES = ["XY", "XZ", "YZ"] as const;

/**
 * The floor, CSS px.
 *
 * Not the 197/308/231 the fix produced — pinning a measurement makes the gate
 * fail on any future re-framing that is perfectly fine. 44 is the touch target
 * floor and is the smallest number that still means "a person can hit this";
 * the pre-fix readings were 8/13/10, so the gate has a 4x margin below the
 * measured good state and a 4x margin above the measured bad one.
 */
const SHEET_MINOR_FLOOR_PX = 44;

/** Seed a part whose body is `height` mm tall on a 40 mm square footprint. */
async function seedColumn(page: Page, height: number): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, `Column ${height}`);
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: {
      type: "sketch",
      version: 1,
      params: rectangleSketch(0, 0, 40, 40),
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
        distance_mm: height,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  return part.id;
}

/**
 * Open the plane-pick stage and leave it there.
 *
 * NOTHING clicks `plane-pick-face`. The sheets render only while
 * `!facePicking`, so that one click is the difference between measuring the
 * affordance and measuring its absence.
 */
async function openPlanePick(page: Page, partId: string): Promise<void> {
  await page.goto(`/parts/${partId}`);
  const cue = page.getByTestId("nav-cue-dismiss");
  if (await cue.isVisible().catch(() => false)) {
    await cue.click();
    await expect(page.getByTestId("nav-cue")).toHaveCount(0);
  }
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 60_000,
  });
  await page.getByTestId("new-sketch").click();
  await expect(page.getByTestId("plane-XY")).toBeVisible();
  // POSITION, not direction. Entering the plane pick eases the camera out to a
  // vantage whose STANDOFF depends on the body, along a direction that barely
  // changes — so a direction-only settle (`waitForCameraRest`) returned while
  // the 1600 mm column's camera was still sliding, and its sheets measured
  // 196.6-198.8 px across runs of one build against a 1 px agreement bar. A
  // measurement taken mid-slide measures the camera, not the sheet.
  await waitForCameraStill(page);
  await waitForFrames(page, 3);
}

async function sheetMinors(page: Page): Promise<Record<string, number>> {
  const out: Record<string, number> = {};
  for (const plane of PLANES) {
    const seen = await expectProjected(page, `datum-sheet-${plane}`);
    console.log(`[sheets] ${describeProjected(`datum-sheet-${plane}`, seen)}`);
    out[plane] = seen.minor;
  }
  return out;
}

test.describe("CRAFT-12 — datum sheet size", () => {
  test("on a 1600 mm column every sheet is still a usable target", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const partId = await seedColumn(page, 1600);
    await openPlanePick(page, partId);

    const minors = await sheetMinors(page);
    console.log(
      `[sheets] 1600 mm column minors: ` +
        PLANES.map((p) => `${p}=${(minors[p] as number).toFixed(1)}`).join(
          ", ",
        ),
    );

    for (const plane of PLANES) {
      const minor = minors[plane] as number;
      expect(
        minor,
        `the ${plane} datum sheet projects to ${minor.toFixed(1)} px on its ` +
          `minor axis on a 1600 mm body — below the ${SHEET_MINOR_FLOOR_PX} px ` +
          `floor, the thing you click to start a sketch is a hairline`,
      ).toBeGreaterThanOrEqual(SHEET_MINOR_FLOOR_PX);
    }
  });

  test("sheet size is INDEPENDENT of body size — a 53x range projects the same", async ({
    page,
  }) => {
    // MEASURED, and it turned out stronger than the claim it was written to
    // check. The premise was "a small fixture hides the regression because it
    // hits the floor"; the reading is that a 30 mm box and a 1600 mm column
    // project the sheets to the SAME numbers to a tenth of a pixel — 196.6 /
    // 308.1 / 230.9 both times, across a 53x range of body size.
    //
    // That independence IS the fix, and it is a better assertion than a floor:
    // the defect was sheet size tracking the BODY (8/13/10 px on the column
    // against ~197/308/231 on a small part), so "the two fixtures agree" fails
    // the instant that coupling comes back, and fails on the small fixture too
    // — which is what makes this case worth having beside the large one rather
    // than a weaker copy of it.
    await installSceneProbe(page);
    const smallPart = await seedColumn(page, 30);
    await openPlanePick(page, smallPart);
    const small = await sheetMinors(page);

    const largePart = await seedColumn(page, 1600);
    await openPlanePick(page, largePart);
    const large = await sheetMinors(page);

    console.log(
      `[sheets] 30 mm vs 1600 mm: ` +
        PLANES.map(
          (p) =>
            `${p} ${(small[p] as number).toFixed(1)}/${(large[p] as number).toFixed(1)}`,
        ).join(", "),
    );

    for (const plane of PLANES) {
      const a = small[plane] as number;
      const b = large[plane] as number;
      // Both clear the floor — the property the large case asserts.
      expect(a).toBeGreaterThanOrEqual(SHEET_MINOR_FLOOR_PX);
      expect(b).toBeGreaterThanOrEqual(SHEET_MINOR_FLOOR_PX);
      // And they AGREE, which is the property that says the coupling is gone.
      // 1 px of tolerance, not zero: the two parts are framed by the same fit
      // arithmetic but not by the same float history.
      expect(
        Math.abs(a - b),
        `the ${plane} sheet projects to ${a.toFixed(1)} px on a 30 mm body ` +
          `and ${b.toFixed(1)} px on a 1600 mm one — sheet size has started ` +
          `tracking the body again, which is the regression in the direction ` +
          `a small fixture cannot see`,
      ).toBeLessThan(1);
    }
  });

  test("NEGATIVE CONTROL: the measurement can report a hairline", async ({
    page,
  }) => {
    // Both assertions above passed from their first run. This drives the SAME
    // measurement toward the failing end by zooming far out, and demands it
    // report a number below the floor — so the floor is a gate rather than a
    // number that has never been near anything.
    //
    // Deliberately NOT done by shrinking the sheet (there is no seam for that
    // without touching app code) and NOT by asserting on a camera distance:
    // what is under test is whether `projectNamed` tracks the thing getting
    // smaller on screen, which is the property the real assertions lean on.
    await installSceneProbe(page);
    const partId = await seedColumn(page, 30);
    await openPlanePick(page, partId);

    const before = await sheetMinors(page);
    const canvas = page.getByTestId("viewport");
    const box = await canvas.boundingBox();
    if (box === null) throw new Error("no viewport box");
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    for (let i = 0; i < 40; i += 1) {
      await page.mouse.wheel(0, 240);
    }
    // A zoom is a pure dolly: the one move a direction-only settle cannot see.
    await waitForCameraStill(page);
    await waitForFrames(page, 3);
    const after = await sheetMinors(page);

    console.log(
      `[sheets] control — XY ${(before["XY"] as number).toFixed(1)} -> ` +
        `${(after["XY"] as number).toFixed(1)} px after zooming out`,
    );
    expect(
      after["XY"] as number,
      "zooming far out did not shrink the measured sheet, so the floor " +
        "assertions above are reading something that does not track the screen",
    ).toBeLessThan(before["XY"] as number);
    expect(
      after["XY"] as number,
      "the measurement never went below the floor even zoomed far out, so " +
        "the floor has never been near a failing value",
    ).toBeLessThan(SHEET_MINOR_FLOOR_PX);
  });
});
