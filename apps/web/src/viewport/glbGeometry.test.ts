import { BufferGeometry } from "three";
import { describe, expect, it, vi } from "vitest";

import { loadGlbGeometry, parseGlbGeometry } from "./glbGeometry";

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
