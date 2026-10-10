/**
 * The create commands' openers, each seeding its editor from the tree or the
 * pre-selection.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { useCallback } from "react";

import { useMeasureStore } from "../../measure/store";
import { type FeatureResponse } from "../../api/parts";
import { defaultDatumForm } from "../../features/datum";
import { isStraightEdge } from "../../features/datumAngle";
import {
  defaultExtrudeForm,
  defaultProfileId,
  seededProfileId,
  optionProvenance,
  closedProfileOptions,
} from "../../features/extrude";
import {
  axisOptions,
  defaultAxisId,
  defaultRevolveForm,
} from "../../features/revolve";
import { defaultPatternForm } from "../../features/pattern";
import { scopeFeature, type ScopeSeed } from "../../features/patternScope";
import {
  defaultSweepForm,
  defaultSweepPathId,
  defaultSweepProfileId,
} from "../../features/sweep";
import { defaultLoftForm, defaultLoftSections } from "../../features/loft";
import {
  defaultBaseFlangeForm,
  defaultCornerReliefForm,
  defaultEdgeFlangeForm,
  defaultHemForm,
  edgeFlangeOptions,
} from "../../features/sheetMetal";
import { defaultMirrorForm } from "../../features/mirror";
import { defaultChamferForm, defaultFilletForm } from "../../features/modify";
import { defaultShellForm } from "../../features/shell";
import { defaultDraftForm } from "../../features/draft";
import { defaultHoleForm } from "../../features/hole";
import {
  preselectedEdges,
  preselectedFace,
  preselectedFaces,
  usePreselectStore,
} from "../../features/preselect";
import type { PartDocument } from "./usePartDocument";
import type { PickState } from "./usePickState";
import type { EditorSeat } from "./useEditorSeat";
import type { PickOverlays } from "./usePickOverlays";

type FeatureOpenersParams = Pick<PartDocument, "lengthUnit" | "tree"> &
  Pick<PickState, "setHolePick" | "setHolePickError"> &
  Pick<
    EditorSeat,
    "setSelectedFeatureId" | "patternScopeSeed" | "setEditorError" | "setEditor"
  > &
  Pick<PickOverlays, "bodyFeatureId">;

export function useFeatureOpeners({
  lengthUnit,
  tree,
  setHolePick,
  setHolePickError,
  setSelectedFeatureId,
  patternScopeSeed,
  setEditorError,
  setEditor,
  bodyFeatureId,
}: FeatureOpenersParams) {
  /**
   * Open the Extrude editor, seeded on `seedProfileId` when one is named and on
   * the tree's default profile otherwise.
   *
   * ONE opener with an optional noun, rather than a second path for the
   * viewport's proposal: everything downstream — the provenance that decides
   * the direction default (FB-4), the form, the drag handle — must be identical
   * however the command was started, and two constructions of the same editor
   * would drift silently rather than fail (FLOW-B1).
   *
   * The `typeof` guard is load-bearing, not defensive noise: this same callback
   * is handed to the band's Extrude button as an `onClick`, so React calls it
   * with a `MouseEvent` as its first argument. Anything that is not a profile
   * id means "no seed".
   *
   * A NAMED SEED THE TREE NO LONGER OFFERS IS A REFUSAL, NOT A FALLBACK (W2
   * review, finding 3). This used to fall through to `defaultProfileId`, so a
   * chip whose `aria-label` said "Extrude Sketch2" could open the editor
   * holding whatever the tree's default happened to be — the silent wrong noun
   * that the cross-agent `defaultPrevented` contract exists to prevent,
   * arriving by a different route. Both sides read the same `closedProfileOptions`
   * today and so agree; a tree refetch landing between the chip's render and
   * the click, a rollback or an undo is all it would take. A chip that does
   * nothing is honest; a chip that opens a different sketch is not.
   */
  const openCreateExtrude = useCallback(
    (seedProfileId?: string) => {
      const features = tree.data?.features ?? [];
      const profiles = closedProfileOptions(features);
      const profileId = seededProfileId(
        profiles,
        features,
        typeof seedProfileId === "string" ? seedProfileId : null,
      );
      if (profileId === null) return;
      useMeasureStore.getState().deactivate();
      setEditorError(null);
      setSelectedFeatureId(null);
      setEditor({
        kind: "extrude",
        mode: "create",
        // The seat of the seeded profile decides the direction default: a sketch
        // on a model face cuts INTO the material, a datum plane has no material
        // side to infer one from (FB-4).
        initial: defaultExtrudeForm(
          profileId,
          optionProvenance(profiles, profileId),
        ),
      });
    },
    [tree.data],
  );

  const openCreateRevolve = useCallback(() => {
    const featureList = tree.data?.features ?? [];
    const profileId = defaultProfileId(featureList);
    if (profileId === "") return;
    const axes = axisOptions(featureList, profileId);
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "revolve",
      mode: "create",
      initial: defaultRevolveForm(profileId, defaultAxisId(axes)),
    });
  }, [tree.data]);

  // A sweep references TWO earlier sketches (a closed profile + a path),
  // so it seeds both slots from the tree — the first sketch as the profile, the
  // first other sketch as the path — and the user retargets either in the form.
  const openCreateSweep = useCallback(() => {
    const featureList = tree.data?.features ?? [];
    const profileId = defaultSweepProfileId(featureList);
    const pathId = defaultSweepPathId(featureList, profileId);
    if (profileId === "" || pathId === "") return;
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "sweep",
      mode: "create",
      initial: defaultSweepForm(profileId, pathId),
    });
  }, [tree.data]);

  // A loft references an ORDERED LIST of ≥2 earlier sketches (its sections),
  // so it seeds the first two sketches in build order as the initial stack; the
  // user retargets, reorders, or adds more sections in the editor.
  const openCreateLoft = useCallback(() => {
    const featureList = tree.data?.features ?? [];
    const initialSections = defaultLoftSections(featureList);
    if (initialSections.length < 2) return;
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "loft",
      mode: "create",
      initial: defaultLoftForm(initialSections),
    });
  }, [tree.data]);

  // A pattern needs no sketch profile — it repeats the body, or the FEATURE the
  // tree named — so it only requires a solid to exist (canModify), unlike
  // extrude/revolve.
  //
  // IT KEEPS THE SELECTION, and it is the only opener here that does, alongside
  // its mirror twin (REACH-2-FLOW P1-3). Every other verb seeds from a FACE or
  // EDGE preselect, which lives in `usePreselectStore` and survives the editor
  // on its own; these two seed from `selectedFeatureId`, so clearing it at the
  // door destroys the very thing that made the proposal — and Cancel then has
  // nothing to hand back, costing the user the whole click/Escape/press
  // sequence to try again. Reading the seed before clearing (which is what this
  // did) kept the FORM right and left the frame wrong: nothing echoed the
  // subject while the editor named it, and backing out was a dead end.
  //
  // Keeping it is not merely undo-safe, it is what makes the subject visible:
  // the tree row keeps its rail, the timeline chip its edge, and the viewport
  // its feature-localized tint — `selectionActive` deliberately does not gate
  // on `editor === null`, precisely so a selection stays lit through the
  // command it armed.
  const openCreatePattern = useCallback(() => {
    const seed = patternScopeSeed;
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setEditor({
      kind: "pattern",
      mode: "create",
      initial: defaultPatternForm(seed),
    });
  }, [patternScopeSeed]);

  // Fillet/chamfer, like a pattern, act on the current BODY via a geometric
  // edge-selector predicate (no sketch profile) — they only need a solid to
  // exist (canModify), so they mirror openCreatePattern's guard.
  // Both seed from the edges the cursor already has selected (UI-W3): picking
  // three edges and then choosing Fillet is how a modeller works, and until
  // now that selection was thrown away at the door. A seeded editor opens in
  // "pick" mode — the picks ARE the selector — and an empty one keeps the
  // all-edges rule default.
  const openCreateFillet = useCallback(() => {
    const picked = preselectedEdges(
      usePreselectStore.getState(),
      bodyFeatureId,
    );
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "fillet",
      mode: "create",
      initial: {
        ...defaultFilletForm(),
        ...(picked.length > 0 ? { mode: "pick" as const } : {}),
      },
      initialPicked: [...picked],
    });
  }, [bodyFeatureId]);

  const openCreateChamfer = useCallback(() => {
    const picked = preselectedEdges(
      usePreselectStore.getState(),
      bodyFeatureId,
    );
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "chamfer",
      mode: "create",
      initial: {
        ...defaultChamferForm(),
        ...(picked.length > 0 ? { mode: "pick" as const } : {}),
      },
      initialPicked: [...picked],
    });
  }, [bodyFeatureId]);

  // A shell, like fillet/chamfer/pattern, hollows the current BODY (no sketch
  // profile) — it only needs a solid to exist (canModify), so it mirrors their
  // guard. It opens with zero picked faces: a sealed hollow is a valid default.
  const openCreateShell = useCallback(() => {
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "shell",
      mode: "create",
      initial: defaultShellForm(),
      // The faces the cursor already has selected are the faces to leave open
      // (UI-W3) — an empty selection still means a sealed hollow.
      initialPickedFaces: preselectedFaces(
        usePreselectStore.getState(),
        bodyFeatureId,
      ).map((face) => face.signature),
    });
  }, [bodyFeatureId]);

  // A draft, like shell, tapers the current BODY's picked faces (no sketch
  // profile) — it only needs a solid to exist (canModify), so it mirrors the
  // shell guard. It opens with zero picked faces; Apply stays disabled until at
  // least one face is picked (a draft with no faces is `no_draft_faces`).
  const openCreateDraft = useCallback(() => {
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "draft",
      mode: "create",
      initial: defaultDraftForm(),
      // Seeded from the cursor selection (UI-W3); Apply stays gated until at
      // least one face is chosen either way.
      initialPickedFaces: preselectedFaces(
        usePreselectStore.getState(),
        bodyFeatureId,
      ).map((face) => face.signature),
    });
  }, [bodyFeatureId]);

  // A hole, like fillet/shell/draft, modifies the current BODY (no sketch
  // profile) — it only needs a solid to exist (canModify), so it mirrors their
  // guard.
  //
  // UI-W3, and the reason this item exists: the hole opens PLACED on whatever
  // face the cursor already had selected (drill point seeded to its centre), so
  // the anchor block reads as confirmation and the modeller types a diameter
  // and hits Enter. With nothing selected the face pick is ARMED on open, so
  // clicking a face just takes it — no arming step, which is the other half of
  // the "must select the same face twice" complaint.
  const openCreateHole = useCallback(() => {
    const seed = preselectedFace(usePreselectStore.getState(), bodyFeatureId);
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "hole",
      mode: "create",
      initial: defaultHoleForm(seed, lengthUnit),
    });
    setHolePickError(null);
    setHolePick(seed === null ? "face" : null);
  }, [bodyFeatureId, lengthUnit]);

  // A mirror, like pattern/fillet/shell, reflects the current BODY about a
  // plane (no sketch profile) — it only needs a solid to exist (canModify), so
  // it mirrors those guards. v1 needs only a plane choice: no face/point pick.
  // Keeps the selection for the same reason `openCreatePattern` does — the two
  // verbs share one subject and must not treat it two different ways.
  const openCreateMirror = useCallback(() => {
    const seed = patternScopeSeed;
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setEditor({
      kind: "mirror",
      mode: "create",
      initial: defaultMirrorForm(seed),
    });
  }, [patternScopeSeed]);

  /**
   * THE SEED GESTURE, TAKEN DIRECTLY FROM A ROW (REACH-2-FLOW P1-4).
   *
   * The advertised flow is "name Hole1, then repeat it". Reaching the verb
   * through the BAND requires the row to be selected, and selecting a row opens
   * that feature's own editor — which then locks the band and the accelerators,
   * so the gesture in practice is "open an editor nobody asked for, abandon it,
   * then press P". That is a dialog charged as a toll, and it is the flow
   * mandate's "no dead ends" test failing.
   *
   * Offering the two verbs on the row's own menu removes the toll without
   * re-teaching what a click does: right-click Hole1 -> Repeat Hole1, and the
   * feature's editor never opens. It is also the incumbent gesture — a
   * right-click on a timeline feature in Fusion/Onshape/SolidWorks asks exactly
   * this question, "what can I do with this one?" — and it costs no band width,
   * so the resting chrome is unchanged.
   *
   * The seed is passed EXPLICITLY rather than through `setSelectedFeatureId` +
   * `patternScopeSeed`: that memo is derived from state this render has not
   * committed yet, so routing through it would open the editor on the PREVIOUS
   * selection. The selection is still set, because the row genuinely is the
   * subject from here on and the band must say so.
   */
  const openScopedVerb = useCallback(
    (verb: "pattern" | "mirror", feature: FeatureResponse) => {
      const picked = scopeFeature(feature);
      if (picked === null) return;
      const seed: ScopeSeed = { ...picked, fromSelection: true };
      useMeasureStore.getState().deactivate();
      setEditorError(null);
      setSelectedFeatureId(feature.id);
      setEditor(
        verb === "pattern"
          ? {
              kind: "pattern",
              mode: "create",
              initial: defaultPatternForm(seed),
            }
          : {
              kind: "mirror",
              mode: "create",
              initial: defaultMirrorForm(seed),
            },
      );
    },
    [],
  );

  // A datum plane needs no sketch/body — it's a construction plane parallel to
  // an origin datum. Available as soon as the tree exists (its own feature row).
  const openCreateDatum = useCallback(() => {
    const preselect = usePreselectStore.getState();
    const seed = preselectedFace(preselect, bodyFeatureId);
    // A selected straight edge means "a plane at an angle about THIS"
    // (Fusion's Plane at Angle): the most recent edge pick, if it is straight.
    const [edge] = preselectedEdges(preselect, bodyFeatureId, 1);
    const edgeSeed =
      edge !== undefined && bodyFeatureId !== null && isStraightEdge(edge)
        ? { signature: edge, anchorId: bodyFeatureId }
        : null;
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    // A selected face means "a plane on THIS" (UI-W3) — the datum opens as an
    // on_face datum sitting on it, instead of the generic 30 mm-above-XY form.
    setEditor({
      kind: "datum",
      mode: "create",
      initial: defaultDatumForm(seed, edgeSeed),
    });
  }, [bodyFeatureId]);

  // A base flange thickens a sketch profile to gauge — the sheet-metal part's
  // first body (sheet-metal.md §4.1). Like extrude it needs a solved sketch to
  // consume, so it mirrors openCreateExtrude's profile guard.
  const openCreateBaseFlange = useCallback(() => {
    const profileId = defaultProfileId(tree.data?.features ?? []);
    if (profileId === "") return;
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "baseFlange",
      mode: "create",
      initial: defaultBaseFlangeForm(profileId),
    });
  }, [tree.data]);

  // An edge flange folds a leg off ONE picked straight edge of the sheet body
  // (sheet-metal.md §4.2). It picks like fillet/chamfer (single-select), so it
  // only needs a sheet body to exist.
  const openCreateEdgeFlange = useCallback(() => {
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "edgeFlange",
      mode: "create",
      initial: defaultEdgeFlangeForm(),
      // ONE edge folds a flange, so a multi-edge selection seeds its most
      // recent member rather than an arbitrary one (UI-W3).
      initialPicked: [
        ...preselectedEdges(usePreselectStore.getState(), bodyFeatureId, 1),
      ],
    });
  }, [bodyFeatureId]);

  // A hem folds ONE picked straight edge 180° back onto the sheet (parity §2) —
  // closed (pressed flat) or open (a deliberate gap), chosen in the editor. It
  // picks like an edge flange (single-select), so it only needs a sheet body.
  const openCreateHem = useCallback(() => {
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "hem",
      mode: "create",
      initial: defaultHemForm(),
      initialPicked: [
        ...preselectedEdges(usePreselectStore.getState(), bodyFeatureId, 1),
      ],
    });
  }, [bodyFeatureId]);

  // A corner relief notches the shared corner of two edge flanges (parity §4.4).
  // It references two edge-flange FEATURES (not an edge pick), so it seeds the
  // first two edge flanges in tree order; the user retargets either in the form.
  const openCreateCornerRelief = useCallback(() => {
    const opts = edgeFlangeOptions(tree.data?.features ?? []);
    const a = opts[0]?.id ?? "";
    const b = opts[1]?.id ?? "";
    if (a === "" || b === "") return;
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "cornerRelief",
      mode: "create",
      initial: defaultCornerReliefForm(a, b),
    });
  }, [tree.data]);
  return {
    openCreateExtrude,
    openCreateRevolve,
    openCreateSweep,
    openCreateLoft,
    openCreatePattern,
    openCreateFillet,
    openCreateChamfer,
    openCreateShell,
    openCreateDraft,
    openCreateHole,
    openCreateMirror,
    openScopedVerb,
    openCreateDatum,
    openCreateBaseFlange,
    openCreateEdgeFlange,
    openCreateHem,
    openCreateCornerRelief,
  };
}

export type FeatureOpeners = ReturnType<typeof useFeatureOpeners>;
