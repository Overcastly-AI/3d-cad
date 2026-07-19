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

/** Flat pattern — a cut blank with a dashed fold line down the middle (the
 * sheet-metal unfold: the shop's flat cut, scored where it bends). */
export const FlatPatternIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x={4} y={7} width={16} height={10} />
    <path d="M12 6 L12 18" strokeDasharray="2.4 1.6" />
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

/**
 * Spline = a free-form interpolant threaded through its fit points. The scribe
 * flows an S-curve that PASSES THROUGH three punch nodes — the "interpolating,
 * through every point" behaviour the tool has — distinct from the Arc's single
 * two-node sweep. Same node vocabulary as Line/Arc, so it reads as one of the
 * draw tools.
 */
export const SplineIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 18 C 6 9, 9 9, 12 12 S 18 16, 20 6" />
    <Node cx={4} cy={18} />
    <Node cx={12} cy={12} />
    <Node cx={20} cy={6} />
  </Icon>
);

// --- Modify sketch (clean-up) -----------------------------------------------

/**
 * Trim = cut at intersection: a scribe line crossed by a second curve, the
 * far segment struck through with the "delete" hatch. The X mark reads as
 * "this piece goes" — the standard cut-at-intersection gesture, in the
 * title-block hatch idiom rather than a generic scissors.
 */
export const TrimIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 15 H20" />
    <path d="M12 5 V19" />
    <path d="M14 12 L18 12 M15 10 L17 14 M17 10 L15 14" />
    <Node cx={4} cy={15} />
  </Icon>
);

/**
 * Extend = grow to meet: a short scribe with an arrow reaching its support
 * line up to a barrier wall (the vertical stop it lands on). The arrow into
 * the wall says "lengthen until it meets", the mirror of trim.
 */
export const ExtendIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 12 H15" />
    <path d="M15 12 L11.5 9 M15 12 L11.5 15" />
    <path d="M19 5 V19" />
    <Node cx={4} cy={12} />
  </Icon>
);

/**
 * Offset = a parallel copy at a set distance: the source scribe and its
 * companion line, bridged by a dimension line with arrowheads at both ends —
 * the gap the user sets. The dimension-line bridge (not a generic "duplicate"
 * arrow) reads as "parallel curve at this distance", the rib/web/wall gesture.
 */
export const OffsetIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 7 H20" />
    <path d="M4 17 H20" />
    <path d="M9 7 V17" />
    <path d="M7 9 L9 7 L11 9" />
    <path d="M7 15 L9 17 L11 15" />
    <Node cx={4} cy={7} />
  </Icon>
);

/**
 * Mirror = reflect across a centerline: a dashed axis with an L-bend scribe on
 * the left and its mirror image on the right — one shape flipped about the
 * line. The dashed axis (the construction centerline this pairs with) plus a
 * true reflected copy reads as "add the symmetric half", distinct from the
 * Symmetric CONSTRAINT glyph (arrows tying two points), because Mirror creates
 * geometry rather than relating existing points.
 */
export const MirrorIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 3 V21" strokeDasharray="2.4 2" />
    <path d="M8 6 V14 H4" />
    <path d="M16 6 V14 H20" />
    <Node cx={4} cy={14} />
    <Node cx={20} cy={14} />
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

export const AngleIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 18 H19" />
    <path d="M5 18 L18 7" />
    <path d="M5 18 A8 8 0 0 1 10.5 11" />
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

/**
 * Sweep = a closed profile section carried along an open path. A small square
 * (the profile) sits at the tail of a curved trajectory that arcs up-and-away
 * with an arrowhead — the section follows the path. Its square section ties it
 * to the same title-block vocabulary the extrude/revolve glyphs speak.
 */
export const SweepIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x={3} y={13} width={6} height={6} />
    <path d="M6 16 C 6 8 14 6 20 6" />
    <path d="M20 6 L17.4 4.9 M20 6 L18.3 8.5" />
  </Icon>
);

/**
 * Loft = a solid skinned THROUGH stacked cross-sections. Two parallel section
 * ellipses (a wide base, a narrower top) joined by ruling lines into a frustum
 * silhouette, with a punch-mark node on each section — the "blend spine"
 * signature the loft editor extends. Its parallel-section vocabulary ties it to
 * the extrude face and the datum quad; the ruling lines say "skinned in order".
 */
export const LoftIcon = (p: IconProps) => (
  <Icon {...p}>
    <ellipse cx={12} cy={18} rx={7} ry={2.2} />
    <ellipse cx={12} cy={6} rx={4} ry={1.4} />
    <path d="M5 18 L8 6 M19 18 L16 6" />
    <Node cx={12} cy={18} />
    <Node cx={12} cy={6} />
  </Icon>
);

