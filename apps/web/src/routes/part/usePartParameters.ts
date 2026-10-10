/**
 * The Parameters panel in the part workspace (PART-PARAMETERS, RESEARCH §20):
 * whether it is open, the working table, and the one write that saves it.
 *
 * A save is a tree write like a feature save: it holds the write counter, sends
 * the tree version on screen, and ends in the same `refreshTreeAndBody` every
 * write uses, so the History buttons and Ctrl+Z see it at once — and an undo
 * or redo, which moves `tree_version`, refetches the table through the query
 * key below, and the panel follows.
 *
 * The working table survives the panel closing (the hook lives as long as the
 * page), so a refused edit is still there, as typed, when it is reopened.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  fetchPartParameters,
  ParameterTableError,
  type ParameterUnit,
  putPartParameters,
} from "../../api/parameters";
import { StaleTreeVersionError } from "../../api/parts";
import {
  blankRow,
  commitCell as commitCellRows,
  deleteRow as deleteRowFrom,
  type DraftRow,
  mapTableError,
  type ParameterField,
  rebaseRows,
  restoreDeletedRow,
  rowsFromServer,
  type RowError,
  sameAsStored,
  setRowUnit,
  tableToWire,
} from "../../features/parameters";
import { useGlobalKeys } from "../../lib/modalGate";
import { KEY_PARAMETERS } from "../../shortcuts/registry";
import type { PartBody } from "./usePartBody";
import type { PartDocument } from "./usePartDocument";
import type { TreeWrites } from "./useTreeWrites";

type PartParametersParams = Pick<
  PartDocument,
  "partId" | "queryClient" | "tree" | "mode" | "lengthUnit"
> &
  Pick<PartBody, "editor"> &
  Pick<
    TreeWrites,
    | "refreshTreeAndBody"
    | "beginTreeWrite"
    | "endTreeWrite"
    | "noteWrittenTreeVersion"
  >;

interface TableState {
  /** The stored table the working rows were last rebased onto. */
  base: DraftRow[];
  /** What the panel shows: the stored table plus the user's unsaved edits. */
  rows: DraftRow[];
  /** The `tree_version` `base` was read at; null before the first read. */
  version: number | null;
}

const EMPTY: TableState = { base: [], rows: [], version: null };

