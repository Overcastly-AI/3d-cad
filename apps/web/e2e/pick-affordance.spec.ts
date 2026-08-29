import type { Locator } from "@playwright/test";

import { expect, test, type Page } from "./fixtures";

import { setupTwoInstances } from "./assemblyFlow";
import { installSceneProbe, waitForCameraRest } from "./invariants";
import {
  labelIsWall,
  litAfterHiding,
  openOccludedPlate,
  setBodyMode,
} from "./occludedPlate";
import { seedDenseHolePlate } from "./partSeed";
import {
  clearOfSilhouette,
  litPoints,
  measureReachabilityWith,
  type Point,
} from "./reachability";
import {
  SCREENSHOT_DIR,
  createPartViaApi,
  distinctCanvasColors,
  seedSession,
  waitForFrames,
} from "./support";

/**
 * SEL-4 — EVERY armed pick addresses the geometry, not a 24 px dot.
 *
 * SEL-1 A2 converted ONE overlay (the sketch-plane face pick) and lifted its
 * reachability from 9.9 % to 84.6 %. The founder's "picking is very difficult"
 * was therefore unfixed the moment the tool was fillet rather than
 * sketch-on-face: `EdgePickOverlay`, `ShellFaceOverlay`, `MeasureOverlay`,
 * `InstanceMateOverlay` and `HolePointOverlay` all still hung their only
 * handler on a `PickNode`. This is the gate for converting them.
 *
 * ## The fixture, and why the box could not do this job
 *
 * A2's acceptance names a DENSE-HOLE-PATTERN fixture and the shipped gate did
 * not have one. On a six-face box every entity is far from every other entity
 * in both ordinal space and screen space, so a pick model that quietly answers
 * "the one next door" scores perfectly. `seedDenseHolePlate` puts seven Ø6
 * bores on a Ø40 bolt circle: 14 circular edges and 7 snap centres crowded
 * together, which is where a widened corridor either stays a corridor or
 * becomes a blanket.
 *
 * ## Why the EDGE metric is anisotropy and not an area fraction
 *
 * A face is 2-D, so "what fraction of the body's lit area addresses a face" is
 * the honest question and the one the FB-3/FB-5 census asks. An edge is 1-D:
 * it has no area, so a fraction is meaningless — a perfect edge pick would
 * still score near zero. What actually changed is the SHAPE of the live region.
 * A 24 px dot addresses ±12 px in every direction and nothing beyond; a band
 * addresses tens-to-hundreds of pixels in two opposite directions and ~12 px
 * perpendicular. So the measurement sweeps directions from each edge's own mark
 * and records how far the edge answers in each — which is exactly the property
 * the fix claims, and exactly the one a dot cannot fake by being moved or
 * multiplied.
 *
 * MUTATION-VERIFIED. Removing `EdgeBandLayer` from `EdgePickOverlay` (i.e.
 * restoring the `PickNode`-only hit-test) leaves every direction at the DOM
 * node's own ~12 px, so `along` collapses to 13 px for every edge and the
 * `>= 40 px` assertion fails on all of them while the perpendicular bound still
 * passes. That asymmetry is the point: the gate is sensitive to the thing that
 * changed and insensitive to the thing that did not.
 *
 * ## How the stamps are READ (CI-4, 2026-08-15)
 *
 * Every probe in this file asks a `data-*-hover` attribute — React state, one
 * commit behind `page.mouse.move`. The sweep of every such reader, what was
 * measured about each, and the rule for which ones get a parked oracle, is in
 * the ORACLE block by `OFF_BODY`. Read that before adding a probe here.
 */

/** Radii swept outward from an edge's mark, in CSS px. */
const RADII = [13, 20, 28, 40, 60, 90, 130] as const;

/** Directions swept. 16 keeps the worst tangent misalignment at 11.25°, where
 *  a 12 px corridor still reaches 61 px — comfortably past the 40 px floor, so
 *  a real band can never fail this for want of angular resolution. */
const DIRECTIONS = 16;

/** Reach floor ALONG an edge (px). A dot cannot exceed its own 12 px. */
const ALONG_MIN_PX = 40;

/** Reach ceiling PERPENDICULAR to a straight edge (px) — it stays a corridor. */
const PERP_MAX_PX = 16;

/** The band's half-width — `edgeBand.EDGE_BAND_TOLERANCE_PX`, in CSS px. */
const EDGE_CORRIDOR_PX = 12;

interface EdgeMark {
  index: number;
  kind: string;
  /** The mark's full accessible name — carries the edge's own mid-span. */
  label: string;
  centre: Point;
}

/** A stamp the sweep saw at a point, kept WITH the point so it is re-checkable. */
interface StampSighting {
  stamp: string;
  at: Point;
}

interface EdgeReach {
  mark: EdgeMark;
  /** Furthest radius still addressing this edge, per direction. */
  profile: number[];
  /** Direction index of `along` — where the oracle re-checks the claim. */
  bestDirection: number;
  along: number;
  perp: number;
  /** Any OTHER edge addressed within the innermost ring — cross-talk. */
  crossTalk: StampSighting[];
}

async function openDensePlate(page: Page): Promise<Locator> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Bolt circle plate");
  await seedDenseHolePlate(page, account.token, part.id);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("prop-volume")).toContainText(/\d/, {
    timeout: 30_000,
  });
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
    .toBeGreaterThan(24);
  // Pin the framing: every number here is in screen pixels, so it is only
  // comparable between runs if the part is the same size in frame.
  const viewport = page.getByTestId("viewport");
  await viewport.evaluate((node) => {
    node.dataset["fitRect"] = "";
  });
  await page.getByTestId("view-fit").click();
  await expect(viewport).not.toHaveAttribute("data-fit-rect", "", {
    timeout: 20_000,
  });
  await waitForFrames(page, 6);
  return viewport;
}

/** Every edge pick mark on screen, with the entity kind from its own name. */
async function edgeMarks(page: Page): Promise<EdgeMark[]> {
  const nodes = page.locator('[data-testid^="edge-pick-"]');
  await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
  const marks: EdgeMark[] = [];
  for (const node of await nodes.all()) {
    const testId = (await node.getAttribute("data-testid")) ?? "";
    const label = (await node.getAttribute("aria-label")) ?? "";
    const box = await node.boundingBox();
    if (box === null) continue;
    marks.push({
      index: Number(testId.replace("edge-pick-", "")),
      // "Edge 5, circle, centred at …" — the kernel's own edge kind.
      kind: (label.split(",")[1] ?? "").trim(),
      label,
      centre: { x: box.x + box.width / 2, y: box.y + box.height / 2 },
    });
  }
  return marks;
}

/**
 * Sweep outward from an edge's mark and record how far that edge still answers
 * in each direction. Contiguous by construction: the first radius that stops
 * answering ends that direction, so a coincidental hit far away cannot inflate
 * the reach.
 *
 * THIS IS A FILTER, NOT AN ORACLE — the same posture the hole scan takes. It
 * reads the hover stamp with no settle, ~330 times per call; every value an
 * ASSERTION consumes is re-checked afterwards through {@link reachHolds} (for a
 * reach) or {@link releasesEntity} / {@link settledStampAt} (for a point-local
 * claim), so a survivor of the previous probe cannot masquerade as a fresh one.
 * See the ORACLE block below for the measurements that set that boundary,
 * including why the sweep itself is NOT converted: parking every probe costs
 * 20x AND changes what is being measured.
 */
async function measureReach(
  page: Page,
  viewport: Locator,
  mark: EdgeMark,
  attribute = "data-edge-pick-hover",
  /** The stamp value that counts as "this edge" (mates stamp `instance:index`). */
  wanted = String(mark.index),
): Promise<EdgeReach> {
  const profile: number[] = [];
  const crossTalk = new Map<string, Point>();
  for (let d = 0; d < DIRECTIONS; d += 1) {
    let reach = 0;
    for (const radius of RADII) {
      const point = radialPoint(mark.centre, d, radius);
      await page.mouse.move(point.x, point.y);
      const stamped = await viewport.getAttribute(attribute);
      if (stamped === wanted) {
        reach = radius;
        continue;
      }
      // The innermost ring is the crowding test: just outside this edge's own
      // 24 px mark, on a bolt circle, nothing else may answer. The POINT is
      // kept with the stamp so the oracle can go back and re-ask there.
      if (stamped !== null && radius === RADII[0] && !crossTalk.has(stamped)) {
        crossTalk.set(stamped, point);
      }
      break;
    }
    profile.push(reach);
  }
  let best = 0;
  profile.forEach((reach, d) => {
    if (reach > (profile[best] as number)) best = d;
  });
  const quarter = DIRECTIONS / 4;
  const perp = Math.max(
    profile[(best + quarter) % DIRECTIONS] as number,
    profile[(best + DIRECTIONS - quarter) % DIRECTIONS] as number,
  );
  return {
    mark,
    profile,
    bestDirection: best,
    along: profile[best] as number,
    perp,
    crossTalk: [...crossTalk].map(([stamp, at]) => ({ stamp, at })),
  };
}

/** The edge marks on offer, split by the body each one belongs to. */
async function splitEdgeMarks(page: Page): Promise<{
  marks: EdgeMark[];
  wall: EdgeMark[];
  plate: EdgeMark[];
}> {
  const marks = await edgeMarks(page);
  return {
    marks,
    wall: marks.filter((m) => labelIsWall(m.label)),
    plate: marks.filter((m) => !labelIsWall(m.label)),
  };
}

/** How many shell face marks each body currently offers. */
async function splitFaceMarks(
  page: Page,
): Promise<{ wall: number; plate: number }> {
  const nodes = page.locator('[data-testid^="shell-face-"]');
  await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
  let wall = 0;
  let plate = 0;
  for (const node of await nodes.all()) {
    const label = (await node.getAttribute("aria-label")) ?? "";
    if (labelIsWall(label)) wall += 1;
    else plate += 1;
  }
  return { wall, plate };
}

/**
 * A page position guaranteed to be off every pick surface — the same one this
 * file's stamp negative control already relies on.
 */
const OFF_BODY: Point = { x: 5, y: 5 };

