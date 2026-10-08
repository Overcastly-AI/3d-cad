import { afterEach, describe, expect, it } from "vitest";

import {
  LOFT_IMPORT_MAX_BYTES,
  precheckLoftFile,
  useLoftImportNotice,
} from "./loftImport";

describe("precheckLoftFile", () => {
  it("accepts a .loft of any case", () => {
    expect(precheckLoftFile({ name: "Bracket.LOFT", size: 10 })).toBeNull();
  });

  it("refuses another suffix, an empty file and one over the cap", () => {
    expect(precheckLoftFile({ name: "bracket.step", size: 10 })).toMatch(
      /not a Loft file/,
    );
    expect(precheckLoftFile({ name: "bracket.loft", size: 0 })).toMatch(
      /empty/,
    );
    expect(
      precheckLoftFile({ name: "b.loft", size: LOFT_IMPORT_MAX_BYTES + 1 }),
    ).toMatch(/64 MB/);
  });
});

describe("useLoftImportNotice", () => {
  afterEach(() => useLoftImportNotice.getState().dismiss());

  it("holds the warnings for the part they describe until dismissed", () => {
    useLoftImportNotice
      .getState()
      .show("p2", [{ code: "loft_volume_mismatch", message: "differs" }]);
    expect(useLoftImportNotice.getState().partId).toBe("p2");
    useLoftImportNotice.getState().dismiss();
    expect(useLoftImportNotice.getState().warnings).toEqual([]);
  });
});
