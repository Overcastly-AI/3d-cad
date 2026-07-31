/**
 * Sketch-mode state (zustand) — plane pick, tool sequence, the local entity
 * buffer, and the constraint/selection layer. All geometry and constraint
 * transitions are the pure functions of `tools.ts` / `pick.ts` /
 * `constraints.ts`; this store only holds state.
 *
 * Persistence model (the live parametric loop): entities/constraints edits
 * bump `revision`; once the sketch is bound to a persisted feature
 * (`featureId`), `PartPage` debounce-saves every revision and feeds the
 * solved evaluate payload back through `adoptSolved` — which does NOT bump
 * `revision`, so the loop terminates.
 */
import { create } from "zustand";

import {
  applyConstraintAction,
  reconcileConstraints,
  toggleConstruction,
  type ConstraintAction,
  type DimensionCommit,
  type DimensionEditorTarget,
  type SketchConstraint,
  type SolvedDimension,
  type SolveInfo,
} from "./constraints";
import { toggleCornerPick, type CornerOp } from "./corner";
import { toggleMirrorTarget, type MirrorAxis } from "./mirror";
import type { DatumPlaneName, Point2D, SketchPlaneSpec } from "./plane";
import { pickCandidates, toggleSelection, type SketchPick } from "./pick";
import { resolveSnap, type SnapCandidate, type SnapResolution } from "./snap";
import {
  escapeAction,
  finishPlacement as finishPlacementSequence,
  placePoint,
  placesPoints,
  type SketchEntity,
  type SketchTool,
} from "./tools";

/**
 * Grid snap step (mm) the sketch opens with. The LIVE step is
 * `snapStepMm` on the store and is set with `setSnapStep` — this is only the
 * starting value, so a settings surface has one number to write to rather than
 * a literal to fight (UI-W5).
 */
export const DEFAULT_SNAP_STEP_MM = 1;

export type SketchMode = "off" | "plane" | "draw";

