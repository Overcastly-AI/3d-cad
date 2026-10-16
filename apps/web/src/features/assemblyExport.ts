/**
 * WHAT THE ASSEMBLY WORKSPACE EXPORTS — the assembly twin of `partExport.ts`.
 *
 * QA 2026-10-10 (blocking): after a part edit left a hinge's joints
 * unresolved, the assembly's export strip still read "Ready" and the STEP held
 * every component at its seed pose. A solve that drops or cannot satisfy a mate
 * still places every instance it can (design §4), so the file is WRITABLE — it
 * is just not the assembly the user built. That is the part workspace's
 * "Partial" case at a second address, and it gets the same three truths: the
 * word in the status cell, the sentence under the row, and `-partial` in the
 * filename. On top of that the assembly asks once before it writes, because a
 * wrong POSE is worse than a short tree: a prefix is a real body, a mis-posed
 * assembly is a file that lies about where its parts are.
 *
 * The faults are read off `AssemblySolve` only — never off the raw evaluation —
 * so a superseded solve claims nothing here either (`assemblySolve.ts`).
 */
import {
  markFilenamePartial,
  type ExportedFile,
  type ExportFormat,
} from "../api/exportPart";
import type {
  AssemblyStatus,
  MateEvaluationError,
  MateResponse,
} from "../api/assemblies";
import type { FailedPart } from "../assembly/partFailures";
import type { AssemblySolve } from "./assemblySolve";

/** What the solve could not honour, counted by kind. */
export interface AssemblySolveFaults {
  readonly unresolvedJoints: number;
  readonly unresolvedMates: number;
  readonly conflictingJoints: number;
  readonly conflictingMates: number;
  /**
   * The solve itself gave up (`conflicting` / `not_converged`) without naming
   * a mate to blame — still a pose nobody asked for.
   */
  readonly unsolved: AssemblyStatus | null;
}

/**
 * The facts a fault count is derived from: `AssemblySolve`'s claimable part on
 * the assembly page, `GET /assemblies/{id}/extents` on a drawing.
 */
export interface AssemblySolveFacts {
  readonly status: AssemblyStatus | null;
  /** `diagnosis.conflicting_mates`: mutually unsatisfiable mates, by id. */
  readonly conflictingMates: readonly string[];
  readonly mateErrors: readonly MateEvaluationError[];
}

/** The claimable facts of the solve on screen (empty while it is stale). */
export function solveFacts(solve: AssemblySolve): AssemblySolveFacts {
  return {
    status: solve.status,
    conflictingMates: solve.diagnosis?.conflicting_mates ?? [],
    mateErrors: solve.mateErrors,
  };
}

/**
 * Why the assembly export is inert, or undefined when it may write.
 *
 * A solve that is not the answer for the graph as it stands has no faults to
 * claim (`assemblySolve.ts` empties them), so the partial gate would read
 * "Ready" over it — while the export re-solves server-side and writes whatever
 * pose THAT solve finds, unannounced. Like Fusion, which does not export
 * mid-compute, the cells wait for the solve: "Solving…" while one is under
 * way, "Not solved" when the last one failed.
 */
export function assemblyExportBlockedReason(
  base: string | undefined,
  solve: Pick<AssemblySolve, "stale" | "activity">,
): string | undefined {
  if (base !== undefined) return base;
  if (!solve.stale) return undefined;
  return solve.activity === "solving" ? "Solving…" : "Not solved";
}

/**
 * Count the unresolved and conflicting mates, split into joints and the
 * relation mates, as the tree badges them (`AssemblyTreePanel`: a mate in
 * `mate_errors` is "unresolved", one in `conflicting_mates` is "conflict";
 * unresolved wins). A mate id the graph does not know counts as a mate.
 */
export function assemblySolveFaults(
  facts: AssemblySolveFacts,
  mates: readonly Pick<MateResponse, "id" | "mate">[],
): AssemblySolveFaults {
  const joints = new Set(
    mates.filter((m) => m.mate.type === "joint").map((m) => m.id),
  );
  const unresolved = new Set(facts.mateErrors.map((e) => e.mate_id));
  const conflicting = new Set(
    facts.conflictingMates.filter((id) => !unresolved.has(id)),
  );
  const count = (ids: Set<string>, wantJoint: boolean) =>
    [...ids].filter((id) => joints.has(id) === wantJoint).length;
  const named = unresolved.size + conflicting.size;
  return {
    unresolvedJoints: count(unresolved, true),
    unresolvedMates: count(unresolved, false),
    conflictingJoints: count(conflicting, true),
    conflictingMates: count(conflicting, false),
    unsolved:
      named === 0 &&
      (facts.status === "conflicting" || facts.status === "not_converged")
        ? facts.status
        : null,
  };
}

function plural(n: number, noun: string): string {
  return `${n} ${noun}${n === 1 ? "" : "s"}`;
}

/**
 * The faults in a clause — "2 joints unresolved, 1 mate conflicting" — or
 * null when there are none.
 */
