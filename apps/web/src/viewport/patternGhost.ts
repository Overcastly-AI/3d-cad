/**
 * THE PATTERN PREVIEW — ghost copies at the instance positions (CRAFT-11).
 *
 * ## Route (b), and why this item would otherwise have been deferred
 *
 * Direction §8.4 is blunt about it: *"a gauge whose drag changes a number and
 * not the model is worse than the form it replaces — it promises direct
 * manipulation and delivers a slider"*, and **"the field updates and the model
 * does not" is not an option** — an item that would ship that is deferred to
 * W5, not shipped. So every gauge in this wave owes a preview, and the one
 * named for pattern is *ghost copies at the instance positions*: line work
 * derived from geometry the client already holds, with no kernel round trip,
 * answering the only question the drag actually poses — **how many of those,
 * and how far apart?**
 *
 * ## The preview and the ladder are the same drawing
 *
 * A `stepped` track's stops ARE the instance positions (direction §3.5), so for
 * this verb the ghosts and the count gauge's rungs mark the same points in
 * space and neither is drawn twice: {@link patternInstanceOffsets} is the one
 * list, the ghosts stand on it, and `countSeat` is arranged so the primitive's
 * own rungs land on it too. Each rung is therefore a centre mark on a copy,
 * which is what a drawing does to a patterned feature anyway.
 *
 * ## LINE WORK, not translucent solids — and this was got wrong first
 *
 * §8.4 says route (b) "is line-work", and the first draft of this read "ghost
 * copies" as filled matcap solids at `preview.surfaceOpacity`. That is route
 * (a) in route (b)'s clothing, and on a real part it was actively wrong:
 *
 *  · a pattern whose copies UNION into one longer bar — the common case, and
 *    the one `pattern.spec.ts` asserts — has a spacing SMALLER than the body,
 *    so every copy overlaps the seed with numerically COINCIDENT faces. They
 *    z-fought, and the ghosts painted brass in bands across committed metal:
 *    the drawing said the existing body was pending.
 *  · MEASURED on a 95 x 65 x 10 plate: the viewport's warm-pixel census barely
 *    moved when the scope tint was cleared — **54 744 lit vs 54 324 unlit**, so
 *    the face tint was ~420 px and the ghost smear was the other 54 000. It had
 *    swallowed the scope tint's whole language, and a `polygonOffset` only took
 *    it to 18 802: no depth bias resolves coplanar surfaces at that scale.
 *
 * So the copies are drawn as the seed's SILHOUETTE at each instance position.
 * It cannot smear over the body, it composes with any overlap (the row reads as
 * the stepped outline it will become), it stays legible at N copies where N
 * translucent solids become fog, and it is the same line-work idiom the gauge
 * itself is drawn in. The screenshot is what found this; no assertion in the
 * suite could see it, and the one that could was in a neighbouring spec.
 *
 * Pure arithmetic on plain tuples, no `three` and no stores, so the instance
 * list is unit-testable without a WebGL context.
 */
import type { Vec3 } from "@loft/design";

import type { Vec3 as WireVec3 } from "../api/parts";

/**
 * What the open pattern editor is currently describing, projected for the
 * viewport — the pattern twin of `ExtrudePreviewState`.
 *
 * It exists so the editor stays the one owner of the form and the viewport
 * never parses a text field. `null` when the form cannot be read as a row yet
 * (a half-typed count, a circular pattern), which is the viewport's cue to draw
 * nothing rather than to guess.
 */
export interface PatternPreviewState {
  /** TOTAL instances INCLUDING the seed, as the form means it. */
  count: number;
  /** Step between copies, canonical mm. */
  spacingMm: number;
  /** Row direction in the KERNEL's world frame (Z-up), as authored. */
  direction: WireVec3;
}

/**
 * KNOWN LIMIT, stated here rather than left for someone to rediscover: the
 * outline drawn is always the SEED BODY's, and a `features`-scoped pattern does
 * not always repeat the whole body.
 *
 * The common case is right. The default flow opens scoped to the tip
 * (`Extrude1`), and where that feature IS the body, its silhouette is exactly
 * the shape of a copy. The wrong case is a MODIFIER: a plate with one bore,
 * scoped to `Hole1`, becomes one plate with three bores, and three plate
 * outlines say something else.
 *
 * Deliberately NOT patched by suppressing the outline for every `features`
 * scope. That was tried and reverted: it trades the COMMON case — where the
 * drawing is correct and is this item's entire preview — to patch the rarer
 * one, and 8.4 is explicit that a verb whose drag moves a number and not the
 * model should not ship at all. The real fix draws the SCOPED FEATURE's own
 * faces, which needs the feature-face subset the selection layer owns: CRAFT-12
 * territory in W4, where this anchor is re-sourced anyway.
 *
 * ---
 *
 * Where the copies go, as translations from the seed body, in scene mm.
 *
 * Instances `1 … count − 1`: the seed is instance 0 and is the REAL body, which
 * is already on screen and must not be ghosted over — a translucent copy laid
 * exactly on committed metal would say the metal is pending.
 *
 * `dir` is expected to be a unit vector in the SCENE frame (`sceneDirection`).
 */
export function patternInstanceOffsets(
  count: number,
  spacingMm: number,
  dir: Vec3,
): Vec3[] {
  const copies = Math.max(0, Math.floor(count) - 1);
  const offsets: Vec3[] = [];
  for (let k = 1; k <= copies; k += 1) {
    offsets.push([
      dir[0] * spacingMm * k,
      dir[1] * spacingMm * k,
      dir[2] * spacingMm * k,
    ]);
  }
  return offsets;
}
