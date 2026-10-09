/**
 * What the feature tree offers: profiles, bodies, sheet-metal state, datum
 * planes and the per-profile axis / path choices.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { useCallback, useMemo, useState } from "react";

import { type EvaluateTreeResult } from "../../api/parts";
import { useNextStepAfterBuild } from "../../components/useNextStep";
import { profileOptions } from "../../features/extrude";
import { type AxisOption, axisOptions } from "../../features/revolve";
import { pathOptions, type ProfileOption } from "../../features/sweep";
import { partBodies } from "../../features/bodies";
import {
  canAuthorCornerRelief,
  edgeFlangeOptions,
  isSheetMetalPart,
  sheetMetalDefaults,
} from "../../features/sheetMetal";
import {
  faceSpecFromDatum,
  resolveDatumPlaneOptions,
  type SketchPlaneRef,
  type SketchPlaneSpec,
} from "../../sketch/plane";
import { NO_BODIES } from "./openEditor";
import type { PartDocument } from "./usePartDocument";
import type { SolvedSketches } from "./useSolvedSketches";

type FeatureCatalogParams = Pick<
  PartDocument,
  "partId" | "tree" | "evaluation"
> &
  Pick<SolvedSketches, "datumById">;

export function useFeatureCatalog({
  partId,
  tree,
  evaluation,
  datumById,
}: FeatureCatalogParams) {
  // ---------------------------------------------------------------------
  // Extrude authoring + feature-tree interactions. Discrete user actions
  // (not the debounced sketch chain): each reads the freshest tree_version,
  // retries once on a stale-version race, then invalidates the tree + the
  // evaluate so the body updates through the #2 render path.
  // ---------------------------------------------------------------------
  const features = tree.data?.features ?? [];
  const sketchProfiles = useMemo(() => profileOptions(features), [features]);
  // What the extrude / revolve / sweep PROFILE pickers offer: no apex sketch.
  const closedProfiles = useMemo(
    () => sketchProfiles.filter((option) => option.apex !== true),
    [sketchProfiles],
  );
  /**
   * FLOW-B3 — what the band proposes now that a feature has landed, or null.
   *
   * Gated on a BUILD, not on the shape of the tree (W2 review, finding 6):
   * `useNextStepAfterBuild` arms only for a feature this workspace watched
   * arrive, so opening a part whose last feature is an old extrude proposes
   * nothing. The table it wraps — which verb follows which, and the much longer
   * list of verbs that propose NOTHING — is `components/nextStep.ts`.
   */
  const nextStep = useNextStepAfterBuild(tree.data?.features);
  // The part's body set (multi-body §MB-1) — drives the Bodies panel and the
  // Combine tool's target/tool pickers. One body is the common case; a
  // `merge: false` add (or an import) starts a second.
  //
  // The evaluate result decides WHICH bodies exist (FAILED-EXTRUDE-BODIES-
  // GHOST-1): a failed extrude is not a body, and Export, which writes the same
  // last-good state, already said so. The tree only names them.
  //
  // HELD ACROSS A PENDING EVALUATE (review S1 on c001220). The evaluate query
  // is keyed on the tree version, so after every edit, undo or redo there is
  // no result until the new one lands, and falling back to the tree replay
  // then put the failed feature's ghost row back for the length of a rebuild.
  // The last result for THIS part stands in; the replay is used only before
  // any result for it has ever arrived. Held in state, set during render (the
  // documented "adjust state when a prop changes" pattern), so the panel
  // never renders a frame without it.
  const [heldBodies, setHeldBodies] = useState<{
    partId: string;
    bodies: NonNullable<EvaluateTreeResult["bodies"]>;
  } | null>(null);
  // `NO_BODIES` rather than a fresh `[]`: a new array every render would
  // never equal the held one, and the set-during-render below would loop.
  const liveBodies =
    evaluation.data === undefined
      ? undefined
      : (evaluation.data.bodies ?? NO_BODIES);
  if (
    liveBodies !== undefined &&
    (heldBodies?.partId !== partId || heldBodies.bodies !== liveBodies)
  ) {
    setHeldBodies({ partId, bodies: liveBodies });
  }
  const evaluatedBodies =
    liveBodies ?? (heldBodies?.partId === partId ? heldBodies.bodies : null);
  const bodies = useMemo(
    () => partBodies(features, evaluatedBodies),
    [features, evaluatedBodies],
  );
  // Per-body lump count from the evaluate wire (§MB-4c): a disjoint-union /
  // multi-solid-import body reports `lumps > 1`, which the Bodies panel flags.
  // Keyed by the body's base feature id (its §MB-0 identity) so a row maps to its
  // count; absent for a tree with no body-affecting feature (the panel shows none).
  const lumpsByFeature = useMemo(() => {
    const map = new Map<string, number>();
    for (const entry of evaluation.data?.bodies ?? []) {
      map.set(entry.base_feature_id, entry.lumps);
    }
    return map;
  }, [evaluation.data?.bodies]);
  // Sheet-metal state: the part is sheet metal once it has a base flange, and
  // that base flange's gauge / bend-radius / K become the defaults every edge
  // flange inherits (sheet-metal.md §4.2). Edge flange + Flat pattern light up
  // from `isSheetMetal`; the edge-flange editor shows `smDefaults`.
  const smDefaults = useMemo(() => sheetMetalDefaults(features), [features]);
  const isSheetMetal = useMemo(() => isSheetMetalPart(features), [features]);
  // Corner relief references TWO edge-flange FEATURES (not an edge pick), so it
  // lights up only with ≥2 edge flanges, and the editor lists them by name.
  const edgeFlangeOpts = useMemo(() => edgeFlangeOptions(features), [features]);
  const canCornerRelief = useMemo(
    () => canAuthorCornerRelief(features),
    [features],
  );
  // Datum features already in the tree, offered as reusable sketch planes in
  // the plane picker (a standalone datum seats many sketches — DRY). The SAME
  // derivation the section-view author reads (`resolveDatumPlaneOptions`), so a
  // datum FeatureRef means exactly the same plane in both flows (one source).
  const datumPlaneOptions = useMemo(
    () => resolveDatumPlaneOptions(features),
    [features],
  );
  /**
   * The inverse of `planeRefFromSpec`: a PERSISTED sketch plane ref back to the
   * viewport spec the sketcher draws and poses its camera with. Re-opening a
   * saved sketch (SKETCH-1) is the one flow that needs it — every other plane
   * spec is minted by the pick that chose it.
   *
   * The datum branches reuse the ONE datum derivation the plane picker and the
   * section author already read, plus the `on_face` reconstruction the solved
   * overlay uses (an on-face datum has no world-frame walk, so
   * `resolveDatumPlaneOptions` deliberately omits it — its face signature is in
   * its own params). Null means the plane is genuinely unresolvable client-side
   * (a rolled-back/deleted datum, or a face-picked midplane side); the caller
   * says so rather than opening a sketcher on a plane it cannot place.
   */
  const specFromPlaneRef = useCallback(
    (ref: SketchPlaneRef): SketchPlaneSpec | null => {
      if (ref.kind === "datum_plane")
        return { kind: "origin", base: ref.plane };
      const option = datumPlaneOptions.find((o) => o.id === ref.feature_id);
      if (option !== undefined) return option.spec;
      const params = datumById.get(ref.feature_id);
      if (params?.kind === "on_face") {
        return faceSpecFromDatum(
          ref.feature_id,
          params.face.selector.signature,
          params.offset_mm,
        );
      }
      return null;
    },
    [datumPlaneOptions, datumById],
  );
  // Axis line-entity choices per profile sketch — the revolve editor scopes its
  // axis picker to the selected profile's own lines.
  const axesByProfile = useMemo(() => {
    const map: Record<string, AxisOption[]> = {};
    for (const profile of sketchProfiles) {
      map[profile.id] = axisOptions(features, profile.id);
    }
    return map;
  }, [sketchProfiles, features]);
  // Path choices per profile sketch — the sweep editor scopes its path picker
  // to every OTHER sketch (a sketch fills one slot: closed profile OR open path).
  const pathsByProfile = useMemo(() => {
    const map: Record<string, ProfileOption[]> = {};
    for (const profile of sketchProfiles) {
      map[profile.id] = pathOptions(features, profile.id);
    }
    return map;
  }, [sketchProfiles, features]);
  return {
    features,
    sketchProfiles,
    closedProfiles,
    nextStep,
    bodies,
    lumpsByFeature,
    smDefaults,
    isSheetMetal,
    edgeFlangeOpts,
    canCornerRelief,
    datumPlaneOptions,
    specFromPlaneRef,
    axesByProfile,
    pathsByProfile,
  };
}

export type FeatureCatalog = ReturnType<typeof useFeatureCatalog>;
