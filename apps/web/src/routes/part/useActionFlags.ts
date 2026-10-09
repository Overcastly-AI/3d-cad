/**
 * The datum editor's references and the discrete actions' busy/error
 * state (STEP import, flat pattern, offset plane).
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { useMemo, useState } from "react";

import type { SketchLineOption } from "../../features/datumAngle";
import type { PartBody } from "./usePartBody";
import type { FeatureCatalog } from "./useFeatureCatalog";

type ActionFlagsParams = Pick<PartBody, "editor"> &
  Pick<FeatureCatalog, "features">;

export function useActionFlags({ editor, features }: ActionFlagsParams) {
  // Earlier datum features offered to the datum editor as references (the
  // offset-from base + the midplane sides). Create authors at the tip, so every
  // existing datum is earlier; an edit sees only the datums strictly before it
  // (the strict-backward rule — a datum can't reference itself or a later one).
  const datumEditorRefs = useMemo(() => {
    if (editor?.kind !== "datum") return [];
    const editingId = editor.featureId;
    const foundAt = editingId
      ? features.findIndex((f) => f.id === editingId)
      : -1;
    const bound = foundAt < 0 ? features.length : foundAt;
    return features
      .filter((f, i) => f.feature.type === "datum" && i < bound)
      .map((f) => ({ id: f.id, name: f.name }));
  }, [editor, features]);
  // Lines of the sketches before the datum: what a plane at an angle can turn
  // about (the same strict-backward bound as the datum references above).
  const datumSketchLines = useMemo((): SketchLineOption[] => {
    if (editor?.kind !== "datum") return [];
    const editingId = editor.featureId;
    const foundAt = editingId
      ? features.findIndex((f) => f.id === editingId)
      : -1;
    const bound = foundAt < 0 ? features.length : foundAt;
    const lines: SketchLineOption[] = [];
    features.slice(0, bound).forEach((f) => {
      if (f.feature.type !== "sketch") return;
      for (const entity of f.feature.params.entities) {
        if (entity.kind !== "line") continue;
        lines.push({
          sketchId: f.id,
          sketchName: f.name,
          entityId: entity.id,
          construction: entity.construction === true,
        });
      }
    });
    return lines;
  }, [editor, features]);
  // STEP import (a discrete toolbar action, no editor panel): busy + the server
  // envelope's own message on rejection, surfaced in the viewport HUD.
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  // Flat pattern (a discrete action, no editor panel): unfolding the sheet body
  // creates a drawing + a lone flat-pattern view referencing this part, then
  // navigates to it. Busy + the server envelope's own message on rejection.
  const [flatPatternBusy, setFlatPatternBusy] = useState(false);
  const [flatPatternError, setFlatPatternError] = useState<string | null>(null);
  // The profile-only DXF cut path (AUDIT-PRODUCT F-2a) — a download, not a
  // navigation, so it gets its own busy flag but SHARES the flat-pattern error
  // surface: both are "the blank could not be produced", and a second alert box
  // in the same corner saying a near-identical sentence is how a UI starts
  // lying about how many things went wrong.
  const [flatDxfBusy, setFlatDxfBusy] = useState(false);
  // Inline offset-plane authoring (the plane-pick "+ Offset plane" path).
  const [offsetPlaneBusy, setOffsetPlaneBusy] = useState(false);
  const [offsetPlaneError, setOffsetPlaneError] = useState<string | null>(null);
  return {
    datumEditorRefs,
    datumSketchLines,
    importing,
    setImporting,
    importError,
    setImportError,
    flatPatternBusy,
    setFlatPatternBusy,
    flatPatternError,
    setFlatPatternError,
    flatDxfBusy,
    setFlatDxfBusy,
    offsetPlaneBusy,
    setOffsetPlaneBusy,
    offsetPlaneError,
    setOffsetPlaneError,
  };
}

export type ActionFlags = ReturnType<typeof useActionFlags>;