export function usePartParameters({
  partId,
  queryClient,
  tree,
  mode,
  lengthUnit,
  editor,
  refreshTreeAndBody,
  beginTreeWrite,
  endTreeWrite,
  noteWrittenTreeVersion,
}: PartParametersParams) {
  const [panelOpen, setPanelOpen] = useState(false);
  const [table, setTableState] = useState<TableState>(EMPTY);
  const [error, setError] = useState<RowError | null>(null);
  const [stale, setStale] = useState(false);
  const [saving, setSaving] = useState(false);
  const [focusRowId, setFocusRowId] = useState<string | null>(null);

  // The async write reads the table AFTER the cell commit that triggered it,
  // in the same tick, so the ref (not React state) is the source of truth.
  const tableRef = useRef<TableState>(EMPTY);
  const setTable = useCallback((next: TableState) => {
    tableRef.current = next;
    setTableState(next);
  }, []);

  // A new part, a new table.
  useEffect(() => {
    setTable(EMPTY);
    setError(null);
    setStale(false);
  }, [partId, setTable]);

  const treeVersion = tree.data?.tree_version;
  const queryKey = useCallback(
    (version: number | undefined) => ["part-parameters", partId, version],
    [partId],
  );
  const query = useQuery({
    queryKey: queryKey(treeVersion),
    queryFn: () => fetchPartParameters(partId),
    enabled: panelOpen && treeVersion !== undefined,
    staleTime: Infinity,
    // Keep the old table on screen while the new version loads, rather than
    // flashing "Reading…" after every undo.
    placeholderData: keepPreviousData,
  });

  // A newer stored table (an undo, a redo, another window, the read after a
  // lost race): take it, with the user's unsaved edits re-applied on top.
  useEffect(() => {
    const data = query.data;
    if (data === undefined || query.isPlaceholderData) return;
    const current = tableRef.current;
    if (data.tree_version === current.version) return;
    const fresh = rowsFromServer(data.parameters);
    setTable({
      base: fresh,
      rows:
        current.version === null
          ? fresh
          : rebaseRows(current.base, current.rows, fresh),
      version: data.tree_version,
    });
  }, [query.data, query.isPlaceholderData, setTable]);

  const blockedReason =
    mode !== "off"
      ? "Finish the sketch to change parameters."
      : editor !== null
        ? "Close the open command to change parameters."
        : undefined;

  /** The highest tree version this page has seen: versions only go up. */
  const knownVersion = useRef<number | null>(null);
  useEffect(() => {
    knownVersion.current = null;
  }, [partId]);
  const expectedVersion = useCallback((): number | undefined => {
    const seen = [treeVersion, knownVersion.current].filter(
      (v): v is number => typeof v === "number",
    );
    return seen.length === 0 ? undefined : Math.max(...seen);
  }, [treeVersion]);

  const inFlight = useRef(false);
  const again = useRef(false);
  const saveRef = useRef<() => Promise<void>>(async () => {});

  const save = useCallback(async () => {
    if (blockedReason !== undefined) return;
    if (inFlight.current) {
      again.current = true;
      return;
    }
    const sent = tableRef.current;
    const wire = tableToWire(sent.rows, sent.base);
    if ("error" in wire) {
      setError(wire.error);
      return;
    }
    if (sameAsStored(wire.body, sent.base)) {
      // Nothing to send: whatever was refused has been put back.
      setError(null);
      return;
    }
    const expected = expectedVersion();
    if (expected === undefined) return;
    inFlight.current = true;
    setSaving(true);
    beginTreeWrite();
    try {
      const response = await putPartParameters(partId, wire.body, expected);
      knownVersion.current = response.tree_version;
      noteWrittenTreeVersion(response.tree_version);
      // The tree refetch below moves the query key to this version; seed it
      // so the panel does not read back what it was just told.
      queryClient.setQueryData(queryKey(response.tree_version), response);
      const fresh = rowsFromServer(response.parameters);
      setTable({
        base: fresh,
        // Anything typed while the write was in flight stays on top.
        rows: rebaseRows(sent.rows, tableRef.current.rows, fresh),
        version: response.tree_version,
      });
      setError(null);
      setStale(false);
      await refreshTreeAndBody();
    } catch (caught) {
      if (caught instanceof StaleTreeVersionError) {
        // The refetch moves the query to the latest version and the effect
        // above rebases the user's edits onto it; they review and retry.
        setError(null);
        setStale(true);
        await refreshTreeAndBody();
      } else if (caught instanceof ParameterTableError) {
        const current = tableRef.current;
        const rows = restoreDeletedRow(
          current.rows,
          current.base,
          caught.parameter,
        );
        setTable({ ...current, rows });
        setError(mapTableError(caught, rows));
      } else {
        setError({
          rowId: null,
          field: "expression",
          code: "unreachable",
          message:
            caught instanceof Error
              ? caught.message
              : "The parameters could not be saved.",
        });
      }
    } finally {
      inFlight.current = false;
      setSaving(false);
      endTreeWrite();
      if (again.current) {
        again.current = false;
        void saveRef.current();
      }
    }
  }, [
    blockedReason,
    expectedVersion,
    beginTreeWrite,
    endTreeWrite,
    noteWrittenTreeVersion,
    partId,
    queryClient,
    queryKey,
    refreshTreeAndBody,
    setTable,
  ]);
  useEffect(() => {
    saveRef.current = save;
  }, [save]);

  const editRows = useCallback(
    (edit: (rows: DraftRow[]) => DraftRow[]) => {
      const current = tableRef.current;
      setTable({ ...current, rows: edit(current.rows) });
    },
    [setTable],
  );

  const commitCell = useCallback(
    (id: string, field: ParameterField, text: string) => {
      editRows((rows) => commitCellRows(rows, id, field, text, lengthUnit));
      void save();
    },
    [editRows, lengthUnit, save],
  );

  const setUnit = useCallback(
    (id: string, unit: ParameterUnit) => {
      editRows((rows) => setRowUnit(rows, id, unit));
      void save();
    },
    [editRows, save],
  );

  const addRow = useCallback(() => {
    const row = blankRow();
    editRows((rows) => [...rows, row]);
    setFocusRowId(row.id);
  }, [editRows]);

  const deleteRow = useCallback(
    (id: string) => {
      editRows((rows) => deleteRowFrom(rows, id));
      if (tableRef.current.base.some((row) => row.id === id)) void save();
      else setError((current) => (current?.rowId === id ? null : current));
    },
    [editRows, save],
  );

  const retry = useCallback(() => {
    setStale(false);
    void save();
  }, [save]);

  const openPanel = useCallback(() => setPanelOpen(true), []);
  const closePanel = useCallback(() => {
    setPanelOpen(false);
    setFocusRowId(null);
  }, []);
  const togglePanel = useCallback(() => {
    setPanelOpen((open) => !open);
    setFocusRowId(null);
  }, []);

  // `=` opens and closes the panel (the equals of a formula), with no command
  // open — the Modelling group's rule. Not while typing: `=` is a character.
  useGlobalKeys(
    "parameters panel",
    mode === "off" && editor === null
      ? (event: KeyboardEvent) => {
          if (event.ctrlKey || event.metaKey || event.altKey) return;
          if (event.key !== KEY_PARAMETERS) return;
          event.preventDefault();
          togglePanel();
        }
      : null,
  );

  const stored = useMemo(
    () => new Map(table.base.map((row) => [row.id, row])),
    [table.base],
  );

  return {
    panelOpen,
    openPanel,
    closePanel,
    togglePanel,
    rows: table.version === null ? undefined : table.rows,
    stored,
    loadError:
      table.version === null && query.error instanceof Error
        ? query.error.message
        : null,
    error,
    stale,
    saving,
    blockedReason,
    focusRowId,
    commitCell,
    setUnit,
    addRow,
    deleteRow,
    retry,
  };
}

export type PartParameters = ReturnType<typeof usePartParameters>;
