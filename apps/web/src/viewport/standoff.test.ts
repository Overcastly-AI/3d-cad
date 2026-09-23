import { Box3, Vector3 } from "three";
import { describe, expect, it } from "vitest";

import { fitDistance, fitZoom, targetShift, type Rect } from "./fitFraming";
import {
  apparentSizeMm,
  boxCornersInCameraAxes,
  frameOverrun,
  overrunNeedsRefit,
  PICK_CAMERA_DISTANCE_MM,
  planePickDistanceMm,
  type PlanePickStandoff,
  type ProjectionState,
} from "./standoff";

/**
 * THE PLANE-PICK VANTAGE HAS TO SEE THE SUBJECT.
 *
 * These are the assertions the fixed 230 mm could not pass and nothing was
 * asking it to. Every fixture this repo grades itself on is small enough that
 * 230 mm frames it, so the hardcoded distance was correct on 100 % of the
 * corpus and inside the first real part it met — measured on the gauntlet's
 * 1280 mm gearbox, where 226 of 452 face marks ended up behind the camera and
 * `elementFromPoint` resolved zero of them.
 *
 * The sizes below are therefore chosen to straddle the boundary deliberately:
 * a 30 mm box (the repo's own fixture class) must be UNCHANGED, and a 1280 mm
 * rail must move. A test that only checked the big part would pass a function
 * that zoomed out of everything.
 */

/** A 1280x652 frame with a 330 px panel down the left — the measured shell. */
const CANVAS: Rect = { x: 0, y: 0, width: 1280, height: 652 };
const FREE: Rect = { x: 330, y: 0, width: 950, height: 652 };
const FOV = 40;

/** The shipped plane-pick attitude, resolved into a camera basis. */
function basis(): PlanePickStandoff {
  const dir = new Vector3(1, 0.68, 1.35).normalize();
  const up = new Vector3(0, 1, 0);
  const right = new Vector3().crossVectors(up, dir).normalize();
  return {
    right,
    up: new Vector3().crossVectors(dir, right).normalize(),
    dir,
    target: new Vector3(0, 0, 0),
  };
}

/** A box centred on the origin, `x`/`y`/`z` being its FULL extents (mm). */
function centred(x: number, y: number, z: number): Box3 {
  return new Box3(
    new Vector3(-x / 2, -y / 2, -z / 2),
    new Vector3(x / 2, y / 2, z / 2),
  );
}

