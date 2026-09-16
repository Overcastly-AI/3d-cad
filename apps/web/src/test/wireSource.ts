/**
 * PYTHON SOURCE READ BY WEB DRIFT GUARDS, LOCATED IN ONE PLACE.
 *
 * Several web unit tests are real drift guards: they parse a constant out of
 * the Python module the TypeScript copy mirrors (`BODY_AFFECTING_FEATURE_TYPES`,
 * the hem-radius ratios, the kernel's ISO pitch table, the kernel's reflectable
 * feature set) so a change made on the Python side and missed on this side
 * fails in CI rather than in front of a user. Those constants are NOT wire
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
 * inside a test — {@link readRepoSource} throws a message that names the file,
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
 *
 * ## Why the generic {@link readRepoSource} exists alongside the wire helper
 *
 * `6ffdcda` fixed the two wire guards and wrote the rule down, but the rule
 * was enforced by nothing and two guards reading KERNEL modules — not wire
 * schemas — kept the old shape. `thread.test.ts` read
 * `services/geometry/src/geometry/kernel/threads.py` at describe-body scope,
 * so moving that file would have taken all **14** of that file's tests out at
 * collection, 11 of which never touch Python, while its own docstring claimed
 * it would "fail loudly rather than silently stop guarding anything".
 * `readWireModule` was the wrong entry point for them — a kernel module is not
 * a wire schema and giving it wire-schema failure text would send the next
 * mover to the wrong directory — so the lazy-read-plus-legible-failure part is
 * hoisted here and the wire helper is now one thin caller of it.
 */
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/** Repository root, derived from this file rather than from a cwd guess. */
const REPO_ROOT = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../..",
);

/** What a caller must tell {@link readRepoSource} so its failure is actionable. */
export interface RepoSourceOptions {
  /**
   * Where the file lived before it last moved, if known. Turns "no such file"
   * into "it moved, and here is which direction" — see the module note on the
   * two spellings of `py_kit.schemas`.
   */
  formerPath?: string;
  /**
   * Where the path constant this read uses is declared, e.g.
   * `"KERNEL_THREADS in apps/web/src/features/thread.test.ts"`. REQUIRED,
   * because the person reading this failure is mid-refactor and has no reason
   * to know the guard exists; a message that does not name the file to edit
   * makes them go and find it.
   */
  declaredIn: string;
  /** One clause naming what stops being guarded, for the same reader. */
  guards: string;
}

/**
 * Read a repo source file for a drift guard, or throw a message that says what
 * to do about it.
 *
 * Call this INSIDE a test (or a lazy getter), never in a `describe` body: the
 * whole point is that a moved file fails one named assertion instead of
 * un-loading every test in the file it was guarding — including the ones that
 * have nothing to do with the read.
 */
export function readRepoSource(
  relPath: string,
  options: RepoSourceOptions,
): string {
  const path = resolve(REPO_ROOT, relPath);
  if (existsSync(path)) return readFileSync(path, "utf8");
  const { formerPath, declaredIn, guards } = options;
  const movedBack =
    formerPath !== undefined && existsSync(resolve(REPO_ROOT, formerPath));
  throw new Error(
    `drift guard: the source file "${relPath}" is not there. ` +
      (movedBack
        ? `It is at the FORMER location ${formerPath} — the move was reverted, ` +
          `so update ${declaredIn}.`
        : formerPath !== undefined
          ? `It is at neither the current nor the former location ` +
            `(${formerPath}). It moved again — update ${declaredIn}, in the ` +
            `SAME commit as the move.`
          : `It moved or was deleted — update ${declaredIn}, in the SAME ` +
            `commit as the move.`) +
      ` This guard mirrors ${guards}, so leaving it unresolved silently stops ` +
      "guarding client/server drift.",
  );
}

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
  return readRepoSource(`${WIRE_DIR}/${module}.py`, {
    formerPath: `${FORMER_WIRE_DIR}/${module}.py`,
    declaredIn: "WIRE_DIR in apps/web/src/test/wireSource.ts",
    guards: "a Python constant that no generated type carries",
  });
}
