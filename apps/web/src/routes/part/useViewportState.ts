/**
 * What the viewport and the panels draw from: the ghost and gauge layers,
 * the one build-state derivation, the export binding and the mode flags.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { useMemo } from "react";

import { derivePartBuild } from "../../features/partBuild";
import { partExportBinding } from "../../features/partExport";
import { type SolvedSketchLayer } from "../../viewport/SketchScene";
import {
  patternAnchor,
  sceneDirection,
  type PatternAnchor,
} from "../../viewport/patternAnchor";
import { usePartViewStore } from "../../viewport/partView";
import { COMMAND_LABEL } from "./openEditor";
import type { PartDocument } from "./usePartDocument";
import type { PartBody } from "./usePartBody";
import type { MeasureSession } from "./useMeasureSession";
import type { SolvedSketches } from "./useSolvedSketches";
import type { FeatureCatalog } from "./useFeatureCatalog";
import type { EditorSeat } from "./useEditorSeat";
import type { TreeWrites } from "./useTreeWrites";
import type { PickSessions } from "./usePickSessions";

type ViewportStateParams = Pick<
  PartDocument,
  "partId" | "mode" | "part" | "tree" | "evaluation"
> &
  Pick<
    PartBody,
    | "bodyProperties"
    | "editor"
    | "viewMeshGlbId"
    | "body"
    | "regenerating"
    | "regenFailed"
  > &
  Pick<MeasureSession, "measureActive"> &
  Pick<SolvedSketches, "solved"> &
  Pick<FeatureCatalog, "features"> &
  Pick<EditorSeat, "extrudePreview" | "revolveGauge" | "patternPreview"> &
  Pick<TreeWrites, "treeWrite"> &
  Pick<PickSessions, "shellPickedFaces">;

export function useViewportState({
  partId,
  mode,
  part,
  tree,
  evaluation,
  bodyProperties,
  editor,
  viewMeshGlbId,
  body,
  regenerating,
  regenFailed,
  measureActive,
  solved,
  features,
  extrudePreview,
  revolveGauge,
  patternPreview,
  treeWrite,
  shellPickedFaces,
}: ViewportStateParams) {
  // The body is the hero: once a solid renders, the profile sketch that
  // defined it recedes (it sits on the body's base face — coincident scribe
  // ink would only z-fight the solid). It returns, live, on sketch re-entry.
  //
  // That rule now lives in the SCENE (`SketchScene`, via `viewport/partView`),
  // as the DEFAULT of a per-sketch view stop rather than as a law the modeler
  // cannot answer back to — UI-W2, founder: "what about the ability to enable
  // planes, sketches and bodies?". The full solved set is handed down and the
  // scene decides which layers draw, so the browser's Sketches rows and the ink
  // on screen read one derivation.
  const bodyPresent = body.data !== undefined;
  // The extrude ghost's profile layer (UI-REVIEW #8): the SOLVED sketch the
  // open extrude editor points at, resolved from the full `solved` set so the
  // ghost shows whether or not a body already exists. Absent until the editor
  // projects a valid form.
  const extrudeGhostLayer = useMemo<SolvedSketchLayer | null>(() => {
    if (extrudePreview === null) return null;
    return (
      solved.find((l) => l.featureId === extrudePreview.profileFeatureId) ??
      null
    );
  }, [extrudePreview, solved]);
  const showExtrudeGhost =
    mode === "off" &&
    editor?.kind === "extrude" &&
    extrudePreview !== null &&
    extrudeGhostLayer !== null;
  // The solved sketch the open revolve turns — resolved from the full `solved`
  // set, like the extrude ghost's layer and for the same reason: the gauge must
  // stand on the profile whether or not a body already exists (CRAFT-10).
  const revolveGaugeLayer = useMemo<SolvedSketchLayer | null>(() => {
    if (revolveGauge === null) return null;
    return (
      solved.find((l) => l.featureId === revolveGauge.profileFeatureId) ?? null
    );
  }, [revolveGauge, solved]);
  // The face the taper gauge stands on: the FIRST picked, because pick order is
  // preserved and a draft of six faces by one angle wants one instrument.
  const draftGaugeFace = shellPickedFaces[0];
  /**
   * The seed body the pattern gauges stand on, and where they stand (CRAFT-11).
   *
   * The drawn mesh is read HERE, at the integration point, and handed to
   * `PatternGaugeLayer` as props — the gauge component reaches into no store,
   * so W4's persistent selection re-sources these two expressions and leaves
   * the instrument alone. `pickGeometry` is `null` for "no mesh", never for
   * "not loaded yet" (`ModelMesh` publishes null before disposing), so a null
   * here is a row with no ghosts rather than a row to wait for.
   */
  const patternBodyGeometry = usePartViewStore((state) => state.pickGeometry);
  const patternGaugeAnchor = useMemo<PatternAnchor | null>(() => {
    if (patternPreview === null) return null;
    const box = patternBodyGeometry?.boundingBox ?? null;
    if (box === null) return null;
    return patternAnchor(
      {
        min: [box.min.x, box.min.y, box.min.z],
        max: [box.max.x, box.max.y, box.max.z],
      },
      sceneDirection(patternPreview.direction),
    );
  }, [patternPreview, patternBodyGeometry]);
  // THE ONE SET OF FACTS about the body on screen. The feature tree's SOLVE
  // cell, the inspector's STATUS cell, the EXPORT gate, the SKIP rows and the
  // partial-body notice below all read this object — they used to compute three
  // separate answers, and on a part with a broken feature the same screen said
  // "Failed", "Up to date" and "Ready" at once (AUDIT-ENGINEERING J2).
  const build = useMemo(
    () =>
      derivePartBuild({
        tree: tree.data,
        evaluation: evaluation.data,
        part: part.data,
        evaluating: evaluation.isFetching,
        treeFetching: tree.isFetching,
        regenerating,
        regenFailed,
        meshPending: viewMeshGlbId !== null && !bodyPresent && body.isFetching,
        writing: treeWrite.pending > 0,
        writtenTreeVersion: treeWrite.version,
      }),
    [
      tree.data,
      tree.isFetching,
      evaluation.data,
      evaluation.isFetching,
      part.data,
      regenerating,
      regenFailed,
      viewMeshGlbId,
      bodyPresent,
      body.isFetching,
      treeWrite,
    ],
  );
  // EXPORT, bound once and mounted twice: the Inspector's ruled strip (the
  // NOTICE surface — it has room to say the file would be partial) and the
  // command band's EXPORT group (the ACTION surface, which survives collapsing
  // the panel). Both read this binding, so the gate and the filename cannot
  // drift apart between them (EXPORT-1).
  const partExport = useMemo(
    () => partExportBinding(partId, build),
    [partId, build],
  );
  // The inspector appears when there's a body to inspect and we're not
  // sketching — sketch mode keeps the viewport dominant (chrome recedes).
  const showInspector = mode === "off" && bodyProperties !== null;
  // With a tree but no body (sketch-only / rolled back before the extrude),
  // still offer the EXPORT strip — disabled and honest about why.
  const showExportOnly =
    mode === "off" &&
    bodyProperties === null &&
    (tree.data?.features.length ?? 0) > 0;

  // A blank part — the tree has loaded with nothing in it and we're at rest.
  // The empty scene gets a first-run call to action (item 13); the grid +
  // atmosphere (Batch 1) already keep it from being a black void.
  const isEmptyPart =
    mode === "off" &&
    editor === null &&
    !measureActive &&
    tree.data !== undefined &&
    features.length === 0;

  // The open command scopes the band + names the mode (breadcrumb + lock).
  // No runtime fallback: COMMAND_LABEL is total over OpenEditor["kind"], so
  // an unmapped editor kind cannot compile, let alone unlock the band.
  const activeCommand = editor === null ? null : COMMAND_LABEL[editor.kind];
  return {
    extrudeGhostLayer,
    showExtrudeGhost,
    revolveGaugeLayer,
    draftGaugeFace,
    patternBodyGeometry,
    patternGaugeAnchor,
    build,
    partExport,
    showInspector,
    showExportOnly,
    isEmptyPart,
    activeCommand,
  };
}

export type ViewportState = ReturnType<typeof useViewportState>;