describe("planePickDistanceMm", () => {
  it("leaves a small part at the composed vantage", () => {
    // 10x20x30 — `box-10x20x30.step`, the fixture half this suite is built on.
    // The whole point of a FLOOR: nothing about the small-part composition may
    // move, or this fix trades one defect for a hundred shifted pick coords.
    expect(
      planePickDistanceMm(
        centred(10, 20, 30),
        basis(),
        { canvas: CANVAS, free: FREE },
        FOV,
      ),
    ).toBe(PICK_CAMERA_DISTANCE_MM);
  });

  it("leaves a mid-size plate at the composed vantage too", () => {
    // 150x80x8 — the motor-mount plate the pick audits use. It fits inside the
    // free rect at 230 mm, so it must not be pushed back either.
    expect(
      planePickDistanceMm(
        centred(150, 80, 8),
        basis(),
        { canvas: CANVAS, free: FREE },
        FOV,
      ),
    ).toBe(PICK_CAMERA_DISTANCE_MM);
  });

  it("stands back for a real imported part, by roughly the ratio of its size", () => {
    // gearbox-11752: 1280.16 x 144.27 x 133.35 mm, centred on the origin.
    const distance = planePickDistanceMm(
      centred(1280.16, 144.27, 133.35),
      basis(),
      { canvas: CANVAS, free: FREE },
      FOV,
    );
    // Not a memorised number: the claim is "far enough that the part is in
    // front of the camera and inside the frame", which for a subject whose
    // half-extent is 640 mm cannot be satisfied anywhere near 230.
    expect(distance).toBeGreaterThan(1000);
    // And not absurdly far — a sphere fit about this rail would stand off
    // ~1.5x further for no reason, which is why this reuses `fitDistance`.
    expect(distance).toBeLessThan(4000);
  });

  it("puts the whole subject IN FRONT of the camera", () => {
    // The failure that was actually measured is `display:none` on 226 marks —
    // drei hides a mark whose anchor is behind the camera. So assert the
    // property that forbids it: every corner's depth toward the camera is less
    // than the distance the camera stands at.
    const box = centred(1280.16, 144.27, 133.35);
    const b = basis();
    const distance = planePickDistanceMm(
      box,
      b,
      { canvas: CANVAS, free: FREE },
      FOV,
    );
    const corners = boxCornersInCameraAxes(box, b.target, b.right, b.up, b.dir);
    expect(corners).toHaveLength(8);
    for (const { c } of corners) expect(c).toBeLessThan(distance);
  });

  it("keeps every corner inside the free rect at the solved distance", () => {
    // The other half of the measured failure: 222 marks projected off the LEFT
    // edge. Re-derive each corner's screen offset at the solved distance and
    // require it to sit within the free rect's share of the frame.
    const box = centred(1280.16, 144.27, 133.35);
    const b = basis();
    const distance = planePickDistanceMm(
      box,
      b,
      { canvas: CANVAS, free: FREE },
      FOV,
    );
    const tan = Math.tan((FOV * Math.PI) / 360);
    for (const { a, c } of boxCornersInCameraAxes(
      box,
      b.target,
      b.right,
      b.up,
      b.dir,
    )) {
      const halfWidthAtCorner =
        (distance - c) * tan * (CANVAS.width / CANVAS.height);
      expect(Math.abs(a)).toBeLessThanOrEqual(
        halfWidthAtCorner * (FREE.width / CANVAS.width) + 1e-6,
      );
    }
  });

  it("falls back to the floor when there is no subject or no frame", () => {
    // Both directions of "we could not measure". Failing toward the floor is
    // the only safe direction: it can never be worse than the behaviour that
    // shipped before this function existed.
    const b = basis();
    expect(
      planePickDistanceMm(null, b, { canvas: CANVAS, free: FREE }, FOV),
    ).toBe(PICK_CAMERA_DISTANCE_MM);
    expect(
      planePickDistanceMm(new Box3(), b, { canvas: CANVAS, free: FREE }, FOV),
    ).toBe(PICK_CAMERA_DISTANCE_MM);
    expect(planePickDistanceMm(centred(1280, 144, 133), b, null, FOV)).toBe(
      PICK_CAMERA_DISTANCE_MM,
    );
    // A degenerate free rect — `fitDistance` returns 0 and the caller must not
    // propagate it as "stand at the origin".
    expect(
      planePickDistanceMm(
        centred(1280, 144, 133),
        b,
        { canvas: CANVAS, free: { x: 0, y: 0, width: 0, height: 0 } },
        FOV,
      ),
    ).toBe(PICK_CAMERA_DISTANCE_MM);
  });

  it("accounts for a subject that is not centred on the orbit target", () => {
    // The vantage targets the world origin by design, so a part modelled a
    // metre away has to be framed from there — a box-centre solve would leave
    // it off screen exactly as the fixed distance did.
    const near = centred(200, 200, 200);
    const far = new Box3(
      new Vector3(900, -100, -100),
      new Vector3(1100, 100, 100),
    );
    const b = basis();
    const frame = { canvas: CANVAS, free: FREE };
    expect(planePickDistanceMm(far, b, frame, FOV)).toBeGreaterThan(
      planePickDistanceMm(near, b, frame, FOV),
    );
  });
});

