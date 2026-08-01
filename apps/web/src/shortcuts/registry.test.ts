/**
 * The key card cannot go stale — proved, not asserted (UI-REVIEW F4).
 *
 * A shortcut reference is a claim about what the app listens for, and a
 * hand-typed one is the "gate that cannot fail" defect in documentation form.
 * `shortcuts/registry` closes that three ways, and this file is where each of
 * them is actually held to it:
 *
 * 1. DERIVED rows — the sketch tools, constraint verbs and view snaps are read
 *    off the very tables the handlers index. Tested by adding nothing: the
 *    tests below compare the sheet against those tables, so a table edit that
 *    did not reach the sheet fails here.
 * 2. DECLARED constants — the register's `N`/`/`, grid snap, measure and the
 *    part create letters are constants the pages import. Tested by asserting
 *    the sheet prints exactly what the constants hold.
 * 3. BEHAVIOURAL pin — `V` / `⇧V` body isolation. That one needs a DOM, so it
 *    lives in `registry.test.tsx` (this repo splits vitest environments by file
 *    extension); see that file.
 */
import { describe, expect, it } from "vitest";

import {
  CONSTRAINT_SHORTCUTS,
  CONSTRUCTION_SHORTCUT,
} from "../sketch/constraints";
import { TOOL_SHORTCUTS } from "../sketch/tools";
import { VIEW_SHORTCUTS } from "../viewport/viewCommands";
import {
  KEY_FILTER,
  KEY_MEASURE,
  KEY_NEW_DOCUMENT,
  KEY_SNAP,
  PART_CREATE_SHORTCUTS,
  shortcutGroups,
} from "./registry";

/** Every `keys` string on the sheet, flattened. */
function allKeys(): string[] {
  return shortcutGroups().flatMap((group) =>
    group.shortcuts.map((shortcut) => shortcut.keys),
  );
}

function group(title: string) {
  const found = shortcutGroups().find((entry) => entry.title === title);
  if (found === undefined) throw new Error(`no group ${title}`);
  return found;
}

describe("derived rows", () => {
  it("lists every sketch tool letter, from the table the handler indexes", () => {
    const printed = group("Sketch tools").shortcuts.map((s) => s.keys);
    for (const key of Object.keys(TOOL_SHORTCUTS)) {
      expect(printed).toContain(key.toUpperCase());
    }
    // ...and names each tool, so the row says what the key does.
    const actions = group("Sketch tools").shortcuts.map((s) => s.action);
    expect(actions).toContain("Line");
    expect(actions).toContain("Chamfer");
  });

  it("lists every constraint verb and the construction toggle", () => {
    const printed = group("Sketch constraints").shortcuts.map((s) => s.keys);
    for (const key of Object.keys(CONSTRAINT_SHORTCUTS)) {
      expect(printed).toContain(key.toUpperCase());
    }
    expect(printed).toContain(CONSTRUCTION_SHORTCUT.toUpperCase());
  });

  it("lists every view snap, verbatim from VIEW_SHORTCUTS", () => {
    const printed = group("View").shortcuts.map((s) => s.keys);
    expect(printed.sort()).toEqual(Object.keys(VIEW_SHORTCUTS).sort());
  });

  it("teaches both sketch vocabularies as SEPARATE groups", () => {
    // One keyboard, two vocabularies (selection presence is the mode). A single
    // merged list would print L twice with contradictory meanings, which is
    // exactly the confusion the reference exists to remove.
    expect(group("Sketch tools").note).toMatch(/nothing selected/i);
    expect(group("Sketch constraints").note).toMatch(/selected/i);
  });
});

describe("declared constants", () => {
  it("prints the register accelerators the register itself uses", () => {
    const printed = group("Registers").shortcuts.map((s) => s.keys);
    expect(printed).toContain(KEY_NEW_DOCUMENT.toUpperCase());
    expect(printed).toContain(KEY_FILTER);
  });

  it("prints the modelling accelerators from the shared table", () => {
    const printed = group("Modelling").shortcuts.map((s) => s.keys);
    for (const entry of PART_CREATE_SHORTCUTS) {
      expect(printed).toContain(entry.keys);
    }
    expect(printed).toContain(KEY_MEASURE.toUpperCase());
    expect(group("Sketch tools").shortcuts.map((s) => s.keys)).toContain(
      KEY_SNAP.toUpperCase(),
    );
  });

  it("has no duplicate key WITHIN a group", () => {
    // Across groups a letter may legitimately mean two things (L draws a line
    // and constrains perpendicular); within one group it may not, or the sheet
    // is teaching an ambiguity that does not exist.
    for (const entry of shortcutGroups()) {
      const keys = entry.shortcuts.map((s) => s.keys);
      expect(new Set(keys).size, `duplicate in ${entry.title}`).toBe(
        keys.length,
      );
    }
  });

  it("names an action for every row", () => {
    expect(allKeys().length).toBeGreaterThan(20);
    for (const entry of shortcutGroups()) {
      for (const shortcut of entry.shortcuts) {
        expect(shortcut.action.trim()).not.toBe("");
      }
    }
  });
});
