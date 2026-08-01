/**
 * Per-instance VIEW state for the assembly workspace (UI-W2 —
 * `docs/design/ui-wave-tool-grade.md` Surface 2): is this component drawn, and
 * how solidly. Founder-raised ("what about different components enablement,
 * opacity, etc."), and measured as a real gap by the product audit: a
 * 21-instance assembly had no way to see inside itself.
 *
 * This is VIEW state, not document state. Hiding a part must never change what
 * the solver solves, what the interference check measures, or what an export
 * contains — a hidden instance still clashes, still exports, still holds its
 * mates. So it lives in the client, is not versioned, and is not written back
 * through the graph OCC. (The `InstanceResponse` contract carries no visibility
 * field, and inventing one client-side would be a hand-written API type — the
 * DRY rule forbids it.)
 *
 * The model is TWO orthogonal facts per instance, not one three-valued enum:
 *
 *   · `hidden` — the eye. Not drawn at all.
 *   · `ghost`  — the opacity stop. Drawn see-through when it IS drawn.
 *
 * They are stored separately so un-hiding restores what you had: ghost a part,
 * hide it, show it again, and it is still ghosted. A single enum would silently
 * drop that, which is the kind of small lie that makes a tool feel unreliable.
 * {@link VisibilityMode} is the flattened projection of the pair — what the
 * SOLID / GHOST / HIDE control writes and the renderer reads.
 *
 * Everything here is pure: the workspace holds one `VisibilityState` in React
 * state and every verb returns the next one.
 */

/** The flattened, user-facing stop: what one row's control shows and writes. */
export type VisibilityMode = "solid" | "ghost" | "hidden";

/** The two orthogonal facts kept per instance. */
export interface InstanceView {
  readonly hidden: boolean;
  readonly ghost: boolean;
}

/**
 * Sparse map instance id → view. An ABSENT id is solid and shown, so a fresh
 * assembly starts as `{}` and only edited instances cost a key.
 */
export type VisibilityState = Readonly<Record<string, InstanceView>>;

/** A fresh workspace: everything solid, nothing hidden. */
export const EMPTY_VISIBILITY: VisibilityState = {};

const SHOWN_SOLID: InstanceView = { hidden: false, ghost: false };

/** This instance's two facts (the default for an id nothing has touched). */
export function instanceView(
  state: VisibilityState,
  instanceId: string,
): InstanceView {
  return state[instanceId] ?? SHOWN_SOLID;
}

/** The flattened stop the row control shows: hidden wins over ghost. */
export function visibilityModeOf(
  state: VisibilityState,
  instanceId: string,
): VisibilityMode {
  const view = instanceView(state, instanceId);
  return view.hidden ? "hidden" : view.ghost ? "ghost" : "solid";
}

/** Is this instance drawn at all? */
export function isInstanceVisible(
  state: VisibilityState,
  instanceId: string,
): boolean {
  return !instanceView(state, instanceId).hidden;
}

/**
 * Write one stop. HIDE preserves the ghost fact underneath (see the module
 * doc); SOLID and GHOST both un-hide, because choosing an opacity is a request
 * to look at the thing.
 */
export function withVisibilityMode(
  state: VisibilityState,
  instanceId: string,
  mode: VisibilityMode,
): VisibilityState {
  const current = instanceView(state, instanceId);
  const next: InstanceView =
    mode === "hidden"
      ? { hidden: true, ghost: current.ghost }
      : { hidden: false, ghost: mode === "ghost" };
  return { ...state, [instanceId]: next };
}

/** The eye: flip drawn/not-drawn, leaving the opacity stop alone. */
export function toggleInstanceHidden(
  state: VisibilityState,
  instanceId: string,
): VisibilityState {
  const current = instanceView(state, instanceId);
  return {
    ...state,
    [instanceId]: { hidden: !current.hidden, ghost: current.ghost },
  };
}

/**
 * Isolate: hide every OTHER instance and show this one solid. The kept
 * instance loses a ghost it may have had — you isolated it in order to look at
 * it, so half-showing it would be an odd answer. Everything else keeps its
 * ghost fact, so `showAll` restores the view you were working in.
 */
export function isolateInstance(
  state: VisibilityState,
  instanceIds: readonly string[],
  keepId: string,
): VisibilityState {
  const next: Record<string, InstanceView> = { ...state };
  for (const id of instanceIds) {
    next[id] =
      id === keepId
        ? SHOWN_SOLID
        : { hidden: true, ghost: instanceView(state, id).ghost };
  }
  return next;
}

/** The way back: un-hide everything. Ghosts are opacity, not hiding — kept. */
export function showAllInstances(
  state: VisibilityState,
  instanceIds: readonly string[],
): VisibilityState {
  const next: Record<string, InstanceView> = { ...state };
  for (const id of instanceIds) {
    next[id] = { hidden: false, ghost: instanceView(state, id).ghost };
  }
  return next;
}

/** How many of these instances are not drawn. */
export function hiddenInstanceCount(
  state: VisibilityState,
  instanceIds: readonly string[],
): number {
  return instanceIds.filter((id) => instanceView(state, id).hidden).length;
}

/**
 * The isolated instance, or null — DERIVED from the state rather than stored as
 * a flag, so the ISOLATED stamp can never claim something the scene contradicts.
 * It also means hiding everything but one BY HAND gets the same "here is why you
 * can only see one thing, here is the way back" banner, which is the actual
 * failure mode ("where did my parts go") this answers.
 */
export function isolatedInstanceId(
  state: VisibilityState,
  instanceIds: readonly string[],
): string | null {
  if (instanceIds.length < 2) return null;
  const shown = instanceIds.filter((id) => !instanceView(state, id).hidden);
  return shown.length === 1 ? (shown[0] ?? null) : null;
}
