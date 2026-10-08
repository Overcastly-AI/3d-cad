import { createGatewayClient } from "@loft/ts-client/gateway";
import { describe, expect, it } from "vitest";

import { StaleTreeVersionError } from "./parts";
import {
  listPartVersions,
  PartVersionLimitError,
  restorePartVersion,
  savePartVersion,
} from "./versions";

const PART = "5d7c1f0e-1111-4222-8333-944445555666";

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, message: string, details?: unknown) {
  return { error: { code, message, details, request_id: "r" } };
}

function clientCapturing(response: Response) {
  const seen: Request[] = [];
  const client = createGatewayClient({
    baseUrl: "http://gateway.test",
    fetch: (request: Request) => {
      seen.push(request);
      return Promise.resolve(response);
    },
  });
  return { client, seen };
}

const V1 = {
  seq: 1,
  name: "v1",
  message: "",
  author: null,
  created_at: "2026-10-08T11:00:00Z",
  feature_count: 2,
  tree_sha256: "a".repeat(64),
};

describe("part versions api", () => {
  it("lists a part's versions", async () => {
    const { client, seen } = clientCapturing(json({ versions: [V1] }, 200));
    await expect(listPartVersions(PART, client)).resolves.toEqual([V1]);
    expect(new URL(seen[0]!.url).pathname).toBe(
      `/api/v1/parts/${PART}/versions`,
    );
  });

  it("saves with the name, message and the tree version on screen", async () => {
    const { client, seen } = clientCapturing(json(V1, 201));
    await savePartVersion(
      PART,
      { name: "v1", message: "first", expectedTreeVersion: 7 },
      client,
    );
    expect(seen[0]!.method).toBe("POST");
    expect(JSON.parse(await seen[0]!.text())).toEqual({
      name: "v1",
      message: "first",
      expected_tree_version: 7,
    });
  });

  it("types the count cap as a sentence a person can act on", async () => {
    const { client } = clientCapturing(
      json(envelope("part_version_limit", "raw", { max_versions: 100 }), 409),
    );
    const error = await savePartVersion(PART, { name: "v101" }, client).catch(
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(PartVersionLimitError);
    expect((error as PartVersionLimitError).cap).toBe("count");
    expect((error as Error).message).toBe(
      "This part already has 100 versions, the limit for one part. Versions are never deleted, so duplicate the part to keep versioning it.",
    );
  });

  it("types the byte cap in MiB, not bytes", async () => {
    const { client } = clientCapturing(
      json(
        envelope("part_version_limit", "raw (134217728 bytes)", {
          max_bytes: 128 * 1024 * 1024,
        }),
        409,
      ),
    );
    const error = (await savePartVersion(PART, { name: "big" }, client).catch(
      (e: unknown) => e,
    )) as PartVersionLimitError;
    expect(error.cap).toBe("bytes");
    expect(error.message).toContain("128 MiB limit");
    expect(error.message).not.toContain("134217728");
  });

  it("a stale save or restore is typed for the soft resync", async () => {
    const stale = () =>
      clientCapturing(json(envelope("stale_tree_version", "moved"), 422))
        .client;
    await expect(
      savePartVersion(PART, { name: "x" }, stale()),
    ).rejects.toBeInstanceOf(StaleTreeVersionError);
    await expect(
      restorePartVersion(PART, 1, 3, stale()),
    ).rejects.toBeInstanceOf(StaleTreeVersionError);
  });

  it("restores by seq with the expected tree version", async () => {
    const tree = {
      part_id: PART,
      tree_version: 9,
      rollback_feature_id: null,
      can_undo: true,
      can_redo: false,
      features: [],
    };
    const { client, seen } = clientCapturing(json(tree, 200));
    await expect(restorePartVersion(PART, 2, 8, client)).resolves.toEqual(tree);
    expect(new URL(seen[0]!.url).pathname).toBe(
      `/api/v1/parts/${PART}/versions/2/restore`,
    );
    expect(JSON.parse(await seen[0]!.text())).toEqual({
      expected_tree_version: 8,
    });
  });

  it("other refusals surface the server's message", async () => {
    const { client } = clientCapturing(
      json(envelope("part_restore_conflict", "A drawing needs Sketch1."), 409),
    );
    await expect(restorePartVersion(PART, 1, 1, client)).rejects.toThrow(
      "A drawing needs Sketch1.",
    );
  });
});
