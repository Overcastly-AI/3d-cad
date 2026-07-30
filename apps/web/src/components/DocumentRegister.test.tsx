/**
 * DocumentRegister — the one register behind all three document homes.
 *
 * What can actually regress here is not the CSS: it is whether the surface
 * still ANSWERS. The register's whole claim (UI-REVIEW 2026-07-24 P2) is that
 * it reports recency, flags the named-but-never-started stub, and shows a unit
 * only where a unit exists. Those are render-time decisions over the list
 * payload, invisible to a pure test and expensive to reach in a browser — and
 * the same three configs also have to keep every `data-testid` the e2e suite
 * drives, which a jsdom render checks cheaply.
 */
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DocumentRegister, type RegisterCopy } from "./DocumentRegister";

const COPY: RegisterCopy = {
  title: "Parts register",
  caption: "Your parts, oldest first.",
  noun: "part",
  nounPlural: "parts",
  loading: "Loading parts…",
  loadError: "Your parts could not be loaded.",
  deleteError: "The part could not be deleted.",
  createError: "The part could not be created.",
  emptyHeadline: "Nothing filed here yet.",
  emptyBody: "Name your first part.",
  fieldLabel: "Part name",
  placeholder: "e.g. Bracket plate",
  createLabel: "New part",
  createFirstLabel: "Create first part",
};

interface Doc {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  length_unit?: "mm" | "in";
  eval_state?: "never" | "ok" | "failed" | "stale";
  last_eval_status?: "ok" | "failed" | null;
  last_eval_at?: string | null;
}

/** Worked: the edit is a day after creation, so it is unambiguously an edit. */
const worked: Doc = {
  id: "a",
  name: "Bracket plate",
  created_at: new Date(Date.now() - 3 * 86_400_000).toISOString(),
  updated_at: new Date(Date.now() - 20 * 60_000).toISOString(),
  length_unit: "mm",
};

/** Unstarted: both stamps from the same INSERT, microseconds apart. */
const unstarted: Doc = {
  id: "b",
  name: "Empty stock",
  created_at: "2026-07-25T09:00:00.000Z",
  updated_at: "2026-07-25T09:00:00.004Z",
  length_unit: "in",
};

function renderRegister(
  documents: Doc[],
  extra: Partial<Parameters<typeof DocumentRegister<Doc>>[0]> = {},
) {
  const onCreate = vi.fn(() => Promise.resolve());
  const onDelete = vi.fn(() => Promise.resolve());
  const view = render(
    <DocumentRegister<Doc>
      idPlural="parts"
      idSingular="part"
      copy={COPY}
      documents={documents}
      isLoading={false}
      isError={false}
      error={null}
      openLink={(entry, props) => (
        <a href={`/parts/${entry.id}`} {...props}>
          {entry.name}
        </a>
      )}
      onCreate={onCreate}
      onDelete={onDelete}
      {...extra}
    />,
  );
  return { ...view, onCreate, onDelete };
}

describe("DocumentRegister — what it reports", () => {
  it("reads recency for a worked document and flags an unstarted one", () => {
    renderRegister([worked, unstarted]);
    const rows = screen.getAllByTestId("part-row");
    expect(within(rows[0]!).getByText("20 min ago")).toBeInTheDocument();
    expect(within(rows[0]!).queryByTestId("part-unstarted")).toBeNull();
    // The stub is named as an exception, not badged alongside every row.
    expect(within(rows[1]!).getByTestId("part-unstarted")).toHaveTextContent(
      "Not started",
    );
    expect(within(rows[1]!).queryByText(/ago/)).toBeNull();
  });

  it("files each row under a stable sheet number and scribes the next one", () => {
    renderRegister([worked, unstarted]);
    const rows = screen.getAllByTestId("part-row");
    expect(within(rows[0]!).getByText("001")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("002")).toBeInTheDocument();
    // The create control IS the next line of the register.
    expect(screen.getByText("003")).toBeInTheDocument();
  });

  it("shows the document unit, and drops the column when there is none", () => {
    const { unmount } = renderRegister([worked, unstarted]);
    expect(screen.getByText("mm")).toBeInTheDocument();
    expect(screen.getByText("in")).toBeInTheDocument();
    unmount();

    // Drawings carry no unit: no blank column rather than a column of dashes.
    renderRegister([
      {
        id: "d",
        name: "Sheet 1",
        created_at: worked.created_at,
        updated_at: worked.updated_at,
      },
    ]);
    expect(screen.queryByText("Units")).toBeNull();
    expect(screen.queryByText("—")).toBeNull();
  });

  it("reports the server's rebuild verdict, one state per row", () => {
    renderRegister([
      { ...worked, id: "ok", eval_state: "ok", last_eval_status: "ok" },
      {
        ...worked,
        id: "bad",
        eval_state: "failed",
        last_eval_status: "failed",
      },
      {
        ...worked,
        id: "stale-ok",
        eval_state: "stale",
        last_eval_status: "ok",
      },
      {
        ...worked,
        id: "stale-bad",
        eval_state: "stale",
        last_eval_status: "failed",
      },
      { ...worked, id: "none", eval_state: "never", last_eval_status: null },
    ]);
    const cells = screen.getAllByTestId("part-health");
    expect(cells[0]).toHaveTextContent("Clean");
    expect(cells[1]).toHaveTextContent("Broken");
    expect(cells[2]).toHaveTextContent("Was clean");
    expect(cells[3]).toHaveTextContent("Was broken");
    expect(cells[4]).toHaveTextContent("Not evaluated");

    // A STALE row is indeterminate — the dashed phantom stamp, never the flag,
    // even when the record it is reporting says "failed".
    expect(cells[3]).toHaveAttribute("data-stamp", "indeterminate");
    expect(cells[1]).toHaveAttribute("data-stamp", "flag");

    // "ok" is not "this part is modelled", and the cell says so where a user
    // can find it rather than letting the word imply a body.
    expect(cells[0]?.getAttribute("title")).toMatch(
      /not a claim that it has a body/,
    );
    expect(cells[3]?.getAttribute("title")).toMatch(
      /tree changed after the last rebuild/,
    );
  });

  it("reads the verdict field and never re-derives it from the timestamps", () => {
    // `updated_at` is 20 min old while the record is 3 days old: a client that
    // compared stamps would call this stale. The SERVER already folded the tree
    // versions and said `ok`, and that is what the register reports — the whole
    // reason `eval_state` is derived server-side (py-kit `derive_part_eval_state`).
    renderRegister([
      {
        ...worked,
        eval_state: "ok",
        last_eval_status: "ok",
        last_eval_at: new Date(Date.now() - 3 * 86_400_000).toISOString(),
      },
    ]);
    expect(screen.getByTestId("part-health")).toHaveTextContent("Clean");
  });

  it("drops the column for document kinds that have no feature tree", () => {
    renderRegister([
      {
        id: "d",
        name: "Sheet 1",
        created_at: worked.created_at,
        updated_at: worked.updated_at,
      },
    ]);
    expect(screen.queryByText("Rebuild")).toBeNull();
    expect(screen.queryByTestId("part-health")).toBeNull();
  });

  it("keeps LAST WORKED meaning 'someone worked on it' after a rebuild is recorded", () => {
    // The backend deliberately does not bump `updated_at` when it records an
    // evaluation, so an untouched part that was evaluated is still NOT STARTED.
    renderRegister([
      {
        ...unstarted,
        eval_state: "ok",
        last_eval_status: "ok",
        last_eval_at: new Date().toISOString(),
      },
    ]);
    expect(screen.getByTestId("part-unstarted")).toBeInTheDocument();
    expect(screen.getByTestId("part-health")).toHaveTextContent("Clean");
  });

  it("counts in the document's own noun", () => {
    const { unmount } = renderRegister([worked]);
    expect(screen.getByTestId("parts-count")).toHaveTextContent("1 part");
    unmount();
    renderRegister([worked, unstarted]);
    expect(screen.getByTestId("parts-count")).toHaveTextContent("2 parts");
  });
});

