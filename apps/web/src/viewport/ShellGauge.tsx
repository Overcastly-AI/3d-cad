/**
 * THE SHELL THICKNESS GAUGE — the extrude instrument, mounted on a picked face
 * (CRAFT-9b).
 *
 * Everything that makes this a manipulator rather than a drawing lives in
 * {@link ParametricGauge} (CRAFT-8/7): the ask-queue, the hit sleeve, key
 * stepping, the digit handoff, nested Escape, the tag-as-input. Everything
 * about WHERE it stands lives in `faceAnchor.ts`. What is left here is the only
 * part that is genuinely about SHELL — that a wall thickness is a length in the
 * document's unit, that it runs into the material, and what the drag is a
 * picture of.
 *
 * ## THE PREVIEW IS ROUTE (b) — the inner offset outline (direction §8.4)
 *
 * The rule the direction pass sets is that a gauge whose drag changes a number
 * and not the model is *worse* than the form it replaces, because it promises
 * direct manipulation and delivers a slider. So the drag draws the rim of the
 * cavity the thickness leaves: the picked face's boundary contracted by the
 * wall, mitred at every corner, redrawn on every value.
 *
 * It is line-work rather than a translucent solid ghost, and that is a choice
 * with a reason beyond cost. A shelled body is a body with its INSIDE removed,
 * so a ghosted SOLID would paint material exactly where the feature is about to
 * take material away — the same inversion the extrude preview had to fix when
 * a CUT was drawn as a proud brass boss (`viewport.preview.cut`'s note). An
 * outline claims nothing about volume; it states one distance, which is the one
 * the gauge is setting.
 *
 * The outline is drawn as a screen-space ribbon (`HighlightLines`), not a GL
 * line, because it is numerically coincident with the face it lies on and a
 * 1 px `lineBasicMaterial` at equal depth is DISCARDED rather than dimmed —
 * SEL-8's measurement, 13 changed pixels out of 1,363,200.
 */
import {
  formatLength,
  linearTrack,
  type GaugeSeat,
  type GaugeTrack,
  type LengthUnit,
} from "@loft/design";
import { viewport } from "@loft/design/tokens";
import { useThree } from "@react-three/fiber";
import { useEffect, useMemo } from "react";

import { useDocumentLengthUnit } from "../units/documentUnit";
import {
  COARSE_STEP_FACTOR,
  DEPTH_EPSILON_MM,
  keyStepMm,
  SNAP_MM,
} from "./extrudeHandle";
import {
  drawnLength,
  insetOutline,
  MAX_THICKNESS_MM,
  MIN_THICKNESS_MM,
  type ShellAnchor,
} from "./faceAnchor";
import { HighlightLines } from "./overlaySegments";
import { ParametricGauge } from "./ParametricGauge";
import { useViewportPickStamp } from "./pickStamp";

export interface ShellGaugeProps {
  /**
   * Where the instrument stands. A VALUE, never a store read — see
   * `faceAnchor.ts`'s note on why W4's selection store must be a re-wiring of
   * this component rather than a rewrite of it.
   */
  anchor: ShellAnchor;
  /** The editor's current wall thickness, canonical mm. */
  thicknessMm: number;
  /** Report a new thickness in canonical mm (the editor owns the value). */
  onChange: (mm: number) => void;
}

/**
 * The shell gauge's arithmetic: a length along the inward normal.
 *
 * The snap grammar is the EXTRUDE's, imported rather than re-picked — one
 * length-snap per document unit across every gauge in the product, or the same
 * gesture means two things two commands apart (CLAUDE.md DRY rule). What the
 * drag actually snaps to is the drawn ladder anyway (§3.1); this is the floor
 * for the zoom at which no ladder is legible.
 */
export function shellTrack(seat: GaugeSeat, unit: LengthUnit): GaugeTrack {
  return linearTrack(seat, {
    min: MIN_THICKNESS_MM,
    max: MAX_THICKNESS_MM,
    snap: SNAP_MM[unit],
    keyStep: keyStepMm(unit),
    coarseFactor: COARSE_STEP_FACTOR,
    epsilon: DEPTH_EPSILON_MM,
    format: (mm, opts) => formatLength(mm, unit, opts ?? {}),
  });
}

export function ShellGauge({ anchor, thicknessMm, onChange }: ShellGaugeProps) {
  const unit = useDocumentLengthUnit();
  const invalidate = useThree((state) => state.invalidate);

  // MEMOISED, and load-bearing rather than tidy: the stop set and the drawn
  // form are derived from the track, so a track rebuilt every render rebuilds
  // both on every frame of a drag — the allocation in the render loop the
  // viewport rules forbid.
  const track = useMemo(
    () => shellTrack(anchor.seat, unit),
    [anchor.seat, unit],
  );
  const outline = useMemo(
    () => insetOutline(anchor, thicknessMm),
    [anchor, thicknessMm],
  );

  // frameloop="demand": the preview only moves when the value does, so ask for
  // the frame that shows it.
  useEffect(() => {
    invalidate();
  }, [outline, invalidate]);

  /**
   * The QA stamp is the DRAWN outline's perimeter, not the thickness that
   * produced it. A stamp of the input cannot fail when the picture stops
   * following, which is the one failure this item exists to prevent.
   */
  useViewportPickStamp(
    "shellPreviewPerimeterMm",
    outline.length === 0 ? null : Math.round(drawnLength(outline) * 100) / 100,
  );

  return (
    <>
      {outline.length > 0 ? (
        <group name="shell-inner-offset">
          <HighlightLines
            positions={outline}
            color={viewport.preview.edge}
            widthPx={viewport.facePick.hoverEdgeWidthPx}
            xrayOpacity={viewport.facePick.hoverEdgeXrayOpacity}
            renderOrder={11}
          />
        </group>
      ) : null}
      <ParametricGauge
        label="Shell thickness"
        tagLabel="T"
        gaugeId="shell-thickness"
        value={thicknessMm}
        onChange={onChange}
        track={track}
        min={MIN_THICKNESS_MM}
        max={MAX_THICKNESS_MM}
        tagUnit={unit}
      />
    </>
  );
}
