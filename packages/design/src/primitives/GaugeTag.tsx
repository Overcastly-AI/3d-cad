import type { HTMLAttributes } from "react";

import { cx } from "../cx";
import { color } from "../tokens";
import type { GaugeTagPlacement } from "../gauge";
import {
  DimensionTag,
  DimensionTagCell,
  type DimensionTagCellProps,
} from "./DimensionTag";

/**
 * THE GAUGE'S TAG — the number a manipulator is currently asserting, written on
 * the work and tied to the grip by a leader.
 *
 * ## What it is, in the app's own grammar
 *
 * The workspace has four ways of telling you something, and a gauge is the
 * fourth:
 *
 *  · brass + leader + `Kbd` = an offer you can take right now. (`ProposalNote`)
 *  · mist + no leader + no `Kbd` = a name for what is under the pointer.
 *  · band cell + eyebrow + `×` = a held state that renames verbs.
 *  · **brass line-work + grip + graduations = a value you can pull.** (this)
 *
 * So this is deliberately NOT a fifth vocabulary. It is {@link DimensionTag} —
 * the drafting strip the sketcher already uses, terse caps label in the display
 * face, value in the data face, unit written once for the strip — hung on
 * {@link ProposalNote}'s leader. Every colour, face and rule is one the
 * workspace already speaks; the only new thing is the pairing, which is the
 * point: a number that belongs to a thing on screen is drawn ATTACHED to it.
 *
 * ## Why the leader is the part worth building
 *
 * MEASURED before this existed: the extrude gauge's tag was placed by a bare
 * CSS offset (`-translate-y-8 translate-x-4`) and floated unattached — `D 10 mm`
 * hanging in space with no tie to the arrow it describes. At that point the tag
 * is a HUD chip that happens to be near some geometry, which is idiom B wearing
 * brass; anything else on screen could equally be its subject. A leader makes
 * the claim explicit and costs one hairline: the anchor dot marks the exact
 * point the number is about, the two-tone stub ties the strip to it, and a flip
 * at the frame edge drags the stub with it.
 *
 * TWO-TONE, exactly as `ProposalNote`'s leader and `PickNode`'s reticle, and
 * for the gauge this is load-bearing rather than styling: a single brass
 * hairline reads on the dark bench and all but vanishes over a lit aluminium
 * face, which is precisely where a manipulator spends its life. Dark casing
 * down first, brass core on top, so the line survives either ground.
 *
 * ## The two cells, and why they are one strip
 *
 * A hole has a depth AND a diameter, and two tags twenty millimetres apart
 * carrying different numbers is the "two dialects drawn on screen" failure
 * literally. {@link GaugeTagProps.cells} therefore takes one or two cells on ONE
 * strip, divided by the same hairline rule a title block divides its cells
 * with — `D 12 · Ø 6 mm`, the way it would be written on a drawing.
 *
 * ## Readout and input are the same cell
 *
 * `DimensionTagCell` already renders both states and the number does not move
 * between them, so the value you watched form under the pointer is the value
 * you type over. Pass `readout` while the pointer owns the number; pass
 * `value`/`onChange` when the caret is in it. There is nothing here to switch
 * on — the cell decides from its own props.
 *
 * ## Motion
 *
 * None, deliberately. No fade-in, no pulse, no spring: the surrounding
 * components have no entry animation either, and a manipulator that animates
 * into place is a manipulator that is not where you left it. That is why
 * `prefers-reduced-motion` needs no new code here — there is no motion to
 * reduce, rather than an omission nobody considered.
 */
export interface GaugeTagProps extends Omit<
  HTMLAttributes<HTMLDivElement>,
  "children"
> {
  /** Unit written once at the end of the strip — e.g. "mm". Omit for an angle. */
  unit?: string;
  /**
   * The value cells, left to right. One for most gauges; a second (the
   * `companion`) for the gauge that drives two numbers from one instrument.
   */
  cells: readonly [DimensionTagCellProps, DimensionTagCellProps?];
  /**
   * Where the strip sits relative to the grip, and where its leader runs —
   * from {@link placeGaugeTag}. OMIT IT and the tag renders in normal flow with
   * no leader at all, which is what a caller positioning the strip by its own
   * CSS wants; the leader is an opt-in, not a default, because a leader drawn
   * from the wrong origin points confidently at nothing.
   */
  placement?: GaugeTagPlacement;
}

export function GaugeTag({
  unit,
  cells,
  placement,
  className,
  ...rest
}: GaugeTagProps) {
  const [primary, companion] = cells;
  const strip = (
    <DimensionTag
      // Spread conditionally rather than `unit={unit}`: under
      // `exactOptionalPropertyTypes` an explicit `undefined` is not the same as
      // an absent property, and an angular gauge legitimately has no suffix
      // cell to write (the degree sign travels with the number).
      {...(unit !== undefined ? { unit } : {})}
      className={cx("whitespace-nowrap", className)}
      {...rest}
    >
      <DimensionTagCell {...primary} />
      {companion !== undefined ? <DimensionTagCell {...companion} /> : null}
    </DimensionTag>
  );

  if (placement === undefined) return strip;

  return (
    <div className="pointer-events-none relative">
      {/*
        The leader. `width`/`height` of 1 with `overflow: visible` rather than a
        frame-sized canvas: this SVG's origin IS the grip (drei `Html` anchors
        its container there), so the placement's numbers can be drawn as given,
        and a leader running up and to the left is simply negative. A
        frame-sized SVG would need the grip's screen position, which is exactly
        the thing the container already knows and the component should not have
        to ask for.
      */}
      <svg
        aria-hidden
        width={1}
        height={1}
        className="absolute left-0 top-0 text-brass"
        style={{ overflow: "visible", pointerEvents: "none" }}
        data-testid="gauge-tag-leader"
      >
        <line
          x1={placement.leader.x1}
          y1={placement.leader.y1}
          x2={placement.leader.x2}
          y2={placement.leader.y2}
          stroke={color.carbide}
          strokeWidth={3}
          strokeLinecap="round"
          opacity={0.55}
        />
        <line
          x1={placement.leader.x1}
          y1={placement.leader.y1}
          x2={placement.leader.x2}
          y2={placement.leader.y2}
          stroke="currentColor"
          strokeWidth={1.25}
          strokeLinecap="round"
        />
        {/* The anchor: the exact point this number is about. */}
        <circle
          cx={placement.leader.x1}
          cy={placement.leader.y1}
          r={3.5}
          fill={color.carbide}
          opacity={0.7}
        />
        <circle
          cx={placement.leader.x1}
          cy={placement.leader.y1}
          r={2}
          fill="currentColor"
        />
      </svg>
      <div
        className="absolute"
        style={{ left: placement.tag.left, top: placement.tag.top }}
        data-gauge-tag-side={placement.side}
      >
        {strip}
      </div>
    </div>
  );
}
