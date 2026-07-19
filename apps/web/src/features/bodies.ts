/**
 * The part's body set, derived from the feature tree (multi-body §MB-1). A
 * body's identity IS its base (creating) feature id — the same eval-time
 * partition the geometry service keys on (design §Decisions-1), replayed here
 * from the tree so the Bodies panel + the Combine tool can name and pick bodies
 * without a second source of truth. The evaluate payload carries only the
 * last-good MESH (all bodies fused into one GLB), never a per-body list, so the
 * partition rule lives here — kept deliberately parallel to the kernel's:
 *
 *   - `import` always starts a new body.
 *   - an ADD extrude/revolve/sweep/loft starts a NEW body when `merge` is false
 *     (or when there is no active body yet — the first solid); a merged ADD
 *     fuses into the active body (no new body).
 *   - a `cut` (extrude/revolve/…) modifies the active body — no new body.
 *   - a `boolean` union consumes the TOOL body and keeps the TARGET's identity
 *     slot (design §Decisions-3), so the set shrinks by one.
 *   - a `sheet_metal_base_flange` starts the sheet body (§4.1), honouring
 *     `merge` like an ADD; a `sheet_metal_edge_flange` folds onto the active
 *     body (§4.2), a `sheet_metal_hem` folds an edge back (parity §2), and a
 *     `sheet_metal_corner_relief` notches a corner (parity §4.4) — all MODIFY
 *     the active sheet body, no new body.
 *   - every other feature (fillet/chamfer/shell/draft/pattern/datum/sketch)
 *     modifies the active body or is non-body — the set is unchanged.
 *
 * Rolled-back features (below the rollback bar) never contribute a body.
 */
import type { FeatureResponse } from "../api/parts";

export interface BodyInfo {
  /** The body's identity — its base (creating) feature id. */
  baseFeatureId: string;
  /** The base feature's name, as the tree shows it (e.g. "Extrude1"). */
  name: string;
  /** The base feature's type (extrude / revolve / sweep / loft / import). */
  featureType: string;
  /** 1-based tree order among bodies — the "Body N" label. */
  ordinal: number;
}

/** Body-creating solid features that carry an `operation` + `merge`. */
const BODY_CREATING = new Set(["extrude", "revolve", "sweep", "loft"]);

/**
 * The bodies a part currently holds, in tree order. See the module docstring for
 * the partition rule (kept parallel to the kernel's `EvaluationState.bodies`).
 */
export function computeBodies(
  features: readonly FeatureResponse[],
): BodyInfo[] {
  const bodies: Omit<BodyInfo, "ordinal">[] = [];
  let activeId: string | null = null;
  const indexOf = (id: string): number =>
    bodies.findIndex((b) => b.baseFeatureId === id);

  for (const f of features) {
    if (f.rolled_back) continue;
    const type = f.feature.type;

    if (type === "import") {
      bodies.push({ baseFeatureId: f.id, name: f.name, featureType: type });
      activeId = f.id;
    } else if (type === "sheet_metal_base_flange") {
      // A base flange always CREATES material (the sheet's first body, §4.1) —
      // it has no `operation`, only `merge` (default true): a merged base flange
      // fuses into the active body, else it starts a new one.
      const params = f.feature.params as { merge?: boolean };
      const merge = params.merge ?? true;
      if (!merge || activeId === null) {
        bodies.push({ baseFeatureId: f.id, name: f.name, featureType: type });
        activeId = f.id;
      }
    } else if (BODY_CREATING.has(type)) {
      const params = f.feature.params as {
        operation: "add" | "cut";
        merge?: boolean;
      };
      if (params.operation !== "add") continue; // a cut modifies the active body
      const merge = params.merge ?? true;
      if (!merge || activeId === null) {
        bodies.push({ baseFeatureId: f.id, name: f.name, featureType: type });
        activeId = f.id;
      }
      // A merged ADD fuses into the active body — no new body.
    } else if (type === "boolean") {
      const params = f.feature.params as {
        target: { feature_id: string };
        tool: { feature_id: string };
      };
      // Union (MB-1): the tool body is consumed; the target keeps its identity.
      const toolIdx = indexOf(params.tool.feature_id);
      if (toolIdx >= 0) bodies.splice(toolIdx, 1);
      if (indexOf(params.target.feature_id) >= 0) {
        activeId = params.target.feature_id;
      }
    }
    // Everything else modifies the active body or is non-body: set unchanged.
  }

  return bodies.map((b, i) => ({ ...b, ordinal: i + 1 }));
}
