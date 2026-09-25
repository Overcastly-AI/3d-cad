/**
 * THE REVOLVE SWEEP GAUGE — the angle you turn, as an instrument (CRAFT-10).
 *
 * Three drawn things, in the order the eye needs them, each answering exactly
 * one question:
 *
 *   1. **the axis** (`RevolveAxisLine`) — *about what?* A brass chain line
 *      through the profile. It did not exist before this item; the axis was a
 *      dropdown and the scene said nothing.
 *   2. **the arc** (`ParametricGauge` on an angular track) — *how far?* A
 *      graduated protractor seated on that axis, starting at the profile's own
 *      outermost point and sweeping to the current angle, with the grip on its
 *      end and the number in the tag beside it.
 *   3. **the sweep** (line-work) — *what will that give me?* The rails the
 *      profile's corners travel and the end section where the turn stops,
 *      redrawn on every value the gauge asks for.
 *
 * The third is not decoration and it is what decides whether this item ships at
 * all: a gauge whose drag changes a number and not the model promises direct
 * manipulation and delivers a slider. This is route **(b)** of the direction
 * pass's two — a geometric preview short of a full ghost — and
 * `revolveSweepLines` explains why a revolve specifically wants line-work
 * rather than a translucent solid.
 *
 * ## The anchor is a PROP
 *
 * Everything this component needs to place itself arrives as a prop: the solved
 * profile layer, the axis reference the form holds, and the angle. It reads no
 * pick store. W4's persistent selection store will change where the caller gets
 * the axis FROM, and that is a re-wiring of one line in `PartPage` rather than
 * a rewrite of this file.
 *
 * ## The rail field is untouched
 *
 * The editor's Angle input stays exactly where it is and so does the axis
 * dropdown, now that the axis is also drawn. The gauge WRITES that field
 * (contract β: the editor echoes the override back as this component's `value`,
 * or the arrow springs back to its old length the instant you let go). Making
 * the number pullable is the job; removing where it is typed is not.
 */
import { useMemo } from "react";

import { viewport } from "@loft/design/tokens";

import type { SketchEntity } from "../api/parts";
import type { RevolveAxisRef } from "../features/revolve";
import type { PlaneBasis } from "../sketch/plane";
import type { Vec3 } from "@loft/design";
import {
  axisReach,
  arcReference,
  pointOnPlane,
  profileAboutAxis,
  revolveAxisAnchor,
} from "./axisAnchor";
import {
  MAX_REVOLVE_DEG,
  MIN_REVOLVE_DEG,
  revolveGaugeTrack,
  revolveSweepLines,
  type ArcSeat,
} from "./axisAnchorGauge";
import { Segments } from "./overlaySegments";
import { ParametricGauge } from "./ParametricGauge";
import { profileRegions } from "./profileLoops";
import { RevolveAxisLine } from "./RevolveAxisLine";

export interface RevolveGaugeProps {
  /** The profile sketch's plane, in SCENE coordinates. */
  basis: PlaneBasis;
  /** The profile sketch's solved entities — the loops the turn sweeps. */
  entities: readonly SketchEntity[];
  /**
   * The axis the form currently holds, exactly as it will be persisted. A
   * PROP — see the note above on W4.
   */
  axis: RevolveAxisRef;
  /** The editor's current sweep, degrees. */
  angleDeg: number;
  /** Report a new sweep (the editor owns the value; this asks for one). */
  onAngleChange: (deg: number) => void;
}

/**
 * How far outside the profile the arc is drawn, as a fraction of the profile's
 * own reach from the axis.
 *
 * The arc must clear the material: seated ON the silhouette it would be a
 * protractor buried in the part, and every graduation would fight the sketch
 * ink beneath it. A fifth out is enough to read as "around" rather than "on",
 * and small enough that the instrument still belongs to the part rather than
 * floating beside it. Proportional, so it survives zoom the way the rest of the
 * gauge's geometry does.
 */
const ARC_CLEARANCE_FRAC = 0.2;

/**
 * Shortest arc radius the gauge will seat at, scene mm.
 *
 * A profile sitting ON its own axis has zero reach, and an arc of radius zero
 * is a point: no spine to grab, no ladder to draw, and a `screenValueAt` that
 * divides by it. The kernel refuses that revolve anyway, but the gauge must not
 * produce a NaN on the way to finding out.
 */
