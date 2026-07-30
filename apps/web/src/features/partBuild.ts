/**
 * WHAT THE WORKSPACE KNOWS ABOUT THE BODY ON SCREEN — one derivation, read by
 * every cell that makes a claim about it.
 *
 * The defect this module exists to make impossible (AUDIT-ENGINEERING J2,
 * 2026-07-30): on a part with one broken feature the same screen said three
 * different things at the same moment —
 *
 *   Solve  "Failed"      from `features.some(f => f.status === "error")`  (true)
 *   Status "Up to date"  from whether a request was in flight              (unentitled)
 *   Export "Ready"       from `hasBody ? undefined : "No body"`            (unentitled)
 *
 * ...and the third one is not a wrong label, it is a wrong FILE: the strict-
 * prefix rule (feature-tree.md §4.3 — the first failure errors, everything
 * after it is `skipped`, and the artifact fields describe the LAST-GOOD state)
 * returns a `mesh_glb_id` for the prefix, so "Ready" hands the user a STEP of a
 * body that is missing every feature from the failure onward.
 *
 * The cure is not three better local expressions — three local expressions are
 * how they drifted. It is ONE fact object, derived here from the wire, that the
 * Solve cell, the Status cell, the Export strip, the tree's SKIP rows and the
 * viewport notice all read. That is the DRY rule applied to state: fix the
 * derivation, never the instance.
 *
 * Every input is a value the server actually sent. Nothing here is inferred
 * from TanStack Query's in-flight flags except the three transient states that
 * genuinely ARE request states (solving / regenerating / mesh unavailable), and
 * those are kept in their own axis (`activity`) so they can never again stand in
 * for a claim about the model.
 */
import type {
  EvaluateTreeResult,
  FeatureTreeResponse,
  PartResponse,
} from "../api/parts";
import { barSlotIndex } from "./rollback";

/** A feature named as a cause, a boundary, or a casualty. */
export interface BuildFeatureRef {
  readonly id: string;
  /** The user's own name for it ("Hole 1") — never a UUID on a surface. */
  readonly name: string;
  /** 1-based build order: the ordinal the tree row and timeline chip show. */
  readonly ordinal: number;
}

/**
 * What the displayed body covers, relative to the tree it came from.
 *
 * `"partial"` is the finding: a body that exists but is a PREFIX — either a
 * feature failed (unintended) or the travel stop is set (intended). A prefix is
 * not the part, and no surface may present it as one.
 */
export type BodyScope = "none" | "whole" | "partial";

/** The only three things request state is entitled to say, plus rest. */
export type BuildActivity = "idle" | "solving" | "regenerating" | "mesh-error";

/** The Solve cell's verdict over the evaluation as a whole. */
export type SolveVerdict = "unknown" | "solving" | "solved" | "failed";

export interface PartBuild {
  /** Transient request state — never a claim about the model. */
  readonly activity: BuildActivity;
  /** `EvaluateTreeResult.tree_version`: the version the body was BUILT FROM. */
  readonly builtFromTreeVersion: number | null;
  /** The newest tree version any authority has reported (the denominator). */
  readonly currentTreeVersion: number | null;
  /** Raw provenance fact: built-from differs from current. */
  readonly stale: boolean;
  /**
   * Staleness worth REPORTING: stale and nothing is in flight to resolve it.
   * While a rebuild is running the honest word is "Solving…", not "Unverified".
   */
  readonly unverified: boolean;
  /** Any evaluated feature returned an error (the Solve cell's own test). */
  readonly failed: boolean;
  /** The FIRST failure in build order — the cause every SKIP row inherits. */
  readonly failure: BuildFeatureRef | null;
  /** Features the strict-prefix rule dropped because `failure` stopped it. */
  readonly excluded: readonly BuildFeatureRef[];
  /** Features held below the travel stop — never evaluated, deliberately. */
  readonly rolledBack: readonly BuildFeatureRef[];
  /** `last_good_feature_id` resolved to a row: what the artifact reflects. */
  readonly lastGood: BuildFeatureRef | null;
  /** The evaluation produced a body (mesh and/or mass properties). */
  readonly hasBody: boolean;
  readonly scope: BodyScope;
  readonly solve: SolveVerdict;
}

export interface PartBuildInput {
  /** The feature tree; `undefined` while it loads. */
  tree: FeatureTreeResponse | undefined;
  /** The evaluate result the screen is currently showing. */
  evaluation: EvaluateTreeResult | undefined;
  /** The part row — `tree_version` is the staleness denominator. */
  part: PartResponse | undefined;
  /** An evaluate is in flight (TanStack `isFetching`). */
  evaluating: boolean;
  /** The tree itself is refetching — an answer is coming, so don't cry stale. */
  treeFetching: boolean;
  /** A `mesh_not_found` re-evaluate is in flight (§7.8 LRU eviction). */
  regenerating: boolean;
  /** That retry already ran and the mesh is still unservable. */
  regenFailed: boolean;
  /** The body's GLB is still downloading. */
  meshPending: boolean;
}