export interface SketchState {
  mode: SketchMode;
  /**
   * Chosen sketch plane (set on entering `draw`) — an origin datum OR an
   * authored offset datum feature. Null until a plane is picked.
   */
  plane: SketchPlaneSpec | null;
  tool: SketchTool;
  /** Points of the in-progress placement sequence (plane mm, snapped). */
  pending: Point2D[];
  /** Locally buffered entities; adopt solved positions once persisted. */
  entities: SketchEntity[];
  /** Constraints authored this session (persisted with the entities). */
  constraints: SketchConstraint[];
  /** Next sketch-local id index (`e1`, `e2`, …). */
  nextIdIndex: number;
  /** GRID snap toggle (G). Entity snapping is always live — Ctrl/Cmd suppresses. */
  snapEnabled: boolean;
  /** Live grid step (mm) — configurable, see `DEFAULT_SNAP_STEP_MM`. */
  snapStepMm: number;
  /** Ctrl/Cmd held: every snap off, freehand placement (UI-W5 polarity). */
  snapSuppressed: boolean;
  /** Shift held: the aim is locked to an axis through the placement anchor. */
  axisLock: boolean;
  /**
   * What the current aim actually took — endpoint / midpoint / centre /
   * intersection / tangent / perpendicular / axis lock — so the viewport can
   * NAME it before the click commits. Null for a grid or freehand point.
   */
  snapCandidate: SnapCandidate | null;
  /**
   * The last RAW (unsnapped) pointer point and its px→mm tolerance. Held so a
   * modifier pressed while the pointer is stationary re-resolves the aim
   * immediately, instead of lying until the next mouse move.
   */
  aimRaw: Point2D | null;
  aimToleranceMm: number;
  /** Pointer position in plane mm, already snapped; null when off-plane. */
  cursor: Point2D | null;
  /** Plane under the pointer / focused cell during plane pick. */
  hoveredPlane: DatumPlaneName | null;
  /** Current selection (select tool): entities and defining points. */
  selection: SketchPick[];
  /** Pick under the pointer (select tool) — hover highlight. */
  hoverPick: SketchPick | null;
  /** Selected constraint glyph (index into `constraints`), for Delete. */
  selectedConstraint: number | null;
  /** Open inline dimension editor, or null. */
  dimensionEdit: DimensionEditorTarget | null;
  /** Persisted feature this session is bound to (null = unsaved). */
  featureId: string | null;
  /** Monotonic edit counter — the sync loop persists every bump. */
  revision: number;
  /** Latest solve feedback for the bound feature (DRO + diagnostics). */
  solve: SolveInfo | null;
  /**
   * Per-dimension solve readouts from the last evaluate, keyed off
   * `constraint_index` (a driving dim's evaluated value / a driven dim's
   * measured value). Empty until the first solve; drives the glyph labels so an
   * expression `width/2` shows as its resolved `10`.
   */
  solvedDimensions: SolvedDimension[];
  /** Transient strip hint (invalid constraint action, duplicates, …). */
  hint: string | null;
  /**
   * A pending trim/extend the scene armed on a target click; PartPage owns the
   * network effect that consumes it (the store stays side-effect-free). The
   * `nonce` lets that effect fire exactly once per request.
   */
  edit: {
    op: "trim" | "extend";
    target: string;
    pick: Point2D;
    nonce: number;
  } | null;
  /** True while a geometry edit (trim/extend/offset) is in flight (blocks re-entry). */
  editBusy: boolean;
  /** Transient confirmation after an edit ("Trimmed. 2 constraints removed."). */
  editNote: string | null;
  /**
   * The target whose signed offset distance the inline editor is collecting.
   * Set when the Offset tool clicks a curve; cleared when the editor arms the
   * request (`armOffset`) or is dismissed (`cancelOffset`).
   */
  offsetDraft: { target: string } | null;
  /**
   * A pending offset the editor armed once the user confirmed a distance;
   * PartPage owns the network effect that consumes it (the store stays
   * side-effect-free). The `nonce` lets that effect fire exactly once. Unlike
   * `edit`, offset ADDS geometry — the result is APPENDED, never swapped.
   */
  offset: { target: string; distance: number; nonce: number } | null;
  /**
   * The Mirror tool's two-phase draft: first collect the entities to reflect
   * (`targets`), then pick the axis line. Null unless the Mirror tool is armed.
   * Held separately from `selection` so the general select grain (points +
   * curves) never mixes with mirror's whole-entity picks.
   */
  mirror: { phase: "targets" | "axis"; targets: string[] } | null;
  /**
   * A pending mirror the axis pick armed; PartPage owns the network effect that
   * consumes it (the store stays side-effect-free), reads the live entity list,
   * and appends the reflected copies. Like `offset` (and unlike `edit`), mirror
   * ADDS geometry. The `nonce` fires the request exactly once.
   */
  mirrorRequest: { targets: string[]; axis: MirrorAxis; nonce: number } | null;
  /**
   * The Fillet/Chamfer tool's corner draft: the two line legs being collected
   * (`picks`, capped at two). Once both are held the inline value editor opens
   * (radius for a fillet, setback for a chamfer). Null unless a corner tool is
   * armed. Held apart from `selection` so the corner's whole-line picks never
   * mix with the general point-first select grain.
   */
  corner: { op: CornerOp; picks: string[] } | null;
  /**
   * A pending corner op the value editor armed; PartPage owns the network
   * effect that consumes it (the store stays side-effect-free), reads the live
   * entity list, and REPLACES it with the rewritten result. Unlike offset/mirror
   * (which append), a corner rewrites in place — like `edit` (trim/extend). The
   * `nonce` fires the request exactly once.
   */
  cornerRequest: {
    op: CornerOp;
    a: string;
    b: string;
    value: number;
    nonce: number;
  } | null;

