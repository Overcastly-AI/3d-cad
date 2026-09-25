/**
 * THE PATTERN GAUGES — two instruments on one feature (CRAFT-11).
 *
 * A `stepped` COUNT gauge along the row and a `linear` SPACING gauge across the
 * first gap, mounted on the two drafting rails {@link patternAnchor} lays out,
 * with the outline of every ghost copy standing on the count gauge's own rungs.
 * Why two and not one is argued in `patternAnchor.ts`; why the copies are line
 * work rather than translucent solids is argued in `patternGhost.ts` — that one
 * was got wrong first and the founder screenshot is what caught it. What is
 * left here is the mount.
 *
 * ## The tag is on the SPACING gauge, and the count gauge carries `tag: "none"`
 *
 * One of the two must be silent — two tags twenty millimetres apart carrying
 * different numbers is the "two dialects on screen" failure drawn literally
 * (direction §9). The count gauge is the one that can afford to be silent,
 * because **its value is the one you can see**: the ghosts ARE the count, they
 * stand on the rungs, and the answer to "how many?" is on screen as shapes you
 * can count. A spacing has no such reading — a 10 mm gap and a 12 mm gap look
 * identical, and the only way to know which you are holding is a number. So the
 * gauge whose quantity is undrawable keeps the tag, and the gauge that draws
 * its own quantity gives it up.
 *
 * It has a second consequence that settles the choice rather than merely
 * supporting it: `tag: "none"` also switches off that gauge's GLOBAL DIGIT
 * CAPTURE, and only one instrument on screen may own the digits. Typing `12`
 * into the pattern editor should mean spacing-or-count exactly once. It means
 * spacing, from the gauge; the count keeps the autofocused `pattern-count`
 * field it has always had (typing goes there because `useGlobalKeys` stands
 * down over a typing target), so neither number has lost a route in.
 *
 * **Neither field is removed.** W5's CRAFT-15/16 may merge the tag and the
 * panel field; until that is decided, a gauge that WRITES the existing field
 * composes with either outcome, and the gauge with no tag especially must not
 * be the only place its value lives.
 *
 * ## Circular patterns are not here
 *
 * A ring has no spacing and its count is not a distance along a direction, so
 * neither track describes it. Its handle is an ANGULAR track on the sweep —
 * CRAFT-10's instrument, on CRAFT-10's verb. Drawing a linear row's gauges on a
 * ring would be a control that lies, which is worse than a ring with no gauge.
 *
 * ## Resources
 *
 * The ghost's material, the seed's `EdgesGeometry` and the merged outline
 * buffer are built here and disposed here. **The body geometry is NOT ours** —
 * `ModelMesh` owns that object's lifetime and publishes `null` before disposing
 * it — so it is never disposed from this file, which is why the outline node
 * carries `dispose={null}` rather than being left to r3f's automatic teardown.
 */
import { formatLength, steppedTrack, linearTrack } from "@loft/design";
import { viewport } from "@loft/design/tokens";
import { useThree } from "@react-three/fiber";
import { useEffect, useMemo } from "react";
import {
  BufferAttribute,
  BufferGeometry,
  EdgesGeometry,
  LineBasicMaterial,
} from "three";

import { useDocumentLengthUnit } from "../units/documentUnit";
// The length-drag grammar — snap per document unit, the coarse multiplier, and
// what counts as the same length. Imported rather than re-picked: a spacing
// drag and a depth drag are both lengths under a pointer, and two opinions
// about how finely a length snaps would be two dialects (CLAUDE.md DRY rule).
import {
  COARSE_STEP_FACTOR,
  DEPTH_EPSILON_MM,
  keyStepMm,
} from "./extrudeHandle";
import { ParametricGauge } from "./ParametricGauge";
import {
  countSeat,
  MAX_PATTERN_COUNT,
  MAX_SPACING_MM,
  MIN_PATTERN_COUNT,
  MIN_SPACING_MM,
  spacingSeat,
  type PatternAnchor,
} from "./patternAnchor";
import { patternInstanceOffsets } from "./patternGhost";
import { useViewportPickStamp } from "./pickStamp";

