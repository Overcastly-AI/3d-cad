/**
 * Tailwind preset derived FROM the TS token constants (`tokens.ts`) — the
 * DOM half of "one palette, two renderers". No hex literals here.
 */
import type { Config } from "tailwindcss";

import {
  color,
  drawing,
  duration,
  font,
  fontSize,
  layout,
  radius,
  spacing,
  target,
  zLayer,
} from "./tokens";

const px = (n: number): string => `${n}px`;

const mapPx = <K extends string>(scale: Record<K, number>): Record<K, string> =>
  Object.fromEntries(
    Object.entries<number>(scale).map(([k, v]) => [k, px(v)]),
  ) as Record<K, string>;

const ms = <K extends string>(scale: Record<K, number>): Record<K, string> =>
  Object.fromEntries(
    Object.entries<number>(scale).map(([k, v]) => [k, `${v}ms`]),
  ) as Record<K, string>;

export const loftPreset = {
  theme: {
    // Closed palettes on purpose: only token values exist in the DOM theme.
    colors: {
      transparent: "transparent",
      current: "currentColor",
      carbide: color.carbide,
      anvil: color.anvil,
      hairline: color.hairline,
      etch: color.etch,
      mist: color.mist,
      gauge: color.gauge,
      brass: color.brass,
      "brass-hover": color.brassHover,
      aluminum: color.aluminum,
      flag: color.flag,
      // Drawing surface (the paper-on-the-bench signature): the sheet chrome
      // that lives in the DOM (title-block text, view labels) draws from the
      // same source as the SVG edge renderer.
      paper: drawing.paper,
      "paper-edge": drawing.paperEdge,
      ink: drawing.ink,
      "ink-label": drawing.label,
    },
    fontFamily: {
      display: font.display,
      body: font.body,
      data: font.data,
    },
    fontSize: mapPx(fontSize),
    spacing: mapPx(spacing),
    borderRadius: mapPx(radius),
    transitionDuration: ms(duration),
    extend: {
      height: {
        toolbar: px(layout.toolbarHeight),
        band: px(layout.commandBandHeight),
        timeline: px(layout.timelineHeight),
      },
      width: {
        inspector: px(layout.inspectorWidth),
        editor: px(layout.editorCardWidth),
      },
      /**
       * The written TARGET-SIZE policy as utilities (`min-h-target`,
       * `min-w-target-dense`, …) — see `target` in tokens.ts. Named rather than
       * spelled `min-h-6` at each site so the floor is one decision that can be
       * audited, and so a reviewer sees the intent rather than a number.
       */
      minHeight: {
        target: px(target.comfortable),
        "target-dense": px(target.dense),
        /** Floor for a panel sharing a chrome rail — see `layout.railPanelFloor`. */
        "rail-panel": px(layout.railPanelFloor),
      },
      minWidth: {
        target: px(target.comfortable),
        "target-dense": px(target.dense),
      },
      inset: {
        /** HUD-card left anchor clearing the floating tree panel. */
        editor: px(layout.editorInset),
        /**
         * The bottom-centre HUD lane — a centred instrument stacked over the
         * view rail (`bottom-hud-lane`). See `layout.hudLaneBottom`.
         */
        "hud-lane": px(layout.hudLaneBottom),
        /**
         * The in-canvas reference cube's band (`bottom-cube-band`) — the same
         * clearance `max-h-cube-card` expresses as a clamp, as an ANCHOR. A
         * chrome rail spans `top-3 bottom-cube-band`, which gives the column a
         * DEFINITE height: without one, a flex child's percentage basis or cap
         * resolves against an indefinite height and silently falls back to
         * content size — measured, that let the feature tree's 591px of content
         * squeeze the open editor by 71px and scroll its Operation row out of
         * sight.
         */
        "cube-band": px(layout.referenceCubeBand),
      },
      maxHeight: {
        /**
         * Clamp for a card anchored at `top-3`: capped so the bottom HUD lane
         * (view rail + centred instruments) stays reachable, with the card's
         * own body scrolling instead of growing off-frame. Every floating
         * panel and feature editor uses this — no editor can outgrow the
         * frame as verbs keep landing (UI-REVIEW 2026-07-30 P1).
         */
        "hud-card": `calc(100% - ${px(layout.cardInset + layout.hudLaneBottom)})`,
        /** As `hud-card`, but also clearing the in-canvas reference cube. */
        "cube-card": `calc(100% - ${px(layout.cardInset + layout.referenceCubeBand)})`,
        /**
         * Clamp for a feature editor DOCKED in a chrome rail: everything the
         * column has, less the gap and the floor its co-resident panel keeps
         * (`layout.railPanelFloor`). Derived, not guessed — a 60 % rule fitted
         * the 1600x1000 frame and clipped the extrude card's Save row by 26 px
         * at 1280x800, because a percentage does not know what the panel below
         * it needs. This does, at every height.
         */
        "rail-card": `calc(100% - ${px(spacing["2"] + layout.railPanelFloor)})`,
      },
      boxShadow: {
        /** Floating instrument panels lifting off the scene (token ground). */
        float: `0 2px 6px ${color.carbide}99, 0 12px 32px ${color.carbide}CC`,
      },
      /** Named page-level stacking layers (`z-overlay` … `z-menu`) — see
          `zLayer` in tokens.ts. Page-level contexts use these, never bare
          numbers, so paint order is one audited scale. */
      zIndex: Object.fromEntries(
        Object.entries<number>(zLayer).map(([k, v]) => [k, String(v)]),
      ) as Record<keyof typeof zLayer, string>,
    },
  },
} satisfies Partial<Config>;

export default loftPreset;