  /** Enter sketch mode at the plane-pick step. */
  begin: () => void;
  /** One-click: sketch on one of the three origin datums (the common case). */
  choosePlane: (plane: DatumPlaneName) => void;
  /** Sketch on an already-resolved plane spec (origin OR authored offset). */
  choosePlaneSpec: (spec: SketchPlaneSpec) => void;
  setTool: (tool: SketchTool) => void;
  setHoveredPlane: (plane: DatumPlaneName | null) => void;
  setCursor: (point: Point2D | null) => void;
  /** Toggle the GRID snap (G). Entity snapping is unaffected — it is always on. */
  toggleSnap: () => void;
  /** Set the grid step in mm (a settings-surface seam; <= 0 is rejected). */
  setSnapStep: (stepMm: number) => void;
  /** Record the live modifier state and re-resolve the aim under it. */
  setSnapModifiers: (modifiers: {
    suppressed: boolean;
    axisLock: boolean;
  }) => void;
  /**
   * Resolve a raw plane point into the point a click would take, recording the
   * cursor and the named snap candidate. THE one aim path: hover and click both
   * go through it, so what the mark promises is what the click places.
   */
  aim: (
    point: Point2D,
    toleranceMm: number,
    modifiers: { suppressed: boolean; axisLock: boolean },
  ) => Point2D;
  /** Place the next point of the active tool's sequence. */
  placeAt: (point: Point2D) => void;
  /**
   * Commit an open placement sequence (Enter / double-click) — the spline's
   * finish gesture. A no-op for tools that self-finish on a click.
   */
  finishPlacement: () => void;
  /** Select-tool click at a raw (unsnapped) plane point. */
  selectAt: (point: Point2D, toleranceMm: number) => void;
  /**
   * Toggle one exact pick into/out of the selection — the DOM fit-point
   * handles' path (a keyboard/pointer surface that names the pick directly,
   * rather than the coordinate raycast `selectAt` does). Same toggle rule.
   */
  togglePick: (pick: SketchPick) => void;
  setHoverPick: (pick: SketchPick | null) => void;
  clearSelection: () => void;
  /** Apply a constraint verb to the selection (H/V/X/C add; D/R edit). */
  applyConstraint: (action: ConstraintAction) => void;
  /** Toggle the selected entities between profile and construction (N). */
  toggleConstruction: () => void;
  /**
   * Arm a trim/extend on the target under the pick (raw plane mm). `target`
   * null means the click missed every curve — a hint, no request.
   */
  requestEdit: (
    op: "trim" | "extend",
    target: string | null,
    pick: Point2D,
  ) => void;
  /** Apply a trim/extend result: swap the entity set, reconcile constraints. */
  applyEditResult: (
    op: "trim" | "extend",
    entities: readonly SketchEntity[],
  ) => void;
  /** Fail the in-flight edit with a surfaced message. */
  failEdit: (message: string) => void;
  /**
   * Arm the inline signed-distance editor on the target under the pick.
   * `target` null means the click missed every curve — a hint, no editor.
   */
  beginOffset: (target: string | null) => void;
  /** Confirm the offset editor with a validated signed distance (mm). */
  armOffset: (distanceMm: number) => void;
  /** Dismiss the offset editor without offsetting. */
  cancelOffset: () => void;
  /** Apply an offset result: APPEND the new offset entity/entities, re-solve. */
  applyOffsetResult: (entities: readonly SketchEntity[]) => void;
  /** Fail the in-flight offset with a surfaced message. */
  failOffset: (message: string) => void;
  /**
   * Toggle an entity into/out of the mirror target set (targets phase).
   * `id` null means the click missed every curve — a hint, no change.
   */
  toggleMirrorTarget: (id: string | null) => void;
  /** Advance the mirror draft from collecting targets to picking the axis. */
  advanceMirror: () => void;
  /**
   * Pick the axis line and arm the mirror (axis phase). `id` null (a miss) or a
   * non-line entity hints instead of firing; a valid line arms one request.
   */
  pickMirrorAxis: (id: string | null) => void;
  /** Apply a mirror result: APPEND the reflected copies, re-solve, re-arm. */
  applyMirrorResult: (entities: readonly SketchEntity[]) => void;
  /** Fail the in-flight mirror with a surfaced message (axis phase survives). */
  failMirror: (message: string) => void;
  /**
   * Add/remove a line leg from the corner pick set (max two). `id` null means
   * the click missed every curve, and a non-line leg pre-empts the backend's
   * `sketch_unsupported_entity` — both hint instead of picking.
   */
  pickCornerLine: (id: string | null) => void;
  /** Confirm the corner value editor with a validated radius/setback (mm). */
  armCorner: (valueMm: number) => void;
  /** Dismiss the corner value editor, clearing the picks (tool survives). */
  cancelCorner: () => void;
  /** Apply a corner result: SWAP the rewritten entity set, reconcile, re-arm. */
  applyCornerResult: (entities: readonly SketchEntity[]) => void;
  /** Fail the in-flight corner op; the picks + editor survive for a retry. */
  failCorner: (message: string) => void;
  /** Open the editor for an existing dimension constraint (glyph click). */
  editDimension: (constraintIndex: number) => void;
  /**
   * Commit the open dimension editor: a positive `value_mm`, an optional
   * `expression` (driving only) that supersedes it, an optional reference
   * `name`, and the driving/driven flag.
   */
  commitDimension: (commit: DimensionCommit) => void;
  cancelDimension: () => void;
  selectConstraint: (index: number | null) => void;
  removeConstraint: (index: number) => void;
  /** Bind the session to its persisted feature (first save). */
  bind: (featureId: string) => void;
  /**
   * Feed solved geometry + diagnosis back in (never bumps `revision`).
   * `dimensions`, when provided, replaces the per-dimension readouts; omit it
   * (error paths) to keep the last-good readouts.
   */
  adoptSolved: (
    entities: readonly SketchEntity[] | null,
    solve: SolveInfo | null,
    dimensions?: readonly SolvedDimension[],
  ) => void;
  /** Escape cascade: editor → placement → tool → selection → exit. */
  escape: () => void;
  /** Leave sketch mode, discarding the local buffer. */
  exit: () => void;
}

