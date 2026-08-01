/**
 * The folder half of the register (#WS2) — what a divider row may SAY.
 *
 * The defect class this whole row is being held to is "a surface asserting
 * something it does not know", so the assertions are aimed there rather than at
 * the happy path: the count must be the server's, an empty folder must not
 * print two zeroes, and a refused delete must NAME what is inside instead of
 * saying "not empty". The rest (the ruled form) is a screenshot's job.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { type FolderResponse, FolderNotEmptyError } from "../api/folders";
import {
  DocumentRegister,
  type RegisterCopy,
  type RegisterDocument,
  type RegisterFiling,
} from "./DocumentRegister";

const COPY: RegisterCopy = {
  title: "Parts register",
  caption: "Your parts, oldest first.",
  noun: "part",
  nounPlural: "parts",
  loading: "Loading parts…",
  loadError: "Your parts could not be loaded.",
  deleteError: "The part could not be deleted.",
  renameError: "The part could not be renamed.",
  duplicateError: "The part could not be duplicated.",
  createError: "The part could not be created.",
  emptyHeadline: "Nothing filed here yet.",
  emptyBody: "Name your first part.",
  fieldLabel: "Part name",
  placeholder: "e.g. Bracket plate",
  createLabel: "New part",
  createFirstLabel: "Create first part",
};

const NOW = "2026-08-01T00:00:00Z";

function folder(over: Partial<FolderResponse> = {}): FolderResponse {
  return {
    id: "f1",
    owner_id: "u1",
    kind: "part",
    name: "Gearbox",
    parent_id: null,
    document_count: 0,
    child_folder_count: 0,
    created_at: NOW,
    updated_at: NOW,
    ...over,
  };
}

function doc(over: Partial<RegisterDocument> = {}): RegisterDocument {
  return {
    id: "d1",
    name: "Bracket",
    created_at: NOW,
    updated_at: NOW,
    folder_id: null,
    ...over,
  };
}

function filing(
  over: Partial<RegisterFiling<RegisterDocument>> = {},
): RegisterFiling<RegisterDocument> {
  return {
    folders: [],
    isLoading: false,
    onCreateFolder: vi.fn().mockResolvedValue(undefined),
    onRenameFolder: vi.fn().mockResolvedValue(undefined),
    onDeleteFolder: vi.fn().mockResolvedValue(undefined),
    onMoveDocument: vi.fn().mockResolvedValue(undefined),
    ...over,
  };
}

function renderRegister(
  documents: RegisterDocument[],
  filingProps: RegisterFiling<RegisterDocument>,
  onCreate = vi.fn().mockResolvedValue(undefined),
) {
  return render(
    <DocumentRegister
      idPlural="parts"
      idSingular="part"
      copy={COPY}
      documents={documents}
      isLoading={false}
      isError={false}
      error={null}
      openLink={(entry, props) => <a {...props}>{entry.name}</a>}
      onCreate={onCreate}
      onRename={vi.fn().mockResolvedValue(undefined)}
      onDuplicate={vi.fn().mockResolvedValue(undefined)}
      onDelete={vi.fn().mockResolvedValue(undefined)}
      filing={filingProps}
    />,
  );
}

describe("divider rows", () => {
  it("prints the SERVER's counts, and 'Empty' rather than two zeroes", () => {
    renderRegister(
      [doc()],
      filing({
        folders: [
          folder({
            id: "f1",
            name: "Gearbox",
            document_count: 6,
            child_folder_count: 2,
          }),
          folder({ id: "f2", name: "Shafts" }),
        ],
      }),
    );
    const counts = screen.getAllByTestId("parts-folder-count");
    // The register is holding ONE document; the folder says six, because the
    // number came from the server and is about a different set.
    expect(counts[0]).toHaveTextContent("6 parts · 2 folders");
    expect(counts[1]).toHaveTextContent("Empty");
  });

  it("says the counts are DIRECT rather than letting a reader assume", () => {
    renderRegister([], filing({ folders: [folder({ document_count: 3 })] }));
    expect(screen.getByTestId("parts-folder-count")).toHaveAttribute(
      "title",
      expect.stringContaining("sub-folders are not counted"),
    );
  });

  it("shows only the folders at THIS level, and enters one on open", () => {
    renderRegister(
      [],
      filing({
        folders: [
          folder({ id: "f1", name: "Gearbox" }),
          folder({ id: "f2", name: "Housings", parent_id: "f1" }),
        ],
      }),
    );
    expect(screen.getAllByTestId("parts-folder-row")).toHaveLength(1);

    fireEvent.click(screen.getByTestId("parts-folder-open"));
    // Inside Gearbox: its child is the only divider, and the breadcrumb says
    // where we are.
    expect(screen.getByTestId("parts-folder-open")).toHaveTextContent(
      "Housings",
    );
    expect(screen.getByTestId("parts-breadcrumb")).toHaveTextContent("Gearbox");
  });

  it("names what is inside when a delete is refused", async () => {
    const onDeleteFolder = vi.fn().mockRejectedValue(
      new FolderNotEmptyError(
        [
          { id: "d1", name: "Bracket", kind: "part" },
          { id: "f9", name: "Housings", kind: "folder" },
        ],
        "'Gearbox' still holds 2 item(s); move them out first.",
      ),
    );
    renderRegister([], filing({ folders: [folder()], onDeleteFolder }));

    fireEvent.click(screen.getByTestId("parts-folder-delete"));
    fireEvent.click(screen.getByTestId("parts-folder-delete-confirm"));

    await waitFor(() =>
      expect(screen.getByTestId("parts-folder-blocked")).toBeInTheDocument(),
    );
    const named = screen
      .getAllByTestId("parts-folder-content")
      .map((node) => node.textContent);
    expect(named).toEqual(["Bracket", "Housings"]);
    // The refusal is not a dead end AND it is not a lie about consequences.
    expect(screen.getByTestId("parts-folder-blocked")).toHaveTextContent(
      "deleting a folder never deletes what is in it",
    );
    // ...and once blocked, the destructive button is gone — the server would
    // refuse it, so offering it again would be chrome that cannot work.
    expect(
      screen.queryByTestId("parts-folder-delete-confirm"),
    ).not.toBeInTheDocument();
  });
});

describe("what the drawer shows", () => {
  it("shows the UNFILED documents at the root, not the whole drawer", () => {
    renderRegister(
      [
        doc({ id: "d1", name: "Loose", folder_id: null }),
        doc({ id: "d2", name: "Filed", folder_id: "f1" }),
      ],
      filing({ folders: [folder({ document_count: 1 })] }),
    );
    expect(
      screen.getAllByTestId("part-open").map((n) => n.textContent),
    ).toEqual(["Loose"]);
    // ...and the count is a FRACTION, because the view is a subset. A plain
    // "1 part" would have meant something different from the same string on an
    // unfoldered drawer.
    expect(screen.getByTestId("parts-count")).toHaveTextContent("1 of 2 parts");
  });

  it("filters the WHOLE drawer and says where each hit lives", () => {
    renderRegister(
      [
        doc({ id: "d1", name: "Loose bracket", folder_id: null }),
        doc({ id: "d2", name: "Filed bracket", folder_id: "f1" }),
      ],
      filing({ folders: [folder({ id: "f1", name: "Gearbox" })] }),
    );
    fireEvent.change(screen.getByTestId("parts-filter"), {
      target: { value: "bracket" },
    });

    // Both, including the one filed in a folder we are NOT standing in — the
    // reachability guarantee.
    expect(screen.getAllByTestId("part-open")).toHaveLength(2);
    expect(
      screen.getAllByTestId("part-location").map((n) => n.textContent),
    ).toEqual(["Unfiled", "Gearbox"]);
    // The drawer goes FLAT while filtering — a filter is a way of looking.
    expect(screen.queryByTestId("parts-folder-row")).not.toBeInTheDocument();
  });

  it("states an empty folder rather than looking like a lost drawer", () => {
    renderRegister(
      [doc({ id: "d1", name: "Loose", folder_id: null })],
      filing({ folders: [folder({ id: "f1", name: "Gearbox" })] }),
    );
    fireEvent.click(screen.getByTestId("parts-folder-open"));
    expect(screen.getByTestId("parts-nothing-here")).toHaveTextContent(
      "Nothing is filed in Gearbox yet.",
    );
  });
});

describe("filing a document", () => {
  it("moves it to the folder chosen, and reports nothing until the server does", async () => {
    const onMoveDocument = vi.fn().mockResolvedValue(undefined);
    renderRegister(
      [doc({ id: "d1", name: "Bracket", folder_id: null })],
      filing({
        folders: [folder({ id: "f1", name: "Gearbox" })],
        onMoveDocument,
      }),
    );

    fireEvent.click(screen.getByTestId("part-move"));
    const select = screen.getByTestId("part-move-folder");
    // Unfiled is a real, first-class destination in the picker.
    expect(
      Array.from(select.querySelectorAll("option")).map((o) => o.textContent),
    ).toEqual(["Unfiled", "Gearbox"]);
    // Save is inert until the destination actually changes.
    expect(screen.getByTestId("part-move-save")).toBeDisabled();

    fireEvent.change(select, { target: { value: "f1" } });
    fireEvent.click(screen.getByTestId("part-move-save"));
    await waitFor(() =>
      expect(onMoveDocument).toHaveBeenCalledWith(
        expect.objectContaining({ id: "d1" }),
        "f1",
      ),
    );
    // The row did NOT paint the destination itself: the register still renders
    // the document it was given, and a refetch is what moves it.
    expect(screen.getByTestId("part-open")).toHaveTextContent("Bracket");
  });

  it("files a new document into the folder being viewed, in one call", async () => {
    const onCreate = vi.fn().mockResolvedValue(undefined);
    renderRegister(
      [],
      filing({ folders: [folder({ id: "f1", name: "Gearbox" })] }),
      onCreate,
    );
    fireEvent.click(screen.getByTestId("parts-folder-open"));
    fireEvent.change(screen.getByTestId("create-part-name"), {
      target: { value: "Housing" },
    });
    fireEvent.submit(screen.getByTestId("create-part-form"));
    await waitFor(() => expect(onCreate).toHaveBeenCalledWith("Housing", "f1"));
  });

  it("files a new FOLDER inside the folder being viewed", async () => {
    const onCreateFolder = vi.fn().mockResolvedValue(undefined);
    renderRegister(
      [doc()],
      filing({
        folders: [folder({ id: "f1", name: "Gearbox" })],
        onCreateFolder,
      }),
    );
    fireEvent.click(screen.getByTestId("parts-folder-open"));
    fireEvent.click(screen.getByTestId("parts-new-folder"));
    fireEvent.change(screen.getByTestId("create-part-folder-name"), {
      target: { value: "Housings" },
    });
    fireEvent.submit(screen.getByTestId("create-part-folder-form"));
    await waitFor(() =>
      expect(onCreateFolder).toHaveBeenCalledWith("Housings", "f1"),
    );
  });
});

describe("a drawer with no filing at all", () => {
  it("draws no dividers, no breadcrumb steps and no MOVE verb", () => {
    render(
      <DocumentRegister
        idPlural="parts"
        idSingular="part"
        copy={COPY}
        documents={[doc()]}
        isLoading={false}
        isError={false}
        error={null}
        openLink={(entry, props) => <a {...props}>{entry.name}</a>}
        onCreate={vi.fn().mockResolvedValue(undefined)}
        onRename={vi.fn().mockResolvedValue(undefined)}
        onDuplicate={vi.fn().mockResolvedValue(undefined)}
        onDelete={vi.fn().mockResolvedValue(undefined)}
      />,
    );
    expect(screen.queryByTestId("parts-folder-row")).not.toBeInTheDocument();
    expect(screen.queryByTestId("part-move")).not.toBeInTheDocument();
    expect(screen.queryByTestId("parts-new-folder")).not.toBeInTheDocument();
    // ...and the count is the plain tally it has always been.
    expect(screen.getByTestId("parts-count")).toHaveTextContent("1 part");
  });
});
