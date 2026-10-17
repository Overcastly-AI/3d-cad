import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchThumbnail, type ThumbnailResult } from "../api/thumbnails";
import { DocumentThumbnail } from "./DocumentThumbnail";

vi.mock("../api/thumbnails", () => ({ fetchThumbnail: vi.fn() }));
const fetchMock = vi.mocked(fetchThumbnail);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function tile(version = 1) {
  return render(
    <DocumentThumbnail kind="part" id="p1" version={version} name="Bracket" />,
    { wrapper },
  );
}

const thumbnail = () => screen.getByTestId("document-thumbnail");

beforeEach(() => {
  let next = 0;
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => `blob:thumb-${(next += 1)}`),
    revokeObjectURL: vi.fn(),
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  fetchMock.mockReset();
});

describe("DocumentThumbnail", () => {
  it("shows the placeholder while rendering, then the picture", async () => {
    let resolve: (result: ThumbnailResult) => void = () => undefined;
    fetchMock.mockReturnValue(
      new Promise((done) => {
        resolve = done;
      }),
    );
    tile();
    expect(thumbnail().dataset.thumbnailState).toBe("loading");
    expect(screen.queryByRole("img")).toBeNull();

    resolve({ kind: "image", blob: new Blob(["png"]) });
    await waitFor(() =>
      expect(thumbnail().dataset.thumbnailState).toBe("ready"),
    );
    expect(
      screen.getByRole("img", { name: "Preview of Bracket" }),
    ).toHaveAttribute("src", "blob:thumb-1");
    expect(fetchMock).toHaveBeenCalledWith("part", "p1");
  });

  it("keeps the placeholder for a part that does not rebuild", async () => {
    fetchMock.mockResolvedValue({ kind: "unavailable", reason: "failed" });
    tile();
    await waitFor(() =>
      expect(thumbnail().dataset.thumbnailState).toBe("failed"),
    );
    expect(screen.queryByRole("img")).toBeNull();
    expect(thumbnail()).toHaveAttribute(
      "title",
      "No preview: this document does not rebuild.",
    );
  });

  it("never shows the old picture for a new version", async () => {
    fetchMock.mockResolvedValueOnce({ kind: "image", blob: new Blob(["v1"]) });
    const view = tile(1);
    await waitFor(() =>
      expect(thumbnail().dataset.thumbnailState).toBe("ready"),
    );

    fetchMock.mockResolvedValueOnce({ kind: "unavailable", reason: "failed" });
    view.rerender(
      <DocumentThumbnail kind="part" id="p1" version={2} name="Bracket" />,
    );
    await waitFor(() =>
      expect(thumbnail().dataset.thumbnailState).toBe("failed"),
    );
    expect(screen.queryByRole("img")).toBeNull();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:thumb-1");
  });
});
