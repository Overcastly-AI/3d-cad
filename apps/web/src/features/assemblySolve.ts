/**
 * WHAT THE ASSEMBLY WORKSPACE KNOWS ABOUT THE SOLVE ON SCREEN — one derivation,
 * read by every cell that makes a claim about it.
 *
 * This is `features/partBuild.ts` at a second address, and it exists for the
 * same defect. The part page reported a body superseded by a write in flight as
 * "Up to date" (QA-R4); the assembly page reported a solve superseded by a
 * write in flight as `Under constrained`, with the free instance still drawn at
 * its PRE-mate pose. A kernel investigation drove the same fixture through the
 * real API and measured the mated answer — `remaining_dof: 3`, the bracket
 * seated at `z = 6.000000` — while the UI reported `remaining_dof: 6` and
 * `z = 3.0`, which is bit-for-bit the `mates=[]` answer. Nothing downstream was
 * wrong: documents persisted the mate, the graph read returned it, geometry
 * acted on it. The OBSERVER was reading the previous evaluation and nothing on
 * the page said so.
 *
 * THE RETAINED EVALUATION IS DELIBERATE AND STAYS. `AssemblyPage`'s evaluate
 * query carries `placeholderData: keepPreviousData` so solved geometry never
 * blinks to null mid-refetch — without it `sceneFitKey` collapses to `""` and
 * back, and the camera teleports away from the view the user orbited to in
 * order to author the mate. The bug was never the retention. It was that
 * nothing distinguished a retained solve from a current one.
 *
 * THE RULE, and it is structural rather than a fourth flag a caller can forget:
 * `status`, `diagnosis` and `mateErrors` are the only things a surface may
 * CLAIM, and they are `null` / empty whenever `stale` is true. There is no way
 * to render a settled verdict over a superseded solve, because the verdict does
 * not exist in that state. `assemblySolveLabel` then spends "Solving…" or "—" —
 * a transient word or an absence, never a claim.
 *
 * MATE-OBS-2 ADDED THE EIGHTH CONSUMER, and it is the reason `mateErrors` lives
 * here rather than being read off the evaluation. `AssemblyTreePanel` badged its
 * mate rows from `evaluation.mate_errors` and `evaluation.diagnosis
 * .conflicting_mates` DIRECTLY — the two fields this module exists to gate —
 * so for the same ~600-840 ms window a row could wear a superseded solve's
 * `conflict` / `unresolved` stamp, or fail to wear one it had just earned. It
 * under-claims as often as it over-claims, which is why it was P2 and not the
 * P0 MATE-OBS was, and it was found only by walking the call sites rather than
 * the paths. The lesson generalises past this one panel: a field that is not on
 * `AssemblySolve` is a field a consumer can read raw, so the fix is to MOVE it
 * here, not to remember to check `stale` at a ninth address.
 *
 * Every input is either a value the server sent or a request state the client
 * genuinely holds; nothing here is inferred from the solve's CONTENT. That
 * matters more here than on the part page: `test_status_alone_cannot_
 * distinguish_the_two` (geometry) proves a seating solve and a constraint-free
 * solve BOTH report `under_constrained`, so a staleness test keyed on the
 * status string would pass in a world where mates do nothing.
 */
import type {
  AssemblySolveDiagnosis,
  AssemblyStatus,
  EvaluateAssemblyResult,
  MateEvaluationError,
} from "../api/assemblies";

export interface AssemblySolveInput {
  /**
   * A graph write the client ISSUED and has not yet resolved.
   *
   * True from the click, because from the instant the app sends the write it
   * KNOWS the solve on screen is superseded — it is holding the mutation. This
   * is the QA-R4 lesson transplanted: seeding the fact only when the reply
   * lands leaves most of the window open, and on the measured mate path the
   * reply is several hundred ms behind the click.
   */
  writing: boolean;
  /**
   * The graph read or the referenced parts' rows are refetching.
   *
   * This is the BULK of the measured window and it is invisible to the evaluate
   * query's own flags: a `doc_version` bump changes the part-docs key, so
   * `partTrees` goes `undefined`, so the evaluate query is DISABLED — not
   * fetching, not stale by its own reckoning, and still handing out the
   * previous solve as placeholder data.
   */
  loading: boolean;
  /** The evaluate request itself is in flight (TanStack `isFetching`). */
  evaluating: boolean;
  /**
   * The evaluate query would run at all: the graph has loaded, there is at
   * least one instance, and every referenced part's tree is in hand.
   *
   * Its FALSE case is not only a transient. Delete the last instance and the
   * query is disabled for good while `keepPreviousData` keeps handing out the
   * solve of the assembly that used to be there — a permanent readout of a
   * world that no longer exists, which no amount of waiting resolves.
   */
  solvable: boolean;
  /**
   * The rendered evaluation came from `placeholderData: keepPreviousData` —
   * TanStack's own statement that it was solved from a DIFFERENT query key.
   *
   * The key is `[assemblyId, doc_version, partStamp]`, so this is the one input
   * that catches the two paths a `doc_version` comparison cannot see: a
   * referenced PART edited elsewhere (the stamp moves, `doc_version` does not)
   * and navigating between assemblies (the retained solve belongs to the
   * previous document entirely).
   */
  placeholder: boolean;
  /** The evaluate request came back an error — there is no verdict to spend. */
  failed: boolean;
  /** The evaluation currently rendered — possibly a previous solve. */
  evaluation: EvaluateAssemblyResult | undefined;
}

