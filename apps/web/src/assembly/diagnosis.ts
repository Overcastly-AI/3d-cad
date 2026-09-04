/**
 * THE SOLVE DIAGNOSIS, RENDERED FROM TYPED DATA — never from the server's
 * prose.
 *
 * `AssemblySolveDiagnosis` carries both: structured fields
 * (`classification`, `conflicting_mates`, `redundant_mates`, `remaining_dof`)
 * AND two pre-built English strings the geometry service assembles for logs and
 * for API consumers (`message`, `suggested_fix`). The panel used to print the
 * strings, which produced this, verbatim, in the SOLVE tab (MATEUI-1):
 *
 *     mates [UUID('4ae95465-…'), UUID('b78a814e-…')] are mutually
 *     unsatisfiable Remove or relax mate 4ae95465-…
 *
 * Three defects, one cause. (a) `f"mates {offending}"` interpolates a Python
 * `list[uuid.UUID]`, so its `repr` — brackets, quotes, the `UUID(` constructor —
 * reached a user. (b) The named mate appears NOWHERE in the mates panel, which
 * numbers nothing: the user is told to remove an object they cannot find. (c)
 * `message` and `suggested_fix` are two sentences and neither ends in a full
 * stop, so any caller that joins them produces a run-on — the healthy path has
 * it too ("…at their seed placement Add mates to…").
 *
 * The server is not wrong to send those strings and this module does not read
 * them. It composes the sentence here, out of the typed fields, naming mates by
 * `mateNamesById` — the SAME handle the tree prints on the row. So the identifier
 * in the message always resolves to a row the user can see, and a raw id can
 * never be the only handle, because a raw id is never printed at all.
 *
 * `sentence()` is where the separator lives: every clause is terminated before
 * the join, so a clause the solver hands over unpunctuated cannot fuse with the
 * next one. `diagnosis.test.ts` asserts that over every branch.
 */
import type { AssemblySolveDiagnosis } from "../api/assemblies";
import type { MateIdentity } from "./mates";

/** A mate the diagnosis names, and can therefore offer to remove. */
export interface DiagnosisSubject extends MateIdentity {
  readonly mateId: string;
}

export interface DiagnosisReadout {
  /** What is wrong and what to do about it, as complete sentences. */
  readonly text: string;
  /**
   * The mates the text names, in the order it names them — each one findable in
   * the panel and removable from here. Empty when the solve is merely
   * under-constrained (no mate is at fault) or when the graph is not in hand.
   */
  readonly subjects: readonly DiagnosisSubject[];
}

/**
 * Join clauses into prose, terminating each one exactly once.
 *
 * This is the whole fix for defect (c) and it is deliberately structural: a
 * caller cannot forget the separator, because there is no way to pass two
 * clauses and get them concatenated bare.
 */
function sentence(...clauses: readonly (string | null)[]): string {
  return clauses
    .map((clause) => clause?.trim() ?? "")
    .filter((clause) => clause !== "")
    .map((clause) => (/[.!?]$/.test(clause) ? clause : `${clause}.`))
    .join(" ");
}

/** "A" / "A and B" / "A, B and C" — the reader's list, not an array's. */
function listPhrase(items: readonly string[]): string {
  if (items.length <= 1) return items[0] ?? "";
  const head = items.slice(0, -1).join(", ");
  return `${head} and ${items[items.length - 1]}`;
}

interface Subjects {
  /** How the sentence refers to them — names when it can, a count when it cannot. */
  readonly phrase: string;
  readonly named: readonly DiagnosisSubject[];
}

/**
 * Name the mates an id list points at.
 *
 * An id with no row in the panel is NOT printed — that is the defect this whole
 * module exists to close, and printing the raw id "just this once" reopens it.
 * It is counted instead, so the sentence stays true when the graph is still in
 * flight or an id outlives its row.
 */
function subjectsOf(
  ids: readonly string[],
  mateNames: ReadonlyMap<string, MateIdentity>,
): Subjects {
  const named: DiagnosisSubject[] = [];
  for (const mateId of ids) {
    const identity = mateNames.get(mateId);
    if (identity !== undefined) named.push({ mateId, ...identity });
  }
  const anonymous = ids.length - named.length;
  const plural = (n: number) => (n === 1 ? "mate" : "mates");
  if (named.length === 0) {
    return { phrase: `${ids.length} ${plural(ids.length)}`, named };
  }
  const names = listPhrase(named.map((subject) => subject.name));
  return {
    phrase:
      anonymous > 0
        ? `${names} and ${anonymous} further ${plural(anonymous)}`
        : names,
    named,
  };
}

/**
 * The diagnosis a user reads, or null when there is nothing to say.
 *
 * `mateNames` comes from `mateNamesById(graph.mates)`; an empty map (graph not
 * loaded) costs the message its names, never its honesty.
 */
export function assemblyDiagnosisReadout(
  diagnosis: AssemblySolveDiagnosis | null,
  mateNames: ReadonlyMap<string, MateIdentity>,
): DiagnosisReadout | null {
  if (diagnosis === null) return null;

  const conflicting = diagnosis.conflicting_mates ?? [];
  if (diagnosis.classification === "conflicting" || conflicting.length > 0) {
    const subjects = subjectsOf(conflicting, mateNames);
    const many = conflicting.length !== 1;
    return {
      text: sentence(
        many
          ? `${subjects.phrase} cannot all be satisfied at once`
          : `${subjects.phrase} cannot be satisfied`,
        many ? "Remove or relax one of them" : "Remove or relax it",
      ),
      subjects: subjects.named,
    };
  }

  const redundant = diagnosis.redundant_mates ?? [];
  if (diagnosis.classification === "redundant" || redundant.length > 0) {
    const subjects = subjectsOf(redundant, mateNames);
    const many = redundant.length !== 1;
    return {
      text: sentence(
        many
          ? `${subjects.phrase} are redundant — the assembly solves without them`
          : `${subjects.phrase} is redundant — the assembly solves without it`,
        many
          ? "Remove any one of them to simplify the mate set"
          : "Remove it to simplify the mate set",
      ),
      subjects: subjects.named,
    };
  }

  const dof = diagnosis.remaining_dof;
  if (dof > 0) {
    return {
      text: sentence(
        dof === 1
          ? "1 degree of freedom remains"
          : `${dof} degrees of freedom remain`,
        "The free components sit where they were seeded; add mates to locate them",
      ),
      subjects: [],
    };
  }

  // The solver ran out of iterations short of tolerance. No mate is named,
  // because the solver named none — saying which one is at fault here would be
  // a guess dressed as a diagnosis.
  return {
    text: sentence(
      "The solver could not settle these mates to tolerance",
      "Loosen or remove a conflicting mate, then solve again",
    ),
    subjects: [],
  };
}