/* ==========================================================================
 * THE ORACLE — and the MEASUREMENTS that say where to spend it (CI-4).
 *
 * Every reader in this file asks a `data-*-hover` attribute what the pointer is
 * addressing. Those attributes are React state written by `useViewportPickStamp`
 * a commit after `page.mouse.move` resolves, so a bare read can answer about the
 * PREVIOUS position. `confirmsPlacementFace` fixed one such reader; this block
 * is the sweep of the rest, and it is deliberately NOT "add a wait everywhere".
 *
 * WHAT WAS MEASURED, on a native stack at load average 13 on 4 cores. Two
 * attributes were instrumented, and THEY DO NOT BEHAVE THE SAME WAY:
 *
 *  · `data-hole-point-hover` (HolePointOverlay) LAGS IN TIME. Over 120 points of
 *    the production 12 px raster: 18 reads (15 %) differed from the same point
 *    re-read 1 s later, alternating in both directions (`-`->`1`, `1`->`-`) —
 *    i.e. exactly the carry-over `2f0b361` described. Path made no difference at
 *    all: the in-place 1 s read equalled the parked read 120 times out of 120.
 *
 *  · `data-edge-pick-hover` (EdgeBandLayer) DOES NOT LAG. Over 96 probes across
 *    six edge marks, the bare read equalled the same point re-read at +50 ms,
 *    +200 ms, +500 ms and +2000 ms in EVERY case. What it does instead is depend
 *    on where the pointer CAME FROM: arriving from 130 px out along the ray
 *    reports nothing where arriving from off-canvas reports the edge, and that
 *    reproduces identically with 2.75 s of settle in both arms. That is a
 *    product property, reported rather than patched (see the return report).
 *
 * WHAT FOLLOWS, and it is the reason `measureReach` is not converted: parking
 * every probe would cost 20x (a full production sweep goes 13.8 s -> 275.7 s,
 * against a 60 s test) AND would measure a pointer path no hand takes. The
 * numbers themselves do not move — three naive sweeps quiet, three at load 13,
 * and a parked ground-truth sweep all report `#0 40/13  #1 60/0  #2 130/0` for
 * the three line edges every assertion in this file consumes. The parked sweep
 * differs only on circle edges at 13 px (`#12 0->13 perp`, `#13 0->13 along`,
 * `#14 0->13 perp`, `#15 0->13 along`), which is below every threshold here and
 * asserted on by nothing. So the thresholds were NOT inflated and are not
 * re-baselined.
 *
 * THERE ARE THEREFORE TWO ORACLES, and picking the wrong one is not a style
 * choice — it produced a red build here before this comment was written:
 *
 *   PARKED, for a POINT-LOCAL question ("is anything addressing this pixel?").
 *   Arrive from the opposite answer — `parkOffBody` for a claim of presence,
 *   the entity's own mark for a claim of release — so the value you read cannot
 *   be the previous probe's. `settledStampAt`, `releasesEntity`,
 *   `confirmsPlacementFace`.
 *
 *   RE-WALKED, for a REACH ("how far along the corridor does it answer?").
 *   A reach is a claim about a pointer TRAVELLING, so a park replaces the
 *   subject. `reachHolds` repeats the sweep's own ray, to the radius the
 *   assertion CLAIMS rather than to the sweep's maximum, and then settles.
 *
 * AND THE RE-WALK EARNED ITS KEEP IMMEDIATELY: it found that the mate-axis gate
 * at the foot of this describe has been passing on a one-ring carry-over, and
 * that on the UNMODIFIED file that gate is already a ~29 % flake. NO THRESHOLD
 * IN THIS FILE WAS MOVED — the mate measurement is not stable enough to
 * re-baseline against (20/28/40/90 px across 15 runs), so it is written down at
 * its call site and handed on rather than tuned into green.
 *
 * WHERE EITHER IS SPENT — on thin margins and strict claims, not uniformly:
 *   · `reachable.length >= 3` is met by EXACTLY 3 of 8 sampled edges. Zero
 *     margin, so every counted edge's reach is re-walked and settled.
 *   · `perp <= 16 px` is met at 13 px, one RADII ring from the ceiling — and the
 *     swept value is not even stable about WHICH line edge carries it (`#0` in
 *     one session, `#1` in the next, both under the ceiling). So the corridor
 *     claim is now stated directly, against the first radius above the ceiling,
 *     through the parked `releasesEntity`.
 *   · a strict `toEqual([])` / `toBe(0)` / `not.toContain` cannot absorb one bad
 *     read, so no such assertion goes red on an unconfirmed value.
 *   · the `>= 0.5` fraction censuses measure 98-99 % — a 48-point margin that a
 *     one-probe race cannot cross. Those keep the cheap read, and gain the free
 *     half of the fix: the pointer is PARKED before the census starts, so the
 *     first probe cannot inherit whatever the previous step left behind.
 * ======================================================================= */

/** What a parked oracle is waiting for the stamp to become. */
type StampGoal =
  | { kind: "absent" }
  | { kind: "present" }
  | { kind: "is"; value: string }
  | { kind: "not"; value: string };

/**
 * How long a parked oracle waits for the transition it parked for.
 *
 * Not a frame budget — a settle-tolerant ceiling, so a slower runner cannot
 * re-break it. Measured transition time with rAF polling on this build: p50
 * 206 ms, p90 229 ms, max 279 ms (the floor is the ~5 fps software-GL frame,
 * not React). 5 s is ~18x the p90 and matches the timeout every other wait in
 * this file already uses. It is only ever SPENT when a claim is about to fail.
 */
const ORACLE_TIMEOUT_MS = 5_000;

/** Wait, polling on animation frames, for the viewport stamp to reach `goal`. */
async function stampSettles(
  page: Page,
  attribute: string,
  goal: StampGoal,
  timeout = ORACLE_TIMEOUT_MS,
): Promise<boolean> {
  return page
    .waitForFunction(
      (input: { attribute: string; goal: StampGoal }) => {
        const value =
          document
            .querySelector('[data-testid="viewport"]')
            ?.getAttribute(input.attribute) ?? null;
        if (input.goal.kind === "absent") return value === null;
        if (input.goal.kind === "present") return value !== null;
        if (input.goal.kind === "is") return value === input.goal.value;
        return value !== input.goal.value;
      },
      { attribute, goal },
      { timeout, polling: "raf" },
    )
    .then(
      () => true,
      () => false,
    );
}

/** Park off every pick surface and prove the stamp is gone. */
async function parkOffBody(page: Page, attribute: string): Promise<void> {
  await page.mouse.move(OFF_BODY.x, OFF_BODY.y);
  const cleared = await stampSettles(
    page,
    attribute,
    { kind: "absent" },
    10_000,
  );
  if (!cleared) {
    throw new Error(
      `${attribute} never cleared with the pointer off the body — every read ` +
        `taken through this oracle would be measuring a stuck attribute.`,
    );
  }
}

/**
 * Does the edge REALLY answer `radius` px out along direction `d` — the value
 * the reach assertions count?
 *
 * WHY THIS ONE DOES NOT PARK, when almost every other oracle in this file does.
 * The park's whole trick is arriving from the opposite answer, and for a
 * point-local question ("is anything here?") that costs nothing. A REACH is not
 * point-local: it is a claim about the corridor a pointer TRAVELS, and on this
 * build the edge stamp depends on where the pointer came from (see the ORACLE
 * block). Parking replaces the traversal with an off-canvas teleport, so it
 * stops answering the question the test is asking — and it does not merely
 * differ in principle. MEASURED, and this is why the first version of this
 * helper was thrown away: with a parked confirmation the mate-axis sweep found
 * `#14 40px` and the parked read at that very point refused it, taking a green
 * test red with no defect anywhere. In the part workspace the park errs the
 * other way and is MORE generous than a drag. Either way it is the wrong
 * instrument for a corridor.
 *
 * So this re-walks the sweep's own ray — the same arrival, in order — and then
 * SETTLES: two reads that agree across a rendered frame. That is what removes
 * the race the ticket is about, because a carry-over from the inner radius
 * cannot survive a frame in which the true value lands; the settle exits on
 * agreement rather than on a fixed budget, so a slower runner cannot re-break
 * it. It costs ~4 pointer moves and 1-2 frames, which is why every counted
 * reach can afford one.
 *
 * Residual, stated plainly: a lag longer than 5 settle rounds (~1 s at the
 * ~200 ms frames measured here) would still pass. Measured lag on this
 * attribute is zero over 96 probes at horizons up to 2.75 s, and one frame on
 * the hole stamp, so the margin is three orders of magnitude, not two-fold.
 */
async function reachHolds(
  page: Page,
  viewport: Locator,
  attribute: string,
  centre: Point,
  direction: number,
  radius: number,
  wanted: string,
): Promise<boolean> {
  for (const ring of RADII) {
    if (ring > radius) break;
    const step = radialPoint(centre, direction, ring);
    await page.mouse.move(step.x, step.y);
  }
  let last = await viewport.getAttribute(attribute);
  for (let round = 0; round < 5; round += 1) {
    await waitForFrames(page, 1);
    const next = await viewport.getAttribute(attribute);
    if (next === last) return next === wanted;
    last = next;
  }
  return last === wanted;
}

/**
 * Does the corridor STOP by `point` — i.e. does the pointer stop addressing
 * `wanted` there?
 *
 * The mirror park, because parking off the body would make this vacuous: null
 * is what you want to see, so a premature read would "prove" it. So park ON
 * `from` — a position that DOES address the edge, proved — and require the
 * stamp to change. A stale `wanted` fails the wait; only a real transition
 * passes. It also parks on the most generous path there is (straight off the
 * edge's own mark), so a negative here is a strong negative.
 *
 * IT CLEARS THE STAMP BEFORE TAKING THE PARK, and that is not ceremony — the
 * guard below caught the version that did not. Arriving at an `edge-pick-*`
 * mark from ANOTHER point on the canvas does not reliably stamp that edge on
 * this build, while arriving from off-canvas does (8 marks of 8, measured). So
 * an oracle that walked straight from the previous probe onto the mark would
 * have sat on a park that reads someone else's index, and every "it released
 * the edge" it reported would have been about the wrong edge. The guard is what
 * turns that into a loud failure instead of a quiet green.
 */
async function releasesEntity(
  page: Page,
  attribute: string,
  from: Point,
  point: Point,
  wanted: string,
): Promise<boolean> {
  await parkOffBody(page, attribute);
  await page.mouse.move(from.x, from.y);
  const parked = await stampSettles(
    page,
    attribute,
    { kind: "is", value: wanted },
    10_000,
  );
  if (!parked) {
    throw new Error(
      `the park position ${Math.round(from.x)},${Math.round(from.y)} for ` +
        `${attribute} does not address ${wanted}, so a "stopped addressing it" ` +
        `reading there would prove nothing.`,
    );
  }
  await page.mouse.move(point.x, point.y);
  return stampSettles(page, attribute, { kind: "not", value: wanted });
}

