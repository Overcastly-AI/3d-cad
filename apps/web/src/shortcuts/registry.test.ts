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
import { PROJECTION_SHORTCUT, VIEW_SHORTCUTS } from "../viewport/viewCommands";
import {
  KEY_ACCEPT_PROPOSAL,
  KEY_FILTER,
  KEY_ISOLATE,
  KEY_MEASURE,
  KEY_NEW_DOCUMENT,
  KEY_SHORTCUT_SHEET,
  KEY_SNAP,
  PART_CREATE_SHORTCUTS,
  partVerbKey,
  type PartVerbId,
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

/**
 * FLOW-B2 — the five most-used verbs got the letters they had been missing.
 *
 * The table used to bind `P S L H D O I` (pattern, sweep, loft, shell, draft,
 * hole, mirror) and left sketch, extrude, revolve, fillet and chamfer with no
 * key at all, which is an exact inversion of what a hand reaches for.
 *
 * Every assertion below states the COUNT it expects as well as the property it
 * checks. A uniqueness test over an empty list passes, a "resolves each" loop
 * over an empty list passes, and both would keep passing if the table were
 * deleted — this repo's most-repeated defect is a check that cannot observe its
 * own failure mode, so the count is what makes these gates able to fail.
 */
describe("the modelling letters", () => {
  /** The five FLOW-B2 added, against the letter each is expected to hold. */
  const FLOW_B2: ReadonlyArray<readonly [PartVerbId, string]> = [
    ["sketch", "k"],
    ["extrude", "e"],
    ["revolve", "r"],
    ["fillet", "f"],
    ["chamfer", "c"],
  ];

  /** The verbs that hold a letter, ordered as the band and the sheet print them. */
  const KEYED: readonly PartVerbId[] = [
    "sketch",
    "extrude",
    "revolve",
    "sweep",
    "loft",
    "fillet",
    "chamfer",
    "pattern",
    "shell",
    "draft",
    "hole",
    "mirror",
  ];

  it("binds all five of the most-used verbs, to the letters W2 chose", () => {
    expect(PART_CREATE_SHORTCUTS).toHaveLength(KEYED.length);
    for (const [id, key] of FLOW_B2) {
      const row = PART_CREATE_SHORTCUTS.find((entry) => entry.id === id);
      expect(row, `${id} has no row`).toBeDefined();
      expect(row?.key).toBe(key);
      // The sheet prints the upper-case glyph of the SAME letter the handler
      // matches — the two halves of one row cannot drift.
      expect(row?.keys).toBe(key.toUpperCase());
    }
  });

  it("did not move a letter a hand already knows", () => {
    // §3.1's rule: a new verb ships keyless rather than displacing an existing
    // binding. These seven predate FLOW-B2 and are the thing that rule protects.
    const before: ReadonlyArray<readonly [PartVerbId, string]> = [
      ["pattern", "p"],
      ["sweep", "s"],
      ["loft", "l"],
      ["shell", "h"],
      ["draft", "d"],
      ["hole", "o"],
      ["mirror", "i"],
    ];
    expect(before).toHaveLength(7);
    for (const [id, key] of before) {
      expect(partVerbKey(id), `${id} moved`).toBe(key);
    }
  });

  it("partVerbKey resolves every keyed verb, and only from the table", () => {
    expect(KEYED).toHaveLength(12);
    const resolved = KEYED.map((id) => partVerbKey(id));
    // Non-vacuous twice over: the count, and that not one came back undefined.
    expect(resolved.filter((key) => key !== undefined)).toHaveLength(12);
    for (const id of KEYED) {
      const key = partVerbKey(id);
      expect(key, `${id} resolves to nothing`).toBeDefined();
      // It is the table's own letter, not a second copy of it.
      expect(key).toBe(PART_CREATE_SHORTCUTS.find((e) => e.id === id)?.key);
    }
  });

  it("answers undefined for a verb that deliberately has no letter", () => {
    // The branch a sibling's `partVerbKey(id) ?? '↵'` fallback depends on. If
    // `PartVerbId` only ever described keyed verbs this could not be written,
    // the fallback would be unreachable code, and the first keyless verb added
    // would be a breaking change instead of one row.
    const keyless: readonly PartVerbId[] = [
      "combine",
      "base-flange",
      "edge-flange",
      "hem",
      "corner-relief",
      "flat-pattern",
    ];
    expect(keyless).toHaveLength(6);
    for (const id of keyless) {
      expect(
        partVerbKey(id),
        `${id} unexpectedly holds a letter`,
      ).toBeUndefined();
    }
  });

  it("the lower-case key and the printed glyph agree on every row", () => {
    expect(PART_CREATE_SHORTCUTS.length).toBeGreaterThanOrEqual(12);
    for (const entry of PART_CREATE_SHORTCUTS) {
      expect(entry.key).toBe(entry.key.toLowerCase());
      expect(entry.keys).toBe(entry.key.toUpperCase());
    }
  });

  it("no two commands claim one key within the modelling mode", () => {
    // "Within one mode" is the whole question: E is Extrude here and `equal` in
    // a sketch, which is not an ambiguity because the create handler bails
    // unless `mode === "off"`. What WOULD be an ambiguity is two things
    // listening for one letter with no mode between them, so this is the set
    // that is live in a part workspace with no command open.
    const claimed = [
      ...PART_CREATE_SHORTCUTS.map((entry) => entry.key),
      KEY_MEASURE,
      KEY_ISOLATE,
      KEY_SHORTCUT_SHEET,
      KEY_ACCEPT_PROPOSAL,
      ...Object.keys(VIEW_SHORTCUTS),
      PROJECTION_SHORTCUT,
    ];
    // 12 verbs + measure + isolate + ? + Enter + 6 view snaps + the projection
    // toggle = 23. Stated, so a table that lost its rows cannot pass this by
    // being trivially unique.
    expect(claimed).toHaveLength(23);
    expect(new Set(claimed).size).toBe(claimed.length);
  });

  it("prints every letter on the sheet, in the band's own order", () => {
    const modelling = group("Modelling").shortcuts.map((s) => s.keys);
    // The five are reachable from the one surface that teaches the keyboard.
    for (const [id] of FLOW_B2) {
      const key = partVerbKey(id);
      expect(key).toBeDefined();
      expect(modelling, `${id} is not on the sheet`).toContain(
        (key as string).toUpperCase(),
      );
    }
    // ...and the create rows lead, in band order, so the reference and the
    // toolbar are one layout rather than two.
    expect(modelling.slice(0, KEYED.length)).toEqual(
      KEYED.map((id) => (partVerbKey(id) as string).toUpperCase()),
    );
  });

  it("says what each of the five does, in the band's own words", () => {
    // The sheet's `action` is the vocabulary the user already met on the tool
    // button; a reference that renamed the verb would teach a second name for
    // one thing.
    const actions = new Map(
      PART_CREATE_SHORTCUTS.map((entry) => [entry.id, entry.action]),
    );
    expect(actions.size).toBe(12);
    expect(actions.get("sketch")).toBe("Sketch");
    expect(actions.get("extrude")).toBe("Extrude");
    expect(actions.get("revolve")).toBe("Revolve");
    expect(actions.get("fillet")).toBe("Fillet");
    expect(actions.get("chamfer")).toBe("Chamfer");
  });
});