describe("boxCornersInCameraAxes", () => {
  it("is empty for an absent or empty box", () => {
    const b = basis();
    expect(
      boxCornersInCameraAxes(null, b.target, b.right, b.up, b.dir),
    ).toEqual([]);
    expect(
      boxCornersInCameraAxes(new Box3(), b.target, b.right, b.up, b.dir),
    ).toEqual([]);
  });

  it("measures from the given centre, not from the box's own", () => {
    // Moving the orbit target moves every corner by exactly the same offset
    // along the camera axes — the property the fit depends on.
    const box = centred(100, 100, 100);
    const b = basis();
    const atOrigin = boxCornersInCameraAxes(
      box,
      b.target,
      b.right,
      b.up,
      b.dir,
    );
    const shifted = boxCornersInCameraAxes(
      box,
      new Vector3(0, 0, 50),
      b.right,
      b.up,
      b.dir,
    );
    for (let i = 0; i < 8; i += 1) {
      const before = atOrigin[i] as { a: number; b: number; c: number };
      const after = shifted[i] as { a: number; b: number; c: number };
      expect(after.a).toBeCloseTo(before.a - 50 * b.right.z, 9);
      expect(after.b).toBeCloseTo(before.b - 50 * b.up.z, 9);
      expect(after.c).toBeCloseTo(before.c - 50 * b.dir.z, 9);
    }
  });
});

/**
 * CRAFT-12 — "IS THE PROPOSAL ON SCREEN?", which is the question a preview
 * poses and the camera never used to ask.
 *
 * Built around the POSE the re-fit itself produces, because the defect this
 * block was rewritten for (2026-09-23) was a check that disagreed with its own
 * remedy: `framePose` parks the orbit target OFF the subject so the subject
 * lands mid-free-rect, and the old ratio mirrored the subject about that target
 * as if it sat mid-free-rect already. A 300 mm -> 12 mm shrink then read 1.139
 * both ways and the camera pulled IN 15.7x, on 6 of 11 identical runs.
 *
 * Every case is a PAIR where it can be — a subject that is on screen and one
 * that is not, under one camera — because a predicate tested only against the
 * overrunning case would pass a function that always says "re-fit".
 */
