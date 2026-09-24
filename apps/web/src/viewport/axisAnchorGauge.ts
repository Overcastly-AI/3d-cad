/**
 * THE ANGULAR GAUGES' ARITHMETIC — revolve sweep and draft taper (CRAFT-10).
 *
 * The same seam `extrudeHandle.ts` makes for the linear gauge: the part a
 * browser is not required to test lives here, and `RevolveGauge.tsx` /
 * `DraftGauge.tsx` are thin r3f shells over it. The file is named for
 * {@link axisAnchor}, whose `AxisAnchor` every track here is seated on — an
 * angular gauge is precisely "a value measured about an anchored axis", and
 * both verbs that have one share this arithmetic rather than a prefix.
 *
 * Both constructors return a `GaugeTrack` built on `@loft/design`'s
 * `angularTrack`, so the ask-queue, the grip, the tag, the keyboard and the
 * nested cancel are the shared ones and nothing here re-implements a line of
 * them.
 *
 * ## THE ANGULAR LADDER IS NOT THE LINEAR ONE ROTATED
 *
 * 10 / 20 / 50 degrees is the failure mode a decade series produces and no
 * machinist uses. The ladder is **15 major / 5 minor**, coarsening to 30, 45
 * and 90 as the arc shortens on screen and subdividing to **1** as it grows —
 * the angles parts are actually dimensioned in. `formatAngle` speaks them.
 *
 * ## TWO THINGS `angularTrack` COULD NOT DO, AND WHY THEY ARE WRAPPED HERE
 *
 * `angularTrack` shipped in CRAFT-8 with NO CONSUMER, and the direction pass
 * marked its signature PROVISIONAL for exactly this moment: "the first use
 * finding out what the interface should have been". Mounting it found two
 * gaps. Both are FIXED HERE BY COMPOSITION rather than by editing
 * `packages/design`, which is CRAFT-8's territory for the whole wave —
 * a track is a plain object, so overriding two of its methods is the same
 * move `extrudeTrack` makes when it hands `linearTrack` a formatter, and it
 * keeps the package's one owner.
 *
 *  1. **The ladder floors at 5 degrees and cannot subdivide further.**
 *     `angularTrack.stops` picks its major from `[15, 30, 45, 90]` and its
 *     minor as `5` (or a third of the major), full stop. A draft's everyday
 *     value is **3 degrees** — below the whole ladder — so the stop set came
 *     back with fewer than three rungs and the instrument lost its signature
 *     element entirely at its own default. {@link angularStops} adds the
 *     1-degree rung the direction pass specifies and is used by both tracks.
 *
 *  2. **`valueAt` wraps into `[0, 360)`, which a SIGNED range cannot use.**
 *     A draft angle lives in the open interval (-90, 90). A pointer a hair the
 *     wrong side of the reference reads as 359.7 rather than -0.3, and the
 *     clamp then slams the value to the far end of the range: the arrow jumps
 *     across the part when you nudge it past zero. {@link draftGaugeTrack}
 *     sidesteps it by making the track's value the taper's MAGNITUDE and
 *     putting the SIGN on the axis direction, so the track never sees a
 *     negative angle and the sign stays where the user typed it.
 *
 * **Both belong in `packages/design` eventually** — the second angular verb
 * would otherwise copy them, which is the WET defect this wave exists to
 * avoid. They are written here, once, with this note, so the move is a lift
 * rather than an archaeology exercise. See the report for CRAFT-10.
 */
import {
  angularTrack,
  formatAngle,
  LADDER_MIN_MAJOR_PX,
  LADDER_MIN_PITCH_PX,
  LADDER_MIN_RUNGS,
  MAX_RUNGS,
  NO_STOPS,
  type GaugeSeat,
  type GaugeStops,
  type GaugeTrack,
  type Vec3,
} from "@loft/design";

import { MAX_TWIST_DEG } from "../features/extrude";

