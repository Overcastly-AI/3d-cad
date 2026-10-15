/**
 * WHICH PARTS OF AN ASSEMBLY FAILED TO BUILD (BIKE2-FAILED-PART-KILLS-PICKS).
 *
 * A part whose feature tree fails (a crank arm's `profile_unsupported`) still
 * gets a result row for every place it occurs — directly, inside a
 * sub-assembly at any depth, or as a component-pattern copy — with
 * `part_mesh_glb_id: null` and its typed `error`. Geometry draws, clash-checks
 * and EXPORTS only the rows with a body, so those occurrences are simply not in
 * the file. Before this module nothing said so: the strip read "Ready" and a
 * STEP of the bike held 72 occurrences instead of 74.
 *
 * This folds those rows into one entry per PART (document), named the way the
 * user knows it, with the components that hold it — the facts the export gate,
 * the component rows and the BOM all speak from. Pure: rows + the request in,
 * entries out.
 */
import type {
  EvaluatedInstance,
  InstancePlacementResult,
} from "../api/assemblies";
import { instanceAt } from "./subAssemblies";

/** One part that produced no body, everywhere it occurs. */
export interface FailedPart {
  /** The part document (from the request's `part_key`), or null if unknown. */
  readonly partDocumentId: string | null;
  /** The part's name as the user knows it ("Crank arm"). */
  readonly name: string;
  /** The kernel's typed code (`profile_unsupported`, `no_body`, …). */
  readonly code: string;
  /** The kernel's sentence. */
  readonly message: string;
  /** The TOP-LEVEL components that hold it (itself, or its sub-assembly). */
  readonly componentIds: readonly string[];
  /** How many occurrences the file leaves out. */
  readonly occurrences: number;
}

/** "Crank arm <2>" → "Crank arm": an instance name, back to its part's. */
export function partNameOf(instanceName: string): string {
  return instanceName.replace(/\s*<\d+>$/, "").trim() || instanceName;
}

/** A failed row's own path into the request, and its top-level component. */
function locate(row: InstancePlacementResult): {
  path: string[];
  componentId: string;
} {
  const path = row.path ?? [];
  if (row.pattern) {
    // A copy of THIS assembly's pattern: it is its seed, moved. A copy of a
    // sub-assembly seed keeps the seed's inner path after the copy id.
    const seed = row.pattern.seed_instance_id;
    return { path: [seed, ...path.slice(1)], componentId: seed };
  }
  if (path.length > 0) return { path, componentId: path[0] as string };
  return { path: [row.instance_id], componentId: row.instance_id };
}

interface Draft {
  partDocumentId: string | null;
  name: string;
  code: string;
  message: string;
  componentIds: string[];
  occurrences: number;
}

/**
 * Every part that produced no body, one entry per part document, in the order
 * the result first meets them. `rows` are the claimable result rows (empty
 * while the solve is stale); `request` names them.
 */
export function failedParts(
  rows: readonly InstancePlacementResult[],
  request: { instances: readonly EvaluatedInstance[] } | null,
): FailedPart[] {
  const failed = rows.filter((row) => row.part_mesh_glb_id === null);
  if (failed.length === 0) return [];
  const byKey = new Map<string, Draft>();
  const unnamed: { row: InstancePlacementResult; componentId: string }[] = [];
  const add = (draft: Draft, componentId: string) => {
    draft.occurrences += 1;
    if (!draft.componentIds.includes(componentId)) {
      draft.componentIds.push(componentId);
    }
  };
  for (const row of failed) {
    const { path, componentId } = locate(row);
    const leaf = request === null ? null : instanceAt(request.instances, path);
    if (leaf === null || leaf.sub_assembly) {
      // A copy placed by a pattern INSIDE a sub-assembly has no request
      // instance of its own; it is a copy of a seed that failed the same way,
      // and that seed is a row here too. Attach it after the named pass.
      unnamed.push({ row, componentId });
      continue;
    }
    const partDocumentId = leaf.part_key.split("@")[0] || null;
    const key = partDocumentId ?? `name:${leaf.name ?? row.instance_id}`;
    const draft = byKey.get(key) ?? {
      partDocumentId,
      name: partNameOf(leaf.name ?? "Part"),
      code: row.error?.code ?? "no_body",
      message: row.error?.message ?? "The part produced no body.",
      componentIds: [],
      occurrences: 0,
    };
    byKey.set(key, draft);
    add(draft, componentId);
  }
  for (const { row, componentId } of unnamed) {
    const code = row.error?.code ?? "no_body";
    const message = row.error?.message ?? "The part produced no body.";
    const twin = [...byKey.values()].find(
      (d) =>
        d.code === code &&
        d.message === message &&
        d.componentIds.includes(componentId),
    );
    if (twin !== undefined) {
      add(twin, componentId);
      continue;
    }
    const key = `row:${code}:${message}:${componentId}`;
    const draft = byKey.get(key) ?? {
      partDocumentId: null,
      name: "A part",
      code,
      message,
      componentIds: [],
      occurrences: 0,
    };
    byKey.set(key, draft);
    add(draft, componentId);
  }
  return [...byKey.values()];
}

/** The failed parts each top-level component holds, by component id. */
export function failuresByComponent(
  failures: readonly FailedPart[],
): ReadonlyMap<string, readonly FailedPart[]> {
  const out = new Map<string, FailedPart[]>();
  for (const failure of failures) {
    for (const id of failure.componentIds) {
      const list = out.get(id) ?? [];
      list.push(failure);
      out.set(id, list);
    }
  }
  return out;
}

/** The part documents that failed, for the BOM's flag. */
export function failedDocumentIds(
  failures: readonly FailedPart[],
): ReadonlySet<string> {
  return new Set(
    failures.flatMap((f) =>
      f.partDocumentId === null ? [] : [f.partDocumentId],
    ),
  );
}