/** The stamp at `point`, parked off the body first so the value is this point's. */
async function settledStampAt(
  page: Page,
  viewport: Locator,
  attribute: string,
  point: Point,
  timeout = ORACLE_TIMEOUT_MS,
): Promise<string | null> {
  await parkOffBody(page, attribute);
  await page.mouse.move(point.x, point.y);
  await stampSettles(page, attribute, { kind: "present" }, timeout);
  return viewport.getAttribute(attribute);
}

/**
 * The ceiling for a parked read inside a MULTI-POINT probe, where "nothing
 * here" is a common and legitimate answer and therefore gets paid for on every
 * such point rather than once at the end.
 *
 * 1.5 s is ~6.5x the measured p90 transition (229 ms) and 5.4x the worst
 * observed (279 ms) — settle-tolerant, but small enough that a six-position
 * probe over an empty region costs 9 s rather than 30 s. The full
 * ORACLE_TIMEOUT_MS stays where a single decision hangs on one read.
 */
const PROBE_SETTLE_MS = 1_500;

/**
 * How far a "vacated" grid point must be from any drawn pixel before the face
 * oracle is asked about it. See `clearOfSilhouette` for the measurement: the
 * rim + outline band around a body reads BELOW the luminance floor while being
 * on the solid, so a point inside it is neither lit nor empty.
 *
 * 8 px is 1.6x the measured 5-px band and one third of the 24-px census grid.
 */
const SILHOUETTE_MARGIN_PX = 8;

/** The sweep's probe position: `radius` px from `centre` along direction `d`. */
function radialPoint(centre: Point, d: number, radius: number): Point {
  const angle = (2 * Math.PI * d) / DIRECTIONS;
  return {
    x: centre.x + radius * Math.cos(angle),
    y: centre.y + radius * Math.sin(angle),
  };
}

/**
 * Is the hole's placement face REALLY under `point`?
 *
 * THE STAMP LAGS THE POINTER, so reading it straight after `page.mouse.move`
 * answers about the PREVIOUS position. `page.mouse.move` resolves once the
 * browser has dispatched the event; `data-hole-point-hover` is React state
 * written a commit later. Measured on this build over 40 sampled points: 4
 * reads lagged (null, then set once settled) and 3 led (set, then null once
 * settled) — the race runs in BOTH directions.
 *
 * At the edge of the face that is fatal rather than cosmetic. The scan below
 * walks a 12 px grid in raster order, so where a row crosses only a narrow
 * sliver of the face the on-face run is one or two points long; a lag of one
 * point makes the FIRST OFF-FACE point inherit the last on-face point's stamp,
 * the scan drills there, `HolePointOverlay.pointAt` correctly refuses a hit
 * that is not the placement face, and the readout never leaves "Centre of
 * face". Reproduced here 3 runs in 6 under CPU load, with the identical
 * message CI reported — and at the same rate with `a810524` (DIM-1) reverted,
 * which is what rules that fix out as the cause.
 *
 * So the scan stays the cheap FILTER it always was and this is the oracle. It
 * is settle-tolerant rather than a fixed frame budget, and it NULLS the stamp
 * first: without that baseline a stale "1" cannot be told from a fresh one,
 * which is the whole defect.
 *
 * RE-MEASURED 2026-08-15 (CI-4) and the original reading holds, with one
 * correction worth having: over 120 points of this very raster, 18 bare reads
 * (15 %) differed from the same point 1 s later — but the in-place 1 s read
 * agreed with the PARKED read 120 times out of 120. So on this attribute it is
 * the SETTLE that does the work and the park is what makes the settle provable
 * rather than assumed; there is no path effect here to trade against. (Contrast
 * `data-edge-pick-hover`, where the ORACLE block above measures the opposite.)
 * Now expressed through the shared parked helpers so there is one shape.
 */
async function confirmsPlacementFace(
  page: Page,
  point: Point,
): Promise<boolean> {
  await parkOffBody(page, "data-hole-point-hover");
  await page.mouse.move(point.x, point.y);
  return stampSettles(page, "data-hole-point-hover", { kind: "present" });
}

/**
 * TILT OFF THE FACE VIEW, so a BURIED edge has a screen position of its own.
 *
 * Why this exists (ORTHO-1, 2026-08-28). The occluded-plate fixture is framed
 * FRONT-ON, and a front view is now ORTHOGRAPHIC — as every incumbent's named
 * views are. Under a parallel projection the plate's back-bottom edge and its
 * front-bottom twin project to *the same screen line*, exactly (measured
 * 0.0016 px apart), because the only thing that used to separate them was
 * perspective foreshortening — and that is precisely the quantity a parallel
 * projection removes by definition. It is not a fixture that broke; it is a
 * separation that was never real, and a probe on it was measuring the VISIBLE
 * edge while claiming to measure the buried one. The guard in `buriedPair`
 * caught it rather than producing a wrong answer, and it stays.
 *
 * There is no repair available inside a face view: for an axis-aligned box
 * seen face-on in parallel projection, EVERY back edge coincides with a front
 * edge. So the camera has to leave the face — and it leaves through the
 * product's own control, the reference cube's TOP-FRONT edge cubelet, which
 * `ViewCube.onPick` routes to `requestDirection` like any other cube pick.
 *
 * The resulting 45 degree front-top view keeps BOTH halves of the subject:
 *
 *  · the wall still stands between the camera and the probed edge — the ray
 *    from the plate's back-bottom edge (30, 50, 0) toward the camera enters
 *    the wall's top face at (30, 10, 40) and leaves through its back face at
 *    (30, 20, 30), so a hidden wall is still the nearest discarded hit, which
 *    is the mechanism SEL-6 exists to pin; and
 *  · the edge is still buried in the STILL-DRAWN plate — that same ray crosses
 *    14.1 mm of plate before it reaches the top face at (30, 40, 10).
 *
 * The separation it buys is a projection-plane one: 20 mm of depth becomes
 * 20 · sin 45 = 14.1 mm of screen height, which does not depend on how far away
 * the camera is. That is the property the old fixture lacked.
 *
 * The cubelet's seat is drei's, not ours: `GizmoViewcube` scales its group by
 * 60 and seats each edge cubelet at 0.38 of that along its two axes, and our
 * cube canvas is orthographic at zoom 1, so one scene unit is one CSS pixel
 * (see the comment block at the top of `viewport/ViewCube.tsx`). Front-on, the
 * top-front cubelet therefore sits 22.8 px above the cube's centre. If drei
 * ever moves it, the direction assertion below fails by name instead of the
 * click silently landing on the FRONT face and leaving the view where it was.
 */
const CUBE_EDGE_OFFSET_PX = 0.38 * 60;

async function tiltOffTheFaceView(page: Page): Promise<void> {
  const viewport = page.getByTestId("viewport");
  const cube = page.getByTestId("view-cube");
  const seat = await cube.boundingBox();
  expect(seat, "the reference cube has a rect to click").not.toBeNull();
  if (seat === null) throw new Error("no reference cube");
  await page.evaluate(() => {
    document
      .querySelector('[data-testid="viewport"]')
      ?.removeAttribute("data-view");
  });
  await page.mouse.click(
    seat.x + seat.width / 2,
    seat.y + seat.height / 2 - CUBE_EDGE_OFFSET_PX,
  );
  await expect(viewport).toHaveAttribute("data-view", "direction", {
    timeout: 20_000,
  });

  // The click reached an EDGE cubelet and not the FRONT face: the view
  // direction must be oblique in both scene axes. Asserted on the live camera
  // rather than on the stamp, because the stamp says "a direction was applied"
  // and this says WHICH — a face pick would satisfy the first and not the
  // second, and would leave the twins coincident all over again.
  const pose = await waitForCameraRest(page);
  const [, dirY, dirZ] = pose.direction;
  expect(
    [Math.abs(dirY), Math.abs(dirZ)].map((v) => Number(v.toFixed(2))),
    `the cube's top-front edge should give a 45 degree front-top view (got ${pose.direction.map((v) => v.toFixed(3)).join(",")})`,
  ).toEqual([0.71, 0.71]);

  // Re-frame at the new attitude. `fit` deliberately does not touch the
  // projection (`viewCommands.orients`), so this is still the orthographic
  // view the ticket is about.
  await viewport.evaluate((node) => {
    node.dataset["fitRect"] = "";
  });
  await page.getByTestId("view-fit").click();
  await expect(viewport).not.toHaveAttribute("data-fit-rect", "", {
    timeout: 20_000,
  });
  await expect(viewport).toHaveAttribute("data-projection", "orthographic");
  await waitForFrames(page, 6);
}

async function armFilletPick(page: Page): Promise<void> {
  await expect(page.getByTestId("new-fillet")).toBeEnabled({ timeout: 30_000 });
  await page.getByTestId("new-fillet").click();
  await expect(page.getByTestId("fillet-editor")).toBeVisible();
  await page.getByTestId("fillet-mode-pick").click();
  await expect(page.locator('[data-testid^="edge-pick-"]').first()).toBeVisible(
    { timeout: 20_000 },
  );
  await waitForFrames(page, 4);
}

