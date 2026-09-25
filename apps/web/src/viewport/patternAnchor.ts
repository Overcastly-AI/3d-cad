/**
 * WHERE THE TWO PATTERN GAUGES STAND — the seats, and nothing else (CRAFT-11).
 *
 * ## Two instruments, not one with two outputs
 *
 * The roadmap's sentence — *"drag to set spacing, drag past a pitch to add
 * count"* — is one pointer driving two numbers, which is the exact ambiguity
 * this wave exists to remove: the user cannot say which quantity they are
 * adjusting and cannot hold one steady. Direction §5.3 decides it the other
 * way and this module is that decision expressed as geometry: a `stepped`
 * COUNT gauge along the row, a `linear` SPACING gauge across the first gap, two
 * grips, two obvious meanings, no modifier keys.
 *
 * ## The layout is a drafting convention, not a placement heuristic
 *
 * Both instruments run PARALLEL to the row on two rails hung off it, the way a
 * machine drawing dimensions a repeated feature: the LOCAL dimension (one gap)
 * nearest the part, the OVERALL dimension (the whole row) outside it. That is
 * the "3 × 10 = 30" stack every engineer reading this app has drawn by hand,
 * and it is doing three jobs at once:
 *
 *  1. it is the app's own vernacular rather than a gizmo convention;
 *  2. it keeps each gauge off the body, so neither instrument is competing
 *     with the metal it describes;
 *  3. **it separates the two HIT SLEEVES geometrically.** Two gauges on one
 *     feature means two DOM bands in the same neighbourhood, and a sleeve that
 *     resolves to its sibling is this repo's most expensive defect class — a
 *     control that is present, correctly computed, and unreachable. Seated on
 *     one line they would overlap for the whole first gap. Separated by a rail
 *     pitch they cannot, and `pattern-gauges.spec.ts` measures that each
 *     resolves to ITSELF rather than merely to "some gauge".
 *
 * ## Why the count gauge's base sits one pitch BEHIND the seed
 *
 * `steppedTrack` draws a rung at every integer `n` at `n × pitch` from its
 * base, and `count` INCLUDES the seed. Seating the base at the seed body would
 * put rung `n` on instance `n`, i.e. one gap past every copy, and seating it so
 * the numbers line up by subtracting one from the value would put a `2` on the
 * gauge beside a `3` in the rail — the two-dialects failure, in the one place
 * this item is explicitly told to avoid it.
 *
 * So the base is `centre − pitch·dir` and the value stays the COUNT. Rung `n`
 * then lands on instance `n − 1`: with `min = 2` the drawn rungs are exactly
 * instances 1…count−1, **which is exactly the set of ghost copies.** The
 * preview and the ladder are one drawing (direction §3.5), the grip sits on the
 * last copy, and the number under the pointer is the number in the field.
 *
 * ## No stores
 *
 * Everything here is a function of a bounding box and a direction. The anchor
 * reaches the component as a PROP so that CRAFT-12's persistent selection store
 * is a re-wiring at the integration point and not a rewrite of this module.
 */
import { crossArms, type GaugeSeat, type Vec3 } from "@loft/design";

import { occtToSceneTuple } from "../sketch/plane";
import type { Vec3 as WireVec3 } from "../api/parts";

/**
 * Smallest spacing a drag may produce, mm.
 *
 * The same floor `MIN_DEPTH_MM` sets on a depth, for the same reason: a drag
 * that can reach a value the form cannot submit is the dead end the flow rule's
 * fourth test forbids, and a zero spacing stacks every copy on the seed.
 */
export const MIN_SPACING_MM = 0.1;

/** Ceiling, mm — a 10 m pitch is past anything this kernel is for. */
export const MAX_SPACING_MM = 10_000;

/**
 * Smallest count a drag may produce.
 *
 * `parseCount` rejects anything under 2 because `count` includes the seed, so
 * `count = 1` repeats nothing. The gauge must not be able to reach it either.
 */
export const MIN_PATTERN_COUNT = 2;

/**
 * Ceiling, and it is the SERVER'S number (`MAX_PATTERN_COUNT = 500`, the audit
 * G2 work bound) rather than a comfortable-looking one of our own. A gauge that
 * stopped at some smaller round number would be a second opinion about what a
 * pattern may be, and the first thing anyone would notice is the drag refusing
 * a count the field accepts.
 */
export const MAX_PATTERN_COUNT = 500;

/**
 * Clearance from the body's surface to the first rail, as a fraction of the
 * instrument's own scale.
 *
 * OF `radius`, NOT of `perpHalf`, and that is the §2.2 lesson a third time: two
 * lengths derived from two unrelated quantities. `perpHalf` is the body's
 * extent along the RAIL direction — its thinnest dimension for the commonest
 * case there is, a flat plate — so a 95 x 65 x 10 mm plate got its rails 6 mm
 * under a 95 mm-wide part. MEASURED: both rods then drew ACROSS the plate's top
 * face, because the gauge is `depthTest: false` and a rail that close to the
 * metal is an x-ray line lying on it. The clearance has to scale with how big
 * the part READS, which is exactly what `radius` already means — it is the
 * number sizing the arrowhead and the rungs, so using it here makes one scale
 * where there were two.
 *
 * It had a `max(…, 6 mm)` floor under it until the seat was measured against
 * the frame; {@link countRailOffset} carries that finding.
 */
