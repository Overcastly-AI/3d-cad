import { createGatewayClient } from "@loft/ts-client/gateway";
import { describe, expect, it } from "vitest";

import type { SketchEntity } from "../sketch/tools";
import { cornerSketch, SketchEditError } from "./sketchEdit";

/** Capture the outbound request so we can assert the body the client builds. */
function recordingClient(response: Response) {
  const calls: Array<{ url: string; method: string; body: unknown }> = [];
  const client = createGatewayClient({
    baseUrl: "http://gateway.test",
    // openapi-fetch dispatches a single `Request` instance.
    fetch: async (request: Request) => {
      const body = await request
        .clone()
        .text()
        .then((t) => (t ? JSON.parse(t) : undefined));
      calls.push({ url: request.url, method: request.method, body });
      return response;
    },
  });
  return { client, calls };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const ENTITIES: SketchEntity[] = [
  {
    id: "e1",
    kind: "line",
    start: { x: 0, y: 0 },
    end: { x: 40, y: 0 },
    construction: false,
  },
  {
    id: "e2",
    kind: "line",
    start: { x: 40, y: 0 },
    end: { x: 40, y: 25 },
    construction: false,
  },
];

describe("cornerSketch — builds the fillet/chamfer request", () => {
  it("posts fillet with a `radius` field to the fillet endpoint", async () => {
    const { client, calls } = recordingClient(json({ entities: ENTITIES }));
    await cornerSketch(
      "fillet",
      { entities: ENTITIES, a: "e1", b: "e2", value: 3 },
      client,
    );
    const call = calls[0];
    expect(call?.url).toContain("/geometry/sketch/fillet");
    expect(call?.method).toBe("POST");
    expect(call?.body).toEqual({
      entities: ENTITIES,
      a: "e1",
      b: "e2",
      radius: 3,
    });
  });

  it("posts chamfer with a `distance` field to the chamfer endpoint", async () => {
    const { client, calls } = recordingClient(json({ entities: ENTITIES }));
    await cornerSketch(
      "chamfer",
      { entities: ENTITIES, a: "e1", b: "e2", value: 4 },
      client,
    );
    const call = calls[0];
    expect(call?.url).toContain("/geometry/sketch/chamfer");
    expect(call?.body).toEqual({
      entities: ENTITIES,
      a: "e1",
      b: "e2",
      distance: 4,
    });
  });

  it("throws a typed SketchEditError carrying the 422 envelope code", async () => {
    const { client } = recordingClient(
      json(
        {
          error: {
            code: "sketch_corner_too_large",
            message: "Radius is too large for this corner.",
          },
        },
        422,
      ),
    );
    await expect(
      cornerSketch(
        "fillet",
        { entities: ENTITIES, a: "e1", b: "e2", value: 999 },
        client,
      ),
    ).rejects.toMatchObject({
      name: "SketchEditError",
      code: "sketch_corner_too_large",
    });
  });

  it("keeps the envelope message verbatim on the error", async () => {
    const { client } = recordingClient(
      json(
        {
          error: {
            code: "sketch_unsupported_entity",
            message: "Fillet needs two lines.",
          },
        },
        422,
      ),
    );
    const error = await cornerSketch(
      "chamfer",
      { entities: ENTITIES, a: "e1", b: "e2", value: 2 },
      client,
    ).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(SketchEditError);
    expect((error as SketchEditError).message).toBe("Fillet needs two lines.");
  });
});