const INITIAL = {
  mode: "off" as SketchMode,
  plane: null,
  tool: "select" as SketchTool,
  pending: [],
  entities: [],
  constraints: [],
  nextIdIndex: 1,
  snapEnabled: true,
  snapStepMm: DEFAULT_SNAP_STEP_MM,
  snapSuppressed: false,
  axisLock: false,
  snapCandidate: null,
  aimRaw: null,
  aimToleranceMm: 0,
  cursor: null,
  hoveredPlane: null,
  selection: [],
  hoverPick: null,
  selectedConstraint: null,
  dimensionEdit: null,
  featureId: null,
  revision: 0,
  solve: null,
  solvedDimensions: [],
  hint: null,
  edit: null,
  editBusy: false,
  editNote: null,
  offsetDraft: null,
  offset: null,
  mirror: null,
  mirrorRequest: null,
  corner: null,
  cornerRequest: null,
};

/**
 * A fresh session that PRESERVES the snap preferences. Grid on/off and the
 * grid step are settings the user chose; wiping them on exit would silently
 * undo a choice, so they survive `begin` / `exit` / the Escape cascade.
 */
const freshSession = (state: SketchState) => ({
  ...INITIAL,
  snapEnabled: state.snapEnabled,
  snapStepMm: state.snapStepMm,
});

/** The one aim resolution — shared by `aim` and the modifier re-resolve. */
function resolveAim(
  state: SketchState,
  point: Point2D,
  toleranceMm: number,
  modifiers: { suppressed: boolean; axisLock: boolean },
): SnapResolution {
  return resolveSnap({
    point,
    entities: state.entities,
    // The placement anchor: the last point of the open sequence. Tangent and
    // perpendicular are defined relative to where the curve comes FROM, and
    // the axis lock pivots on it.
    from: state.pending[state.pending.length - 1] ?? null,
    toleranceMm,
    gridStepMm: state.snapEnabled ? state.snapStepMm : 0,
    suppressed: modifiers.suppressed,
    axisLock: modifiers.axisLock,
    entitySnap: placesPoints(state.tool),
  });
}

