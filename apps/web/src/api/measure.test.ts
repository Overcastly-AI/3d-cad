import { createGatewayClient } from "@loft/ts-client/gateway";
import { describe, expect, it } from "vitest";

import {
  fetchOverlay,
  measureTargets,
  MeasureError,
  type EvaluateTreeRequest,
} from "./measure";

/** Typed client whose transport is a canned response — no network. */
function clientReturning(response: Response) {
  return createGatewayClient({
    baseUrl: "http://gateway.test",
    fetch: () => Promise.resolve(response),
  });
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const TREE: EvaluateTreeRequest = {
  part_id: "00000000-0000-0000-0000-000000000000",
  tree_version: 3,
  linear_deflection: 0.1,
  features: [],
};

describe("fetchOverlay", () => {
  it("returns the vertices + edges on success", async () => {
    const result = {
      vertices: [{ x: 0, y: 0, z: 0 }],
      edges: [
        {
          kind: "line",
          start: { x: 0, y: 0, z: 0 },
          end: { x: 1, y: 0, z: 0 },
          polyline: [
            { x: 0, y: 0, z: 0 },
            { x: 1, y: 0, z: 0 },
          ],
        },
      ],
    };
    const overlay = await fetchOverlay(TREE, clientReturning(json(result)));
    expect(overlay.vertices).toHaveLength(1);
    expect(overlay.edges[0]?.kind).toBe("line");
  });

  it("throws a typed MeasureError carrying the envelope code", async () => {
    const client = clientReturning(
      json({ error: { code: "tree_overlay_failed", message: "no body" } }, 422),
    );
    await expect(fetchOverlay(TREE, client)).rejects.toMatchObject({
      name: "MeasureError",
      code: "tree_overlay_failed",
      message: "no body",
    });
  });
});

describe("measureTargets", () => {
  it("returns the measured distance on success", async () => {
    const result = {
      kind: "point_point",
      distance: 37.416573867739416,
      delta: { x: 10, y: 20, z: 30 },
      point_on_a: { x: 0, y: 0, z: 0 },
      point_on_b: { x: 10, y: 20, z: 30 },
      angle_deg: null,
    };
    const measured = await measureTargets(
      {
        a: { kind: "point", position: { x: 0, y: 0, z: 0 } },
        b: { kind: "point", position: { x: 10, y: 20, z: 30 } },
      },
      clientReturning(json(result)),
    );
    expect(measured.distance).toBeCloseTo(37.4166, 3);
    expect(measured.kind).toBe("point_point");
  });

  it("maps edge_index_out_of_range to a typed MeasureError", async () => {
    const client = clientReturning(
      json(
        { error: { code: "edge_index_out_of_range", message: "bad index" } },
        422,
      ),
    );
    await expect(
      measureTargets(
        {
          a: { kind: "edge", index: 99 },
          b: { kind: "point", position: { x: 0, y: 0, z: 0 } },
          tree: TREE,
        },
        client,
      ),
    ).rejects.toBeInstanceOf(MeasureError);
  });
});
