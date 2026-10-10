import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as api from "../api/assemblies";
import {
  type InstanceResponse,
  StaleAssemblyVersionError,
} from "../api/assemblies";
import { copyBlocker, useCopyComponent } from "./useCopyComponent";

const copyMock = vi.spyOn(api, "copyInstance");

const source = {
  id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  name: "Hole plate <1>",
  grounded: true,
} as InstanceResponse;
const copied = {
  id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
  name: "Hole plate <3>",
  grounded: false,
} as InstanceResponse;

function setup() {
  const refreshGraph = vi.fn(() => Promise.resolve());
  const onError = vi.fn();
  const hook = renderHook(() =>
    useCopyComponent({
      assemblyId: "asm",
      docVersion: 7,
      refreshGraph,
      onError,
    }),
  );
  return { hook, refreshGraph, onError };
}

afterEach(() => copyMock.mockReset());

describe("copyBlocker", () => {
  it("needs a selection, and offers a grounded one", () => {
    expect(copyBlocker(null, false)).toMatch(/Select a component/);
    expect(copyBlocker(source, false)).toBeNull();
    expect(copyBlocker(source, true)).toMatch(/Waiting/);
  });
});

describe("useCopyComponent", () => {
  it("sends ONE copy at the current version and resolves to the copy once the graph has it", async () => {
    copyMock.mockResolvedValue({ doc_version: 8, instance: copied });
    const { hook, refreshGraph } = setup();

    let result: InstanceResponse | null = null;
    await act(async () => {
      const first = hook.result.current.copy(source.id);
      // A held chord: the repeat lands before the first write settles.
      const repeat = hook.result.current.copy(source.id);
      result = await first;
      expect(await repeat).toBeNull();
    });

    expect(copyMock).toHaveBeenCalledOnce();
    expect(copyMock).toHaveBeenCalledWith("asm", source.id, {
      expected_version: 7,
    });
    expect(refreshGraph).toHaveBeenCalledOnce();
    expect(result).toEqual(copied);
    expect(hook.result.current.copying).toBe(false);
  });

  it("a stale version resyncs the graph and says so", async () => {
    copyMock.mockImplementation(() =>
      Promise.reject(new StaleAssemblyVersionError("graph moved on")),
    );
    const { hook, refreshGraph, onError } = setup();

    let result: InstanceResponse | null = copied;
    await act(async () => {
      result = await hook.result.current.copy(source.id);
    });

    expect(result).toBeNull();
    expect(refreshGraph).toHaveBeenCalledOnce();
    expect(onError).toHaveBeenLastCalledWith("graph moved on");
  });
});