/**
 * Draw order for the ghost outlines — under the gauge (12/13), over the body.
 *
 * Unlike the extrude ghost these keep DEPTH TESTING ON. An extrude ghost is a
 * sweep that happens INSIDE material, so it has to be an x-ray to be seen at
 * all; a pattern's copies stand in open space BESIDE the seed, and where a
 * close pitch does overlap the real body the honest read is the committed metal
 * in front and the pending copy behind it — a row that unions into one longer
 * bar then draws as the stepped outline it will actually become. Depth WRITING
 * stays off, as it must for anything translucent.
 */
const GHOST_RENDER_ORDER = 11;

export interface PatternGaugeLayerProps {
  /**
   * Where the row stands, in scene mm.
   *
   * A PROP, deliberately: this component never reaches into a pick or selection
   * store. CRAFT-12's persistent selection lands in W4 and will re-source this
   * value; taking it as a prop makes that a re-wiring at the integration point
   * instead of a rewrite here.
   */
  anchor: PatternAnchor;
  /** TOTAL instances INCLUDING the seed — the editor's own number. */
  count: number;
  /** Step between copies, canonical mm. */
  spacingMm: number;
  /** Ask the editor for a new count (contract β — it must echo it back). */
  onCountChange: (count: number) => void;
  /** Ask the editor for a new spacing, canonical mm. */
  onSpacingChange: (mm: number) => void;
  /**
   * The drawn body, for the ghost copies. `null` is "no raycast target / no
   * mesh", never "not loaded yet" — the count gauge's rungs still mark every
   * instance position, so the ladder degrades to line work rather than to
   * nothing.
   *
   * Pass `null` whenever the seed's silhouette would NOT be the shape of a
   * copy — see `PatternPreviewState.scope`.
   */
  bodyGeometry: BufferGeometry | null;
}

