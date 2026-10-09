import { Vector3 } from "three";

import { VIEW_DIRECTIONS } from "./viewCommands";

/** The studio iso direction — every "home" has always opened here. */
export const ISO_DIR = new Vector3(...VIEW_DIRECTIONS.iso).normalize();
/**
 * Where the camera BOOTS: on {@link ISO_DIR}, at the radius the old literal
 * `[45, 32, 60]` sat at. That literal was a degree off iso, and the miss was
 * not cosmetic: a chrome `fit` that lands before the first geometry keeps the
 * boot DIRECTION, while an auto-fit that lands first uses `ISO_DIR` — so the
 * same part opened at one of two attitudes depending on which won the race
 * (SEL-7's ink census read 74 px or 90 px of origin mark on identical scenes).
 */
export const BOOT_CAMERA_POSITION = ISO_DIR.clone()
  .multiplyScalar(81.5)
  .toArray();
/** Fit margin: orbit radius = bounds diagonal × this (the historic framing). */
export const FIT_FACTOR = 1.75;
/** Default orbit radius when the scene is empty (the resting bench view). */
export const EMPTY_RADIUS = 200 * FIT_FACTOR;
/**
 * The scene camera's vertical field of view. Declared here rather than only in
 * the `<Canvas camera>` prop because the projection swap has to reproduce this
 * exact framing when it converts a zoom back into a distance — two copies of
 * the number would be two framings that drift apart.
 */
export const CAMERA_FOV_DEG = 40;
