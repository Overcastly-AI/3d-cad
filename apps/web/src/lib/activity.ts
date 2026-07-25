/**
 * "When was this last worked on, and has it been worked on at all?" — the two
 * questions a register has to answer before any other (frontend-design pass,
 * 2026-07-25).
 *
 * The document list endpoints carry `created_at` + `updated_at` and nothing
 * else, so those two stamps are the ONLY honest activity signal available
 * client-side. They carry more than they look like they do: `updated_at` is
 * bumped by every tree write (documents keeps the `history_cursor` on the
 * document row, in the same transaction as the write), so a document whose
 * `updated_at` still equals its `created_at` has had no edit at all since it
 * was named — the empty stub in a drawer of real work.
 *
 * Deliberately NOT claimed here: "has a body", "has drawings", "is broken".
 * None of those are on the wire for a list, and inventing them would need an
 * evaluate-per-row. A register that guesses is worse than one that reports.
 */

/**
 * Both stamps are written by separate `datetime.now()` calls in the same INSERT,
 * so a never-edited document's two stamps differ by microseconds rather than
 * being exactly equal — "never edited" cannot be an equality test. 250 ms is
 * three orders of magnitude above that skew and (being a separate authenticated
 * request a person had to act to produce) well below a real edit, so the two
 * cases separate with nothing plausible in the gap.
 */
const CREATION_SKEW_MS = 250;

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** What a register row says in its LAST WORKED column. */
export type DocumentActivity =
  /** Never edited since it was created — a named but unstarted document. */
  | { readonly kind: "never" }
  /** Edited at least once; `label` is the coarse relative age of that edit. */
  | { readonly kind: "worked"; readonly label: string }
  /** A stamp we could not read — say nothing rather than guess. */
  | { readonly kind: "unknown" };

/**
 * Coarse relative age — the precision a person actually reads a register at.
 * Buckets are deliberately wide (no "37 seconds ago"): the question is "was
 * this this morning or last month", and wide buckets also keep the surface
 * visually stable between renders. Anything older than a week is better named
 * by its date than by a count of days, so it falls through to the caller's
 * absolute date.
 */
export function relativeAge(elapsedMs: number): string | null {
  if (elapsedMs < 45 * 1000) return "just now";
  if (elapsedMs < HOUR) {
    const minutes = Math.max(1, Math.round(elapsedMs / MINUTE));
    return `${minutes} min ago`;
  }
  if (elapsedMs < DAY) {
    const hours = Math.max(1, Math.floor(elapsedMs / HOUR));
    return `${hours} h ago`;
  }
  if (elapsedMs < 2 * DAY) return "Yesterday";
  if (elapsedMs < 7 * DAY) return `${Math.floor(elapsedMs / DAY)} d ago`;
  return null;
}

/**
 * The activity state of one register row. `absolute` is the fallback label for
 * an edit older than the relative buckets (the caller passes the same ISO date
 * it shows in FILED, so the two columns agree on format).
 */
export function documentActivity(
  createdIso: string,
  updatedIso: string,
  absolute: string,
  now: number = Date.now(),
): DocumentActivity {
  const created = Date.parse(createdIso);
  const updated = Date.parse(updatedIso);
  if (Number.isNaN(created) || Number.isNaN(updated))
    return { kind: "unknown" };
  if (updated - created <= CREATION_SKEW_MS) return { kind: "never" };
  // A stamp from the future (clock skew between the server and this browser) is
  // still an edit that happened — clamp rather than print a negative age.
  const elapsed = Math.max(0, now - updated);
  return { kind: "worked", label: relativeAge(elapsed) ?? absolute };
}
