import { viewport } from "@loft/design/tokens";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
} from "react";
import {
  Box3,
  BufferGeometry,
  EdgesGeometry,
  LineBasicMaterial,
  MeshMatcapMaterial,
  Vector3,
} from "three";
import { useThree, type ThreeEvent } from "@react-three/fiber";

import { bodyFaceSets, faceLumps } from "./bodyPartition";
import {
  faceCount,
  faceOrdinalOfTriangle,
  faceStarts,
  loadGlbGeometry,
  setFaceMaterials,
  subsetEdges,
} from "./glbGeometry";
import { instanceView } from "./instanceVisibility";
import { usePartViewStore } from "./partView";
import { studioMatcap } from "./studioMatcap";

/**
 * How the body reads: neutral, pointer-hovered, whole-body selected, or
 * feature-localized (only the selected feature's faces lit; matcap preserved
 * on the rest — FINDINGS #9).
 */
export type BodyHighlight = "none" | "hover" | "selected" | "feature";

export interface ModelMeshProps {
  glb: ArrayBuffer;
  /** Called with the mm-scaled geometry whenever a new mesh is ready. */
  onGeometry?: (geometry: BufferGeometry) => void;
  /**
   * Called when the GLB cannot be parsed. The stale mesh is cleared first —
   * a wrong model on screen next to fresh inspector numbers is worse than an
   * empty viewport.
   */
  onError?: (error: Error) => void;
  /**
   * The body responds to the pointer (hover glow) when true — off while a pick
   * tool owns the viewport (measure / edge / face pick), so the two highlight
   * languages never fight (Makeover Batch 3, item 11).
   */
  interactive?: boolean;
  /**
   * The body's feature is selected in the tree — the body warms even when not
   * interactive (the tree→geometry link). Wins over hover.
   */
  selected?: boolean;
  /**
   * `body.faces()` ordinals owned by the selected feature (== `OverlayFace.index`
   * == the merged geometry's face partition). When these are a PROPER subset of the
   * body's faces, the selection localizes to just them — brass face tint + brass
   * boundary edges — and the studio matcap is preserved on every other face
   * (FINDINGS #9). Covering every face (or `null`, e.g. an overlay not yet
   * loaded / a body-less feature) falls back to the whole-body select state.
   */
  selectedFaceIndices?: readonly number[] | null;
  /** Report the current highlight so the viewport can stamp a QA hook. */
  onHighlightChange?: (highlight: BodyHighlight) => void;
  /**
   * Report the face ordinal under the cursor and the body's total face count
   * (SEL-1 / spec A1). Null when nothing is addressed, or when the mesh could
   * not be face-partitioned and hover fell back to the whole-body glow — so a
   * QA gate can prove "exactly ONE face lights" as a number, not as pixels,
   * the same posture `onFaceSelectionChange` already takes for selection.
   */
  onFaceHoverChange?: (ordinal: number | null, total: number) => void;
  /**
   * Report the highlighted face count and the body's total face count, so QA
   * can prove the highlight is a PROPER subset (matcap preserved on the rest)
   * without reading pixels. `selected` is 0 when nothing is lit.
   */
  onFaceSelectionChange?: (selected: number, total: number) => void;
  /**
   * Bounds of what is actually DRAWN (UI-W2 part half). A hidden body must be
   * out of the camera-fit bounds — a fit that frames a solid nobody can see is
   * the same broken promise as a fit that frames it under a panel. Null when
   * nothing is drawn at all.
   */
  onVisibleBounds?: (bounds: Box3 | null) => void;
  /**
   * Report the drawn / ghosted / hidden face counts so QA can prove a body eye
   * changed the SCENE, not just an aria attribute, without reading pixels. The
   * pixel census in the spec is still the load-bearing assertion (mandate 3c);
   * this is the cheap, raster-independent companion.
   */
  onBodyViewChange?: (counts: {
    drawn: number;
    ghosted: number;
    hidden: number;
  }) => void;
}

