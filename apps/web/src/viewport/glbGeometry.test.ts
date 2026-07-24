import { BufferGeometry, EdgesGeometry, Float32BufferAttribute } from "three";
import { describe, expect, it, vi } from "vitest";

import { loadGlbGeometry, parseGlbGeometry, subsetEdges } from "./glbGeometry";

const notCancelled = () => false;

describe("loadGlbGeometry", () => {
  it("routes a parse rejection to onError and never to onGeometry", async () => {
    const failure = new Error("Unexpected magic: 0x0BADF00D");
    const parse = vi.fn().mockRejectedValue(failure);
    const onGeometry = vi.fn();
    const onError = vi.fn();

    await expect(
      loadGlbGeometry(
        new ArrayBuffer(8),
        {
          isCancelled: notCancelled,
          onGeometry,
          onError,
        },
        parse,
      ),
    ).resolves.toBeUndefined(); // never rejects — no unhandled rejection

    expect(onError).toHaveBeenCalledExactlyOnceWith(failure);
    expect(onGeometry).not.toHaveBeenCalled();
  });

  it("normalizes non-Error rejection values", async () => {
    const parse = vi.fn().mockRejectedValue("bad chunk");
    const onError = vi.fn();

    await loadGlbGeometry(
      new ArrayBuffer(8),
      {
        isCancelled: notCancelled,
        onGeometry: vi.fn(),
        onError,
      },
      parse,
    );

    expect(onError).toHaveBeenCalledOnce();
    const error = onError.mock.calls[0]?.[0] as Error;
    expect(error).toBeInstanceOf(Error);
    expect(error.message).toContain("bad chunk");
  });

  it("treats a mesh-less scene as an error (no silent stale viewport)", async () => {
    const parse = vi.fn().mockResolvedValue(null);
    const onGeometry = vi.fn();
    const onError = vi.fn();

    await loadGlbGeometry(
      new ArrayBuffer(8),
      {
        isCancelled: notCancelled,
        onGeometry,
        onError,
      },
      parse,
    );

    expect(onGeometry).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledOnce();
    expect((onError.mock.calls[0]?.[0] as Error).message).toMatch(
      /no renderable mesh/,
    );
  });

  it("delivers the geometry on success", async () => {
    const geometry = new BufferGeometry();
    const parse = vi.fn().mockResolvedValue(geometry);
    const onGeometry = vi.fn();
    const onError = vi.fn();

    await loadGlbGeometry(
      new ArrayBuffer(8),
      {
        isCancelled: notCancelled,
        onGeometry,
        onError,
      },
      parse,
    );

    expect(onGeometry).toHaveBeenCalledExactlyOnceWith(geometry);
    expect(onError).not.toHaveBeenCalled();
  });

  it("fires no callbacks after cancellation and disposes the result", async () => {
    const geometry = new BufferGeometry();
    const dispose = vi.spyOn(geometry, "dispose");
    const onGeometry = vi.fn();
    const onError = vi.fn();

    await loadGlbGeometry(
      new ArrayBuffer(8),
      {
        isCancelled: () => true,
        onGeometry,
        onError,
      },
      vi.fn().mockResolvedValue(geometry),
    );
    await loadGlbGeometry(
      new ArrayBuffer(8),
      {
        isCancelled: () => true,
        onGeometry,
        onError,
      },
      vi.fn().mockRejectedValue(new Error("boom")),
    );

    expect(onGeometry).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
    expect(dispose).toHaveBeenCalledOnce();
  });
});

describe("parseGlbGeometry", () => {
  it("rejects on a truncated/corrupt GLB payload", async () => {
    // Valid GLB magic ("glTF") but a truncated body — the wire-corruption case.
    const truncated = new Uint8Array([0x67, 0x6c, 0x54, 0x46, 2, 0, 0, 0]);
    await expect(parseGlbGeometry(truncated.buffer)).rejects.toThrow();
  });
});

describe("subsetEdges", () => {
  /**
   * A quad split into two triangles that read as two B-rep "faces" — one draw
   * group each (group ordinal === face ordinal), exactly as the GLB merge lays
   * a real body out (one glTF primitive per face).
   */
  function twoFaceQuad(): BufferGeometry {
    const geometry = new BufferGeometry();
    geometry.setAttribute(
      "position",
      new Float32BufferAttribute([0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 1, 0], 3),
    );
    geometry.setIndex([0, 1, 2, 2, 1, 3]);
    geometry.addGroup(0, 3, 0);
    geometry.addGroup(3, 3, 1);
    return geometry;
  }

  it("traces only the requested face ordinals", () => {
    const geometry = twoFaceQuad();
    const one = subsetEdges(geometry, new Set([0]));
    const both = subsetEdges(geometry, new Set([0, 1]));
    expect(one).toBeInstanceOf(EdgesGeometry);
    expect(both).toBeInstanceOf(EdgesGeometry);
    // One triangle has fewer boundary edges than the merged pair.
    const oneCount = one?.getAttribute("position")?.count ?? 0;
    const bothCount = both?.getAttribute("position")?.count ?? 0;
    expect(oneCount).toBeGreaterThan(0);
    expect(bothCount).toBeGreaterThan(oneCount);
    one?.dispose();
    both?.dispose();
    geometry.dispose();
  });

  it("returns null for an empty subset (nothing to emphasise)", () => {
    const geometry = twoFaceQuad();
    expect(subsetEdges(geometry, new Set())).toBeNull();
    geometry.dispose();
  });

  it("returns null for an ungrouped geometry (single-material body)", () => {
    const geometry = new BufferGeometry();
    geometry.setAttribute(
      "position",
      new Float32BufferAttribute([0, 0, 0, 1, 0, 0, 0, 1, 0], 3),
    );
    geometry.setIndex([0, 1, 2]);
    expect(subsetEdges(geometry, new Set([0]))).toBeNull();
    geometry.dispose();
  });
});