/**
 * The shortest sweep the revolve gauge will pull to, degrees.
 *
 * NOT ZERO, and the reasoning is `MIN_DEPTH_MM`'s, reused rather than
 * re-derived: `parseAngleDeg` rejects a non-positive angle, so a drag that
 * could reach 0 would drive the editor into a state its own Save refuses —
 * the dead end the flow rule's fourth test forbids. Dragging back past the
 * reference parks here instead of going invalid.
 */
export const MIN_REVOLVE_DEG = 0.1;

/** A full turn — the form's own ceiling (`parseAngleDeg` rejects >360). */
export const MAX_REVOLVE_DEG = 360;

/**
 * The taper bounds, degrees of MAGNITUDE. The kernel's interval is open at
 * both ends (-90, 90) and `parseAngleDeg` enforces it, so the gauge stops a
 * hair inside rather than at a value Save would refuse.
 */
export const MIN_DRAFT_DEG = 0.1;
export const MAX_DRAFT_DEG = 89.9;

/** Coarse multiplier for Shift + arrow / PageUp / PageDown — extrude's. */
export const ANGLE_COARSE_FACTOR = 10;

/**
 * One fine key press, degrees. A degree is the unit an angle is typed in and
 * the finest rung the ladder draws, so one press is one degree — the promise
 * `data-step` makes to a screen reader and the grid the key lands on are then
 * the same number as the mark under the pointer.
 */
export const ANGLE_KEY_STEP_DEG = 1;

/**
 * Drag snap when no ladder is legible, degrees. Falls back to the ladder's own
 * minor whenever one is drawn — the rungs ARE the stops.
 */
export const ANGLE_SNAP_DEG = 5;

/** Two angles are the same turn within this, degrees. */
export const ANGLE_EPSILON_DEG = 1e-4;

/** The ladder, coarse to fine. 15/5 is the decision; 1 is the subdivision. */
const MAJOR_LADDER = [15, 30, 45, 90] as const;

/** Radians per degree, the direction this module converts in most. */
const RAD = Math.PI / 180;

/**
 * THE ANGULAR LADDER — major and minor graduations across a sweep of `value`
 * degrees drawn at `radius`, floored so no rung lands on its neighbour's pixel.
 *
 * Reimplements `angularTrack.stops` to add the 1-degree subdivision, and is
 * otherwise deliberately the same shape and the same two screen floors: a
 * MAJOR carries a number so it needs room to be read; a MINOR is only counted
 * past, so it clears the finer floor. That split is `ladderStops`' and the
 * reason is the ruler's own — long marks for the numbers, short between.
 *
 * `span` is the MAGNITUDE of the sweep, so a signed track passes `Math.abs`
 * and gets its rungs at positive offsets; the drawing places them along its own
 * sweep direction.
 */