export const RAIL_CLEARANCE_FRAC = 0.35;

/**
 * Rail separation, as a fraction of the instrument's own scale.
 *
 * This is the number that keeps the two hit sleeves apart, and it used to be
 * `max(0.5 · radius, 10 mm)`. **The floor was the defect** — see
 * {@link countRailOffset} — and with it gone the fraction carries the whole
 * guarantee, so it is now chosen against a projected pixel count rather than a
 * world length: under the fit-to-body camera `0.3 · radius` measured **78, 83
 * and 70 px** on parts of 29, 11 and 102 mm, against a 12 px sleeve
 * half-thickness. The floor gave **208, 371 and 116 px** on the same three —
 * the same requirement, met by 3x as much screen on the part that could least
 * afford it. A fraction can be scale-invariant; a millimetre cannot.
 */
export const RAIL_PITCH_FRAC = 0.3;

/** Seat scale floor, mm — a hairline part still gets a grabbable instrument. */
const MIN_SEAT_RADIUS_MM = 2;

/** An axis-aligned box in SCENE millimetres. */
export interface SceneBounds {
  min: Vec3;
  max: Vec3;
}

/** Where a pattern's instruments stand, in SCENE millimetres. */
export interface PatternAnchor {
  /** Centre of the seed body — instance 0, the point the row grows from. */
  centre: Vec3;
  /** Unit direction the row runs along, in the SCENE frame. */
  dir: Vec3;
  /** Unit direction the dimension rails hang along, across {@link dir}. */
  perp: Vec3;
  /** Half the body's extent along {@link perp} — where clearance starts. */
  perpHalf: number;
  /**
   * The instruments' own scale: half-diagonal of the body's section ACROSS the
   * row. It is the pattern's analogue of the extrude gauge's profile radius —
   * the size of the thing being repeated, not the size of the repetition — so
   * the arrowheads and rungs suit the part and hold still while you drag.
   */
  radius: number;
}

const add = (a: Vec3, b: Vec3, k: number): Vec3 => [
  a[0] + b[0] * k,
  a[1] + b[1] * k,
  a[2] + b[2] * k,
];

const dot = (a: Vec3, b: Vec3): number =>
  a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

/** `-0` normalised away, so a zero component never renders or reads as `-0`. */
const unsign = (n: number): number => (n === 0 ? 0 : n);

function normalize(v: Vec3): Vec3 {
  const length = Math.hypot(v[0], v[1], v[2]);
  if (length === 0) return [1, 0, 0];
  return [unsign(v[0] / length), unsign(v[1] / length), unsign(v[2] / length)];
}

/**
 * Which way the dimension rails hang, in the SCENE frame.
 *
 * DOWN (`−Y`) for any row that is not itself vertical, because a drawing hangs
 * its dimensions below the view and because the space under a part is the space
 * a modeller is least likely to be working in. A vertical row has no "below"
 * that is not along itself, so its rails go out to `+X` instead.
 *
 * Deliberately one of the two, deterministically, rather than "whichever faces
 * the camera": a dimension that swaps sides as you orbit is a dimension you
 * cannot point at, and the gauge is a thing you grab.
 */
export function patternPerp(dir: Vec3): Vec3 {
  const unit = normalize(dir);
  return Math.abs(unit[1]) > 0.9 ? [1, 0, 0] : [0, -1, 0];
}

/** A wire `Vec3` (OCCT world mm, Z-up) as a scene-frame tuple. */
export function sceneDirection(v: WireVec3): Vec3 {
  return normalize(occtToSceneTuple([v.x, v.y, v.z]));
}

/**
 * The anchor for a row of `dir` through a body of `bounds`.
 *
 * `bounds` are already SCENE millimetres — the GLB bakes OCCT's Z-up→Y-up
 * rotation — while a pattern's direction is authored in the kernel's world
 * frame, so the direction is the only thing that needs converting and
 * {@link sceneDirection} is the one place it happens.
 */
export function patternAnchor(bounds: SceneBounds, dir: Vec3): PatternAnchor {
  const unit = normalize(dir);
  const perp = patternPerp(unit);
  const centre: Vec3 = [
    (bounds.min[0] + bounds.max[0]) / 2,
    (bounds.min[1] + bounds.max[1]) / 2,
    (bounds.min[2] + bounds.max[2]) / 2,
  ];
  const half: Vec3 = [
    Math.abs(bounds.max[0] - bounds.min[0]) / 2,
    Math.abs(bounds.max[1] - bounds.min[1]) / 2,
    Math.abs(bounds.max[2] - bounds.min[2]) / 2,
  ];
  const perpHalf = Math.abs(dot(half, perp));
  // The SECTION across the row: the box's half-diagonal with the component
  // along the row removed. A long row of a small part must not get a huge
  // instrument just because the row is long — the seat is about the thing being
  // repeated, which is what `radius` means everywhere else in the gauge.
  const alongHalf = Math.abs(dot(half, unit));
  const diagonal = Math.hypot(half[0], half[1], half[2]);
  const section = Math.sqrt(
    Math.max(0, diagonal * diagonal - alongHalf * alongHalf),
  );
  return {
    centre,
    dir: unit,
    perp,
    perpHalf,
    radius: Math.max(MIN_SEAT_RADIUS_MM, section),
  };
}

