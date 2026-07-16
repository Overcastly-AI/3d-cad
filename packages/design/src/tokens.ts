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
 *
 * Makeover Batch 1 ("the scene is a place", UI-REVIEW 2026-07-16): the scene
 * is the workbench under shop lights. Grid inks brightened one step (the old
 * minor read ≈1.3:1 on carbide — invisible); the studio look is a procedural
 * matcap ("machined aluminum under shop lights") declared here as four stops
 * and rasterised in the viewport; the background gains a skylight glow and a
 * vignette; a soft contact shadow grounds the stock on the bench.
 */
export const viewport = {
  background: color.carbide,
  /** Section (major) grid ink — ≈2.9:1 on carbide, a legible scribe line. */
  gridMajor: "#3E4D61",
  /** Cell (minor) grid ink — ≈1.8:1 on carbide, quiet but present. */
  gridMinor: "#232E3C",
  /** Default model surface material (the matcap body stop multiplies white). */
  modelSurface: color.aluminum,
  /** B-rep edge overlay lines on the model — graphite scribe on aluminum. */
  modelEdge: "#333B46",
  selection: color.brass,
  hover: color.brassHover,
  /**
   * Body selection/hover feedback (Makeover Batch 3, item 11). Hovering the
   * body brightens its edges (`hover`); selecting its feature warms the whole
   * body — brass edges (`selection`) + a surface tint that multiplies the
   * studio matcap toward brass (matcaps carry no emissive channel, so the metal
   * read is preserved). The rest tint is the matcap multiply identity.
   */
  selectedSurfaceTint: "#E8CDA4",
  restSurfaceTint: "#FFFFFF",
  /**
   * Atmosphere — the DOM half of the scene (the canvas is transparent and the
   * wrapper paints depth behind it; the vignette overlays it). One palette,
   * two renderers: the WebGL grid fades into these exact inks.
   */
  atmosphere: {
    /** Skylight glow above the horizon (radial-gradient inner stop). */
    horizon: "#182028",
    /** The deep edge of the shop — vignette / gradient outer stop. */
    abyss: "#080B0F",
    /** Vignette strength (outer-stop alpha, 0–1). */
    vignetteOpacity: 0.6,
  },
  /** Soft contact shadow under the body — the stock sits ON the bench. */
  groundShadow: "#02050A",
  groundShadowOpacity: 0.85,
  /**
   * "Machined aluminum under shop lights" — the studio matcap's four stops
   * (rasterised procedurally in the viewport; no external HDR/asset requests,
   * deterministic across runs). Key falls high-left, a cool rim low-right.
   */
  matcap: {
    /** Warm key highlight (shop lamp). */
    key: "#F6EFE4",
    /** Body tone — machined aluminum, held a step under the DOM aluminum so
     *  tone mapping leaves headroom for the key (no washed-white faces). */
    body: "#9AA3AD",
    /** Core shade — blued steel shadow side. */
    shade: "#48525D",
    /** Cool fill rim (skylight bounce). */
    rim: "#93A9C1",
  },
  /** The view reference cube (orientation gizmo) — a machinist's block. */
  gizmo: {
    face: color.anvil,
    stroke: color.etch,
    text: color.mist,
    hover: color.brass,
    opacity: 0.92,
  },
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

/**
 * Measurement-overlay palette — the inspect mode inside the WebGL viewport.
 * Pickable snap points and edges are quiet at rest and take the brass accent
 * on hover/selection (the same selection language as the sketcher). The
 * dimension line + its witness marks are THE signature measurement moment, so
 * they carry brass at full strength. References existing colors only — no new
 * hex, one palette across both renderers.
 */
export const measure = {
  /** A hovered edge's highlighted polyline. */
  edgeHover: color.brassHover,
  /** A selected edge's highlighted polyline. */
  edgeSelected: color.brass,
  /** The dimension line drawn between the two witness points + its end marks. */
  dimension: color.brass,
  /** Witness-point marker size (px, screen space — sizeAttenuation off). */
  witnessSizePx: 8,
} as const;

/**
 * Assembly-mode palette — the multi-instance viewport inside the WebGL scene.
 * Every instance is machined aluminum like a single part; the grounded anchor
 * ("fixed to the bench") and the addressed instance take the brass accent, the
 * same selection language as the sketcher/measure overlays. The mating
 * geometry pick highlight reuses the measure edge tokens. References existing
 * colors only — no new hex, one palette across both renderers.
 */
export const assembly = {
  /** Every instance's default surface — machined aluminum (== a lone part). */
  instanceSurface: color.aluminum,
  /** B-rep edge overlay on an instance — matches the part viewport. */
  instanceEdge: "#454F5B",
  /** The grounded instance ("fixed to the bench") reads a touch warmer. */
  grounded: color.brass,
  /** The addressed/selected instance — brass, matching viewport.selection. */
  selected: color.brass,
  /**
   * Surface tint of the addressed instance — multiplies the studio matcap
   * toward brass (matcaps carry no emissive channel), warm but still metal.
   * Shares the part body's selection tint — one selection language, one source.
   */
  selectedTint: viewport.selectedSurfaceTint,
  /** Resting surface tint — the matcap multiply identity (no tint). */
  restTint: viewport.restSurfaceTint,
  /** Hovered instance / mate pick — brass-hover. */
  hover: color.brassHover,
} as const;

/**
 * Drawing-sheet palette — the 2D print surface (SVG, not WebGL). THE signature
 * inversion of the product: every other surface is blued-steel dark, but a
 * drawing IS paper, so the sheet is a leaf of cool drafting vellum laid on the
 * bench, drawn in graphite ink. Spent boldly here and nowhere else. Values are
 * NEW surface colors (a new renderer, like `sketch`/`measure`/`assembly`), and
 * stroke weights are millimetre design decisions, not per-element magic numbers,
 * so the print is scale-correct. Consumed by the SVG sheet renderer directly (no
 * hex duplicated in app code — one palette, N renderers).
 */
export const drawing = {
  /** The sheet — cool drafting white (deliberately not warm cream). */
  paper: "#ECEFF2",
  /** Sheet drop-edge / seat shadow against the bench. */
  paperEdge: "#C9CFD7",
  /** Border rules, title-block rules + stamped text — graphite ink. */
  ink: "#1B222B",
  /** Visible projected edge — solid graphite (the print's primary lines). */
  edgeVisible: "#1B222B",
  /** Hidden (occluded) projected edge — lighter graphite, drawn dashed (≥3:1 on paper). */
  edgeHidden: "#6E7A88",
  /** View labels + secondary title-block captions — mid graphite. */
  label: "#48525E",
  /** Stroke weights on the sheet, in millimetres (drawn at the sheet's mm scale). */
  borderWeightMm: 0.7,
  visibleWeightMm: 0.5,
  hiddenWeightMm: 0.35,
  /** Hidden-edge dash pattern (sheet mm) — the conventional short dash. */
  hiddenDashMm: 2,
  hiddenGapMm: 1.4,
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
  /**
   * The full-width command band under the brand bar — quiet by mandate (the
   * viewport is the hero), but two-tier: a stamped group eyebrow (Create /
   * Modify / Inspect) over its tool row, so the taxonomy the band already
   * encodes in `role=group`s reads on screen (UI-REVIEW 2026-07-16, Track C
   * P2). Fixed so swapping its contents by mode (sketch tools ⇄ feature-create
   * tools) never reflows the r3f canvas beneath it.
   */
  commandBandHeight: 46,
  inspectorWidth: 320,
  /**
   * Fixed width of a HUD feature-editor card (the datum/extrude/… panels that
   * hang top-left over the viewport). A real, token-driven width so the card
   * wraps its own copy instead of shrink-wrapping to its longest line — the
   * Tailwind spacing scale stops at 12, so the old `w-72`/`w-80` were dead
   * classes that let the card grow with its content. Quiet chrome: the viewport
   * keeps the pixels (design mandate 3).
   */
  editorCardWidth: 320,
  /**
   * Left inset for HUD cards (feature editors, mate HUD) so they clear the
   * floating tree panel: panel inset (12) + panel width + gutter (12).
   */
  editorInset: 12 + 320 + 12,
} as const;
