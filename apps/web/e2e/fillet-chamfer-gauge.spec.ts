/**
 * CRAFT-9a — THE FILLET AND CHAMFER GAUGES, AND THE THING THAT MAKES THEM MORE
 * THAN SLIDERS.
 *
 * Direction §8.4: *"A gauge whose drag changes a number and not the model is
 * worse than the form it replaces."* So the load-bearing case in this file is
 * not "the field moved" — it is **the field moved AND the drawn result moved**,
 * measured as two independent readings that must both change: the editor's own
 * input value, and the world bounding box of the `fillet-preview` /
 * `chamfer-preview` subtree. The preview subtree is measured rather than the
 * whole gauge deliberately: the arrow's length tracks the value too, so a
 * preview frozen at the opening radius would sail through a whole-gauge check.
 *
 * The other three, from §9's per-verb list:
 *
 *  · `document.elementFromPoint` down the projected track reaches the gauge at
 *    >= 12 of 16 offsets — the affordance and the hit target are one thing;
 *  · arrow keys step the same value a drag moves;
 *  · **contract beta** — release the pointer and the instrument STAYS where you
 *    dragged it. This is the one that catches a missing echo, and it fires on
 *    `pointerup`, which is after every screenshot anybody would take.
 *
 * **No `force: true` anywhere in this file, and there must never be.** Every
 * pick here is a real `page.mouse` event at a pixel chosen from the drawn
 * geometry; if nothing is listening there, nothing happens, which is exactly
 * the failure this class of spec exists to see.
 */
import { expect, test, type Page } from "./fixtures";
import {
  gripCentre,
  projectedSpine,
  reach,
  REACH_FLOOR,
  SAMPLES,
  shaftMidpoint,
  type Point,
} from "./gaugeReach";
import {
  installSceneProbe,
  namedWorldBox,
  waitForCameraRest,
} from "./invariants";
import { seedCube } from "./partSeed";
import {
  clickForReal,
  createPartViaApi,
  expectSeatsSettled,
  SCREENSHOT_DIR,
  seedSession,
  waitForFrames,
} from "./support";

/**
 * The shortest projected track this spec will accept as a drag target.
 *
 * Not a tolerance — a precondition. At iso, one of a cube's top edges points
 * its bisector nearly at the camera, and a track with no screen direction has
 * no axis to walk; choosing an edge by index would make the whole file's
 * verdict depend on which edge `body.edges()` happened to yield first.
 */
const MIN_TRACK_PX = 70;

/** The radius/distance the gauges open at here — big enough to aim at. */
const OPENING_MM = 8;

async function seedCubePart(page: Page): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Gauge cube");
  await seedCube(page, account.token, part.id);
  return part.id;
}

async function waitForCube(page: Page): Promise<void> {
  await expect(page.getByTestId("prop-volume")).toContainText("8,000", {
    timeout: 30_000,
  });
}

/** Distance between two page points. */
function span(a: Point, b: Point): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

/**
 * Pick an edge whose gauge has a readable track, and say which one.
 *
 * Clicks candidate edges in turn with a REAL mouse (`clickForReal` refuses a
 * zero-area or occluded target before it presses), measures the projected
 * track, and unpicks anything too foreshortened to drag. Returns the index of
 * the edge it settled on.
 */
async function pickDraggableEdge(page: Page, gaugeId: string): Promise<number> {
  const nodes = page.locator('[data-testid^="edge-pick-"]');
  await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
  const count = await nodes.count();
  const selected = page.getByTestId("selected-count");
  for (let i = 0; i < count; i += 1) {
    const testId = await nodes.nth(i).getAttribute("data-testid");
    if (testId === null) continue;
    await clickForReal(page, testId);
    // The mark re-seats itself over several frames after a camera move
    // (`useEdgeMarkAnchors` budgets its hit-tests), so a click can land where
    // the diamond WAS. The pick is confirmed by the editor's own count, not by
    // the click returning — measured here: the first attempt after `view-iso`
    // routinely misses and the same mark takes the second.
    if (!(await selected.filter({ hasText: "1 edge" }).isVisible())) continue;
    const handle = page.getByTestId(`${gaugeId}-handle`);
    if ((await handle.count()) === 0) {
      // No anchor on this edge (the seater refused) — put it back.
      await clickForReal(page, testId);
      continue;
    }
    await expect(handle).toBeVisible({ timeout: 10_000 });
    const { seat } = await projectedSpine(page, gaugeId);
    const apex = await gripCentre(page, gaugeId);
    if (span(seat, apex) >= MIN_TRACK_PX) return i;
    await clickForReal(page, testId);
  }
  throw new Error(`no edge gave ${gaugeId} a track of ${MIN_TRACK_PX}px`);
}

