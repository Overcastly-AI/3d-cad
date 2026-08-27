import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { FeatureResponse } from "../api/parts";
import {
  buildScope,
  type ScopeFeature,
  defaultScopeMode,
  REPEATABLE_FEATURE_TYPES,
  scopeFeature,
  scopeBadgeSuffix,
  scopeFromParams,
  scopeNote,
  scopeSeed,
  scopeSubject,
  verbHint,
  verbLabel,
} from "./patternScope";

/**
 * The kernel module this list mirrors. The path is deliberate: if the module
 * moves, this test fails loudly rather than silently stopping guarding anything
 * (the idiom `face.test.ts` uses for the body-affecting set, and
 * `thread.test.ts` for the pitch table).
 */
const EVALUATE_PY = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../../services/geometry/src/geometry/features/evaluate.py",
);

/**
 * Parse `_MIRROR_REFLECTABLE_TYPES` out of the geometry evaluator — THE source
 * of truth for which kinds contribute a rigid tool, which
 * `docs/design/pattern-scope.md` §3 adopts unchanged for the pattern ("Identical
 * to mirror-semantics §4.1–§4.4 and §4.7 … that table is not restated").
 *
 * The set is a semantic subset, not a field, so it cannot come from the
 * generated contract today — the same limitation `face.test.ts` documents.
 */
function kernelReflectableTypes(source: string): string[] {
  const marker = "\n_MIRROR_REFLECTABLE_TYPES: frozenset[str] = frozenset(";
  const start = source.indexOf(marker);
  expect(start, "kernel _MIRROR_REFLECTABLE_TYPES not found").toBeGreaterThan(
    -1,
  );
  const open = source.indexOf("{", start);
  const close = source.indexOf("}", open);
  const body = source.slice(open + 1, close);
  return [...body.matchAll(/"([a-z_]+)"/g)].map((m) => m[1] as string);
}

/** A minimal tree row with the fields this module reads. */
function row(
  id: string,
  type: string,
  params: Record<string, unknown> = {},
  extra: { rolled_back?: boolean; suppressed?: boolean; name?: string } = {},
): FeatureResponse {
  const feature = {
    type,
    params,
    suppressed: extra.suppressed ?? false,
  } as unknown as FeatureResponse["feature"];
  return {
    id,
    name: extra.name ?? id,
    part_id: "p",
    order_index: 0,
    created_at: "2026-08-26T00:00:00Z",
    updated_at: "2026-08-26T00:00:00Z",
    rolled_back: extra.rolled_back ?? false,
    feature,
  } as unknown as FeatureResponse;
}

const HOLE = row("h1", "hole", { diameter_mm: 8 }, { name: "Hole1" });
const BOSS = row("e1", "extrude", { operation: "add" }, { name: "Extrude1" });
const POCKET = row("e2", "extrude", { operation: "cut" }, { name: "Pocket1" });
const FILLET = row("f1", "fillet", { radius_mm: 3 }, { name: "Fillet1" });

describe("REPEATABLE_FEATURE_TYPES", () => {
  // The negative control: reverting a member here (or the kernel widening its
  // own set) turns this red. Without it the UI could offer a subject the kernel
  // refuses with `pattern_feature_unsupported` AFTER the user commits — the
  // "refused kinds are non-selectable, not a post-OK error" rule of §7.4.
  it("matches the kernel's own reflectable set exactly", () => {
    const kernel = kernelReflectableTypes(readFileSync(EVALUATE_PY, "utf8"));
    expect(kernel.length).toBeGreaterThan(0);
    expect([...REPEATABLE_FEATURE_TYPES].sort()).toEqual([...kernel].sort());
  });

  it("excludes every modifier, boolean, sketch and datum", () => {
    for (const type of [
      "fillet",
      "chamfer",
      "shell",
      "draft",
      "boolean",
      "sketch",
      "datum",
      "sheet_metal_base_flange",
      "sheet_metal_edge_flange",
    ]) {
      expect(REPEATABLE_FEATURE_TYPES.has(type)).toBe(false);
    }
  });
});