/** Distance from the body centre to the near (spacing) rail. */
export function spacingRailOffset(anchor: PatternAnchor): number {
  return anchor.perpHalf + RAIL_CLEARANCE_FRAC * anchor.radius;
}

/**
 * Distance from the body centre to the far (count) rail.
 *
 * ## THE SEAT USED TO LEAVE THE FRAME, AND THE FLOORS ARE WHY (P1, 2026-09-14)
 *
 * Measured on the flow `pattern-gauges.spec.ts` drives: `elementFromPoint` down
 * the count gauge's own projected track resolved to the instrument at **3 of 16
 * sample points**, and — the fact that names the cause — **six of the sixteen
 * resolved to `null`**, off the frame entirely. Occlusion cannot produce a
 * `null`. The rest landed on `view-home` / `view-fit` / `timeline-way`: the
 * track was being laid across the nav chrome and then off the bottom edge.
 *
 * CRAFT-11 honestly measured 16/16 for the same gauge. Both readings are true,
 * and the state that differs between them is **the size of the part in
 * millimetres**:
 *
 * | body (scene mm) | camera zoom | count reach | spacing reach |
 * |---|---|---|---|
 * | 102 x 10 x 73 | 6.9 | 16/16 | 16/16 |
 * | 29 x 10 x 23 (the spec's) | 22.5 | **3/16** | 16/16 |
 * | 11 x 10 x 11 | 40.1 | **0/16** | **2/16** |
 *
 * The camera fits the BODY, so every world millimetre buys more pixels the
 * smaller the part is. The rails were hung at `perpHalf + max(6, 0.35·r) +
 * max(10, 0.5·r)`, and BOTH `max`es select their constant whenever
 * `radius < 17 mm` — any part whose section across the row is under about
 * 34 mm, which is most of them. So the offset stopped shrinking with the part
 * while the frame went on shrinking with it.
 *
 * In pixels, on the spec's part: the far rail sat **438 px below the body's
 * centre on a canvas whose centre-to-bottom is 449 px**, and the track then
 * descends a further 166 px as it runs. The rail was 11 px above the bottom
 * edge before the arrow had drawn anything.
 *
 * **The floors were screen-space requirements written in world units.** Their
 * own docstrings said so — "10 mm projects to comfortably more than the 12 px
 * sleeve half-thickness at any camera that can frame a part worth patterning" —
 * and that sentence is only true of parts big enough to make the fraction win
 * anyway. A fraction of `radius` IS the scale-invariant form of the same
 * requirement, because the camera frames `radius`: measured across a 9x range
 * of part size the rail separation now holds at **78 / 83 / 70 px**, where the
 * floors produced **208 / 371 / 116**. So the floors are gone and the
 * fractions, retuned, carry it.
 *
 * What this does NOT fix, said plainly: a part SMALLER than the row it
 * generates. At 11 x 11 x 10 mm with a 10 mm pitch the ghost copies themselves
 * run off the right edge — the whole preview is outside a frame fitted to one
 * body, and the gauge merely inherits it. That is a camera question (nothing
 * re-fits when a preview appears), not a seat question, and it is not fixable
 * from this file.
 */
export function countRailOffset(anchor: PatternAnchor): number {
  return spacingRailOffset(anchor) + RAIL_PITCH_FRAC * anchor.radius;
}

/**
 * The SPACING gauge's seat: the near rail, starting under the seed body, so the
 * arrow spans exactly the first gap and its point lands on the first copy.
 */
export function spacingSeat(anchor: PatternAnchor): GaugeSeat {
  return {
    base: add(anchor.centre, anchor.perp, spacingRailOffset(anchor)),
    dir: anchor.dir,
    radius: anchor.radius,
    arms: crossArms(anchor.dir),
  };
}

/**
 * The COUNT gauge's seat: the far rail, ONE PITCH BEHIND the seed — see this
 * module's note. `pitch` is the current spacing in mm, which is also the
 * stepped track's `unitsPerValue`, so the seat moves as the spacing is dragged
 * and the rungs stay on the copies.
 */
export function countSeat(anchor: PatternAnchor, pitch: number): GaugeSeat {
  const base = add(anchor.centre, anchor.perp, countRailOffset(anchor));
  return {
    base: add(base, anchor.dir, -pitch),
    dir: anchor.dir,
    radius: anchor.radius,
    arms: crossArms(anchor.dir),
  };
}
