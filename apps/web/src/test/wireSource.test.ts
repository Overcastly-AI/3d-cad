import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { readRepoSource, readWireModule, wireModulePath } from "./wireSource";

/**
 * THE GUARD'S OWN GUARD.
 *
 * `wireSource.ts` exists because two drift guards died at COLLECTION when the
 * Python schemas moved — no assertion, no message, just a file that would not
 * load and a suite that exited 1 with everything green. The fix is only worth
 * anything if its failure is legible, and an assertion nobody has watched fail
 * is not yet a gate, so the negative control below asks for a module that
 * cannot exist and reads what comes back.
 *
 * It deliberately does NOT assert on the exit code or on `toThrow()` alone:
 * "it threw" was already true of the broken version. What was missing is the
 * SENTENCE, so that is what is asserted.
 */
describe("wireSource — where the Python wire schemas live", () => {
  it("resolves a module that really is there", () => {
    const path = wireModulePath("features");
    expect(path).toContain("packages/loft-wire/src/loft_wire/features.py");
    expect(existsSync(path), `${path} does not exist`).toBe(true);
  });

  it("hands back the real source, not an empty string", () => {
    // A zero-byte read would make every `toContain` downstream vacuously
    // false and every parse silently empty — the failure shape this repo has
    // paid for more than once. Assert on size AND on a landmark.
    const source = readWireModule("features");
    expect(source.length).toBeGreaterThan(10_000);
    expect(source).toContain("BODY_AFFECTING_FEATURE_TYPES = frozenset(");
  });

  it("a module that has moved fails with a sentence that says what to do", () => {
    // The negative control. `no_such_module` stands in for "the schemas moved
    // again": the guard must name the module, the directory it expected, and
    // the file to edit — because the person reading this failure is mid-refactor
    // and has no reason to know this guard exists.
    let message = "";
    try {
      readWireModule("no_such_module");
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toContain("no_such_module");
    expect(message).toContain("packages/loft-wire/src/loft_wire");
    expect(message).toContain("apps/web/src/test/wireSource.ts");
    // It also says where the schemas USED to live, because the fallout audit
    // for the real move searched `py_kit.schemas` (dots) while the guards spelt
    // it `py-kit/src/py_kit/schemas` (slashes) — one identifier, two spellings,
    // and a literal grep can only see the one it was typed with. Carrying the
    // former location in the failure is how that miss becomes a sentence
    // somebody reads instead of a hole in a search.
    expect(message).toContain("py_kit/schemas");
  });
});

describe("readRepoSource — the generic lazy read", () => {
  it("hands back a real file that is not a wire schema", () => {
    // The reason this helper exists: the two guards that kept the broken shape
    // read KERNEL modules, and `readWireModule` is the wrong entry point for
    // them — its failure text would send the next mover to the wire directory.
    const source = readRepoSource(
      "services/geometry/src/geometry/kernel/threads.py",
      { declaredIn: "this test", guards: "nothing — positive control" },
    );
    expect(source.length).toBeGreaterThan(1_000);
    expect(source).toContain("ISO_METRIC_PITCHES");
  });

  it("names the file, the fix site and the stakes when it cannot read", () => {
    // The negative control. `toThrow()` alone would have passed against the
    // BROKEN version too — a describe-body `readFileSync` also throws. What
    // was missing is the SENTENCE, so the sentence is what is asserted.
    let message = "";
    try {
      readRepoSource("services/geometry/src/geometry/kernel/nope.py", {
        declaredIn: "KERNEL_THREADS in apps/web/src/features/thread.test.ts",
        guards: "the kernel's ISO metric pitch table",
      });
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toContain("kernel/nope.py");
    expect(message).toContain("thread.test.ts");
    expect(message).toContain("ISO metric pitch table");
    expect(message).toContain("SAME commit as the move");
  });

  it("distinguishes a REVERTED move from a further one", () => {
    // The mirror. The `formerPath` branch has two directions and a guard
    // written against one tends to encode that one's direction, so both are
    // exercised: a former path that EXISTS means the move was reverted and the
    // reader should put the constant back; one that does not means it moved
    // again. Getting these the wrong way round sends the reader to a directory
    // that is empty.
    const call = (formerPath: string): string => {
      try {
        readRepoSource("packages/loft-wire/src/loft_wire/gone.py", {
          formerPath,
          declaredIn: "WIRE_DIR in apps/web/src/test/wireSource.ts",
          guards: "a Python constant",
        });
      } catch (error) {
        return (error as Error).message;
      }
      throw new Error("readRepoSource must throw for a file that is not there");
    };

    // A former path that really exists -> "the move was reverted".
    const reverted = call("packages/loft-wire/src/loft_wire/features.py");
    expect(reverted).toContain("FORMER location");
    expect(reverted).toContain("the move was reverted");
    expect(reverted).not.toContain("moved again");

    // A former path that does not -> "it moved again".
    const movedAgain = call("packages/py-kit/src/py_kit/schemas/gone.py");
    expect(movedAgain).toContain("moved again");
    expect(movedAgain).not.toContain("the move was reverted");
  });
});

/**
 * THE RULE, ENFORCED RATHER THAN WRITTEN DOWN.
 *
 * `6ffdcda` fixed two describe-body reads and wrote "call this INSIDE a test,
 * never in a `describe` body" into `wireSource.ts`. Nothing graded it, so two
 * more guards kept the old shape until a reviewer went looking —
 * `thread.test.ts` read a kernel module at describe-body scope, which takes all
 * 14 of that file's tests out at COLLECTION when the module moves, 11 of them
 * for no reason.
 *
 * ## What this checks, stated exactly
 *
 * Every read that reaches OUTSIDE `apps/web` must go through this module. The
 * mechanism a bypass needs is a repo-escaping path literal (four `..` segments,
 * assembled below rather than spelled out), which both offenders used and which
 * nothing else under `apps/web/src` has any business containing. That is a
 * textual property with no scope analysis and no heuristic in it, so it cannot
 * cry wolf — and a gate that cries wolf gets muted.
 *
 * ## What it does NOT check, stated because an unstated gap gets trusted
 *
 * It does not prove the read is LAZY. A caller could still write
 * `const s = readRepoSource(...)` in a `describe` body and this would pass.
 * Deciding that lexically means telling a `describe` callback from an
 * expression-bodied arrow (`const source = () => readWireModule("features")`,
 * the idiom `face.test.ts` uses and which IS lazy), and an indentation or
 * brace-stack approximation of that produces false positives on legitimate
 * code. What this gate does buy is that the bypass ROUTE is closed: a new
 * cross-language guard has to come through `readRepoSource`, whose doc comment
 * and failure text both say lazy.
 */
describe("no drift guard reaches outside apps/web on its own", () => {
  const WEB_SRC = resolve(dirname(fileURLToPath(import.meta.url)), "..");
  /**
   * Assembled rather than written out, so THIS file does not contain the
   * literal it forbids. The alternative — exempting the gate's own path —
   * would also exempt a real violation that happened to live here, and a
   * self-exemption is the cheapest way for a gate to stop seeing itself.
   */
  const REPO_ESCAPE = ["..", "..", "..", ".."].join("/");
  /** This module owns repo-root resolution; it is the one legitimate holder. */
  const OWNER = "test/wireSource.ts";

  const sourceFiles = (dir: string, out: string[] = []): string[] => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "node_modules" || entry.name === "__fixtures__") {
          continue;
        }
        sourceFiles(path, out);
      } else if (/\.(ts|tsx)$/.test(entry.name)) {
        out.push(path);
      }
    }
    return out;
  };

  it("routes every repo-escaping read through wireSource.ts", () => {
    const files = sourceFiles(WEB_SRC);
    // Non-vacuity: a walk that found nothing would make the assertion below
    // vacuously true, which is the failure shape this repo keeps paying for.
    // 276 files at the time of writing; the floor is a collapse detector.
    expect(files.length).toBeGreaterThan(200);

    const holders = files
      .filter((file) => readFileSync(file, "utf8").includes(REPO_ESCAPE))
      .map((file) => relative(WEB_SRC, file).split("\\").join("/"));

    // A POSITIVE control lives inside the assertion: the owner must still be
    // found. If the walk silently stopped reading, or the literal changed
    // shape, `holders` would come back empty and a `toEqual([])`-style
    // assertion would pass while checking nothing at all.
    expect(holders).toEqual([OWNER]);
  });
});