export function angularStops(
  span: number,
  radius: number,
  unitsPerPixel: number,
): GaugeStops {
  const magnitude = Math.abs(span);
  if (!(magnitude > 0) || !(radius > 0)) return NO_STOPS;
  /** Arc length of `deg` at this radius, in CSS pixels. */
  const arcPx = (deg: number): number =>
    unitsPerPixel > 0 ? (deg * RAD * radius) / unitsPerPixel : Infinity;

  const majorStep =
    MAJOR_LADDER.find((d) => arcPx(d) >= LADDER_MIN_MAJOR_PX) ?? 90;
  // The minor below the major, FINEST FIRST — the ladder gets finer as the arc
  // gets longer on screen, so the first candidate that still clears the floor is
  // the smallest one that fits, not the largest.
  //
  // Coarsest-first is the plausible mistake and it is silent: it picks 5 at
  // every zoom where 5 fits, which is every zoom where 1 also fits, so the
  // 1-degree rung the direction pass specifies would never once be drawn and
  // the ladder would look perfectly correct while doing it.
  //
  // 15 subdivides by 5 then 1 — the drafting sequence — while a PROMOTED coarse
  // major subdivides by a third of itself, which is how 30/45/90 give back a
  // 10/15/30 rung rather than a decade one.
  const candidates =
    majorStep === 15 ? ([1, 5] as const) : ([majorStep / 3] as const);

  const round = (d: number): number => Math.round(d * 1e6) / 1e6;
  const major: number[] = [];
  // Strictly INSIDE the sweep: a graduation drawn under the arrowhead is a mark
  // you cannot read, and one at zero is the seat, which the axis already states.
  for (let d = majorStep; d < magnitude - majorStep * 0.5; d += majorStep) {
    major.push(round(d));
  }

  // Walk the candidates coarse-ward until one clears BOTH gates: the screen
  // floor below, and the rung ceiling above. `majorStep` terminates the walk —
  // a minor equal to its major contributes nothing, which is the "no minors"
  // answer. The ceiling matters at a close camera on a full turn, where a
  // 1-degree minor would put 360 crosses on the arc and make a hairbrush; it is
  // the linear ladder's own `MAX_RUNGS`, so the two instruments cannot disagree
  // about what "too many marks" means.
  let minorStep: number = majorStep;
  const minor: number[] = [];
  for (const step of [...candidates, majorStep]) {
    if (step < majorStep && arcPx(step) < LADDER_MIN_PITCH_PX) continue;
    const count = Math.max(0, Math.ceil(magnitude / step) - 1);
    if (step < majorStep && major.length + count > MAX_RUNGS) continue;
    minorStep = step;
    break;
  }
  if (minorStep < majorStep) {
    for (let d = minorStep; d < magnitude - minorStep * 0.5; d += minorStep) {
      const r = round(d);
      if (!major.includes(r)) minor.push(r);
    }
  }
  // Fewer than three marks is not a scale, it is debris on the shaft.
  if (major.length + minor.length < LADDER_MIN_RUNGS) return NO_STOPS;
  return { major, minor, pitch: minorStep, majorStep };
}

/** Where an arc gauge stands: the axis, the zero reference, and the radii. */
export interface ArcSeat {
  /** A point ON the axis — the arc's centre. */
  centre: Vec3;
  /** Unit direction of the axis. The sweep is right-handed about it. */
  axis: Vec3;
  /** Unit direction across the axis that the arc measures FROM (0 degrees). */
  reference: Vec3;
  /** Radius the arc is drawn at, scene mm. */
  arcRadiusMm: number;
  /**
   * The instrument's OWN scale, scene mm — the arrowhead and the rung arms are
   * fractions of it, so the gauge suits the part rather than the number.
   */
  seatRadiusMm: number;
}

/** The `GaugeSeat` an {@link ArcSeat} means, in `angularTrack`'s own terms. */
function gaugeSeat(seat: ArcSeat): GaugeSeat {
  return {
    base: seat.centre,
    // For an ANGULAR track the seat's `dir` is the axis of rotation and
    // `arms[0]` is the zero-degree reference — not the value direction. The
    // second arm is unused by the angular draw (it builds its cross from the
    // radial and the axis) and is filled with the axis so the tuple is honest
    // rather than carrying a vector nothing derived.
    dir: seat.axis,
    radius: seat.seatRadiusMm,
    arms: [seat.reference, seat.axis],
  };
}

/**
 * THE REVOLVE SWEEP GAUGE — a protractor arc seated on the axis of revolution,
 * running from the profile out to the current angle.
 *
 * The arc starts at the profile's own furthest-out point rather than at some
 * neutral reference, because the turn being dimensioned starts AT the material:
 * an arc that began elsewhere would carry the right number and describe the
 * wrong solid.
 */
export function revolveGaugeTrack(seat: ArcSeat): GaugeTrack {
  const base = angularTrack(gaugeSeat(seat), {
    min: MIN_REVOLVE_DEG,
    max: MAX_REVOLVE_DEG,
    radius: seat.arcRadiusMm,
    snap: ANGLE_SNAP_DEG,
    keyStep: ANGLE_KEY_STEP_DEG,
    coarseFactor: ANGLE_COARSE_FACTOR,
    epsilon: ANGLE_EPSILON_DEG,
    format: (value, opts) => formatAngle(value, opts ?? {}),
  });
  return {
    ...base,
    stops: (value, unitsPerPixel) =>
      angularStops(value, seat.arcRadiusMm, unitsPerPixel),
  };
}

