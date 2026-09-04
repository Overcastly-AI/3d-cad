/**
 * Fixtures for the part-workspace build facts (`features/partBuild.ts`).
 *
 * Shared because the J2 defect was three surfaces disagreeing about ONE part:
 * if each test file invented its own idea of "a part with a broken fillet", the
 * suite could pass while the surfaces still disagreed. Every tier — the pure
 * derivation test, the inspector, the tree panel, the export strip — is pinned
 * to the SAME scenarios here, and each one runs the REAL `derivePartBuild`
 * rather than a hand-written `PartBuild` literal, so breaking the derivation
 * breaks the component tests too.
 *
 * The scenarios mirror the audits: a clean cube (`cleanCube`), the r50 all-edge
 * fillet OCCT genuinely cannot build (`brokenFillet` — the same failure
 * `e2e/p2-register-health.spec.ts` produces from the real stack), the N3 bracket
 * where one bad hole pick strands independent downstream features
 * (`strandedDownstream`), and a tree held back by the travel stop (`rolledBack`).
 */
import type {
  EvaluateTreeResult,
  FeatureResponse,
  FeatureResult,
  FeatureTreeResponse,
  PartResponse,
} from "../api/parts";
import type { ShapeProperties } from "../api/tessellate";
import {
  derivePartBuild,
  type PartBuild,
  type PartBuildInput,
} from "../features/partBuild";

export const MESH_ID = "sha256:abc";

/** Mass properties of a 20 mm cube — a real prefix body, not a placeholder. */
export const CUBE_PROPERTIES: ShapeProperties = {
  volume: 8000,
  surface_area: 2400,
  centroid: { x: 10, y: 10, z: 10 },
  bounding_box: { min: { x: 0, y: 0, z: 0 }, max: { x: 20, y: 20, z: 20 } },
  topology: { faces: 6, edges: 12, shells: 1 },
};

/** One tree row. The `type` only matters where a surface reads it, so: sketch. */
export function feature(
  id: string,
  name: string,
  orderIndex: number,
): FeatureResponse {
  return {
    id,
    name,
    part_id: "p1",
    order_index: orderIndex,
    created_at: "2026-07-30T00:00:00Z",
    updated_at: "2026-07-30T00:00:00Z",
    rolled_back: false,
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "datum_plane", plane: "XY" },
        entities: [],
        constraints: [],
      },
    },
  };
}

export function makeTree(
  names: readonly string[],
  options: { treeVersion?: number; rollbackFeatureId?: string | null } = {},
): FeatureTreeResponse {
  return {
    part_id: "p1",
    tree_version: options.treeVersion ?? 3,
    features: names.map((name, index) => feature(`f${index + 1}`, name, index)),
    rollback_feature_id: options.rollbackFeatureId ?? null,
    can_undo: false,
    can_redo: false,
  };
}

export function makePart(treeVersion: number): PartResponse {
  return {
    id: "p1",
    name: "Motor mount",
    owner_id: "u1",
    length_unit: "mm",
    // No material assigned — the honest empty assignment every part starts
    // with (docs/design/materials.md), which reports NO mass rather than 0 g.
    materials: { default_material: null, bodies: [] },
    tree_version: treeVersion,
    eval_state: "ok",
    last_eval_status: "ok",
    last_eval_at: "2026-07-30T00:00:00Z",
    last_eval_tree_version: treeVersion,
    created_at: "2026-07-30T00:00:00Z",
    updated_at: "2026-07-30T00:00:00Z",
  };
}

export function makeEvaluation(
  statuses: readonly FeatureResult["status"][],
  options: {
    treeVersion?: number;
    lastGoodFeatureId?: string | null;
    meshGlbId?: string | null;
    properties?: ShapeProperties | null;
  } = {},
): EvaluateTreeResult {
  return {
    part_id: "p1",
    tree_version: options.treeVersion ?? 3,
    features: statuses.map((status, index) => ({
      feature_id: `f${index + 1}`,
      status,
      ...(status === "error"
        ? {
            error: {
              code: "fillet_failed",
              message: "OCCT could not build the fillet.",
            },
          }
        : {}),
    })),
    mesh_glb_id: options.meshGlbId === undefined ? MESH_ID : options.meshGlbId,
    properties:
      options.properties === undefined ? CUBE_PROPERTIES : options.properties,
    last_good_feature_id: options.lastGoodFeatureId ?? null,
  };
}

/** `derivePartBuild` with everything settled — override only what you mean to. */
export function makeBuild(input: Partial<PartBuildInput> = {}): PartBuild {
  return derivePartBuild({
    tree: undefined,
    evaluation: undefined,
    part: undefined,
    evaluating: false,
    treeFetching: false,
    regenerating: false,
    regenFailed: false,
    meshPending: false,
    writing: false,
    writtenTreeVersion: null,
    ...input,
  });
}