test.describe("SEL-4 — the armed pick addresses the geometry", () => {
  test("fillet edges: the EDGE is the target, not a diamond at its mid-span", async ({
    page,
  }) => {
    // 34-35 s measured over three runs at load average 13 on 4 cores, against
    // the config's 60 s default — and the parked oracles below add ~10 waits.
    // Same ceiling, and same reason, as the mate sibling at the foot of this
    // describe: a sweep-plus-oracle test must not be one slow shard away from a
    // false red in nobody's diff.
    test.setTimeout(300_000);
    const viewport = await openDensePlate(page);
    await armFilletPick(page);

    // A 60 mm plate with seven Ø6 bores: 12 box edges + 7 × (two circular
    // mouths + the cylinder's own SEAM line) = 33. If this count ever changes
    // the fixture changed, and the numbers below stop being comparable.
    const marks = await edgeMarks(page);
    expect(marks.length, "the plate's B-rep edges are all pickable").toBe(33);

    // Sample rather than sweep all 26: each edge costs ~100 pointer moves, and
    // the claim is about the SHAPE of the live region, which does not need
    // every instance of it. Circles first, because the crowded bolt circle is
    // the part of the fixture the box could not provide.
    const circles = marks.filter((m) => m.kind === "circle").slice(0, 5);
    const lines = marks.filter((m) => m.kind === "line").slice(0, 3);
    const sampled: EdgeReach[] = [];
    for (const mark of [...circles, ...lines]) {
      sampled.push(await measureReach(page, viewport, mark));
    }

    const report = sampled
      .map((r) => `#${r.mark.index}(${r.mark.kind}) ${r.along}/${r.perp}px`)
      .join(" ");

    // NON-VACUITY FIRST, so this cannot pass by measuring nothing: a stamp that
    // gets stuck set would score every direction at the outermost radius.
    await page.mouse.move(5, 5);
    await expect(viewport).not.toHaveAttribute("data-edge-pick-hover", /.*/, {
      timeout: 5_000,
    });

    // THE CLAIM. Some sampled edges face away from the camera or hide behind
    // the plate, and those are correctly refused by the occlusion test — so the
    // assertion is about the visible ones. Under the old dot every edge scores
    // 13 px, so no arrangement of dots reaches this.
    //
    // EVERY COUNTED EDGE IS RE-CONFIRMED, because this is the thinnest margin in
    // the file: exactly 3 of the 8 sampled edges clear the floor, so ONE bad
    // read either way decides the test. The sweep says WHICH RAY to walk;
    // `reachHolds` re-walks it and settles before the count believes it.
    //
    // Confirmed AT THE FLOOR, not at the swept maximum, because the floor is
    // what the assertion claims: "this edge answers 40 px out". Demanding the
    // swept maximum instead would hold the gate to a number it never states,
    // and would fail on an edge whose corridor is real but whose last ring the
    // sweep over-reported.
    const reachable: EdgeReach[] = [];
    const refused: string[] = [];
    for (const reach of sampled) {
      if (reach.along < ALONG_MIN_PX) continue;
      if (
        await reachHolds(
          page,
          viewport,
          "data-edge-pick-hover",
          reach.mark.centre,
          reach.bestDirection,
          ALONG_MIN_PX,
          String(reach.mark.index),
        )
      ) {
        reachable.push(reach);
      } else {
        refused.push(`#${reach.mark.index}@${ALONG_MIN_PX}px`);
      }
    }
    expect(
      reachable.length,
      `edges addressable >= ${ALONG_MIN_PX}px along: ${report}` +
        (refused.length > 0
          ? ` — the sweep claimed ${refused.join(",")} and the settled ` +
            `re-walk did not confirm it`
          : ""),
    ).toBeGreaterThanOrEqual(3);

    // …AND IT IS STILL A CORRIDOR. A straight edge's live region must stay
    // narrow across the entity, or neighbours stop being distinguishable and
    // the fix has traded one founder complaint for a worse one. Circles are
    // excluded deliberately: a Ø6 bore is ~40 px across at this framing, so
    // "perpendicular" from a point on it lands on the SAME edge's far side —
    // that measures the entity, not the tolerance.
    //
    // STATED AGAINST THE CEILING RATHER THAN AGAINST THE PROFILE. The old form
    // compared a swept maximum (13 px here) to 16 px — one RADII ring of margin,
    // decided by an unconfirmed read, and inflating in the direction that turns
    // a healthy corridor red. This asks the claim itself: at the first radius
    // ABOVE the ceiling, in both perpendicular directions, the edge must have
    // let go. `releasesEntity` parks ON the edge's own mark, so a stale
    // `wanted` cannot pass for a fresh release — only a real transition can.
    const beyondCeiling = RADII.find((r) => r > PERP_MAX_PX) as number;
    const quarter = DIRECTIONS / 4;
    for (const reach of reachable.filter((r) => r.mark.kind === "line")) {
      for (const side of [quarter, DIRECTIONS - quarter]) {
        const across = radialPoint(
          reach.mark.centre,
          (reach.bestDirection + side) % DIRECTIONS,
          beyondCeiling,
        );
        expect(
          await releasesEntity(
            page,
            "data-edge-pick-hover",
            reach.mark.centre,
            across,
            String(reach.mark.index),
          ),
          `edge #${reach.mark.index} still answers ${beyondCeiling}px across ` +
            `itself, past the ${PERP_MAX_PX}px corridor (${report})`,
        ).toBe(true);
      }
    }

    // THE MIS-RESOLUTION DETECTOR the dense fixture exists for: probing just
    // outside one bore's mark must never report a different edge.
    // …applied to the edges that are actually ADDRESSABLE, which is the whole
    // claim and not a convenient subset. An edge hidden behind the plate is
    // SUPPOSED to yield to the visible one in front of it, and this fixture
    // produces exactly that case — measured 2026-08-08: bore #12's occluded
    // bottom circle sits 34 px from bore #19's visible top mouth, because a
    // 10 mm plate is thin next to a Ø40 bolt circle. Demanding silence there
    // would be demanding the occlusion test be wrong. A six-face box cannot
    // stage this at all, which is why A2 asked for this fixture.
    //
    // `toEqual([])` cannot absorb one bad read, so no sighting reaches it
    // unconfirmed: the sweep's candidate is re-asked at its own point with the
    // pointer parked off the body first. Costs nothing while the answer is the
    // empty list, which is what it has always been for these edges.
    for (const reach of reachable) {
      const confirmed: string[] = [];
      for (const sighting of reach.crossTalk) {
        const settled = await settledStampAt(
          page,
          viewport,
          "data-edge-pick-hover",
          sighting.at,
        );
        if (settled === sighting.stamp) confirmed.push(sighting.stamp);
      }
      expect(
        confirmed,
        `edge #${reach.mark.index} answered as another edge (${report})`,
      ).toEqual([]);
    }
  });

  test("shell faces: the visible body IS the pick target", async ({ page }) => {
    const viewport = await openDensePlate(page);
    await expect(page.getByTestId("new-shell")).toBeEnabled({
      timeout: 30_000,
    });
    await page.getByTestId("new-shell").click();
    await expect(page.getByTestId("shell-editor")).toBeVisible();
    await expect(
      page.locator('[data-testid^="shell-face-"]').first(),
    ).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 6);

    // The FB-3/FB-5 census, pointed at the overlay SEL-1 did not convert. One
    // round trip per point, so the grid is coarse; the lit silhouette supplies
    // the points, so this is a fraction of what the user can SEE.
    //
    // PARKED FIRST, so the census cannot open on an inherited value: the last
    // thing before it is a `click()`, whose stamp the very first probe would
    // otherwise be free to read back as its own answer. Free, and it removes
    // the one error here that is systematic rather than random. The per-point
    // read stays cheap on purpose — see the ORACLE block: this floor is 50 %
    // and the measured fraction is 98-99 %, a margin no one-probe race crosses,
    // and 135 parked probes would cost more than the whole test.
    const points = await litPoints(page, { step: 24 });
    await parkOffBody(page, "data-shell-face-hover");
    const measured = await measureReachabilityWith(points, async (point) => {
      await page.mouse.move(point.x, point.y);
      return (await viewport.getAttribute("data-shell-face-hover")) !== null;
    });

    expect(measured.sampled, "body sampled").toBeGreaterThan(40);
    await page.mouse.move(5, 5);
    await expect(viewport).not.toHaveAttribute("data-shell-face-hover", /.*/, {
      timeout: 5_000,
    });

    // The same 50 % floor the sketch-plane pick is held to, for the same
    // reason: it cannot be reached by adding dots, only by changing what a
    // target is. The bore walls are cylindrical and shell refuses them, so this
    // will not reach 100 % on this fixture and should not.
    expect(
      measured.fraction,
      `clickable ${measured.reachable}/${measured.sampled} = ${(measured.fraction * 100).toFixed(1)}%`,
    ).toBeGreaterThanOrEqual(0.5);
  });

  test("measure: a vertex still beats the widened edge band", async ({
    page,
  }) => {
    const viewport = await openDensePlate(page);
    await page.keyboard.press("m");
    await expect(
      page.locator('[data-testid^="measure-vertex-"]').first(),
    ).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 4);

    // Widening the edges could have cost the vertices their precedence: a
    // corner sits under two marks, which is why `VERTEX_Z_RANGE` /
    // `EDGE_Z_RANGE` exist. The DOM saves us by mechanism — a `PickNode` is a
    // drei `Html` node ABOVE the canvas, so a pointer over a vertex square is
    // consumed before r3f ever raycasts. That is asserted here rather than
    // assumed, because "it works because of a layering detail" is exactly the
    // kind of guarantee that quietly stops being true.
    const vertex = page.locator('[data-testid^="measure-vertex-"]').first();
    const box = await vertex.boundingBox();
    expect(box, "a vertex mark is on screen").not.toBeNull();
    if (box === null) return;
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);

    // The edge band does not claim the point…
    await expect(viewport).not.toHaveAttribute(
      "data-measure-edge-hover",
      /.*/,
      { timeout: 5_000 },
    );
    // …and the click lands on the VERTEX, which the readout names.
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    await expect(page.getByTestId("measure-readout")).toContainText("Vertex");
  });

  test("measure: an edge answers along its whole span", async ({ page }) => {
    const viewport = await openDensePlate(page);
    await page.keyboard.press("m");
    await expect(
      page.locator('[data-testid^="measure-edge-"]').first(),
    ).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 4);

    const nodes = page.locator('[data-testid^="measure-edge-"]');
    const marks: EdgeMark[] = [];
    for (const node of await nodes.all()) {
      const testId = (await node.getAttribute("data-testid")) ?? "";
      const box = await node.boundingBox();
      if (box === null) continue;
      marks.push({
        index: Number(testId.replace("measure-edge-", "")),
        kind: "",
        label: (await node.getAttribute("aria-label")) ?? "",
        centre: { x: box.x + box.width / 2, y: box.y + box.height / 2 },
      });
    }
    expect(marks.length).toBeGreaterThan(10);

    // The same sweep against a DIFFERENT overlay and a different stamp: the
    // shared `EdgeBandLayer` has to be live here too, or Measure keeps the old
    // dot while Fillet gets the band — which is exactly the split SEL-4 exists
    // to close.
    const sampled: EdgeReach[] = [];
    for (const mark of marks.slice(0, 5)) {
      sampled.push(
        await measureReach(page, viewport, mark, "data-measure-edge-hover"),
      );
    }
    const report = sampled
      .map((r) => `#${r.mark.index} ${r.along}px`)
      .join(" ");

    await page.mouse.move(5, 5);
    await expect(viewport).not.toHaveAttribute(
      "data-measure-edge-hover",
      /.*/,
      { timeout: 5_000 },
    );

    // Same oracle as the fillet sibling, and at the same floor, for the same
    // reason: the count is what the assertion reads, so every edge it counts
    // has the claimed radius re-walked and settled before it is believed.
    let addressable = 0;
    const unconfirmed: string[] = [];
    for (const reach of sampled) {
      if (reach.along < ALONG_MIN_PX) continue;
      if (
        await reachHolds(
          page,
          viewport,
          "data-measure-edge-hover",
          reach.mark.centre,
          reach.bestDirection,
          ALONG_MIN_PX,
          String(reach.mark.index),
        )
      ) {
        addressable += 1;
      } else {
        unconfirmed.push(`#${reach.mark.index}@${ALONG_MIN_PX}px`);
      }
    }
    expect(
      addressable,
      `measure edges addressable >= ${ALONG_MIN_PX}px along: ${report}` +
        (unconfirmed.length > 0
          ? ` — the settled re-walk did not confirm ${unconfirmed.join(",")}`
          : ""),
    ).toBeGreaterThanOrEqual(2);
  });

  test("a HIDDEN body stops occluding the edges behind it", async ({
    page,
  }) => {
    // 13.5-14.6 s measured at load 13; the parked probe adds up to 9 s per
    // call over an empty span, three calls. Headroom, not a fix.
    test.setTimeout(300_000);
    // THE REASON YOU HIDE A BODY IS TO REACH WHAT IS BEHIND IT. The pick mesh
    // is fused, and three's raycaster never reads `material.visible` — only
    // `material.side` — so `Mesh.raycast` tests a switched-off body's triangles
    // exactly like a drawn one's (`partView.pickHiddenFaces`), and the band's
    // occlusion test used to measure that hit, so hiding the wall killed edge
    // picking over the whole region it used to cover. No spec covered
    // multi-body + hidden + edge pick, which is why it shipped (SEL-4 review,
    // 2026-08-08).
    const viewport = await openOccludedPlate(page);
    await armFilletPick(page);

    // The plate's two top edges — y = 30 (facing the camera) and y = 50 —
    // project to the SAME screen line in the front view, so either is a correct
    // answer for a probe on it. Named by their own OCCT mid-span rather than by
    // an index that depends on kernel order.
    const marks = await edgeMarks(page);
    const topEdges = marks.filter(
      (m) => m.kind === "line" && /centred at 30, (30|50), 10 /.test(m.label),
    );
    expect(
      topEdges.map((m) => m.index).sort(),
      `the plate's top edges are on offer (${marks.map((m) => m.label).join(" | ")})`,
    ).toHaveLength(2);
    const wanted = new Set(topEdges.map((m) => String(m.index)));
    const centre = (topEdges[0] as EdgeMark).centre;

    /**
     * Which edges answer along the occluded span, clear of any 24 px mark.
     *
     * SIX PARKED READS, not six bare ones. Both assertions below are strict
     * set-membership over this handful of points — `toEqual([])` and
     * `toHaveLength(1)` — and neither can absorb a single stamp that survived
     * the previous position. Parking off the body first makes every value in
     * the set provably this point's; it also happens to be the most generous
     * arrival path there is, which makes the "must not answer" control the
     * stronger claim rather than the weaker one.
     */
    const probe = async (): Promise<Set<string>> => {
      const seen = new Set<string>();
      for (const dx of [-45, -30, -18, 18, 30, 45]) {
        const stamped = await settledStampAt(
          page,
          viewport,
          "data-edge-pick-hover",
          { x: centre.x + dx, y: centre.y },
          PROBE_SETTLE_MS,
        );
        if (stamped !== null) seen.add(stamped);
      }
      return seen;
    };

    // 1) WITH BOTH BODIES DRAWN the edge is genuinely behind material, and the
    //    occlusion test is RIGHT to refuse it. This is the control that keeps
    //    the fix from being "delete the occlusion test".
    const occluded = await probe();
    expect(
      [...occluded].filter((s) => wanted.has(s)),
      "an edge behind drawn material must not answer",
    ).toEqual([]);

    // 2) HIDE ONE BODY AT A TIME. Hiding the wall must open the pick; hiding
    //    the plate itself must not (the wall is still in the way) — so exactly
    //    one of the two toggles changes the answer, whichever ordinal the
    //    kernel gave the wall.
    const answered: boolean[] = [];
    for (const index of [0, 1]) {
      await setBodyMode(page, index, "hidden");
      await waitForFrames(page, 4);
      const seen = await probe();
      answered.push([...seen].some((s) => wanted.has(s)));
      await setBodyMode(page, index, "solid");
      await waitForFrames(page, 4);
    }
    expect(
      answered,
      `edges behind the hidden body answered: body1=${answered[0]} body2=${answered[1]}`,
    ).toEqual(expect.arrayContaining([true]));
    expect(
      answered.filter(Boolean),
      "exactly ONE body is the occluder — hiding the other changes nothing",
    ).toHaveLength(1);

    // Negative control for the stamp: off the body it must clear, or every
    // probe above scored on a stuck attribute.
    await page.mouse.move(5, 5);
    await expect(viewport).not.toHaveAttribute("data-edge-pick-hover", /.*/, {
      timeout: 5_000,
    });
  });

  test("SEL-6 — a hidden body in FRONT no longer eats the pick for the body behind it", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    // THE HEADLINE NUMBER. SEL-4's shell pick refused a hidden body's face —
    // correctly — but could only ever REFUSE it: three's raycaster ignores
    // `material.visible`, r3f keeps ONE hit per object, so the nearest triangle
    // was the hidden wall's and the DRAWN plate behind it was never offered.
    // Measured on this fixture before the fix: 8.5 % of the plate's lit pixels
    // could address a face with the wall hidden, against 98 % with both bodies
    // drawn — i.e. hiding the thing in your way, which is the whole reason to
    // hide it, took the pick with it, and it did so BELOW the >= 50 % floor
    // SEL-4 itself establishes for this overlay a few tests above.
    const viewport = await openOccludedPlate(page);

    // WHICH ROW IS THE WALL, discovered rather than assumed — a kernel ordinal
    // is not a contract. See `litAfterHiding`.
    const litWithout = [
      await litAfterHiding(page, 0),
      await litAfterHiding(page, 1),
    ];
    const wall = (litWithout[0] as number) < (litWithout[1] as number) ? 0 : 1;
    const plate = 1 - wall;
    expect(
      Math.max(...litWithout) / Math.max(1, Math.min(...litWithout)),
      `the two bodies must be tellable apart by silhouette: ${litWithout.join(" vs ")} lit points`,
    ).toBeGreaterThan(1.5);

    await expect(page.getByTestId("new-shell")).toBeEnabled({
      timeout: 30_000,
    });
    await page.getByTestId("new-shell").click();
    await expect(page.getByTestId("shell-editor")).toBeVisible();
    await expect(
      page.locator('[data-testid^="shell-face-"]').first(),
    ).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 6);

    /**
     * The FB-3/FB-5 census, over whatever is currently lit.
     *
     * Parked before each leg — the step before a census is always a
     * `setBodyMode` click, and without this the first probe of the leg is free
     * to read that click's leftover stamp as its own answer. Per-point reads
     * stay cheap: see the ORACLE block for why a 50 % floor measured at 98 %
     * does not buy 3 x 135 parked probes.
     */
    const census = async () => {
      const points = await litPoints(page, { step: 24 });
      await parkOffBody(page, "data-shell-face-hover");
      return measureReachabilityWith(points, async (point) => {
        await page.mouse.move(point.x, point.y);
        return (await viewport.getAttribute("data-shell-face-hover")) !== null;
      });
    };
    const pct = (n: number) => `${(n * 100).toFixed(1)}%`;

    const bothDrawn = await census();
    await setBodyMode(page, wall, "hidden");
    await waitForFrames(page, 6);
    const wallHidden = await census();
    await setBodyMode(page, wall, "solid");
    await waitForFrames(page, 6);
    await setBodyMode(page, plate, "hidden");
    await waitForFrames(page, 6);
    const plateHidden = await census();
    await setBodyMode(page, plate, "solid");
    await waitForFrames(page, 6);

    const report =
      `both drawn ${bothDrawn.reachable}/${bothDrawn.sampled} = ${pct(bothDrawn.fraction)}; ` +
      `WALL (row ${wall}) hidden ${wallHidden.reachable}/${wallHidden.sampled} = ${pct(wallHidden.fraction)}; ` +
      `plate (row ${plate}) hidden ${plateHidden.reachable}/${plateHidden.sampled} = ${pct(plateHidden.fraction)}`;

    for (const leg of [bothDrawn, wallHidden, plateHidden]) {
      expect(leg.sampled, `body sampled (${report})`).toBeGreaterThan(40);
    }

    // NON-VACUITY: a stamp that got stuck set would score every leg at 100 %.
    await page.mouse.move(5, 5);
    await expect(viewport).not.toHaveAttribute("data-shell-face-hover", /.*/, {
      timeout: 5_000,
    });

    // The two CONTROLS first, so a regression in either is not mistaken for the
    // claim: nothing about hiding a body behind, or hiding nothing at all,
    // should move the number.
    expect(
      bothDrawn.fraction,
      `control, both drawn (${report})`,
    ).toBeGreaterThanOrEqual(0.5);
    expect(
      plateHidden.fraction,
      `control, the body BEHIND hidden (${report})`,
    ).toBeGreaterThanOrEqual(0.5);

    // THE CLAIM, against the same floor SEL-4 set at `pick-affordance.spec.ts`'s
    // shell census: with the occluder switched off, the body you switched it off
    // to reach is a pick target. Measured 8.5 % before the fix.
    expect(
      wallHidden.fraction,
      `the WALL is hidden and the plate behind it must be pickable — ${report}`,
    ).toBeGreaterThanOrEqual(0.5);
  });

  test("SEL-6 — and the occlusion test still applies BEHIND a hidden body", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    // THE OPPOSITE FACE OF THE SAME BUG, and the reason this fix is not "delete
    // the occlusion test". While a hidden wall was the nearest surface hit,
    // `edgeBand` discarded it and left `surfaceDistance` null — so BEHIND a
    // hidden body every edge was accepted, including edges buried inside the
    // still-DRAWN plate. Both faces close together, because the hidden
    // triangle now never reaches the intersection list at all.
    //
    // The scene probe is installed for `tiltOffTheFaceView`, which asserts on
    // the live camera's direction rather than on a stamp; `addInitScript` only
    // applies to loads that come after it, so it must precede the fixture.
    await installSceneProbe(page);
    const viewport = await openOccludedPlate(page);
    const litWithout = [
      await litAfterHiding(page, 0),
      await litAfterHiding(page, 1),
    ];
    const wall = (litWithout[0] as number) < (litWithout[1] as number) ? 0 : 1;
    expect(
      Math.max(...litWithout) / Math.max(1, Math.min(...litWithout)),
      `the two bodies must be tellable apart by silhouette: ${litWithout.join(" vs ")} lit points`,
    ).toBeGreaterThan(1.5);

    // Leave the face view before arming: under an orthographic FRONT view the
    // buried edge has no screen position of its own. See the helper.
    await tiltOffTheFaceView(page);
    await armFilletPick(page);

    /**
     * The plate's BACK-BOTTOM edge and its y = 30 twin, named by their own OCCT
     * mid-spans rather than by kernel indices.
     *
     * That edge is the one entity of this fixture that is unambiguously INSIDE
     * the solid: its two faces (the plate's underside and its back) both point
     * away from the camera, so a ray to it crosses 14.1 mm of still-drawn plate
     * — and, while the wall is drawn, the wall as well. The twin is the
     * silhouette edge between the plate's visible front and bottom faces.
     *
     * The 45 degree tilt `tiltOffTheFaceView` applies is what makes the two
     * SEPARABLE, and it separates them in the PROJECTION PLANE rather than by
     * foreshortening — so the guard below no longer depends on how far away the
     * camera happens to be framed. Measured across the three regimes, on the
     * same fixture and the same two 60 mm edges:
     *
     *   orthographic FRONT (what CI hit)     0.0016 px   — coincident
     *   perspective FRONT (what this was)      ~29    px   — depth parallax
     *   orthographic 45 deg front-top         166.8   px   — projection plane
     *
     * The guard demands 12. The middle row is the one to keep in mind: it was
     * only ever twice the corridor, and it was a function of the fit distance,
     * so this probe was one framing change away from going vacuous even before
     * the projection changed.
     */
    const buriedPair = async () => {
      const marks = await edgeMarks(page);
      const buried = marks.find((m) => /centred at 30, 50, 0 /.test(m.label));
      const twin = marks.find((m) => /centred at 30, 30, 0 /.test(m.label));
      expect(
        buried,
        `the plate's back-bottom edge is on offer (${marks.map((m) => m.label).join(" | ")})`,
      ).toBeDefined();
      expect(twin, "its visible y = 30 twin is on offer too").toBeDefined();
      if (buried === undefined || twin === undefined) {
        throw new Error("the plate's bottom edges are not on offer");
      }
      expect(
        Math.abs(buried.centre.y - twin.centre.y),
        "the twins must be further apart than the 12 px corridor, or this probe measures the VISIBLE edge",
      ).toBeGreaterThan(EDGE_CORRIDOR_PX);
      return { marks, buried };
    };

    /**
     * Which edges answer along a mark's own line, clear of its 24 px mark.
     *
     * Parked per position, as in the sibling above: this set feeds two
     * `not.toContain` refusals AND one `toContain` — so a survivor of the
     * previous position can produce either a false red or a false green here,
     * and six extra waits is the whole price of removing both.
     */
    const probe = async (mark: EdgeMark): Promise<Set<string>> => {
      const seen = new Set<string>();
      for (const dx of [-45, -30, -18, 18, 30, 45]) {
        const stamped = await settledStampAt(
          page,
          viewport,
          "data-edge-pick-hover",
          { x: mark.centre.x + dx, y: mark.centre.y },
          PROBE_SETTLE_MS,
        );
        if (stamped !== null) seen.add(stamped);
      }
      return seen;
    };

    // 1) BOTH BODIES DRAWN — refused, which is the pre-existing behaviour.
    const drawn = await buriedPair();
    const drawnSeen = await probe(drawn.buried);
    expect(
      [...drawnSeen],
      `an edge inside the solid must not answer with both bodies drawn (answered: ${[...drawnSeen].join(",") || "nothing"})`,
    ).not.toContain(String(drawn.buried.index));

    // 2) WALL HIDDEN — the case that regressed. The plate is still drawn and
    //    the edge is still buried inside it, so the answer must not change.
    //    Before the fix it DID: the hidden wall's hit was discarded,
    //    `surfaceDistance` stayed null, and the buried edge answered.
    //
    //    The marks are RE-READ rather than reused: the framing follows the
    //    visible bounds, so hiding the wall moves every mark on screen and a
    //    stale coordinate would probe empty space.
    await setBodyMode(page, wall, "hidden");
    await waitForFrames(page, 6);
    const behind = await buriedPair();
    const behindSeen = await probe(behind.buried);
    expect(
      [...behindSeen],
      `hiding the wall must not make the plate transparent (answered: ${[...behindSeen].join(",") || "nothing"})`,
    ).not.toContain(String(behind.buried.index));

    // …AND THE FIX IS NOT "REFUSE EVERYTHING". The plate's own VISIBLE top edge
    // answers over the span the hidden wall used to cover — the claim of the
    // census above, stated on the edge overlay, and the non-vacuity guard for
    // the two refusals: a dead stamp would satisfy both of them.
    const topFront = behind.marks.find((m) =>
      /centred at 30, 30, 10 /.test(m.label),
    );
    expect(
      topFront,
      "the plate's visible front-top edge is on offer",
    ).toBeDefined();
    if (topFront === undefined) return;
    const live = await probe(topFront);
    expect(
      [...live],
      `the visible top edge over the hidden wall's span (answered: ${[...live].join(",") || "nothing"})`,
    ).toContain(String(topFront.index));

    await page.mouse.move(5, 5);
    await expect(viewport).not.toHaveAttribute("data-edge-pick-hover", /.*/, {
      timeout: 5_000,
    });
  });

  test("SEL-6 — the default face hover sees past a hidden body too", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    // `ModelMesh`'s own face-grain hover (SEL-1 A1) had the same defect on the
    // same mechanism: the nearest triangle won even when its body was switched
    // off, so `data-hovered-face` went silent over the region the wall covered
    // instead of naming the plate's face behind it.
    const viewport = await openOccludedPlate(page);
    const litWithout = [
      await litAfterHiding(page, 0),
      await litAfterHiding(page, 1),
    ];
    const wall = (litWithout[0] as number) < (litWithout[1] as number) ? 0 : 1;

    // Where the wall DRAWS today — the region whose picks it used to eat.
    const covered = await litPoints(page, { step: 24 });
    await setBodyMode(page, wall, "hidden");
    await waitForFrames(page, 6);
    const stillLit = await litPoints(page, { step: 24 });
    const litKeys = new Set(
      stillLit.map((p) => `${Math.round(p.x)},${Math.round(p.y)}`),
    );
    const nowEmpty = covered.filter(
      (p) => !litKeys.has(`${Math.round(p.x)},${Math.round(p.y)}`),
    );
    expect(stillLit.length, "the plate is still on screen").toBeGreaterThan(20);
    expect(
      nowEmpty.length,
      "the wall really did cover part of the frame",
    ).toBeGreaterThan(20);

    /*
      "LIT BEFORE AND NOT LIT NOW" IS NOT "THE REGION THE WALL VACATED", and
      the difference is what made this test fail 1 run in 4 (CI-4 pass,
      2026-08-29). Two censuses taken under DIFFERENT camera framings — hiding
      the wall refits the view to the visible bounds, so the plate moves and
      grows — are differenced here, so `nowEmpty` picks up not only the wall's
      old span but every pixel the REFIT moved, including the still-drawn
      plate's own outline. `litPoints` reads one pixel against a luminance
      floor, and a body's drawn edge is a dark rim plus an outline stroke ~5 px
      wide that is under that floor while being squarely ON the solid.

      Measured on the failing run: 5 ghosts, all five in ONE grid column at
      x = 1236, with the plate's last lit pixel at x = 1234 on every one of
      those rows (lum 178 at 1234, 65 at 1236, 89 at 1238, 18 at 1240). The
      face oracle was RIGHT and the region was wrong.

      So the sweep is restricted to points that are background with room to
      spare. This is not a widened tolerance — the assertion below is still
      `toBe(0)` — it is the census refusing to ask the oracle about pixels its
      own classifier cannot decide. The strong claim, stated by ORDINAL over
      the whole canvas rather than by luminance difference, is
      `qa-sel6-verify.spec.ts`'s "a hidden body's ordinals answer at NO point
      on the canvas" (1710 points, 0 naming a hidden face), so nothing this
      erosion could hide is ungated.
    */
    const vacated = await clearOfSilhouette(page, nowEmpty, {
      marginPx: SILHOUETTE_MARGIN_PX,
    });
    expect(
      vacated.length,
      `vacated points clear of the drawn body by ${SILHOUETTE_MARGIN_PX}px ` +
        `(${nowEmpty.length - vacated.length} of ${nowEmpty.length} discarded ` +
        `as silhouette-adjacent)`,
    ).toBeGreaterThan(20);
    console.log(
      `    [SEL-6] vacated region: ${vacated.length} clear of ` +
        `${nowEmpty.length} candidates ` +
        `(${nowEmpty.length - vacated.length} within ${SILHOUETTE_MARGIN_PX}px of drawn pixels)`,
    );

    // A FRACTION against a 50 % floor, measured at 99.3 % — parked once at the
    // start so the first probe cannot inherit the `setBodyMode` click's stamp,
    // then cheap per point. The margin is 66 of 135 points; no per-probe race
    // crosses that.
    await parkOffBody(page, "data-hovered-face");
    const answered = await measureReachabilityWith(stillLit, async (point) => {
      await page.mouse.move(point.x, point.y);
      return (await viewport.getAttribute("data-hovered-face")) !== null;
    });

    // THE GHOST SWEEP IS A DIFFERENT KIND OF ASSERTION AND GETS A DIFFERENT
    // TREATMENT: `toBe(0)` has no margin at all, so a single point that reads
    // non-null fails it — and the point most at risk is the FIRST, which
    // follows ~135 mostly-non-null probes over the drawn plate. A bare read
    // there is free to hand the last on-plate stamp to the first off-plate
    // point, which is precisely the carry-over `2f0b361` measured on the hole
    // raster. So the sweep stays the cheap filter and every CANDIDATE is
    // re-asked with the pointer parked off the body first. Measured 0/832 both
    // ways on this build, so in the healthy case this costs one park.
    await parkOffBody(page, "data-hovered-face");
    const ghosts: Point[] = [];
    for (const point of vacated) {
      await page.mouse.move(point.x, point.y);
      if ((await viewport.getAttribute("data-hovered-face")) === null) continue;
      const settled = await settledStampAt(
        page,
        viewport,
        "data-hovered-face",
        point,
        PROBE_SETTLE_MS,
      );
      if (settled !== null) ghosts.push(point);
    }

    await page.mouse.move(5, 5);
    await expect(viewport).not.toHaveAttribute("data-hovered-face", /.*/, {
      timeout: 5_000,
    });

    // The drawn plate names a face…
    expect(
      answered.fraction,
      `hovered faces over the still-drawn plate: ${answered.reachable}/${answered.sampled}`,
    ).toBeGreaterThanOrEqual(0.5);
    // …and the vacated region names nothing, which is the guard that seeing
    // PAST the hidden body did not make it pickable.
    expect(
      ghosts.length,
      `points over the vacated region that still name a face, confirmed with ` +
        `the pointer parked off the body first: ${ghosts.length}/${vacated.length}` +
        (ghosts.length > 0
          ? ` at ${ghosts
              .slice(0, 8)
              .map((p) => `${Math.round(p.x)},${Math.round(p.y)}`)
              .join(" ")}${ghosts.length > 8 ? " …" : ""}`
          : ""),
    ).toBe(0);
  });

  test("SEL-6 — a hidden body stops OFFERING picks, not only eating them", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    // THE MIRROR HALF, and the gap the first SEL-6 pass left open (review,
    // 2026-08-08). `/overlay` describes the WHOLE part with no notion of
    // visibility, so a switched-off body kept every one of its entities on
    // offer: its edges hoverable and clickable through the full 24 px
    // `EdgeBandLayer` corridor (a 24 px dot before SEL-4 widened it), its faces
    // selectable through their centroid marks, and a brass `FacePatch` painted
    // over the empty space where the body used to be. The previous gate here
    // hid the plate and asserted only that the WALL still occludes — it never
    // asked whether the hidden plate had left the offer.
    const viewport = await openOccludedPlate(page);

    // The lit silhouette with BOTH bodies drawn, captured before anything is
    // armed: the region the wall covers is where its entities live on screen.
    const covered = await litPoints(page, { step: 24 });

    await armFilletPick(page);
    const both = await splitEdgeMarks(page);
    expect(
      [both.wall.length, both.plate.length],
      `both bodies' edges are on offer (${both.marks.map((m) => m.label).join(" | ")})`,
    ).toEqual([12, 12]);

    // WHICH ROW IS THE WALL, discovered rather than assumed — a kernel ordinal
    // is not a contract. Hiding one body must remove exactly ITS edges from
    // the offer and leave the other's untouched, so the two rows answer
    // symmetrically and neither ordering needs to be known in advance.
    const afterHiding: { wall: number; plate: number }[] = [];
    for (const row of [0, 1]) {
      await setBodyMode(page, row, "hidden");
      await waitForFrames(page, 6);
      const split = await splitEdgeMarks(page);
      afterHiding.push({ wall: split.wall.length, plate: split.plate.length });
      await setBodyMode(page, row, "solid");
      await waitForFrames(page, 6);
    }
    const report = afterHiding
      .map((r, i) => `row ${i}: ${r.wall} wall + ${r.plate} plate edges`)
      .join("; ");
    // Before the fix BOTH rows read "12 wall + 12 plate" — hiding a body
    // removed nothing from the offer.
    expect(
      afterHiding.map((r) => `${r.wall}/${r.plate}`).sort(),
      `exactly the hidden body's edges leave the offer (${report})`,
    ).toEqual(["0/12", "12/0"]);
    const wall = afterHiding[0]?.wall === 0 ? 0 : 1;

    // …AND THE CORRIDOR GOES WITH THEM. A mark can be gone from the DOM while
    // the band still answers along the edge, which is the half SEL-4 made
    // bigger: the sweep is over the region the wall VACATED, and no probe
    // there may report an edge the wall owned. Plate edges may legitimately
    // answer here — their corridor is 12 px wide and the bodies are close — so
    // the assertion names the wall's indices rather than demanding silence.
    const wallEdges = new Set(both.wall.map((m) => String(m.index)));
    await setBodyMode(page, wall, "hidden");
    await waitForFrames(page, 6);
    const stillLit = await litPoints(page, { step: 24 });
    const litKeys = new Set(
      stillLit.map((p) => `${Math.round(p.x)},${Math.round(p.y)}`),
    );
    const nowEmpty = covered.filter(
      (p) => !litKeys.has(`${Math.round(p.x)},${Math.round(p.y)}`),
    );
    expect(
      nowEmpty.length,
      "the wall really did cover part of the frame",
    ).toBeGreaterThan(20);
    // The sweep is the cheap filter and the `toEqual([])` is strict, so any
    // stamp naming a WALL edge is re-asked at its own point with the pointer
    // parked off the body first. Plate edges are collected for the message and
    // deliberately not re-asked — they are allowed here, so confirming them
    // would be paying for a value nothing decides.
    await parkOffBody(page, "data-edge-pick-hover");
    const stamped = new Set<string>();
    const wallStillAnswering = new Set<string>();
    for (const point of nowEmpty) {
      await page.mouse.move(point.x, point.y);
      const value = await viewport.getAttribute("data-edge-pick-hover");
      if (value === null) continue;
      stamped.add(value);
      if (!wallEdges.has(value)) continue;
      const settled = await settledStampAt(
        page,
        viewport,
        "data-edge-pick-hover",
        point,
        PROBE_SETTLE_MS,
      );
      if (settled !== null && wallEdges.has(settled)) {
        wallStillAnswering.add(settled);
      }
    }
    expect(
      [...wallStillAnswering],
      `edges of the hidden wall still answering over the space it vacated (all stamps: ${[...stamped].join(",") || "none"})`,
    ).toEqual([]);

    // NON-VACUITY, two ways: the stamp clears off the body (so the sweep was
    // not reading a dead attribute), and showing the wall again brings its 12
    // edges back — the filter is a view of the state, not a one-way sink.
    await page.mouse.move(5, 5);
    await expect(viewport).not.toHaveAttribute("data-edge-pick-hover", /.*/, {
      timeout: 5_000,
    });
    await setBodyMode(page, wall, "solid");
    await waitForFrames(page, 6);
    const restored = await splitEdgeMarks(page);
    expect(
      [restored.wall.length, restored.plate.length],
      "showing the body puts its edges back on offer",
    ).toEqual([12, 12]);

    // THE FACE HALF, on the overlay whose only DOM target is a centroid mark.
    await page.getByTestId("fillet-cancel").click();
    await expect(page.getByTestId("new-shell")).toBeEnabled({
      timeout: 30_000,
    });
    await page.getByTestId("new-shell").click();
    await expect(page.getByTestId("shell-editor")).toBeVisible();
    await expect(
      page.locator('[data-testid^="shell-face-"]').first(),
    ).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 6);

    const facesDrawn = await splitFaceMarks(page);
    expect(
      [facesDrawn.wall, facesDrawn.plate],
      "both bodies' faces are on offer",
    ).toEqual([6, 6]);
    await setBodyMode(page, wall, "hidden");
    await waitForFrames(page, 6);
    const facesHidden = await splitFaceMarks(page);
    expect(
      [facesHidden.wall, facesHidden.plate],
      `the hidden body's faces leave the offer (${facesHidden.wall} wall + ${facesHidden.plate} plate)`,
    ).toEqual([0, 6]);
    await setBodyMode(page, wall, "solid");
    await waitForFrames(page, 6);
  });

  test("hole: the face is the placement target, and a snap still lands exact", async ({
    page,
  }) => {
    const viewport = await openDensePlate(page);
    await expect(page.getByTestId("new-hole")).toBeEnabled({ timeout: 30_000 });
    await page.getByTestId("new-hole").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();

    // Seat the hole on the plate's TOP face — the one carrying the bolt circle,
    // named by its own z rather than by an index that depends on kernel order.
    const faces = page.locator('[data-testid^="plane-pick-face-"]');
    await expect(faces.first()).toBeVisible({ timeout: 20_000 });
    let topIndex = 0;
    let topZ = -Infinity;
    const all = await faces.all();
    for (let i = 0; i < all.length; i += 1) {
      const label = (await all[i]?.getAttribute("aria-label")) ?? "";
      const nums = label.match(/-?\d+(?:\.\d+)?/g) ?? [];
      const z = Number.parseFloat(nums[nums.length - 1] ?? "NaN");
      if (Number.isFinite(z) && z > topZ) {
        topZ = z;
        topIndex = i;
      }
    }
    await all[topIndex]?.click();
    await expect(page.getByTestId("hole-position")).toContainText(
      "Centre of face",
    );

    await page.getByTestId("hole-point-pick").click();
    await expect(page.getByTestId("hole-point-center")).toBeVisible({
      timeout: 20_000,
    });
    await waitForFrames(page, 4);

    // FREE PLACEMENT — the behaviour change SEL-4 ships. Find a lit point on
    // the top face that is clear of every snap mark, and drill there. Under the
    // old overlay this click did nothing at all: the only live targets were the
    // centre, the four corners and the seven bore centres, which is why a
    // fifth mounting hole on a vendor plate could not be authored (QA3-1).
    const snapBoxes = (
      await Promise.all(
        (
          await page
            .locator(
              '[data-testid^="hole-point-center"], [data-testid^="hole-point-vertex-"], [data-testid^="hole-point-circle-"]',
            )
            .all()
        ).map((n) => n.boundingBox()),
      )
    ).flatMap((b) => (b === null ? [] : [b]));
    const points = await litPoints(page, { step: 12 });
    let placed: Point | null = null;
    let confirmations = 0;
    for (const point of points) {
      const clear = snapBoxes.every(
        (b) =>
          point.x < b.x - 16 ||
          point.x > b.x + b.width + 16 ||
          point.y < b.y - 16 ||
          point.y > b.y + b.height + 16,
      );
      if (!clear) continue;
      await page.mouse.move(point.x, point.y);
      // The FILTER: one round trip over ~1500 grid points, and it is allowed to
      // be wrong at the face's edge because nothing is drilled on its word.
      if ((await viewport.getAttribute("data-hole-point-hover")) === null) {
        continue;
      }
      // The ORACLE (see confirmsPlacementFace). Bounded, because each one is a
      // settle: a healthy scan needs one or two, so 12 is headroom, not a
      // budget the run is expected to spend.
      confirmations += 1;
      if (confirmations > 12) break;
      if (await confirmsPlacementFace(page, point)) {
        placed = point;
        break;
      }
    }
    expect(
      placed,
      "a point on the placement face, clear of every snap mark",
    ).not.toBeNull();
    if (placed === null) return;

    await page.mouse.click(placed.x, placed.y);
    // The readout leaves "Centre of face" for a real coordinate — the click
    // placed the drill somewhere the old overlay could not reach.
    await expect(page.getByTestId("hole-position")).not.toContainText(
      "Centre of face",
    );
    await expect(page.getByTestId("hole-position")).toContainText("mm");

    // …AND THE SNAP STILL WINS WHERE IT SHOULD. A bore centre clicked through
    // its `PickNode` echoes the exact centre, not the pixel under the cursor:
    // the DOM node sits above the canvas, so the raycast never runs there.
    await page.getByTestId("hole-point-pick").click();
    const circle = page.locator('[data-testid^="hole-point-circle-"]').first();
    await expect(circle).toBeVisible({ timeout: 20_000 });
    await circle.click();
    await expect(page.getByTestId("hole-position")).toContainText("mm");

    // Negative control for the stamp — a stuck attribute would make the free
    // placement search above succeed anywhere, including off the body.
    await page.mouse.move(5, 5);
    await expect(viewport).not.toHaveAttribute("data-hole-point-hover", /.*/, {
      timeout: 5_000,
    });
  });

  test("assembly mates: each INSTANCE's own geometry is the mate target", async ({
    page,
  }) => {
    // The same ceiling its four heavy siblings in this file already take, which
    // this one was simply never given. It runs a `litPoints` census over two
    // plates plus TWO `measureReach` sweeps (DIRECTIONS x RADII pointer moves
    // each), and measured ALONE in a quiet window it takes 44.9 s against the
    // config's 60 s default — 15 s of headroom for a test whose cost is three
    // sweeps. It duly timed out inside the final sweep in a five-spec run
    // (2026-08-11), a false red in nobody's diff.
    test.setTimeout(300_000);
    // The mate half of SEL-4 shipped without a gate. The only mate coverage —
    // `assembly.spec.ts` via `authorBoltMates` — dispatches clicks straight at
    // `mate-face-*` / `mate-axis-*` by test id, which is verbatim the "the
    // suite proved a path no hand takes" failure the conversion exists to fix:
    // those specs passed before it and after it, so they cannot discriminate.
    // This one aims at the geometry.
    const { idA, idB } = await setupTwoInstances(page);
    const viewport = page.getByTestId("viewport");

    await page.getByTestId("mate-coincident").click();
    await expect(page.getByTestId("mate-hud")).toBeVisible();
    await expect(
      page.locator('[data-testid^="mate-face-"]').first(),
    ).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 6);

    // The FB-3/FB-5 census over both plates at once. The stamp carries
    // `instanceId:index`, so this measures not just "something answered" but
    // WHICH instance answered — a single shared hover writer cannot fake it.
    // Parked before the census, as everywhere else here, so the first probe
    // cannot read the `mate-coincident` click's leftover stamp as its own.
    const stamps = new Set<string>();
    const points = await litPoints(page, { step: 24 });
    await parkOffBody(page, "data-mate-pick-hover");
    const measured = await measureReachabilityWith(points, async (point) => {
      await page.mouse.move(point.x, point.y);
      const stamped = await viewport.getAttribute("data-mate-pick-hover");
      if (stamped !== null) stamps.add(stamped);
      return stamped !== null;
    });
    expect(measured.sampled, "two plates sampled").toBeGreaterThan(40);

    await page.mouse.move(5, 5);
    await expect(viewport).not.toHaveAttribute("data-mate-pick-hover", /.*/, {
      timeout: 5_000,
    });

    // The same 50 % floor the shell and sketch-plane picks are held to. The
    // Ø10 bore wall is cylindrical and a coincident mate refuses it, so this
    // will not reach 100 % on this fixture and should not.
    expect(
      measured.fraction,
      `mate faces clickable ${measured.reachable}/${measured.sampled} = ${(measured.fraction * 100).toFixed(1)}%`,
    ).toBeGreaterThanOrEqual(0.5);

    // BOTH instances answer, and each answers AS ITSELF. This is the
    // cross-instance check: the overlays are siblings writing one stamp, so a
    // hover owned per-overlay can have A's unmount clobber B's live value.
    expect(
      new Set([...stamps].map((s) => s.split(":")[0])),
      `instances addressed: ${[...stamps].join(" ")}`,
    ).toEqual(new Set([idA, idB]));

    // …AND THE AXIS PICK IS A BAND, not a diamond. Same sweep as the part
    // workspace, against the assembly's own `EdgeBandLayer` mount.
    await page.getByTestId("mate-concentric").click();
    await expect(page.getByTestId("mate-hud")).toBeVisible();
    const axes = page.locator(`[data-testid^="mate-axis-${idA}-"]`);
    await expect(axes.first()).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 4);

    const sampled: EdgeReach[] = [];
    for (const node of (await axes.all()).slice(0, 2)) {
      const testId = (await node.getAttribute("data-testid")) ?? "";
      const box = await node.boundingBox();
      if (box === null) continue;
      const index = Number(testId.replace(`mate-axis-${idA}-`, ""));
      sampled.push(
        await measureReach(
          page,
          viewport,
          {
            index,
            kind: "circle",
            label: (await node.getAttribute("aria-label")) ?? "",
            centre: { x: box.x + box.width / 2, y: box.y + box.height / 2 },
          },
          "data-mate-pick-hover",
          `${idA}:${index}`,
        ),
      );
    }
    const report = sampled
      .map((r) => `#${r.mark.index} ${r.along}px`)
      .join(" ");
    // THE ONE READER IN THIS FILE LEFT UNCONFIRMED, deliberately, and this
    // comment is the handover rather than an excuse. Every other reach gate
    // above now re-walks its claimed radius through `reachHolds`; this one does
    // not, because doing so turns it RED — and the red is real. Measured at
    // load average 13 on 4 cores:
    //
    //   · On the UNMODIFIED file (only a `console.log` added, so none of this is
    //     the CI-4 diff) the sweep reported `#14 40px` in 5 runs of 7 and
    //     `#14 28px` in the other 2. The 28s FAILED. This gate is therefore
    //     ALREADY a ~29 % flake in CI, and has been.
    //   · Every 40 px reading is refused by the settled re-walk — 5 of 5 across
    //     two protocols. So on the runs where it passes, it passes on a one-ring
    //     carry-over from 28 px, which is exactly the defect class CI-4 exists
    //     to remove.
    //   · The measurement is not stable enough to re-baseline against, which is
    //     why no threshold here was moved: across 15 runs `#14` came back 20,
    //     28, 40 and 90 px. `setupTwoInstances` never pins the camera the way
    //     `openDensePlate` does ("only comparable between runs if the part is
    //     the same size in frame"), and adding that pin here did NOT close it
    //     either — pinned, the sweep still read 28/40/40/40/90. So the cause is
    //     upstream of the framing and upstream of this file.
    //
    // What it SHOULD assert, when the fixture can support it: a reach CONFIRMED
    // by `reachHolds`, against a floor derived from the mark it discriminates
    // against — a 24 px `PickNode` scores 13 px on this sweep (the header's own
    // mutation run), and 20 px is the smallest RADII ring whose diagonal
    // (14.1, 14.1) falls outside a 12 px half-extent, so `>= 20` confirmed is
    // the honest statement of "a band, not a diamond". Gating that needs a
    // stable assembly fixture first, which is `assemblyFlow.ts`, not here.
    expect(
      sampled.filter((r) => r.along >= ALONG_MIN_PX).length,
      `mate axes addressable >= ${ALONG_MIN_PX}px along: ${report}`,
    ).toBeGreaterThanOrEqual(1);
  });
});