/**
 * THE DRAFT TAPER GAUGE — the same instrument, seated on the line where the
 * tapered face meets the neutral plane, measuring from the face's own plane.
 *
 * ## The value is a MAGNITUDE and the sign rides on the axis
 *
 * A draft angle is SIGNED: ＋ tapers inward toward the pull, − outward. Handing
 * that straight to `angularTrack` does not work, because its `valueAt` wraps a
 * pointer answer into `[0, 360)` — so a pointer a hair below the reference
 * reads 359.7, the clamp slams it to the far end of (-90, 90), and the arrow
 * jumps across the part every time you cross zero. Since zero is also the one
 * value the form rejects (`"A draft needs a non-zero angle to taper by"`), a
 * gauge that crosses it is a gauge that walks through a dead end.
 *
 * So the track's value is `|angle|` and the SIGN is applied to the axis
 * direction, which reverses the sweep. Three consequences, all wanted:
 *
 *  · the arc always sweeps AWAY from the face, whichever way the taper leans,
 *    so it never doubles back over the geometry it dimensions;
 *  · the drag cannot reach the invalid zero or step over it into the other
 *    sense, which is the Pull control's job and one key away; and
 *  · the readout still says **−3°**, because {@link draftGaugeTrack} formats
 *    the SIGNED value — the grip's `aria-valuenow` is the magnitude and its
 *    `valueText` is the signed angle, which is exactly what `valueText` is for.
 *
 * @param sign ＋1 or −1 — the sense of the taper the editor currently holds.
 */
export function draftGaugeTrack(seat: ArcSeat, sign: 1 | -1): GaugeTrack {
  const signed: ArcSeat = {
    ...seat,
    axis: [seat.axis[0] * sign, seat.axis[1] * sign, seat.axis[2] * sign],
  };
  const base = angularTrack(gaugeSeat(signed), {
    min: MIN_DRAFT_DEG,
    max: MAX_DRAFT_DEG,
    radius: seat.arcRadiusMm,
    snap: ANGLE_SNAP_DEG,
    keyStep: ANGLE_KEY_STEP_DEG,
    coarseFactor: ANGLE_COARSE_FACTOR,
    epsilon: ANGLE_EPSILON_DEG,
    // The magnitude in, the SIGNED angle out — one place, so the tag, the
    // spoken value and the field cannot disagree about which way it leans.
    format: (value, opts) => formatAngle(value * sign, opts ?? {}),
  });
  return {
    ...base,
    stops: (value, unitsPerPixel) =>
      angularStops(value, seat.arcRadiusMm, unitsPerPixel),
  };
}

/**
 * THE EXTRUDE TWIST GAUGE — the same instrument a third time, seated on the far
 * cap about the twist axis (helical-gear gap G1; the seat is `twistArcSeat`).
 *
 * A twist is the one angle here that is SIGNED, CROSSES ZERO, and runs to TEN
 * TURNS, so it meets both of the gaps the header names and cannot take the
 * draft's way round the first:
 *
 *  · **The sign cannot ride on the axis.** Zero is a valid twist (none), and
 *    dragging through it from right-hand to left-hand is one gesture, so the
 *    track's value IS the signed angle. The ladder is drawn on the side the
 *    value is on: {@link angularStops} is asked for the magnitude and its rungs
 *    are mirrored for a negative sweep.
 *
 *  · **`valueAt` must not wrap.** The drag reads `grab + (at - atGrab)`, so a
 *    pointer answer that jumps from 359 to 0 as it passes the reference jumps
 *    the twist by a whole turn. The wrapper UNWRAPS: each answer is the
 *    equivalent of the raw angle nearest the previous answer, so a pointer
 *    circling the axis twice reads 720. That is state on a pure object, and it
 *    is deliberate: the track is memoised per seat, the seat does not move
 *    while you drag its twist, and the only failure is a pointer that crosses
 *    half a turn between two `pointermove` events, which no hand does.
 *
 * The bounds are the contract's (`MAX_TWIST_DEG` either way): a drag can
 * reach everything the kernel takes and nothing it refuses.
 */
