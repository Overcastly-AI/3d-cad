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
  type DimensionEditorTarget,
  type SketchConstraint,
  type SolveInfo,
} from "./constraints";
import { toggleMirrorTarget, type MirrorAxis } from "./mirror";
import type { DatumPlaneName, Point2D } from "./plane";
import { snapPoint } from "./plane";
import { pickCandidates, toggleSelection, type SketchPick } from "./pick";
import {
  escapeAction,
  placePoint,
  type SketchEntity,
  type SketchTool,
} from "./tools";

/** Default grid snap (mm) — toggled with G, not adjustable yet. */
export const SNAP_STEP_MM = 1;

export type SketchMode = "off" | "plane" | "draw";

export interface SketchState {
  mode: SketchMode;
  /** Chosen datum plane (set on entering `draw`). */
  plane: DatumPlaneName | null;
  tool: SketchTool;
  /** Points of the in-progress placement sequence (plane mm, snapped). */
  pending: Point2D[];
  /** Locally buffered entities; adopt solved positions once persisted. */
  entities: SketchEntity[];
  /** Constraints authored this session (persisted with the entities). */
  constraints: SketchConstraint[];
  /** Next sketch-local id index (`e1`, `e2`, …). */
  nextIdIndex: number;
  snapEnabled: boolean;
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

  /** Enter sketch mode at the plane-pick step. */
  begin: () => void;
  choosePlane: (plane: DatumPlaneName) => void;
  setTool: (tool: SketchTool) => void;
  setHoveredPlane: (plane: DatumPlaneName | null) => void;
  setCursor: (point: Point2D | null) => void;
  toggleSnap: () => void;
  /** Apply the current snap setting to a raw plane-space point. */
  snap: (point: Point2D) => Point2D;
  /** Place the next point of the active tool's sequence. */
  placeAt: (point: Point2D) => void;
  /** Select-tool click at a raw (unsnapped) plane point. */
  selectAt: (point: Point2D, toleranceMm: number) => void;
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
  /** Open the editor for an existing dimension constraint (glyph click). */
  editDimension: (constraintIndex: number) => void;
  /** Commit the open dimension editor with a validated value (mm). */
  commitDimension: (valueMm: number) => void;
  cancelDimension: () => void;
  selectConstraint: (index: number | null) => void;
  removeConstraint: (index: number) => void;
  /** Bind the session to its persisted feature (first save). */
  bind: (featureId: string) => void;
  /** Feed solved geometry + diagnosis back in (never bumps `revision`). */
  adoptSolved: (
    entities: readonly SketchEntity[] | null,
    solve: SolveInfo | null,
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
  cursor: null,
  hoveredPlane: null,
  selection: [],
  hoverPick: null,
  selectedConstraint: null,
  dimensionEdit: null,
  featureId: null,
  revision: 0,
  solve: null,
  hint: null,
  edit: null,
  editBusy: false,
  editNote: null,
  offsetDraft: null,
  offset: null,
  mirror: null,
  mirrorRequest: null,
};

export const useSketchStore = create<SketchState>()((set, get) => ({
  ...INITIAL,

  begin: () => set({ ...INITIAL, mode: "plane" }),
  choosePlane: (plane) =>
    set({ mode: "draw", plane, hoveredPlane: null, cursor: null }),
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
      hint: null,
      editNote: null,
    }),
  setHoveredPlane: (hoveredPlane) => set({ hoveredPlane }),
  setCursor: (cursor) => set({ cursor }),
  toggleSnap: () => set((state) => ({ snapEnabled: !state.snapEnabled })),
  snap: (point) => snapPoint(point, get().snapEnabled ? SNAP_STEP_MM : 0),

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

  selectAt: (point, toleranceMm) => {
    const { entities, selection } = get();
    const candidates = pickCandidates(entities, point, toleranceMm);
    set({
      selection: toggleSelection(selection, candidates),
      selectedConstraint: null,
      hint: null,
    });
  },

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
        constraintIndex,
      },
      selectedConstraint: null,
      hint: null,
    });
  },

  commitDimension: (valueMm) => {
    const { dimensionEdit, constraints, revision } = get();
    if (dimensionEdit === null || !(valueMm > 0)) return;
    const constraint: SketchConstraint = {
      kind: dimensionEdit.kind,
      entity: dimensionEdit.entity,
      value_mm: valueMm,
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

  adoptSolved: (entities, solve) => {
    if (entities === null) {
      set({ solve });
      return;
    }
    const solvedById = new Map(entities.map((e) => [e.id, e]));
    set((state) => ({
      solve,
      entities: state.entities.map((e) => solvedById.get(e.id) ?? e),
    }));
  },

  escape: () => {
    const { tool, pending, selection, dimensionEdit, offsetDraft, mirror } =
      get();
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
        set({ ...INITIAL });
        return;
    }
  },

  exit: () => set({ ...INITIAL }),
}));
