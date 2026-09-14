import { describe, expect, it } from "vitest";

import {
  backdropFor,
  backdropPose,
  BACKDROP_ENGAGE,
  BACKDROP_RELEASE,
  type Backdrop,
} from "./benchBackdrop";

/** A view direction `degrees` above horizontal, looking down −Z. */
function fromFront(degrees: number): [number, number, number] {
  const radians = (degrees * Math.PI) / 180;
  return [0, Math.sin(radians), Math.cos(radians)];
}

describe("backdropFor", () => {
  it("never engages under a perspective camera, at any attitude", () => {
    // The defect is specific to a PARALLEL projection: a perspective camera
    // shows the ground's half-plane below the eye however edge-on it is, so
    // there is nothing to rescue and a second grid would be noise.
    expect(backdropFor(fromFront(0), false, null)).toBeNull();
    expect(backdropFor([1, 0, 0], false, null)).toBeNull();
  });

  it("engages squared-on and stays off at an attitude the floor can carry", () => {
    expect(backdropFor(fromFront(0), true, null)).toEqual({
      axis: "z",
      side: -1,
    });
    // 30 degrees above horizontal is the iso-ish bench view the audit measured
    // at 11 795 px of grid — the floor is doing its job and gets no wall.
    expect(backdropFor(fromFront(30), true, null)).toBeNull();
  });

  it("hangs the sheet on the FAR side of the subject, never between it and the camera", () => {
    expect(backdropFor([0, 0, 1], true, null)?.side).toBe(-1);
    expect(backdropFor([0, 0, -1], true, null)?.side).toBe(1);
    expect(backdropFor([1, 0, 0], true, null)).toEqual({ axis: "x", side: -1 });
    expect(backdropFor([-1, 0, 0], true, null)).toEqual({ axis: "x", side: 1 });
  });

  it("looks down the DOMINANT horizontal axis when the camera is between two", () => {
    expect(backdropFor([1, 0, 0.9], true, null)?.axis).toBe("x");
    expect(backdropFor([0.9, 0, 1], true, null)?.axis).toBe("z");
  });

  it("holds the sheet up through the hysteresis band, and drops it past it", () => {
    // The band exists so a sheet does not strobe on and off while the modeler
    // orbits across the threshold. Asserted as a PAIR at one attitude: the
    // same camera answers differently depending on what is already drawn, and
    // that IS the hysteresis — a single-threshold implementation returns the
    // same answer for both and this is the only test that can tell.
    const between = Math.asin((BACKDROP_ENGAGE + BACKDROP_RELEASE) / 2);
    const attitude = fromFront((between * 180) / Math.PI);
    const up: Backdrop = { axis: "z", side: -1 };
    expect(backdropFor(attitude, true, null)).toBeNull(); // would not engage
    expect(backdropFor(attitude, true, up)).toEqual(up); // but stays up
    const past = fromFront(
      ((Math.asin(BACKDROP_RELEASE) + 0.02) * 180) / Math.PI,
    );
    expect(backdropFor(past, true, up)).toBeNull();
  });

  it("ignores a degenerate direction rather than picking an axis from noise", () => {
    expect(backdropFor([0, 0, 0], true, null)).toBeNull();
  });

  it("is blind to the direction's LENGTH — it is an attitude, not a distance", () => {
    expect(backdropFor([0, 0, 1], true, null)).toEqual(
      backdropFor([0, 0, 4000], true, null),
    );
  });
});

describe("backdropPose", () => {
  const plate = {
    min: [0, 0, -60] as const,
    max: [80, 12, 0] as const,
  };

  it("parks the sheet BEHIND the subject, clear of it, facing the camera", () => {
    const pose = backdropPose({ axis: "z", side: -1 }, plate);
    // Behind the far face (-60), by half the 100.8 mm diagonal.
    expect(pose.position[2]).toBeLessThan(-60);
    expect(pose.position[2]).toBeCloseTo(-60 - 100.8 / 2, 0);
    // The normal points back toward the camera, which is on the +z side.
    expect(pose.normal).toEqual([0, 0, 1]);
    // And it is a plane, not a point: the other two axes carry no offset.
    expect(pose.position[0]).toBe(0);
    expect(pose.position[1]).toBe(0);
  });

  it("scales its clearance with the subject, with a floor for a small one", () => {
    const dowel = { min: [0, 0, 0] as const, max: [6, 6, 6] as const };
    const far = backdropPose({ axis: "z", side: -1 }, dowel);
    // A 6 mm dowel's diagonal is 10.4 mm; half of that would put the sheet
    // 5 mm behind it, which is inside the part's own line work.
    expect(far.position[2]).toBeCloseTo(-25, 5);

    const weldment = {
      min: [0, 0, -2000] as const,
      max: [1000, 500, 0] as const,
    };
    const wall = backdropPose({ axis: "z", side: -1 }, weldment);
    // And a 2 m weldment gets a sheet behind it rather than through it.
    expect(wall.position[2]).toBeLessThan(-2000);
  });

  it("puts the sheet through the origin for an empty part", () => {
    const pose = backdropPose({ axis: "x", side: 1 }, null);
    expect(pose.position).toEqual([0, 0, 0]);
    expect(pose.normal).toEqual([-1, 0, 0]);
  });
});