export function twistGaugeTrack(seat: ArcSeat): GaugeTrack {
  const base = angularTrack(gaugeSeat(seat), {
    min: -MAX_TWIST_DEG,
    max: MAX_TWIST_DEG,
    radius: seat.arcRadiusMm,
    snap: ANGLE_SNAP_DEG,
    keyStep: ANGLE_KEY_STEP_DEG,
    coarseFactor: ANGLE_COARSE_FACTOR,
    epsilon: ANGLE_EPSILON_DEG,
    format: (value, opts) => formatAngle(value, opts ?? {}),
  });
  let last: number | null = null;
  return {
    ...base,
    valueAt: (rayOrigin, rayDirection) => {
      const wrapped = base.valueAt(rayOrigin, rayDirection);
      if (wrapped === null) return null;
      last =
        last === null
          ? wrapped > 180
            ? wrapped - 360
            : wrapped
          : wrapped + Math.round((last - wrapped) / 360) * 360;
      return last;
    },
    stops: (value, unitsPerPixel) => {
      const stops = angularStops(value, seat.arcRadiusMm, unitsPerPixel);
      if (value >= 0 || stops === NO_STOPS) return stops;
      return {
        ...stops,
        major: stops.major.map((d) => -d),
        minor: stops.minor.map((d) => -d),
      };
    },
  };
}

/**
 * A point on the arc `deg` degrees from the reference — the same parametrisation
 * `angularTrack.pointAt` uses, exposed so the PREVIEW line-work can be drawn on
 * the identical circle the gauge is drawn on.
 *
 * DRY, and load-bearing: a preview computed on its own circle would drift from
 * the instrument by whatever the two derivations disagreed about, and the
 * disagreement would be invisible until somebody looked at a screenshot at a
 * large angle. One parametrisation, two drawings.
 */
export function arcPoint(seat: ArcSeat, deg: number, radiusMm: number): Vec3 {
  const r = deg * RAD;
  const { axis, reference, centre } = seat;
  const perp: Vec3 = [
    axis[1] * reference[2] - axis[2] * reference[1],
    axis[2] * reference[0] - axis[0] * reference[2],
    axis[0] * reference[1] - axis[1] * reference[0],
  ];
  const c = Math.cos(r);
  const s = Math.sin(r);
  return [
    centre[0] + (reference[0] * c + perp[0] * s) * radiusMm,
    centre[1] + (reference[1] * c + perp[1] * s) * radiusMm,
    centre[2] + (reference[2] * c + perp[2] * s) * radiusMm,
  ];
}

/**
 * Rotate `point` about the arc seat's axis by `deg` — Rodrigues, allocation-free
 * enough for a preview rebuilt on a value change (not per frame).
 *
 * This is what turns a profile polyline into the swept result's end section.
 */
export function rotateAboutAxis(seat: ArcSeat, point: Vec3, deg: number): Vec3 {
  const r = deg * RAD;
  const c = Math.cos(r);
  const s = Math.sin(r);
  const k = seat.axis;
  const p: Vec3 = [
    point[0] - seat.centre[0],
    point[1] - seat.centre[1],
    point[2] - seat.centre[2],
  ];
  const kDotP = k[0] * p[0] + k[1] * p[1] + k[2] * p[2];
  const kCrossP: Vec3 = [
    k[1] * p[2] - k[2] * p[1],
    k[2] * p[0] - k[0] * p[2],
    k[0] * p[1] - k[1] * p[0],
  ];
  return [
    seat.centre[0] + p[0] * c + kCrossP[0] * s + k[0] * kDotP * (1 - c),
    seat.centre[1] + p[1] * c + kCrossP[1] * s + k[1] * kDotP * (1 - c),
    seat.centre[2] + p[2] * c + kCrossP[2] * s + k[2] * kDotP * (1 - c),
  ];
}

// --- THE RESULT PREVIEW, AS LINE-WORK ---------------------------------------