describe("frameOverrun", () => {
  /**
   * The shell measured in the running app with an extrude editor open at
   * 1280x800: the feature tree on the left, the editor on the right and the
   * command bar above, so the free rect is off centre in BOTH axes. The
   * re-fit's own pose is built for this frame below, which is what makes the
   * check-agrees-with-pose cases able to fail.
   */
  const REFIT_FREE: Rect = { x: 356, y: 24, width: 568, height: 558 };
  const framing = { canvas: CANVAS, free: REFIT_FREE };

  /** A box's corners on the shipped attitude, measured from `about`. */
  const cornersOf = (box: Box3, about: Vector3) =>
    boxCornersInCameraAxes(box, about, basis().right, basis().up, basis().dir);

  /**
   * THE POSE `Viewport.framePose` WOULD PRODUCE for `box`: solve the standoff
   * (or zoom) about the subject's centre, then slide the target by
   * `targetShift` so the subject lands in the middle of the free rect. Returns
   * the target it chose and the projection it would leave the camera in — so a
   * case can ask the check about the frame the fix actually builds.
   */
  function posed(
    box: Box3,
    kind: "perspective" | "orthographic",
  ): { target: Vector3; projection: ProjectionState } {
    const b = basis();
    const centre = box.getCenter(new Vector3());
    const corners = cornersOf(box, centre);
    let shift: { right: number; up: number };
    let projection: ProjectionState;
    if (kind === "orthographic") {
      const zoom = fitZoom(corners, REFIT_FREE);
      shift = targetShift(CANVAS, REFIT_FREE, {
        width: CANVAS.width / zoom,
        height: CANVAS.height / zoom,
      });
      projection = { kind, zoom };
    } else {
      const distanceMm = fitDistance(corners, CANVAS, REFIT_FREE, FOV);
      const visibleHeight = 2 * distanceMm * Math.tan((FOV * Math.PI) / 360);
      shift = targetShift(CANVAS, REFIT_FREE, {
        width: visibleHeight * (CANVAS.width / CANVAS.height),
        height: visibleHeight,
      });
      projection = { kind, fovDeg: FOV, distanceMm };
    }
    const target = centre
      .clone()
      .add(b.right.clone().multiplyScalar(shift.right))
      .add(b.up.clone().multiplyScalar(shift.up));
    return { target, projection };
  }

  /** A box standing on the XZ plane, `h` mm tall — an extrude ghost. */
  const column = (h: number) =>
    new Box3(new Vector3(0, 0, -10), new Vector3(10, h, 0));

  for (const kind of ["perspective", "orthographic"] as const) {
    it(`reads just under 1 for the frame the re-fit itself builds (${kind})`, () => {
      // The check and the pose must AGREE: a subject the re-fit has just framed
      // must not read as needing another re-fit. The free rect here is off
      // centre (a 330 px panel on the left), so a check that ignored where the
      // camera actually aims — the old ratio — fails this by the panel width.
      const box = column(300);
      const { target, projection } = posed(box, kind);
      const overrun = frameOverrun(cornersOf(box, target), framing, projection);
      expect(overrun).toBeGreaterThan(0.9); // not vacuous: it IS framed tight
      expect(overrun).toBeLessThanOrEqual(1);
      expect(overrunNeedsRefit(overrun)).toBe(false);
    });

    it(`never reads a SHRINKING proposal as larger — "only outward" (${kind})`, () => {
      // The measured flow: frame a 300 mm ghost, then type 12. The target is
      // still where the 300 mm pose left it, 150 mm up the column.
      //
      // An invariant guard rather than the reproduction, and said so: against
      // the OLD ratio this case on its own passes. In the app the pull-in
      // needed a SECOND re-fit first -- the old check read the 300 mm ghost's
      // own freshly posed frame as 1.139 and fired again -- and that is the
      // disagreement the case above pins, and reddens on.
      const { target, projection } = posed(column(300), kind);
      const wide = frameOverrun(
        cornersOf(column(300), target),
        framing,
        projection,
      );
      const narrow = frameOverrun(
        cornersOf(column(12), target),
        framing,
        projection,
      );
      // `<=`, not `<`: the base corner is shared by both ghosts and can be the
      // binding one, so "never larger" is the property, not "always smaller".
      expect(narrow).toBeLessThanOrEqual(wide);
      expect(overrunNeedsRefit(narrow)).toBe(false);
    });

    it(`fires when the proposal outgrows the frame it was posed for (${kind})`, () => {
      const { target, projection } = posed(column(12), kind);
      const small = frameOverrun(
        cornersOf(column(12), target),
        framing,
        projection,
      );
      const grown = frameOverrun(
        cornersOf(column(300), target),
        framing,
        projection,
      );
      expect(overrunNeedsRefit(small)).toBe(false);
      expect(overrunNeedsRefit(grown)).toBe(true);
    });
  }

  it("fires for a subject parked under a panel, even one that would fit a centred frame", () => {
    // The other half of what the old ratio could not see. The camera aims at
    // the CANVAS centre; the left 330 px are under the feature tree. A small
    // cube sitting mostly behind that panel is not on screen, however little
    // room it would need if it were centred.
    const zoom = 20;
    const target = new Vector3(0, 0, 0);
    const b = basis();
    // Push the cube left by ~20 mm of world: 20 * zoom = 400 px from centre,
    // i.e. at x ~ 240 on a 1280 canvas — under the 330 px panel.
    const centre = b.right.clone().multiplyScalar(-20);
    const cube = new Box3(
      centre.clone().subScalar(2),
      centre.clone().addScalar(2),
    );
    // One panel on the left and nothing else, so the free rect is off the
    // canvas centre HORIZONTALLY -- the axis this case is about.
    const leftPanel = { canvas: CANVAS, free: FREE };
    const hidden = frameOverrun(cornersOf(cube, target), leftPanel, {
      kind: "orthographic",
      zoom,
    });
    const visible = frameOverrun(
      cornersOf(
        new Box3(new Vector3(-2, -2, -2), new Vector3(2, 2, 2)),
        target,
      ),
      leftPanel,
      { kind: "orthographic", zoom },
    );
    expect(overrunNeedsRefit(hidden)).toBe(true);
    expect(overrunNeedsRefit(visible)).toBe(false);
  });

  it("reads a corner BEHIND a perspective camera as off screen", () => {
    const behind = frameOverrun(
      cornersOf(
        new Box3(new Vector3(-60, -60, -60), new Vector3(60, 60, 60)),
        new Vector3(),
      ),
      framing,
      { kind: "perspective", fovDeg: FOV, distanceMm: 40 },
    );
    expect(behind).toBe(Number.POSITIVE_INFINITY);
    expect(overrunNeedsRefit(behind)).toBe(true);
  });

  it("returns 0 — not a verdict — when the question cannot be asked", () => {
    // Each of these is a REFUSAL, and the predicate must read every one of them
    // as "leave the camera alone". A `> 1.02` on a 0 gets this right; a
    // `< 1` fits-test on the same 0 would get it exactly backwards, which is
    // why the direction of the comparison is pinned here.
    const cube40 = cornersOf(
      new Box3(new Vector3(-20, -20, -20), new Vector3(20, 20, 20)),
      new Vector3(),
    );
    const degenerate: Rect = { x: 0, y: 0, width: 0, height: 0 };
    expect(frameOverrun([], framing, { kind: "orthographic", zoom: 20 })).toBe(
      0,
    );
    expect(frameOverrun(cube40, null, { kind: "orthographic", zoom: 20 })).toBe(
      0,
    );
    expect(
      frameOverrun(
        cube40,
        { canvas: CANVAS, free: degenerate },
        { kind: "perspective", fovDeg: FOV, distanceMm: 40 },
      ),
    ).toBe(0);
    expect(
      frameOverrun(cube40, framing, {
        kind: "perspective",
        fovDeg: FOV,
        distanceMm: 0,
      }),
    ).toBe(0);
    expect(
      frameOverrun(cube40, framing, { kind: "orthographic", zoom: 0 }),
    ).toBe(0);
    expect(overrunNeedsRefit(0)).toBe(false);
  });
});