/** Transient request state — never a claim about the assembly. */
export type AssemblySolveActivity = "idle" | "solving";

export interface AssemblySolve {
  /**
   * The solve on screen is NOT the answer for the graph as it stands.
   *
   * The `data-eval-stale` stamp on the workspace is exactly this, so a reader
   * holding ANY readout in the assembly — a status cell, a DOF count, a
   * balloon's `data-solved-*` pose — can ask its ancestor whether the number it
   * just read is current, in the same DOM read.
   */
  readonly stale: boolean;
  readonly activity: AssemblySolveActivity;
  /** The status a surface may CLAIM. Null while it is not established. */
  readonly status: AssemblyStatus | null;
  /** The diagnosis a surface may CLAIM. Null while it is not established. */
  readonly diagnosis: AssemblySolveDiagnosis | null;
  /**
   * The per-mate resolution failures a surface may CLAIM (MATE-OBS-2).
   *
   * EMPTY while stale, for the same structural reason `status` is null: a badge
   * on a mate row is a claim about the solve, and a superseded solve has none
   * to make. Empty is the honest reading here — "nothing is known yet" and
   * "nothing is wrong" both draw no badge, and `solve.activity` is what a
   * surface spends if it wants to say which.
   */
  readonly mateErrors: readonly MateEvaluationError[];
}

/** Nothing known — one frozen empty, so a stale solve allocates nothing. */
const NO_MATE_ERRORS: readonly MateEvaluationError[] = [];

const STATUS_LABEL: Record<AssemblyStatus, string> = {
  well_constrained: "Well constrained",
  under_constrained: "Under constrained",
  over_constrained: "Over constrained",
  conflicting: "Conflicting",
  not_converged: "Not converged",
};

/** Fold the request states + the retained evaluation into one set of facts. */
export function deriveAssemblySolve({
  writing,
  loading,
  evaluating,
  solvable,
  placeholder,
  failed,
  evaluation,
}: AssemblySolveInput): AssemblySolve {
  // WORK IS UNDER WAY — the one condition that entitles a surface to spend a
  // transient word instead of a verdict. Four ways in, and they tile the whole
  // window from the click to the new solve landing:
  //
  //  - `writing`     the app is holding a write it knows supersedes this solve;
  //  - `loading`     the graph / part rows are refetching, which is when the
  //                  evaluate query is DISABLED and therefore silent;
  //  - `evaluating`  the evaluate itself is in flight;
  //  - a placeholder solve on a SOLVABLE assembly — the current key has no
  //    answer yet and one is coming, so calling that idle would flash "—"
  //    between two renders of a running rebuild.
  const inFlight =
    writing || loading || evaluating || (placeholder && solvable);
  // Anything but a settled answer for the CURRENT key is stale. `!solvable`
  // is in here on its own account: it is the state that does not resolve.
  const stale = inFlight || placeholder || failed || !solvable;
  return {
    stale,
    activity: inFlight ? "solving" : "idle",
    // THE INVARIANT (asserted in `assemblySolve.test.ts`): a stale solve has no
    // verdict to spend. Deriving both fields from `stale` is what makes it
    // impossible to render one — a separate `stale` flag beside a `status` a
    // caller reads anyway would be the same defect one indirection along.
    status: stale ? null : (evaluation?.status ?? null),
    diagnosis: stale ? null : (evaluation?.diagnosis ?? null),
    mateErrors: stale ? NO_MATE_ERRORS : (evaluation?.mate_errors ?? []),
  };
}

/**
 * The STATUS cell's word.
 *
 * "Solving…" is a transient state; "—" is an absence (nothing to solve, or
 * nothing solved yet). Neither is a claim, which is the point: the only claims
 * this function can spend are the five the solver actually returned.
 */
export function assemblySolveLabel(solve: AssemblySolve): string {
  if (solve.status !== null) return STATUS_LABEL[solve.status];
  return solve.activity === "solving" ? "Solving…" : "—";
}

/** A sick solve reads flag; a healthy, under-constrained or unknown one is quiet. */
export function assemblySolveTone(solve: AssemblySolve): string {
  if (solve.status === null) return "text-gauge";
  return solve.status === "well_constrained" ||
    solve.status === "under_constrained"
    ? "text-mist"
    : "text-flag";
}