/**
 * How many points of a profile loop trace a RAIL through the sweep.
 *
 * The rails are the arcs the profile's own corners travel along, and they are
 * what makes a drag read as *turning material* rather than *moving a line*.
 * Eight is a deliberate ceiling: a rail per vertex on a 60-segment arc-
 * approximated loop is 3 600 segments rebuilt on every pointermove, and the
 * picture is no clearer for it — a sweep is legible from a handful of rails
 * plus its end section, which is exactly how a lathe part is drawn.
 */
const MAX_RAILS = 8;

/** Points along a rail per 90 degrees swept — smooth without being a mesh. */
const RAIL_POINTS_PER_QUARTER = 8;

/** Evenly spread at most {@link MAX_RAILS} indices across a loop. */
function railIndices(count: number): number[] {
  if (count <= MAX_RAILS) return Array.from({ length: count }, (_, i) => i);
  const out: number[] = [];
  for (let i = 0; i < MAX_RAILS; i += 1) {
    out.push(Math.round((i * count) / MAX_RAILS) % count);
  }
  return out;
}

/** Append one polyline to a flat segment-pair buffer. */
function pushPolyline(out: number[], points: readonly Vec3[], close: boolean) {
  for (let i = 0; i + 1 < points.length; i += 1) {
    const a = points[i] as Vec3;
    const b = points[i + 1] as Vec3;
    out.push(a[0], a[1], a[2], b[0], b[1], b[2]);
  }
  if (close && points.length > 2) {
    const a = points[points.length - 1] as Vec3;
    const b = points[0] as Vec3;
    out.push(a[0], a[1], a[2], b[0], b[1], b[2]);
  }
}

/**
 * THE RESULT PREVIEW — the swept arc and its end plane, as pure line-work.
 *
 * ## Why line-work and not a translucent solid
 *
 * The direction pass gives every gauge in this wave a choice: ship a ghost
 * MESH, or ship a GEOMETRIC preview short of one — and a gauge whose drag
 * changes a number and not the model "is worse than the form it replaces: it
 * promises direct manipulation and delivers a slider". Route (b) is the
 * recommended one and it is the right one here for a reason specific to a
 * revolve: the swept solid of a 300-degree turn ENCLOSES the axis and the
 * profile, so a translucent shell would hide the very instrument you are
 * dragging, and the ladder — the signature element — would be read through two
 * layers of tinted metal. Line-work leaves the gauge legible at every angle,
 * needs no kernel round-trip, belongs to idiom D, and answers the only question
 * the drag poses: *how far round does that go?*
 *
 * ## What is drawn
 *
 *  · **the end section** — the profile's own loops, rotated to the current
 *    angle. This is the "end plane": the face the turn stops on, in the place
 *    it will actually stop. It is the part that MOVES under the pointer, and it
 *    is drawn solid because it is a real edge of the result.
 *  · **the rails** — the arcs a handful of the profile's corners travel along.
 *    They state the path, and they are what stops a 200-degree sweep reading as
 *    a section that teleported to the far side.
 *
 * A closed turn (360 degrees) draws its end section exactly on top of the
 * profile, which is correct: a full revolution HAS no end face, and the rails
 * alone carry the picture.
 *
 * Rebuilt on a value change, never per frame.
 */
export function revolveSweepLines(
  seat: ArcSeat,
  loops: readonly (readonly Vec3[])[],
  angleDeg: number,
): Float32Array {
  const out: number[] = [];
  const quarters = Math.max(1, Math.abs(angleDeg) / 90);
  const steps = Math.max(2, Math.ceil(quarters * RAIL_POINTS_PER_QUARTER));
  for (const loop of loops) {
    if (loop.length < 2) continue;
    const end = loop.map((p) => rotateAboutAxis(seat, p, angleDeg));
    pushPolyline(out, end, true);
    for (const index of railIndices(loop.length)) {
      const from = loop[index] as Vec3;
      const rail: Vec3[] = [];
      for (let i = 0; i <= steps; i += 1) {
        rail.push(rotateAboutAxis(seat, from, (angleDeg * i) / steps));
      }
      pushPolyline(out, rail, false);
    }
  }
  return new Float32Array(out);
}
