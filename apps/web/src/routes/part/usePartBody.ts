/**
 * The authoring seat and the body the viewport draws for it: an open edit
 * previews its INPUT body (`features/editPreview`), and an evicted mesh is
 * regenerated once per content address.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { fetchBodyMesh, MeshNotFoundError } from "../../api/mesh";
import { useEditPreview } from "../../features/editPreview";
import { type OpenEditor } from "./openEditor";
import type { PartDocument } from "./usePartDocument";

type PartBodyParams = Pick<
  PartDocument,
  "partId" | "queryClient" | "tree" | "evaluation"
>;

export function usePartBody({
  partId,
  queryClient,
  tree,
  evaluation,
}: PartBodyParams) {
  // ---------------------------------------------------------------------
  // The body: a body-affecting feature (extrude) evaluates to a content-
  // addressed GLB. Fetch it through the gateway mesh proxy and render it in
  // the same GLB→mesh pipeline first light uses. `mesh_glb_id: null` means no
  // body yet — the sketch renders alone, no error.
  // ---------------------------------------------------------------------
  const meshGlbId = evaluation.data?.mesh_glb_id ?? null;
  const bodyProperties = evaluation.data?.properties ?? null;

  // The authoring seat (see the note on `setEditor`). Declared here, above
  // the body, because WHICH body is drawn depends on it: editing a fillet,
  // chamfer, shell or draft draws the body the feature is built on.
  const [editor, setEditorState] = useState<OpenEditor | null>(null);

  // EDIT SHOWS THE INPUT BODY (FILLET-EDIT-REPICK, `features/editPreview`): a
  // read-only evaluation cut off before the feature under edit. Nothing is
  // written, so a reload, a crash or a closed tab mid-edit leaves the part as
  // it was. Until the preview lands (or if it fails) the tip stays on screen
  // and the picks still come from the input body's overlay.
  // `displayTree` is the timeline's view of it: display only; everything
  // that evaluates, exports or writes reads `tree.data`.
  const { inputMeshGlbId, displayTree } = useEditPreview(
    partId,
    tree.data,
    editor,
  );
  /** The body the viewport draws: the input body while an edit previews it. */
  const viewMeshGlbId = inputMeshGlbId ?? meshGlbId;
  const body = useQuery({
    queryKey: ["mesh", partId, viewMeshGlbId],
    queryFn: () => fetchBodyMesh(viewMeshGlbId as string),
    enabled: viewMeshGlbId !== null,
    staleTime: Infinity, // content-addressed: the bytes never change per id
    retry: (count, error) => !(error instanceof MeshNotFoundError) && count < 2,
  });

  // Honest failure (§7.8): a `mesh_not_found` 404 means the LRU evicted the
  // artifact — re-evaluate to regenerate it, then refetch. Guarded per content
  // address so a genuinely unservable body surfaces an error, never a loop.
  const regeneratedFor = useRef<Set<string>>(new Set());
  const [regenerating, setRegenerating] = useState(false);
  const [regenFailed, setRegenFailed] = useState(false);
  useEffect(() => {
    if (!(body.error instanceof MeshNotFoundError) || viewMeshGlbId === null) {
      return;
    }
    if (regeneratedFor.current.has(viewMeshGlbId)) {
      setRegenerating(false);
      setRegenFailed(true);
      return;
    }
    regeneratedFor.current.add(viewMeshGlbId);
    setRegenFailed(false);
    setRegenerating(true);
    let cancelled = false;
    void (async () => {
      await queryClient.invalidateQueries({ queryKey: ["evaluate", partId] });
      await queryClient.invalidateQueries({ queryKey: ["mesh", partId] });
      if (!cancelled) setRegenerating(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [body.error, viewMeshGlbId, partId, queryClient]);

  const retryBody = useCallback(() => {
    regeneratedFor.current.clear();
    setRegenFailed(false);
    void queryClient.invalidateQueries({ queryKey: ["evaluate", partId] });
    void queryClient.invalidateQueries({ queryKey: ["mesh", partId] });
  }, [partId, queryClient]);

  const hasBody = body.data !== undefined;

  /**
   * PICK-2 — does ANY pick have something to pick? This is the exact predicate
   * all six pick overlays are fetched on (`meshGlbId !== null`: face pick,
   * datum face pick, hole, edge, shell, measure), lifted to one name so the
   * arming guards below cannot drift away from the queries they guard.
   *
   * `hasBody` is NOT the same question and is not a substitute: it is true only
   * once the GLB has been fetched, so it also reads false while the mesh is
   * merely in flight. This says "an overlay can populate at all".
   */
  const hasPickTargets = meshGlbId !== null;
  return {
    meshGlbId,
    bodyProperties,
    editor,
    setEditorState,
    displayTree,
    viewMeshGlbId,
    body,
    regenerating,
    regenFailed,
    retryBody,
    hasBody,
    hasPickTargets,
  };
}

export type PartBody = ReturnType<typeof usePartBody>;