/** The tessellated model: token-driven surface + B-rep edge overlay. */
export function ModelMesh({
  glb,
  onGeometry,
  onError,
  interactive = false,
  selected = false,
  selectedFaceIndices = null,
  onHighlightChange,
  onFaceSelectionChange,
  onFaceHoverChange,
  onVisibleBounds,
  onBodyViewChange,
}: ModelMeshProps) {
  const invalidate = useThree((state) => state.invalidate);
  const [geometry, setGeometry] = useState<BufferGeometry | null>(null);
  const [hovered, setHovered] = useState(false);
  /** The B-rep face ordinal under the cursor, or null when none is addressed. */
  const [hoveredFace, setHoveredFace] = useState<number | null>(null);
  const partBodies = usePartViewStore((state) => state.bodies);
  const partView = usePartViewStore((state) => state.view);

  // The selected feature's face set — null unless a non-empty ordinal list
  // arrived (an unloaded overlay / a body-less feature leaves it null).
  const faceSet = useMemo<ReadonlySet<number> | null>(
    () =>
      selectedFaceIndices && selectedFaceIndices.length > 0
        ? new Set(selectedFaceIndices)
        : null,
    [selectedFaceIndices],
  );
  const totalFaces = geometry === null ? 0 : faceCount(geometry);
  // Localize only when the selected feature owns a PROPER subset of the faces
  // (a feature that owns every face — the base extrude of a plain box — reads
  // as the whole-body select state instead, so the two stay distinct).
  const localized =
    selected && faceSet !== null && totalFaces > 0 && faceSet.size < totalFaces;

  // -------------------------------------------------------------------
  // Per-body view state (UI-W2, part half). The evaluate ships ONE fused GLB,
  // so the split back into bodies is derived from the mesh's own connected
  // components (see `bodyPartition.ts`). When it cannot be derived honestly the
  // sets come back null and the whole mesh keeps its single state — the Bodies
  // panel withholds the per-body control in exactly that case, so the two ends
  // agree about when the control is offered.
  // -------------------------------------------------------------------
  const lumps = useMemo(
    () => (geometry === null ? null : faceLumps(geometry)),
    [geometry],
  );
  const perBodyFaces = useMemo(
    () => (lumps === null ? null : bodyFaceSets(lumps, partBodies)),
    [lumps, partBodies],
  );
  const bodyFaceState = useMemo(() => {
    const ghosted = new Set<number>();
    const hiddenFaces = new Set<number>();
    if (perBodyFaces === null) return { ghosted, hidden: hiddenFaces };
    partBodies.forEach((body, index) => {
      const faces = perBodyFaces[index];
      if (faces === undefined) return;
      const stop = instanceView(partView, body.key);
      if (stop.hidden) for (const face of faces) hiddenFaces.add(face);
      else if (stop.ghost) for (const face of faces) ghosted.add(face);
    });
    return { ghosted, hidden: hiddenFaces };
  }, [perBodyFaces, partBodies, partView]);
  /** Any face not drawn at full opacity — the mesh needs the four-way split. */
  const bodyStatesActive =
    bodyFaceState.ghosted.size > 0 || bodyFaceState.hidden.size > 0;
  /** Faces drawn at all (solid or ghost) — what the edges and bounds follow. */
  const drawnFaces = useMemo(() => {
    const drawn = new Set<number>();
    for (let ordinal = 0; ordinal < totalFaces; ordinal += 1) {
      if (!bodyFaceState.hidden.has(ordinal)) drawn.add(ordinal);
    }
    return drawn;
  }, [totalFaces, bodyFaceState]);

  // Selection wins over hover; hover only reads while the body is interactive.
  const highlight: BodyHighlight = localized
    ? "feature"
    : selected
      ? "selected"
      : interactive && hovered
        ? "hover"
        : "none";

  /**
   * SEL-1 / spec A1 — the face under the cursor, not the whole solid. Hover
   * granularity matches the finest thing the raycast can resolve, so a mis-aim
   * becomes visible and free instead of invisible and expensive (FB-8: "too
   * many to see what you are clicking"; FB-3: "picking a face is very
   * difficult"). Null means fall back to today's whole-body glow, which is the
   * honest answer in exactly three cases:
   *
   *   - the pointer is not on the body at all;
   *   - the mesh carries a single B-rep face (a sphere), so "one face" and
   *     "the whole body" are the same set and the localized path would only
   *     cost draw groups;
   *   - the hovered face is HIDDEN, which the pointer handler already declines
   *     to address so the click falls through to what is genuinely behind it.
   *
   * A face-grain hover deliberately does NOT suppress the `"hover"` highlight
   * it reports upward: the body IS hovered, and that hook is the body-grain
   * statement. What changes is where the tint LANDS — see the base-material
   * effect, which stays at rest so the body does not glow as a whole.
   */
  const faceHover: number | null =
    interactive &&
    hovered &&
    hoveredFace !== null &&
    totalFaces > 1 &&
    !bodyFaceState.hidden.has(hoveredFace)
      ? hoveredFace
      : null;

  // Materials are created once and shared across re-tessellations. The studio
  // matcap ("machined aluminum under shop lights") carries the whole lighting
  // rig — the scene needs no lights, and the body reads its curvature at every
  // camera angle (Batch 1 makeover, P0-3). `feature*` are the localized-select
  // pair: the selected feature's faces multiply the matcap toward brass while
  // the base material keeps it (FINDINGS #9).
  const baseMaterial = useMemo(
    () => new MeshMatcapMaterial({ matcap: studioMatcap() }),
    [],
  );
  const featureMaterial = useMemo(
    () => new MeshMatcapMaterial({ matcap: studioMatcap() }),
    [],
  );
  const edgeMaterial = useMemo(
    () => new LineBasicMaterial({ color: viewport.modelEdge }),
    [],
  );
  const featureEdgeMaterial = useMemo(
    () => new LineBasicMaterial({ color: viewport.featureSelect.edge }),
    [],
  );
  /**
   * The addressed face's pair (SEL-1): `facePick.hoverTint` on the surface,
   * `viewport.hover` brass on its boundary. Both stay a step below the
   * full-strength brass of `featureSelect`, which is the hover-vs-selected
   * contrast §1 requires, and the studio matcap survives underneath because
   * the tint multiplies it exactly as every other state does.
   *
   * The boundary is drawn WITHOUT depth testing. Its segments are numerically
   * identical to the ones the body-wide `edges` overlay already draws, so with
   * depth on, the two fight per fragment and the "line" comes out stippled —
   * measured on the founder capture, and it reads as a rendering fault rather
   * than as an affordance. Drawing on top is safe precisely because of what
   * this highlight IS: the face under the cursor was resolved from a raycast
   * hit, so the traced boundary is front-facing where it matters, and the cue
   * is transient. `depthWrite` stays off so the pass leaves nothing behind for
   * the next frame.
   */
  const faceHoverMaterial = useMemo(
    () => new MeshMatcapMaterial({ matcap: studioMatcap() }),
    [],
  );
  const faceHoverEdgeMaterial = useMemo(
    () =>
      new LineBasicMaterial({
        color: viewport.hover,
        depthTest: false,
        depthWrite: false,
        transparent: true,
      }),
    [],
  );
  // GHOST and HIDE (UI-W2, part half). The ghost strengths are the product's
  // EXISTING translucency (`viewport.preview`) — the same source
  // `assembly.ghost` references — so a ghosted body, a ghosted component and a
  // feature preview are one see-through language. What a ghost deliberately
  // does NOT take is the preview's brass tint: brass means "about to be", and a
  // ghosted body is committed and merely de-emphasised. HIDE is a material with
  // `visible: false`, which the renderer skips per draw GROUP — so a hidden
  // body costs no fragments and leaves no pick target, while its neighbours in
  // the same fused mesh draw normally.
  const ghostMaterial = useMemo(
    () =>
      new MeshMatcapMaterial({
        matcap: studioMatcap(),
        transparent: true,
        opacity: viewport.preview.surfaceOpacity,
        depthWrite: false,
      }),
    [],
  );
  const hiddenMaterial = useMemo(
    () => new MeshMatcapMaterial({ matcap: studioMatcap(), visible: false }),
    [],
  );
  const ghostEdgeMaterial = useMemo(
    () =>
      new LineBasicMaterial({
        color: viewport.modelEdge,
        transparent: true,
        opacity: viewport.preview.edgeOpacity,
      }),
    [],
  );
  useEffect(
    () => () => {
      baseMaterial.dispose();
      featureMaterial.dispose();
      edgeMaterial.dispose();
      featureEdgeMaterial.dispose();
      ghostMaterial.dispose();
      hiddenMaterial.dispose();
      ghostEdgeMaterial.dispose();
      faceHoverMaterial.dispose();
      faceHoverEdgeMaterial.dispose();
    },
    [
      baseMaterial,
      featureMaterial,
      edgeMaterial,
      featureEdgeMaterial,
      ghostMaterial,
      hiddenMaterial,
      ghostEdgeMaterial,
      faceHoverMaterial,
      faceHoverEdgeMaterial,
    ],
  );

  // Highlight cue (Batch 3, item 11; UI audit #19b; FINDINGS #9). Whole-body
  // selection warms the surface + brasses the edges (the assembly selection
  // language); FEATURE selection keeps the matcap on the base material and lets
  // only the selected group carry the deeper brass tint; hover gives a QUIET
  // warm-up. Matcap tint multiplies the studio sphere — the machined read is
  // preserved in every state.
  // SEL-1: when the hover has landed on ONE face, the body-wide warm-up is
  // exactly the defect ("hovering glows the whole solid"), so the base drops
  // back to rest and the tint rides the hovered face's own draw group instead.
  useEffect(() => {
    const bodyWideHover = highlight === "hover" && faceHover === null;
    baseMaterial.color.set(
      highlight === "selected"
        ? viewport.selectedSurfaceTint
        : bodyWideHover
          ? viewport.hoverSurfaceTint
          : // "feature", "none", and a face-grain hover all keep the matcap
            // identity on the base faces.
            viewport.restSurfaceTint,
    );
    featureMaterial.color.set(viewport.featureSelect.faceTint);
    faceHoverMaterial.color.set(viewport.facePick.hoverTint);
    edgeMaterial.color.set(
      highlight === "selected"
        ? viewport.selection
        : bodyWideHover
          ? viewport.hover
          : // "feature" and a face-grain hover leave the base edges quiet; the
            // emphasis rides the separate subset lineSegments below.
            viewport.modelEdge,
    );
    invalidate();
  }, [
    highlight,
    faceHover,
    baseMaterial,
    featureMaterial,
    faceHoverMaterial,
    edgeMaterial,
    invalidate,
  ]);

  // Route each B-rep face to the base (0), selected (1), ghost (2), hidden
  // (3) or hovered (4) material. `setFaceMaterials` lays down the MINIMUM
  // number of draw groups that expresses the assignment (one per run of
  // consecutive faces sharing a material) — three.js emits one render item per
  // group whenever the mesh has a material array, so per-face groups cost one
  // draw call per B-rep face the moment a body is ghosted, hidden,
  // feature-selected or hovered. Layout effect so the assignment lands before
  // the demanded frame paints (a multi-material mesh with stale groups would
  // drop faces).
  //
  // Precedence, strongest first: hidden > ghosted > feature-selected > hovered
  // > base. Selection beating hover is the rule §1 states — a face you have
  // COMMITTED to outranks the one you are merely addressing — and it is what
  // keeps a hover from quietly dimming a selected face as the pointer crosses.
  useLayoutEffect(() => {
    if (geometry === null) return;
    setFaceMaterials(geometry, (ordinal) =>
      bodyFaceState.hidden.has(ordinal)
        ? 3
        : bodyFaceState.ghosted.has(ordinal)
          ? 2
          : localized && faceSet !== null && faceSet.has(ordinal)
            ? 1
            : faceHover === ordinal
              ? 4
              : 0,
    );
    invalidate();
  }, [geometry, localized, faceSet, bodyFaceState, faceHover, invalidate]);

  // Report the highlight + face selection up so the viewport can stamp QA hooks.
  useEffect(() => {
    onHighlightChange?.(highlight);
  }, [highlight, onHighlightChange]);
  useEffect(() => {
    const lit =
      highlight === "feature"
        ? (faceSet?.size ?? 0)
        : highlight === "selected"
          ? totalFaces
          : 0;
    onFaceSelectionChange?.(lit, totalFaces);
  }, [highlight, faceSet, totalFaces, onFaceSelectionChange]);

  // SEL-1 / A1: the addressed face, as a number, so a gate can prove exactly
  // ONE face lights without reading WebGL pixels. Null while the fallback
  // whole-body glow is what is on screen, so the hook distinguishes "one face"
  // from "the whole body" rather than conflating them.
  useEffect(() => {
    onFaceHoverChange?.(faceHover, totalFaces);
  }, [faceHover, totalFaces, onFaceHoverChange]);

  // Leaving interactive mode drops a stale hover (e.g. arming Measure while the
  // pointer rests on the body) so the body never sticks lit.
  useEffect(() => {
    if (!interactive && hovered) setHovered(false);
    if (!interactive && hoveredFace !== null) setHoveredFace(null);
  }, [interactive, hovered, hoveredFace]);

  // A re-tessellation renumbers the faces, so an ordinal captured against the
  // OLD mesh addresses an unrelated face on the new one — drop it and let the
  // next pointer move re-resolve against the geometry actually on screen.
  useEffect(() => {
    setHoveredFace(null);
  }, [geometry]);

  /**
   * Hidden means NOTHING drawn — including no pick target. `Mesh.raycast` walks
   * every draw group regardless of its material's `visible`, so a hidden body
   * would still light the hover state from under the parts you can see. The
   * intersected triangle is resolved back to a B-rep face ordinal and dropped
   * when that face is hidden, which also lets the pointer fall THROUGH to
   * whatever is genuinely behind it.
   */
  const faceOrdinalOf = useCallback(
    (event: ThreeEvent<PointerEvent>): number | null => {
      const faceIndex = event.faceIndex;
      if (geometry === null || faceIndex === undefined || faceIndex === null) {
        return null;
      }
      return faceOrdinalOfTriangle(geometry, faceIndex);
    },
    [geometry],
  );

  const onPointerOver = useCallback(
    (event: ThreeEvent<PointerEvent>) => {
      if (!interactive) return;
      const ordinal = faceOrdinalOf(event);
      if (ordinal !== null && bodyFaceState.hidden.has(ordinal)) return;
      event.stopPropagation();
      setHovered(true);
      setHoveredFace(ordinal);
    },
    [interactive, faceOrdinalOf, bodyFaceState],
  );
  /**
   * SEL-1: r3f re-fires `onPointerOver` only when the pointer ENTERS the mesh,
   * never when it crosses from one face to another of the SAME mesh — and our
   * whole part is one fused mesh, so `onPointerOver` alone can only ever
   * address the face you happened to arrive on. Tracking `onPointerMove` is
   * what makes the addressed face follow the cursor.
   */
  const onPointerMove = useCallback(
    (event: ThreeEvent<PointerEvent>) => {
      if (!interactive) return;
      const ordinal = faceOrdinalOf(event);
      // A hidden face is not addressed — the pointer falls THROUGH it to
      // whatever is genuinely behind, the same rule `onPointerOver` applies.
      if (ordinal !== null && bodyFaceState.hidden.has(ordinal)) {
        setHoveredFace(null);
        return;
      }
      event.stopPropagation();
      setHovered(true);
      // Re-render only when the addressed face actually changes; a pointer move
      // across one face fires this handler every frame.
      setHoveredFace((current) => (current === ordinal ? current : ordinal));
    },
    [interactive, faceOrdinalOf, bodyFaceState],
  );
  const onPointerOut = useCallback(() => {
    setHovered(false);
    setHoveredFace(null);
  }, []);

  useEffect(() => {
    let cancelled = false;
    // loadGlbGeometry never rejects — every failure lands in onError.
    void loadGlbGeometry(glb, {
      isCancelled: () => cancelled,
      onGeometry: (next) => {
        setGeometry(next);
        onGeometry?.(next);
      },
      onError: (error) => {
        setGeometry(null);
        onError?.(error);
      },
    });
    return () => {
      cancelled = true;
    };
  }, [glb, onGeometry, onError]);

  // Post-commit frame. With frameloop="demand" + preserveDrawingBuffer, an
  // invalidate() issued inside the load callback draws BEFORE React commits
  // the mesh change — clearing a stale mesh would leave its last frame in
  // the framebuffer. This effect runs after the commit, so the drawn frame
  // always matches the React scene graph.
  useEffect(() => {
    invalidate();
  }, [geometry, invalidate]);

  // Dispose GPU resources when a geometry is replaced or unmounts. When a body
  // is hidden the edge overlay has to follow it — a wireframe silhouette of a
  // body you switched off is exactly the "hidden means nothing drawn" rule
  // being broken — so the edges are rebuilt over the DRAWN face subset.
  const edges = useMemo(() => {
    if (geometry === null) return null;
    if (bodyFaceState.hidden.size === 0) return new EdgesGeometry(geometry, 25);
    const solid = new Set(
      [...drawnFaces].filter((face) => !bodyFaceState.ghosted.has(face)),
    );
    return subsetEdges(geometry, solid);
  }, [geometry, bodyFaceState, drawnFaces]);
  const ghostEdges = useMemo(
    () =>
      geometry !== null && bodyFaceState.ghosted.size > 0
        ? subsetEdges(geometry, bodyFaceState.ghosted)
        : null,
    [geometry, bodyFaceState],
  );
  useEffect(() => () => ghostEdges?.dispose(), [ghostEdges]);
  useEffect(
    () => () => {
      geometry?.dispose();
      edges?.dispose();
    },
    [geometry, edges],
  );

  // Bounds of what is DRAWN — the camera fit's subject (a hidden body is out).
  useEffect(() => {
    if (onVisibleBounds === undefined) return;
    if (geometry === null) {
      onVisibleBounds(null);
      return;
    }
    if (bodyFaceState.hidden.size === 0) {
      onVisibleBounds(geometry.boundingBox?.clone() ?? null);
      return;
    }
    const index = geometry.getIndex();
    const position = geometry.getAttribute("position");
    if (index === null || position === undefined) {
      onVisibleBounds(geometry.boundingBox?.clone() ?? null);
      return;
    }
    const box = new Box3();
    const point = new Vector3();
    const starts = faceStarts(geometry);
    for (let ordinal = 0; ordinal + 1 < starts.length; ordinal += 1) {
      if (!drawnFaces.has(ordinal)) continue;
      const end = starts[ordinal + 1] as number;
      for (let i = starts[ordinal] as number; i < end; i += 1) {
        const vertex = index.array[i] as number;
        box.expandByPoint(
          point.set(
            position.getX(vertex),
            position.getY(vertex),
            position.getZ(vertex),
          ),
        );
      }
    }
    onVisibleBounds(box.isEmpty() ? null : box);
  }, [geometry, bodyFaceState, drawnFaces, onVisibleBounds]);

  // Publish the two facts only the mesh knows: a solid IS on screen (the sketch
  // layer's derived default and the browser's sketch rows read it), and whether
  // the fused mesh could be split per body (the Bodies panel offers or withholds
  // its eye on exactly this).
  const setBodyPresent = usePartViewStore((state) => state.setBodyPresent);
  const setPartitioned = usePartViewStore((state) => state.setPartitioned);
  useEffect(() => {
    setBodyPresent(geometry !== null);
  }, [geometry, setBodyPresent]);
  useEffect(() => {
    setPartitioned(perBodyFaces !== null);
  }, [perBodyFaces, setPartitioned]);
  // Unmounting means the part has no mesh at all (a sketch-only tree, a
  // rollback below the first solid) — the sketch layer's default flips back to
  // "show the ink", which is the only thing left to look at.
  useEffect(
    () => () => {
      setBodyPresent(false);
      setPartitioned(false);
    },
    [setBodyPresent, setPartitioned],
  );

  // QA hook: the drawn / ghosted / hidden face census.
  useEffect(() => {
    onBodyViewChange?.({
      drawn: drawnFaces.size - bodyFaceState.ghosted.size,
      ghosted: bodyFaceState.ghosted.size,
      hidden: bodyFaceState.hidden.size,
    });
  }, [drawnFaces, bodyFaceState, onBodyViewChange]);

  // Brass boundary edges of ONLY the selected feature's faces (FINDINGS #9) —
  // the localized emphasis that traces the feature over the preserved matcap.
  const featureEdges = useMemo<EdgesGeometry | null>(
    () =>
      geometry !== null && localized && faceSet !== null
        ? subsetEdges(geometry, faceSet)
        : null,
    [geometry, localized, faceSet],
  );
  useEffect(() => () => featureEdges?.dispose(), [featureEdges]);

  // SEL-1: the addressed face TRACED — its own boundary, the real topology,
  // not a bounding box. This is what makes a face read as a face rather than
  // as a patch of tint, and it is the same `subsetEdges` machinery the
  // feature-selected state already uses, one ordinal wide.
  const faceHoverEdges = useMemo<EdgesGeometry | null>(
    () =>
      geometry !== null && faceHover !== null
        ? subsetEdges(geometry, new Set([faceHover]))
        : null,
    [geometry, faceHover],
  );
  useEffect(() => () => faceHoverEdges?.dispose(), [faceHoverEdges]);

  if (geometry === null) {
    return null;
  }
  return (
    <group>
      <mesh
        geometry={geometry}
        material={
          // Index order is FIXED (base 0, feature 1, ghost 2, hidden 3, hover
          // 4) so `setFaceMaterials` can name a slot without knowing which
          // states happen to be live. The shortest array that still contains
          // every index in play is chosen — a plain resting body stays a
          // single-material mesh and pays no draw-group cost at all.
          bodyStatesActive || faceHover !== null
            ? [
                baseMaterial,
                featureMaterial,
                ghostMaterial,
                hiddenMaterial,
                faceHoverMaterial,
              ]
            : localized
              ? [baseMaterial, featureMaterial]
              : baseMaterial
        }
        onPointerOver={interactive ? onPointerOver : undefined}
        onPointerMove={interactive ? onPointerMove : undefined}
        onPointerOut={interactive ? onPointerOut : undefined}
      />
      {edges !== null ? (
        <lineSegments geometry={edges} material={edgeMaterial} />
      ) : null}
      {ghostEdges !== null ? (
        <lineSegments geometry={ghostEdges} material={ghostEdgeMaterial} />
      ) : null}
      {featureEdges !== null ? (
        <lineSegments geometry={featureEdges} material={featureEdgeMaterial} />
      ) : null}
      {faceHoverEdges !== null ? (
        <lineSegments
          geometry={faceHoverEdges}
          material={faceHoverEdgeMaterial}
          renderOrder={1}
        />
      ) : null}
    </group>
  );
}
