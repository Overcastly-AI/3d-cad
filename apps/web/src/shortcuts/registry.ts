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
/**
 * Open the file picker on a register that accepts one — `AssembliesPage`.
 *
 * `f4c590b` deliberately kept this out of the registry ("one register, extract
 * on the second use"), and the reasoning was sound about the CONSTANT. It was
 * wrong about the SHEET: this file is the only place the app teaches the
 * keyboard, so a binding declared elsewhere is a binding nobody can find unless
 * they are already standing on the page that has it (UI-REVIEW 2026-08-27
 * P3-B) — and P1-A in the same pass is precisely that they may not be. The row
 * carries a `when`, which is how the sheet already handles bindings that are
 * live on some surfaces and not others.
 */
export const KEY_IMPORT = "i";
/** Open THIS reference. `?` is the convention; the shift is implicit in the glyph. */
export const KEY_SHORTCUT_SHEET = "?";
/** Toggle grid snap while sketching — `PartPage`'s sketch cascade. */
export const KEY_SNAP = "g";
/** Arm the measure tool — `PartPage`. */
export const KEY_MEASURE = "m";
/**
 * Accept the sketch proposal the viewport is offering — `SketchProposal`.
 *
 * `Enter` rather than a letter, for two reasons. Every bare letter in this
 * workspace is already a create verb (the table below), and more importantly
 * the binding is not "start a sketch": it ACCEPTS a specific proposal that is
 * on screen at that moment, naming a specific face. Accept is what Enter means
 * everywhere else in the product, and a proposal that could be committed by
 * some other key would be teaching a second accept vocabulary for one surface.
 *
 * It is live ONLY while the note is showing, which is why the chip prints the
 * glyph itself: the fastest way to teach a keyboard path is to put it on the
 * thing the mouse is already pointing at.
 */
export const KEY_ACCEPT_PROPOSAL = "Enter";

/**
 * Every verb the command band names with a `new-<id>` test id — the id half of
 * that vocabulary, so a verb is one word in the handler, the chip, the tooltip
 * and the sheet rather than four spellings of itself.
 *
 * It deliberately includes the verbs that have NO letter (combine and the sheet
 * metal group). That is what makes `partVerbKey`'s `undefined` a real answer
 * instead of a branch nothing can reach: §3.1 of the W2 direction rules that a
 * new verb "ships without a letter and gets filed" rather than displacing one a
 * hand already knows, and a type that could only describe keyed verbs would make
 * that rule unrepresentable.
 */
export type PartVerbId =
  // keyed, in the band's own left-to-right order
  | "sketch"
  | "extrude"
  | "revolve"
  | "sweep"
  | "loft"
  | "fillet"
  | "chamfer"
  | "pattern"
  | "shell"
  | "draft"
  | "hole"
  | "mirror"
  // keyless today — present so the absence is sayable
  | "combine"
  | "base-flange"
  | "edge-flange"
  | "hem"
  | "corner-relief"
  | "flat-pattern";

/**
 * The part workspace's create/modify accelerators, each with the condition the
 * handler ALSO enforces. Written as a table so the sheet cannot list a verb the
 * keyboard does not fire, and so a new verb is one entry rather than two edits.
 *
 * ROW ORDER IS THE BAND'S ORDER (Create left-to-right, then Modify), because the
 * sheet prints the rows in this order and a reference that lists verbs in a
 * different sequence from the toolbar makes the reader translate between two
 * layouts of one vocabulary. Nothing here is alphabetical; the order is a fact
 * about where the tool sits.
 *
 * FLOW-B2: the five most-used verbs — sketch, extrude, revolve, fillet, chamfer
 * — had no letter at all while pattern, sweep, loft, shell, draft, hole and
 * mirror did, which is an exact inversion of what a hand reaches for. The five
 * new letters are `K E R F C`; every pre-existing letter keeps its verb (a moved
 * shortcut is worse than a missing one), which is why Sketch is `K` and not the
 * `S` that Sweep has held since it shipped.
 *
 * `E R F C K` collide with the sketch tool/constraint letters and that is NOT an
 * ambiguity: the create handler bails unless `mode === "off"` and the sketch
 * vocabulary is only consulted inside a sketch, so mode resolves it before the
 * key is ever read. The two vocabularies are printed as separate groups below
 * for the same reason.
 */
