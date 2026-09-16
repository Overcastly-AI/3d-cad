import { Box3, Vector3 } from "three";
import { describe, expect, it } from "vitest";

import { fitZoom, type Rect } from "./fitFraming";
import {
  apparentSizeMm,
  boxCornersInCameraAxes,
  frameOverrun,
  overrunNeedsRefit,
  PICK_CAMERA_DISTANCE_MM,
  planePickDistanceMm,
  type PlanePickStandoff,
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
 * The cases are built as a PAIR around one camera pose deliberately: the same
 * frame, the same attitude, a body that fits and a preview that does not. A
 * predicate tested only against the overrunning case would pass a function that
 * always says "re-fit", which is the jarring failure the policy note in
 * `Viewport.tsx` rules out by name.
 */
describe("frameOverrun", () => {
  const framing = { canvas: CANVAS, free: FREE };

  /** Corners of a cube of side `mm` centred on the camera's target. */
  const cube = (mm: number) =>
    boxCornersInCameraAxes(
      new Box3(
        new Vector3(-mm / 2, -mm / 2, -mm / 2),
        new Vector3(mm / 2, mm / 2, mm / 2),
      ),
      new Vector3(0, 0, 0),
      basis().right,
      basis().up,
      basis().dir,
    );

  it("reads ~1 for a subject the camera is exactly framing", () => {
    const corners = cube(40);
    const exact = planePickDistanceMm(
      new Box3(new Vector3(-20, -20, -20), new Vector3(20, 20, 20)),
      basis(),
      framing,
      FOV,
    );
    const overrun = frameOverrun(corners, framing, {
      kind: "perspective",
      fovDeg: FOV,
      distanceMm: Math.max(exact, 1),
    });
    // 230 mm is the FLOOR, so a 40 mm cube is framed from further than its own
    // exact fit — the overrun is at or below 1 either way, never above.
    expect(overrun).toBeLessThanOrEqual(1);
    expect(overrunNeedsRefit(overrun)).toBe(false);
  });

  it("rises above the threshold when the preview runs past the frame", () => {
    // The measured case: an 11 mm part framed close, and a pattern whose copies
    // span 120 mm. Same camera, ten times the subject.
    const close = frameOverrun(cube(11), framing, {
      kind: "perspective",
      fovDeg: FOV,
      distanceMm: 40,
    });
    const withGhosts = frameOverrun(cube(120), framing, {
      kind: "perspective",
      fovDeg: FOV,
      distanceMm: 40,
    });
    expect(overrunNeedsRefit(close)).toBe(false);
    expect(overrunNeedsRefit(withGhosts)).toBe(true);
    expect(withGhosts).toBeGreaterThan(close * 5);
  });

  it("measures a PARALLEL frame by zoom, not by distance", () => {
    // The projection that carries no size in its position. The zoom is DERIVED
    // from the exact fit of the 40 mm body rather than written as a literal —
    // the corners are resolved onto the camera's TILTED axes, so a hand-picked
    // number is really a guess about a rotation, and a wrong guess fails for a
    // reason that has nothing to do with the predicate under test.
    const zoom = fitZoom(cube(40), FREE);
    expect(zoom).toBeGreaterThan(0);
    const fits = frameOverrun(cube(40), framing, {
      kind: "orthographic",
      zoom,
    });
    const spills = frameOverrun(cube(120), framing, {
      kind: "orthographic",
      zoom,
    });
    expect(fits).toBeCloseTo(1, 6);
    expect(overrunNeedsRefit(fits)).toBe(false);
    expect(spills).toBeCloseTo(3, 6); // three times the subject, same frame
    expect(overrunNeedsRefit(spills)).toBe(true);
  });

  it("returns 0 — not a verdict — when the question cannot be asked", () => {
    // Each of these is a REFUSAL, and the predicate must read every one of them
    // as "leave the camera alone". A `> 1.02` on a 0 gets this right; a
    // `< 1` fits-test on the same 0 would get it exactly backwards, which is
    // why the direction of the comparison is pinned here.
    const degenerate: Rect = { x: 0, y: 0, width: 0, height: 0 };
    expect(frameOverrun([], framing, { kind: "orthographic", zoom: 20 })).toBe(
      0,
    );
    expect(
      frameOverrun(cube(40), null, { kind: "orthographic", zoom: 20 }),
    ).toBe(0);
    expect(
      frameOverrun(
        cube(40),
        { canvas: CANVAS, free: degenerate },
        { kind: "perspective", fovDeg: FOV, distanceMm: 40 },
      ),
    ).toBe(0);
    expect(
      frameOverrun(cube(40), framing, {
        kind: "perspective",
        fovDeg: FOV,
        distanceMm: 0,
      }),
    ).toBe(0);
    expect(
      frameOverrun(cube(40), framing, { kind: "orthographic", zoom: 0 }),
    ).toBe(0);
    for (const refused of [0]) expect(overrunNeedsRefit(refused)).toBe(false);
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