/**
 * Datum = a construction plane parallel to a base datum, held off it by an
 * offset. A dashed base quad (the origin datum) with a solid parallel quad
 * above it and a short offset tick between — the "sketch on a plane at a
 * height" glyph, in the same parallelogram vocabulary the extrude face speaks.
 */
export const DatumIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3 17 L9 13 H21 L15 17 Z" strokeDasharray="2.4 2" />
    <path d="M3 9 L9 5 H21 L15 9 Z" />
    <path d="M12 15 V7" strokeDasharray="1.5 1.5" />
  </Icon>
);

// --- Modify features --------------------------------------------------------

/** Fillet = a rounded inner corner (the radius arc rounds the vertex). */
export const FilletIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 4 V12 A7 7 0 0 0 13 19 H20" />
    <path d="M6 19 H20 M6 19 V4" strokeDasharray="2.4 2" />
  </Icon>
);

/** Chamfer = a beveled (flat-cut) corner — the anti-fillet, a straight facet. */
export const ChamferIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 4 V12 L13 19 H20" />
    <path d="M6 19 H20 M6 19 V4" strokeDasharray="2.4 2" />
  </Icon>
);

/**
 * Shell = the solid hollowed to a uniform wall with an OPEN top — the housing /
 * enclosure primitive. An isometric box whose top rim is drawn twice (outer +
 * an inset inner rim): the gap between the two rims IS the wall thickness, and
 * the open mouth reads as "material scooped out, this face left open". Its box
 * vocabulary ties it to the extrude solid; the double rim is the thing no other
 * feature glyph shows, so it says "hollow wall", not "cut".
 */
export const ShellIcon = (p: IconProps) => (
  <Icon {...p}>
    {/* The outer open mouth (top rim of the box). */}
    <path d="M4 8 L12 4 L20 8 L12 12 Z" />
    {/* The inner mouth — inset by the wall thickness (the reveal). */}
    <path d="M7.5 8 L12 6 L16.5 8 L12 10 Z" />
    {/* Outer walls dropping to the base + the near vertical edge. */}
    <path d="M4 8 V15 L12 19 L20 15 V8" />
    <path d="M12 12 V19" />
  </Icon>
);

/**
 * Draft = the mold-release taper — a wall tilted off a fixed parting plane so
 * the part pulls cleanly from a die. A trapezoid whose TOP NARROWS (the tapered
 * wall) rises from a dashed neutral/parting plane (the fixed line the faces
 * rotate about), with a short arrow off the top marking the pull direction (out
 * of the mold). The slanted walls ARE the draft angle; the dashed parting line
 * is the thing no other glyph shows, so it reads as "taper for release", never a
 * corner bevel (chamfer) or a hollow (shell).
 */
export const DraftIcon = (p: IconProps) => (
  <Icon {...p}>
    {/* The neutral / parting plane the faces pivot about (fixed, dashed). */}
    <path d="M3 18 H21" strokeDasharray="2.4 2" />
    {/* The tapered wall rising off it — the top narrows toward the pull. */}
    <path d="M5 18 L8.5 6 H15.5 L19 18" />
    {/* Pull direction — out of the mold, along the neutral-plane normal. */}
    <path d="M12 6 V2 M12 2 L10.6 3.5 M12 2 L13.4 3.5" />
  </Icon>
);

// --- Sheet metal features ---------------------------------------------------

/**
 * Base flange = the sheet-metal part's first body — a flat plate at gauge. A
 * thin iso slab (top face parallelogram + a visible front/side thickness): the
 * gauge is the thing this glyph shows that a plain extrude solid does not, so it
 * reads as "flat sheet at a fixed thickness", the anchor the bends fold off.
 */
export const BaseFlangeIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3 12 L9 8 H21 L15 12 Z" />
    <path d="M3 12 V15 L15 15 V12" />
    <path d="M15 15 L21 11 V8" />
  </Icon>
);

/**
 * Edge flange = a leg folded up off a straight edge of the sheet. An L-section
 * strip of CONSTANT gauge (two parallel outlines a wall-thickness apart) bent
 * about a radius — the double outline + bend arc say "the sheet itself is
 * folded", distinct from the fillet's solid rounded corner.
 */
export const EdgeFlangeIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 14 H13 A3 3 0 0 0 16 11 V4" />
    <path d="M4 17 H14 A6 6 0 0 0 20 11 V4" />
    <path d="M16 4 H20" />
    <path d="M4 14 V17" />
  </Icon>
);

