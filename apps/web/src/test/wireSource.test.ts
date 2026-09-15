import { existsSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { readWireModule, wireModulePath } from "./wireSource";

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
