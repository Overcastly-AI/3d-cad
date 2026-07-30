import { createGatewayClient } from "@loft/ts-client/gateway";
import { describe, expect, it } from "vitest";

import {
  fetchMaterials,
  type MaterialAssignment,
  updatePartMaterials,
} from "./materials";

/** Typed client whose transport is a canned response — no network. */
function clientReturning(response: Response, seen?: { request?: Request }) {
  return createGatewayClient({
    baseUrl: "http://gateway.test",
    fetch: (request: Request) => {
      if (seen !== undefined) seen.request = request;
      return Promise.resolve(response);
    },
  });
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const PART = {
  id: "p1",
  name: "Bracket",
  owner_id: "u1",
  length_unit: "mm",
  tree_version: 4,
  eval_state: "stale",
  last_eval_status: "ok",
  last_eval_at: "2026-07-30T00:00:00Z",
  last_eval_tree_version: 3,
  materials: { default_material: "steel_1018", bodies: [] },
  created_at: "2026-07-30T00:00:00Z",
  updated_at: "2026-07-30T00:00:00Z",
};

describe("fetchMaterials", () => {
  it("returns the SERVED library — densities are never typed client-side", async () => {
    const library = await fetchMaterials(
      clientReturning(
        json({
          materials: [
            {
              key: "aluminium_6061",
              name: "Aluminium 6061",
              density_kg_m3: 2700,
            },
          ],
        }),
      ),
    );
    expect(library).toHaveLength(1);
    expect(library[0]?.key).toBe("aluminium_6061");
    expect(library[0]?.density_kg_m3).toBe(2700);
  });

  it("reads it from the GATEWAY, never past it", async () => {
    const seen: { request?: Request } = {};
    await fetchMaterials(clientReturning(json({ materials: [] }), seen));
    expect(seen.request?.url).toBe("http://gateway.test/api/v1/materials");
  });

  it("surfaces the server envelope when the library cannot be read", async () => {
    const client = clientReturning(
      json(
        {
          error: { code: "upstream_unavailable", message: "documents is down" },
        },
        503,
      ),
    );
    await expect(fetchMaterials(client)).rejects.toThrow("documents is down");
  });
});

describe("updatePartMaterials", () => {
  it("PATCHes the WHOLE assignment under the tree-version guard", async () => {
    const seen: { request?: Request } = {};
    const assignment: MaterialAssignment = {
      default_material: "steel_1018",
      bodies: [{ base_feature_id: "b1", material: "aluminium_6061" }],
    };
    const part = await updatePartMaterials(
      "p1",
      assignment,
      4,
      clientReturning(json(PART), seen),
    );
    expect(seen.request?.method).toBe("PATCH");
    expect(seen.request?.url).toBe("http://gateway.test/api/v1/parts/p1");
    expect(await seen.request?.json()).toEqual({
      materials: assignment,
      expected_tree_version: 4,
    });
    expect(part.materials.default_material).toBe("steel_1018");
  });

  it("sends an EMPTY assignment to clear back to no material", async () => {
    const seen: { request?: Request } = {};
    await updatePartMaterials(
      "p1",
      { default_material: null, bodies: [] },
      4,
      clientReturning(json(PART), seen),
    );
    const body = (await seen.request?.json()) as {
      materials: MaterialAssignment;
    };
    expect(body.materials.default_material).toBeNull();
    expect(body.materials.bodies).toEqual([]);
  });

  it("surfaces the stale-version envelope verbatim (422)", async () => {
    const client = clientReturning(
      json(
        {
          error: {
            code: "stale_tree_version",
            message: "The part changed since you loaded it.",
          },
        },
        422,
      ),
    );
    await expect(
      updatePartMaterials("p1", { default_material: null }, 1, client),
    ).rejects.toThrow("The part changed since you loaded it.");
  });
});
