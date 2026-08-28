import { Vector3 } from "three";
import { beforeEach, describe, expect, it } from "vitest";

import {
  safeUp,
  upFor,
  useViewCommandStore,
  VIEW_DIRECTIONS,
} from "./viewCommands";

/**
 * The camera-basis helpers behind every framing (FB-20).
 *
 * `framePose` builds its basis as `right = up × dir`, so an up parallel to the
 * view direction does not merely look odd — the cross product collapses and the
 * roll of the resulting framing is decided by rounding. These two functions are
 * the only thing standing between that and the user, which is why they are
 * tested here rather than inferred from a browser run.
 */

function dir(x: number, y: number, z: number): Vector3 {
  return new Vector3(x, y, z).normalize();
}

describe("upFor", () => {
  it("gives world up for an oblique direction", () => {
    const up = upFor(dir(...VIEW_DIRECTIONS.iso));
    expect([up.x, up.y, up.z]).toEqual([0, 1, 0]);
  });

  it("gives world up for the axis views that can use it", () => {
    for (const named of ["front", "right"] as const) {
      const [x, y, z] = VIEW_DIRECTIONS[named];
      const up = upFor(dir(x, y, z));
      expect([up.x, up.y, up.z], named).toEqual([0, 1, 0]);
    }
  });

  it("looks down with kernel +y up-screen (top)", () => {
    // Camera above, looking down: up = −Z is the plan-view convention, so the
    // kernel's +y (scene −z) reads up the screen.
    const up = upFor(dir(...VIEW_DIRECTIONS.top));
    expect([up.x, up.y, up.z]).toEqual([0, 0, -1]);
  });

  it("mirrors the convention from below (bottom)", () => {
    const up = upFor(dir(0, -1, 0));
    expect([up.x, up.y, up.z]).toEqual([0, 0, 1]);
  });

  it("switches convention only inside the parallel band", () => {
    // The threshold is |dir.y| > 0.99, i.e. within 8.1° of vertical. 11.5° off
    // is a normal steep view and keeps world up …
    const usable = upFor(dir(Math.sin(0.2), Math.cos(0.2), 0));
    expect([usable.x, usable.y, usable.z]).toEqual([0, 1, 0]);
    // … 5° off is effectively plan view and does not.
    const degenerate = upFor(dir(Math.sin(0.087), Math.cos(0.087), 0));
    expect([degenerate.x, degenerate.y, degenerate.z]).toEqual([0, 0, -1]);
  });
});

describe("safeUp", () => {
  it("returns the live up unchanged when it is oblique to the view", () => {
    const live = new Vector3(0, 1, 0);
    expect(safeUp(dir(...VIEW_DIRECTIONS.iso), live)).toBe(live);
  });

  it("substitutes when the up is parallel to the view direction", () => {
    // The measured FB-20 pose: leaving a sketch on XY parks the camera looking
    // straight down while SketchScene restores world up, so |up · dir| ≈ 0.9996.
    const view = dir(-0.027, 0.9996, 0.0246);
    const substituted = safeUp(view, new Vector3(0, 1, 0));
    expect([substituted.x, substituted.y, substituted.z]).toEqual([0, 0, -1]);
  });

  it("substitutes for an anti-parallel up too", () => {
    const substituted = safeUp(dir(0, 1, 0), new Vector3(0, -1, 0));
    expect([substituted.x, substituted.y, substituted.z]).toEqual([0, 0, -1]);
  });

  it("leaves a basis that is never degenerate", () => {
    // The property the caller actually depends on: right = up × dir is a real
    // direction, whatever the camera was doing.
    for (const view of [
      dir(0, 1, 0),
      dir(0, -1, 0),
      dir(-0.027, 0.9996, 0.0246),
      dir(...VIEW_DIRECTIONS.iso),
      dir(...VIEW_DIRECTIONS.front),
    ]) {
      const right = new Vector3().crossVectors(
        safeUp(view, new Vector3(0, 1, 0)),
        view,
      );
      expect(right.length(), `${view.x},${view.y},${view.z}`).toBeGreaterThan(
        0.1,
      );
    }
  });

  it("keeps a tilted-but-usable up rather than flattening it", () => {
    // A user who has orbited has a rolled up vector; the guard must not steal
    // it just because the view is somewhat steep.
    const rolled = new Vector3(0.3, 0.9, 0).normalize();
    const view = dir(0.6, 0.5, 0.6);
    expect(safeUp(view, rolled)).toBe(rolled);
  });
});

/**
 * WHICH COMMANDS ARM ORTHOGRAPHIC (ORTHO-1).
 *
 * The policy lives on the store because every instrument routes through it —
 * the rail, the numeric snaps, the viewport context menu and the reference
 * cube. These cases are what stops it becoming four policies.
 */
describe("projection policy", () => {
  beforeEach(() => {
    useViewCommandStore.setState({ command: null, projection: "perspective" });
  });

  it("opens perspective — the resting bench view keeps its depth", () => {
    expect(useViewCommandStore.getState().projection).toBe("perspective");
  });

  it("arms orthographic for every named view", () => {
    // The ticket's whole complaint: FRONT is opened to CHECK something, and a
    // perspective FRONT cannot answer the question it was opened for.
    for (const kind of ["front", "top", "right", "iso", "home"] as const) {
      useViewCommandStore.setState({ projection: "perspective" });
      useViewCommandStore.getState().request(kind);
      expect(useViewCommandStore.getState().projection, kind).toBe(
        "orthographic",
      );
    }
  });

  it("arms orthographic for a reference-cube pick", () => {
    // A cube facet click is the same act as pressing FRONT, by another
    // instrument — landing in a perspective view of a face is the same defect
    // from the other direction.
    useViewCommandStore.getState().requestDirection([0, 0, 1]);
    expect(useViewCommandStore.getState().projection).toBe("orthographic");
  });

  it("leaves the projection alone on FIT — it frames, it does not orient", () => {
    // Fit is also fired by the chrome itself when a panel collapses
    // (`VIEWPORT_CHROME_EVENT`). A fit that switched projection would mean
    // closing the inspector silently changed how the model is drawn.
    useViewCommandStore.getState().request("fit");
    expect(useViewCommandStore.getState().projection).toBe("perspective");
    useViewCommandStore.setState({ projection: "orthographic" });
    useViewCommandStore.getState().request("fit");
    expect(useViewCommandStore.getState().projection).toBe("orthographic");
  });

  it("still issues the command it was asked for", () => {
    // The projection is a side effect; nonce-keyed command dispatch is the job.
    const before = useViewCommandStore.getState().command?.nonce ?? 0;
    useViewCommandStore.getState().request("front");
    const command = useViewCommandStore.getState().command;
    expect(command?.kind).toBe("front");
    expect(command?.nonce).toBe(before + 1);
  });

  it("toggles both ways and is its own inverse", () => {
    const { toggleProjection } = useViewCommandStore.getState();
    toggleProjection();
    expect(useViewCommandStore.getState().projection).toBe("orthographic");
    toggleProjection();
    expect(useViewCommandStore.getState().projection).toBe("perspective");
  });

  it("keeps the projection through a free orbit — nothing silently flips it", () => {
    // The decision stated in the commit: orbiting away from a named view does
    // NOT hand perspective back. Orbit writes no command at all, so the only
    // way the projection can move is a named view or the toggle — which is
    // exactly what makes the rail's word trustworthy.
    useViewCommandStore.getState().request("front");
    useViewCommandStore.setState({ command: null }); // an orbit issues nothing
    expect(useViewCommandStore.getState().projection).toBe("orthographic");
  });
});