describe("DocumentRegister — states", () => {
  it("announces a failed list as an alert, with no count beside it", () => {
    renderRegister([], {
      isError: true,
      error: new Error("gateway unreachable"),
    });
    expect(screen.getByTestId("parts-error")).toHaveAttribute("role", "alert");
    expect(screen.getByTestId("parts-error")).toHaveTextContent(
      "gateway unreachable",
    );
    expect(screen.queryByTestId("parts-count")).toBeNull();
  });

  it("invites the first sheet when the drawer is empty", () => {
    renderRegister([]);
    expect(screen.getByTestId("parts-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("parts-table")).toBeNull();
    expect(screen.getByTestId("create-part-submit")).toHaveTextContent(
      "Create first part",
    );
  });

  it("reports loading with a status role", () => {
    renderRegister([], { isLoading: true });
    expect(screen.getByTestId("parts-loading")).toHaveAttribute(
      "role",
      "status",
    );
  });
});

describe("DocumentRegister — actions", () => {
  it("never deletes on one click, and passes the row through on confirm", async () => {
    const { onDelete } = renderRegister([worked]);
    fireEvent.click(screen.getByTestId("part-delete"));
    expect(onDelete).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("part-delete-confirm"));
    await waitFor(() => expect(onDelete).toHaveBeenCalledWith(worked));
  });

  it("backs out of the confirm without deleting", () => {
    const { onDelete } = renderRegister([worked]);
    fireEvent.click(screen.getByTestId("part-delete"));
    fireEvent.click(screen.getByTestId("part-delete-cancel"));
    expect(onDelete).not.toHaveBeenCalled();
    expect(screen.getByTestId("part-delete")).toBeInTheDocument();
  });

  it("pins a failed delete beside the confirm instead of losing it", async () => {
    renderRegister([worked], {
      onDelete: () => Promise.reject(new Error("part is referenced")),
    });
    fireEvent.click(screen.getByTestId("part-delete"));
    fireEvent.click(screen.getByTestId("part-delete-confirm"));
    const error = await screen.findByTestId("part-delete-error");
    expect(error).toHaveTextContent("part is referenced");
    expect(error).toHaveAttribute("role", "alert");
  });

  it("files a trimmed name and clears the line", async () => {
    const { onCreate } = renderRegister([worked]);
    const field = screen.getByTestId("create-part-name");
    fireEvent.change(field, { target: { value: "  Motor mount  " } });
    fireEvent.submit(screen.getByTestId("create-part-form"));
    await waitFor(() => expect(onCreate).toHaveBeenCalledWith("Motor mount"));
    await waitFor(() => expect(field).toHaveValue(""));
  });

  it("pins a rejected name on the field — the server's own words", async () => {
    renderRegister([worked], {
      onCreate: () =>
        Promise.reject(new Error("A part named Bracket plate already exists.")),
    });
    fireEvent.change(screen.getByTestId("create-part-name"), {
      target: { value: "Bracket plate" },
    });
    fireEvent.submit(screen.getByTestId("create-part-form"));
    expect(await screen.findByText(/already exists/)).toBeInTheDocument();
  });

  it("focuses the scribe line from anywhere on the page with N", () => {
    renderRegister([worked]);
    const field = screen.getByTestId("create-part-name");
    expect(field).not.toHaveFocus();
    fireEvent.keyDown(window, { key: "n" });
    expect(field).toHaveFocus();
  });
});
