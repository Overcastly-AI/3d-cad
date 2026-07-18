import { describe, expect, it } from "vitest";

import {
  IMPORT_MAX_BYTES,
  isStepFilename,
  precheckStepFile,
  stepFeatureName,
} from "./import";

describe("isStepFilename", () => {
  it("accepts .step / .stp in any case, rejects anything else", () => {
    expect(isStepFilename("bracket.step")).toBe(true);
    expect(isStepFilename("BRACKET.STP")).toBe(true);
    expect(isStepFilename("Housing.Step")).toBe(true);
    expect(isStepFilename("model.stl")).toBe(false);
    expect(isStepFilename("notes.txt")).toBe(false);
    expect(isStepFilename("stepless")).toBe(false);
  });
});

describe("stepFeatureName", () => {
  it("uses the base name without directory or extension", () => {
    expect(stepFeatureName("bracket.step")).toBe("bracket");
    expect(stepFeatureName("/downloads/Housing-v2.stp")).toBe("Housing-v2");
    expect(stepFeatureName("C:\\parts\\Gear.STEP")).toBe("Gear");
  });

  it("falls back to the server default for blank/edge names", () => {
    expect(stepFeatureName("   .step")).toBe("Imported STEP");
    expect(stepFeatureName(".step")).toBe(".step");
  });
});

describe("precheckStepFile", () => {
  it("passes a plausible STEP file", () => {
    expect(precheckStepFile({ name: "part.step", size: 4096 })).toBeNull();
  });

  it("flags a non-STEP extension", () => {
    expect(precheckStepFile({ name: "part.stl", size: 4096 })).toContain(
      "not a STEP file",
    );
  });

  it("flags an empty file", () => {
    expect(precheckStepFile({ name: "part.step", size: 0 })).toContain("empty");
  });

  it("flags a file over the 16 MiB cap", () => {
    expect(
      precheckStepFile({ name: "part.step", size: IMPORT_MAX_BYTES + 1 }),
    ).toContain("16 MB");
    // Exactly at the cap is allowed (the server checks strictly-greater too).
    expect(
      precheckStepFile({ name: "part.step", size: IMPORT_MAX_BYTES }),
    ).toBeNull();
  });
});
