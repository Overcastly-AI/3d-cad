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

import { DocumentHasDependentsError } from "../api/parts";
import { DocumentRegister, type RegisterCopy } from "./DocumentRegister";

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

interface Doc {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  length_unit?: "mm" | "in";
  eval_state?: "never" | "ok" | "failed" | "stale";
  eval_scope?: "whole" | "rolled_back" | null;
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

/**
 * Unstarted: both stamps from the same INSERT, microseconds apart. Filed AFTER
 * `worked`, because the register's default order is FILED ascending — the same
 * order documents lists in — so a fixture out of that order would be testing a
 * list the server could never have sent.
 */
const unstartedFiled = new Date(Date.now() - 86_400_000);
const unstarted: Doc = {
  id: "b",
  name: "Empty stock",
  created_at: unstartedFiled.toISOString(),
  updated_at: new Date(unstartedFiled.getTime() + 4).toISOString(),
  length_unit: "in",
};

function renderRegister(
  documents: Doc[],
  extra: Partial<Parameters<typeof DocumentRegister<Doc>>[0]> = {},
) {
  const onCreate = vi.fn(() => Promise.resolve());
  const onDelete = vi.fn(() => Promise.resolve());
  const onRename = vi.fn(() => Promise.resolve());
  const onDuplicate = vi.fn(() => Promise.resolve());
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
      onRename={onRename}
      onDuplicate={onDuplicate}
      onDelete={onDelete}
      {...extra}
    />,
  );
  return { ...view, onCreate, onDelete, onRename, onDuplicate };
}

/**
 * Reach a row verb. Since REGISTER-1 the four verbs live in the row's overflow
 * menu (`part-actions`) instead of being printed on every row, so a test that
 * drives one opens the menu first — the ids are unchanged, only the address is.
 */
