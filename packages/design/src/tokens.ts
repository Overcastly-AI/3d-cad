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
  /**
   * Hover surface tint — a QUIET warm multiply of the studio matcap, held much
   * closer to white than the selection tint so hovering the body reads as a
   * gentle warm-up (not a commit). Paired with the brass-hover edge, it makes
   * body hover perceptible where the edge alone was imperceptible (UI audit
   * #19b). Selection still wins and reads clearly warmer.
   */
  hoverSurfaceTint: "#F3E9D8",
  restSurfaceTint: "#FFFFFF",
  /**
   * Feature-localized selection (FINDINGS #9). Selecting a feature in the tree
   * (e.g. a hole) highlights ONLY the faces that feature owns — the studio
   * matcap is PRESERVED on the rest of the body, never a whole-body clay swap.
   * The selected subset takes a deeper warm-brass multiply than the whole-body
   * `selectedSurfaceTint` so it POPS against its machined-aluminum neighbours
   * (Plasticity's "addressed feature under a worklight" read), and its B-rep
   * boundary edges brass to trace the feature. A feature that owns EVERY face
   * (the base extrude of a plain box) stays the gentler whole-body select — one
   * selection language, two ranges (subset vs whole).
   */
  featureSelect: {
    /** Selected-feature face tint — multiplies the studio matcap toward brass,
     *  a step deeper than the whole-body select so a subset reads as focused.
     *  Matcaps carry no emissive channel, so the machined-metal read survives. */
    faceTint: "#E4BE85",
    /** Selected-feature B-rep edge emphasis — the selection brass. */
    edge: color.brass,
  },
  /** Surface tint of a clashing/interfering body — multiplies the studio matcap
   * toward a warm red (matcaps carry no emissive channel), so the body reads
   * red-flushed but still metal. The single source `assembly.clashTint` reads. */
  clashSurfaceTint: "#F2C9C9",
  /**
   * Surface tint of a body the interference check could NOT measure. Cooled and
   * held a step down from the rest identity: the part reads "set aside for
   * inspection" against its warm-neutral neighbours, WITHOUT the alarm the flag
   * tint asserts. Deliberately cool — every "committed" state in this product is
   * warm (brass select, red clash), so cool is unmistakably "not established".
   * Read by `assembly.unverifiedTint` (one tint, one source).
   */
  unverifiedSurfaceTint: "#C6D3E2",
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
  /**
   * Face-pick highlight (UI audit #19a). A face pick used to read as a blanket
   * of floating DOM squares; now the face UNDER the cursor (hovered or the
   * armed pick) also gets a translucent brass patch laid ON its plane — the
   * pick reads as the real surface, cursor-driven, not a square. Two strengths
   * (hover / chosen); opacities are design decisions held here.
   */
  facePick: {
    hover: color.brassHover,
    selected: color.brass,
    hoverOpacity: 0.16,
    selectedOpacity: 0.3,
    /**
     * Surface tint of the face UNDER THE CURSOR in the default select tool
     * (SEL-1). It multiplies the studio matcap exactly as the other surface
     * tints do, and it sits deliberately between them:
     *
     *   restSurfaceTint        #FFFFFF  untinted machined aluminium
     *   facePick.hoverTint     #EFD6AE  <- addressed, not yet committed
     *   featureSelect.faceTint #E4BE85  committed selection
     *
     * The design spec expected `hoverSurfaceTint` to carry this, and the first
     * build did use it — then the screenshot said no. That token was chosen to
     * wash the WHOLE body, so it is only ~5 % off white; spread over every
     * face that is a tasteful glow, but landed on ONE face it is invisible,
     * which makes it a cue that does not cue. Localising the highlight is
     * exactly what buys the room to state it louder, so this is a new value
     * rather than a reused one — while staying a clear step below the
     * selection brass, because hover must never read as committed.
     */
    hoverTint: "#EFD6AE",
    /**
     * The addressed face's TRACED boundary (SEL-1). Drawn as a screen-space
     * ribbon rather than a GL line so it can carry width and a depth bias:
     * the trace is numerically coincident with the body's own B-rep edge
     * overlay, and two 1 px lines at identical depth come out stippled.
     *
     * `xrayOpacity` is the strength of the part of the loop that is BEHIND the
     * body — a cylindrical face's far seam, a bore's bottom circle. It is
     * drawn, faintly, because the boundary of the face you are addressing does
     * genuinely wrap out of sight and saying so is information; it is drawn
     * FAINTLY because at full strength it paints over the face in front of it
     * and stops being a trace of anything (code review, 2026-08-06).
     */
    hoverEdgeWidthPx: 2,
    hoverEdgeXrayOpacity: 0.22,
  },
  /** The view reference cube (orientation gizmo) — a machinist's block. */
  gizmo: {
    face: color.anvil,
    stroke: color.etch,
    text: color.mist,
    hover: color.brass,
    opacity: 0.92,
  },
  /**
   * Feature preview ghost (live extrude preview; UI-REVIEW 2026-07-24 #8). The
   * result of the OPEN editor before Save — a translucent swept volume in the
   * working-brass selection language, so it reads as "about to be", not
   * committed. The surface takes the same studio matcap as the real body,
   * tinted toward brass (the matcap carries the metal read; the tint is the
   * "pending" cue); the edges take the selection brass. Opacities are design
   * decisions, held here — not per-mesh magic numbers.
   */
  preview: {
    /** Ghost surface tint — multiplies the studio matcap toward brass (shares
     *  the body-selection tint: one "addressed" language, one source). */
    surfaceTint: "#E8CDA4",
    /** Ghost B-rep edge lines — the selection brass. */
    edge: color.brass,
    /** Ghost surface opacity (translucent — the "not yet committed" read). */
    surfaceOpacity: 0.42,
    /** Ghost edge opacity (a hair under solid so it reads as a preview). */
    edgeOpacity: 0.85,
    /**
     * CUT ghost (FINDINGS burn-down 2026-07-25 #5). An extrude that REMOVES
     * material must never paint a proud brass solid — the preview would state
     * the opposite of the result. A cut is drawn as a VOID instead, and the
     * whole read inverts:
     *   · only the cavity's BACK walls are shaded (you look INTO the pocket,
     *     not at a body's near surface);
     *   · they are shaded DARK and cold — a hole in machined aluminum is a
     *     shadow, not a highlight — where the add ghost is warm and bright.
     * Add = warm, bright, filling. Cut = cold, dark, hollow. Distinct at a
     * glance, and distinct from the red clash tint (interference), which is the
     * only other tinted body state.
     */
    cut: {
      /** Cavity wall tint — multiplies the studio matcap down into cold shade. */
      wallTint: "#3B4757",
      /** Cavity wall opacity — the plate still reads THROUGH the void. */
      wallOpacity: 0.55,
      /** Void silhouette ink — cold steel, the anti-brass. */
      edge: "#AFC3D6",
      /** Void silhouette opacity. */
      edgeOpacity: 0.8,
    },
  },
  /**
   * DIRECT-MANIPULATION HANDLES (T-23) — the depth gauge you pull to set an
   * extrude, and the language every handle after it inherits.
   *
   * The design mandate calls the missing drag affordance "the single biggest
   * 'does not feel like a modeling tool' gap we have", and the fifth product
   * audit found the product carried none at all. The read had to be decided
   * once, here, because there will be more of these (revolve angle, fillet
   * radius, pattern spacing) and four hand-tuned gizmos would be four dialects.
   *
   * It is the WORKING BRASS, deliberately the same accent as the ghost it
   * pulls: the handle and the volume it is sizing are one pending edit, and
   * giving the manipulator its own colour would say they were two things. What
   * separates them is FORM, not hue — the ghost is a translucent solid, the
   * gauge is a scribed line with graduations, exactly as a drawing separates
   * material from dimensioning.
   *
   * The graduations are the signature. A plain arrow says "you may pull this";
   * a RULED arrow says what you are pulling against, which is the difference
   * between a generic gizmo and a machinist's depth gauge. They are held quiet
   * (about half strength) and appear only once the grip is taken or focused —
   * boldness spent in one place, and nothing extra painted while you are just
   * looking at the model.
   */
  manipulator: {
    /** The pull axis, the arrow, and the grip at rest — working brass. */
    axis: color.brass,
    /** Grabbed, hovered or keyboard-focused. */
    active: color.brassHover,
    /** Axis + arrow opacity. Solid enough to aim at, short of committed metal. */
    axisOpacity: 0.92,
    /** Graduation opacity — present, never competing with the ink beneath. */
    ladderOpacity: 0.5,
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
  /**
   * LAYOUT BLUING — the ground the scribe reads against when the active sketch
   * is seated on a model FACE.
   *
   * The founder's report (2026-08-01): *"sketches should be more visible. I had
   * an extruded face then was trying to add a sketch and it was snapping back
   * and I couldn't see it."* Depth was half of it; the other half is measured
   * contrast. `scribe` (#E9F1F8) reads **16.2:1** on the carbide viewport ground
   * and **1.32:1** on a lit machined-aluminum face (≈#C5C7C8 under the studio
   * matcap) — i.e. drawing on stock was near-invisible even with the depth fight
   * won. No single flat ink fixes that: clearing 3:1 on aluminum forces the ink
   * DOWN to L≈0.18, which costs the bright-scribe identity and only buys 4:1 on
   * the dark ground. The ground is the variable, so the ground is what changes.
   *
   * A machinist sprays Dykem layout blue on the stock and scribes THROUGH it —
   * the line reads because the ground under it is dark. This token file already
   * claimed that metaphor ("scribed bright metal through layout bluing") without
   * the product ever rendering it. It renders now: a translucent wash laid on
   * the picked face while you draw, so the sketcher has ONE ground whether you
   * work in space or on stock, and the ink keeps its full brightness.
   *
   * The wash is the viewport ground itself (`carbide`), not a new blue — the
   * palette's one accent stays brass, and blueing steel IS what carbide is.
   * At 0.62 the composite over a lit face measures ≈#585C60, putting the scribe
   * at **5.9:1** (WCAG-AA for text, well past the 3:1 non-text floor) while 38%
   * of the face's shading still reads through, so the stock stays legible as a
   * solid rather than becoming a hole.
   */
  faceBluing: color.carbide,
  faceBluingOpacity: 0.62,
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
  /**
   * An interfering (clashing) instance — flag red, matching the DOM clash
   * schedule + tree badge, so the WebGL edge and the panel read one alarm.
   */
  clash: color.flag,
  /**
   * Surface tint of a clashing instance — multiplies the studio matcap toward
   * a warm red (matcaps carry no emissive channel), so an interfering body
   * reads red-flushed but still metal. References `viewport.clashSurfaceTint`,
   * mirroring how `selectedTint` references `selectedSurfaceTint` — one clash
   * tint, one source (never a raw hex duplicated here).
   */
  clashTint: viewport.clashSurfaceTint,
  /**
   * A pair the kernel could NOT measure (`unresolved` — the exact boolean
   * failed and only an AABB upper bound exists). The viewport still says "look
   * here", but red is reserved for a measurement that was actually taken, so
   * the body is COOLED rather than flushed and its edges are lifted one step
   * (never to gauge — a light edge on a light aluminum body disappears, which
   * is the opposite of attention). Paired with the dashed gauge balloon, this
   * is the schedule's UNVERIFIED stamp rendered in three dimensions
   * (UI-REVIEW 2026-07-30 P1).
   */
  unverified: color.etch,
  /** Surface tint of an unmeasurable body — cool "held for inspection". */
  unverifiedTint: viewport.unverifiedSurfaceTint,
  /**
   * GHOSTED instance (UI-W2 — per-instance visibility/opacity/isolate). The
   * middle stop of the quantized opacity control: the part is still there, you
   * just see THROUGH it to the parts behind. That is the founder's "see inside a
   * 21-instance assembly" case, so the read has to be honestly translucent, not
   * merely dimmed.
   *
   * The two opacities are the product's EXISTING ghost translucency
   * (`viewport.preview`), referenced rather than re-picked, so a ghosted
   * instance and a feature preview are the same strength of see-through — one
   * ghost language, one source.
   *
   * What it deliberately does NOT borrow is the preview's brass `surfaceTint`.
   * Brass means "about to be" (an uncommitted feature); a ghosted instance is
   * fully committed and merely de-emphasised, so tinting it brass would state
   * the opposite of the truth. A ghost keeps the resting tint — the SAME
   * machined aluminum as its solid neighbours, just see-through. Transparency is
   * the whole cue, which is also why it survives at any zoom.
   */
  ghost: {
    /** Ghost surface opacity — the established translucency (0.42). */
    surfaceOpacity: viewport.preview.surfaceOpacity,
    /** Ghost B-rep edge opacity — the silhouette stays readable through it. */
    edgeOpacity: viewport.preview.edgeOpacity,
  },
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
  /** Caption height (mm) for a dimension the model could not measure — one
   *  notch under the value stamp, so a broken dimension speaks without shouting
   *  over the good ones. MATCHES the server composer's `_DIM_ERROR_TEXT_MM`, so
   *  the on-screen sheet and the exported SVG/PDF/DXF read one height (the same
   *  cross-renderer rule `noteTextMm` carries). */
  dimensionErrorTextMm: 2.4,
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

  // --- Section crosshatch — the cut-face fill of a section view (drawings-section.md §5). ---
  // A section view slices the part on a datum plane and hatches the solid it cuts
  // through: the ANSI 45° parallel-line fill. The ink + weight are the SAME the
  // server composer hand-emits for the exported hatch (compose.py `_HATCH_INK` /
  // `_HATCH_W`), so the on-screen section fill and the exported SVG/PDF/DXF read
  // ONE colour — the design token is the single source both renderers draw from
  // (one palette, two renderers — CLAUDE.md DRY design rule).
  /** Section crosshatch ink — a quiet thin graphite (4.0:1 on the vellum). */
  hatch: "#7A8695",
  /** Section crosshatch stroke weight (mm) — the lightest fill rule on the sheet. */
  hatchWeightMm: 0.25,

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

  // --- View placement — the drag-to-place affordance (drawing-export.md §4.2). ---
  // A view is grabbable to author its position on the sheet: a thin blueprint-blue
  // FRAME (the CAD view-border idiom, Fusion/Plasticity) reveals on hover/focus,
  // with a corner grip you drag. Reused pick-blue (`pickHover`/`pickSelected`) so
  // placement and dimensioning read as one instrument, not two accents — boldness
  // stays spent on the sheet inversion, this chrome is quiet and precise.
  /** Placement-frame stroke weight (mm) — a light annotation rule, not an object edge. */
  placementFrameWeightMm: 0.35,
  /** Placement-frame dash + gap (mm) — a phantom-line frame, distinct from an object edge. */
  placementFrameDashMm: 2.4,
  placementFrameGapMm: 1.8,
  /** Padding (mm) between the view's geometry extents and its placement frame. */
  placementPadMm: 5,
  /** Corner-grip half-size (mm) — the square drag handle at the frame's top-left. */
  placementGripMm: 2.6,
  /** Keyboard nudge step (mm) per arrow press; the coarse step (Shift) is 5×. */
  placementNudgeMm: 1,
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

/**
 * Spacing scale (px) — 4px grid, with the two half-steps and the hairline the
 * dense chrome actually uses.
 *
 * CLOSED on purpose (the preset *replaces* Tailwind's scale), which makes it a
 * loaded gun: Tailwind emits **no rule at all** for a step that is missing —
 * no warning, no build error — so the element silently has no size. Until
 * 2026-07-30 the scale was missing `1.5`, `2.5` and `px`, which deleted ~118
 * utilities and with them the feature tree's rollback bar (`h-px`), the tapped
 * hole's thread-note rules, the active-tool brass scribe, the command band's
 * vertical padding and the measure HUD's anchor — all invisible in review
 * because a 0px element photographs as absent-by-design (UI-REVIEW 2026-07-30
 * P1). Guarded now by `apps/web/src/test/tailwindUtilities.test.ts`.
 *
 * `px` (1) is not a rhythm step — it is the HAIRLINE, the drafting language's
 * primary mark (rules, leader ticks, the active scribe). It belongs here
 * because the design draws lines with `h-px`/`w-px`, not with borders.
 *
 * Steps outside this scale stay outside it: use an arbitrary value
 * (`max-h-[16rem]`) or a named `layout` token instead of reopening the scale.
 */
export const spacing = {
  "0": 0,
  /** Hairline — a ruled line, not a gap. */
  px: 1,
  "0.5": 2,
  "1": 4,
  /** Half-step: the dense chrome's vertical rhythm (band rows, menu rows). */
  "1.5": 6,
  "2": 8,
  /** Half-step: icon↔label gap where 8 crowds and 12 drifts apart. */
  "2.5": 10,
  "3": 12,
  "4": 16,
  "5": 20,
  "6": 24,
  "8": 32,
  "10": 40,
  "12": 48,
} as const;

/**
 * TARGET SIZE (px) — the product's written answer to "how small may a control
 * be", because "dense" had been operating as a licence: in 2026-07 EVERY
 * interactive element measured in the chrome was 15–23 px tall and the design
 * mandate's own touch floor was met on no surface (UI-REVIEW 2026-07-30 P2).
 * WCAG 2.2 SC 2.5.8 (AA) asks 24x24, and the policy is to meet it by SIZE rather
 * than by leaning on the spacing exception — a 15 px button surrounded by air
 * passes an audit and still misses under a finger.
 *
 *  - `comfortable` (32) — command surfaces: band tools, the view rail, panel
 *    action cells. Utilities `min-h-target` / `min-w-target`.
 *  - `dense` (24) — data rows and their inline verbs: a register row's OPEN and
 *    DELETE, a tree row's select and suppress, a context-menu row, a HUD
 *    dismiss. Utilities `min-h-target-dense` / `min-w-target-dense`. This is a
 *    FLOOR, not a target: rows keep their tight rhythm, they just stop going
 *    under it.
 *
 * ONE exception, granted by SC 2.5.8 itself:
 *  1. INLINE — a link inside a sentence of running text takes the sentence's
 *     line height (the spec's "inline" exception).
 *
 * The second exception this comment used to carry — the feature tree's 8 px
 * rollback drop slots, "drag targets whose y-position IS their meaning" — is
 * RETIRED, because the element is gone (UI-W1, 2026-07-30): rollback moved to the
 * bottom timeline strip, where a slot is a 24 x `timelineHeight` target on the
 * machine way and the travel stop is a 24 px-wide draggable, keyboard-operable
 * slider. Nothing in the product now claims the essential exception.
 *
 * Anything else under `dense` is a defect. `apps/web/e2e/p1-token-scale.spec.ts`
 * measures the named set with `getBoundingClientRect` plus an `elementFromPoint`
 * reachability check on every run, because this class of defect is invisible in a
 * screenshot: a 16 px button and a correct one both photograph as "dense".
 */
export const target = {
  comfortable: 32,
  dense: 24,
} as const;

/**
 * Radii (px) — rectilinear, drawing-like; title-block cells are square.
 * `full` is the one exception and it is a drafting convention, not a
 * softening: BALLOONS ARE CIRCLES on an engineering drawing, so the assembly
 * balloon, the tree's item chip and pick nodes are round.
 */
export const radius = {
  none: 0,
  sm: 2,
  md: 4,
  full: 9999,
} as const;

/** Motion durations (ms). Respect `prefers-reduced-motion` at use sites. */
export const duration = {
  fast: 120,
  base: 200,
} as const;

/**
 * THE CARRIAGE — the geometry of an indeterminate wait (`ProgressTrack`).
 *
 * A machine tool that is cutting has a carriage travelling its bed, and that is
 * the only honest picture of work whose END IS NOT KNOWN: something is moving,
 * and the distance covered means nothing. A bar that fills would be a claim
 * about remaining time the client does not have — the server is parsing a solid
 * model and no byte count predicts how long that takes.
 *
 * The carriage RECIPROCATES rather than wrapping: it runs to the end of its
 * travel and comes back, so there is no frame where it teleports. It also stays
 * wholly inside the bed (`translateEnd` is derived from its own share of the
 * width, not guessed), so the track never reads as empty.
 *
 * Everything here is derived rather than transcribed: the keyframe end in the
 * Tailwind preset is a function of `carriage`, so changing the carriage width
 * cannot leave the travel wrong.
 */
export const progress = {
  /** One traverse, in ms. `alternate` makes the visible cycle twice this. */
  travelMs: 900,
  /** The bed's thickness (px) — a rule, not a bar. */
  trackHeight: 2,
  /**
   * The bed's resting LENGTH (px). It belongs to the primitive, not to each
   * caller, and the reason is a measured defect rather than a preference: the
   * first draft let the caller size it with `w-32`, which does not exist —
   * this theme's spacing scale is CLOSED and stops at 12 — so the class was
   * dropped, the bed's only child is absolutely positioned, and the bed
   * resolved to ZERO WIDTH. Playwright reported the progressbar as `hidden`
   * while the DOM node was present and correct, which is the same
   * looks-fine-reads-wrong shape as an SVG stroke with no hit box.
   */
  bedWidth: 96,
  /** The carriage's share of the bed's width (%). */
  carriage: 28,
} as const;

/**
 * How far the carriage moves, as a percentage of ITS OWN width — which is what
 * `translateX` is relative to. Derived so the carriage lands exactly flush with
 * the far end of the bed and never overshoots it.
 */
export const carriageTravelPercent =
  ((100 - progress.carriage) / progress.carriage) * 100;

/**
 * The REFERENCE CUBE — the machinist's block that names the view, and the one
 * piece of geometry the DOM and the WebGL scene both have to agree on. ONE
 * source, two renderers, exactly like the palette above.
 *
 * It is here rather than in `apps/web` because the two halves had already come
 * apart. Until 2026-08-17 the placement lived in `viewport/Viewport.tsx` (a
 * 96 px inset around a 120 px footprint, i.e. a 156 px corner) while the
 * clearance the chrome kept for it lived here as a hand-copied `140` — so a
 * right-hand rail was licensed to paint 16 px into a control the design mandate
 * calls table stakes. That drift was NOT the cause of VIEWCUBE-1 (raising the
 * band to 176 was measured and changed nothing; the cause was drei's two-pass
 * `Hud` render — see `ViewCube.tsx`), but it was a second, quieter defect found
 * in the same corner, and it is the reason the numbers are derived now. A
 * number transcribed between two files is not a token; it is a copy waiting to
 * drift, which is the DRY rule this repo enforces on API types and palettes and
 * had not yet enforced on layout geometry.
 *
 * `face` is in SCENE units, which equal CSS px because the cube's camera is
 * orthographic at zoom 1 over a host sized from these same numbers.
 */
const VIEW_CUBE_FACE = 60;
const VIEW_CUBE_MARGIN = 96;
/**
 * The square the block needs on screen. Its ISO silhouette is the SPACE
 * DIAGONAL, `face * sqrt(3)` ≈ 103.9 px across — not the face — plus 2 px each
 * side so the hairline stroke on the far corner is never clipped. Getting this
 * wrong is what made the old footprint constant (120) both too generous for
 * the fit and, paired with a 140 px clearance, too mean for the chrome.
 */
const VIEW_CUBE_SIZE = Math.ceil(VIEW_CUBE_FACE * Math.sqrt(3)) + 4;

export const viewCube = {
  /** Face of the block, scene units == CSS px at zoom 1. */
  face: VIEW_CUBE_FACE,
  /** Centre of the block, inset from the frame's bottom-right corner. */
  margin: VIEW_CUBE_MARGIN,
  /** Side of the square DOM host the block is drawn into. */
  size: VIEW_CUBE_SIZE,
  /** Inset of that host's bottom/right edges — derived, never transcribed. */
  inset: VIEW_CUBE_MARGIN - VIEW_CUBE_SIZE / 2,
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
   *
   * It is the SUM of what it holds, not a round number: group padding (2x4) +
   * eyebrow (13) + a 32px tool target + the band's own bottom rule (1) = 54,
   * plus 2px of slack. It was 46 while every tool was silently 16px tall
   * (`py-1.5` was a dead class — UI-REVIEW 2026-07-30 P1); with real targets the
   * band has to be tall enough to hold them, and `e2e/p1-token-scale.spec.ts`
   * asserts no tool spills out of this frame.
   */
  commandBandHeight: 56,
  inspectorWidth: 320,
  /**
   * THE BOUNDED SHEET — the widest a page-level "sheet" composition may grow
   * (`max-w-sheet`), shared by the sign-in plate and the document registers.
   *
   * It exists because SIGNIN-1 was, underneath the visual complaint, a units
   * problem. The sign-in's thesis is a drawing sheet with the auth form as its
   * title block, and a title block belongs in the sheet's bottom-right corner —
   * but the "sheet" was the browser WINDOW, which has no edges. At 1600x1000
   * that put a 320x260 card at (1233, 692) with 94.8 % of the frame empty, and
   * it read as a CSS fault rather than as the corner of anything
   * (docs/AUDIT-PRODUCT.md R-1, S-1, T-1 — filed four times, at P3 twice "on the
   * assumption it was a minute's work"). Bounding the sheet is what makes a
   * corner a corner.
   *
   * 1120 is a measured fit, not a round number: at the 1280 floor the mandate
   * holds every surface to it leaves 80 px of ground either side — enough that
   * the sheet reads as an object ON the bench rather than as the bench — and at
   * 1600 it centres inside a 240 px margin, which is a mount rather than a void.
   * The registers share it (they were capped at `max-w-5xl` = 1024, a Tailwind
   * default nobody chose), so the two surfaces an evaluating engineer meets
   * before modelling anything are one width instead of two accidents.
   */
  sheetWidth: 1120,
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
   * Width of the CAPTION column in a DENSE field row — the label set BESIDE its
   * control rather than stacked above it (`FieldRow`; FB-19).
   *
   * A real title block does not stack a caption over its value: it prints a
   * small caption in the corner of a ruled cell and the value beside it, and
   * `PanelRow` has drawn read-only cells that way since day one. Editable cells
   * were the only ones still stacking, which cost a whole line of leading per
   * parameter on forms that are almost entirely short values — six full-width
   * rows for the extrude's five fields (founder photo, 2026-08-01).
   *
   * 64 px is the measured fit, not a round number: the widest caption the dense
   * editors set is "Operation" (9 characters of 11 px Hanken Grotesk, ~52 px);
   * 64 clears it with the 8 px gutter the rest of the chrome breathes on and
   * still leaves 216 px of control column inside a 320 px card.
   */
  fieldLabelWidth: 64,
  /**
   * Left inset for HUD cards (feature editors, mate HUD) so they clear the
   * floating tree panel: panel inset (12) + panel width + gutter (12).
   */
  editorInset: 12 + 320 + 12,
  /** Inset of every floating card from the frame edge (== `spacing.3`). */
  cardInset: spacing["3"],
  /**
   * Height of the view rail: a 32px `ToolButton` target inside its 1px frame.
   * Not decorative arithmetic — it defines the bottom HUD lane below.
   */
  viewRailHeight: 34,
  /**
   * The bottom-centre HUD lane: where a centred instrument (the measure
   * readout, the nav cue) sits so it clears the view rail — rail inset + rail
   * height + a gutter. One lane, one anchor: `bottom-hud-lane`.
   *
   * The measure readout asked for `bottom-16` before 2026-07-30, which the
   * closed spacing scale silently dropped, so it rendered STATIC at the top of
   * the frame under the command band — the opposite end of the viewport from
   * the picks it was reporting on.
   */
  hudLaneBottom: spacing["3"] + 34 + spacing["3"],
  /**
   * The least a co-resident panel may be squeezed to in a chrome RAIL — the
   * column where a feature editor and the feature tree share one seat instead
   * of the editor floating over the model (FB-7).
   *
   * A floor, not a height: the editor is the instrument being operated, so it
   * takes the room it needs, but the tree it was opened FROM must never be
   * squeezed to a sliver — about three rows plus its heading, still scrollable.
   * Auto-collapsing the neighbour instead was rejected: a panel that vanishes
   * when you open an editor is its own flow defect (and specs read the tree
   * while editors are open).
   */
  railPanelFloor: 120,
  /**
   * Bottom band occupied by the reference cube (bottom-RIGHT). A right-side
   * panel clamps above it so a table-stakes nav element is never covered
   * (mandate 3a).
   *
   * DERIVED from {@link viewCube}, not chosen: the cube's host reaches
   * `inset + size` up from the frame's bottom edge, and the band adds the same
   * 12 px gutter every other floating card breathes on. The hand-written 140
   * this replaces was 16 px short of the cube's real 156 px reach.
   */
  referenceCubeBand: viewCube.inset + viewCube.size + spacing["3"],
  /**
   * Height of the bottom TIMELINE strip — the machine way the build travels
   * along, docked under the viewport (UI-W1, founder-directed 2026-07-30;
   * `docs/design/ui-wave-tool-grade.md` Surface 1). Like Fusion's timeline it is
   * chrome IN FLOW, not floating: the bottom of the frame already carries three
   * floating occupants (the HUD lane, the reference cube, status banners) and a
   * fourth would fight all of them.
   *
   * The SUM of what it holds, not a round number: a `target.comfortable` op chip
   * (32) + 6 px of seat above and below + the strip's own top rule (1) = 45,
   * plus 3 px of slack so the chips' focus rings never clip. The travel stop
   * spans the full height — it is the one element that touches both rails.
   */
  timelineHeight: 48,
} as const;

/**
 * Stacking layers (z-index) — ONE named scale for every page-level stacking
 * context, so no surface ever wins or loses a paint battle by an ad-hoc
 * number (the 2026-07-24 audit P1: the band's `z-10` context trapped its
 * tooltips underneath the `z-30` panels). Values inside a layer's own
 * stacking context stay local (small relative numbers are fine there);
 * anything that competes at the PAGE level must use this scale.
 *
 * Order, bottom → top:
 * - `overlay` — transient sheets hanging off a surface into the viewport
 *   (offset-plane author, constraint hints, save errors).
 * - `panel` — floating instrument panels over the canvas (tree, inspector).
 * - `hud` — viewport HUD chrome (DRO, view rail, status banners).
 * - `band` — the command band. ABOVE panel/hud deliberately: its tooltips
 *   and flyouts hang down into the viewport and must never be occluded by a
 *   panel. The band itself never geometrically overlaps a panel (it sits
 *   above the canvas in flow), so panels lose no pixels to it.
 * - `menu` — context menus / popovers and their dismiss scrims.
 */
export const zLayer = {
  overlay: 20,
  panel: 30,
  hud: 40,
  band: 50,
  menu: 60,
} as const;