describe("scopeFeature", () => {
  it("names a hole as a subtractive subject", () => {
    expect(scopeFeature(HOLE)).toEqual({
      id: "h1",
      name: "Hole1",
      subtractive: true,
    });
  });

  it("reads an extrude's own operation for the cut flag", () => {
    expect(scopeFeature(BOSS)?.subtractive).toBe(false);
    expect(scopeFeature(POCKET)?.subtractive).toBe(true);
  });

  it("refuses a modifier — it has a result and no tool", () => {
    expect(scopeFeature(FILLET)).toBeNull();
  });

  it("refuses a rolled-back or suppressed row (it contributes nothing)", () => {
    expect(
      scopeFeature(row("h2", "hole", {}, { rolled_back: true })),
    ).toBeNull();
    expect(
      scopeFeature(row("h3", "hole", {}, { suppressed: true })),
    ).toBeNull();
  });

  // A whole-BODY mirror/pattern records no tool of its own (mirror-semantics
  // §4.6), so membership in the kind list is necessary and not sufficient.
  it("refuses a body-scope mirror but accepts a features-scope one", () => {
    expect(scopeFeature(row("m1", "mirror", {}))).toBeNull();
    expect(
      scopeFeature(row("m2", "mirror", { scope: { kind: "body" } })),
    ).toBeNull();
    expect(
      scopeFeature(
        row("m3", "mirror", {
          scope: { kind: "features", features: [] },
        }),
      ),
    ).not.toBeNull();
  });
});

describe("scopeSeed", () => {
  const tree = [BOSS, HOLE, FILLET];

  it("prefers the row the user selected", () => {
    expect(scopeSeed(tree, "h1")).toEqual({
      id: "h1",
      name: "Hole1",
      subtractive: true,
      fromSelection: true,
    });
  });

  it("falls back to the TIP repeatable feature when nothing is selected", () => {
    // Fillet1 is the tip of the tree and cannot be repeated, so the seed walks
    // back to Hole1 rather than proposing a subject the kernel would refuse.
    expect(scopeSeed(tree, null)).toEqual({
      id: "h1",
      name: "Hole1",
      subtractive: true,
      fromSelection: false,
    });
  });

  it("does not take an unrepeatable selection as the subject", () => {
    expect(scopeSeed(tree, "f1")?.id).toBe("h1");
    expect(scopeSeed(tree, "f1")?.fromSelection).toBe(false);
  });

  it("is null when nothing in the tree can be repeated", () => {
    expect(scopeSeed([FILLET], null)).toBeNull();
  });
});

describe("defaultScopeMode", () => {
  /** The seed a tree row would produce, with where it came from stated. */
  const seedOf = (r: FeatureResponse, fromSelection: boolean) => ({
    ...(scopeFeature(r) as ScopeFeature),
    fromSelection,
  });

  it("opens on the selection when the user named one", () => {
    expect(defaultScopeMode(seedOf(BOSS, true))).toBe("features");
  });

  // §1's coin flip: with a cut as the subject, `body` means "the hole today,
  // the whole plate once a fillet lands in between", so the tool proposes the
  // reading that can only mean one thing.
  it("opens on the feature for an INFERRED cut tip", () => {
    expect(defaultScopeMode(seedOf(HOLE, false))).toBe("features");
  });

  // An additive tip reads the same either way, so the legacy spelling holds —
  // the byte-identical behaviour every existing part already has.
  it("keeps the body reading for an INFERRED additive tip", () => {
    expect(defaultScopeMode(seedOf(BOSS, false))).toBe("body");
  });

  it("keeps the body reading when nothing can be repeated", () => {
    expect(defaultScopeMode(null)).toBe("body");
  });
});

describe("buildScope", () => {
  it("spells the legacy reading out rather than omitting it", () => {
    expect(buildScope("body", [])).toEqual({ kind: "body" });
  });

  it("emits FeatureRefs for a selection", () => {
    expect(
      buildScope("features", [
        { id: "h1", name: "Hole1", subtractive: true },
        { id: "e1", name: "Extrude1", subtractive: false },
      ]),
    ).toEqual({
      kind: "features",
      features: [
        { kind: "feature", feature_id: "h1" },
        { kind: "feature", feature_id: "e1" },
      ],
    });
  });

  it("refuses an empty selection (min_length=1)", () => {
    expect(buildScope("features", [])).toBeNull();
  });
});

