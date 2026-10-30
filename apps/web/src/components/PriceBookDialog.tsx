/**
 * PRICE BOOK (CUT-LIST-PRICES): what you pay for lumber, the list the cut list
 * prices itself from (RESEARCH §27). Chief Architect's Master List and
 * SolidWorks' Cost property, reduced to the one table a builder keeps: a
 * material and a profile, priced Each at a stock length, per linear foot or
 * per board foot; a sheet product (SHEATHING), priced Each per sheet; or a
 * window or door unit (OPENING-UNITS), priced Each by its call size
 * ('window_3040') and frame material; or an item priced its one way: a
 * foundation item (SLAB), ready-mix per cubic yard, #4 rebar Each per 20 ft
 * stick, an anchor bolt Each, a casework item (CASEWORK), edge banding per
 * foot and hinges and slide pairs Each, or siding (SIDING-TRIM), a 12 ft
 * board Each or vinyl per square. The profile list files each kind under its own heading.
 *
 * The book is saved whole (`PUT` replaces it), so the dialog edits a draft and
 * Save sends every row; Cancel or Escape drops the draft. Opened from a blank
 * price in the cut list it adds a row pre-filled with that line's material,
 * profile and stock length (or sheet, or unit), its price field focused, so pricing a
 * line is typing a number and pressing Enter. A save refetches every cut
 * list, so the panel re-prices without a reload.
 *
 * The save names the book's version it was drafted from (PRICE-BOOK-VERSION):
 * a book saved elsewhere since is refused by the server with 412, shown as
 * "the price book changed elsewhere" with a Reload, and never overwritten.
 *
 * Prices are typed as decimals and parsed to integer cents on the digits
 * (`lib/money`); nothing here does float arithmetic on money.
 */
import { Button, Kbd, SelectField, TextField } from "@loft/design";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import type { MaterialKey, MaterialLibrary } from "../api/materials";
import { fetchMaterialLibrary } from "../api/materials";
import {
  BOOK_CHANGED,
  fetchPriceBook,
  type LumberProfileKey,
  PRICE_UNIT_LABEL,
  type PriceBook,
  PriceBookChangedError,
  type PriceBookEntry,
  type PriceProfileKey,
  type PriceUnit,
  savePriceBook,
  type SheetSizeKey,
  STOCK_LENGTHS_FT,
} from "../api/priceBook";
import { useModalLayer } from "../lib/modalGate";
import { centsToDecimal, parseMoney } from "../lib/money";
import { containFocus } from "./dialogKeys";

/** The line a blank price was clicked on: what the new row starts as. */
export interface PriceBookSeed {
  material: MaterialKey;
  /** The profile as the cut list names it ("2x10", "5/4x6", "7/16 OSB"). */
  profile: string;
  /** A lumber line's stock length (ft); null for a sheet line. */
  stockLengthFt: number | null;
  /**
   * A spliced line's pieces (ft, e.g. [16, 8]): a row is added for each
   * length the book does not price yet, so every piece can be priced.
   */
  stockLengthsFt?: readonly number[];
  /** A sheet line's sheet ("4x9"); null or absent for lumber. */
  sheet?: SheetSizeKey | null;
  /**
   * A window or door unit line's price-book key ('window_3040'): the row is
   * that unit, priced Each. Null or absent for lumber and sheets.
   */
  unitKey?: string | null;
}

export interface PriceBookDialogProps {
  /** Pre-fill a new row for this line; null opens the book as it is. */
  seed: PriceBookSeed | null;
  onClose: () => void;
}

/** What a row prices: lumber, a sheet product, a window or door unit, or a
 * foundation item (priced its one way: its unit and stock are the item's). */
type RowKind = "lumber" | "sheet" | "unit" | "item";

