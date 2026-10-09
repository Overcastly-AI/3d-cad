/**
 * The sketch Point tool (Fusion's, SolidWorks' and Onshape's Point): one click
 * places one `point` entity, with the same snapping, coincident inference,
 * typed X/Y entry, constraints, selection and delete as every other entity.
 * A sketch of one point is a loft apex.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { CONSTRAINT_SHORTCUTS, CONSTRUCTION_SHORTCUT } from "./constraints";
import { PLANE_BASES } from "./plane";
import { pointEntryOpening } from "./pointEntry";
import {
  isApexSketch,
  pointEntityStations,
  stationPositions,
} from "./pointEntity";
import { useSketchStore } from "./store";
import {
  dragDraws,
  finishPlacement,
  placePoint,
  placesPoints,
  previewEntities,
  TOOL_SHORTCUTS,
  type SketchEntity,
} from "./tools";
import {
  closedProfileOptions,
  defaultProfileId,
  profileOptions,
} from "../features/extrude";
import { defaultSweepProfileId } from "../features/sweep";
import type { FeatureResponse } from "../api/parts";
import { PART_CREATE_SHORTCUTS } from "../shortcuts/registry";
import { VIEW_SHORTCUTS } from "../viewport/viewCommands";

const p = (x: number, y: number) => ({ x, y });
const NONE = { suppressed: false, axisLock: false } as const;

describe("the Point tool's placement", () => {
  it("emits one point entity per click and never holds a sequence", () => {
    const result = placePoint("point", [], p(0, 30), 7);
    expect(result).toEqual({
      pending: [],
      entities: [
        { id: "e7", kind: "point", position: p(0, 30), construction: false },
      ],
      nextIdIndex: 8,
    });
  });

  it("places points, has no rubber band, no drag gesture and no finish step", () => {
    expect(placesPoints("point")).toBe(true);
    expect(dragDraws("point")).toBe(false);
    expect(previewEntities("point", [], p(3, 4))).toEqual([]);
    expect(finishPlacement("point", [], 1).entities).toEqual([]);
  });
});

describe("the Point tool's key", () => {
  it("is W, and W means nothing else in a sketch or in the workspace", () => {
    expect(TOOL_SHORTCUTS.w).toBe("point");
    expect(
      Object.values(TOOL_SHORTCUTS).filter((t) => t === "point"),
    ).toHaveLength(1);
    expect(CONSTRAINT_SHORTCUTS.w).toBeUndefined();
    expect(CONSTRUCTION_SHORTCUT).not.toBe("w");
    expect(PART_CREATE_SHORTCUTS.some((s) => s.key === "w")).toBe(false);
    expect(VIEW_SHORTCUTS.w).toBeUndefined();
  });
});

describe("the Point tool in the store", () => {
  const store = useSketchStore.getState;
  beforeEach(() => {
    store().exit();
    store().begin();
    store().choosePlane("XY");
    useSketchStore.setState({ snapEnabled: true, snapStepMm: 1 });
  });

  it("a click on a line's end places a point coincident with it", () => {
    store().setTool("line");
    store().placeAt(p(0, 0));
    store().placeAt(p(20, 0));
    store().escape(); // end the chain, keep the tool family honest
    store().setTool("point");
    const at = store().aim(p(20.3, 0.2), 1, NONE);
    expect(at).toEqual(p(20, 0));
    store().placeAt(at);
    const placed = store().entities.find((e) => e.kind === "point");
    expect(placed).toMatchObject({ kind: "point", position: p(20, 0) });
    expect(store().constraints).toContainEqual({
      kind: "coincident",
      a: { entity: placed?.id, point: "position" },
      b: { entity: "e1", point: "end" },
    });
    // The tool stays armed for the next point.
    expect(store().tool).toBe("point");
    expect(store().pending).toEqual([]);
  });

  it("a typed X / Y places the point exactly, at any time", () => {
    store().setTool("point");
    const opening = pointEntryOpening(store());
    expect(opening).toMatchObject({ target: null });
    store().openPointEntry(opening?.anchor ?? p(0, 0), null);
    store().commitPointEntry(p(0, 30));
    expect(store().entities).toEqual([
      { id: "e1", kind: "point", position: p(0, 30), construction: false },
    ]);
  });

  it("a placed point is picked, fixed, and deleted like any entity", () => {
    store().setTool("point");
    store().placeAt(p(5, 5));
    store().setTool("select");
    store().selectAt(p(5.2, 5.1), 1);
    expect(store().selection).toEqual([
      { kind: "point", entity: "e1", point: "position" },
    ]);
    store().applyConstraint("fixed");
    expect(store().constraints).toContainEqual({
      kind: "fixed",
      point: { entity: "e1", point: "position" },
    });
    store().selectAt(p(5, 5), 1);
    store().deleteSelection();
    expect(store().entities.filter((e) => e.kind === "point")).toEqual([]);
    expect(store().constraints).toEqual([]);
  });
});

describe("point entities as ink and as loft sections", () => {
  const point = (
    id: string,
    construction = false,
    position = p(1, 2),
  ): SketchEntity => ({ id, kind: "point", position, construction });
  const line: SketchEntity = {
    id: "l1",
    kind: "line",
    start: p(0, 0),
    end: p(1, 0),
    construction: false,
  };

  it("draws a station per placed point, never the sketch's own origin", () => {
    const stations = pointEntityStations([
      point("e1"),
      point("e2", true),
      line,
      point("origin", true, p(0, 0)),
    ]);
    expect(stations).toEqual({ profile: [p(1, 2)], construction: [p(1, 2)] });
    // On XZ, sketch (x, y) is world (x, 0, y): the apex lands up +Z.
    expect(Array.from(stationPositions([p(0, 30)], PLANE_BASES.XZ))).toEqual([
      0, 0, 30,
    ]);
  });

  it("a sketch whose only profile entity is a point is an apex", () => {
    expect(isApexSketch({ entities: [point("a1")] })).toBe(true);
    expect(isApexSketch({ entities: [point("a1"), point("o", true)] })).toBe(
      true,
    );
    expect(isApexSketch({ entities: [point("a1"), line] })).toBe(false);
    expect(isApexSketch({ entities: [point("a1"), point("a2")] })).toBe(false);
    expect(isApexSketch({ entities: [] })).toBe(false);
  });

  it("the loft list names the apex sketch; the profile pickers drop it", () => {
    const sketch = (id: string, entities: SketchEntity[]) =>
      ({
        id,
        name: id,
        feature: {
          type: "sketch",
          version: 1,
          params: {
            plane: { kind: "datum_plane", plane: "XY" },
            entities,
            constraints: [],
          },
        },
      }) as unknown as FeatureResponse;
    const options = profileOptions([
      sketch("Sketch1", [line]),
      sketch("Sketch2", [point("a1")]),
    ]);
    expect(options.map((o) => o.apex ?? false)).toEqual([false, true]);

    // ...and by the same rule, the extrude / revolve / sweep PROFILE pickers
    // never offer it, nor default to it even when it is the newest sketch.
    const tree = [sketch("Sketch1", [line]), sketch("Sketch2", [point("a1")])];
    expect(closedProfileOptions(tree).map((o) => o.id)).toEqual(["Sketch1"]);
    expect(defaultProfileId(tree)).toBe("Sketch1");
    expect(defaultSweepProfileId([tree[1], tree[0]] as typeof tree)).toBe(
      "Sketch1",
    );
    expect(defaultProfileId([tree[1]] as typeof tree)).toBe("");
  });
});