/**
 * Closed hem = a sheet edge folded ~180° back FLAT onto itself. The parent
 * plate runs in, makes a tight U-turn at the edge, and the return layer folds
 * back over it a gauge-gap above — the doubled edge that reads "hemmed", not
 * "flanged" (the edge-flange icon folds a leg UP; this folds one BACK).
 */
export const HemIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3 15 H18 A2 2 0 0 0 18 11 H8" />
    <path d="M3 15 V12" />
  </Icon>
);

/**
 * Corner relief = the shared corner of two adjacent flanges with a small square
 * notch removed so the blank develops flat. Two solid flange legs meet at the
 * corner; the removed notch is drawn as a dashed square (the cut material) —
 * an engineering-drawing "this is taken away" reading, not a generic cutout.
 */
export const CornerReliefIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M10 10 V20 H4 V10 Z" />
    <path d="M10 10 H20 V4 H10 Z" />
    <path d="M4 4 H10 V10 H4 Z" strokeDasharray="2 1.5" />
  </Icon>
);

/**
 * Pattern = the seed body copied into an array — a 2×2 grid of square cells,
 * the top-left one punched to mark the seed (instance 0). Reads as "repeat",
 * and its square cells tie it to the title-block grid rather than a generic
 * "copy" glyph.
 */
export const PatternIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x={4} y={4} width={6} height={6} />
    <rect x={14} y={4} width={6} height={6} />
    <rect x={4} y={14} width={6} height={6} />
    <rect x={14} y={14} width={6} height={6} />
    <Node cx={7} cy={7} />
  </Icon>
);

/** Linear pattern = the seed square stepped along a row (a direction arrow). */
export const LinearPatternIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x={3} y={9} width={6} height={6} />
    <path d="M11 12 H21" />
    <path d="M21 12 L18 10 M21 12 L18 14" />
    <Node cx={13} cy={12} />
    <Node cx={17} cy={12} />
  </Icon>
);

/** Circular pattern = the seed square copied around a center (a ring of nodes). */
export const CircularPatternIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x={9.5} y={2.5} width={5} height={5} />
    <path d="M6 6 A 9 9 0 1 0 18 6" />
    <Node cx={12} cy={13} />
    <Node cx={5} cy={16} />
    <Node cx={19} cy={16} />
  </Icon>
);

/**
 * Combine = a boolean between two independently-built bodies (union). Two
 * overlapping solids scribed as offset squares — the Venn-of-boxes gesture in
 * the title-block square vocabulary the extrude/pattern glyphs speak, so it
 * reads as "fuse these two bodies into one", not a generic group/merge icon.
 */
export const CombineIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x={4} y={9} width={10} height={10} />
    <rect x={10} y={5} width={10} height={10} />
  </Icon>
);

// --- Feature operations (add / cut, direction) ------------------------------

/** Add = material joined onto the body. */
export const AddIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 5 V19" />
    <path d="M5 12 H19" />
  </Icon>
);

/** Cut = material removed from the body. */
export const CutIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 12 H19" />
  </Icon>
);

/** Normal = the feature grows along the face normal (arrow off the face). */
export const NormalIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 19 H20" />
    <path d="M12 19 V6" />
    <path d="M12 6 L8 10 M12 6 L16 10" />
  </Icon>
);

/** Reverse = the feature grows against the normal (arrow into the face). */
export const ReverseIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 5 H20" />
    <path d="M12 5 V18" />
    <path d="M12 18 L8 14 M12 18 L16 14" />
  </Icon>
);

// --- Inspect ----------------------------------------------------------------

/**
 * Measure = a caliper reading a distance: a dimension line with end arrows
 * between two witness ticks. Drawn from engineering-drawing dimension
 * notation, not a generic ruler — it ties the tool to the title-block idiom.
 */
export const MeasureIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 6 V18" />
    <path d="M19 6 V18" />
    <path d="M5 12 H19" />
    <path d="M5 12 L8 10 M5 12 L8 14" />
    <path d="M19 12 L16 10 M19 12 L16 14" />
    <Node cx={5} cy={12} />
    <Node cx={19} cy={12} />
  </Icon>
);

// --- DRO --------------------------------------------------------------------

/** Grid snap = a ruled grid with one punched intersection (the snapped node). */
export const GridSnapIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 10 H20 M4 14 H20 M10 4 V20 M14 4 V20" />
    <Node cx={10} cy={14} />
  </Icon>
);

// --- Export -----------------------------------------------------------------

/** STEP = an exact B-rep solid (an isometric cube — every edge is real). */
export const StepIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 8 L12 4 L20 8 L12 12 Z" />
    <path d="M4 8 V16 L12 20 V12" />
    <path d="M20 8 V16 L12 20" />
  </Icon>
);