interface DraftRow {
  id: number;
  kind: RowKind;
  material: MaterialKey;
  profile: PriceProfileKey;
  unit: PriceUnit;
  stockLengthFt: number;
  /** The sheet a sheet product's price is for (unused for lumber). */
  sheet: SheetSizeKey;
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
const DEFAULT_SHEET: SheetSizeKey = "4x8";

const HEAD =
  "py-1 pr-2 text-left font-display text-2xs font-normal uppercase tracking-[0.14em] text-gauge";

/**
 * What a profile key prices, by the library's lists. A stored key the library
 * no longer lists is read from its entry's shape: a sheet names a sheet, a
 * stock length or a per-foot price is lumber, and a bare Each is a unit.
 */
function kindOf(
  profile: PriceProfileKey,
  library: MaterialLibrary | undefined,
  entry?: PriceBookEntry,
): RowKind {
  if (library?.opening_units?.some((u) => u.key === profile)) return "unit";
  if (pricedItems(library).some((i) => i.key === profile)) return "item";
  if (library?.sheet_goods.some((g) => g.key === profile)) return "sheet";
  if (library?.profiles.some((p) => p.key === profile)) return "lumber";
  if (entry === undefined)
    return profile.startsWith("us_") ? "lumber" : "sheet";
  if (entry.sheet !== null && entry.sheet !== undefined) return "sheet";
  if (entry.unit === "cubic_yard" || entry.unit === "square") return "item";
  if (entry.unit !== "each" || entry.stock_length_ft != null) return "lumber";
  return "unit";
}

/** The items the book prices one way, with their unit and stock: the
 * foundation items (SLAB) and casework banding and hardware (CASEWORK). */
function pricedItems(library: MaterialLibrary | undefined): {
  key: PriceProfileKey;
  name: string;
  material: MaterialKey;
  price_unit: PriceUnit;
  stock_length_ft: number | null;
  group: string;
}[] {
  return [
    ...(library?.foundation_items ?? []).map((i) => ({
      key: i.key as PriceProfileKey,
      name: i.name,
      material: i.material as MaterialKey,
      price_unit: i.price_unit as PriceUnit,
      stock_length_ft: i.stock_length_ft ?? null,
      group: "Foundation",
    })),
    ...(library?.casework_items ?? []).map((i) => ({
      key: i.key as PriceProfileKey,
      name: i.name,
      material: (i.materials[0] ?? "steel_1018") as MaterialKey,
      price_unit: i.unit as PriceUnit,
      stock_length_ft: null,
      group: "Casework",
    })),
    // Siding (SIDING-TRIM): a 12 ft board Each, vinyl per square.
    ...(library?.siding_products ?? []).map((i) => ({
      key: i.key as PriceProfileKey,
      name: i.name,
      material: i.material as MaterialKey,
      price_unit: i.price_unit as PriceUnit,
      stock_length_ft: i.stock_length_ft ?? null,
      group: "Siding",
    })),
  ];
}

function rowKey(row: DraftRow): string {
  if (row.kind === "item") {
    return [row.material, row.profile, row.unit, row.stockLengthFt].join("|");
  }
  return [
    row.material,
    row.profile,
    row.kind === "lumber" ? row.unit : "each",
    row.kind === "sheet"
      ? row.sheet
      : row.kind === "unit" || row.unit !== "each"
        ? ""
        : row.stockLengthFt,
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

export { BOOK_CHANGED };

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
    // The server checks the version (If-Match) and refuses a book saved
    // elsewhere since this draft was read: 412, never an overwrite.
    mutationFn: (entries: PriceBookEntry[]) =>
      savePriceBook(entries, base.current?.version ?? 0),
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
    const draft: DraftRow[] = (book.data.entries ?? []).map((entry) => {
      const kind = kindOf(entry.profile, library.data, entry);
      return {
        id: nextId.current++,
        kind,
        material: entry.material,
        profile: entry.profile,
        unit: entry.unit,
        // An item's stock is its own (a rebar stick's 20 ft, else none).
        stockLengthFt:
          entry.stock_length_ft ?? (kind === "item" ? 0 : DEFAULT_STOCK_FT),
        sheet: entry.sheet ?? DEFAULT_SHEET,
        price: centsToDecimal(entry.price_cents),
      };
    });
    const unitKey = seed?.unitKey ?? null;
    const seedProfile: PriceProfileKey | undefined =
      seed === null
        ? undefined
        : unitKey !== null
          ? library.data.opening_units?.find((u) => u.key === unitKey)?.key
          : (library.data.profiles.find((p) => p.name === seed.profile)?.key ??
            library.data.sheet_goods.find((g) => g.name === seed.profile)
              ?.key ??
            pricedItems(library.data).find((i) => i.name === seed.profile)
              ?.key);
    const seedItem = pricedItems(library.data).find(
      (i) => i.key === seedProfile,
    );
    if (seed !== null && seedProfile !== undefined) {
      const lengths = [...new Set(seed.stockLengthsFt ?? [seed.stockLengthFt])];
      let focus: number | null = null;
      let firstExisting: number | null = null;
      for (const feet of lengths) {
        const row: DraftRow = {
          id: nextId.current++,
          kind: kindOf(seedProfile, library.data),
          material: seed.material,
          profile: seedProfile,
          unit: seedItem?.price_unit ?? "each",
          stockLengthFt:
            seedItem === undefined
              ? (feet ?? DEFAULT_STOCK_FT)
              : (seedItem.stock_length_ft ?? 0),
          sheet: seed.sheet ?? DEFAULT_SHEET,
          price: "",
        };
        const existing = draft.find((r) => rowKey(r) === rowKey(row));
        if (existing === undefined) {
          draft.push(row);
          focus ??= row.id;
        } else {
          firstExisting ??= existing.id;
        }
      }
      setFocusRow(focus ?? firstExisting);
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
      kind: last?.kind ?? "lumber",
      material: last?.material ?? DEFAULT_MATERIAL,
      profile: last?.profile ?? DEFAULT_PROFILE,
      unit: last?.unit ?? "each",
      stockLengthFt: last?.stockLengthFt ?? DEFAULT_STOCK_FT,
      sheet: last?.sheet ?? DEFAULT_SHEET,
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
      rows.map((row) => {
        const lumber = row.kind === "lumber";
        if (row.kind === "item") {
          // An item is priced its one way (profilePatch set it).
          return {
            material: row.material,
            profile: row.profile,
            unit: row.unit,
            stock_length_ft: row.stockLengthFt > 0 ? row.stockLengthFt : null,
            sheet: null,
            price_cents: parseMoney(row.price) ?? 0,
          };
        }
        return {
          material: row.material,
          profile: row.profile,
          // A sheet is priced Each per sheet, a unit Each per unit.
          unit: lumber ? row.unit : "each",
          stock_length_ft:
            lumber && row.unit === "each" ? row.stockLengthFt : null,
          sheet: row.kind === "sheet" ? row.sheet : null,
          // validate() proved every price parses.
          price_cents: parseMoney(row.price) ?? 0,
        };
      }),
    );
  };

  const materialOptions = (library.data?.materials ?? []).map((m) => ({
    value: m.key,
    label: m.name,
  }));
  // Each kind under its own heading, as a builder's price list is laid out.
  const profileOptions: {
    value: PriceProfileKey;
    label: string;
    group: string;
  }[] = [
    ...(library.data?.profiles ?? []).map((p) => ({
      value: p.key,
      label: p.name,
      group: "Lumber",
    })),
    ...(library.data?.sheet_goods ?? []).map((g) => ({
      value: g.key,
      label: g.name,
      group: "Sheet goods",
    })),
    ...(library.data?.opening_units ?? []).map((u) => ({
      value: u.key,
      label: u.name,
      group: u.kind === "door" ? "Doors" : "Windows",
    })),
    ...pricedItems(library.data).map((i) => ({
      value: i.key,
      label: i.name,
      group: i.group,
    })),
  ];
  const sheetOptions = (library.data?.sheet_sizes ?? []).map((size) => ({
    value: size.key,
    label: size.key,
  }));
  const profileName = (key: PriceProfileKey) =>
    profileOptions.find((p) => p.value === key)?.label ?? key;
  /**
   * A new profile: a sheet product is priced Each in its own material, and a
   * unit Each in its frame's.
   */
  const profilePatch = (key: PriceProfileKey): Partial<DraftRow> => {
    const good = library.data?.sheet_goods.find((g) => g.key === key);
    if (good !== undefined) {
      return {
        profile: key,
        kind: "sheet",
        unit: "each",
        material: good.material,
      };
    }
    const unit = library.data?.opening_units?.find((u) => u.key === key);
    if (unit !== undefined) {
      return {
        profile: key,
        kind: "unit",
        unit: "each",
        material: unit.material,
      };
    }
    const item = pricedItems(library.data).find((i) => i.key === key);
    if (item !== undefined) {
      return {
        profile: key,
        kind: "item",
        unit: item.price_unit,
        stockLengthFt: item.stock_length_ft ?? 0,
        material: item.material,
      };
    }
    return { profile: key, kind: "lumber" };
  };
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
          then per linear foot, then per board foot (nominal size). Sheet goods
          are priced Each per sheet, on the sheets their area needs; windows and
          doors Each per unit, by call size; concrete per cubic yard ordered,
          rebar Each per 20 ft stick and anchor bolts Each.
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
                  <th scope="col" className={`${HEAD} w-[152px]`}>
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
                  const sheet = row.kind === "sheet";
                  const unitRow = row.kind === "unit";
                  const itemRow = row.kind === "item";
                  const what = `${profileName(row.profile)} ${materialName(row.material)}`;
                  return (
                    <tr
                      key={row.id}
                      data-row-id={row.id}
                      data-testid="price-book-row"
                      data-material={row.material}
                      data-profile={row.profile}
                      data-unit={row.unit}
                      data-kind={row.kind}
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
                            update(
                              row.id,
                              profilePatch(
                                event.target.value as PriceProfileKey,
                              ),
                            )
                          }
                        />
                      </td>
                      <td className="py-1.5 pr-2">
                        {itemRow ? (
                          <span
                            className="block px-2 font-data text-xs text-mist"
                            title="An item is priced one way"
                            data-testid="price-book-unit-item"
                          >
                            {PRICE_UNIT_LABEL[row.unit]}
                          </span>
                        ) : sheet || unitRow ? (
                          <span
                            className="block px-2 font-data text-xs text-mist"
                            title={
                              sheet
                                ? "A sheet is priced Each, per sheet"
                                : "A window or door is priced Each, per unit"
                            }
                            data-testid={
                              sheet
                                ? "price-book-unit-sheet"
                                : "price-book-unit-each"
                            }
                          >
                            Each
                          </span>
                        ) : (
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
                        )}
                      </td>
                      <td className="py-1.5 pr-2">
                        {itemRow ? (
                          <span
                            className="block px-2 font-data text-xs text-gauge"
                            data-testid="price-book-stock-item"
                          >
                            {row.stockLengthFt > 0
                              ? `${row.stockLengthFt} ft`
                              : row.unit === "cubic_yard"
                                ? "Ordered"
                                : "Each"}
                          </span>
                        ) : sheet ? (
                          <SelectField
                            hideLabel
                            label={`Sheet, price ${n}`}
                            options={sheetOptions}
                            value={row.sheet}
                            disabled={save.isPending}
                            data-testid="price-book-sheet"
                            onChange={(event) =>
                              update(row.id, {
                                sheet: event.target.value as SheetSizeKey,
                              })
                            }
                          />
                        ) : unitRow ? (
                          <span
                            className="block px-2 font-data text-xs text-gauge"
                            title="One price per unit: its frame and its glazing or slab"
                            data-testid="price-book-stock-unit"
                          >
                            Unit
                          </span>
                        ) : row.unit === "each" ? (
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
              {save.error instanceof PriceBookChangedError ? (
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