test.describe("SEL-4 — founder screenshots", () => {
  async function captureEdgePick(
    page: Page,
    width: "desktop" | "laptop",
  ): Promise<void> {
    const viewport = await openDensePlate(page);
    await armFilletPick(page);
    // Park the pointer ON a bore mouth, well away from its mark, so the shot is
    // the thing that changed: the edge lights because the EDGE is the target,
    // not because the cursor found a 24 px diamond. The bore is chosen by
    // MEASURED reach rather than by index — the first circle in kernel order is
    // as likely as not the occluded bottom mouth, and parking on that would
    // photograph the occlusion test doing its job instead of the band doing
    // its job.
    const circles = (await edgeMarks(page)).filter((m) => m.kind === "circle");
    let target: { point: Point; reach: number } | null = null;
    for (const circle of circles) {
      // Stop at the first bore that is genuinely reachable. The kernel emits
      // every bore's BOTTOM mouth before any of the tops, so scanning a fixed
      // prefix photographs seven occluded circles and nothing else — measured
      // 2026-08-08, and it produced a byte-identical "after" shot.
      if (target !== null && target.reach >= ALONG_MIN_PX) break;
      const reach = await measureReach(page, viewport, circle);
      const radius = reach.along;
      if (target !== null && radius <= target.reach) continue;
      target = {
        reach: radius,
        // 60 % of the way out: unambiguously off the mark, comfortably inside
        // the corridor, so the shot does not depend on a boundary pixel. No
        // oracle here — nothing is ASSERTED on this number, it only aims the
        // camera, and the screenshot itself is the evidence.
        point: radialPoint(circle.centre, reach.bestDirection, radius * 0.6),
      };
    }
    // With the band gone this is every-direction zero, so the pointer lands on
    // the mark itself — which is exactly the "before" picture.
    const point = target?.point ?? circles[0]?.centre;
    if (point !== undefined) await page.mouse.move(point.x, point.y);
    await waitForFrames(page, 4);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sel4-edge-band-${width}.png`,
    });
  }

  test("armed edge pick on a bolt circle (desktop 1600×1000)", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1600, height: 1000 });
    await captureEdgePick(page, "desktop");
  });

  test("armed edge pick on a bolt circle (small laptop 1280×800)", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await captureEdgePick(page, "laptop");
  });
});