/**
 * Import STEP = an external B-rep solid brought IN. The same isometric cube the
 * export `StepIcon` draws (every edge is real), dropped to make room for a
 * scribed arrow descending into its top face — the "bring it in" gesture. The
 * incoming arrow is the one mark that separates it from export; same square-cap
 * scribe vocabulary, so it reads as a member of the feature set, not an office
 * "upload" glyph.
 */
export const ImportStepIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 11 L12 7 L20 11 L12 15 Z" />
    <path d="M4 11 V17 L12 21 V15" />
    <path d="M20 11 V17 L12 21" />
    <path d="M12 1 V8" />
    <path d="M9.5 5.5 L12 8.5 L14.5 5.5" />
  </Icon>
);

/** STL = a faceted mesh (a triangulated strip — the approximation). */
export const StlIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 17 L8 7 L12 17 L16 7 L20 17 Z" />
    <path d="M8 7 L16 7" />
  </Icon>
);

/**
 * Export SVG = the drafting SHEET saved out as a vector file. A framed sheet
 * with a title-block cell scribed into its lower-right corner (the drawing you
 * see), and a scribed arrow descending out from under it — the "download the
 * sheet" gesture. Its framed-sheet + title-block vocabulary ties it to the
 * drawing signature and separates it from the STEP cube (a solid) and the STL
 * strip (a mesh): this exports the 2D print, not the 3D body.
 */
export const SheetExportIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x={4} y={3} width={16} height={11} />
    <path d="M14 14 V10 H20" />
    <path d="M12 15 V22" />
    <path d="M8.5 18.5 L12 22 L15.5 18.5" />
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

// --- History -----------------------------------------------------------------
//
// Undo/redo in the scribed idiom: a return stroke that doubles back through a
// TRUE squared elbow (H–V–H, mitered corners) — rhyming with the L-bends of
// Perpendicular/Mirror, not the round circular-arrow of the office icon sets.

/** Undo — the scribe line runs back left, returning under via a squared elbow. */
export const UndoIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 9 H16 V17 H8" />
    <path d="M9 5 L5 9 L9 13" />
  </Icon>
);

/** Redo — the mirror stroke (about x=12): the line re-runs right, elbow under. */
export const RedoIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M19 9 H8 V17 H16" />
    <path d="M15 5 L19 9 L15 13" />
  </Icon>
);

// --- View navigation ---------------------------------------------------------
//
// The viewport's view rail (Batch 1 makeover). Same scribed vocabulary: an
// isometric reference block for the named views, with the addressed face
// hatched — engineering-drawing view notation, not office camera glyphs.

/** The iso reference block (shared frame of the view glyphs). */
function IsoBlock() {
  return (
    <>
      <path d="M4 8 L12 4 L20 8 L12 12 Z" />
      <path d="M4 8 V16 L12 20 V12" />
      <path d="M20 8 V16 L12 20" />
    </>
  );
}

/** Home view — the block with the bench line under it (back to the bench). */
export const ViewHomeIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 6.5 L12 3 L19 6.5 L12 10 Z" />
    <path d="M5 6.5 V13.5 L12 17 V10" />
    <path d="M19 6.5 V13.5 L12 17" />
    <path d="M3 21 H21" />
  </Icon>
);

/** Fit to model — the block held by four corner registration ticks. */
export const ViewFitIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M9 9 H15 V15 H9 Z" />
    <path d="M3 7 V3 H7" />
    <path d="M17 3 H21 V7" />
    <path d="M21 17 V21 H17" />
    <path d="M7 21 H3 V17" />
  </Icon>
);

/** Front view — the front face addressed (filled node in its centre). */
export const ViewFrontIcon = (p: IconProps) => (
  <Icon {...p}>
    <IsoBlock />
    <Node cx={8} cy={13.5} />
  </Icon>
);

/** Top view — the top face addressed. */
export const ViewTopIcon = (p: IconProps) => (
  <Icon {...p}>
    <IsoBlock />
    <Node cx={12} cy={8} />
  </Icon>
);

/** Right view — the right face addressed. */
export const ViewRightIcon = (p: IconProps) => (
  <Icon {...p}>
    <IsoBlock />
    <Node cx={16} cy={13.5} />
  </Icon>
);

/** Isometric view — the block with its three visible faces all open. */
export const ViewIsoIcon = (p: IconProps) => (
  <Icon {...p}>
    <IsoBlock />
    <path d="M12 12 V20" strokeDasharray="2 2" />
  </Icon>
);
