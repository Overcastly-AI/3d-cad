/**
 * Loft icon set — hand-drawn, single-grid, inline SVG. NO external asset
 * requests (the prod CSP forbids them) and NO icon dependency: every glyph is
 * a React component that renders inline paths.
 *
 * House style is "scribed", not "sketched": a 24-unit grid, 1.6 stroke,
 * SQUARE caps and MITER joins, `currentColor` throughout. Square-cap/miter is
 * the deliberate anti-default choice — the ubiquitous Feather/Lucide look is
 * round-cap, and it would read as generic here; scribed strokes tie the icons
 * to the "scribe line" language of the token system and the title-block
 * signature. Because the ink is `currentColor`, the active (brass) state flows
 * straight from the button's text color — one palette, no per-icon color.
 *
 * The set is deliberately CAD-specific: the constraint and feature glyphs are
 * drawn from engineering-drawing notation (dimension lines, the fixed/ground
 * support, the bullseye for concentric), not repurposed office icons.
 */
import type { SVGProps } from "react";

export interface IconProps extends SVGProps<SVGSVGElement> {
  /** Square edge length in px (default 16 — the dense toolbar target). */
  size?: number;
}

/** Shared frame: fixed grid, scribed stroke, no fill. */
function Icon({ size = 16, children, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="square"
      strokeLinejoin="miter"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  );
}

/** A small defining node (endpoint / center) — the scribe's punch mark. */
function Node({ cx, cy }: { cx: number; cy: number }) {
  return <circle cx={cx} cy={cy} r={1.4} fill="currentColor" stroke="none" />;
}

// --- Sketch tools -----------------------------------------------------------

export const LineIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 19 L19 5" />
    <Node cx={5} cy={19} />
    <Node cx={19} cy={5} />
  </Icon>
);

export const RectIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x={5} y={7} width={14} height={10} />
  </Icon>
);

export const CircleIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx={12} cy={12} r={7} />
    <Node cx={12} cy={12} />
  </Icon>
);

export const ArcIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 18 A 13 13 0 0 1 18 5" />
    <Node cx={5} cy={18} />
    <Node cx={18} cy={5} />
  </Icon>
);

// --- Geometric constraints --------------------------------------------------

export const HorizontalIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 12 H19" />
    <Node cx={5} cy={12} />
    <Node cx={19} cy={12} />
  </Icon>
);

export const VerticalIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 5 V19" />
    <Node cx={12} cy={5} />
    <Node cx={12} cy={19} />
  </Icon>
);

export const ParallelIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M8 19 L13 5" />
    <path d="M13 19 L18 5" />
  </Icon>
);

export const PerpendicularIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M7 4 V17 H20" />
    <path d="M7 13 H11 V17" />
  </Icon>
);

export const TangentIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx={9} cy={14} r={5} />
    <path d="M3 7 L21 7" />
  </Icon>
);

// --- Dimensional constraints ------------------------------------------------

export const DistanceIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 7 V17" />
    <path d="M19 7 V17" />
    <path d="M5 12 H19" />
    <path d="M5 12 L8 10 M5 12 L8 14" />
    <path d="M19 12 L16 10 M19 12 L16 14" />
  </Icon>
);

export const RadiusIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx={12} cy={12} r={7} />
    <path d="M12 12 L18.5 8" />
    <path d="M18.5 8 L15.7 8 M18.5 8 L17.4 10.6" />
    <Node cx={12} cy={12} />
  </Icon>
);

export const EqualIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 9 H18" />
    <path d="M6 15 H18" />
  </Icon>
);

// --- Relational constraints -------------------------------------------------

export const CoincidentIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx={9.5} cy={12} r={4.5} />
    <circle cx={14.5} cy={12} r={4.5} />
  </Icon>
);

export const ConcentricIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx={12} cy={12} r={7.5} />
    <circle cx={12} cy={12} r={3.5} />
    <Node cx={12} cy={12} />
  </Icon>
);

export const SymmetricIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 3 V21" strokeDasharray="2.4 2" />
    <path d="M5 8 L9 12 L5 16" />
    <path d="M19 8 L15 12 L19 16" />
  </Icon>
);

/** Fixed = the statics "ground/fixed support" — a datum the geometry pins to. */
export const FixedIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 4 V12" />
    <path d="M5 12 H19" />
    <path d="M6 15 L9 12 M10 15 L13 12 M14 15 L17 12" />
    <Node cx={12} cy={4} />
  </Icon>
);

// --- Construction toggle ----------------------------------------------------

export const ConstructionIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 18 L20 6" strokeDasharray="2.6 2.2" />
    <Node cx={4} cy={18} />
    <Node cx={20} cy={6} />
  </Icon>
);

// --- Features ---------------------------------------------------------------

/** Sketch = a scribe on a datum plane (the parallelogram is the sheet). */
export const SketchIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 9 L14 9 L20 15 L10 15 Z" />
    <path d="M8 12.6 L16 11.4" />
    <Node cx={8} cy={12.6} />
  </Icon>
);

/** Extrude = a profile face pushed along its normal into a solid. */
export const ExtrudeIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x={5} y={11} width={9} height={9} />
    <path d="M5 11 L9 7 H18 L14 11" />
    <path d="M14 11 L18 7 V16 L14 20" />
    <path d="M17 5 V2 M17 2 L15.6 3.4 M17 2 L18.4 3.4" />
  </Icon>
);

/** Revolve = a profile swept about an axis (dashed) with a turn arrow. */
export const RevolveIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 3 V21" strokeDasharray="2.4 2" />
    <rect x={9} y={9} width={5} height={6} />
    <path d="M9 9 A 9 6 0 0 1 20 8" />
    <path d="M20 8 L17.6 7.2 M20 8 L19.4 10.3" />
  </Icon>
);

// --- Chrome -----------------------------------------------------------------

export const CaretDownIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 9 L12 15 L18 9" />
  </Icon>
);

export const CheckIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 12 L10 17 L19 6" />
  </Icon>
);

export const CloseIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 6 L18 18" />
    <path d="M18 6 L6 18" />
  </Icon>
);
