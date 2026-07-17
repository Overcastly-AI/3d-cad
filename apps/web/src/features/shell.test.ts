import { describe, expect, it } from "vitest";

import type { PlanarFaceSignature, ShellParams } from "../api/parts";
import { faceSubshapeRef } from "./face";
import {
  buildShellParams,
  canSubmitShell,
  defaultShellForm,
  facesSelector,
  formFromShellParams,
  parseThicknessMm,
  pickedFacesFromShellParams,
  type ShellForm,
  thicknessError,
} from "./shell";

const TOP: PlanarFaceSignature = {
  normal: { x: 0, y: 0, z: 1 },
  centroid: { x: 10, y: 10, z: 20 },
  area_mm2: 400,
  subshape_type: "face",
  surface: "plane",
};
const BOTTOM: PlanarFaceSignature = {
  normal: { x: 0, y: 0, z: -1 },
  centroid: { x: 10, y: 10, z: 0 },
  area_mm2: 400,
  subshape_type: "face",
  surface: "plane",
};

describe("parseThicknessMm", () => {
  it("parses a positive number", () => {
    expect(parseThicknessMm("2", "mm")).toBe(2);
    expect(parseThicknessMm(" 1.5 ", "mm")).toBe(1.5);
  });

  it("converts through the document unit", () => {
    expect(parseThicknessMm("2", "in")).toBe(50.8);
    expect(parseThicknessMm("2in", "mm")).toBe(50.8);
  });

  it("rejects empty, non-numeric, zero, and negative", () => {
    expect(parseThicknessMm("", "mm")).toBeNull();
    expect(parseThicknessMm("abc", "mm")).toBeNull();
    expect(parseThicknessMm("0", "mm")).toBeNull();
    expect(parseThicknessMm("-3", "mm")).toBeNull();
  });
});

describe("thicknessError", () => {
  it("is null while empty (pending) and for a valid value", () => {
    expect(thicknessError("", "mm")).toBeNull();
    expect(thicknessError("2", "mm")).toBeNull();
  });

  it("messages an invalid value", () => {
    expect(thicknessError("0", "mm")).toBe(
      "Thickness must be a positive length.",
    );
  });
});

describe("facesSelector", () => {
  it("builds a sealed hollow (empty refs) with no picks — anchor irrelevant", () => {
    expect(facesSelector(null, [])).toEqual({ kind: "faces", refs: [] });
    expect(facesSelector("feat-1", [])).toEqual({ kind: "faces", refs: [] });
  });

  it("opens the picked faces, anchored on the body feature", () => {
    expect(facesSelector("feat-1", [TOP, BOTTOM])).toEqual({
      kind: "faces",
      refs: [faceSubshapeRef("feat-1", TOP), faceSubshapeRef("feat-1", BOTTOM)],
    });
  });

  it("is null when faces are picked but there is no body anchor", () => {
    expect(facesSelector(null, [TOP])).toBeNull();
  });
});

describe("buildShellParams", () => {
  const form: ShellForm = { thicknessInput: "2" };

  it("builds a sealed hollow from thickness alone (no picks)", () => {
    expect(buildShellParams(form, [], "feat-1", "mm")).toEqual({
      thickness_mm: 2,
      faces: { kind: "faces", refs: [] },
    });
  });

  it("builds an open-face shell from the picked faces", () => {
    const params = buildShellParams(form, [TOP], "feat-1", "mm");
    expect(params).toEqual({
      thickness_mm: 2,
      faces: { kind: "faces", refs: [faceSubshapeRef("feat-1", TOP)] },
    });
  });

  it("converts the thickness through the document unit", () => {
    expect(buildShellParams(form, [], "feat-1", "in")?.thickness_mm).toBe(50.8);
  });

  it("is null for an invalid thickness", () => {
    expect(
      buildShellParams({ thicknessInput: "0" }, [], "feat-1", "mm"),
    ).toBeNull();
  });

  it("is null when faces are picked without a body anchor", () => {
    expect(buildShellParams(form, [TOP], null, "mm")).toBeNull();
  });
});

describe("canSubmitShell", () => {
  it("allows a valid thickness with zero picks (sealed hollow)", () => {
    expect(canSubmitShell({ thicknessInput: "2" }, [], "feat-1", "mm")).toBe(
      true,
    );
  });

  it("blocks an invalid thickness", () => {
    expect(canSubmitShell({ thicknessInput: "" }, [], "feat-1", "mm")).toBe(
      false,
    );
  });
});

describe("defaultShellForm", () => {
  it("seeds a 2 mm wall", () => {
    expect(defaultShellForm()).toEqual({ thicknessInput: "2" });
  });
});

describe("formFromShellParams / pickedFacesFromShellParams", () => {
  const sealed: ShellParams = {
    thickness_mm: 3,
    faces: { kind: "faces", refs: [] },
  };
  const open: ShellParams = {
    thickness_mm: 2.5,
    faces: { kind: "faces", refs: [faceSubshapeRef("feat-1", TOP)] },
  };

  it("seeds the form thickness as trimmed text", () => {
    expect(formFromShellParams(sealed, "mm")).toEqual({ thicknessInput: "3" });
    expect(formFromShellParams(open, "mm")).toEqual({ thicknessInput: "2.5" });
  });

  it("seeds no picked faces from a sealed shell", () => {
    expect(pickedFacesFromShellParams(sealed)).toEqual([]);
  });

  it("seeds the picked-open signatures from an open shell", () => {
    expect(pickedFacesFromShellParams(open)).toEqual([TOP]);
  });

  it("treats a missing refs list as a sealed hollow", () => {
    const noRefs = {
      thickness_mm: 2,
      faces: { kind: "faces" },
    } as unknown as ShellParams;
    expect(pickedFacesFromShellParams(noRefs)).toEqual([]);
  });
});
