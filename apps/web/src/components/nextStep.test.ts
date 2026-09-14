/**
 * FLOW-B3's table — and, more importantly, its SILENCE.
 *
 * The half of this module most likely to rot is not "extrude proposes extrude";
 * it is "a sweep proposes nothing", because that is a property somebody closes
 * by accident while adding a row they thought was obvious. The direction brief
 * is explicit that a band which guesses is the templated affordance this wave
 * exists to avoid, so the negative cases are gated here by name, one per verb
 * that is deliberately absent.
 */
import { describe, expect, it } from "vitest";

import type { FeatureResponse } from "../api/parts";
import { nextStepFor } from "./nextStep";

/**
 * A feature stub carrying only what `nextStepFor` reads — id, order, the
 * rolled-back/suppressed flags and the type. Cast because `FeatureResponse`'s
 * `feature` is the full 19-member params union and every member's `params`
 * would have to be spelled out to name one `type` string; the cast is narrowed
 * to this file's fixtures and the module under test touches no other field.
 */
function feat(
  id: string,
  type: string,
  extra: { rolledBack?: boolean; suppressed?: boolean } = {},
): FeatureResponse {
  return {
    id,
    name: id,
    part_id: "p",
    order_index: 0,
    created_at: "2026-09-12T00:00:00Z",
    updated_at: "2026-09-12T00:00:00Z",
    rolled_back: extra.rolledBack ?? false,
    feature: {
      type,
      version: 1,
      params: {},
      ...(extra.suppressed === undefined
        ? {}
        : { suppressed: extra.suppressed }),
    },
  } as unknown as FeatureResponse;
}

const sketch = (id: string) => feat(id, "sketch");

describe("nextStepFor — the first body", () => {
  it("proposes Fillet the instant the part's first body exists", () => {
    const step = nextStepFor([sketch("s1"), feat("e1", "extrude")]);

    expect(step).toEqual({
      featureId: "e1",
      tool: "new-fillet",
      caption: "Round the new body's edges",
    });
  });

  it("proposes it for ANY verb that makes the first body, not just extrude", () => {
    // The row is "the whole MODIFY group stops being disabled", which is a fact
    // about the BODY, not about the verb that made it — so an imported solid or
    // a lofted one has to reach it too.
    for (const type of [
      "import",
      "loft",
      "revolve",
      "sheet_metal_base_flange",
    ]) {
      const step = nextStepFor([sketch("s1"), feat("b1", type)]);
      expect(step?.tool, type).toBe("new-fillet");
      expect(step?.caption, type).toBe("Round the new body's edges");
    }
  });

  it("wins over the repeat row it collides with", () => {
    // A first extrude matches BOTH rows; the brief rules the first body wins,
    // because unlocking eight tools silently is the bigger flow failure.
    expect(nextStepFor([feat("e1", "extrude")])?.tool).toBe("new-fillet");
    // …and the SECOND extrude is where the repeat row takes over.
    expect(
      nextStepFor([feat("e1", "extrude"), feat("e2", "extrude")])?.tool,
    ).toBe("new-extrude");
  });
});

describe("nextStepFor — the repeat rows", () => {
  const cases: ReadonlyArray<readonly [string, string, string]> = [
    ["extrude", "new-extrude", "Another extrude on this body"],
    ["revolve", "new-revolve", "Another revolve on this body"],
    ["hole", "new-hole", "Another hole on this body"],
    ["fillet", "new-fillet", "Another fillet on this body"],
    ["chamfer", "new-chamfer", "Another chamfer on this body"],
    [
      "sheet_metal_edge_flange",
      "new-edge-flange",
      "Another edge flange on this body",
    ],
  ];

  for (const [type, tool, caption] of cases) {
    it(`${type} proposes another ${type}`, () => {
      // A prior body, so the first-body row does not fire instead.
      const step = nextStepFor([feat("b0", "extrude"), feat("f1", type)]);
      expect(step).toEqual({ featureId: "f1", tool, caption });
    });
  }

  it("keeps every caption inside the band's caption budget", () => {
    // 33 chars is the precedent ("Repeats Hole1, not the whole body"); past it
    // the tooltip's second line stops being a glanceable line.
    for (const [type, , caption] of cases) {
      expect(caption.length, `${type}: ${caption}`).toBeLessThanOrEqual(33);
    }
  });
});

describe("nextStepFor — what it refuses to propose", () => {
  it("proposes nothing for a verb we cannot name a reason for", () => {
    // One case per deliberately-absent verb. If a row is added for any of
    // these, this test must be deleted ON PURPOSE, with the reason written in
    // the table — which is the whole point of gating the silence.
    for (const type of [
      "sweep",
      "loft",
      "shell",
      "draft",
      "pattern",
      "mirror",
      "boolean",
      "import",
      "sheet_metal_hem",
      "sheet_metal_corner_relief",
    ]) {
      // A prior body, so the first-body row cannot answer for it.
      expect(nextStepFor([feat("b0", "extrude"), feat("x1", type)]), type).toBe(
        null,
      );
    }
  });

  it("proposes nothing after a sketch — B1 owns that transition", () => {
    // The sketch -> extrude moment gets a viewport leader note, not a band dot.
    // Two marks for one transition is the two-dialects failure drawn on screen.
    expect(nextStepFor([feat("e1", "extrude"), sketch("s2")])).toBe(null);
    expect(nextStepFor([sketch("s1")])).toBe(null);
  });

  it("proposes nothing for a datum, and nothing on an empty tree", () => {
    expect(nextStepFor([])).toBe(null);
    expect(nextStepFor([feat("b0", "extrude"), feat("d1", "datum")])).toBe(
      null,
    );
  });

  it("reads past a rolled-back tip to the feature that is actually built", () => {
    // The rollback bar is "the tip is earlier than the last row", so a proposal
    // derived from the last ROW would describe geometry that is not on screen.
    const step = nextStepFor([
      feat("b0", "extrude"),
      feat("h1", "hole"),
      feat("c1", "chamfer", { rolledBack: true }),
    ]);
    expect(step?.featureId).toBe("h1");
    expect(step?.tool).toBe("new-hole");
  });

  it("reads past a suppressed tip for the same reason", () => {
    const step = nextStepFor([
      feat("b0", "extrude"),
      feat("h1", "hole"),
      feat("c1", "chamfer", { suppressed: true }),
    ]);
    expect(step?.tool).toBe("new-hole");
  });

  it("does not count a rolled-back body toward the first-body row", () => {
    // Only one body is BUILT here, so the fillet unlock is still news.
    const step = nextStepFor([
      feat("b0", "extrude", { rolledBack: true }),
      feat("b1", "extrude"),
    ]);
    expect(step?.tool).toBe("new-fillet");
  });
});
