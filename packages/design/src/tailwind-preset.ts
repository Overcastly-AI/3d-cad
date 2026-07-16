/**
 * Tailwind preset derived FROM the TS token constants (`tokens.ts`) — the
 * DOM half of "one palette, two renderers". No hex literals here.
 */
import type { Config } from "tailwindcss";

import {
  color,
  duration,
  font,
  fontSize,
  layout,
  radius,
  spacing,
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
      },
      boxShadow: {
        /** Floating instrument panels lifting off the scene (token ground). */
        float: `0 2px 6px ${color.carbide}99, 0 12px 32px ${color.carbide}CC`,
      },
    },
  },
} satisfies Partial<Config>;

export default loftPreset;
