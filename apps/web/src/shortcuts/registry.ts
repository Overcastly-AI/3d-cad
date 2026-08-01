import {
  CONSTRAINT_SHORTCUTS,
  CONSTRUCTION_SHORTCUT,
} from "../sketch/constraints";
import { TOOL_SHORTCUTS } from "../sketch/tools";
import { VIEW_SHORTCUTS } from "../viewport/viewCommands";

/**
 * THE keyboard reference (UI-REVIEW 2026-07-30 F4) — and the source the
 * handlers read.
 *
 * The finding was that this app trains shortcuts in button captions, calls
 * itself keyboard-first in its design docs, and gives a user nowhere to learn
 * the keyboard. The obvious fix — a hand-typed help panel — is this repo's
 * "gate that cannot fail" defect in documentation form: it would be correct on
 * the day it shipped and silently wrong on the day someone changed a binding.
 * So the sheet is DERIVED, by two mechanisms, and every binding on it is
 * covered by one of them:
 *
 * 1. **Derived from the table the handler indexes.** The sketch tool letters,
 *    the constraint verbs, the construction toggle and the view snaps are
 *    already single-source tables (`TOOL_SHORTCUTS`, `CONSTRAINT_SHORTCUTS`,
 *    `CONSTRUCTION_SHORTCUT`, `VIEW_SHORTCUTS`). This module reads THOSE, so
 *    adding a tool adds a row and re-keying one re-keys the row. There is no
 *    second list to forget.
 *
 * 2. **Declared here and read by the handler.** Everything the pages used to
 *    compare against an inline string literal — the create/modify letters,
 *    measure, grid snap, the register's `N` and `/` — is a constant in this
 *    file, and the page imports it. The sheet and the handler are then the same
 *    fact by construction.
 *
 * ...and where a handler is out of this slice's reach (`V`/`⇧V` body isolation
 * lives in `viewport/partView.ts`, held by a concurrent agent), the binding is
 * declared here and pinned by a BEHAVIOURAL test instead: `registry.test.ts`
 * drives the real hook with the key THIS FILE declares and asserts the store
 * changed. That is a stronger guarantee than a shared constant, not a weaker
 * one — it proves the key works, rather than proving two files agree about a
 * string. Anything added here without one of the three is a regression.
 *
 * The sheet is the ONLY consumer that renders all of this; the pages consume
 * the individual constants. Nothing in this module knows how it will be drawn.
 */

/** One binding, as the sheet prints it and as a page may check it. */
export interface Shortcut {
  /** Authored in the Windows/Linux vocabulary; `formatChord` re-teaches Mac. */
  keys: string;
  /** What it does, in the interface's own vocabulary ("Trim", not "trimTool"). */
  action: string;
  /**
   * When it is live, when that is not obvious from the group ("with a
   * selection", "needs a body"). Omitted where the group already says it —
   * a qualifier on every row is noise that stops being read.
   */
  when?: string;
}

/** A titled block of bindings — one surface's vocabulary. */
export interface ShortcutGroup {
  /** The surface: "Everywhere", "Sketching"… */
  title: string;
  /** One sentence on when this group applies, or null when it always does. */
  note: string | null;
  shortcuts: Shortcut[];
}

// --- (2) constants the HANDLERS import ------------------------------------------
//
// Each of these is compared against `event.key.toLowerCase()` (or `event.key`
// for the named keys) by exactly one handler, which imports it from here.

/** Focus the register's create field — `ScribeLine`, every register. */
export const KEY_NEW_DOCUMENT = "n";
/** Focus the register's filter field — `FilterField`, every register. */
export const KEY_FILTER = "/";
/** Open THIS reference. `?` is the convention; the shift is implicit in the glyph. */
export const KEY_SHORTCUT_SHEET = "?";
/** Toggle grid snap while sketching — `PartPage`'s sketch cascade. */
export const KEY_SNAP = "g";
/** Arm the measure tool — `PartPage`. */
export const KEY_MEASURE = "m";

/**
 * The part workspace's create/modify accelerators, each with the condition the
 * handler ALSO enforces. Written as a table so the sheet cannot list a verb the
 * keyboard does not fire, and so a new verb is one entry rather than two edits.
 */