const MIN_ARC_RADIUS_MM = 0.5;

export function RevolveGauge({
  basis,
  entities,
  axis,
  angleDeg,
  onAngleChange,
}: RevolveGaugeProps) {
  const anchor = useMemo(
    () => revolveAxisAnchor(axis, basis, entities),
    [axis, basis, entities],
  );
  const regions = useMemo(() => profileRegions(entities), [entities]);

  /**
   * The profile's loops as scene-space polylines — the ONE lift from sketch
   * (u, v) to world, shared by the sweep preview and the seat. Holes ride along
   * with the outer loop: a turned part with a bore has two rails' worth of
   * information and drawing only the silhouette would state the wrong section.
   */
  const loops = useMemo<Vec3[][]>(
    () =>
      regions.flatMap((region) =>
        [region.outer, ...region.holes].map((loop) =>
          loop.map((p) => pointOnPlane(basis, p.x, p.y)),
        ),
      ),
    [regions, basis],
  );

  const seat = useMemo<ArcSeat | null>(() => {
    if (anchor === null) return null;
    const about = profileAboutAxis(
      anchor,
      basis,
      regions.map((r) => r.outer),
    );
    if (about === null) return null;
    const arcRadiusMm = Math.max(
      MIN_ARC_RADIUS_MM,
      about.radiusMm * (1 + ARC_CLEARANCE_FRAC),
    );
    return {
      centre: about.centre,
      axis: anchor.dir,
      reference: arcReference(
        anchor,
        basis,
        regions.map((r) => r.outer),
      ),
      arcRadiusMm,
      // The instrument's own scale: the profile's half-diagonal about the axis,
      // the same quantity the extrude gauge takes for the same job. It sizes
      // the arrowhead and the rung arms, so the gauge suits the PART — the
      // number it happens to be showing must never set its proportions, which
      // is the two-scale defect the direction pass closed in CRAFT-7.
      seatRadiusMm: Math.max(
        MIN_ARC_RADIUS_MM,
        Math.hypot(about.extentMm, about.radiusMm * 2) / 2,
      ),
    };
  }, [anchor, basis, regions]);

  const track = useMemo(
    () => (seat === null ? null : revolveGaugeTrack(seat)),
    [seat],
  );

  const sweep = useMemo(
    () =>
      seat === null
        ? new Float32Array(0)
        : revolveSweepLines(seat, loops, angleDeg),
    [seat, loops, angleDeg],
  );

  const reachMm = useMemo(() => {
    if (anchor === null || seat === null) return 0;
    const about = profileAboutAxis(
      anchor,
      basis,
      regions.map((r) => r.outer),
    );
    return about === null ? 0 : axisReach(about.extentMm, seat.arcRadiusMm);
  }, [anchor, seat, basis, regions]);

  // NULL IS A REAL ANSWER. A `sketch_line` axis names an entity by id, and the
  // editor can be pointed at a different profile between the axis being chosen
  // and this being asked; a profile with no closed loop has nothing to turn.
  // Drawing an arc around a line that is not there would be worse than the
  // dropdown-only state this item replaces.
  if (anchor === null || seat === null || track === null) return null;

  return (
    <>
      <RevolveAxisLine anchor={anchor} centre={seat.centre} reachMm={reachMm} />
      {/* NAMED so a probe can read the drawn buffer directly. "The preview
          redraws" is otherwise only checkable as a pixel difference, which
          cannot tell a redraw from a camera nudge — and it is the one claim
          that decides whether this gauge is direct manipulation or a slider. */}
      <group name="revolve-sweep-preview">
        <Segments
          positions={sweep}
          color={viewport.preview.edge}
          opacity={viewport.preview.edgeOpacity}
          depthTest={false}
          renderOrder={10}
        />
      </group>
      <ParametricGauge
        label="Revolve angle"
        tagLabel="A"
        gaugeId="revolve-angle"
        value={angleDeg}
        onChange={onAngleChange}
        track={track}
        min={MIN_REVOLVE_DEG}
        max={MAX_REVOLVE_DEG}
        // No `tagUnit`: an angle wears its degree sign in the number itself
        // (`formatAngle`), so a trailing unit cell would say it twice.
      />
    </>
  );
}
