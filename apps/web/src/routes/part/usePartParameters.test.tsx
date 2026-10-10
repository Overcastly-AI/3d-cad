/**
 * The Parameters panel's writes (PART-PARAMETERS review, two data-loss bugs):
 *
 *  1. a save must not drop an unsaved new row it left out of the PUT;
 *  2. a PUT carries the version the ON-SCREEN table was read at, so rows read
 *     before an undo are refused as stale instead of written over it.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api/parameters";
import type { PartParametersResponse } from "../../api/parameters";
import { StaleTreeVersionError } from "../../api/parts";
import { usePartParameters } from "./usePartParameters";

const W_ID = "00000000-0000-4000-8000-000000000001";

function table(version: number, w: string, value: number) {
  return {
    tree_version: version,
    parameters: [
      {
        id: W_ID,
        name: "W",
        expression: w,
        unit: "length" as const,
        value,
        comment: "",
      },
    ],
  } satisfies PartParametersResponse;
}

afterEach(() => vi.restoreAllMocks());

function setup(
  fetchImpl: (version: number) => Promise<PartParametersResponse>,
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  let version = 1;
  vi.spyOn(api, "fetchPartParameters").mockImplementation(() =>
    fetchImpl(version),
  );
  const put = vi.spyOn(api, "putPartParameters");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const view = renderHook(
    ({ treeVersion }: { treeVersion: number }) =>
      usePartParameters({
        partId: "p",
        queryClient: client,
        tree: { data: { tree_version: treeVersion } } as never,
        mode: "off",
        lengthUnit: "mm",
        editor: null,
        refreshTreeAndBody: vi.fn(async () => {}),
        beginTreeWrite: vi.fn(),
        endTreeWrite: vi.fn(),
        noteWrittenTreeVersion: vi.fn(),
      }),
    { wrapper, initialProps: { treeVersion: 1 } },
  );
  const moveTree = (next: number) => {
    version = next;
    view.rerender({ treeVersion: next });
  };
  return { ...view, put, moveTree };
}

describe("usePartParameters", () => {
  it("keeps an unsaved new row through a save that left it out", async () => {
    const { result, put } = setup(async () => table(1, "10", 10));
    act(() => result.current.openPanel());
    await waitFor(() => expect(result.current.rows).toHaveLength(1));
    put.mockResolvedValue(table(2, "20", 20));

    act(() => result.current.addRow());
    const draftId = result.current.rows?.[1]?.id as string;
    act(() => result.current.commitCell(draftId, "name", "Height"));
    act(() => result.current.commitCell(draftId, "comment", "overall height"));
    // The draft has no expression yet: nothing to send so far.
    expect(put).not.toHaveBeenCalled();
    act(() => result.current.commitCell(W_ID, "expression", "20"));
    await waitFor(() => expect(result.current.saving).toBe(false));

    expect(put).toHaveBeenCalledOnce();
    expect(put.mock.calls[0]?.[1].map((row) => row.name)).toEqual(["W"]);
    expect(result.current.rows).toEqual([
      expect.objectContaining({ name: "W", expression: "20", value: 20 }),
      expect.objectContaining({
        id: draftId,
        name: "Height",
        comment: "overall height",
        expression: "",
      }),
    ]);
  });

  it("sends the on-screen version after an undo, so the write is refused as stale", async () => {
    let releaseV2: (value: PartParametersResponse) => void = () => {};
    const { result, put, moveTree } = setup((version) =>
      version === 1
        ? Promise.resolve(table(1, "10", 10))
        : new Promise((resolve) => {
            releaseV2 = resolve;
          }),
    );
    act(() => result.current.openPanel());
    await waitFor(() => expect(result.current.rows).toHaveLength(1));

    // An undo moves the tree to version 2; its table has not landed yet.
    moveTree(2);
    put.mockRejectedValue(new StaleTreeVersionError("stale"));
    act(() => result.current.commitCell(W_ID, "expression", "30"));
    await waitFor(() => expect(result.current.stale).toBe(true));
    // Read at 1, sent at 1: never the newer version the rows did not see.
    expect(put.mock.calls[0]?.[2]).toBe(1);

    // The undone table lands; the edit is re-applied on top of it.
    act(() => releaseV2(table(2, "5", 5)));
    await waitFor(() =>
      expect(result.current.rows?.[0]).toMatchObject({
        expression: "30",
        value: 5,
      }),
    );
    // Retry now sends at 2.
    put.mockResolvedValue(table(3, "30", 30));
    act(() => result.current.retry());
    await waitFor(() => expect(put).toHaveBeenCalledTimes(2));
    expect(put.mock.calls[1]?.[2]).toBe(2);
  });

  it("holds edits when a re-read fails, and lets go once it succeeds", async () => {
    let fail = false;
    const { result, put, moveTree } = setup(async (version) => {
      if (fail) throw new Error("gateway down");
      return table(version, "10", 10);
    });
    act(() => result.current.openPanel());
    await waitFor(() => expect(result.current.rows).toHaveLength(1));

    fail = true;
    moveTree(2);
    await waitFor(() => expect(result.current.refreshFailed).toBe(true));
    expect(result.current.blockedReason).toMatch(/could not be read/);
    act(() => result.current.commitCell(W_ID, "expression", "30"));
    expect(put).not.toHaveBeenCalled();
    // The typed text is kept.
    expect(result.current.rows?.[0]?.expression).toBe("30");

    fail = false;
    act(() => result.current.reload());
    await waitFor(() => expect(result.current.refreshFailed).toBe(false));
    expect(result.current.blockedReason).toBeUndefined();
  });
});