export function PatternGaugeLayer({
  anchor,
  count,
  spacingMm,
  onCountChange,
  onSpacingChange,
  bodyGeometry,
}: PatternGaugeLayerProps) {
  const invalidate = useThree((state) => state.invalidate);
  // Read here rather than injected, as `ExtrudePreview` reads it: the document
  // unit is ambient and the provider reaches inside the canvas. The ANCHOR is
  // the thing that must be a prop (see its note) — a unit is not a selection.
  const unit = useDocumentLengthUnit();

  // MEMOISED because the gauge derives its drawn form and its stop set from the
  // track: a track rebuilt every render would rebuild both, which is the
  // allocation in the render loop the viewport rules forbid. The count track
  // legitimately rebuilds while the SPACING is being dragged — its pitch and
  // its seat really do move — and that is once per pointermove, not per frame.
  const spacingTrack = useMemo(
    () =>
      linearTrack(spacingSeat(anchor), {
        min: MIN_SPACING_MM,
        max: MAX_SPACING_MM,
        snap: keyStepMm(unit),
        keyStep: keyStepMm(unit),
        coarseFactor: COARSE_STEP_FACTOR,
        epsilon: DEPTH_EPSILON_MM,
        format: (mm, opts) => formatLength(mm, unit, opts ?? {}),
      }),
    [anchor, unit],
  );
  const countTrack = useMemo(
    () =>
      steppedTrack(countSeat(anchor, spacingMm), {
        pitch: spacingMm,
        min: MIN_PATTERN_COUNT,
        max: MAX_PATTERN_COUNT,
      }),
    [anchor, spacingMm],
  );

  const offsets = useMemo(
    () => patternInstanceOffsets(count, spacingMm, anchor.dir),
    [count, spacingMm, anchor.dir],
  );

  const ghostMaterial = useMemo(() => {
    const material = new LineBasicMaterial({ color: viewport.preview.edge });
    material.transparent = true;
    material.opacity = viewport.preview.edgeOpacity;
    material.depthWrite = false;
    return material;
  }, []);
  useEffect(() => () => ghostMaterial.dispose(), [ghostMaterial]);

  // The seed's own silhouette, derived once per mesh. `EdgesGeometry` is a
  // render-time derivation from a mesh we already hold, not a B-rep
  // computation — the client still never computes geometry.
  const silhouette = useMemo(
    () => (bodyGeometry === null ? null : new EdgesGeometry(bodyGeometry)),
    [bodyGeometry],
  );
  useEffect(() => {
    if (silhouette === null) return;
    // OURS to dispose — `EdgesGeometry` is a new buffer. The mesh it was
    // derived from is NOT, and is never touched here.
    return () => silhouette.dispose();
  }, [silhouette]);

  // One buffer holding every copy's outline, so N copies cost one draw call.
  //
  // The two QA STAMPS are computed from THIS BUFFER, never from `count` and
  // `spacingMm`. A stamp of the input cannot fail when the picture stops
  // following it, which is the one failure the preview exists to prevent — and
  // an earlier probe here published `offsets.length`, which would have reported
  // a frozen drawing as a live one.
  //
  // TWO of them, because this verb has two quantities and ONE stamp cannot tell
  // them apart: adding a copy and moving the copies apart both change the same
  // drawing. `segments` counts what is drawn (it moves only when a copy is
  // added); `spanMm` measures how far the drawing reaches along the row (it
  // moves when the pitch changes). So "the spacing drag left the count alone"
  // is checkable against the picture instead of only against the field. This is
  // CRAFT-9b's perimeter lesson in a sharper form: a translating square has a
  // constant perimeter, and a stamp that cannot distinguish the two motions
  // passes while both of them happen.
  const ghosts = useMemo(() => {
    if (silhouette === null || offsets.length === 0) return null;
    const source = silhouette.getAttribute("position");
    const stride = source.count * 3;
    const out = new Float32Array(stride * offsets.length);
    let lo = Infinity;
    let hi = -Infinity;
    for (let copy = 0; copy < offsets.length; copy += 1) {
      const offset = offsets[copy];
      if (offset === undefined) continue;
      for (let i = 0; i < source.count; i += 1) {
        const at = copy * stride + i * 3;
        const x = source.getX(i) + offset[0];
        const y = source.getY(i) + offset[1];
        const z = source.getZ(i) + offset[2];
        out[at] = x;
        out[at + 1] = y;
        out[at + 2] = z;
        const along = x * anchor.dir[0] + y * anchor.dir[1] + z * anchor.dir[2];
        if (along < lo) lo = along;
        if (along > hi) hi = along;
      }
    }
    const geometry = new BufferGeometry();
    geometry.setAttribute("position", new BufferAttribute(out, 3));
    return {
      geometry,
      segments: (out.length / 3) >> 1,
      spanMm: Math.round((hi - lo) * 100) / 100,
    };
  }, [silhouette, offsets, anchor.dir]);
  useEffect(() => {
    if (ghosts === null) return;
    invalidate();
    return () => ghosts.geometry.dispose();
  }, [ghosts, invalidate]);
  useViewportPickStamp("patternGhostSegments", ghosts?.segments ?? null);
  useViewportPickStamp("patternGhostSpanMm", ghosts?.spanMm ?? null);

  return (
    <>
      {ghosts === null ? null : (
        <lineSegments
          geometry={ghosts.geometry}
          material={ghostMaterial}
          // NAMED because the preview is drawn in GL, where no DOM probe can
          // reach it. The numbers a spec reads are the two buffer-derived
          // stamps above, not anything hung on this node.
          name="pattern-ghosts"
          renderOrder={GHOST_RENDER_ORDER}
          // The copies sit outside the source mesh's bounds, so a cull computed
          // from them would drop copies that are plainly on screen.
          frustumCulled={false}
          dispose={null}
        />
      )}
      {/* THE COUNT GAUGE — far rail, silent tag. Its rungs are the ghosts. */}
      <ParametricGauge
        label="Pattern count"
        tagLabel="N"
        tag="none"
        gaugeId="pattern-count-gauge"
        value={count}
        onChange={onCountChange}
        track={countTrack}
        min={MIN_PATTERN_COUNT}
        max={MAX_PATTERN_COUNT}
      />
      {/* THE SPACING GAUGE — near rail, and the one that speaks. */}
      <ParametricGauge
        label="Pattern spacing"
        tagLabel="S"
        gaugeId="pattern-spacing-gauge"
        value={spacingMm}
        onChange={onSpacingChange}
        track={spacingTrack}
        min={MIN_SPACING_MM}
        max={MAX_SPACING_MM}
        tagUnit={unit}
      />
    </>
  );
}
