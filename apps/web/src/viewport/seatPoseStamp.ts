/**
 * WHEN HAS THE CAMERA MOVED ENOUGH TO RE-OWE THE EDGE-MARK SEATS?
 *
 * Measured on the screen, in CSS px, not in the camera's matrix. The seat
 * pass (`useEdgeMarkAnchors`) answers a SCREEN question (does the band answer
 * this edge under a 24 px mark, is that mark clear of its neighbours and of
 * the gauges), so the only camera change that can alter an answer is one that
 * moves something on screen.
 *
 * The stamp this replaces quantised `camera.matrixWorld` to 1e-3. In this
 * scene's units (mm) that is 0.001 mm of camera travel, about 0.01 px at the
 * framings these marks are used at, so after an orbit the seats kept being
 * re-owed through the whole of `OrbitControls`' damping tail, long after
 * anything visible had stopped moving. That tail is a fixed frame count, so on
 * a software rasteriser the `settled` latch drifted towards the 90 s spec
 * ceiling with machine load. Measured on the PICKMARK-OCCLUDE-1 orbit budget,
 * from `mouse.up` to `settled` on one loaded 4-core box: 189 re-owed poses,
 * 231 frames and 51.6 s with the matrix stamp; 87 poses, 131 frames and
 * 23.8 s with this one.
 *
 * ## The quantum is half a pixel, and why that is the honest bound
 *
 * Each probe point is projected with the CURRENT camera, view and projection
 * matrices both, so a dolly or a zoom changes the pixel scale and is seen
 * exactly like an orbit. Each projected coordinate is rounded to a 0.5 px
 * cell. While no cell changes, every probe point is still inside the cell it
 * occupied when the seats were last computed, so it is less than 0.5 px from
 * where the pass last saw it. A latched `settled` therefore never describes a
 * mark more than half a pixel from the seat it would be given now. That is
 * below what the browser can draw (marks land on whole CSS px) and 1/48 of a
 * mark's 24 px box. A coarser cell would let a mark latch visibly off its
 * edge. A finer one only buys more tail frames.
 *
 * ## What is probed
 *
 * Both ends and the mid-span of every offered edge. Together they pin the
 * camera against the part's own extent, so no seat on those edges can swing
 * by more than about one cell while they all hold still. The seats themselves
 * are NOT probed: the pass moves them, and a stamp that changed whenever the
 * pass did its job would re-owe every edge forever. The canvas size is part
 * of the stamp, so a resize re-owes too.
 */
import { Vector3 } from "three";
import type { Camera } from "three";

/** The cell, in CSS px, a probe point must leave to re-owe the seats. */
export const SEAT_STAMP_QUANTUM_PX = 0.5;

/**
 * A projection that is not finite (a point on the camera plane) records as
 * this sentinel. NaN never equals itself, so storing it would re-owe every
 * frame and the seats could never settle.
 */
const OFF_SCREEN = Number.MAX_SAFE_INTEGER;

type Point = readonly [number, number, number];

export class SeatPoseStamp {
  private cells = new Float64Array(0);
  private width = -1;
  private height = -1;
  private count = -1;
  private stale = true;
  private readonly probe = new Vector3();

  /** Force the next `update` to report a change (a new offer, a gauge moved). */
  invalidate(): void {
    this.stale = true;
  }

  /**
   * Record where `points` project with `camera` on a `width` x `height`
   * canvas. Returns true when that differs from the previous call: a point
   * changed its half-pixel cell, the point count or canvas size changed, or
   * `invalidate` was called. Allocates only when the point count grows.
   */
  update(
    points: Iterable<Point>,
    camera: Camera,
    width: number,
    height: number,
  ): boolean {
    let changed = this.stale || width !== this.width || height !== this.height;
    this.stale = false;
    this.width = width;
    this.height = height;
    let n = 0;
    for (const point of points) {
      this.probe.set(point[0], point[1], point[2]).project(camera);
      const x = this.cell(((this.probe.x + 1) / 2) * width);
      const y = this.cell(((1 - this.probe.y) / 2) * height);
      if (2 * n + 1 >= this.cells.length) {
        const grown = new Float64Array(Math.max(16, this.cells.length * 2));
        grown.set(this.cells);
        grown.fill(Number.NaN, this.cells.length);
        this.cells = grown;
      }
      if (this.cells[2 * n] !== x || this.cells[2 * n + 1] !== y) {
        changed = true;
        this.cells[2 * n] = x;
        this.cells[2 * n + 1] = y;
      }
      n += 1;
    }
    if (n !== this.count) changed = true;
    this.count = n;
    return changed;
  }

  private cell(px: number): number {
    return Number.isFinite(px)
      ? Math.round(px / SEAT_STAMP_QUANTUM_PX)
      : OFF_SCREEN;
  }
}
