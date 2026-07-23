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
/** Muted graphite — the receding, secondary line ink on the vellum. The single
 * source both a hidden (dashed) projected edge and an at-rest vertex handle
 * share, so the "no hex duplicated" DRY rule holds inside the token source too. */
const graphiteMuted = "#6E7A88";

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
  edgeHidden: graphiteMuted,
  /** View labels + secondary title-block captions — mid graphite. */
  label: "#48525E",
  /** Stroke weights on the sheet, in millimetres (drawn at the sheet's mm scale). */
  borderWeightMm: 0.7,
  visibleWeightMm: 0.5,
  hiddenWeightMm: 0.35,
  /** Hidden-edge dash pattern (sheet mm) — the conventional short dash. */
  hiddenDashMm: 2,
  hiddenGapMm: 1.4,

  // --- Dimensions — the drafting-annotation layer (Drawings v1 #6b). ---
  // A dimension is a precise annotation drawn OVER the projected geometry:
  // thin extension + dimension lines, filled arrowheads, and a stamped value.
  // The annotation ink is a lighter graphite than the object lines so the
  // measurement reads as a second layer, yet still clears WCAG-AA on the vellum.
  /** Extension + dimension-line ink and arrowheads — annotation graphite. */
  dimensionInk: "#2A3542",
  /** The stamped value text — full graphite for maximum legibility (AA on paper). */
  dimensionText: "#1B222B",
  /** A dimension the model could not measure — a muted drafting red marker (AA on paper). */
  dimensionFlag: "#B23A2E",
  /** Dimension-line weight (mm) — thinner than a visible object edge. */
  dimensionWeightMm: 0.3,
  /** Witness/extension-line weight (mm) — the lightest rule on the sheet. */
  extensionWeightMm: 0.25,
  /** Filled arrowhead length + half-width (mm) — the drafting barb. */
  arrowLengthMm: 3.4,
  arrowHalfWidthMm: 0.9,
  /** Gap (mm) between the measured feature and where its extension line starts. */
  dimensionGapMm: 1.4,
  /** Extension-line overrun (mm) past the dimension line — the drafting tick. */
  extensionOverrunMm: 1.6,
  /** Default auto-place offset (mm) of the dimension line from its edge. */
  dimensionOffsetMm: 11,
  /** Stamped value text height (mm) — sibling of the title-block value stamp. */
  dimensionTextMm: 3.2,
  /** Radius (mm) of an angular dimension's arc, swept apex→out between the two
   * edges. Sized to clear the vertex yet read as a distinct annotation layer. */
  dimensionArcRadiusMm: 13,

  // --- Free-text notes — the sheet's plain-language annotation layer (§2.2). ---
  // A note is ordinary sheet body text: left-anchored graphite ink at its
  // authored sheet point, a sibling of the dimension/title-block value stamp.
  /** Free-text note height (mm) — MATCHES the server composer's `_NOTE_TEXT_MM`,
   *  so the on-screen note and the exported SVG/PDF/DXF note are ONE height (the
   *  cross-renderer token duplication drawing-export.md notes; one source here). */
  noteTextMm: 3.2,

  // --- Title-block secondary fields (author/date/notes) — drawing D1b. ---
  // The optional TitleBlock free-text stamps as labeled DRAWN / DATE / NOTES rows
  // in the left cell's mid-band, below the primary title. A real block's secondary
  // fields are smaller than its title; these two heights MATCH the server composer's
  // `_TB_FIELD_CAP_MM` / `_TB_FIELD_VAL_MM`, so the DOM sheet and the exported
  // SVG/PDF/DXF read one height rather than each hardcoding it (one source, two
  // renderers — the same cross-renderer rule `noteTextMm` carries).
  /** Secondary-field caption height (mm) — the quiet DRAWN / DATE / NOTES label. */
  titleFieldCaptionMm: 2.1,
  /** Secondary-field value height (mm) — the stamped free-text, below the title. */
  titleFieldValueMm: 2.4,

  // --- Vertex handles — the endpoint pick affordance for point-to-point. ---
  // A point-to-point dimension names two edge ENDPOINTS (design §3.3), so a
  // straight edge's ends get small square handles: precise vertex picking, the
  // CAD idiom, in the same blueprint-blue pick ink as an edge.
  /** Half-side (mm) of a vertex handle square on the sheet. */
  vertexHandleMm: 1.5,
  /** Vertex handle ink at rest — the same muted graphite a hidden edge uses
   * (aliases `edgeHidden` via `graphiteMuted`; recedes until the handle is used). */
  vertexHandleRest: graphiteMuted,

  // --- Pick affordance — dimensionable edges are interactive. ---
  // A blueprint blue: the one accent on the graphite sheet, grounded in the
  // subject (the blueprint), never a generic UI highlight. Both clear AA on the
  // vellum so a hovered/selected edge stays legible.
  /** Hover ink for a pickable (dimensionable) projected edge — blueprint blue. */
  pickHover: "#1E6FBF",
  /** Selected-edge ink — the deeper blueprint blue. */
  pickSelected: "#0F4C81",
  /** Keyboard-focus ring width (mm) — a deep-blue halo UNDER the edge so a
   * focused edge reads as a ring (a distinct shape), not merely the hover
   * recolor: keyboard focus must be visibly distinct from mouse hover (WCAG
   * 2.4.7). The ring ink reuses `pickSelected` (≥3:1 on the vellum). */
  pickFocusRingMm: 2.4,
  /** Invisible hit-stroke width (mm) so thin edges are easy to click/focus. */
  pickHitMm: 2.6,

  // --- Flat-pattern fold lines — the sheet-metal signature (sheet-metal.md §7). ---
  // A sheet-metal flat blank's defining mark is the FOLD LINE: where the shop
  // bends the cut sheet. A fold is neither a cut outline (a visible object edge)
  // nor an occluded edge (hidden dashed) — it is its own annotation, so it reads
  // as a distinct DASHED BLUE stroke, the drafting vernacular for a bend/phantom
  // line. Boldness is spent here (design mandate) — one bright blue on the
  // graphite sheet, clearly not the blueprint-blue PICK accent above. The hex is
  // the SAME one the server composer hand-emits for a `bend` edge (compose.py
  // `_EDGE_BEND`); landing it here makes the design token the single source both
  // renderers read (one palette, two renderers — CLAUDE.md DRY design rule).
  /** Fold-line ink — a distinct drafting blue (3.96:1 on the vellum, WCAG 1.4.11). */
  bend: "#2F6FEB",
  /** Fold-line weight (mm) — a light annotation stroke (matches `_BEND_W`). */
  bendWeightMm: 0.4,
  /** Fold-line dash + gap (mm) — matches the server composer's `_BEND_DASH`, so
   * the on-screen fold line and the exported PDF/DXF/SVG read identically. */
  bendDashMm: 3,
  bendGapMm: 1.6,

  // --- Bend table — the shop's fold instructions, a quiet precision instrument. ---
  // Placed at its server-given anchor rect (top-left, the mirror of the title
  // block). Dense, legible, columnar — a real annotation table, never a card.
  /** Bend-table value height (mm) — sibling of the title-block value stamp. */
  bendTableTextMm: 2.8,
  /** Bend-table column-caption height (mm) — the quiet header row. */
  bendTableCaptionMm: 2.1,
  /** Bend-table header-row height (mm) — matches the server composer's
   *  `_BEND_TABLE_HEADER_H`, so the DOM sheet + the server SVG share one metric
   *  rather than each hardcoding 7. */
  bendTableHeaderMm: 7,
  /** Bend-table per-bend row height (mm) — matches `_BEND_TABLE_ROW_H` (was a
   *  loose `6` inside the renderer). */
  bendTableRowMm: 6,
  /** Bend-table column-start offsets, as FRACTIONS of the block width. The
   *  renderer derives each column x from `table.width` (`x + width * fraction`)
   *  instead of the old magic absolute mm (3/26/43/62/77) coupled to the fixed
   *  92 mm block — the same `_BEND_COL_DX / _BEND_TABLE_W` ratio the server uses,
   *  named once here (BEND · ANGLE · RADIUS · DIR · ALLOW). */
  bendTableColumnFractions: [3 / 92, 26 / 92, 43 / 92, 62 / 92, 77 / 92],
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
