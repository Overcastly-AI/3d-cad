/**
 * PRICE BOOK (CUT-LIST-PRICES): what you pay for lumber, the list the cut list
 * prices itself from (RESEARCH §27). Chief Architect's Master List and
 * SolidWorks' Cost property, reduced to the one table a deck builder keeps: a
 * material and a profile, priced Each at a stock length, per linear foot or
 * per board foot.
 *
 * The book is saved whole (`PUT` replaces it), so the dialog edits a draft and
 * Save sends every row; Cancel or Escape drops the draft. Opened from a blank
 * price in the cut list it adds a row pre-filled with that line's material,
 * profile and stock length, its price field focused, so pricing a line is
 * typing a number and pressing Enter. A save refetches every cut list, so the
 * panel re-prices without a reload.
 *
 * Prices are typed as decimals and parsed to integer cents on the digits
 * (`lib/money`); nothing here does float arithmetic on money.
 */
import { Button, Kbd, SelectField, TextField } from "@loft/design";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import type { MaterialKey } from "../api/materials";
import { fetchMaterialLibrary } from "../api/materials";
import {
  fetchPriceBook,
  type LumberProfileKey,
  PRICE_UNIT_LABEL,
  type PriceBook,
  type PriceBookEntry,
  type PriceUnit,
  savePriceBook,
  STOCK_LENGTHS_FT,
} from "../api/priceBook";
import { useModalLayer } from "../lib/modalGate";
import { centsToDecimal, parseMoney } from "../lib/money";
import { containFocus } from "./dialogKeys";

/** The line a blank price was clicked on: what the new row starts as. */
export interface PriceBookSeed {
  material: MaterialKey;
  /** The profile as the cut list names it ("2x10", "5/4x6"). */
  profile: string;
  stockLengthFt: number;
}

export interface PriceBookDialogProps {
  /** Pre-fill a new row for this line; null opens the book as it is. */
  seed: PriceBookSeed | null;
  onClose: () => void;
}

interface DraftRow {
  id: number;
  material: MaterialKey;
  profile: LumberProfileKey;
  unit: PriceUnit;
  stockLengthFt: number;
  price: string;
}

const UNITS: PriceUnit[] = ["each", "linear_foot", "board_foot"];
const UNIT_OPTIONS = UNITS.map((unit) => ({
  value: unit,
  label: PRICE_UNIT_LABEL[unit],
}));
const STOCK_OPTIONS = STOCK_LENGTHS_FT.map((ft) => ({
  value: String(ft),
  label: `${ft} ft`,
}));
const DEFAULT_MATERIAL: MaterialKey = "southern_pine_pt";
const DEFAULT_PROFILE: LumberProfileKey = "us_2x4";
const DEFAULT_STOCK_FT = 8;

const HEAD =
  "py-1 pr-2 text-left font-display text-2xs font-normal uppercase tracking-[0.14em] text-gauge";

function rowKey(row: DraftRow): string {
  return [
    row.material,
    row.profile,
    row.unit,
    row.unit === "each" ? row.stockLengthFt : "",
  ].join("|");
}

/** Every row's problem, by row id; empty when the book can be saved. */
function validate(rows: DraftRow[]): Map<number, string> {
  const problems = new Map<number, string>();
  const seen = new Set<string>();
  for (const row of rows) {
    const cents = parseMoney(row.price);
    if (cents === null) {
      problems.set(
        row.id,
        row.price.trim() === ""
          ? "Enter a price."
          : "Enter a price in dollars, e.g. 19.98.",
      );
    } else if (cents > 10_000_000) {
      problems.set(row.id, "A price is at most $100,000.00.");
    }
    const key = rowKey(row);
    if (seen.has(key) && !problems.has(row.id)) {
      problems.set(
        row.id,
        "This material, profile and unit is already priced.",
      );
    }
    seen.add(key);
  }
  return problems;
}

/** Why a save was refused: the stored book is no longer the one drafted. */
export const BOOK_CHANGED =
  "The price book changed elsewhere (another tab or device) since you opened it. Reload it, then make your changes again.";

/** The same stored book: same save stamp and the same entries in order. */
function sameBook(a: PriceBook, b: PriceBook): boolean {
  return (
    (a.updated_at ?? null) === (b.updated_at ?? null) &&
    JSON.stringify(a.entries ?? []) === JSON.stringify(b.entries ?? [])
  );
}

/** Each opening (and each reload) drafts from its own GET, never the cache. */
let draftCounter = 0;

