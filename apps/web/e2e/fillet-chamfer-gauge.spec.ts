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
 *  · **contract beta** — release the pointer and the instrument still SHOWS
 *    what you dragged it to. This is the one that catches a missing echo, and
 *    it fires on `pointerup`, which is after every screenshot anybody would
 *    take. Read as the value the gauge announces and the world length it draws
 *    at, never as a page coordinate; the block itself says why, with the
 *    52.7 px that taught us.
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

/**
 * How long after `pointerup` the rod and the field are watched, per frame.
 *
 * Sized from the measurement that produced `fb32a13`, not picked: the rod held
 * the stale value from +15.2 ms to +350.7 ms on the two gauges that were
 * profiled. 1 500 ms is four times the far end, so a slower shard cannot make
 * this window close before the defect would have shown.
 */
const RELEASE_WINDOW_MS = 1_500;

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

/**
 * What the INSTRUMENT says it is showing — `shown` (`live ?? value`), stamped
 * on the grip by `ParametricGauge` as `data-value` and announced beside it as
 * `aria-valuenow`.
 *
 * This is the gauge's own reading of the number, taken independently of the
 * editor field: contract beta is precisely the claim that those two agree
 * after the pointer comes up, so reading only one of them cannot check it.
 */
async function shownValue(page: Page, gaugeId: string): Promise<number> {
  const grip = page.getByTestId(`${gaugeId}-handle`);
  const [drawn, announced] = await Promise.all([
    grip.getAttribute("data-value"),
    grip.getAttribute("aria-valuenow"),
  ]);
  if (drawn === null) throw new Error(`the ${gaugeId} grip has no data-value`);
  const value = Number.parseFloat(drawn);
  // The instrument draws one number and says another only if somebody has
  // wired the two to different sources — cheap to check here, and it is the
  // difference between "the arrow is right" and "the arrow is right and the
  // screen reader agrees".
  expect(
    Number.parseFloat(announced ?? "NaN"),
    `the ${gaugeId} grip draws ${drawn} and announces ${announced ?? "nothing"}`,
  ).toBeCloseTo(value, 6);
  return value;
}

/** One animation frame of the release window: what each surface read. */
interface ReleaseFrame {
  /** ms since the `pointerup` that ended the drag; negative is before it. */
  sinceRelease: number;
  /** `data-value` off the grip — the number the instrument is drawing. */
  rod: string | null;
  /** The editor field's value, in the document unit. */
  field: string | null;
}

/**
 * WATCH THE ROD AND THE FIELD ON EVERY ANIMATION FRAME ACROSS THE RELEASE.
 *
 * The contract-beta defect does not sit still long enough to be sampled by a
 * round trip. Measured when it was fixed (`fb32a13`): the panel settled at
 * +4.9 to +8.7 ms and the rod held the OLD value from +15.2 to +350.7 ms — one
 * `await` from the test runner lands after that has begun and can land after it
 * has ended, so a poll from Node reads a healthy pair and reports green on a
 * build that flashes two different numbers for a third of a second. A rewrite
 * of this block that only read the settled state was measured against the
 * reverted `release()` and **the mutant survived**, which is why the sampler
 * runs in the page.
 *
 * The release is stamped by a `pointerup` listener rather than by the test's
 * clock, so "after the release" is exact: that listener runs in the same task
 * as the gauge's own handler.
 */
async function sampleReleaseWindow(
  page: Page,
  gaugeId: string,
  fieldId: string,
  windowMs: number,
): Promise<void> {
  await page.evaluate(
    ({ id, field, ms }: { id: string; field: string; ms: number }) => {
      const frames: { t: number; rod: string | null; field: string | null }[] =
        [];
      const state = { frames, releasedAt: null as number | null };
      (window as unknown as Record<string, unknown>)["__betaSample"] = state;
      window.addEventListener(
        "pointerup",
        () => {
          state.releasedAt = performance.now();
        },
        { once: true },
      );
      const tick = (): void => {
        const grip = document.querySelector(`[data-testid="${id}-handle"]`);
        const input = document.querySelector(`[data-testid="${field}"]`);
        frames.push({
          t: performance.now(),
          rod: grip?.getAttribute("data-value") ?? null,
          field: (input as HTMLInputElement | null)?.value ?? null,
        });
        if (
          state.releasedAt === null ||
          performance.now() - state.releasedAt < ms
        ) {
          requestAnimationFrame(tick);
        }
      };
      requestAnimationFrame(tick);
    },
    { id: gaugeId, field: fieldId, ms: windowMs },
  );
}

/** Drain the sampler once it has covered its window. */
async function releaseFrames(
  page: Page,
  windowMs: number,
): Promise<ReleaseFrame[]> {
  await page.waitForFunction(
    (ms: number) => {
      const s = (window as unknown as Record<string, unknown>)[
        "__betaSample"
      ] as { frames: { t: number }[]; releasedAt: number | null } | undefined;
      if (s === undefined || s.releasedAt === null) return false;
      return performance.now() - s.releasedAt >= ms + 100;
    },
    windowMs,
    { timeout: 30_000 },
  );
  return page.evaluate(() => {
    const s = (window as unknown as Record<string, unknown>)[
      "__betaSample"
    ] as {
      frames: { t: number; rod: string | null; field: string | null }[];
      releasedAt: number;
    };
    return s.frames.map((f) => ({
      sinceRelease: f.t - s.releasedAt,
      rod: f.rod,
      field: f.field,
    }));
  });
}

