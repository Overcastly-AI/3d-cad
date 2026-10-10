/**
 * The Move command's typed pose — the six cells of the Move panel (X, Y, Z in
 * the document unit, Rx, Ry, Rz in degrees) to and from an OCCT `Placement`.
 *
 * Everything here is in the KERNEL frame (Z up), because that is the frame the
 * modeller reads in every other readout: the solve block, the mate values and
 * the exported STEP. The scene frame (Y up) never reaches a cell.
 *
 * ANGLE CONVENTION: fixed-axis X, then Y, then Z (roll, pitch, yaw about the
 * world axes), i.e. `R = Rz · Ry · Rx`. That is the reading where typing only
 * Rz = 90 means "turn it a quarter about world Z", which is what the cell
 * says. three.js names that matrix Euler order `"ZYX"`.
 *
 * Pure: three's maths types run headless, so this is unit-tested in node.
 */
import { type LengthUnit, parseLength } from "@loft/design";
import { Euler, MathUtils, Quaternion } from "three";

import { lengthInputValue } from "../units/length";
import type { Placement } from "./placement";

/** The six raw cell strings, exactly as typed. */
export interface MoveFields {
  x: string;
  y: string;
  z: string;
  rx: string;
  ry: string;
  rz: string;
}

export type MoveField = keyof MoveFields;

export const POSITION_FIELDS = ["x", "y", "z"] as const;
export const ROTATION_FIELDS = ["rx", "ry", "rz"] as const;

const EULER_ORDER = "ZYX";

/** A placement's orientation as fixed-axis X→Y→Z degrees `[rx, ry, rz]`. */
export function orientationToDegrees(
  orientation: Placement["orientation"],
): [number, number, number] {
  const q = new Quaternion(
    orientation.x,
    orientation.y,
    orientation.z,
    orientation.w,
  );
  if (q.lengthSq() === 0) q.set(0, 0, 0, 1);
  q.normalize();
  const e = new Euler().setFromQuaternion(q, EULER_ORDER);
  return [e.x, e.y, e.z].map((r) => clean(MathUtils.radToDeg(r))) as [
    number,
    number,
    number,
  ];
}

/** Fixed-axis X→Y→Z degrees → a unit orientation quaternion (w ≥ 0). */
export function degreesToOrientation(
  rx: number,
  ry: number,
  rz: number,
): Placement["orientation"] {
  const q = new Quaternion().setFromEuler(
    new Euler(
      MathUtils.degToRad(rx),
      MathUtils.degToRad(ry),
      MathUtils.degToRad(rz),
      EULER_ORDER,
    ),
  );
  const sign = q.w < 0 ? -1 : 1;
  return {
    w: clean(sign * q.w),
    x: clean(sign * q.x),
    y: clean(sign * q.y),
    z: clean(sign * q.z),
  };
}

/**
 * Snap float dust to the value it is standing in for: −0 and |n| < 1e-12 → 0.
 * Without it a 90° turn reads `-1.2e-15` in a cell that should say `0`.
 */
function clean(n: number): number {
  return Math.abs(n) < 1e-12 ? 0 : n;
}

/** An angle as a cell string: up to 4 decimals, trailing zeros trimmed. */
function angleInputValue(degrees: number): string {
  const rounded = Number.parseFloat(degrees.toFixed(4));
  return String(rounded === 0 ? 0 : rounded);
}

/** Seed the six cells from a placement, lengths in the document unit. */
export function fieldsFromPlacement(
  placement: Placement,
  unit: LengthUnit,
): MoveFields {
  const [rx, ry, rz] = orientationToDegrees(placement.orientation);
  const { x, y, z } = placement.position;
  return {
    x: lengthInputValue(x, unit),
    y: lengthInputValue(y, unit),
    z: lengthInputValue(z, unit),
    rx: angleInputValue(rx),
    ry: angleInputValue(ry),
    rz: angleInputValue(rz),
  };
}

/** Parse a degree cell: a plain signed number, or null. */
export function parseDegrees(input: string): number | null {
  const trimmed = input.trim().replace(/°$/, "");
  if (trimmed === "") return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

/** Which cells do not parse — the panel flags them and holds the commit. */
export function invalidFields(
  fields: MoveFields,
  unit: LengthUnit,
): Set<MoveField> {
  const bad = new Set<MoveField>();
  for (const key of POSITION_FIELDS) {
    if (parseLength(fields[key], unit) === null) bad.add(key);
  }
  for (const key of ROTATION_FIELDS) {
    if (parseDegrees(fields[key]) === null) bad.add(key);
  }
  return bad;
}

/**
 * The placement the six cells describe, or null while any cell is unparseable.
 *
 * `base` supplies the orientation when no angle cell has been edited: the cells
 * show angles rounded to 4 decimals, and rebuilding the quaternion from those
 * would turn a move that only touched Y into a tiny unasked-for rotation too.
 */
export function placementFromFields(
  fields: MoveFields,
  unit: LengthUnit,
  base: Placement,
  rotationEdited: boolean,
): Placement | null {
  if (invalidFields(fields, unit).size > 0) return null;
  const mm = (key: (typeof POSITION_FIELDS)[number]) =>
    parseLength(fields[key], unit) as number;
  const deg = (key: (typeof ROTATION_FIELDS)[number]) =>
    parseDegrees(fields[key]) as number;
  return {
    position: { x: mm("x"), y: mm("y"), z: mm("z") },
    orientation: rotationEdited
      ? degreesToOrientation(deg("rx"), deg("ry"), deg("rz"))
      : base.orientation,
  };
}

/**
 * Are two placements the same pose, within a hair? Position to 1e-6 mm, and
 * rotation by |q·q'| (q and −q are one rotation), so a release that moved
 * nothing writes nothing.
 */
export function samePlacement(a: Placement, b: Placement): boolean {
  const dp = Math.hypot(
    a.position.x - b.position.x,
    a.position.y - b.position.y,
    a.position.z - b.position.z,
  );
  const qa = a.orientation;
  const qb = b.orientation;
  const dot = Math.abs(qa.w * qb.w + qa.x * qb.x + qa.y * qb.y + qa.z * qb.z);
  return dp < 1e-6 && 1 - dot < 1e-12;
}
