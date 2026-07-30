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
      },
      width: {
        inspector: px(layout.inspectorWidth),
        editor: px(layout.editorCardWidth),
      },
      inset: {
        /** HUD-card left anchor clearing the floating tree panel. */
        editor: px(layout.editorInset),
        /**
         * The bottom-centre HUD lane — a centred instrument stacked over the
         * view rail (`bottom-hud-lane`). See `layout.hudLaneBottom`.
         */
        "hud-lane": px(layout.hudLaneBottom),
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