export const useSketchStore = create<SketchState>()((set, get) => ({
  ...INITIAL,

  begin: () => set((state) => ({ ...freshSession(state), mode: "plane" })),
  choosePlane: (plane) =>
    set({
      mode: "draw",
      plane: { kind: "origin", base: plane },
      hoveredPlane: null,
      cursor: null,
    }),
  choosePlaneSpec: (spec) =>
    set({ mode: "draw", plane: spec, hoveredPlane: null, cursor: null }),
  setTool: (tool) =>
    set({
      tool,
      pending: [],
      selection: [],
      hoverPick: null,
      selectedConstraint: null,
      dimensionEdit: null,
      offsetDraft: null,
      // Arming Mirror opens its target-collection phase; any other tool clears
      // the draft. The armed `mirrorRequest` is left alone — its nonce guards a
      // late in-flight response from re-firing.
      mirror: tool === "mirror" ? { phase: "targets", targets: [] } : null,
      // Fillet/Chamfer open a fresh two-line corner draft; any other tool clears
      // it. The armed `cornerRequest` is left alone (nonce-guarded), like mirror.
      corner:
        tool === "fillet" || tool === "chamfer"
          ? { op: tool, picks: [] }
          : null,
      hint: null,
      editNote: null,
    }),
  setHoveredPlane: (hoveredPlane) => set({ hoveredPlane }),
  // Leaving the plane drops the aim entirely: a mark left behind would name a
  // snap for a cursor that is no longer there.
  setCursor: (cursor) =>
    set(
      cursor === null
        ? { cursor: null, snapCandidate: null, aimRaw: null }
        : { cursor },
    ),
  toggleSnap: () => set((state) => ({ snapEnabled: !state.snapEnabled })),
  setSnapStep: (stepMm) => {
    if (!Number.isFinite(stepMm) || stepMm <= 0) return;
    set({ snapStepMm: stepMm });
  },

  setSnapModifiers: ({ suppressed, axisLock }) => {
    const state = get();
    if (state.snapSuppressed === suppressed && state.axisLock === axisLock) {
      return;
    }
    // Re-resolve from the last raw point so a modifier pressed with the mouse
    // held still takes effect NOW — the mark must never outlive its truth.
    if (state.aimRaw === null) {
      set({ snapSuppressed: suppressed, axisLock });
      return;
    }
    const resolution = resolveAim(state, state.aimRaw, state.aimToleranceMm, {
      suppressed,
      axisLock,
    });
    set({
      snapSuppressed: suppressed,
      axisLock,
      cursor: resolution.at,
      snapCandidate: resolution.candidate,
    });
  },

  aim: (point, toleranceMm, modifiers) => {
    const resolution = resolveAim(get(), point, toleranceMm, modifiers);
    set({
      cursor: resolution.at,
      snapCandidate: resolution.candidate,
      snapSuppressed: modifiers.suppressed,
      axisLock: modifiers.axisLock,
      aimRaw: point,
      aimToleranceMm: toleranceMm,
    });
    return resolution.at;
  },

  placeAt: (point) => {
    const { tool, pending, nextIdIndex, entities, revision } = get();
    const result = placePoint(tool, pending, point, nextIdIndex);
    set({
      pending: result.pending,
      nextIdIndex: result.nextIdIndex,
      entities:
        result.entities.length > 0
          ? [...entities, ...result.entities]
          : entities,
      revision: result.entities.length > 0 ? revision + 1 : revision,
    });
  },

  finishPlacement: () => {
    const { tool, pending, nextIdIndex, entities, revision } = get();
    const result = finishPlacementSequence(tool, pending, nextIdIndex);
    if (result.entities.length === 0) return;
    set({
      pending: result.pending,
      nextIdIndex: result.nextIdIndex,
      entities: [...entities, ...result.entities],
      revision: revision + 1,
    });
  },

  selectAt: (point, toleranceMm) => {
    const { entities, selection } = get();
    const candidates = pickCandidates(entities, point, toleranceMm);
    set({
      selection: toggleSelection(selection, candidates),
      selectedConstraint: null,
      hint: null,
    });
  },

  togglePick: (pick) =>
    set((state) => ({
      selection: toggleSelection(state.selection, [pick]),
      selectedConstraint: null,
      hint: null,
    })),

  setHoverPick: (hoverPick) => set({ hoverPick }),
  clearSelection: () => set({ selection: [], selectedConstraint: null }),

  applyConstraint: (action) => {
    const { selection, entities, constraints, revision } = get();
    const result = applyConstraintAction(
      action,
      selection,
      entities,
      constraints,
    );
    switch (result.outcome) {
      case "added":
        set({
          constraints: [...constraints, ...result.constraints],
          revision: revision + 1,
          selection: [],
          hint: null,
        });
        return;
      case "editor":
        set({ dimensionEdit: result.target, hint: null });
        return;
      case "hint":
        set({ hint: result.hint });
        return;
    }
  },

  toggleConstruction: () => {
    const { selection, entities, revision } = get();
    const next = toggleConstruction(selection, entities);
    if (next === null) {
      set({ hint: "Select an entity to toggle construction." });
      return;
    }
    // Clear the selection so the toggled entities read in their construction
    // ink (selected entities render in brass, which would mask the dash).
    set({ entities: next, revision: revision + 1, selection: [], hint: null });
  },

  requestEdit: (op, target, pick) => {
    const { editBusy, edit } = get();
    if (editBusy) return;
    if (target === null) {
      set({ hint: `Aim at a curve to ${op}.` });
      return;
    }
    set({
      edit: { op, target, pick, nonce: (edit?.nonce ?? 0) + 1 },
      editBusy: true,
      selection: [],
      hoverPick: null,
      selectedConstraint: null,
      hint: null,
      editNote: null,
    });
  },

  applyEditResult: (op, entities) => {
    const { edit, constraints, revision } = get();
    if (edit === null) return;
    // Reconcile: the stateless edit rewrote geometry only, so a delete/split
    // can strand constraints on ids that no longer exist. Drop the danglers
    // BEFORE the revision bump re-triggers the solve — an unreconciled trim
    // that leaves a dangling constraint would throw on the next evaluate.
    const { constraints: kept, removed } = reconcileConstraints(
      constraints,
      entities,
    );
    const verb = op === "trim" ? "Trimmed" : "Extended";
    const note =
      removed > 0
        ? `${verb}. ${removed} ${removed === 1 ? "constraint" : "constraints"} removed.`
        : `${verb}.`;
    set({
      entities: [...entities],
      constraints: kept,
      revision: revision + 1,
      edit: null,
      editBusy: false,
      editNote: note,
      hoverPick: null,
    });
  },

  failEdit: (message) => set({ edit: null, editBusy: false, hint: message }),

  beginOffset: (target) => {
    const { editBusy } = get();
    if (editBusy) return;
    if (target === null) {
      set({ hint: "Aim at a curve to offset." });
      return;
    }
    set({
      offsetDraft: { target },
      selection: [],
      hoverPick: null,
      selectedConstraint: null,
      dimensionEdit: null,
      hint: null,
      editNote: null,
    });
  },

  armOffset: (distanceMm) => {
    const { offsetDraft, offset } = get();
    // Guard the sign convention at the store edge too: zero collapses the
    // request to the backend's `sketch_offset_zero_distance` — reject it here.
    if (
      offsetDraft === null ||
      !Number.isFinite(distanceMm) ||
      distanceMm === 0
    ) {
      return;
    }
    set({
      offset: {
        target: offsetDraft.target,
        distance: distanceMm,
        nonce: (offset?.nonce ?? 0) + 1,
      },
      offsetDraft: null,
      editBusy: true,
      hint: null,
      editNote: null,
    });
  },

  cancelOffset: () => set({ offsetDraft: null }),

  applyOffsetResult: (added) => {
    const { offset, entities, revision } = get();
    if (offset === null) return;
    // Offset ADDS: append the new offset entity/entities (fresh backend ids,
    // source unchanged). No constraint reconciliation — nothing was deleted or
    // split, so no existing reference can dangle. The revision bump re-solves.
    const count = added.length;
    set({
      entities: [...entities, ...added],
      revision: revision + 1,
      offset: null,
      editBusy: false,
      editNote:
        count === 1 ? "Offset added." : `Offset added. ${count} entities.`,
      hoverPick: null,
    });
  },

  failOffset: (message) =>
    set({ offset: null, offsetDraft: null, editBusy: false, hint: message }),

  toggleMirrorTarget: (id) => {
    const { mirror } = get();
    if (mirror === null || mirror.phase !== "targets") return;
    if (id === null) {
      set({ hint: "Click an entity to add it to the mirror." });
      return;
    }
    set({
      mirror: {
        phase: "targets",
        targets: toggleMirrorTarget(mirror.targets, id),
      },
      hint: null,
    });
  },

  advanceMirror: () => {
    const { mirror } = get();
    if (mirror === null || mirror.phase !== "targets") return;
    if (mirror.targets.length === 0) {
      set({ hint: "Select at least one entity to mirror." });
      return;
    }
    set({ mirror: { phase: "axis", targets: mirror.targets }, hint: null });
  },

  pickMirrorAxis: (id) => {
    const { mirror, entities, editBusy, mirrorRequest } = get();
    if (mirror === null || mirror.phase !== "axis" || editBusy) return;
    if (id === null) {
      set({ hint: "Aim at a line to mirror about." });
      return;
    }
    const axisEntity = entities.find((e) => e.id === id);
    if (axisEntity === undefined || axisEntity.kind !== "line") {
      // Pre-empt the backend's `sketch_mirror_axis_not_line` with an aim hint —
      // only a line (construction or profile) is a valid axis.
      set({
        hint: "The mirror axis must be a line — pick a line or centerline.",
      });
      return;
    }
    set({
      mirrorRequest: {
        targets: mirror.targets,
        axis: { kind: "entity", entity: id },
        nonce: (mirrorRequest?.nonce ?? 0) + 1,
      },
      editBusy: true,
      hint: null,
      editNote: null,
    });
  },

  applyMirrorResult: (added) => {
    const { mirrorRequest, entities, revision } = get();
    if (mirrorRequest === null) return;
    // Mirror ADDS: append the reflected copies (fresh backend ids, sources
    // untouched). No constraint reconciliation — nothing was deleted or split,
    // so no existing reference can dangle. Re-arm a fresh targets phase so the
    // user can mirror another group without re-selecting the tool.
    const count = added.length;
    set({
      entities: [...entities, ...added],
      revision: revision + 1,
      mirrorRequest: null,
      mirror: { phase: "targets", targets: [] },
      editBusy: false,
      editNote: count === 1 ? "Mirrored." : `Mirrored. ${count} copies added.`,
      hoverPick: null,
    });
  },

  failMirror: (message) =>
    // Keep the draft in its axis phase so the user can pick a different line.
    set({ mirrorRequest: null, editBusy: false, hint: message }),

  pickCornerLine: (id) => {
    const { corner, entities, editBusy } = get();
    if (corner === null || editBusy) return;
    // Both legs already held → the value editor is open; ignore stray clicks.
    if (corner.picks.length >= 2 && !corner.picks.includes(id ?? "")) return;
    if (id === null) {
      set({ hint: "Click a line to break the corner." });
      return;
    }
    const entity = entities.find((e) => e.id === id);
    if (entity === undefined || entity.kind !== "line") {
      // Pre-empt the backend's `sketch_unsupported_entity`: v1 rounds/bevels the
      // corner between two LINES only.
      set({ hint: "Fillet and chamfer join two lines — pick a line." });
      return;
    }
    set({
      corner: { op: corner.op, picks: toggleCornerPick(corner.picks, id) },
      selection: [],
      hoverPick: null,
      hint: null,
      editNote: null,
    });
  },

  armCorner: (valueMm) => {
    const { corner, cornerRequest } = get();
    if (corner === null || corner.picks.length !== 2) return;
    // Guard the strictly-positive contract at the store edge (the backend's
    // `radius`/`distance` are > 0); a non-positive value never leaves the UI.
    if (!Number.isFinite(valueMm) || !(valueMm > 0)) return;
    const [a, b] = corner.picks;
    if (a === undefined || b === undefined) return;
    set({
      cornerRequest: {
        op: corner.op,
        a,
        b,
        value: valueMm,
        nonce: (cornerRequest?.nonce ?? 0) + 1,
      },
      editBusy: true,
      hint: null,
      editNote: null,
    });
  },

  cancelCorner: () => {
    const { corner } = get();
    if (corner === null) return;
    set({ corner: { op: corner.op, picks: [] }, hint: null });
  },

  applyCornerResult: (result) => {
    const { cornerRequest, corner, constraints, revision } = get();
    if (cornerRequest === null) return;
    // Corner REWRITES (like trim/extend): the two source lines are trimmed in
    // place with ids preserved, so their constraints survive — but reconcile on
    // the uniform, safe path anyway, so a dangling ref can never reach the solve.
    const { constraints: kept, removed } = reconcileConstraints(
      constraints,
      result,
    );
    const verb = cornerRequest.op === "fillet" ? "Filleted" : "Chamfered";
    const note =
      removed > 0
        ? `${verb}. ${removed} ${removed === 1 ? "constraint" : "constraints"} removed.`
        : `${verb}.`;
    set({
      entities: [...result],
      constraints: kept,
      revision: revision + 1,
      cornerRequest: null,
      editBusy: false,
      editNote: note,
      hoverPick: null,
      // Re-arm a fresh corner draft so the user can break another corner without
      // reselecting the tool (mirror does the same after a copy).
      corner: corner !== null ? { op: cornerRequest.op, picks: [] } : null,
    });
  },

  failCorner: (message) =>
    // Keep the picks (the editor stays open) so a too-large radius can be retyped
    // smaller without re-picking the corner.
    set({ cornerRequest: null, editBusy: false, hint: message }),

  editDimension: (constraintIndex) => {
    const constraint = get().constraints[constraintIndex];
    if (constraint?.kind !== "distance" && constraint?.kind !== "radius") {
      return;
    }
    set({
      dimensionEdit: {
        kind: constraint.kind,
        entity: constraint.entity,
        initialMm: constraint.value_mm,
        initialExpression: constraint.expression ?? null,
        initialName: constraint.name ?? null,
        initialDriving: constraint.driving !== false,
        constraintIndex,
      },
      selectedConstraint: null,
      hint: null,
    });
  },

  commitDimension: (commit) => {
    const { dimensionEdit, constraints, revision } = get();
    if (dimensionEdit === null || !(commit.valueMm > 0)) return;
    // Fully specify every additive field (null = default/unset) so an edit that
    // clears a name/expression, or flips driving↔driven, replaces cleanly —
    // `driving: null` means driving (the wire default), `false` means driven; an
    // expression only rides a DRIVING dim (a driven dim is measured, not fed).
    const constraint: SketchConstraint = {
      kind: dimensionEdit.kind,
      entity: dimensionEdit.entity,
      value_mm: commit.valueMm,
      expression: commit.driving ? commit.expression : null,
      name: commit.name,
      driving: commit.driving ? null : false,
    };
    const next =
      dimensionEdit.constraintIndex === null
        ? [...constraints, constraint]
        : constraints.map((c, i) =>
            i === dimensionEdit.constraintIndex ? constraint : c,
          );
    set({
      constraints: next,
      revision: revision + 1,
      dimensionEdit: null,
      selection: [],
      hint: null,
    });
  },

  cancelDimension: () => set({ dimensionEdit: null }),

  selectConstraint: (selectedConstraint) =>
    set({ selectedConstraint, selection: [], hint: null }),

  removeConstraint: (index) => {
    const { constraints, revision, selectedConstraint } = get();
    if (index < 0 || index >= constraints.length) return;
    set({
      constraints: constraints.filter((_, i) => i !== index),
      revision: revision + 1,
      selectedConstraint:
        selectedConstraint === index
          ? null
          : selectedConstraint !== null && selectedConstraint > index
            ? selectedConstraint - 1
            : selectedConstraint,
      dimensionEdit: null,
    });
  },

  bind: (featureId) => set({ featureId }),

  adoptSolved: (entities, solve, dimensions) => {
    const dims =
      dimensions === undefined ? {} : { solvedDimensions: [...dimensions] };
    if (entities === null) {
      set({ solve, ...dims });
      return;
    }
    const solvedById = new Map(entities.map((e) => [e.id, e]));
    set((state) => ({
      solve,
      ...dims,
      entities: state.entities.map((e) => solvedById.get(e.id) ?? e),
    }));
  },

  escape: () => {
    const {
      tool,
      pending,
      selection,
      dimensionEdit,
      offsetDraft,
      mirror,
      corner,
    } = get();
    // Corner's own cascade, most-local first: an open editor / any picks →
    // clear the picks (close the editor); empty picks → drop the tool.
    if (corner !== null) {
      if (corner.picks.length > 0) {
        set({ corner: { op: corner.op, picks: [] }, hint: null });
        return;
      }
      set({ tool: "select", corner: null, hint: null });
      return;
    }
    // Mirror's own cascade, most-local first: axis phase → back to targets;
    // targets with picks → clear the picks; empty targets → drop the tool.
    if (mirror !== null) {
      if (mirror.phase === "axis") {
        set({
          mirror: { phase: "targets", targets: mirror.targets },
          hint: null,
        });
        return;
      }
      if (mirror.targets.length > 0) {
        set({ mirror: { phase: "targets", targets: [] }, hint: null });
        return;
      }
      set({ tool: "select", mirror: null, hint: null });
      return;
    }
    switch (
      escapeAction(
        tool,
        pending.length,
        selection.length > 0,
        dimensionEdit !== null || offsetDraft !== null,
      )
    ) {
      case "close-editor":
        set({ dimensionEdit: null, offsetDraft: null });
        return;
      case "cancel-placement":
        set({ pending: [] });
        return;
      case "reset-tool":
        set({ tool: "select", pending: [] });
        return;
      case "clear-selection":
        set({ selection: [], selectedConstraint: null, hint: null });
        return;
      case "exit":
        set(freshSession(get()));
        return;
    }
  },

  exit: () => set(freshSession(get())),
}));
