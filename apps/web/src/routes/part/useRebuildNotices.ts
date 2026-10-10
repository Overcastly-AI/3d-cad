/**
 * Rebuild notices at the editor seat and the sketch-count gates.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { useMemo } from "react";

import { friendlyFeatureError } from "../../features/featureErrors";
import {
  describeInputError,
  INPUT_ERROR_CODES,
} from "../../features/fieldFormulas";
import type { PartDocument } from "./usePartDocument";
import type { PartBody } from "./usePartBody";
import type { FeatureCatalog } from "./useFeatureCatalog";
import type { EditorSeat } from "./useEditorSeat";

type RebuildNoticesParams = Pick<PartDocument, "evaluation"> &
  Pick<PartBody, "editor"> &
  Pick<FeatureCatalog, "sketchProfiles"> &
  Pick<EditorSeat, "lastSavedFeatureId" | "rebuildNoticeDismissed">;

export function useRebuildNotices({
  evaluation,
  editor,
  sketchProfiles,
  lastSavedFeatureId,
  rebuildNoticeDismissed,
}: RebuildNoticesParams) {
  // The last-saved feature's rebuild error (UX audit #20e), surfaced at the
  // editor seat so it reads where the user just clicked Create/Save — not only
  // in the tree across the screen. Dismissible; the next save re-arms it.
  const rebuildNotice = useMemo<string | null>(() => {
    if (lastSavedFeatureId === null || rebuildNoticeDismissed) return null;
    const result = evaluation.data?.features.find(
      (f) => f.feature_id === lastSavedFeatureId,
    );
    if (result?.status !== "error" || result.error == null) return null;
    // A formula's `input_error` reads in the field's words, as in the tree.
    return INPUT_ERROR_CODES.has(result.error.code)
      ? describeInputError(result.error.message)
      : result.error.message;
  }, [lastSavedFeatureId, rebuildNoticeDismissed, evaluation.data]);

  // The rebuild error of the SWEEP being edited, in the tree's friendly copy,
  // shown inside its editor (TWIST-TO-SWEEP): a twist refused for its path
  // (`twist_path_unsupported`) or for its cost (`twist_failed`) is cured by a
  // control in that editor, so the reason reads next to the control.
  const sweepRebuildError = useMemo<string | null>(() => {
    if (editor === null || editor.kind !== "sweep") return null;
    if (editor.mode !== "edit" || editor.featureId === undefined) return null;
    const result = evaluation.data?.features.find(
      (f) => f.feature_id === editor.featureId,
    );
    if (result === undefined || result.status !== "error") return null;
    if (result.error == null) return null;
    return friendlyFeatureError(
      result.error.code,
      result.error.message,
      "sweep",
    );
  }, [editor, evaluation.data]);

  // A solved sketch must exist before an extrude or revolve can consume one.
  const hasSolvedSketch =
    sketchProfiles.length > 0 &&
    (evaluation.data?.features.some(
      (f) => f.status === "ok" && f.data?.kind === "solved_sketch",
    ) ??
      false);
  // A sweep needs TWO sketch features to reference (a profile + a path), both
  // solved so their wires exist — hence ≥2 sketches AND a solve has landed.
  const canSweep = sketchProfiles.length >= 2 && hasSolvedSketch;
  // A loft blends through ≥2 ordered section sketches — the same gate as sweep
  // (two sketch features must exist and a solve must have produced their wires).
  const canLoft = sketchProfiles.length >= 2 && hasSolvedSketch;
  return {
    rebuildNotice,
    sweepRebuildError,
    hasSolvedSketch,
    canSweep,
    canLoft,
  };
}

export type RebuildNotices = ReturnType<typeof useRebuildNotices>;