/**
 * THE staleness comparison, once, on this side of the wire.
 *
 * The rule and its wording come from `py_kit.schemas.parts.is_stale_for_tree`,
 * which `derive_part_eval_state` folds through server-side; this is that same
 * comparison applied to the two numbers the API hands the browser
 * (`EvaluateTreeResult.tree_version` against `PartResponse.tree_version`), so a
 * body readout and the register's four-state verdict cannot disagree about what
 * "stale" means.
 *
 * INEQUALITY, not `<`: undo/redo also bumps `tree_version`, so a result stamped
 * with a version the part never reached is exactly as unusable as an old one.
 */
export function isStaleForTree({
  builtFromTreeVersion,
  treeVersion,
}: {
  builtFromTreeVersion: number;
  treeVersion: number;
}): boolean {
  return builtFromTreeVersion !== treeVersion;
}

/**
 * The tree version to compare AGAINST: the newest any authority has reported.
 *
 * Two sources carry it — the part row (`PartResponse.tree_version`, refetched
 * on focus, so it is the one that can LEARN about a concurrent edit) and the
 * feature tree (refetched after every local mutation, so it is the one that is
 * fresh while you model). Monotonic in the same transaction as every tree write
 * (feature-tree.md §1.2), so "newest" is well defined and taking the max cannot
 * invent staleness out of one source merely lagging the other.
 */
function newestTreeVersion(
  part: PartResponse | undefined,
  tree: FeatureTreeResponse | undefined,
): number | null {
  const known = [part?.tree_version, tree?.tree_version].filter(
    (v): v is number => typeof v === "number",
  );
  return known.length === 0 ? null : Math.max(...known);
}

/** Fold the wire + the three real request states into one set of facts. */
export function derivePartBuild({
  tree,
  evaluation,
  part,
  evaluating,
  treeFetching,
  regenerating,
  regenFailed,
  meshPending,
}: PartBuildInput): PartBuild {
  const features = tree?.features ?? [];
  const statusById = new Map(
    (evaluation?.features ?? []).map((f) => [f.feature_id, f.status]),
  );
  const barSlot = barSlotIndex(features, tree?.rollback_feature_id ?? null);

  const ref = (index: number): BuildFeatureRef => {
    const feature = features[index];
    return {
      id: feature?.id ?? "",
      name: feature?.name ?? "",
      ordinal: index + 1,
    };
  };

  let failure: BuildFeatureRef | null = null;
  const excluded: BuildFeatureRef[] = [];
  const rolledBack: BuildFeatureRef[] = [];
  features.forEach((feature, index) => {
    if (index > barSlot) {
      rolledBack.push(ref(index));
      return;
    }
    const status = statusById.get(feature.id);
    if (status === "error") {
      if (failure === null) failure = ref(index);
      return;
    }
    // `skipped` is the strict-prefix rule's casualty list: these features were
    // never attempted because an EARLIER one failed. A `suppressed` feature is
    // NOT here — the user held that one out on purpose and the row says so.
    if (status === "skipped") excluded.push(ref(index));
  });

  const lastGoodId = evaluation?.last_good_feature_id ?? null;
  const lastGoodIndex =
    lastGoodId === null ? -1 : features.findIndex((f) => f.id === lastGoodId);
  const lastGood = lastGoodIndex === -1 ? null : ref(lastGoodIndex);

  const builtFromTreeVersion = evaluation?.tree_version ?? null;
  const currentTreeVersion = newestTreeVersion(part, tree);
  const stale =
    builtFromTreeVersion !== null &&
    currentTreeVersion !== null &&
    isStaleForTree({ builtFromTreeVersion, treeVersion: currentTreeVersion });

  const activity: BuildActivity = regenFailed
    ? "mesh-error"
    : regenerating || meshPending
      ? "regenerating"
      : evaluating
        ? "solving"
        : "idle";

  const failed = (evaluation?.features ?? []).some((f) => f.status === "error");
  const hasBody =
    (evaluation?.mesh_glb_id ?? null) !== null ||
    (evaluation?.properties ?? null) !== null;
  const scope: BodyScope = !hasBody
    ? "none"
    : failed || rolledBack.length > 0
      ? "partial"
      : "whole";
  const solve: SolveVerdict = evaluating
    ? "solving"
    : evaluation === undefined
      ? "unknown"
      : failed
        ? "failed"
        : "solved";

  return {
    activity,
    builtFromTreeVersion,
    currentTreeVersion,
    stale,
    unverified: stale && activity === "idle" && !treeFetching,
    failed,
    failure,
    excluded,
    rolledBack,
    lastGood,
    hasBody,
    scope,
    solve,
  };
}

