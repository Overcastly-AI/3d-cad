/**
 * How a register orders and filters its drawer (moved out of
 * `DocumentRegister.tsx`, which re-exports all of it). Pure functions over the
 * three fields they read, so they need nothing from the component.
 */
interface OrderedDocument {
  name: string;
  created_at: string;
  updated_at: string;
}

/** Which column the drawer is ordered by. */
export type RegisterSortKey = "name" | "activity" | "filed";

export interface RegisterSort {
  key: RegisterSortKey;
  direction: "asc" | "desc";
}

/**
 * LAST WORKED, newest first (REGISTER-2, UI-REVIEW 2026-08-17 P1-3).
 *
 * It used to be FILED ascending, defended as "the order the server already
 * returns, so the initial state is a true description rather than a label over
 * an arbitrary order". That is a good argument about HONESTY and the wrong
 * answer to the question the surface is asked. A returning engineer opens this
 * page to get back into the thing they were doing; oldest-first put that at the
 * BOTTOM — measured at row 120 of 120 — so the register's first screen was the
 * work they had finished with. Fusion's Data Panel and Onshape both default to
 * recently-modified-first for the same reason.
 *
 * The honesty argument survives intact: this order is SORTED, `aria-sort` says
 * so on the LAST WORKED header from the first paint, and the caption says it in
 * words. Nothing is unlabelled.
 */
export const DEFAULT_SORT: RegisterSort = {
  key: "activity",
  direction: "desc",
};

/**
 * Name-substring filter, case- and accent-insensitive, applied to the list the
 * server returned.
 *
 * Client-side on purpose, and honestly so: the list endpoint returns the
 * caller's WHOLE drawer in one response (no pagination on the wire), so the
 * browser is filtering the complete set — the count can therefore say "4 of 12"
 * and mean it. If that list ever becomes a page, the filter has to move to the
 * server in the same change, because "4 of 12" would silently start meaning
 * "4 of the 12 I happen to be holding".
 */
export function filterDocuments<T extends OrderedDocument>(
  documents: T[],
  query: string,
): T[] {
  const needle = query.trim().toLocaleLowerCase();
  if (needle === "") return documents;
  return documents.filter((entry) =>
    entry.name.toLocaleLowerCase().includes(needle),
  );
}

/**
 * Order the drawer.
 *
 * NAME uses a numeric collator so "Rib 2" sorts before "Rib 10" — a register
 * full of numbered parts sorted lexically is a register nobody trusts.
 *
 * TIES ARE NOT BROKEN, deliberately: `Array.prototype.sort` is stable, so equal
 * rows keep the order the SERVER sent them in (documents lists by
 * `created_at, id`). Inventing a client-side tiebreak — collating the uuids, say
 * — would order two same-millisecond documents differently from every other
 * surface that shows them, for no gain; borrowing the server's order costs
 * nothing and cannot disagree with it.
 */
export function sortDocuments<T extends OrderedDocument>(
  documents: T[],
  sort: RegisterSort,
): T[] {
  const collator = new Intl.Collator(undefined, {
    numeric: true,
    sensitivity: "base",
  });
  const sign = sort.direction === "asc" ? 1 : -1;
  const compare = (a: T, b: T): number => {
    if (sort.key === "name") return collator.compare(a.name, b.name);
    const key = sort.key === "activity" ? "updated_at" : "created_at";
    return Date.parse(a[key]) - Date.parse(b[key]);
  };
  return [...documents].sort((a, b) => sign * compare(a, b));
}