/**
 * HOW LONG THE ARROW IS DRAWN, IN WORLD UNITS — the reading contract beta is
 * actually about, and the one a camera cannot move.
 *
 * `gauge-<id>-spine` is the shaft the gauge lays along its track, so its world
 * extent IS the instrument's length at the value it is drawing. Measured in
 * world space on purpose: see the contract-beta block below for the 52.7 px of
 * page-coordinate travel that a legitimate re-fit produces at the exact moment
 * this reading is taken.
 */
async function spineWorldLength(page: Page, gaugeId: string): Promise<number> {
  const box = await namedWorldBox(page, `gauge-${gaugeId}-spine`);
  if (box === null || box.vertices === 0) {
    throw new Error(`no drawn spine for ${gaugeId}`);
  }
  return Math.hypot(...box.max.map((v, i) => v - (box.min[i] ?? 0)));
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
      const beforeSpine = await spineWorldLength(page, gaugeId);
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
      // The instrument's own two readings, taken while the pointer is STILL
      // DOWN: what it says, and how long it is drawn in the world.
      const duringShown = await shownValue(page, gaugeId);
      const duringSpine = await spineWorldLength(page, gaugeId);
      await sampleReleaseWindow(page, gaugeId, field, RELEASE_WINDOW_MS);
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

      // CONTRACT BETA — THE INSTRUMENT KEEPS WHAT YOU DRAGGED TO.
      //
      // The gauge draws `live ?? value`, so a mount that takes `onChange`
      // without feeding its `value` prop from the editor's ECHOED state falls
      // back to the owner's opening number the instant the pointer comes up:
      // the rail field reads what you dragged to and the arrow springs back to
      // where it started. Measured on the pre-fix tree the revert lands within
      // 15-110 ms and holds, so the readings are taken ACROSS that window
      // rather than once — a single reading at +0 ms can be taken before the
      // owner has even been asked.
      //
      // ## WHY NEITHER READING IS A PAGE COORDINATE, and it is not a softening
      //
      // This block used to compare the grip's page position before and after
      // the release, and that is not a reading about the instrument at all.
      // CRAFT-12 (`7a15bea`) re-frames a proposal that runs past its frame on
      // exactly the frame the hand comes off — `handUnderway()` falling to zero
      // IS the trigger — so a legitimate re-fit slides the whole instrument
      // across the page while the value it draws does not move. Measured at
      // HEAD on this very case: `data-value` held 10.5 from before the release
      // to three seconds after it, the drawn arrow did not change length, and
      // the grip travelled **52.7 px** because the camera dollied from 81.3 to
      // 85.4 mm. The old assertion read that as the arrow springing back to
      // 8 mm, and it was red on six consecutive commits for a defect that is
      // not in this contract.
      //
      // So both readings below are CAMERA-INVARIANT and both are about the
      // thing the contract names: the number the instrument announces, and the
      // length it is DRAWN at in the world. That is strictly more sensitive
      // than the page-distance proxy — the proxy could be satisfied by a
      // camera move that happened to cancel a real spring-back, and these
      // cannot be.
      // (1) EVERY FRAME OF THE RELEASE WINDOW, not the settled state. The rod
      // and the field must never read two different numbers — that pair, not
      // the rod alone, is what `fb32a13` left this case responsible for.
      const frames = (await releaseFrames(page, RELEASE_WINDOW_MS)).filter(
        (f) => f.sinceRelease >= 0,
      );
      expect(
        frames.length,
        "no frame was sampled after the release — the window is vacuous",
      ).toBeGreaterThan(10);
      const disagreed = frames.filter((f) => {
        const rod = Number.parseFloat(f.rod ?? "NaN");
        const shownField = Number.parseFloat(f.field ?? "NaN");
        return !(Math.abs(rod - shownField) < 5e-4);
      });
      expect(
        disagreed
          .slice(0, 4)
          .map(
            (f) =>
              `+${f.sinceRelease.toFixed(1)}ms rod=${f.rod ?? "-"} field=${f.field ?? "-"}`,
          )
          .join("; "),
        `contract beta: ${disagreed.length} of ${frames.length} frames after ` +
          `the release drew a rod and a field that disagree`,
      ).toBe("");

      // (2) AND THE NUMBER THEY AGREE ON IS THE ONE THE DRAG ENDED AT — a pair
      // that reverted together would satisfy (1) perfectly.
      for (const settleMs of [0, 250, 1_000]) {
        if (settleMs > 0) await page.waitForTimeout(settleMs);
        expect(
          await shownValue(page, gaugeId),
          `${settleMs} ms after release the instrument must still show the ` +
            `dragged value (${duringShown}), not the ${OPENING_MM} mm it ` +
            `opened at`,
        ).toBeCloseTo(duringShown, 3);
        expect(
          await spineWorldLength(page, gaugeId),
          `${settleMs} ms after release the arrow must still be DRAWN at the ` +
            `dragged length`,
        ).toBeCloseTo(duringSpine, 3);
      }
      // …and every assertion above is vacuous unless the drag actually moved
      // the instrument, so say so in the two terms they are written in.
      expect(
        duringShown,
        "the drag must have moved the instrument's own number — otherwise " +
          "contract beta passes vacuously",
      ).not.toBeCloseTo(OPENING_MM, 3);
      expect(
        duringSpine - beforeSpine,
        `the drag must have grown the DRAWN arrow (${beforeSpine.toFixed(3)} ` +
          `-> ${duringSpine.toFixed(3)} world units)`,
      ).toBeGreaterThan(1);
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
