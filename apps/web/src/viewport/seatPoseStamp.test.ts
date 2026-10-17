import { OrthographicCamera, PerspectiveCamera, Vector3 } from "three";
import { describe, expect, it } from "vitest";

import { SEAT_STAMP_QUANTUM_PX, SeatPoseStamp } from "./seatPoseStamp";

const W = 1600;
const H = 1000;
/** A 40 mm part's corners, the scale the shaft coupling is framed at. */
const POINTS: [number, number, number][] = [
  [-20, -20, -20],
  [20, -20, -20],
  [20, 20, 20],
  [-20, 20, 20],
  [0, 0, 0],
];

function camera(x: number): PerspectiveCamera {
  const cam = new PerspectiveCamera(45, W / H, 1, 5000);
  cam.position.set(x, 0, 150);
  cam.lookAt(0, 0, 0);
  cam.updateMatrixWorld();
  return cam;
}

function screen(cam: PerspectiveCamera): [number, number][] {
  return POINTS.map((p) => {
    const v = new Vector3(...p).project(cam);
    return [((v.x + 1) / 2) * W, ((1 - v.y) / 2) * H];
  });
}

/** Screen px per mm of sideways camera travel at the part, for this framing. */
const PX_PER_MM = H / (2 * 150 * Math.tan((45 / 2) * (Math.PI / 180)));

describe("SeatPoseStamp", () => {
  it("reports the first pose, then holds still for the same pose", () => {
    const stamp = new SeatPoseStamp();
    expect(stamp.update(POINTS, camera(0), W, H)).toBe(true);
    expect(stamp.update(POINTS, camera(0), W, H)).toBe(false);
  });

  it("ignores a damping-tail move that shifts nothing by a cell", () => {
    const stamp = new SeatPoseStamp();
    stamp.update(POINTS, camera(0.0101), W, H);
    // 1e-3 mm: the old matrix stamp re-owed the seats for this, and it moves
    // the part about a hundredth of a pixel.
    expect(stamp.update(POINTS, camera(0.0111), W, H)).toBe(false);
  });

  it("re-owes once a probe point crosses a half-pixel cell", () => {
    const stamp = new SeatPoseStamp();
    stamp.update(POINTS, camera(0), W, H);
    const overOneCell = (1.05 * SEAT_STAMP_QUANTUM_PX) / PX_PER_MM;
    expect(stamp.update(POINTS, camera(overOneCell), W, H)).toBe(true);
  });

  it("never lets a stable stamp hide a point that moved a cell or more", () => {
    // Creep in sub-cell steps: the stamp may stay quiet between steps, but no
    // point may drift a whole cell from where it was at the last change.
    const stamp = new SeatPoseStamp();
    let at = screen(camera(0));
    stamp.update(POINTS, camera(0), W, H);
    const step = (0.1 * SEAT_STAMP_QUANTUM_PX) / PX_PER_MM;
    let changes = 0;
    for (let i = 1; i <= 200; i += 1) {
      const cam = camera(i * step);
      const now = screen(cam);
      if (stamp.update(POINTS, cam, W, H)) {
        changes += 1;
        at = now;
        continue;
      }
      for (let k = 0; k < now.length; k += 1) {
        const [x0, y0] = at[k] as [number, number];
        const [x1, y1] = now[k] as [number, number];
        expect(Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0))).toBeLessThan(
          SEAT_STAMP_QUANTUM_PX,
        );
      }
    }
    // ...and the creep did re-owe, so the loop above tested something.
    expect(changes).toBeGreaterThan(5);
  });

  it("sees a zoom, which moves nothing in the camera's world matrix", () => {
    const stamp = new SeatPoseStamp();
    const cam = new OrthographicCamera(-50, 50, 30, -30, 1, 1000);
    cam.position.set(0, 0, 200);
    cam.updateMatrixWorld();
    stamp.update(POINTS, cam, W, H);
    cam.zoom = 1.1;
    cam.updateProjectionMatrix();
    expect(stamp.update(POINTS, cam, W, H)).toBe(true);
  });

  it("re-owes on a resize and on invalidate", () => {
    const stamp = new SeatPoseStamp();
    stamp.update(POINTS, camera(0), W, H);
    expect(stamp.update(POINTS, camera(0), W - 1, H)).toBe(true);
    stamp.invalidate();
    expect(stamp.update(POINTS, camera(0), W - 1, H)).toBe(true);
    expect(stamp.update(POINTS, camera(0), W - 1, H)).toBe(false);
  });

  it("settles on a point in the camera plane instead of re-owing forever", () => {
    const stamp = new SeatPoseStamp();
    const plane: [number, number, number][] = [[0, 0, 150]];
    stamp.update(plane, camera(0), W, H);
    expect(stamp.update(plane, camera(0), W, H)).toBe(false);
  });
});
