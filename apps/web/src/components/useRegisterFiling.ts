import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";

import {
  createFolder,
  deleteFolder,
  fetchFolders,
  type FolderKind,
  type FolderResponse,
  renameFolder,
} from "../api/folders";
import type { RegisterDocument, RegisterFiling } from "./DocumentRegister";

/**
 * The filing wiring, written ONCE for all three drawers (#WS2, CLAUDE.md DRY).
 *
 * Parts, assemblies and drawings file identically — the only thing that differs
 * is the drawer's `kind`, the query key its documents live under, and which
 * `move*` function to call. Three copies of this hook would be three chances
 * for one drawer's move to forget an invalidation and start showing a document
 * in the folder it used to be in, which is precisely the defect this row is
 * being held to.
 *
 * INVALIDATION IS THE POINT. Every mutation here invalidates BOTH queries: the
 * documents list (a moved document's `folder_id` changed) and the folder list
 * (its counts changed). A move that refreshed only the documents would leave a
 * folder row printing the count it had before — a number the server never sent
 * for that state, which is the same class of defect as a stale rebuild badge.
 */
export function useRegisterFiling<T extends RegisterDocument>(
  kind: FolderKind,
  /** The TanStack key the drawer's documents live under ("parts", …). */
  documentsKey: string,
  /** The drawer's move endpoint — `movePart`, `moveAssembly`, `moveDrawing`. */
  move: (documentId: string, folderId: string | null) => Promise<unknown>,
): RegisterFiling<T> {
  const queryClient = useQueryClient();
  const folders = useQuery({
    queryKey: ["folders", kind],
    queryFn: () => fetchFolders(kind),
    staleTime: 30_000,
  });

  return useMemo(() => {
    const refresh = async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["folders", kind] }),
        queryClient.invalidateQueries({ queryKey: [documentsKey] }),
      ]);
    };
    return {
      // An in-flight or failed folder query yields an EMPTY tree, so the
      // register draws no dividers rather than dividers it cannot vouch for.
      // The documents themselves still list — filing is an index over the
      // drawer, not a gate on reading it.
      folders: folders.data ?? [],
      isLoading: folders.isLoading,
      onCreateFolder: async (name: string, parentId: string | null) => {
        await createFolder(name, kind, parentId);
        await refresh();
      },
      onRenameFolder: async (folder: FolderResponse, name: string) => {
        await renameFolder(folder.id, name);
        await refresh();
      },
      onDeleteFolder: async (folder: FolderResponse) => {
        await deleteFolder(folder.id);
        await refresh();
      },
      onMoveDocument: async (document: T, folderId: string | null) => {
        await move(document.id, folderId);
        await refresh();
      },
    };
  }, [folders.data, folders.isLoading, kind, documentsKey, move, queryClient]);
}
