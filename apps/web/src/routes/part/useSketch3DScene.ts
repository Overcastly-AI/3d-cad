/**
 * The 3D sketches the viewport draws, and the snap targets of the open 3D
 * sketch editor (SKETCH-3D). Runs outside the r3f Canvas (it queries the
 * body's overlay for model vertices); `Sketch3DSceneLayer` draws the result.
 */
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { fetchPartOverlay } from "../../api/measure";
import type { FeatureResponse } from "../../api/parts";
import { sketch3DLayers, solvedSketch3DMap } from "../../features/sketch3d";
import {
  type FlatSketchLayer,
  snapTargets,
} from "../../features/sketch3dSnaps";
import type { SolvedSketchLayer } from "../../viewport/SketchScene";
import type { OpenEditor } from "./openEditor";

export function useSketch3DScene({
  partId,
  features,
  results,
  editor,
  solved,
  treeVersion,
  meshGlbId,
  bodyFeatureId,
}: {
  partId: string;
  features: readonly FeatureResponse[];
  results: readonly { feature_id: string; data?: unknown }[] | undefined;
  editor: OpenEditor | null;
  solved: readonly SolvedSketchLayer[];
  treeVersion: number | undefined;
  meshGlbId: string | null;
  bodyFeatureId: string | null;
}) {
  const editing = editor?.kind === "sketch3d";
  const solved3d = useMemo(() => solvedSketch3DMap(results), [results]);
  const layers = useMemo(
    () => sketch3DLayers(features, solved3d),
    [features, solved3d],
  );
  const overlay = useQuery({
    queryKey: ["overlay", partId, treeVersion, meshGlbId],
    queryFn: () => fetchPartOverlay(partId),
    enabled: editing && meshGlbId !== null,
    staleTime: Infinity,
    retry: false,
  });
  const edges = overlay.data?.edges ?? null;
  const targets = useMemo(() => {
    if (!editing) return [];
    // Only what comes BEFORE the sketch can be referenced (a later feature
    // is a forward reference the write refuses).
    const index =
      editor.featureId === undefined
        ? features.length
        : features.findIndex((f) => f.id === editor.featureId);
    const before = features.slice(0, Math.max(0, index));
    const names = new Map(before.map((f) => [f.id, f.name] as const));
    const flat: FlatSketchLayer[] = solved
      .filter((layer) => names.has(layer.featureId))
      .map((layer) => ({
        featureId: layer.featureId,
        name: names.get(layer.featureId) ?? "",
        basis: layer.basis,
        entities: layer.entities,
      }));
    return snapTargets({
      flat,
      sketches3d: layers.filter((layer) => names.has(layer.featureId)),
      edges: editor.featureId === undefined ? edges : null,
      anchorId: bodyFeatureId,
    });
  }, [editing, editor, features, solved, layers, edges, bodyFeatureId]);
  return { layers, targets };
}
