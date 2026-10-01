/**
 * The part workspace's documents: the route's part id, the sketch-store
 * selectors the page reacts to, and the part / feature-tree / evaluate
 * queries.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";

import { evaluatePart, fetchFeatureTree, fetchPart } from "../../api/parts";
import { useSketchStore } from "../../sketch/store";
import { partRoute } from "../../router";

export function usePartDocument() {
  const { partId } = partRoute.useParams();
  const queryClient = useQueryClient();

  const mode = useSketchStore((state) => state.mode);
  const edit = useSketchStore((state) => state.edit);
  const offset = useSketchStore((state) => state.offset);
  const mirrorRequest = useSketchStore((state) => state.mirrorRequest);
  const cornerRequest = useSketchStore((state) => state.cornerRequest);
  const revision = useSketchStore((state) => state.revision);
  const featureId = useSketchStore((state) => state.featureId);
  // The USER's authoring, not the raw count — and now for two independent
  // reasons, which is the tell that this is the right seam rather than a
  // workaround. RECT-1: a drawn rectangle arrives with its rigidity set, so
  // `constraints.length > 0` would bind every rectangle the instant it was
  // drawn. SNAP-3: placement infers a coincident whenever a corner snaps onto
  // something, so it would bind the first time two corners met. Either way the
  // unsaved-exit confirm would vanish on an action the user never read as
  // constraining anything. See `SketchState.userConstrained`.
  const userConstrained = useSketchStore((state) => state.userConstrained);
  // Counts, not the arrays: FLOW-A2's draft mirror and its exit prompt both
  // need to re-run when the buffer CHANGES SIZE, and selecting the arrays
  // themselves would re-render this page on every solved-position adoption.
  const entityCount = useSketchStore((state) => state.entities.length);
  const constraintCount = useSketchStore((state) => state.constraints.length);
  const begin = useSketchStore((state) => state.begin);
  const setTool = useSketchStore((state) => state.setTool);
  const toggleSnap = useSketchStore((state) => state.toggleSnap);
  const navigate = useNavigate();

  const part = useQuery({
    queryKey: ["part", partId],
    queryFn: () => fetchPart(partId),
    // NOT `staleTime: Infinity` (it was, until 2026-07-30). The part row is five
    // scalars — id/name/unit/`tree_version`/`eval_state` — and one of them is the
    // DENOMINATOR of the staleness comparison the STATUS cell now reports
    // (`features/partBuild.ts`). A version the client never refreshes cannot
    // detect the case that motivated the readout: another session edits the tree,
    // nothing here invalidates, and the workspace would keep asserting currency
    // indefinitely (UI-REVIEW 2026-07-30 F2). Re-reading five scalars when the
    // tab regains focus is cheap; being confidently wrong is not.
    staleTime: 5_000,
  });
  // The document display unit (docs/design/units.md §U2). Edit-form seeds render
  // their canonical mm in this unit; the DocumentUnitProvider carries it to
  // every dimension cell + readout below. Falls back to mm until the part loads.
  const lengthUnit = part.data?.length_unit ?? "mm";
  const tree = useQuery({
    queryKey: ["features", partId],
    queryFn: () => fetchFeatureTree(partId),
  });
  const treeVersion = tree.data?.tree_version;
  const evaluation = useQuery({
    queryKey: ["evaluate", partId, treeVersion],
    queryFn: () => evaluatePart(partId),
    enabled: tree.data !== undefined && tree.data.features.length > 0,
    staleTime: Infinity,
  });
  return {
    partId,
    queryClient,
    mode,
    edit,
    offset,
    mirrorRequest,
    cornerRequest,
    revision,
    featureId,
    userConstrained,
    entityCount,
    constraintCount,
    begin,
    setTool,
    toggleSnap,
    navigate,
    part,
    lengthUnit,
    tree,
    treeVersion,
    evaluation,
  };
}

export type PartDocument = ReturnType<typeof usePartDocument>;
