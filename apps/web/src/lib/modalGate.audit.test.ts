/**
 * THE LOUD HALF OF THE KEYBOARD SEAM — a raw window key listener has to be
 * declared here, or this test names the file that added one.
 *
 * `lib/modalGate.ts` can shield a keystroke automatically only while a MODAL
 * layer is open; the focused control's claim on `Enter`/`Space` cannot be
 * enforced that way without silencing the control's own React handlers (the
 * module says why, at length). So that half lives at the registration seam,
 * `useGlobalKeys`, and a seam is forgettable — which is exactly how the W2
 * blocking finding happened: `lib/modalGate.ts` shipped in W0 as "one gate, not
 * a patch per listener", and the very next feature bound `window` by hand and
 * walked straight past it.
 *
 * This is the control for that. It is deliberately a COUNT per file rather than
 * a line list: line numbers churn on every edit, and a count still fails for
 * its own reason — a new listener anywhere reddens it, and the message says
 * what to do. The rows below record the 22 listeners that predate the seam,
 * across 12 files. They are not endorsed, they are RECORDED; migrating one is a
 * fix, and the fix is to lower its number in the same commit.
 *
 * Note what this cannot see, said out loud: a listener registered inside a
 * `packages/**` primitive, or one built through an alias
 * (`const add = window.addEventListener`). Neither exists today. The first is
 * worth extending this walk to the moment `packages/design` grows one.
 */
import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/** `apps/web/src`, derived from this file's own location. */
const SRC = fileURLToPath(new URL("..", import.meta.url));

/**
 * Every raw global key registration, by file, as of the seam landing.
 *
 * A file here is a listener that has NOT been through `useGlobalKeys`, so it
 * does not get the typing-target bail, the `defaultPrevented` bail or — the one
 * that matters — the focused control's claim on `Enter`/`Space`.
 */
const DECLARED: Readonly<Record<string, number>> = {
  // The seam itself: the shield (keydown + keypress), its three self-probes,
  // and the one listener `useGlobalKeys` registers on every caller's behalf.
  "lib/modalGate.ts": 6,
  // Pre-seam listeners. Ordered by count so the heaviest surfaces are visible.
  "routes/PartPage.tsx": 7,
  "viewport/SketchScene.tsx": 2,
  "routes/AssemblyPage.tsx": 2,
  "components/FeatureTreePanel.tsx": 2,
  "components/DocumentRegister.tsx": 2,
  "viewport/viewCommands.ts": 1,
  "viewport/partView.ts": 1,
  "routes/DrawingPage.tsx": 1,
  "routes/AssembliesPage.tsx": 1,
  "components/TimelineStrip.tsx": 1,
  "components/SketchStrip.tsx": 1,
  "components/CreateStrip.tsx": 1,
};

const REGISTRATION =
  /\b(?:window|document)\.addEventListener\(\s*"(?:keydown|keypress)"/g;

function sourceFiles(dir: string, prefix = ""): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const rel = prefix === "" ? entry.name : `${prefix}/${entry.name}`;
    if (entry.isDirectory()) {
      found.push(...sourceFiles(join(dir, entry.name), rel));
      continue;
    }
    if (!/\.tsx?$/.test(entry.name)) continue;
    // Tests register listeners as SPIES — that is the shape of the thing they
    // are asserting about, not a shortcut.
    if (/\.test\.tsx?$/.test(entry.name)) continue;
    found.push(rel);
  }
  return found;
}

function rawRegistrations(): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const file of sourceFiles(SRC)) {
    const matches = readFileSync(join(SRC, file), "utf8").match(REGISTRATION);
    if (matches !== null) counts[file] = matches.length;
  }
  return counts;
}

describe("global key listeners", () => {
  it("are all declared, so a new one cannot slip past the seam", () => {
    const found = rawRegistrations();
    // NON-VACUOUS: the walk must actually be reading the source tree. Without
    // this, a broken path would report zero registrations and agree with an
    // empty expectation — this repo's most-repeated defect.
    expect(
      Object.keys(found).length,
      "the source walk found nothing at all, so this gate is measuring an " +
        `empty tree rather than ${SRC}`,
    ).toBeGreaterThan(5);
    expect(
      found,
      "A raw window/document key listener changed. Register it through " +
        "`useGlobalKeys` in lib/modalGate.ts — it is shorter than the " +
        "listener it replaces and it is what keeps `Enter` on a focused " +
        "button working (W2 review, blocking finding). If you migrated one, " +
        "lower its count here in the same commit.",
    ).toEqual(DECLARED);
  });

  it("counts the seam's own listeners, so the walk is reading real bytes", () => {
    // A second, independently derived reading of one entry: if the regex
    // stopped matching, the comparison above would pass against a table that
    // had been edited to match the nothing it found.
    const source = readFileSync(join(SRC, "lib/modalGate.ts"), "utf8");
    expect(source).toContain(
      'window.addEventListener("keydown", shield, true)',
    );
    expect(source.match(REGISTRATION)).toHaveLength(
      DECLARED["lib/modalGate.ts"] ?? 0,
    );
  });
});
