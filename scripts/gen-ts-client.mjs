#!/usr/bin/env node
/**
 * Generate the typed TS client from the committed OpenAPI contracts
 * (`just gen` step 2).
 *
 * For each service in packages/contracts/<service>.openapi.json:
 *   - src/<service>/schema.ts — types via openapi-typescript (a plain .ts so
 *     `tsc --noEmit` fully checks it even with skipLibCheck)
 *   - src/<service>/index.ts  — thin openapi-fetch wrapper
 *     (`create<Service>Client`) + type re-exports
 *
 * Output is deterministic for a given contracts + openapi-typescript version
 * (pinned by pnpm-lock.yaml), so the drift check never flaps.
 *
 * Usage: node scripts/gen-ts-client.mjs [--contracts DIR] [--out DIR]
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { relative, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { parseArgs } from "node:util";
import openapiTS, { astToString } from "openapi-typescript";

const REPO_ROOT = resolve(new URL("..", import.meta.url).pathname);
const SERVICES = ["documents", "gateway", "geometry"];
const HEADER = "// GENERATED — do not edit; run `just gen`.";

const { values: args } = parseArgs({
  options: {
    contracts: {
      type: "string",
      default: resolve(REPO_ROOT, "packages/contracts"),
    },
    out: {
      type: "string",
      default: resolve(REPO_ROOT, "packages/ts-client/src"),
    },
  },
});

/** @param {string} service */
function indexModule(service) {
  const pascal = service[0].toUpperCase() + service.slice(1);
  return `${HEADER}
// Thin typed fetch wrapper for the ${service} service
// (source contract: packages/contracts/${service}.openapi.json).
import createClient from "openapi-fetch";
import type { ClientOptions } from "openapi-fetch";
import type { paths } from "./schema";

export type * from "./schema";

/** Create a typed openapi-fetch client for the ${service} service. */
export function create${pascal}Client(options?: ClientOptions) {
  return createClient<paths>(options);
}

export type ${pascal}Client = ReturnType<typeof create${pascal}Client>;
`;
}

for (const service of SERVICES) {
  const contract = resolve(args.contracts, `${service}.openapi.json`);
  const ast = await openapiTS(pathToFileURL(contract));
  const outDir = resolve(args.out, service);
  mkdirSync(outDir, { recursive: true });

  const schemaPath = resolve(outDir, "schema.ts");
  writeFileSync(
    schemaPath,
    `${HEADER}\n// Types for the ${service} service (source contract: packages/contracts/${service}.openapi.json).\n${astToString(ast)}`,
  );
  const indexPath = resolve(outDir, "index.ts");
  writeFileSync(indexPath, indexModule(service));
  console.log(
    `gen-ts-client: wrote ${relative(process.cwd(), schemaPath)}, ${relative(process.cwd(), indexPath)}`,
  );
}
