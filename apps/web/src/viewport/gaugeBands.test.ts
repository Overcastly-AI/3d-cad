import { describe, expect, it, vi } from "vitest";

import { attachBand } from "./gaugeBands";

/** A band as the frame loop sees it: only `style.display` is read. */
const band = (display: string): HTMLDivElement =>
  ({ style: { display } }) as unknown as HTMLDivElement;

describe("attachBand", () => {
  it("asks for a frame when a band mounts un-placed", () => {
    const bands: (HTMLDivElement | null)[] = [];
    const invalidate = vi.fn();
    const node = band("none");
    attachBand(bands, 3, node, invalidate);
    expect(bands[3]).toBe(node);
    expect(invalidate).toHaveBeenCalledTimes(1);
  });

  it("costs no frame for a band the frame loop already placed", () => {
    const bands: (HTMLDivElement | null)[] = [];
    const invalidate = vi.fn();
    const node = band("block");
    attachBand(bands, 0, node, invalidate);
    expect(bands[0]).toBe(node);
    expect(invalidate).not.toHaveBeenCalled();
  });

  it("clears the slot on detach without asking for a frame", () => {
    const node = band("block");
    const bands: (HTMLDivElement | null)[] = [node];
    const invalidate = vi.fn();
    attachBand(bands, 0, null, invalidate);
    expect(bands[0]).toBeNull();
    expect(invalidate).not.toHaveBeenCalled();
  });
});