/**
 * THE SHEET HAS TO STAY CLICKABLE WHEN THE CAMERA STANDS BACK.
 *
 * The pair that matters is "unchanged at the floor" / "grows with the
 * standoff": a function tested only on the big case would pass one that scaled
 * every part, which would move the small-part composition the standoff fix was
 * careful to leave alone.
 */
describe("apparentSizeMm", () => {
  it("is EXACTLY a no-op at the floor", () => {
    // Not `toBeCloseTo`. Every fixture in this repo gets the floor, so any
    // drift here is a change to a hundred pick coordinates.
    expect(apparentSizeMm(90, PICK_CAMERA_DISTANCE_MM)).toBe(90);
  });

  it("never shrinks a sheet below its composed size", () => {
    // A standoff BELOW the floor cannot happen (`planePickDistanceMm` maxes
    // against it), but a caller that passed one must not get a sheet smaller
    // than the composition — failing toward the known-good size is the only
    // safe direction, exactly as the standoff itself does. NaN is in here
    // because `!(NaN > x)` is the only comparison that gets it right, and a
    // later "tidy" to `standoffMm <= FLOOR` would silently invert it.
    expect(apparentSizeMm(90, 10)).toBe(90);
    expect(apparentSizeMm(90, 0)).toBe(90);
    expect(apparentSizeMm(90, Number.NaN)).toBe(90);
  });

  it("holds the sheet's APPARENT size as the camera stands back", () => {
    // The property, stated as the thing a user sees: sheet over distance sets
    // the angle it subtends, so that ratio must not move.
    const atFloor = 90 / PICK_CAMERA_DISTANCE_MM;
    for (const standoff of [1291, 2366, 10_000]) {
      expect(apparentSizeMm(90, standoff) / standoff).toBeCloseTo(atFloor, 12);
    }
  });

  it("grows by the same factor the standoff did, on the measured parts", () => {
    // gearbox-11752 and the 1600 mm column, the two the review measured.
    expect(apparentSizeMm(90, 1291)).toBeCloseTo((90 * 1291) / 230, 9);
    expect(apparentSizeMm(90, 2366)).toBeCloseTo((90 * 2366) / 230, 9);
    // And the direction, said out loud: bigger standoff, bigger sheet.
    expect(apparentSizeMm(90, 2366)).toBeGreaterThan(apparentSizeMm(90, 1291));
  });
});
