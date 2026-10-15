/**
 * Edit in Place, the pure half (ASM-A3-IN-CONTEXT): the other components posed
 * in the edited part's frame, a component's edge carried into that frame and
 * projected as an in-context link (one undoable sketch edit, Break-link-able),
 * and the typed errors said in words.
 */
import { beforeEach, describe, expect, it } from "vitest";

import type {
  EvaluateAssemblyResult,
  EvaluatedInstance,
} from "../api/assemblies";
import type { OverlayEdge, Vec3 } from "../api/measure";
import { breakLinks, inContextLinks, isProjected } from "../sketch/project";
import type { ContextEdge } from "../sketch/projectActions";
import { useSketchStore } from "../sketch/store";
import {
  carryOverlayEdge,
  contextOf,
  IN_CONTEXT_REASON_TEXT,
  inContextErrors,
  inContextLink,
  type InContextStatus,
} from "./inContext";

const v = (x: number, y: number, z: number): Vec3 => ({ x, y, z });
const at = (x: number, y: number, z: number) => ({
  position: v(x, y, z),
  orientation: { x: 0, y: 0, z: 0, w: 1 },
});
const RAIL = "00000000-0000-0000-0000-0000000000e1";
const PLATE = "00000000-0000-0000-0000-0000000000e2";
const ASM = "00000000-0000-0000-0000-0000000000a3";
const R1 = "00000000-0000-0000-0000-0000000000f1";
const PL = "00000000-0000-0000-0000-0000000000f3";

const instance = (id: string, part: string): EvaluatedInstance => ({
  instance_id: id,
  part_key: `${part}@tip`,
  name: id === R1 ? "Rail <1>" : "Plate <1>",
  features: [],
  grounded: true,
  placement: at(0, 0, 0),
});

const evaluation = (railY: number): EvaluateAssemblyResult => ({
  assembly_id: ASM,
  version: 1,
  status: "well_constrained",
  mate_errors: [],
  instances: [
    {
      instance_id: R1,
      part_mesh_glb_id: "sha256:rail",
      placement: at(25, railY, 10),
    },
    {
      instance_id: PL,
      part_mesh_glb_id: "sha256:plate",
      placement: at(200, 0, 26),
    },
  ],
});

/** Rail hole 8's top rim, in the rail's own frame (r 1.75 at (187.5, 0, 8)). */
const HOLE: OverlayEdge = {
  kind: "circle",
  start: v(189.25, 0, 8),
  end: v(189.25, 0, 8),
  polyline: [0, 1, 2, 3, 4].map((k) =>
    v(
      187.5 + 1.75 * Math.cos((k * Math.PI) / 2),
      1.75 * Math.sin((k * Math.PI) / 2),
      8,
    ),
  ),
  signature: {
    subshape_type: "edge",
    curve: "circle",
    end_a: v(189.25, 0, 8),
    end_b: v(189.25, 0, 8),
    midpoint: v(185.75, 0, 8),
    length_mm: 2 * Math.PI * 1.75,
  },
};

describe("contextOf", () => {
  it("poses the other components in the host part's frame", () => {
    const scene = contextOf(
      evaluation(45),
      { instances: [instance(R1, RAIL), instance(PL, PLATE)] },
      PL,
    );
    expect(scene.host?.position).toEqual(v(200, 0, 26));
    expect(scene.components).toHaveLength(1);
    const [rail] = scene.components;
    expect(rail).toMatchObject({
      occurrenceId: R1,
      partId: RAIL,
      name: "Rail <1>",
      meshId: "sha256:rail",
    });
    expect(rail?.placement.position).toEqual(v(-175, 45, -16));
  });

  it("has no host when the part is not at that occurrence", () => {
    const scene = contextOf(
      evaluation(45),
      { instances: [instance(R1, RAIL), instance(PL, PLATE)] },
      "nope",
    );
    expect(scene).toEqual({ host: null, components: [] });
  });
});

describe("projecting a component's edge", () => {
  const store = () => useSketchStore.getState();
  beforeEach(() => {
    store().exit();
    store().begin();
    store().choosePlane("XY");
  });

  it("lands as an in-context link at the carried position, one undoable edit", () => {
    const scene = contextOf(
      evaluation(45),
      { instances: [instance(R1, RAIL), instance(PL, PLATE)] },
      PL,
    );
    const rail = scene.components[0];
    if (rail === undefined) throw new Error("no rail");
    const carried = carryOverlayEdge(HOLE, rail.placement);
    expect(carried.signature.end_a).toEqual(v(14.25, 45, -8));
    const link = inContextLink({
      assemblyId: ASM,
      hostOccurrenceId: PL,
      component: rail,
      edge: HOLE,
    });
    // The link keeps the edge in the RAIL's frame, for geometry to follow.
    expect(link).toEqual({
      assembly_id: ASM,
      host_occurrence_id: PL,
      occurrence_id: R1,
      part_id: RAIL,
      edge: HOLE.signature,
    });
    const before = store().revision;
    const edge: ContextEdge = { ...carried, inContext: link };
    store().projectEdge(edge, "");
    const [entity] = store().entities;
    expect(entity).toMatchObject({
      kind: "circle",
      center: { x: 12.5, y: 45 },
      projection: { in_context: link },
    });
    expect(isProjected(entity)).toBe(true);
    expect(inContextLinks(store().entities)).toEqual([link]);
    expect(store().revision).toBe(before + 1);

    // The same edge of the same component again is refused in words.
    store().projectEdge(edge, "");
    expect(store().entities).toHaveLength(1);
    expect(store().hint).toMatch(/already projected/);

    // Break link: the circle stays where it was, unlinked.
    const broken = breakLinks([{ kind: "entity", id: "e1" }], store().entities);
    expect(broken?.entities[0]).toEqual({
      id: "e1",
      kind: "circle",
      center: { x: 12.5, y: 45 },
      radius: 1.75,
      construction: false,
    });

    store().undo();
    expect(store().entities).toHaveLength(0);
  });
});

describe("the errors", () => {
  it("names every typed reason and keeps only this part's errors", () => {
    const status = (part: string, state: "ok" | "error"): InContextStatus => ({
      part_id: part,
      feature_id: "f",
      entity_id: "e1",
      occurrence_id: R1,
      state,
      reason: state === "error" ? "component_missing" : null,
      changed: false,
    });
    expect(
      inContextErrors(
        [status(PLATE, "error"), status(PLATE, "ok"), status(RAIL, "error")],
        PLATE,
      ),
    ).toEqual([status(PLATE, "error")]);
    for (const text of Object.values(IN_CONTEXT_REASON_TEXT)) {
      expect(text.length).toBeGreaterThan(20);
    }
    expect(IN_CONTEXT_REASON_TEXT.component_missing).toMatch(/removed/);
  });
});