export const PART_CREATE_SHORTCUTS: readonly (Shortcut & {
  key: string;
  id: PartVerbId;
})[] = [
  { id: "sketch", key: "k", keys: "K", action: "Sketch" },
  {
    id: "extrude",
    key: "e",
    keys: "E",
    action: "Extrude",
    when: "needs a solved sketch",
  },
  {
    id: "revolve",
    key: "r",
    keys: "R",
    action: "Revolve",
    when: "needs a solved sketch",
  },
  {
    id: "sweep",
    key: "s",
    keys: "S",
    action: "Sweep",
    when: "needs a profile and a path",
  },
  {
    id: "loft",
    key: "l",
    keys: "L",
    action: "Loft",
    when: "needs two profiles",
  },
  { id: "fillet", key: "f", keys: "F", action: "Fillet", when: "needs a body" },
  {
    id: "chamfer",
    key: "c",
    keys: "C",
    action: "Chamfer",
    when: "needs a body",
  },
  {
    id: "pattern",
    key: "p",
    keys: "P",
    action: "Pattern",
    when: "needs a body",
  },
  { id: "shell", key: "h", keys: "H", action: "Shell", when: "needs a body" },
  { id: "draft", key: "d", keys: "D", action: "Draft", when: "needs a body" },
  { id: "hole", key: "o", keys: "O", action: "Hole", when: "needs a body" },
  { id: "mirror", key: "i", keys: "I", action: "Mirror", when: "needs a body" },
];

/**
 * The letter a part-workspace verb answers to, or `undefined` where it has none.
 *
 * THE point of this accessor is that no other module may hardcode a letter. The
 * viewport's proposal chip prints `partVerbKey("extrude")` on its `Kbd`, the
 * band's `ToolButton`s pass it as their `shortcut`, and the sheet derives its
 * rows from the same table — so a re-keyed verb re-keys every surface that
 * teaches it, and a letter can never be taught that nothing listens for. A chip
 * printing a hardcoded key is the "gate that cannot fail" defect wearing a
 * `Kbd`: correct the day it is written and silently lying afterwards.
 *
 * Lower case, as the handlers compare it (`event.key.toLowerCase()`). Callers
 * that DISPLAY it upper-case it themselves, which keeps the one string the
 * handler matches from also being a presentation decision.
 */
export function partVerbKey(id: PartVerbId): string | undefined {
  return PART_CREATE_SHORTCUTS.find((entry) => entry.id === id)?.key;
}

/**
 * Body isolation — the one binding whose handler this slice may not edit
 * (`viewport/partView.ts`, a concurrent agent's territory). Declared here and
 * pinned by the behavioural test described in the module docstring.
 */
export const KEY_ISOLATE = "v";

/**
 * Move the SELECTED feature up or down the build order (REACH-ORDER). A chord
 * rather than a letter because it acts on a selection and every bare letter in
 * the workspace is a create verb; `Alt` is unclaimed — every other keydown
 * handler on this surface bails on `altKey`.
 *
 * Declared here and read by `FeatureTreePanel`'s handler, so the sheet and the
 * keyboard are the same fact. The grip's own `ArrowUp`/`ArrowDown` (no
 * modifier, only while it has focus) is a control-local binding, not a global
 * accelerator, so it stays off the sheet — it is described by the grip's
 * accessible name where a user meets it.
 */
export const KEY_REORDER_EARLIER = "ArrowUp";
export const KEY_REORDER_LATER = "ArrowDown";

/** How the sheet prints an arrow the handler names by its `event.key`. */
const ARROW_GLYPH: Record<string, string> = {
  ArrowUp: "↑",
  ArrowDown: "↓",
};

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
          keys: KEY_IMPORT.toUpperCase(),
          action: "Import a STEP file",
          when: "assemblies",
        },
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
          keys: KEY_ACCEPT_PROPOSAL,
          action: "Sketch on the face under the pointer",
          when: "while the proposal is showing",
        },
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
      // Its OWN group, not a Modelling row: the Modelling note says "with no
      // command open", and these two deliberately work WHILE an editor is
      // open — selecting a row opens its editor, which is the state that arms
      // them. A row filed under a note that contradicts it teaches the wrong
      // thing.
      title: "Feature tree",
      note: "With a row selected. The row's number is also a drag handle.",
      shortcuts: [
        {
          keys: `Alt+${ARROW_GLYPH[KEY_REORDER_EARLIER]}`,
          action: "Move the feature earlier in the build",
        },
        {
          keys: `Alt+${ARROW_GLYPH[KEY_REORDER_LATER]}`,
          action: "Move it later",
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