describe("scopeFromParams", () => {
  it("reads an absent scope as the body reading (pre-v2 parts)", () => {
    expect(scopeFromParams(undefined, [])).toEqual({
      mode: "body",
      features: [],
    });
    expect(scopeFromParams(null, [])).toEqual({ mode: "body", features: [] });
  });

  it("names a persisted selection from the tree, never by uuid", () => {
    expect(
      scopeFromParams(
        { kind: "features", features: [{ kind: "feature", feature_id: "h1" }] },
        [BOSS, HOLE],
      ),
    ).toEqual({
      mode: "features",
      features: [{ id: "h1", name: "Hole1", subtractive: true }],
    });
  });
});

describe("scopeSubject", () => {
  it("uses the feature's own name for a single subject", () => {
    expect(scopeSubject([{ id: "h1", name: "Hole1", subtractive: true }])).toBe(
      "Hole1",
    );
  });

  it("counts a multi-feature selection", () => {
    expect(
      scopeSubject([
        { id: "h1", name: "Hole1", subtractive: true },
        { id: "e1", name: "Extrude1", subtractive: false },
      ]),
    ).toBe("2 features");
  });
});

describe("scopeNote", () => {
  const hole = [{ id: "h1", name: "Hole1", subtractive: true }];
  const boss = [{ id: "e1", name: "Extrude1", subtractive: false }];

  it("states what a features-scope pattern does to a cut", () => {
    expect(scopeNote("pattern", "features", hole)).toBe(
      "Repeats Hole1's cut at every placement. Nothing else about the body moves.",
    );
  });

  /**
   * THE LOAD-BEARING ASSERTION. `body` with a cut subject is not wrong, it is
   * UNSTABLE: today the tree hands the pattern the hole's tool, and the day
   * someone adds a fillet above it the identical feature repeats the whole plate
   * (§1.1) — 24 mm longer, every feature reporting `ok`. The editor has to say
   * so IN PLACE; silence here is the defect the whole scope union exists to end.
   */
  it("warns that the body reading is a coin flip on a cut", () => {
    const note = scopeNote("pattern", "body", hole);
    expect(note).toContain("whatever the tree hands it");
    expect(note).toContain("Hole1's cut today");
    expect(note).toContain("the whole body once another feature lands");
  });

  it("keeps the plain body sentence for an additive subject", () => {
    expect(scopeNote("pattern", "body", boss)).toBe(
      "Repeats the whole body and fuses the copies into one solid.",
    );
  });

  it("speaks the mirror's verb without a second vocabulary", () => {
    // A mirror has ONE reflection, so it must not borrow the pattern's "at
    // every placement" — the copy is shared, the phrasing is not.
    expect(scopeNote("mirror", "features", boss)).toBe(
      "Reflects Extrude1 about the plane and re-applies its own join or cut.",
    );
    expect(scopeNote("mirror", "features", hole)).toBe(
      "Reflects Hole1's cut about the plane. Nothing else about the body moves.",
    );
    expect(scopeNote("mirror", "body", boss)).toBe(
      "Reflects the whole body and joins the reflection to it.",
    );
  });
});

describe("verbLabel / verbHint", () => {
  it("keeps the plain verb when nothing is selected", () => {
    expect(verbLabel("pattern", null)).toBe("Pattern");
    expect(verbLabel("mirror", null)).toBe("Mirror");
    expect(verbHint("pattern", null)).toContain("(P)");
  });

  it("proposes the selected feature by name", () => {
    expect(verbLabel("pattern", "Hole1")).toBe("Repeat Hole1");
    expect(verbLabel("mirror", "Hole1")).toBe("Mirror Hole1");
    expect(verbHint("pattern", "Hole1")).toBe(
      "Repeat Hole1 — place it in a linear or circular array (P)",
    );
  });
});

describe("scopeBadgeSuffix", () => {
  const scoped = row("p1", "pattern", {
    scope: {
      kind: "features",
      features: [{ kind: "feature", feature_id: "h1" }],
    },
  });

  it("names the subject on a scoped pattern row", () => {
    expect(scopeBadgeSuffix(scoped.feature, [HOLE, scoped])).toBe("Hole1");
  });

  it("says nothing extra for a whole-body pattern", () => {
    expect(
      scopeBadgeSuffix(
        row("p2", "pattern", { scope: { kind: "body" } }).feature,
        [],
      ),
    ).toBeNull();
  });

  it("says nothing for a kind that has no scope", () => {
    expect(scopeBadgeSuffix(HOLE.feature, [HOLE])).toBeNull();
  });
});