/** The SOLVE cell of the feature-tree title block (unchanged vocabulary). */
export function solveSummary(build: PartBuild): string {
  switch (build.solve) {
    case "solving":
      return "Solving…";
    case "unknown":
      return "—";
    case "failed":
      return "Failed";
    case "solved":
      return "Solved";
  }
}

/** The one word the STATUS cell spends, plus the sentence underneath it. */
export type BodyStatus =
  | "up-to-date"
  | "partial"
  | "rolled-back"
  | "unverified"
  | "evaluating"
  | "regenerating"
  | "error";

export interface BodyStatusReadout {
  readonly status: BodyStatus;
  /** Tracked-caps cell value. */
  readonly label: string;
  /** What it means, in the user's terms — null when there is nothing to add. */
  readonly detail: string | null;
  /** An established exception (flag) vs. one that is merely not established. */
  readonly tone: "quiet" | "flag" | "indeterminate";
}

/**
 * STATUS, derived from PROVENANCE — never from `isFetching`.
 *
 * Precedence is deliberate: the three transient states first (a request in
 * flight is the most useful thing to say while it is happening), then the
 * claims about the model, most specific first. "Up to date" is the LAST branch
 * and now means what it says: this body was built from the tree as it stands,
 * with nothing excluded.
 *
 * `detail` is a title-block REGISTER LINE, not prose: one tabular clause naming
 * the cause and the state the body reflects. The full sentence belongs to the
 * viewport notice, which has the room for it — a panel that spends four lines on
 * a paragraph pushes the EXPORT strip below the fold at 1366x768, and the gated
 * export is the most important thing on this panel when a feature has failed.
 */
export function bodyStatusReadout(build: PartBuild): BodyStatusReadout {
  if (build.activity === "mesh-error") {
    return {
      status: "error",
      label: "Error",
      detail: "Mesh unavailable · re-evaluate",
      tone: "flag",
    };
  }
  if (build.activity === "regenerating") {
    return {
      status: "regenerating",
      label: "Regenerating…",
      detail: null,
      tone: "quiet",
    };
  }
  if (build.activity === "solving") {
    return {
      status: "evaluating",
      label: "Solving…",
      detail: null,
      tone: "quiet",
    };
  }
  if (build.failed) {
    return {
      status: "partial",
      label: "Partial",
      detail: `${
        build.failure === null ? "A feature" : build.failure.name
      } failed · built to ${build.lastGood?.name ?? "the last good state"}`,
      tone: "flag",
    };
  }
  if (build.unverified) {
    return {
      status: "unverified",
      label: "Unverified",
      detail: "Tree moved since this build · re-evaluate",
      tone: "indeterminate",
    };
  }
  if (build.rolledBack.length > 0) {
    return {
      status: "rolled-back",
      label: "Rolled back",
      detail: `Travel stop at ${
        build.lastGood?.name ?? "the start of the build"
      } · ${excludedCount(build.rolledBack.length)}`,
      tone: "quiet",
    };
  }
  return {
    status: "up-to-date",
    label: "Up to date",
    detail: null,
    tone: "quiet",
  };
}

/** "3 features are excluded" / "1 feature is excluded" — counted, not adjectival. */
function countClause(count: number): string {
  return `${count} ${count === 1 ? "feature is" : "features are"} excluded`;
}

/** The register form of the same count: "1 feature excluded". */
function excludedCount(count: number): string {
  return `${count} feature${count === 1 ? "" : "s"} excluded`;
}

/**
 * The N3 sentence: what the viewport is actually showing when a feature broke,
 * and what that costs you. Rendered by the viewport's PARTIAL BODY notice, which
 * is the one surface with room for prose.
 *
 * The product-audit finding was that one bad pick turned a modelled bracket into
 * "a plain 72000 mm³ brick and nothing tells the user that is not their part" —
 * while `last_good_feature_id`, the datum that says exactly which state IS on
 * screen, was on the wire and used nowhere in the app. It is used here.
 *
 * The export clause belongs in the SAME breath: the gate refuses for exactly this
 * condition, and stating the consequence where the condition is explained beats a
 * fourth restatement down in the title block (the strip is one scroll away on a
 * 768px-tall screen).
 */
