/**
 * Tailwind preset derived FROM the TS token constants (`tokens.ts`) — the
 * DOM half of "one palette, two renderers". No hex literals here.
 */
import type { Config } from "tailwindcss";
import plugin from "tailwindcss/plugin";

import {
  carriageTravelPercent,
  color,
  drawing,
  duration,
  font,
  fontSize,
  layout,
  progress,
  radius,
  spacing,
  target,
  viewCube,
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
        /** Square host of the reference cube — see `viewCube.size`. */
        "view-cube": px(viewCube.size),
        /** The indeterminate carriage's bed — see `progress.trackHeight`. */
        track: px(progress.trackHeight),
      },
      width: {
        inspector: px(layout.inspectorWidth),
        editor: px(layout.editorCardWidth),
        /** Caption column of a dense `FieldRow` — see `layout.fieldLabelWidth`. */
        "field-label": px(layout.fieldLabelWidth),
        /** Square host of the reference cube — see `viewCube.size`. */
        "view-cube": px(viewCube.size),
        /** The indeterminate carriage's share of its bed — see `progress`. */
        carriage: `${progress.carriage}%`,
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
        /**
         * The indeterminate carriage's bed. A MINIMUM rather than a width so
         * the bed can still take the slack of the line it sits in, but can
         * never collapse: its only child is absolutely positioned, so its
         * content width is 0 and a missing width makes the whole progressbar
         * measure as hidden. See `progress.bedWidth`.
         */
        progress: px(progress.bedWidth),
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
        /**
         * The reference cube's own seat (`bottom-view-cube right-view-cube`).
         * Derived so the block's centre lands on `viewCube.margin` from both
         * edges — the placement the founder's 2026-07-31 capture settled — with
         * the host's size and the chrome's clearance coming from the SAME
         * numbers. Nothing here is transcribed.
         */
        "view-cube": px(viewCube.inset),
      },
      maxWidth: {
        /** The bounded page-level sheet — see `layout.sheetWidth`. */
        sheet: px(layout.sheetWidth),
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
      /**
       * THE CARRIAGE TRAVERSING ITS BED — the one motion an indeterminate wait
       * is allowed (`ProgressTrack`). Both the distance and the period are
       * DERIVED from `progress` in tokens.ts, so the carriage's width and its
       * travel cannot drift apart the way a transcribed `357%` would.
       *
       * Consumed as `motion-safe:animate-travel`, never bare: under
       * `prefers-reduced-motion` the carriage holds still and the elapsed
       * readout carries the liveness instead.
       */
      keyframes: {
        travel: {
          "0%": { transform: "translateX(0)" },
          "100%": {
            transform: `translateX(${carriageTravelPercent.toFixed(4)}%)`,
          },
        },
      },
      animation: {
        travel: `travel ${progress.travelMs}ms cubic-bezier(0.45, 0, 0.55, 1) infinite alternate`,
      },
      /** Named page-level stacking layers (`z-overlay` … `z-menu`) — see
          `zLayer` in tokens.ts. Page-level contexts use these, never bare
          numbers, so paint order is one audited scale. */
      zIndex: Object.fromEntries(
        Object.entries<number>(zLayer).map(([k, v]) => [k, String(v)]),
      ) as Record<keyof typeof zLayer, string>,
    },
  },
  plugins: [
    /**
     * `scrollbar-instrument` — the scribed scrollbar every clamped panel body
     * wears (`ScrollRegion`). A defect this repo has now paid for three times
     * (AUDIT-PRODUCT T-18) is a panel that silently truncates: with the
     * platform's overlay scrollbars, an `overflow-y-auto` region that is
     * hiding four sections looks exactly like one that has nothing more to
     * show. So the bar is ALWAYS drawn while the region overflows, slim and
     * square-cornered in the panel's own ink — an instrument, not a widget.
     *
     * Both engines, from the same tokens: the standard `scrollbar-width` /
     * `scrollbar-color` pair (Firefox) and the WebKit pseudo-elements, which
     * Chromium still needs for the square corners and the exact width.
     */
    plugin(({ addUtilities }) => {
      addUtilities({
        ".scrollbar-instrument": {
          "scrollbar-width": "thin",
          "scrollbar-color": `${color.etch} ${color.anvil}`,
          "&::-webkit-scrollbar": { width: px(spacing["1.5"]) },
          "&::-webkit-scrollbar-track": {
            background: color.anvil,
            "border-left": `1px solid ${color.hairline}`,
          },
          "&::-webkit-scrollbar-thumb": {
            background: color.etch,
            "border-radius": "0",
          },
          "&::-webkit-scrollbar-thumb:hover": { background: color.gauge },
        },
      });
    }),
  ],
} satisfies Partial<Config>;

export default loftPreset;