/** Sketch + extrude, both ok, current: the happy path every cell agrees on. */
export function cleanCube(): PartBuild {
  return makeBuild({
    tree: makeTree(["Sketch1", "Extrude1"]),
    part: makePart(3),
    evaluation: makeEvaluation(["ok", "ok"], { lastGoodFeatureId: "f2" }),
  });
}

/**
 * The audit's own broken part: the r50 all-edge fillet errors, so the body on
 * screen is the 20 mm cube prefix and the fillet is missing from it.
 */
export function brokenFillet(): PartBuild {
  return makeBuild({
    tree: makeTree(["Sketch1", "Extrude1", "Fillet1"]),
    part: makePart(4),
    evaluation: makeEvaluation(["ok", "ok", "error"], {
      treeVersion: 4,
      lastGoodFeatureId: "f2",
    }),
  });
}

/**
 * N3: one bad hole pick errors `Hole 1`, and four features that have nothing to
 * do with it — a datum plane, a far-corner dowel hole, a mirror, a fillet — are
 * never attempted. The screen shows a bare brick.
 */
export function strandedDownstream(): PartBuild {
  return makeBuild({
    tree: makeTree([
      "Base profile",
      "Base extrude",
      "Hole 1",
      "Mirror plane x=45",
      "Dowel hole",
      "Corner fillets R8",
    ]),
    part: makePart(9),
    evaluation: makeEvaluation(
      ["ok", "ok", "error", "skipped", "skipped", "skipped"],
      { treeVersion: 9, lastGoodFeatureId: "f2" },
    ),
  });
}

/** The travel stop after `Extrude1`: a DELIBERATE prefix, nothing broken. */
export function rolledBack(): PartBuild {
  return makeBuild({
    tree: makeTree(["Sketch1", "Extrude1", "Fillet1"], {
      treeVersion: 5,
      rollbackFeatureId: "f2",
    }),
    part: makePart(5),
    evaluation: makeEvaluation(["ok", "ok"], {
      treeVersion: 5,
      lastGoodFeatureId: "f2",
    }),
  });
}

/** A solved sketch and nothing else: a tree with no body to export. */
export function sketchOnly(): PartBuild {
  return makeBuild({
    tree: makeTree(["Sketch1"]),
    part: makePart(3),
    evaluation: makeEvaluation(["ok"], { meshGlbId: null, properties: null }),
  });
}

/**
 * EXPORT-3's NEGATIVE CONTROL: a failure with no successfully built body behind
 * it. The fillet is the FIRST body-making operation attempted and it errors, so
 * the strict-prefix rule has no prefix to fall back to — `mesh_glb_id` and
 * `properties` are both null and there is genuinely nothing to write.
 *
 * This is the fixture that keeps "allow the last good body" from degenerating
 * into "always allow": without it, enabling export unconditionally passes every
 * other test in the file. Reproduced against the real stack on 2026-08-28 —
 * the gateway answers this exact tree with a 422 `tree_export_failed`
 * (`no_target_body`), so the client gate and the server agree.
 */
export function brokenBeforeAnyBody(): PartBuild {
  return makeBuild({
    tree: makeTree(["Sketch1", "Fillet1"], { treeVersion: 4 }),
    part: makePart(4),
    evaluation: makeEvaluation(["ok", "error"], {
      treeVersion: 4,
      meshGlbId: null,
      properties: null,
    }),
  });
}

/**
 * QA-R4, the window itself: the user has submitted a feature edit and NO cache
 * knows yet — part, tree and evaluation all still read version 7, so the
 * provenance test comes out "current" about a body the server has already
 * superseded. Only the in-flight write says otherwise, which is why it is an
 * input to the derivation and not merely a spinner somewhere.
 */
export function midWrite(): PartBuild {
  return makeBuild({
    tree: makeTree(["Sketch1", "Extrude1", "Pattern1"], { treeVersion: 7 }),
    part: makePart(7),
    evaluation: makeEvaluation(["ok", "ok", "ok"], {
      treeVersion: 7,
      lastGoodFeatureId: "f3",
    }),
    writing: true,
  });
}

/**
 * The second half of the same window: the write has REPLIED with version 8 and
 * both caches still hold 7. The provenance fact stands on its own here — the
 * in-flight flag is deliberately false, so this is what the derivation says
 * when a caller records the version but drops the flag.
 */
export function justWritten(): PartBuild {
  return makeBuild({
    tree: makeTree(["Sketch1", "Extrude1", "Pattern1"], { treeVersion: 7 }),
    part: makePart(7),
    evaluation: makeEvaluation(["ok", "ok", "ok"], {
      treeVersion: 7,
      lastGoodFeatureId: "f3",
    }),
    writtenTreeVersion: 8,
  });
}

/** Built from tree 3, part has moved to 4, and nothing is in flight. */
export function unverified(): PartBuild {
  return makeBuild({
    tree: makeTree(["Sketch1", "Extrude1"], { treeVersion: 3 }),
    part: makePart(4),
    evaluation: makeEvaluation(["ok", "ok"], {
      treeVersion: 3,
      lastGoodFeatureId: "f2",
    }),
  });
}
