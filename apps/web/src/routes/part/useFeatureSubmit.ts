/**
 * The shared feature save path and every editor's submit.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { useCallback } from "react";

import {
  type BooleanParams,
  booleanFeatureCreate,
  type ChamferParams,
  chamferFeatureCreate,
  chamferFeatureUpdate,
  createFeature,
  type DatumParams,
  datumFeatureCreate,
  datumFeatureUpdate,
  type DraftParams,
  draftFeatureCreate,
  draftFeatureUpdate,
  type ExtrudeParams,
  extrudeFeatureCreate,
  extrudeFeatureUpdate,
  type FeatureCreate,
  type FeatureUpdate,
  fetchFeatureTree,
  type FilletParams,
  filletFeatureCreate,
  filletFeatureUpdate,
  type HoleParams,
  holeFeatureCreate,
  holeFeatureUpdate,
  type LoftParams,
  loftFeatureCreate,
  loftFeatureUpdate,
  type MirrorParams,
  mirrorFeatureCreate,
  mirrorFeatureUpdate,
  type PatternParams,
  patternFeatureCreate,
  patternFeatureUpdate,
  type RevolveParams,
  revolveFeatureCreate,
  revolveFeatureUpdate,
  type ShellParams,
  shellFeatureCreate,
  shellFeatureUpdate,
  type SheetMetalBaseFlangeParams,
  baseFlangeFeatureCreate,
  baseFlangeFeatureUpdate,
  type SheetMetalEdgeFlangeParams,
  edgeFlangeFeatureCreate,
  edgeFlangeFeatureUpdate,
  type SheetMetalHemParams,
  hemFeatureCreate,
  hemFeatureUpdate,
  type SheetMetalCornerReliefParams,
  cornerReliefFeatureCreate,
  cornerReliefFeatureUpdate,
  type SweepParams,
  sweepFeatureCreate,
  sweepFeatureUpdate,
  updateFeature,
} from "../../api/parts";
import { usePreselectStore } from "../../features/preselect";
import type { PartDocument } from "./usePartDocument";
import type { PartBody } from "./usePartBody";
import type { FeatureCatalog } from "./useFeatureCatalog";
import type { EditorSeat } from "./useEditorSeat";
import type { TreeWrites } from "./useTreeWrites";

type FeatureSubmitParams = Pick<PartDocument, "partId"> &
  Pick<PartBody, "editor"> &
  Pick<FeatureCatalog, "features"> &
  Pick<
    EditorSeat,
    | "setSelectedFeatureId"
    | "setEditorSaving"
    | "setEditorError"
    | "setLastSavedFeatureId"
    | "setRebuildNoticeDismissed"
    | "setEditor"
  > &
  Pick<
    TreeWrites,
    | "freshTreeVersion"
    | "refreshTreeAndBody"
    | "beginTreeWrite"
    | "endTreeWrite"
    | "noteWrittenTreeVersion"
  >;

export function useFeatureSubmit({
  partId,
  editor,
  features,
  setSelectedFeatureId,
  setEditorSaving,
  setEditorError,
  setLastSavedFeatureId,
  setRebuildNoticeDismissed,
  setEditor,
  freshTreeVersion,
  refreshTreeAndBody,
  beginTreeWrite,
  endTreeWrite,
  noteWrittenTreeVersion,
}: FeatureSubmitParams) {
  // The shared save path for either body-affecting feature: read the freshest
  // tree_version, retry once on a stale-version race, then invalidate the tree
  // + evaluate + mesh so the body updates through the #2 render path.
  const runFeatureSave = useCallback(
    (
      createEnvelope: (version: number) => FeatureCreate,
      updateEnvelope: (version: number) => FeatureUpdate,
      isCreate: boolean,
      featureId: string | undefined,
      fallbackMessage: string,
    ) => {
      setEditorSaving(true);
      setEditorError(null);
      // The body on screen is superseded from HERE, not from when the reply
      // lands — see the tree-write block above.
      beginTreeWrite();
      void (async () => {
        try {
          const attempt = async (version: number) =>
            isCreate
              ? createFeature(partId, createEnvelope(version))
              : updateFeature(
                  partId,
                  featureId as string,
                  updateEnvelope(version),
                );
          let response;
          try {
            response = await attempt(await freshTreeVersion());
          } catch {
            response = await attempt(
              (await fetchFeatureTree(partId)).tree_version,
            );
          }
          // The reply carries the version the write PRODUCED: the staleness
          // denominator, in hand a full refetch before either cache has it.
          noteWrittenTreeVersion(response.tree_version);
          setSelectedFeatureId(response.feature.id);
          setLastSavedFeatureId(response.feature.id);
          setRebuildNoticeDismissed(false);
          // The command saved: its picks are a real selection now (preselect
          // rule 3), so the close below must not drop them.
          usePreselectStore.getState().settle();
          setEditor(null);
          await refreshTreeAndBody();
        } catch (error) {
          setEditorError(
            error instanceof Error ? error.message : fallbackMessage,
          );
        } finally {
          setEditorSaving(false);
          endTreeWrite();
        }
      })();
    },
    [
      partId,
      freshTreeVersion,
      refreshTreeAndBody,
      beginTreeWrite,
      endTreeWrite,
      noteWrittenTreeVersion,
    ],
  );

  const submitExtrude = useCallback(
    (params: ExtrudeParams) => {
      const current = editor;
      if (current === null || current.kind !== "extrude") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "extrude").length + 1;
      runFeatureSave(
        (version) =>
          extrudeFeatureCreate(`Extrude${nextIndex}`, params, version),
        (version) => extrudeFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The extrude could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitRevolve = useCallback(
    (params: RevolveParams) => {
      const current = editor;
      if (current === null || current.kind !== "revolve") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "revolve").length + 1;
      runFeatureSave(
        (version) =>
          revolveFeatureCreate(`Revolve${nextIndex}`, params, version),
        (version) => revolveFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The revolve could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitSweep = useCallback(
    (params: SweepParams) => {
      const current = editor;
      if (current === null || current.kind !== "sweep") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "sweep").length + 1;
      runFeatureSave(
        (version) => sweepFeatureCreate(`Sweep${nextIndex}`, params, version),
        (version) => sweepFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The sweep could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitLoft = useCallback(
    (params: LoftParams) => {
      const current = editor;
      if (current === null || current.kind !== "loft") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "loft").length + 1;
      runFeatureSave(
        (version) => loftFeatureCreate(`Loft${nextIndex}`, params, version),
        (version) => loftFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The loft could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitPattern = useCallback(
    (params: PatternParams) => {
      const current = editor;
      if (current === null || current.kind !== "pattern") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "pattern").length + 1;
      runFeatureSave(
        (version) =>
          patternFeatureCreate(`Pattern${nextIndex}`, params, version),
        (version) => patternFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The pattern could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitMirror = useCallback(
    (params: MirrorParams) => {
      const current = editor;
      if (current === null || current.kind !== "mirror") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "mirror").length + 1;
      runFeatureSave(
        (version) => mirrorFeatureCreate(`Mirror${nextIndex}`, params, version),
        (version) => mirrorFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The mirror could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitFillet = useCallback(
    (params: FilletParams) => {
      const current = editor;
      if (current === null || current.kind !== "fillet") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "fillet").length + 1;
      runFeatureSave(
        (version) => filletFeatureCreate(`Fillet${nextIndex}`, params, version),
        (version) => filletFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The fillet could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitChamfer = useCallback(
    (params: ChamferParams) => {
      const current = editor;
      if (current === null || current.kind !== "chamfer") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "chamfer").length + 1;
      runFeatureSave(
        (version) =>
          chamferFeatureCreate(`Chamfer${nextIndex}`, params, version),
        (version) => chamferFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The chamfer could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitShell = useCallback(
    (params: ShellParams) => {
      const current = editor;
      if (current === null || current.kind !== "shell") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "shell").length + 1;
      runFeatureSave(
        (version) => shellFeatureCreate(`Shell${nextIndex}`, params, version),
        (version) => shellFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The shell could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitDraft = useCallback(
    (params: DraftParams) => {
      const current = editor;
      if (current === null || current.kind !== "draft") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "draft").length + 1;
      runFeatureSave(
        (version) => draftFeatureCreate(`Draft${nextIndex}`, params, version),
        (version) => draftFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The draft could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitHole = useCallback(
    (params: HoleParams) => {
      const current = editor;
      if (current === null || current.kind !== "hole") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "hole").length + 1;
      runFeatureSave(
        (version) => holeFeatureCreate(`Hole${nextIndex}`, params, version),
        (version) => holeFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The hole could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitDatum = useCallback(
    (params: DatumParams) => {
      const current = editor;
      if (current === null || current.kind !== "datum") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "datum").length + 1;
      runFeatureSave(
        (version) => datumFeatureCreate(`Plane${nextIndex}`, params, version),
        (version) => datumFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The datum plane could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitBaseFlange = useCallback(
    (params: SheetMetalBaseFlangeParams) => {
      const current = editor;
      if (current === null || current.kind !== "baseFlange") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "sheet_metal_base_flange")
          .length + 1;
      runFeatureSave(
        (version) =>
          baseFlangeFeatureCreate(`Base flange${nextIndex}`, params, version),
        (version) => baseFlangeFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The base flange could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitEdgeFlange = useCallback(
    (params: SheetMetalEdgeFlangeParams) => {
      const current = editor;
      if (current === null || current.kind !== "edgeFlange") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "sheet_metal_edge_flange")
          .length + 1;
      runFeatureSave(
        (version) =>
          edgeFlangeFeatureCreate(`Edge flange${nextIndex}`, params, version),
        (version) => edgeFlangeFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The edge flange could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitHem = useCallback(
    (params: SheetMetalHemParams) => {
      const current = editor;
      if (current === null || current.kind !== "hem") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "sheet_metal_hem").length + 1;
      runFeatureSave(
        (version) => hemFeatureCreate(`Hem${nextIndex}`, params, version),
        (version) => hemFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The hem could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitCornerRelief = useCallback(
    (params: SheetMetalCornerReliefParams) => {
      const current = editor;
      if (current === null || current.kind !== "cornerRelief") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "sheet_metal_corner_relief")
          .length + 1;
      runFeatureSave(
        (version) =>
          cornerReliefFeatureCreate(
            `Corner relief${nextIndex}`,
            params,
            version,
          ),
        (version) => cornerReliefFeatureUpdate(params, version),
        current.mode === "create",
        current.featureId,
        "The corner relief could not be saved.",
      );
    },
    [editor, features, runFeatureSave],
  );

  const submitCombine = useCallback(
    (params: BooleanParams) => {
      const current = editor;
      if (current === null || current.kind !== "combine") return;
      const nextIndex =
        features.filter((f) => f.feature.type === "boolean").length + 1;
      runFeatureSave(
        (version) =>
          booleanFeatureCreate(`Combine${nextIndex}`, params, version),
        // A boolean is create-only in MB-1 (its operands are fixed at authoring);
        // the update arm is never taken but keeps runFeatureSave's shape.
        (version) => ({
          expected_tree_version: version,
          feature: { type: "boolean", version: 1, params },
        }),
        true,
        undefined,
        "The bodies could not be combined.",
      );
    },
    [editor, features, runFeatureSave],
  );
  return {
    submitExtrude,
    submitRevolve,
    submitSweep,
    submitLoft,
    submitPattern,
    submitMirror,
    submitFillet,
    submitChamfer,
    submitShell,
    submitDraft,
    submitHole,
    submitDatum,
    submitBaseFlange,
    submitEdgeFlange,
    submitHem,
    submitCornerRelief,
    submitCombine,
  };
}

export type FeatureSubmit = ReturnType<typeof useFeatureSubmit>;
