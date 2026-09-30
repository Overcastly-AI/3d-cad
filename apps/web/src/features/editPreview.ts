/**
 * EDIT FEATURE SHOWS THE INPUT BODY (FILLET-EDIT-REPICK), as Fusion 360's Edit
 * Feature does: while a fillet, chamfer, shell or draft is being edited, the
 * viewport shows the body the feature is BUILT ON, which is the body its picks
 * live on, and the timeline shows its stop just before the feature. At the tip
 * the edges a fillet rounded are gone, so its picks had nothing to sit on.
 *
 * This is a VIEW, never a write. The first cut moved the persisted rollback
 * bar, and a reload, crash or closed tab mid-edit then left the part rolled
 * back, so drawings, assemblies and exports quietly used the partial body (a
 * blocking review finding on aa445e5). The input body now comes from a
 * read-only evaluation cut off before the feature, and the stop on the
 * timeline is a display of the same fact. The stored bar is untouched; the
 * timeline's own travel stop and TO TIP are still the only writers.
 */
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { evaluatePart, type FeatureTreeResponse } from "../api/parts";

/** The editors whose Edit shows the body the feature is built on. */
export const PREVIEW_BEFORE_KINDS: ReadonlySet<string> = new Set([
  "fillet",
  "chamfer",
  "shell",
  "draft",
]);

/**
 * Where the timeline's stop reads while `featureId` is edited: the feature
 * right before it (a stop names the LAST INCLUDED feature). Undefined when the
 * feature is unknown or first, which has no input body to show.
 */
export function editPreviewStop(
  features: FeatureTreeResponse["features"],
  featureId: string,
): string | undefined {
  const at = features.findIndex((feature) => feature.id === featureId);
  if (at <= 0) return undefined;
  return features[at - 1]?.id;
}

/**
 * The tree AS DISPLAYED while an edit previews its input body: the stop at
 * `stopId` and every feature after it marked rolled back. Display only. It is
 * handed to the timeline, never to anything that evaluates, exports or
 * writes, and the stored stop is not consulted: an edit of a feature the
 * user had rolled back shows the stop just before that feature, as Fusion
 * moves its marker to the feature being edited.
 */
export function previewTree(
  tree: FeatureTreeResponse,
  stopId: string,
): FeatureTreeResponse {
  const at = tree.features.findIndex((feature) => feature.id === stopId);
  if (at < 0) return tree;
  return {
    ...tree,
    rollback_feature_id: stopId,
    features: tree.features.map((feature, index) =>
      feature.rolled_back === index > at
        ? feature
        : { ...feature, rolled_back: index > at },
    ),
  };
}

/**
 * The preview's query key. It carries the part's REAL tree version over a
 * PARTIAL body, so it must never be (or overwrite) the full evaluation's key,
 * `["evaluate", partId, treeVersion]`, or the whole part could later draw as
 * the pre-fillet body. It lives under that prefix only so invalidations of
 * the part's evaluation reach it too.
 */
export function editPreviewKey(
  partId: string,
  treeVersion: number | undefined,
  beforeFeatureId: string | null,
): readonly unknown[] {
  return ["evaluate", partId, treeVersion, { before: beforeFeatureId }];
}

/** What `useEditPreview` needs to know about the open editor. */
export interface PreviewedEditor {
  kind: string;
  mode: "create" | "edit";
  featureId?: string;
}

export interface EditPreview {
  /** The input body's mesh while an edit previews it, else null. */
  inputMeshGlbId: string | null;
  /** The tree as the timeline shows it (the stored tree when not previewing). */
  displayTree: FeatureTreeResponse | undefined;
}

/**
 * The read-only input-body evaluation for an open Edit, and the timeline's
 * display of it. Keyed under `["evaluate", partId]`, so every invalidation of
 * the part's evaluation (a write, an evicted mesh) refreshes it too. Until it
 * lands, or if it fails, the tip stays on screen and the timeline reads the
 * stored stop.
 */
export function useEditPreview(
  partId: string,
  tree: FeatureTreeResponse | undefined,
  editor: PreviewedEditor | null,
): EditPreview {
  const featureId =
    editor !== null &&
    editor.mode === "edit" &&
    editor.featureId !== undefined &&
    PREVIEW_BEFORE_KINDS.has(editor.kind)
      ? editor.featureId
      : null;
  const stop =
    featureId === null || tree === undefined
      ? undefined
      : editPreviewStop(tree.features, featureId);
  const previewed = stop === undefined ? null : featureId;
  const inputBody = useQuery({
    queryKey: editPreviewKey(partId, tree?.tree_version, previewed),
    queryFn: () => evaluatePart(partId, undefined, previewed as string),
    enabled: previewed !== null,
    staleTime: Infinity,
    retry: false,
  });
  const inputMeshGlbId =
    previewed !== null ? (inputBody.data?.mesh_glb_id ?? null) : null;
  const displayTree = useMemo(
    () =>
      inputMeshGlbId !== null && stop !== undefined && tree !== undefined
        ? previewTree(tree, stop)
        : tree,
    [inputMeshGlbId, stop, tree],
  );
  return { inputMeshGlbId, displayTree };
}
