/**
 * Folders — the register's filing tree (#WS2). Every type comes from the
 * generated `@loft/ts-client` (pydantic → OpenAPI → TS; CLAUDE.md DRY rule);
 * nothing here re-describes a shape the server already documents.
 *
 * The four decisions this layer is a client of are stated on the server
 * (`py_kit/schemas/folders.py`) and are worth repeating only where they change
 * what a caller may DO:
 *
 * - a folder belongs to ONE drawer, so every call carries a `kind`;
 * - "unfiled" is `folder_id: null` and is a real destination, never an omission
 *   — which is why `moveDocument` takes `string | null` and never an optional;
 * - deleting a folder that still holds things is REFUSED, with the contents
 *   named (`FolderNotEmptyError`), the same grammar the document delete uses;
 * - the counts on a folder come from the server. Nothing in this file derives
 *   one, and the register must not either: at the root the browser is holding
 *   the *unfiled* documents, so any count it made itself would be about a
 *   different set.
 */
import type { components, GatewayClient } from "@loft/ts-client/gateway";

import { gatewayClient } from "./client";
import { envelopeCode, envelopeMessage } from "./envelope";

/** One folder as stored, with its two DIRECT (non-recursive) counts. */
export type FolderResponse = components["schemas"]["FolderResponse"];
/**
 * Which drawer a folder belongs to: `part` | `assembly` | `drawing`.
 * Read off the response's own field — a bare `Literal` alias does not become a
 * named OpenAPI component, so this is where the generated union actually lives.
 */
export type FolderKind = FolderResponse["kind"];
/** One thing inside a folder whose delete was refused (a sub-folder or a doc). */
export type FolderMember = components["schemas"]["FolderMember"];

/**
 * A folder delete was refused because the folder still holds things (409
 * `folder_not_empty`) — the filing-level sibling of
 * `DocumentHasDependentsError`.
 *
 * Typed for the same reason: the user's next action is to move those items out,
 * so the refusal has to name them. "This folder is not empty" would end the
 * conversation.
 */
export class FolderNotEmptyError extends Error {
  constructor(
    readonly contents: FolderMember[],
    message: string,
  ) {
    super(message);
    this.name = "FolderNotEmptyError";
  }
}

/**
 * Runtime narrowing of a 409 envelope's `details.contents`, or null.
 *
 * The SHAPE is the generated contract; this only checks that an `unknown` body
 * really is that shape before trusting it. Returns null rather than a partial
 * list — half a contents list is worse than none, because a user would move out
 * exactly what they were shown and hit the same refusal again.
 */
export function parseFolderContents(body: unknown): FolderMember[] | null {
  if (typeof body !== "object" || body === null) return null;
  const error = (body as Record<string, unknown>).error;
  if (typeof error !== "object" || error === null) return null;
  const details = (error as Record<string, unknown>).details;
  if (typeof details !== "object" || details === null) return null;
  const raw = (details as Record<string, unknown>).contents;
  if (!Array.isArray(raw)) return null;
  const contents: FolderMember[] = [];
  for (const entry of raw) {
    if (typeof entry !== "object" || entry === null) return null;
    const { id, name, kind } = entry as Record<string, unknown>;
    if (typeof id !== "string" || typeof name !== "string") return null;
    if (
      kind !== "folder" &&
      kind !== "part" &&
      kind !== "assembly" &&
      kind !== "drawing"
    ) {
      return null;
    }
    contents.push({ id, name, kind });
  }
  return contents.length > 0 ? contents : null;
}

/** The caller's whole folder tree for one drawer, name-ordered. */
export async function fetchFolders(
  kind: FolderKind,
  client: GatewayClient = gatewayClient,
): Promise<FolderResponse[]> {
  const { data, error } = await client.GET("/api/v1/folders", {
    params: { query: { kind } },
  });
  if (error !== undefined) {
    throw new Error(
      envelopeMessage(error, "Your folders could not be loaded."),
    );
  }
  return data.folders;
}

/** Create a folder at the root (`parentId` null) or inside another (201). */
export async function createFolder(
  name: string,
  kind: FolderKind,
  parentId: string | null = null,
  client: GatewayClient = gatewayClient,
): Promise<FolderResponse> {
  const { data, error } = await client.POST("/api/v1/folders", {
    body: { name, kind, parent_id: parentId },
  });
  if (error !== undefined) {
    if (envelopeCode(error) === "folder_name_taken") {
      throw new Error(
        envelopeMessage(error, `A folder named “${name}” already exists here.`),
      );
    }
    throw new Error(envelopeMessage(error, "The folder could not be created."));
  }
  return data;
}