export function assemblyFaultSummary(
  faults: AssemblySolveFaults,
): string | null {
  const parts: string[] = [];
  if (faults.unresolvedJoints > 0)
    parts.push(`${plural(faults.unresolvedJoints, "joint")} unresolved`);
  if (faults.unresolvedMates > 0)
    parts.push(`${plural(faults.unresolvedMates, "mate")} unresolved`);
  if (faults.conflictingJoints > 0)
    parts.push(`${plural(faults.conflictingJoints, "joint")} conflicting`);
  if (faults.conflictingMates > 0)
    parts.push(`${plural(faults.conflictingMates, "mate")} conflicting`);
  if (faults.unsolved === "conflicting") parts.push("mates conflicting");
  if (faults.unsolved === "not_converged") parts.push("solve did not converge");
  return parts.length === 0 ? null : parts.join(", ");
}

/** Where the parts of a partial assembly end up — the confirm's own words. */
export const PARTIAL_POSE_CLAUSE =
  "parts at their last solved or initial positions";

export interface AssemblyExportGate {
  /** QA hook, `data-export-state`: "ready" or "partial". */
  readonly state: "ready" | "partial";
  readonly partial: boolean;
  /** The status cell's text when partial ("Partial · 1 joint unresolved"). */
  readonly statusLabel: string | undefined;
  /** The sentence under the strip, or null. */
  readonly notice: string | null;
  /** The band's caption clause, or null. */
  readonly qualifier: string | null;
  /** Set = a format click asks first; this is why. */
  readonly confirmReason: string | null;
  /** The confirm button's words, or null for the pose default. */
  readonly confirmLabel: string | null;
}

const READY: AssemblyExportGate = {
  state: "ready",
  partial: false,
  statusLabel: undefined,
  notice: null,
  qualifier: null,
  confirmReason: null,
  confirmLabel: null,
};

/** How many part names a clause spells out before "and N more". */
const NAMED_PARTS = 2;

/** "Crank arm", "Crank arm and Pedal", "Crank arm, Pedal and 2 more". */
function partNames(failed: readonly FailedPart[]): string {
  const names = [...new Set(failed.map((f) => f.name))];
  if (names.length === 1) return names[0] as string;
  if (names.length <= NAMED_PARTS + 1) {
    return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
  }
  const rest = names.length - NAMED_PARTS;
  return `${names.slice(0, NAMED_PARTS).join(", ")} and ${rest} more`;
}

/**
 * The failed parts in a clause — "Crank arm failed to build" — or null.
 *
 * A part that failed is not in the file AT ALL (geometry writes only the
 * occurrences with a body, BIKE2-FAILED-PART-KILLS-PICKS), which is worse than
 * a misplaced one: the file is short and nothing in it says so.
 */
export function failedPartSummary(
  failed: readonly FailedPart[],
): string | null {
  if (failed.length === 0) return null;
  return `${partNames(failed)} failed to build`;
}

/** How many occurrences the file would leave out ("2 bodies"). */
function omittedBodies(failed: readonly FailedPart[]): string {
  const n = failed.reduce((sum, f) => sum + f.occurrences, 0);
  return `${n} ${n === 1 ? "body" : "bodies"}`;
}

/**
 * Ready, or Partial and why. `failed` are the parts that produced no body
 * (`partFailures.ts`), at any depth: the file would leave them out.
 */
export function assemblyExportGate(
  facts: AssemblySolveFacts,
  mates: readonly Pick<MateResponse, "id" | "mate">[],
  failed: readonly FailedPart[] = [],
): AssemblyExportGate {
  const pose = assemblyFaultSummary(assemblySolveFaults(facts, mates));
  const parts = failedPartSummary(failed);
  if (pose === null && parts === null) return READY;
  const summary = [parts, pose].filter((s) => s !== null).join(", ");
  const sentences: string[] = [];
  if (parts !== null) {
    sentences.push(
      `${parts}, so the file would leave out ${omittedBodies(failed)}.`,
    );
  }
  if (pose !== null) {
    sentences.push(
      `${capitalise(pose)}, so the file would hold the ${PARTIAL_POSE_CLAUSE}` +
        ", not where the mates put them.",
    );
  }
  sentences.push("Its name will say partial.");
  return {
    state: "partial",
    partial: true,
    statusLabel: `Partial · ${summary}`,
    notice: sentences.join(" "),
    qualifier: `${summary}, marked partial`,
    confirmReason: `${capitalise(summary)}.`,
    confirmLabel:
      parts === null
        ? null
        : `Export anyway — without ${partNames(failed)}` +
          (pose === null ? "" : `, ${PARTIAL_POSE_CLAUSE}`),
  };
}

/** "2 joints unresolved" → "2 joints unresolved"; "mates …" → "Mates …". */
export function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Name the download as the gate requires (`-partial`, like a part prefix). */
export function assemblyExporter(
  exporter: (format: ExportFormat) => Promise<ExportedFile>,
  partial: boolean,
): (format: ExportFormat) => Promise<ExportedFile> {
  if (!partial) return exporter;
  return async (format) => {
    const file = await exporter(format);
    return { ...file, filename: markFilenamePartial(file.filename) };
  };
}
