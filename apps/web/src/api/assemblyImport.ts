/**
 * STEP ASSEMBLY IMPORT — the register's way in for geometry that already
 * exists (REACH-2).
 *
 * `POST /api/v1/assemblies/import` takes the raw file bytes as the request body
 * (`application/octet-stream`, exactly as the part-level `importStep` does) and
 * answers with a DISCRIMINATED result: a STEP carrying product structure becomes
 * an assembly (`kind: "assembly"` — deduped parts + named instances at their
 * imported placements), a flat one becomes a single part (`kind: "part"`). Both
 * shapes come from the generated `@loft/ts-client` (CLAUDE.md DRY rule); nothing
 * here hand-writes an API type, and every rejection surfaces the server
 * envelope's own message (`import_not_step` / `import_too_large` /
 * `import_too_many_products` / `import_no_solid` / …).
 *
 * Lives beside `assemblies.ts` rather than inside it because the import is the
 * only call in the register that is not assembly CRUD: it can return a PART.
 */
import type { components, GatewayClient } from "@loft/ts-client/gateway";

// The name-collision error is the SAME concept the create path already has, so
// it is reused rather than re-declared (DRY): a caller only has to know one
// type to offer one recovery.
import { AssemblyNameTakenError } from "./assemblies";
import { gatewayClient } from "./client";
import { envelopeCode, envelopeMessage } from "./envelope";

export type AssemblyImportResult =
  components["schemas"]["AssemblyImportResult"];
export type SingleBodyImportResult =
  components["schemas"]["SingleBodyImportResult"];

/**
 * What the server made of the file. Narrow on `kind` — the server decides, the
 * client never guesses from the filename or the byte count.
 */
export type StepImportResult = AssemblyImportResult | SingleBodyImportResult;

/**
 * The document-name ceiling the route declares (`maxLength: 200`). Mirrored
 * here only so the suffix retry below cannot build a name the server must
 * reject for a second, unrelated reason.
 */
export const IMPORT_NAME_MAX = 200;

/**
 * WITHDRAWING AN IMPORT IS A USER ACTION, NOT A FAILURE.
 *
 * `fetch` rejects an aborted request with a `DOMException` named
 * `"AbortError"`, and the one thing a caller must never do with it is surface
 * it as "the STEP file could not be imported" — the user knows perfectly well
 * what happened; they did it. This predicate is exported so the page and the
 * retry loop below both recognise it the same way, rather than each
 * string-matching a message.
 */
export function isImportAborted(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

/**
 * Stream one STEP file at the import route and return the server's result.
 *
 * A name collision (409 `assembly_name_taken` / `part_name_taken`) throws the
 * typed {@link AssemblyNameTakenError} so the caller can retry under a free
 * name — see {@link importStepAsNewDocument}, which is what the register uses.
 *
 * `signal` withdraws the request in flight. It matters because the client's own
 * ceiling is 16 MiB and a real supplier assembly parses server-side for as long
 * as it takes: UI-REVIEW 2026-08-27 P1-B measured 3.35 s for a 52 KB fixture,
 * over 300x smaller than a file this route will accept. A wait you cannot stop
 * is a dead end, which this repo's flow rule forbids outright.
 */
export async function importAssemblyStep(
  bytes: ArrayBuffer,
  name: string,
  client: GatewayClient = gatewayClient,
  signal?: AbortSignal,
): Promise<StepImportResult> {
  const { data, error } = await client.POST("/api/v1/assemblies/import", {
    params: { query: { name } },
    // The generated schema types the octet-stream body as `string`; the raw
    // bytes pass through a byte-identity serializer and the content-type is set
    // explicitly so the default JSON header is not sent (same seam as
    // `importStep` in `parts.ts`).
    body: bytes as unknown as string,
    bodySerializer: (raw: unknown) => raw as BodyInit,
    headers: { "Content-Type": "application/octet-stream" },
    signal,
  });
  if (error !== undefined) {
    const code = envelopeCode(error);
    if (
      code === "assembly_name_taken" ||
      code === "part_name_taken" ||
      code === "name_taken"
    ) {
      throw new AssemblyNameTakenError(
        name,
        envelopeMessage(error, `A document named “${name}” already exists.`),
      );
    }
    throw new Error(
      envelopeMessage(error, "The STEP file could not be imported."),
    );
  }
  return data;
}

/** How many names are tried before the collision is reported to the user. */
export const IMPORT_NAME_ATTEMPTS = 6;

/**
 * Import the file under its own name, stepping to "name (2)", "name (3)", …
 * when that name is already filed.
 *
 * A supplier file is imported under the name it arrives with — that is the
 * whole point of importing rather than scribing — and the user cannot rename a
 * file they do not own. So a bare "an assembly named bracket already exists"
 * would be a DEAD END (CLAUDE.md flow rule: no dead ends), reachable simply by
 * importing the same file twice. Fusion resolves the same collision the same
 * way. After {@link IMPORT_NAME_ATTEMPTS} the collision IS the answer and the
 * server's message is surfaced verbatim.
 */
export async function importStepAsNewDocument(
  bytes: ArrayBuffer,
  baseName: string,
  client: GatewayClient = gatewayClient,
  signal?: AbortSignal,
): Promise<StepImportResult> {
  // Leave room for the " (n)" the retries append, so a long supplier filename
  // cannot turn a collision into a length rejection.
  const stem = baseName.slice(0, IMPORT_NAME_MAX - 8);
  let lastTaken: AssemblyNameTakenError | null = null;
  for (let attempt = 1; attempt <= IMPORT_NAME_ATTEMPTS; attempt += 1) {
    // A withdrawn import must not come back as attempt 2 under a new name.
    // Aborting mid-loop is the case that would otherwise file a document the
    // user had just told us to stop making — checked BEFORE the call so an
    // abort between attempts is honoured too, not only one during a request.
    signal?.throwIfAborted();
    try {
      return await importAssemblyStep(
        bytes,
        attempt === 1 ? stem : `${stem} (${attempt})`,
        client,
        signal,
      );
    } catch (error) {
      if (!(error instanceof AssemblyNameTakenError)) throw error;
      lastTaken = error;
    }
  }
  throw lastTaken ?? new Error("The STEP file could not be imported.");
}
