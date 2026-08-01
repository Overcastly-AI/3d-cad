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
import { loadGlbGeometry, subsetEdges } from "./glbGeometry";
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
   * `body.faces()` ordinals owned by the selected feature (== the GLB primitive
   * ordinals / merged draw groups). When these are a PROPER subset of the
   * body's faces, the selection localizes to just them — brass face tint + brass
   * boundary edges — and the studio matcap is preserved on every other face
   * (FINDINGS #9). Covering every face (or `null`, e.g. an overlay not yet
   * loaded / a body-less feature) falls back to the whole-body select state.
   */
  selectedFaceIndices?: readonly number[] | null;
  /** Report the current highlight so the viewport can stamp a QA hook. */
  onHighlightChange?: (highlight: BodyHighlight) => void;
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
  onVisibleBounds,
  onBodyViewChange,
}: ModelMeshProps) {
  const invalidate = useThree((state) => state.invalidate);
  const [geometry, setGeometry] = useState<BufferGeometry | null>(null);
  const [hovered, setHovered] = useState(false);
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
  const totalFaces = geometry?.groups.length ?? 0;
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
    },
    [
      baseMaterial,
      featureMaterial,
      edgeMaterial,
      featureEdgeMaterial,
      ghostMaterial,
      hiddenMaterial,
      ghostEdgeMaterial,
    ],
  );

  // Highlight cue (Batch 3, item 11; UI audit #19b; FINDINGS #9). Whole-body
  // selection warms the surface + brasses the edges (the assembly selection
  // language); FEATURE selection keeps the matcap on the base material and lets
  // only the selected group carry the deeper brass tint; hover gives a QUIET
  // warm-up. Matcap tint multiplies the studio sphere — the machined read is
  // preserved in every state.
  useEffect(() => {
    baseMaterial.color.set(
      highlight === "selected"
        ? viewport.selectedSurfaceTint
        : highlight === "hover"
          ? viewport.hoverSurfaceTint
          : // "feature" and "none" keep the matcap identity on the base faces.
            viewport.restSurfaceTint,
    );
    featureMaterial.color.set(viewport.featureSelect.faceTint);
    edgeMaterial.color.set(
      highlight === "selected"
        ? viewport.selection
        : highlight === "hover"
          ? viewport.hover
          : // "feature" leaves the base edges quiet; the brass emphasis rides
            // the separate subset lineSegments below.
            viewport.modelEdge,
    );
    invalidate();
  }, [highlight, baseMaterial, featureMaterial, edgeMaterial, invalidate]);

  // Route each merged draw group to the base (0) or the selected (1) material
  // for the localized state — group ordinal `i` is B-rep face `i`. Layout
  // effect so the assignment lands before the demanded frame paints (a
  // two-material mesh with a stale materialIndex would drop that group).
  useLayoutEffect(() => {
    if (geometry === null) return;
    if (bodyStatesActive) {
      // Four-way split: hidden wins, then ghost, then the localized selection.
      geometry.groups.forEach((group, ordinal) => {
        group.materialIndex = bodyFaceState.hidden.has(ordinal)
          ? 3
          : bodyFaceState.ghosted.has(ordinal)
            ? 2
            : localized && faceSet !== null && faceSet.has(ordinal)
              ? 1
              : 0;
      });
    } else if (localized && faceSet !== null) {
      geometry.groups.forEach((group, ordinal) => {
        group.materialIndex = faceSet.has(ordinal) ? 1 : 0;
      });
    }
    invalidate();
  }, [
    geometry,
    localized,
    faceSet,
    bodyStatesActive,
    bodyFaceState,
    invalidate,
  ]);

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

  // Leaving interactive mode drops a stale hover (e.g. arming Measure while the
  // pointer rests on the body) so the body never sticks lit.
  useEffect(() => {
    if (!interactive && hovered) setHovered(false);
  }, [interactive, hovered]);

  /**
   * Hidden means NOTHING drawn — including no pick target. `Mesh.raycast` walks
   * every draw group regardless of its material's `visible`, so a hidden body
   * would still light the hover state from under the parts you can see. The
   * intersected triangle's group is resolved back to a face ordinal and dropped
   * when that face is hidden, which also lets the pointer fall THROUGH to
   * whatever is genuinely behind it.
   */
  const faceOrdinalOf = useCallback(
    (event: ThreeEvent<PointerEvent>): number | null => {
      const faceIndex = event.faceIndex;
      if (geometry === null || faceIndex === undefined || faceIndex === null) {
        return null;
      }
      const triangleStart = faceIndex * 3;
      const ordinal = geometry.groups.findIndex(
        (group) =>
          triangleStart >= group.start &&
          triangleStart < group.start + group.count,
      );
      return ordinal < 0 ? null : ordinal;
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
    },
    [interactive, faceOrdinalOf, bodyFaceState],
  );
  const onPointerOut = useCallback(() => setHovered(false), []);

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
    geometry.groups.forEach((group, ordinal) => {
      if (!drawnFaces.has(ordinal)) return;
      const end = group.start + group.count;
      for (let i = group.start; i < end; i += 1) {
        const vertex = index.array[i] as number;
        box.expandByPoint(
          point.set(
            position.getX(vertex),
            position.getY(vertex),
            position.getZ(vertex),
          ),
        );
      }
    });
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

  if (geometry === null) {
    return null;
  }
  return (
    <group>
      <mesh
        geometry={geometry}
        material={
          bodyStatesActive
            ? [baseMaterial, featureMaterial, ghostMaterial, hiddenMaterial]
            : localized
              ? [baseMaterial, featureMaterial]
              : baseMaterial
        }
        onPointerOver={interactive ? onPointerOver : undefined}
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
    </group>
  );
}
