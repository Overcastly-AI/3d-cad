/**
 * THE PYTHON WIRE SCHEMAS, LOCATED IN ONE PLACE, FOR THE DRIFT GUARDS THAT READ
 * THEM.
 *
 * Several web unit tests are real drift guards: they parse a constant out of
 * the pydantic module the TypeScript copy mirrors (`BODY_AFFECTING_FEATURE_TYPES`,
 * the hem-radius ratios) so a change made on the Python side and missed on this
 * side fails in CI rather than in front of a user. Those constants are NOT wire
 * fields — they are semantic subsets and module-level numbers — so the generated
 * client carries no value to read and parsing the source is the only honest
 * oracle available.
 *
 * ## Why this module exists, and the shape of the failure it removes
 *
 * The path used to be written out at each call site. `14f6e14` ("the wire types
 * get their own distribution") moved the schemas from
 * `packages/py-kit/src/py_kit/schemas/` to `packages/loft-wire/src/loft_wire/`,
 * and both guards then threw inside their `describe` body — i.e. at COLLECTION.
 * The files never loaded, so the suite reported **2516 passing and exit 1**,
 * with no assertion anywhere naming the cause.
 *
 * That is the least useful shape a drift guard can take: when the thing it
 * guards moves, it stops guarding AND stops explaining, in the same instant,
 * and what it leaves behind looks like an infrastructure problem rather than a
 * stale reference. So the read is LAZY and the failure is an ordinary assertion
 * inside a test — {@link readWireModule} throws a message that names the module,
 * the path it tried, the path it used to be at, and the one-line fix.
 *
 * ## Why it also knows the OLD location
 *
 * The refactor's own fallout audit searched for `py_kit.schemas` — the module
 * path, with dots — while these guards spelled it `py-kit/src/py_kit/schemas`,
 * the filesystem path, with a hyphen. Same identifier, two spellings, and a
 * literal search can only ever see the one it was typed with. Recording the
 * previous location here turns that class of miss into a sentence the next
 * mover reads in the failure output, instead of a silent gap in a grep.
 */
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/** Repository root, derived from this file rather than from a cwd guess. */
const REPO_ROOT = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../..",
);

/** Where the wire schemas live now. One spelling, one place. */
const WIRE_DIR = "packages/loft-wire/src/loft_wire";

/**
 * Where they lived before `14f6e14`. Kept so a guard that cannot find its
 * module can say "it moved" rather than "no such file" — see the module note.
 */
const FORMER_WIRE_DIR = "packages/py-kit/src/py_kit/schemas";

/** Absolute path of a wire schema module, e.g. `wireModulePath("features")`. */
export function wireModulePath(module: string): string {
  return resolve(REPO_ROOT, WIRE_DIR, `${module}.py`);
}

/**
 * Read a wire schema module's source, or throw a message that says what to do.
 *
 * Call this INSIDE a test (or a lazy getter), never in a `describe` body: the
 * whole point is that a moved module fails one named assertion instead of
 * un-loading the file it was guarding.
 */
export function readWireModule(module: string): string {
  const path = wireModulePath(module);
  if (existsSync(path)) return readFileSync(path, "utf8");
  const former = resolve(REPO_ROOT, FORMER_WIRE_DIR, `${module}.py`);
  const movedBack = existsSync(former);
  throw new Error(
    `drift guard: the wire schema module "${module}" is not at ${WIRE_DIR}/${module}.py. ` +
      (movedBack
        ? `It is at the FORMER location ${FORMER_WIRE_DIR}/${module}.py — ` +
          "the move was reverted, so update WIRE_DIR in apps/web/src/test/wireSource.ts."
        : "It is at neither the current nor the former location " +
          `(${FORMER_WIRE_DIR}/${module}.py). It moved again — update WIRE_DIR in ` +
          "apps/web/src/test/wireSource.ts, in the SAME commit as the move.") +
      " This guard mirrors a Python constant that no generated type carries, so " +
      "leaving it unresolved silently stops guarding client/server drift.",
  );
}