/** Rename a folder. Renaming cannot move it — that is `moveFolder`. */
export async function renameFolder(
  folderId: string,
  name: string,
  client: GatewayClient = gatewayClient,
): Promise<FolderResponse> {
  const { data, error } = await client.PATCH("/api/v1/folders/{folder_id}", {
    params: { path: { folder_id: folderId } },
    body: { name },
  });
  if (error !== undefined) {
    throw new Error(envelopeMessage(error, "The folder could not be renamed."));
  }
  return data;
}

/**
 * Re-parent a folder; `parentId: null` moves it to the root of its drawer.
 *
 * A move into the folder itself or into one of its own descendants is refused
 * (422 `folder_cycle`) — the server decides that, because only the server holds
 * the whole tree. The message it sends is what the user sees.
 */
export async function moveFolder(
  folderId: string,
  parentId: string | null,
  client: GatewayClient = gatewayClient,
): Promise<FolderResponse> {
  const { data, error } = await client.POST(
    "/api/v1/folders/{folder_id}/move",
    {
      params: { path: { folder_id: folderId } },
      body: { parent_id: parentId },
    },
  );
  if (error !== undefined) {
    throw new Error(envelopeMessage(error, "The folder could not be moved."));
  }
  return data;
}

/**
 * Delete an EMPTY folder (204).
 *
 * A folder that still holds sub-folders or documents is refused with a 409 that
 * NAMES them — thrown as `FolderNotEmptyError` so the register can list them.
 * Never a cascade: deleting a folder cannot delete a document.
 */
export async function deleteFolder(
  folderId: string,
  client: GatewayClient = gatewayClient,
): Promise<void> {
  const { error } = await client.DELETE("/api/v1/folders/{folder_id}", {
    params: { path: { folder_id: folderId } },
  });
  if (error !== undefined) {
    const contents = parseFolderContents(error);
    if (contents !== null) {
      throw new FolderNotEmptyError(
        contents,
        envelopeMessage(error, "That folder still holds items."),
      );
    }
    throw new Error(envelopeMessage(error, "The folder could not be deleted."));
  }
}

/**
 * The ancestor chain of a folder, ROOT FIRST — the breadcrumb.
 *
 * Pure, over the flat tree the list endpoint returns, and defensive about a
 * chain that does not terminate: it stops at the number of folders that exist,
 * so a malformed tree renders a short breadcrumb rather than hanging the tab.
 * Returns an empty array for the root view.
 */
export function folderPath(
  folders: readonly FolderResponse[],
  folderId: string | null,
): FolderResponse[] {
  const byId = new Map(folders.map((folder) => [folder.id, folder]));
  const chain: FolderResponse[] = [];
  let current = folderId === null ? undefined : byId.get(folderId);
  while (current !== undefined && chain.length <= folders.length) {
    chain.unshift(current);
    current =
      current.parent_id === null ? undefined : byId.get(current.parent_id);
  }
  return chain;
}

/**
 * A folder's full path as text ("Gearbox / Housings"), for a row label and for
 * the move picker. `null` is the drawer root, which has a NAME rather than an
 * empty string, because "Unfiled" is a place a document can be.
 */
export function folderPathLabel(
  folders: readonly FolderResponse[],
  folderId: string | null,
): string {
  if (folderId === null) return UNFILED_LABEL;
  const chain = folderPath(folders, folderId);
  // A folder we were not given (deleted or filtered out) is reported as
  // unknown rather than silently drawn as the root: the register would
  // otherwise claim a document is unfiled when the server says it is not.
  return chain.length === 0
    ? "Unknown folder"
    : chain.map((folder) => folder.name).join(" / ");
}

/** What the root of a drawer is called wherever a folder name would go. */
export const UNFILED_LABEL = "Unfiled";

/** The folders directly inside `parentId` (null = the drawer's top level). */
export function childFolders(
  folders: readonly FolderResponse[],
  parentId: string | null,
): FolderResponse[] {
  return folders.filter((folder) => folder.parent_id === parentId);
}
