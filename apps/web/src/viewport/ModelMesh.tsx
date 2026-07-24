import { viewport } from "@loft/design/tokens";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
} from "react";
import {
  BufferGeometry,
  EdgesGeometry,
  LineBasicMaterial,
  MeshMatcapMaterial,
} from "three";
import { useThree, type ThreeEvent } from "@react-three/fiber";

import { loadGlbGeometry, subsetEdges } from "./glbGeometry";
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
}: ModelMeshProps) {
  const invalidate = useThree((state) => state.invalidate);
  const [geometry, setGeometry] = useState<BufferGeometry | null>(null);
  const [hovered, setHovered] = useState(false);

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
  useEffect(
    () => () => {
      baseMaterial.dispose();
      featureMaterial.dispose();
      edgeMaterial.dispose();
      featureEdgeMaterial.dispose();
    },
    [baseMaterial, featureMaterial, edgeMaterial, featureEdgeMaterial],
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
    if (localized && faceSet !== null) {
      geometry.groups.forEach((group, ordinal) => {
        group.materialIndex = faceSet.has(ordinal) ? 1 : 0;
      });
    }
    invalidate();
  }, [geometry, localized, faceSet, invalidate]);

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

  const onPointerOver = useCallback(
    (event: ThreeEvent<PointerEvent>) => {
      if (!interactive) return;
      event.stopPropagation();
      setHovered(true);
    },
    [interactive],
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

  // Dispose GPU resources when a geometry is replaced or unmounts.
  const edges = useMemo(
    () => (geometry ? new EdgesGeometry(geometry, 25) : null),
    [geometry],
  );
  useEffect(
    () => () => {
      geometry?.dispose();
      edges?.dispose();
    },
    [geometry, edges],
  );

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

  if (geometry === null || edges === null) {
    return null;
  }
  return (
    <group>
      <mesh
        geometry={geometry}
        material={localized ? [baseMaterial, featureMaterial] : baseMaterial}
        onPointerOver={interactive ? onPointerOver : undefined}
        onPointerOut={interactive ? onPointerOut : undefined}
      />
      <lineSegments geometry={edges} material={edgeMaterial} />
      {featureEdges !== null ? (
        <lineSegments geometry={featureEdges} material={featureEdgeMaterial} />
      ) : null}
    </group>
  );
}