export function partialBodySentence(build: PartBuild): string {
  const built =
    build.lastGood === null
      ? "the last good state"
      : `the last good state — built to ${build.lastGood.name}`;
  const cause =
    build.failure === null
      ? "A feature failed"
      : `${build.failure.name} failed`;
  const rest =
    build.excluded.length === 0
      ? "."
      : `, so ${countClause(build.excluded.length)} from it onward.`;
  return `Showing ${built}. ${cause}${rest} Export is blocked until it builds.`;
}

/**
 * EXPORT — the cell where a wrong label becomes a wrong file.
 *
 * Two prefixes reach this gate and they are NOT the same event, so they get
 * different answers:
 *
 *  - **a feature error** is an accident. The user did not ask for a truncated
 *    body and has no reason to suspect the file is one, so export REFUSES and
 *    names the feature to fix. Honest-and-blocked beats silently-wrong.
 *  - **the travel stop** is a deliberate act with a control on screen holding
 *    it. Refusing would be paternalistic, so export is ALLOWED — and both the
 *    cell and the FILENAME say `partial`, because a file outlives the screen
 *    that explained it.
 *
 * A stale provenance is a third case: we do not know what the current tree
 * exports, and the server exports the CURRENT tree, so the honest answer is to
 * wait for the rebuild rather than to guess.
 */
export interface ExportGate {
  readonly state:
    "ready" | "no-body" | "feature-error" | "unverified" | "partial";
  /** Set = the row is inert; this is the cell's text and the cells' reason. */
  readonly blockedReason?: string;
  /** Allowed, but the artifact is a prefix: the filename is marked. */
  readonly partial: boolean;
  /** The sentence rendered under the row (blocked or partial). */
  readonly notice: string | null;
}

export function exportGate(build: PartBuild): ExportGate {
  if (build.failed) {
    return {
      state: "feature-error",
      blockedReason:
        build.failure === null
          ? "Feature error"
          : `${build.failure.name} failed`,
      partial: false,
      // No band. Three cells of this strip already carry "Fillet1 failed" (the
      // status cell plus each format cell's reason), the STATUS cell above states
      // what the body is, and the viewport notice states the consequence — a
      // fourth copy would be the accessory to remove, and at 1366x768 it pushed
      // the gated cells themselves below the panel's fold.
      notice: null,
    };
  }
  if (build.unverified) {
    return {
      state: "unverified",
      blockedReason: "Unverified",
      partial: false,
      notice:
        "The tree changed after this body was built. Re-evaluate before " +
        "exporting so the file matches the part.",
    };
  }
  if (!build.hasBody) {
    // "No body" is true of a sketch-only part and MISLEADING of a part whose
    // body has been rolled away by the travel stop: the modeller has a body,
    // they have parked the stop in front of it, and the fix is a control on
    // screen (UI-REVIEW 2026-07-30 P3 — a wording bug fixed at the source, so
    // every cell reading this derivation gets the corrected answer).
    const byTravelStop = build.rolledBack.length > 0;
    return {
      state: "no-body",
      blockedReason: byTravelStop ? "Rolled back" : "No body",
      partial: false,
      notice: byTravelStop
        ? "The travel stop is before the first feature that makes a body. " +
          "Move it forward to export."
        : null,
    };
  }
  if (build.rolledBack.length > 0) {
    return {
      state: "partial",
      partial: true,
      notice: `${excludedCount(
        build.rolledBack.length,
      )} by the travel stop. The file will be the rolled-back body, and its name will say partial.`,
    };
  }
  return { state: "ready", partial: false, notice: null };
}

/**
 * Why a feature's row says SKIP, naming the feature that caused it.
 *
 * `skipped` used to render as the bare badge "SKIP" (N3): an independent corner
 * fillet vanishing therefore looked like a fillet bug, when the fillet was never
 * attempted. The row now carries the cause — the id in `data-blocked-by` for
 * QA, the NAME in the accessible name and the tooltip for the user.
 */
export function skippedReason(build: PartBuild): string | null {
  if (build.failure === null) return null;
  return `not attempted — ${build.failure.name} failed first`;
}

/**
 * The drafting note the tree prints where the build stopped — said ONCE, at the
 * seam, rather than repeated down every stranded row.
 *
 * The sentence a modeler needs is not "these were skipped" (the badges say that)
 * but WHY features that have nothing to do with the failure are gone too.
 */
export function excludedNote(build: PartBuild): string | null {
  if (build.failure === null || build.excluded.length === 0) return null;
  const rows =
    build.excluded.length === 1
      ? "1 feature"
      : `${build.excluded.length} features`;
  return `Not attempted: the ${rows} below. The build stops at the first failure, even for a feature that does not depend on ${build.failure.name}.`;
}
