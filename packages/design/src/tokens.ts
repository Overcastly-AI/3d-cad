/**
 * Loft design tokens — THE single source of truth for both renderers.
 *
 * The Tailwind preset (`tailwind-preset.ts`) derives the DOM theme from these
 * constants, and the react-three-fiber viewport reads the `viewport` set
 * directly — one palette, two renderers (CLAUDE.md design mandate). No hex
 * value may be duplicated outside this file.
 *
 * Direction (frontend-design skill, 2026-07-10): the machine shop, not a SaaS
 * dashboard. Ground is gun-blued steel (deliberately not near-black), the
 * model is machined aluminum, and the single accent is scribed brass. The
 * signature element is the "title block" inspection panel; everything else
 * stays quiet.
 */

export const color = {
  /** App + viewport ground — gun-blued steel. */
  carbide: "#0F141A",
  /** Panel / chrome surfaces. */
  anvil: "#161D27",
  /** Ruled lines of the title block; decorative borders. */
  hairline: "#2C3747",
  /** Interactive control borders (3.06:1 on anvil — WCAG 1.4.11). */
  etch: "#5A6A7E",
  /** Primary text (13.2:1 on anvil). */
  mist: "#DDE4EB",
  /** Secondary text / labels (7.2:1 on anvil). */
  gauge: "#9DAABA",
  /** THE accent — scribe-line / DRO brass. Selection, focus, wordmark. */
  brass: "#E3A64B",
  /** Hover state of the accent. */
  brassHover: "#EFC98A",
  /** Model default material — machined aluminum. */
  aluminum: "#B9C0C8",
  /** Validation / error text (6.5:1 on anvil). */
  flag: "#F27E7E",
} as const;

/**
 * WebGL scene palette — consumed by the r3f viewport. Values reference the
 * DOM palette above so the two renderers can never drift.
 */
export const viewport = {
  background: color.carbide,
  gridMajor: color.hairline,
  gridMinor: "#1B2330",
  /** Default model surface material. */
  modelSurface: color.aluminum,
  /** B-rep edge overlay lines on the model. */
  modelEdge: "#454F5B",
  selection: color.brass,
  hover: color.brassHover,
  /** Key / fill / rim studio light tints (kept near-neutral, cool fill). */
  lightKey: "#FFFFFF",
  lightFill: "#B9C7D9",
} as const;

/**
 * Sketch-scene palette — the 2D authoring layer inside the WebGL viewport.
 * Committed entities read as scribed bright metal through layout bluing;
 * the in-progress preview is the working brass accent; datum planes are
 * quiet steel sheets that take a brass edge when addressed. Opacities live
 * here too: they are design decisions, not per-mesh magic numbers.
 */
export const sketch = {
  /** Committed sketch entity ink — a scribed line through the bluing. */
  scribe: "#E9F1F8",
  /** Persisted-and-solved sketch ink (slightly settled vs. the live buffer). */
  scribeSolved: "#C4D2DE",
  /**
   * Construction (reference-only) geometry ink — centerlines, mirror axes,
   * diagonals: solved and constrainable but excluded from the extrude/revolve
   * profile, so it reads muted (dimmer than both scribe inks) and dashes fine
   * to say "reference, not profile".
   */
  constructionInk: color.gauge,
  /** Construction dash pattern (world mm) — finer than the preview rubber band. */
  constructionDashMm: 1.4,
  constructionGapMm: 1,
  /** In-progress preview (rubber band) — dashes in working brass. */
  preview: color.brass,
  /** Entity defining points (endpoints, centers). */
  point: color.brass,
  /** Snap-cursor crosshair. */
  cursor: color.brassHover,
  /** Datum plane fill / edge at rest. */
  planeFill: color.hairline,
  planeEdge: color.etch,
  /** Datum plane under the pointer or keyboard focus. */
  planeHoverEdge: color.brass,
  /** The chosen sketch plane while drawing. */
  planeActiveEdge: color.brass,
  /** Plane fill opacities (rest / hover / active sketch sheet). */
  planeFillOpacity: 0.14,
  planeHoverFillOpacity: 0.28,
  planeActiveFillOpacity: 0.06,
  /** Selected entity ink — brass, matching `viewport.selection`. */
  selectedInk: color.brass,
  /** Hovered pick (entity or point) — matching `viewport.hover`. */
  hoverInk: color.brassHover,
  /**
   * Constraint glyph ink — engineering-drawing annotation, quiet by default.
   * Driving dimensions carry brass (they are THE parametric handles);
   * conflicting/redundant constraints flip to flag ink.
   */
  glyph: color.gauge,
  glyphDimension: color.brass,
  glyphConflict: color.flag,
  /** Constraint glyph type size (px) and offset from the geometry (mm). */
  glyphSizePx: 11,
  glyphOffsetMm: 3.5,
  /** Entity defining-point size (px, screen space — sizeAttenuation off). */
  pointSizePx: 5,
  /** Selected/hovered defining points render larger — the finer target. */
  pickedPointSizePx: 8,
  /** Snap-cursor crosshair arm length (world mm). */
  cursorArmMm: 2.5,
  /** Rubber-band dash pattern (world mm). */
  previewDashMm: 2,
  previewGapMm: 1.25,
} as const;

export const font = {
  /** Display: wordmark + tracked eyebrow labels. Used with restraint. */
  display: '"Fragment Mono", ui-monospace, monospace',
  /** Body / UI face. */
  body: '"Hanken Grotesk", system-ui, sans-serif',
  /** Data readouts — tabular by nature (monospace). */
  data: '"Fragment Mono", ui-monospace, monospace',
} as const;

/** Type scale (px) — dense precision instrument, not marketing type. */
export const fontSize = {
  /** Eyebrow labels, chip text. */
  "2xs": 10,
  /** Cell labels, captions. */
  xs: 11,
  /** Dense UI default. */
  sm: 12,
  /** Body / data readouts. */
  base: 13,
  /** Inputs, emphasized data. */
  md: 14,
  /** Section values, wordmark. */
  lg: 16,
  /** Hero numerals (used sparingly). */
  xl: 20,
} as const;

/** Spacing scale (px) — 4px grid. */
export const spacing = {
  "0": 0,
  "0.5": 2,
  "1": 4,
  "2": 8,
  "3": 12,
  "4": 16,
  "5": 20,
  "6": 24,
  "8": 32,
  "10": 40,
  "12": 48,
} as const;

/** Radii (px) — rectilinear, drawing-like; title-block cells are square. */
export const radius = {
  none: 0,
  sm: 2,
  md: 4,
} as const;

/** Motion durations (ms). Respect `prefers-reduced-motion` at use sites. */
export const duration = {
  fast: 120,
  base: 200,
} as const;

/** Fixed layout dimensions (px) of the shell. */
export const layout = {
  toolbarHeight: 44,
  inspectorWidth: 320,
} as const;