/** One unreachable mark, and the thing that is on top of it. */
interface Cover {
  /** `edge-pick-<n>`. */
  mark: string;
  /** The nearest named ancestor of whatever `elementFromPoint` resolved to. */
  by: string;
  /** Whether that something belongs to THIS gauge — the sleeve, grip or tag. */
  gauge: boolean;
}

/**
 * Which edge-pick marks a pointer aimed at their own centre does NOT reach,
 * AND WHAT IS ON TOP OF EACH ONE.
 *
 * Some are unreachable for reasons that have nothing to do with this item — a
 * mark whose edge is buried behind the body, two marks that overlap at a
 * silhouette corner — so a bare "4 of 12 are covered" is consistent with the
 * gauge covering four and with it covering none, and those are different
 * products. The original reading of that was a BEFORE/AFTER pair, and the
 * subtraction is what went wrong: it attributes to the gauge every mark whose
 * reachability changed for ANY reason between the two readings, and one such
 * reason drifts on its own schedule (see `expectSeatsSettled` at both call
 * sites). So each reading now names its own occluder and the verdict is read
 * off the AFTER set directly — `gauge` is the guarantee, the delta is kept as
 * a second, independently-derived opinion.
 */
async function coveredMarks(page: Page, gaugeId: string): Promise<Cover[]> {
  const nodes = page.locator('[data-testid^="edge-pick-"]');
  const count = await nodes.count();
  const covered: Cover[] = [];
  for (let i = 0; i < count; i += 1) {
    const testId = await nodes.nth(i).getAttribute("data-testid");
    if (testId === null) continue;
    const box = await nodes.nth(i).boundingBox();
    if (box === null) continue;
    const hit = await page.evaluate(
      ({
        x,
        y,
        id,
        gauge,
      }: {
        x: number;
        y: number;
        id: string;
        gauge: string;
      }) => {
        const el = document.elementFromPoint(x, y);
        if (el === null) return { own: false, by: "(nothing)", gauge: false };
        const named = el.closest("[data-testid]");
        return {
          own: el.closest(`[data-testid="${id}"]`) != null,
          by:
            (named as HTMLElement | null)?.dataset["testid"] ??
            el.tagName.toLowerCase(),
          // The instrument's own parts, by the hook `ParametricGauge` puts on
          // them for exactly this question: `data-gauge` on the grip and every
          // sleeve band, `<id>-readout` / `-steps` on the tag.
          gauge:
            el.closest(`[data-gauge="${gauge}"], [data-testid^="${gauge}-"]`) !=
            null,
        };
      },
      {
        x: box.x + box.width / 2,
        y: box.y + box.height / 2,
        id: testId,
        gauge: gaugeId,
      },
    );
    if (!hit.own) covered.push({ mark: testId, by: hit.by, gauge: hit.gauge });
  }
  return covered;
}

/** `edge-pick-3 (by viewport)`, for a message somebody has to read in CI. */
function describeCovers(covers: readonly Cover[]): string {
  return covers.length === 0
    ? "none"
    : covers.map(({ mark, by }) => `${mark} (by ${by})`).join(", ");
}

/** The preview subtree's world box, as a comparable string. */
async function previewExtent(page: Page, name: string): Promise<string> {
  const box = await namedWorldBox(page, name);
  if (box === null || box.vertices === 0) {
    throw new Error(`no drawn preview under "${name}"`);
  }
  return [...box.min, ...box.max].map((v) => v.toFixed(4)).join(",");
}

/** Open a fillet or chamfer editor on the seeded cube, in pick mode. */
async function openModifyEditor(
  page: Page,
  verb: "fillet" | "chamfer",
): Promise<void> {
  await page.getByTestId(`new-${verb}`).click();
  await expect(page.getByTestId(`${verb}-editor`)).toBeVisible();
  const field = verb === "fillet" ? "fillet-radius" : "chamfer-distance";
  await page.getByTestId(field).fill(String(OPENING_MM));
  await page.getByTestId(`${verb}-mode-pick`).click();
  await page.getByTestId("view-iso").click();
  await waitForCameraRest(page);
}

