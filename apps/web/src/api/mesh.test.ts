import { createGatewayClient } from "@loft/ts-client/gateway";
import { describe, expect, it } from "vitest";

import { fetchBodyMesh, MeshNotFoundError } from "./mesh";

/** Typed client whose transport is a canned response — no network. */
function clientReturning(response: Response) {
  return createGatewayClient({
    baseUrl: "http://gateway.test",
    fetch: () => Promise.resolve(response),
  });
}

const MESH_ID = "sha256:0123456789abcdef";

describe("fetchBodyMesh", () => {
  it("returns the GLB bytes on a hit", async () => {
    const bytes = new Uint8Array([0x67, 0x6c, 0x54, 0x46, 2, 0, 0, 0]); // "glTF"
    const client = clientReturning(
      new Response(bytes, {
        status: 200,
        headers: { "Content-Type": "model/gltf-binary" },
      }),
    );
    const glb = await fetchBodyMesh(MESH_ID, client);
    expect(glb).toBeInstanceOf(ArrayBuffer);
    expect(new Uint8Array(glb)).toEqual(bytes);
  });

  it("maps a 404 mesh_not_found to the re-evaluate signal", async () => {
    const client = clientReturning(
      new Response(
        JSON.stringify({
          error: { code: "mesh_not_found", message: "evicted" },
        }),
        { status: 404, headers: { "Content-Type": "application/json" } },
      ),
    );
    await expect(fetchBodyMesh(MESH_ID, client)).rejects.toBeInstanceOf(
      MeshNotFoundError,
    );
  });

  it("carries the requested content address on the typed error", async () => {
    const client = clientReturning(new Response(null, { status: 404 }));
    await expect(fetchBodyMesh(MESH_ID, client)).rejects.toMatchObject({
      meshGlbId: MESH_ID,
    });
  });

  it("surfaces the envelope message on other upstream failures", async () => {
    const client = clientReturning(
      new Response(
        JSON.stringify({
          error: { code: "upstream_unavailable", message: "geometry is down" },
        }),
        { status: 502, headers: { "Content-Type": "application/json" } },
      ),
    );
    await expect(fetchBodyMesh(MESH_ID, client)).rejects.toThrow(
      /geometry is down/,
    );
  });
});