export const PART_CREATE_SHORTCUTS: readonly (Shortcut & { key: string })[] = [
  { key: "p", keys: "P", action: "Pattern", when: "needs a body" },
  { key: "s", keys: "S", action: "Sweep", when: "needs a profile and a path" },
  { key: "l", keys: "L", action: "Loft", when: "needs two profiles" },
  { key: "h", keys: "H", action: "Shell", when: "needs a body" },
  { key: "d", keys: "D", action: "Draft", when: "needs a body" },
  { key: "o", keys: "O", action: "Hole", when: "needs a body" },
  { key: "i", keys: "I", action: "Mirror", when: "needs a body" },
];

/**
 * Body isolation — the one binding whose handler this slice may not edit
 * (`viewport/partView.ts`, a concurrent agent's territory). Declared here and
 * pinned by the behavioural test described in the module docstring.
 */
export const KEY_ISOLATE = "v";

// --- (1) rows DERIVED from the tables the handlers index -------------------------

/** Title Case for a tool/constraint name the tables hold as an identifier. */
function label(name: string): string {
  const spaced = name.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** Sketch draw/modify tools, straight off `TOOL_SHORTCUTS`. */
function toolShortcuts(): Shortcut[] {
  return Object.entries(TOOL_SHORTCUTS).map(([key, tool]) => ({
    keys: key.toUpperCase(),
    action: label(tool),
  }));
}

/** Constraint verbs, straight off `CONSTRAINT_SHORTCUTS`. */
function constraintShortcuts(): Shortcut[] {
  return Object.entries(CONSTRAINT_SHORTCUTS).map(([key, action]) => ({
    keys: key.toUpperCase(),
    action: label(action),
  }));
}

/** View snaps, straight off `VIEW_SHORTCUTS` (the view rail's own table). */
function viewShortcuts(): Shortcut[] {
  return Object.entries(VIEW_SHORTCUTS).map(([key, kind]) => ({
    keys: key,
    action:
      kind === "fit"
        ? "Fit to the model"
        : kind === "home"
          ? "Home view"
          : `${label(kind)} view`,
  }));
}

/**
 * The whole reference, in the order a user meets it: what works everywhere,
 * then the register, then the workspace, then the two modal vocabularies.
 *
 * A FUNCTION, not a constant, because the derived halves read module tables at
 * call time — the sheet therefore cannot be built from a snapshot taken before
 * a table was edited, and a test can assert the derivation rather than a copy.
 */
export function shortcutGroups(): ShortcutGroup[] {
  return [
    {
      title: "Everywhere",
      note: null,
      shortcuts: [
        { keys: "?", action: "Show this reference" },
        {
          keys: "Esc",
          action: "Back out one step",
          when: "closes, then exits",
        },
        { keys: "Ctrl+Z", action: "Undo" },
        { keys: "Ctrl+Shift+Z", action: "Redo" },
      ],
    },
    {
      title: "Registers",
      note: "The parts, assemblies and drawings drawers.",
      shortcuts: [
        { keys: KEY_NEW_DOCUMENT.toUpperCase(), action: "Name a new document" },
        { keys: KEY_FILTER, action: "Filter by name" },
        {
          keys: "Esc",
          action: "Clear the filter",
          when: "in the filter field",
        },
      ],
    },
    {
      title: "Modelling",
      note: "In a part workspace, with no command open.",
      shortcuts: [
        ...PART_CREATE_SHORTCUTS.map(({ keys, action, when }) => ({
          keys,
          action,
          when,
        })),
        { keys: KEY_MEASURE.toUpperCase(), action: "Measure" },
        {
          keys: KEY_ISOLATE.toUpperCase(),
          action: "Hide or show the addressed body",
        },
        {
          keys: `Shift+${KEY_ISOLATE.toUpperCase()}`,
          action: "Isolate it — or show everything again",
        },
      ],
    },
    {
      title: "View",
      note: "Whenever the camera is yours (not while sketching).",
      shortcuts: viewShortcuts(),
    },
    {
      title: "Sketch tools",
      note: "In a sketch, with nothing selected.",
      shortcuts: [
        ...toolShortcuts(),
        { keys: KEY_SNAP.toUpperCase(), action: "Grid snap on or off" },
        { keys: "Ctrl", action: "Hold to suppress snapping" },
        { keys: "Shift", action: "Hold to lock to an axis" },
      ],
    },
    {
      title: "Sketch constraints",
      note: "The SAME letters, once something is selected.",
      shortcuts: [
        ...constraintShortcuts(),
        {
          keys: CONSTRUCTION_SHORTCUT.toUpperCase(),
          action: "Construction geometry on or off",
        },
      ],
    },
  ];
}