export function PriceBookDialog({ seed, onClose }: PriceBookDialogProps) {
  const queryClient = useQueryClient();
  const [draftId, setDraftId] = useState(() => ++draftCounter);
  // A fresh GET per draft: a cached book may predate a save from another tab,
  // and a draft built from it would drop that save's entries on the PUT.
  const book = useQuery({
    queryKey: ["price-book", "draft", draftId],
    queryFn: () => fetchPriceBook(),
    staleTime: 0,
    gcTime: 0,
    retry: false,
  });
  /** The stored book the draft was built from: the save checks it still is. */
  const base = useRef<PriceBook | null>(null);
  /** The clicked line's profile is not in the library, so no row was added. */
  const [seedNotice, setSeedNotice] = useState<string | null>(null);
  const library = useQuery({
    queryKey: ["material-library"],
    queryFn: () => fetchMaterialLibrary(),
    staleTime: Infinity,
  });
  const panelRef = useRef<HTMLFormElement>(null);
  const returnFocusTo = useRef<Element | null>(null);
  const nextId = useRef(1);
  const [rows, setRows] = useState<DraftRow[] | null>(null);
  const [problems, setProblems] = useState<Map<number, string>>(new Map());
  /** The row whose price field takes focus once it is on screen. */
  const [focusRow, setFocusRow] = useState<number | null>(null);

  const save = useMutation({
    mutationFn: async (entries: PriceBookEntry[]) => {
      // No version on the PUT (RESEARCH §27), so re-read just before it: a
      // book saved elsewhere since this draft was built is refused, never
      // overwritten.
      const current = await fetchPriceBook();
      if (base.current === null || !sameBook(current, base.current)) {
        throw new Error(BOOK_CHANGED);
      }
      return savePriceBook(entries);
    },
    onSuccess: async (saved) => {
      queryClient.setQueryData(["price-book"], saved);
      onClose();
      await queryClient.invalidateQueries({ queryKey: ["cut-list"] });
    },
  });

  // The draft starts from the stored book, plus the seed's row, once both the
  // book and the library (which resolves the seed's profile name) are in.
  useEffect(() => {
    if (
      rows !== null ||
      book.data === undefined ||
      book.isFetching ||
      library.data === undefined
    )
      return;
    base.current = book.data;
    const draft: DraftRow[] = (book.data.entries ?? []).map((entry) => ({
      id: nextId.current++,
      material: entry.material,
      profile: entry.profile,
      unit: entry.unit,
      stockLengthFt: entry.stock_length_ft ?? DEFAULT_STOCK_FT,
      price: centsToDecimal(entry.price_cents),
    }));
    const seedProfile =
      seed === null
        ? undefined
        : library.data.profiles.find((p) => p.name === seed.profile)?.key;
    if (seed !== null && seedProfile !== undefined) {
      const row: DraftRow = {
        id: nextId.current++,
        material: seed.material,
        profile: seedProfile,
        unit: "each",
        stockLengthFt: seed.stockLengthFt,
        price: "",
      };
      const existing = draft.find((r) => rowKey(r) === rowKey(row));
      if (existing === undefined) draft.push(row);
      setFocusRow(existing?.id ?? row.id);
    }
    setSeedNotice(
      seed !== null && seedProfile === undefined
        ? `${seed.profile} is not a profile in the library, so the price book cannot price it.`
        : null,
    );
    setRows(draft);
  }, [rows, book.data, book.isFetching, library.data, seed]);

  /** Drop the draft and build a new one from the book as it is stored now. */
  const reload = () => {
    save.reset();
    setProblems(new Map());
    setRows(null);
    setDraftId(++draftCounter);
  };

  useEffect(() => {
    returnFocusTo.current = document.activeElement;
    panelRef.current?.focus();
    return () => {
      const target = returnFocusTo.current;
      if (target instanceof HTMLElement && target.isConnected) target.focus();
    };
  }, []);

  useEffect(() => {
    if (focusRow === null || rows === null) return;
    const input = panelRef.current?.querySelector<HTMLInputElement>(
      `[data-row-id="${focusRow}"] [data-testid="price-book-price"]`,
    );
    if (input) {
      input.focus();
      input.select();
      setFocusRow(null);
    }
  }, [focusRow, rows]);

  const saving = save.isPending;
  const onKeyDown = useCallback(
    (event: KeyboardEvent, insidePanel: boolean) => {
      if (event.key === "Escape") {
        event.preventDefault();
        // A save in flight finishes (and closes) on its own.
        if (!saving) onClose();
        return;
      }
      containFocus(panelRef.current, event, insidePanel);
    },
    [onClose, saving],
  );
  useModalLayer("price book", panelRef, onKeyDown);

  const update = (id: number, patch: Partial<DraftRow>) => {
    setRows((current) =>
      current === null
        ? current
        : current.map((row) => (row.id === id ? { ...row, ...patch } : row)),
    );
    if (problems.has(id)) {
      setProblems((current) => {
        const next = new Map(current);
        next.delete(id);
        return next;
      });
    }
  };

  const addRow = () => {
    const last = rows?.[rows.length - 1];
    const row: DraftRow = {
      id: nextId.current++,
      material: last?.material ?? DEFAULT_MATERIAL,
      profile: last?.profile ?? DEFAULT_PROFILE,
      unit: last?.unit ?? "each",
      stockLengthFt: last?.stockLengthFt ?? DEFAULT_STOCK_FT,
      price: "",
    };
    setRows((current) => [...(current ?? []), row]);
    setFocusRow(row.id);
  };

  const removeRow = (id: number) => {
    setRows((current) => current?.filter((row) => row.id !== id) ?? current);
    setProblems((current) => {
      const next = new Map(current);
      next.delete(id);
      return next;
    });
  };

  const submit = () => {
    if (rows === null || save.isPending) return;
    const found = validate(rows);
    setProblems(found);
    if (found.size > 0) {
      const first = rows.find((row) => found.has(row.id));
      if (first) setFocusRow(first.id);
      return;
    }
    save.mutate(
      rows.map((row) => ({
        material: row.material,
        profile: row.profile,
        unit: row.unit,
        stock_length_ft: row.unit === "each" ? row.stockLengthFt : null,
        // validate() proved every price parses.
        price_cents: parseMoney(row.price) ?? 0,
      })),
    );
  };

  const materialOptions = (library.data?.materials ?? []).map((m) => ({
    value: m.key,
    label: m.name,
  }));
  const profileOptions = (library.data?.profiles ?? []).map((p) => ({
    value: p.key,
    label: p.name,
  }));
  const profileName = (key: LumberProfileKey) =>
    library.data?.profiles.find((p) => p.key === key)?.name ?? key;
  const materialName = (key: MaterialKey) =>
    library.data?.materials.find((m) => m.key === key)?.name ?? key;
  const loadError = book.error ?? library.error;

  return createPortal(
    <div
      data-testid="price-book-backdrop"
      className="fixed inset-0 z-menu flex items-center justify-center bg-carbide/85 p-4"
    >
      <form
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="price-book-title"
        aria-describedby="price-book-note"
        tabIndex={-1}
        noValidate
        data-testid="price-book-dialog"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
        className="flex max-h-full w-full max-w-4xl flex-col border border-etch bg-anvil text-mist shadow-float outline-none"
      >
        <header className="flex items-baseline gap-x-4 border-b border-hairline bg-carbide px-4 py-2.5">
          <h2
            id="price-book-title"
            className="font-display text-2xs uppercase tracking-[0.2em] text-gauge"
          >
            Price book
          </h2>
          <span className="grow" />
          <span className="font-data text-xs text-brass">
            {book.data?.currency ?? "USD"}
          </span>
        </header>
        <p
          id="price-book-note"
          className="px-4 pt-3 font-body text-xs text-gauge"
        >
          What you pay for each material and profile. The cut list prices every
          line on the stock pieces it buys: Each at that stock length first,
          then per linear foot, then per board foot (nominal size).
        </p>
        <div className="min-h-0 overflow-y-auto px-4 pt-2">
          {loadError ? (
            <p
              role="alert"
              data-testid="price-book-load-error"
              className="py-3 font-body text-xs text-flag"
            >
              {loadError.message}
            </p>
          ) : rows === null ? (
            <p
              aria-live="polite"
              data-testid="price-book-loading"
              className="py-3 font-body text-xs text-gauge"
            >
              Loading the price book…
            </p>
          ) : (
            <table
              data-testid="price-book-table"
              aria-label={`Price book, ${rows.length} prices`}
              className="w-full table-fixed border-collapse font-body text-sm"
            >
              <thead className="sticky top-0 bg-anvil">
                <tr className="border-b border-hairline">
                  <th scope="col" className={HEAD}>
                    Material
                  </th>
                  <th scope="col" className={`${HEAD} w-[96px]`}>
                    Profile
                  </th>
                  <th scope="col" className={`${HEAD} w-[104px]`}>
                    Priced
                  </th>
                  <th scope="col" className={`${HEAD} w-[96px]`}>
                    Stock
                  </th>
                  <th scope="col" className={`${HEAD} w-[120px]`}>
                    Price (USD)
                  </th>
                  <th scope="col" className="w-[32px]">
                    <span className="sr-only">Remove</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr>
                    <td
                      colSpan={6}
                      data-testid="price-book-empty"
                      className="py-3 font-body text-xs text-gauge"
                    >
                      No prices yet. Add one, or click a blank price in the cut
                      list.
                    </td>
                  </tr>
                ) : null}
                {rows.map((row, index) => {
                  const n = index + 1;
                  const what = `${profileName(row.profile)} ${materialName(row.material)}`;
                  return (
                    <tr
                      key={row.id}
                      data-row-id={row.id}
                      data-testid="price-book-row"
                      data-material={row.material}
                      data-profile={row.profile}
                      data-unit={row.unit}
                      className="border-b border-hairline/60 align-middle"
                    >
                      <td className="py-1.5 pr-2">
                        <SelectField
                          hideLabel
                          label={`Material, price ${n}`}
                          options={materialOptions}
                          value={row.material}
                          disabled={save.isPending}
                          data-testid="price-book-material"
                          onChange={(event) =>
                            update(row.id, {
                              material: event.target.value as MaterialKey,
                            })
                          }
                        />
                      </td>
                      <td className="py-1.5 pr-2">
                        <SelectField
                          hideLabel
                          label={`Profile, price ${n}`}
                          options={profileOptions}
                          value={row.profile}
                          disabled={save.isPending}
                          data-testid="price-book-profile"
                          onChange={(event) =>
                            update(row.id, {
                              profile: event.target.value as LumberProfileKey,
                            })
                          }
                        />
                      </td>
                      <td className="py-1.5 pr-2">
                        <SelectField
                          hideLabel
                          label={`Priced, price ${n}`}
                          options={UNIT_OPTIONS}
                          value={row.unit}
                          disabled={save.isPending}
                          data-testid="price-book-unit"
                          onChange={(event) =>
                            update(row.id, {
                              unit: event.target.value as PriceUnit,
                            })
                          }
                        />
                      </td>
                      <td className="py-1.5 pr-2">
                        {row.unit === "each" ? (
                          <SelectField
                            hideLabel
                            label={`Stock length, price ${n}`}
                            options={STOCK_OPTIONS}
                            value={String(row.stockLengthFt)}
                            disabled={save.isPending}
                            data-testid="price-book-stock"
                            onChange={(event) =>
                              update(row.id, {
                                stockLengthFt: Number(event.target.value),
                              })
                            }
                          />
                        ) : (
                          <span
                            className="block px-2 font-data text-xs text-gauge"
                            title="A per-foot or per-board-foot price is for any stock length"
                          >
                            Any
                          </span>
                        )}
                      </td>
                      <td className="py-1.5 pr-2">
                        <TextField
                          hideLabel
                          label={`Price in dollars, price ${n}`}
                          value={row.price}
                          inputMode="decimal"
                          autoComplete="off"
                          placeholder="0.00"
                          disabled={save.isPending}
                          error={problems.get(row.id) ?? null}
                          data-testid="price-book-price"
                          onChange={(event) =>
                            update(row.id, { price: event.target.value })
                          }
                        />
                      </td>
                      <td className="py-1.5">
                        <button
                          type="button"
                          aria-label={`Remove the ${what} price`}
                          title="Remove this price"
                          data-testid="price-book-remove"
                          disabled={save.isPending}
                          onClick={() => removeRow(row.id)}
                          className="inline-flex min-h-target-dense w-full items-center justify-center font-data text-xs text-gauge outline-none transition-colors duration-fast hover:text-flag focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass disabled:opacity-50"
                        >
                          ×
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          {rows !== null ? (
            <Button
              data-testid="price-book-add"
              className="mt-2"
              disabled={save.isPending || library.data === undefined}
              onClick={addRow}
            >
              Add price
            </Button>
          ) : null}
          {seedNotice !== null ? (
            <p
              role="status"
              data-testid="price-book-seed-notice"
              className="mt-3 font-body text-xs text-gauge"
            >
              {seedNotice}
            </p>
          ) : null}
          {save.error ? (
            <div
              role="alert"
              data-testid="price-book-error"
              className="mt-3 flex items-center gap-3 border border-flag px-3 py-2 font-body text-xs text-flag"
            >
              <span className="grow">{save.error.message}</span>
              {save.error.message === BOOK_CHANGED ? (
                <Button data-testid="price-book-reload" onClick={reload}>
                  Reload the book
                </Button>
              ) : null}
            </div>
          ) : null}
        </div>
        <footer className="mt-4 flex items-center justify-end gap-2 border-t border-hairline px-4 py-2.5">
          <Button
            onClick={onClose}
            disabled={saving}
            data-testid="price-book-cancel"
            className="gap-2"
          >
            Cancel
            <Kbd aria-hidden="true">Esc</Kbd>
          </Button>
          <Button
            type="submit"
            variant="solid"
            disabled={save.isPending || rows === null}
            aria-busy={save.isPending}
            data-testid="price-book-save"
          >
            {save.isPending ? "Saving…" : "Save prices"}
          </Button>
        </footer>
      </form>
    </div>,
    document.body,
  );
}