/** The editor's own number, as a number. */
async function fieldValue(page: Page, testId: string): Promise<number> {
  return Number.parseFloat(await page.getByTestId(testId).inputValue());
}

interface VerbFixture {
  verb: "fillet" | "chamfer";
  gaugeId: string;
  field: string;
  previewName: string;
}

const VERBS: VerbFixture[] = [
  {
    verb: "fillet",
    gaugeId: "fillet-radius",
    field: "fillet-radius",
    previewName: "fillet-preview",
  },
  {
    verb: "chamfer",
    gaugeId: "chamfer-distance",
    field: "chamfer-distance",
    previewName: "chamfer-preview",
  },
];

for (const { verb, gaugeId, field, previewName } of VERBS) {
  test.describe(`${verb} gauge`, () => {
    test(`a drag moves the number AND redraws the ${verb} preview`, async ({
      page,
    }) => {
      await installSceneProbe(page);
      const partId = await seedCubePart(page);
      await page.goto(`/parts/${partId}`);
      await waitForCube(page);
      await openModifyEditor(page, verb);
      await pickDraggableEdge(page, gaugeId);

      const beforeValue = await fieldValue(page, field);
      const beforeDrawn = await previewExtent(page, previewName);
      expect(beforeValue).toBeCloseTo(OPENING_MM, 3);

      // THE REACH, before the drag: a track you cannot take hold of is the
      // defect CRAFT-7 measured on extrude (2 of 16), and it is the defect this
      // mount would inherit for free if the sleeve were not along the track.
      const walked = await reach(page, gaugeId);
      console.log(
        `CRAFT-9a ${verb} reach: ${walked.hits}/${SAMPLES} — ${walked.resolved.join(", ")}`,
      );
      expect(
        walked.hits,
        `the drawn track must BE the target: ${walked.hits}/${SAMPLES} sample ` +
          `points resolved to the gauge (${walked.resolved.join(", ")})`,
      ).toBeGreaterThanOrEqual(REACH_FLOOR);

      // A real drag from the MIDDLE of the drawn shaft — not from the grip, and
      // with no locator: the pixel is chosen from the geometry the user sees.
      const mid = await shaftMidpoint(page, gaugeId);
      const seat = (await projectedSpine(page, gaugeId)).seat;
      const apex = await gripCentre(page, gaugeId);
      // Pull ALONG the track, away from the seat, so the gesture grows the
      // value whichever way the bisector happens to project.
      const ux = (apex.x - seat.x) / span(seat, apex);
      const uy = (apex.y - seat.y) / span(seat, apex);

      await page.mouse.move(mid.x, mid.y);
      await page.mouse.down();
      for (let step = 1; step <= 6; step += 1) {
        await page.mouse.move(mid.x + ux * step * 10, mid.y + uy * step * 10);
      }
      const duringGrip = await gripCentre(page, gaugeId);
      await page.mouse.up();

      // BOTH readings move. The field alone is the slider this item exists not
      // to ship; the drawn extent alone could move because the arrow grew.
      await expect
        .poll(() => fieldValue(page, field), {
          message:
            "a drag from the middle of the drawn shaft must move the value",
          timeout: 10_000,
        })
        .not.toBeCloseTo(beforeValue, 3);
      const afterValue = await fieldValue(page, field);
      const afterDrawn = await previewExtent(page, previewName);
      expect(
        afterDrawn,
        `the ${verb} preview must redraw at the dragged value ` +
          `(${beforeValue} -> ${afterValue}); it did not move`,
      ).not.toBe(beforeDrawn);

      // CONTRACT BETA. The gauge draws `live ?? value` and clears `live` on
      // pointer-up, so an editor that takes `onChange` without echoing its
      // state back leaves the arrow snapping to its opening length the instant
      // you let go — while the rail field shows the number you dragged to. The
      // grip is where that shows: it must still be where the pointer left it.
      await expect
        .poll(async () => span(await gripCentre(page, gaugeId), duringGrip), {
          message:
            "contract beta: releasing the pointer must leave the instrument " +
            "where the drag put it, not back at its opening length",
          timeout: 10_000,
        })
        .toBeLessThanOrEqual(6);
      const settled = await gripCentre(page, gaugeId);
      expect(
        span(settled, mid),
        "the grip must have travelled — otherwise the drag did nothing and " +
          "contract beta passes vacuously",
      ).toBeGreaterThan(20);
    });

    test("arrow keys step the same value the drag moves", async ({ page }) => {
      await installSceneProbe(page);
      const partId = await seedCubePart(page);
      await page.goto(`/parts/${partId}`);
      await waitForCube(page);
      await openModifyEditor(page, verb);
      await pickDraggableEdge(page, gaugeId);

      const before = await fieldValue(page, field);
      const drawnBefore = await previewExtent(page, previewName);
      await page.getByTestId(`${gaugeId}-handle`).focus();
      await page.keyboard.press("ArrowUp");

      // The document unit's own 0.5 mm step, landing on its own grid — the
      // same increment an extrude drag snaps to, because both read `SNAP_MM`.
      await expect
        .poll(() => fieldValue(page, field), { timeout: 10_000 })
        .toBeCloseTo(before + 0.5, 3);
      // AND THE SYNCHRONISATION IS WRITTEN DOWN, because the two readings live
      // on different clocks: the poll above settles on the editor's INPUT — DOM
      // — while `previewExtent` measures object matrices in a DEMAND-RENDERED
      // scene, which are stale until r3f runs a frame. Nothing connected them,
      // so the assertion was resolved by whichever won the race, and the race
      // was being lost quietly on a fast machine (measured here 2/2: the box
      // still read the opening 8 mm, `-0,0,-8, 8,20,0`, a step after the field
      // said 8.5) while a loaded CI shard's slower round trips handed the
      // renderer the time and it passed. An accidental settle is a latent flake
      // whether or not anyone has tripped it — so state the wait.
      await waitForFrames(page);
      expect(
        await previewExtent(page, previewName),
        "a keyed step must redraw the preview exactly as a drag does — a " +
          "keyboard path that moves only the number is the same defect",
      ).not.toBe(drawnBefore);

      await page.keyboard.press("ArrowDown");
      await expect
        .poll(() => fieldValue(page, field), { timeout: 10_000 })
        .toBeCloseTo(before, 3);
    });

    test("the gauge covers ONLY the mark it stands on", async ({ page }) => {
      // The sleeve is a transparent DOM band stacked ABOVE the edge-pick marks
      // (29..22 against 17..0), so mounting it into a live pick session is the
      // one way this item could make the product worse: edges you can see and
      // cannot pick. MEASURED here rather than assumed, with a floor, because
      // "it did not seem to break anything" is how a band creeps across a
      // scene one release at a time.
      //
      // The honest result, pinned so a regression is legible: the gauge's seat
      // IS the picked edge's midpoint, which is where that edge's own diamond
      // sits, so the seated edge's mark goes under the sleeve. Every OTHER mark
      // stays reachable, and the seated edge is still removable through the
      // editor's Clear — the selection is never trapped.
      await installSceneProbe(page);
      const partId = await seedCubePart(page);
      await page.goto(`/parts/${partId}`);
      await waitForCube(page);
      await openModifyEditor(page, verb);
      // THE CONTROL: with pick mode armed and nothing picked yet, no gauge is
      // mounted. Whatever is unreachable here is unreachable for reasons that
      // predate this item.
      //
      // AND THE WAIT IS PART OF THE CONTROL, not tidiness. A mark's
      // reachability is decided by the burial classification in
      // `useEdgeMarkAnchors`, which is drained by a rotating per-frame budget
      // and announces its own completion on `data-edge-mark-seats`; measured
      // convergence after a camera move is 16-21 s quiet and up to 31 s under
      // load (see `SEAT_SETTLE_TIMEOUT_MS`). `waitForCameraRest` above waits
      // for the CAMERA and says nothing about that pass, so a BEFORE reading
      // taken without this line is a half-drained census — and since the AFTER
      // reading is taken seconds later, through a pick, every mark the pass
      // buried in between shows up in the subtraction as work the gauge did.
      // That is exactly how this case went red on CI at 894c6f3 with a sleeve
      // that had not moved: `before [7, 8]` against `after [0, 7, 8, 10]`,
      // where edge-pick-10 is buried behind the body and is covered by the
      // CANVAS in both readings once the pass has drained.
      await expectSeatsSettled(page, `${verb} marks, no gauge`);
      const before = await coveredMarks(page, gaugeId);
      const first = await pickDraggableEdge(page, gaugeId);
      await expect(page.getByTestId("selected-count")).toContainText("1 edge");
      await expectSeatsSettled(page, `${verb} marks, gauge mounted`);
      const after = await coveredMarks(page, gaugeId);

      const nodes = page.locator('[data-testid^="edge-pick-"]');
      const count = await nodes.count();
      const byGauge = after.filter((cover) => cover.gauge);
      const beforeMarks = before.map(({ mark }) => mark);
      const added = after.filter(({ mark }) => !beforeMarks.includes(mark));
      console.log(
        `CRAFT-9a ${verb} mark cover: ${before.length}/${count} before ` +
          `[${describeCovers(before)}], ${after.length}/${count} after ` +
          `[${describeCovers(after)}]; the gauge itself covers ` +
          `[${describeCovers(byGauge)}]`,
      );

      // THE GUARANTEE, attributed rather than subtracted: of everything a
      // pointer cannot reach with the gauge up, at most ONE mark has a piece of
      // the gauge on top of it — its own seat. This is the assertion that says
      // what the product promises, and unlike the delta it cannot be moved by
      // anything the gauge does not own.
      expect(
        byGauge.length,
        `the gauge may take at most the mark it stands on; it is on top of ` +
          `${byGauge.length} (${describeCovers(byGauge)}) — after ` +
          `[${describeCovers(after)}]`,
      ).toBeLessThanOrEqual(1);

      // And the second opinion, from a different derivation: with both censuses
      // taken on a settled pass, nothing but the gauge can change between them,
      // so the delta must agree with the attribution above. Two readings that
      // disagree mean one of them is measuring something nobody named — which
      // is the state this case was in — so it refuses rather than guessing.
      expect(
        added.map(({ mark }) => mark).sort(),
        `the marks that became unreachable (${describeCovers(added)}) must be ` +
          `exactly the marks the gauge is on top of (${describeCovers(byGauge)})`,
      ).toEqual(byGauge.map(({ mark }) => mark).sort());

      // And a real click on a mark that is NOT the seat still picks.
      const other = (first + 1) % count;
      const testId = await nodes.nth(other).getAttribute("data-testid");
      await clickForReal(page, testId as string);
      await expect(page.getByTestId("selected-count")).toContainText(
        "2 edges picked",
      );

      // The seated edge is never trapped: Clear empties the selection, which
      // also retires the gauge that was covering its mark.
      await page.getByTestId(`${verb}-pick-clear`).click();
      await expect(page.getByTestId("selected-count")).toHaveText(
        "No edges picked",
      );
      await expect(page.getByTestId(`${gaugeId}-sleeve`)).toHaveCount(0);
    });

    test(`the ${verb} gauge leaves with its command`, async ({ page }) => {
      await installSceneProbe(page);
      const partId = await seedCubePart(page);
      await page.goto(`/parts/${partId}`);
      await waitForCube(page);
      await openModifyEditor(page, verb);
      await pickDraggableEdge(page, gaugeId);
      await expect(page.getByTestId(`${gaugeId}-sleeve`)).toHaveCount(1);

      await page.keyboard.press("Escape");
      await expect(page.getByTestId(`${verb}-editor`)).toHaveCount(0);
      await expect(page.getByTestId(`${gaugeId}-sleeve`)).toHaveCount(0);
      // And the override was cleared, so the NEXT open seeds from its own
      // default rather than from the last drag — anchor B, the line everyone
      // forgets, which is silent until somebody notices the wrong default.
      await page.getByTestId(`new-${verb}`).click();
      await expect(page.getByTestId(field)).toHaveValue(
        verb === "fillet" ? "2" : "1",
      );
    });
  });
}

test.describe("small laptop (1280x800) — founder capture", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("fillet and chamfer gauges, drawn on a picked edge", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const partId = await seedCubePart(page);
    await page.goto(`/parts/${partId}`);
    await waitForCube(page);

    await openModifyEditor(page, "fillet");
    await pickDraggableEdge(page, "fillet-radius");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/craft9a-fillet-gauge-after-laptop.png`,
    });

    // Clear before switching verbs. A closed pick session is REMEMBERED (the
    // preselect store re-seeds the next modify command with it), so opening
    // chamfer straight after would arrive with the fillet's edge already
    // picked and its gauge already standing on that edge's own mark — correct
    // product behaviour, and not the state this capture is of.
    await page.getByTestId("fillet-pick-clear").click();
    await page.keyboard.press("Escape");
    await openModifyEditor(page, "chamfer");
    await pickDraggableEdge(page, "chamfer-distance");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/craft9a-chamfer-gauge-after-laptop.png`,
    });

    // The viewport still owns the width — chrome recedes (design mandate #3).
    const box = await page.getByTestId("viewport").boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(560);
  });
});