function rowVerb(testid: string, row?: HTMLElement) {
  const scope = row ?? screen.getAllByTestId("part-row")[0]!;
  fireEvent.click(within(scope).getByTestId("part-actions"));
  return screen.getByTestId(testid);
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

  it("numbers rows by position, and says so rather than implying an identity", () => {
    renderRegister([worked, unstarted]);
    const rows = screen.getAllByTestId("part-row");
    expect(within(rows[0]!).getByTestId("part-ordinal")).toHaveTextContent("1");
    expect(within(rows[1]!).getByTestId("part-ordinal")).toHaveTextContent("2");
    // The create control IS the next line of the register.
    expect(screen.getByText("3")).toBeInTheDocument();
    // No zero padding, because `001` is what made a row position read as a
    // filing identity that a user could cite (UI-REVIEW 2026-07-30 P2)…
    expect(screen.queryByText("001")).toBeNull();
    // …and the header names it, for the eye and for a screen reader.
    const header = screen.getByTestId("parts-ordinal-header");
    expect(header).toHaveTextContent("#");
    expect(header).toHaveTextContent("Row");
  });

  it("re-numbers on delete — which is why it never claims to be an identity", () => {
    const { rerender } = renderRegister([worked, unstarted]);
    expect(
      within(screen.getAllByTestId("part-row")[1]!).getByTestId("part-ordinal"),
    ).toHaveTextContent("2");
    // The same document is row 1 once the row above it is gone. A stable
    // "sheet number" would have to come from the document row in the database.
    rerender(
      <DocumentRegister<Doc>
        idPlural="parts"
        idSingular="part"
        copy={COPY}
        documents={[unstarted]}
        isLoading={false}
        isError={false}
        error={null}
        openLink={(entry, props) => (
          <a href={`/parts/${entry.id}`} {...props}>
            {entry.name}
          </a>
        )}
        onCreate={() => Promise.resolve()}
        onRename={() => Promise.resolve()}
        onDuplicate={() => Promise.resolve()}
        onDelete={() => Promise.resolve()}
      />,
    );
    const row = screen.getAllByTestId("part-row")[0]!;
    expect(within(row).getByTestId("part-ordinal")).toHaveTextContent("1");
    expect(within(row).getByTestId("part-open")).toHaveTextContent(
      "Empty stock",
    );
  });

  it("shows the document unit per row when the drawer disagrees about it", () => {
    // Two units in the drawer: the column earns its width back, because now it
    // discriminates rows instead of repeating one word (REGISTER-1).
    const { unmount } = renderRegister([worked, unstarted]);
    expect(screen.getByText("Units")).toBeInTheDocument();
    expect(screen.getByText("mm")).toBeInTheDocument();
    expect(screen.getByText("in")).toBeInTheDocument();
    expect(screen.queryByTestId("parts-drawer-units")).toBeNull();
    unmount();
  });

  it("states ONE unit once on the header rule instead of down a column", () => {
    // The measured defect (UI-REVIEW P1-2): a 72 px column reading
    // `mm, mm, mm, mm` — 8 % of the table's width carrying a constant. The fact
    // is kept, at drawer level, where it is true.
    const { unmount } = renderRegister([
      worked,
      { ...unstarted, id: "c", length_unit: "mm" },
    ]);
    expect(screen.queryByText("Units")).toBeNull();
    const readout = screen.getByTestId("parts-drawer-units");
    expect(readout).toHaveTextContent("mm");
    expect(readout.getAttribute("title")).toMatch(/dimensioned in mm/);
    unmount();
  });

  it("drops the column entirely for a kind that has no unit", () => {
    // Drawings carry no unit: no blank column rather than a column of dashes,
    // and no drawer-level readout either — there is nothing to state.
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
    expect(screen.queryByTestId("parts-drawer-units")).toBeNull();
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

  it("will not call a ROLLED-BACK prefix clean, and still calls a broken one broken", () => {
    // Audit J3b: the wire's two axes combine. `ok` over a prefix is not a
    // verdict on the part; `failed` over a prefix still is.
    renderRegister([
      {
        ...worked,
        id: "prefix-ok",
        eval_state: "ok",
        eval_scope: "rolled_back",
        last_eval_status: "ok",
      },
      {
        ...worked,
        id: "prefix-bad",
        eval_state: "failed",
        eval_scope: "rolled_back",
        last_eval_status: "failed",
      },
      {
        ...worked,
        id: "whole-ok",
        eval_state: "ok",
        eval_scope: "whole",
        last_eval_status: "ok",
      },
    ]);
    const cells = screen.getAllByTestId("part-health");

    // The bare all-clear word, alone, is the thing that must not appear.
    expect(cells[0]?.textContent).not.toBe("Clean");
    expect(cells[0]).toHaveTextContent("Clean to stop");
    expect(cells[0]).toHaveAttribute("data-health", "ok");
    expect(cells[0]).toHaveAttribute("data-health-scope", "rolled_back");
    expect(cells[0]).toHaveAttribute("data-stamp", "indeterminate");
    expect(cells[0]?.getAttribute("title")).toMatch(/travel stop/);

    expect(cells[1]).toHaveTextContent("Broken");
    expect(cells[1]).toHaveAttribute("data-stamp", "flag");

    // A stop parked on the LAST feature excludes nothing: hedging a part that
    // DID fully build is the mirror-image lie.
    expect(cells[2]).toHaveTextContent("Clean");
    expect(cells[2]).not.toHaveAttribute("data-stamp");
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

  /**
   * The REBUILD column obeying the rule UNITS already obeyed: "a column of one
   * repeated value is not a column". Measured on a real five-part drawer before
   * this landed, every cell in it read the same em dash — one of six headings
   * carrying nothing. Both directions are pinned, because the dangerous failure
   * is not the column staying: it is the column vanishing while the rows
   * actually DISAGREE, which would hide a broken part behind a clean drawer.
   */
  it("collapses REBUILD to a header readout when every document agrees", () => {
    renderRegister([
      { ...worked, eval_state: "never" },
      { ...unstarted, eval_state: "never" },
    ]);
    expect(screen.queryByText("Rebuild")).toBeNull();
    expect(screen.queryAllByTestId("part-health")).toHaveLength(0);
    const readout = screen.getByTestId("parts-drawer-health");
    expect(readout).toHaveTextContent("Not evaluated");
    expect(readout).toHaveAttribute("data-health", "never");
  });

  it("keeps the column the moment two documents disagree", () => {
    renderRegister([
      { ...worked, eval_state: "ok", last_eval_status: "ok" },
      { ...unstarted, eval_state: "failed", last_eval_status: "failed" },
    ]);
    expect(screen.getByText("Rebuild")).toBeInTheDocument();
    expect(screen.queryAllByTestId("part-health")).toHaveLength(2);
    expect(screen.queryByTestId("parts-drawer-health")).toBeNull();
  });

  it("keeps the column for a drawer of ONE — a single row repeats nothing", () => {
    renderRegister([{ ...worked, eval_state: "never" }]);
    expect(screen.getByTestId("part-health")).toBeInTheDocument();
    expect(screen.queryByTestId("parts-drawer-health")).toBeNull();
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

describe("DocumentRegister — the name is the column that identifies (REGISTER-1)", () => {
  const long = {
    ...worked,
    id: "long",
    name: "Motor mount adapter plate rev C",
  };

  it("keeps a clipped name readable: ellipsis in a block box, full name on title", () => {
    // The measured defect: `<td class="truncate">` around an `inline-flex`
    // anchor computed `text-overflow: clip` and `title: null`, so
    // "…adapter plate rev C" rendered as "Motor mount adapter plat" with no cue
    // and no way to recover the rest (UI-REVIEW P1-2).
    renderRegister([long]);
    const link = screen.getByTestId("part-open");
    expect(link).toHaveAttribute("title", "Motor mount adapter plate rev C");
    expect(link.className).toContain("truncate");
    expect(link.className).toContain("block");
    expect(link.className).not.toContain("inline-flex");
  });

  it("spends its fixed width on data, not on repeating the same four verbs", () => {
    renderRegister([long]);
    // NAME's header carries no width class at all — it takes what the fixed
    // columns leave, which is the whole point of the budget. The verbs' column
    // is the gutter's width, holding one mark.
    const nameHeader = screen.getByTestId("parts-sort-name-header");
    expect(nameHeader.className).not.toMatch(/\bw-\[/);
    const row = screen.getByTestId("part-row");
    const actionCell = within(row).getByTestId("part-actions").closest("td")!;
    const headers = row.closest("table")!.querySelectorAll("thead th");
    const actionHeader = headers[headers.length - 1]!;
    expect(actionHeader.className).toContain("w-[3.5rem]");
    // …and one tab stop per row instead of four.
    expect(within(actionCell).getAllByRole("button")).toHaveLength(1);
  });

  it("gives the mark an accessible name that says which row it acts on", () => {
    renderRegister([long, { ...worked, id: "other", name: "Rib" }]);
    expect(
      screen.getByLabelText("Actions for Motor mount adapter plate rev C"),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Actions for Rib")).toBeInTheDocument();
  });

  it("still refuses to delete on one click, now from inside the menu", async () => {
    const { onDelete } = renderRegister([long]);
    fireEvent.click(rowVerb("part-delete"));
    expect(onDelete).not.toHaveBeenCalled();
    // The menu closed behind the verb; the row is the confirmation.
    expect(screen.queryByRole("menu")).toBeNull();
    fireEvent.click(screen.getByTestId("part-delete-confirm"));
    await waitFor(() => expect(onDelete).toHaveBeenCalledWith(long));
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
    fireEvent.click(rowVerb("part-delete"));
    expect(onDelete).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("part-delete-confirm"));
    await waitFor(() => expect(onDelete).toHaveBeenCalledWith(worked));
  });

  it("backs out of the confirm without deleting", () => {
    const { onDelete } = renderRegister([worked]);
    fireEvent.click(rowVerb("part-delete"));
    fireEvent.click(screen.getByTestId("part-delete-cancel"));
    expect(onDelete).not.toHaveBeenCalled();
    expect(screen.getByTestId("part-actions")).toBeInTheDocument();
  });

  it("pins a failed delete beside the confirm instead of losing it", async () => {
    renderRegister([worked], {
      onDelete: () => Promise.reject(new Error("part is referenced")),
    });
    fireEvent.click(rowVerb("part-delete"));
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
    // The folder the register is standing in rides the create (#WS2); at the
    // root — where this test stands — that is null.
    await waitFor(() =>
      expect(onCreate).toHaveBeenCalledWith("Motor mount", null),
    );
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

describe("DocumentRegister — search and count", () => {
  it("filters by name substring as you type, case-insensitively", () => {
    renderRegister([worked, unstarted]);
    fireEvent.change(screen.getByTestId("parts-filter"), {
      target: { value: "brack" },
    });
    const rows = screen.getAllByTestId("part-row");
    expect(rows).toHaveLength(1);
    expect(within(rows[0]!).getByTestId("part-open")).toHaveTextContent(
      "Bracket plate",
    );
  });

  it("says how many of how many, so a narrowed drawer is not data loss", () => {
    renderRegister([worked, unstarted]);
    expect(screen.getByTestId("parts-count")).toHaveTextContent("2 parts");
    fireEvent.change(screen.getByTestId("parts-filter"), {
      target: { value: "brack" },
    });
    // The fraction is derived from the two arrays this render drew from, so it
    // cannot disagree with the rows on screen.
    expect(screen.getByTestId("parts-count")).toHaveTextContent("1 of 2 parts");
  });

  it("makes an empty result legible, quotes what was searched, and offers the way out", () => {
    renderRegister([worked, unstarted]);
    fireEvent.change(screen.getByTestId("parts-filter"), {
      target: { value: "zzz" },
    });
    expect(screen.queryByTestId("part-row")).toBeNull();
    expect(screen.getByTestId("parts-count")).toHaveTextContent("0 of 2 parts");
    const empty = screen.getByTestId("parts-no-matches");
    expect(empty).toHaveTextContent("No parts match");
    expect(empty).toHaveTextContent("zzz");

    fireEvent.click(screen.getByTestId("parts-no-matches-clear"));
    expect(screen.getAllByTestId("part-row")).toHaveLength(2);
    expect(screen.getByTestId("parts-count")).toHaveTextContent("2 parts");
  });

  it("offers a clear only while there is something to clear", () => {
    renderRegister([worked, unstarted]);
    // A control with no job is chrome: the chip teaching `/` holds the seat
    // until the field has a value.
    expect(screen.queryByTestId("parts-filter-clear")).toBeNull();
    fireEvent.change(screen.getByTestId("parts-filter"), {
      target: { value: "brack" },
    });
    fireEvent.click(screen.getByTestId("parts-filter-clear"));
    expect(screen.getAllByTestId("part-row")).toHaveLength(2);
  });

  it("focuses the filter from anywhere with / and clears it with Escape", () => {
    renderRegister([worked, unstarted]);
    const field = screen.getByTestId("parts-filter");
    expect(field).not.toHaveFocus();
    fireEvent.keyDown(window, { key: "/" });
    expect(field).toHaveFocus();

    fireEvent.change(field, { target: { value: "brack" } });
    expect(screen.getAllByTestId("part-row")).toHaveLength(1);
    fireEvent.keyDown(field, { key: "Escape" });
    expect(screen.getAllByTestId("part-row")).toHaveLength(2);
  });
});

describe("DocumentRegister — sort", () => {
  const a: Doc = {
    id: "1",
    name: "Rib 10",
    created_at: "2026-07-01T09:00:00.000Z",
    updated_at: "2026-07-20T09:00:00.000Z",
  };
  const b: Doc = {
    id: "2",
    name: "Rib 2",
    created_at: "2026-07-02T09:00:00.000Z",
    updated_at: "2026-07-10T09:00:00.000Z",
  };

  const names = () =>
    screen.getAllByTestId("part-open").map((node) => node.textContent);

  it("defaults to what you touched LAST, and says which column that is", () => {
    // REGISTER-2. `a` was created FIRST and worked LAST; the old default (filed
    // ascending, the server's own order) put it first for the wrong reason, so
    // this fixture only distinguishes the two rules through `b`, which is newer
    // on disk and older in the hands.
    renderRegister([b, a]);
    expect(names()).toEqual(["Rib 10", "Rib 2"]);
    expect(screen.getByTestId("parts-sort-activity-header")).toHaveAttribute(
      "aria-sort",
      "descending",
    );
    expect(screen.getByTestId("parts-sort-filed-header")).toHaveAttribute(
      "aria-sort",
      "none",
    );
    expect(screen.getByTestId("parts-sort-name-header")).toHaveAttribute(
      "aria-sort",
      "none",
    );
  });

  it("keeps FILED reachable — the order it replaced is one click away", () => {
    renderRegister([b, a]);
    fireEvent.click(screen.getByTestId("parts-sort-filed"));
    expect(names()).toEqual(["Rib 10", "Rib 2"]);
    expect(screen.getByTestId("parts-sort-filed-header")).toHaveAttribute(
      "aria-sort",
      "ascending",
    );
  });

  it("sorts names the way a numbered part drawer reads, not lexically", () => {
    renderRegister([a, b]);
    fireEvent.click(screen.getByTestId("parts-sort-name"));
    // Lexical order would put "Rib 10" first; a numeric collator does not.
    expect(names()).toEqual(["Rib 2", "Rib 10"]);
  });

  it("reverses on a second click of the active column", () => {
    renderRegister([a, b]);
    fireEvent.click(screen.getByTestId("parts-sort-name"));
    fireEvent.click(screen.getByTestId("parts-sort-name"));
    expect(names()).toEqual(["Rib 10", "Rib 2"]);
    expect(screen.getByTestId("parts-sort-name-header")).toHaveAttribute(
      "aria-sort",
      "descending",
    );
  });

  it("sorts by last worked, which is a different order from filed", () => {
    renderRegister([a, b]);
    fireEvent.click(screen.getByTestId("parts-sort-activity"));
    expect(names()).toEqual(["Rib 2", "Rib 10"]);
    fireEvent.click(screen.getByTestId("parts-sort-activity"));
    expect(names()).toEqual(["Rib 10", "Rib 2"]);
  });

  it("renumbers the gutter when the order changes — it is a position, not an id", () => {
    renderRegister([a, b]);
    fireEvent.click(screen.getByTestId("parts-sort-name"));
    const rows = screen.getAllByTestId("part-row");
    expect(within(rows[0]!).getByTestId("part-open")).toHaveTextContent(
      "Rib 2",
    );
    expect(within(rows[0]!).getByTestId("part-ordinal")).toHaveTextContent("1");
  });
});

describe("DocumentRegister — rename", () => {
  it("opens with the current name selected and commits it on submit", async () => {
    const { onRename } = renderRegister([worked]);
    fireEvent.click(rowVerb("part-rename"));
    const field = screen.getByTestId("part-rename-name");
    expect(field).toHaveValue("Bracket plate");
    expect(field).toHaveFocus();

    fireEvent.change(field, { target: { value: "  Bracket plate v2  " } });
    fireEvent.submit(screen.getByTestId("part-rename-form"));
    await waitFor(() =>
      expect(onRename).toHaveBeenCalledWith(worked, "Bracket plate v2"),
    );
  });

  it("does not spend a write when the name did not change", () => {
    const { onRename } = renderRegister([worked]);
    fireEvent.click(rowVerb("part-rename"));
    fireEvent.submit(screen.getByTestId("part-rename-form"));
    expect(onRename).not.toHaveBeenCalled();
    expect(screen.getByTestId("part-actions")).toBeInTheDocument();
  });

  it("reverts on Escape without writing", () => {
    const { onRename } = renderRegister([worked]);
    fireEvent.click(rowVerb("part-rename"));
    fireEvent.change(screen.getByTestId("part-rename-name"), {
      target: { value: "Something else" },
    });
    fireEvent.keyDown(screen.getByTestId("part-rename-name"), {
      key: "Escape",
    });
    expect(onRename).not.toHaveBeenCalled();
    expect(screen.getByTestId("part-open")).toHaveTextContent("Bracket plate");
  });

  it("keeps the typed name in the field when the server refuses it", async () => {
    renderRegister([worked], {
      onRename: () =>
        Promise.reject(new Error('A part named "Rib" already exists.')),
    });
    fireEvent.click(rowVerb("part-rename"));
    fireEvent.change(screen.getByTestId("part-rename-name"), {
      target: { value: "Rib" },
    });
    fireEvent.submit(screen.getByTestId("part-rename-form"));
    expect(await screen.findByText(/already exists/)).toBeInTheDocument();
    // Still editing, still holding what was typed — nothing to retype.
    expect(screen.getByTestId("part-rename-name")).toHaveValue("Rib");
  });

  it("never paints the typed name into the row itself", async () => {
    // The row renders the LIST payload. A rename that repainted the cell would
    // show a name the server may have refused (audit class: the surface
    // asserting something it does not know).
    let resolve = () => {};
    renderRegister([worked], {
      onRename: () => new Promise<void>((r) => (resolve = r)),
    });
    fireEvent.click(rowVerb("part-rename"));
    fireEvent.change(screen.getByTestId("part-rename-name"), {
      target: { value: "Renamed" },
    });
    fireEvent.submit(screen.getByTestId("part-rename-form"));
    resolve();
    await waitFor(() =>
      expect(screen.getByTestId("part-open")).toHaveTextContent(
        "Bracket plate",
      ),
    );
  });
});

describe("DocumentRegister — duplicate", () => {
  it("asks the server for a copy without naming it", async () => {
    const { onDuplicate } = renderRegister([worked]);
    fireEvent.click(rowVerb("part-duplicate"));
    await waitFor(() => expect(onDuplicate).toHaveBeenCalledWith(worked));
    // One argument: the document. The register has no say in the copy's name.
    expect(onDuplicate.mock.calls[0]).toHaveLength(1);
  });

  it("surfaces a failed duplicate on the row rather than swallowing it", async () => {
    renderRegister([worked], {
      onDuplicate: () => Promise.reject(new Error("upstream unavailable")),
    });
    fireEvent.click(rowVerb("part-duplicate"));
    const error = await screen.findByTestId("part-action-error");
    expect(error).toHaveTextContent("upstream unavailable");
    expect(error).toHaveAttribute("role", "alert");
  });
});

describe("DocumentRegister — delete with dependents", () => {
  it("names the documents holding the reference instead of summarising them", async () => {
    renderRegister([worked], {
      onDelete: () =>
        Promise.reject(
          new DocumentHasDependentsError(
            [
              { id: "asm-1", name: "gearbox", kind: "assembly" },
              { id: "dwg-1", name: "bracket-detail", kind: "drawing" },
            ],
            "Document is referenced by 2 document(s).",
          ),
        ),
    });
    fireEvent.click(rowVerb("part-delete"));
    fireEvent.click(screen.getByTestId("part-delete-confirm"));

    const blocked = await screen.findByTestId("part-blocked");
    expect(blocked).toHaveAttribute("role", "alert");
    const named = within(blocked).getAllByTestId("part-dependent");
    expect(named.map((node) => node.textContent)).toEqual([
      "gearbox",
      "bracket-detail",
    ]);
    expect(named[0]).toHaveAttribute("data-dependent-kind", "assembly");
    expect(named[1]).toHaveAttribute("data-dependent-kind", "drawing");
    // ...and the delete button is gone: there is nothing to retry until the
    // references are removed, so offering it again would be theatre.
    expect(screen.queryByTestId("part-delete-confirm")).toBeNull();
  });
});
