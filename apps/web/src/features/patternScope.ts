/**
 * What a pattern (or a mirror) repeats — the SCOPE, stated by the tree.
 *
 * The defect this closes, from `docs/design/pattern-scope.md` §1: a v1 pattern
 * has one field and INFERS its subject from the shape of the body chain. Drill a
 * hole, pattern it, and you get six holes; add an unrelated corner fillet between
 * the two and the SAME dialog with the SAME numbers repeats the whole plate
 * instead — 24 mm longer, every feature reporting `ok`. The kernel grew a
 * `scope` union to end the guess (`{kind: "body"}` | `{kind: "features", …}`),
 * and nothing in the UI could send it. This module is the UI's half: the
 * selection the user already made IS the answer, so the pattern stops guessing.
 *
 * It is `preselect.ts`'s idiom moved up one level. There, a FACE or EDGE picked
 * anywhere is remembered and every editor seeds from it. Here the pick is a TREE
 * ROW: select `Hole1`, and the Create strip's verb renames itself to
 * "Repeat Hole1" and the editor opens with Hole1 already in scope. Arming a
 * selection is how you CHANGE the subject, never the only way to state one.
 *
 * Two rules, the same two `preselect.ts` keeps:
 *
 *  1. **A scope is a suggestion until it is submitted.** The editor shows a
 *     two-state row (`This body` | `Hole1`) and the user can flip it; nothing is
 *     written until they commit.
 *  2. **Only name what the kernel can actually repeat.** A modifier (fillet,
 *     chamfer, shell, draft, the sheet-metal family), a `boolean`, a `sketch` or
 *     a `datum` has a RESULT and no rigid tool, so naming one is a rebuild error
 *     (`pattern_feature_unsupported`) rather than a body. Those rows never
 *     become the subject; the row falls back to `body` and says why.
 *
 * Pure — unit-tested without a DOM, and its type list is cross-checked against
 * the kernel's own set (`patternScope.test.ts`) so the two cannot drift.
 */
import type {
  FeatureRef,
  FeatureResponse,
  MirrorParams,
  PatternParams,
} from "../api/parts";

/** The `scope` wire union, shared verbatim by pattern and mirror (same shape). */
export type FeatureScope = NonNullable<PatternParams["scope"]>;

/** Which of the two readings a form is currently holding. */
export type ScopeMode = FeatureScope["kind"];

/** Which verb is asking — the copy differs, the mechanism does not. */
export type ScopeVerb = "pattern" | "mirror";

/**
 * The feature kinds whose contribution is a RIGID TOOL plus one boolean, and
 * which a `features` scope can therefore repeat or reflect. Mirrors the kernel's
 * `_MIRROR_REFLECTABLE_TYPES` (`services/geometry/src/geometry/features/
 * evaluate.py`), which `docs/design/pattern-scope.md` §3 adopts unchanged for the
 * pattern — `patternScope.test.ts` parses that frozenset and fails if the two
 * lists ever disagree, the same guard `face.test.ts` puts on the body-affecting
 * set.
 *
 * `mirror` and `pattern` are conditional members: a WHOLE-BODY mirror or pattern
 * records nothing to repeat (§4.6), so membership is necessary and not
 * sufficient — see {@link scopeFeature}.
 */
export const REPEATABLE_FEATURE_TYPES: ReadonlySet<string> = new Set([
  "extrude",
  "revolve",
  "sweep",
  "loft",
  "hole",
  "pattern",
  "mirror",
  "import",
]);

/** A feature named as the subject: what to send, and what to call it on screen. */
export interface ScopeFeature {
  id: string;
  /** The user's own name for it ("Hole1") — never the raw uuid (audit M16). */
  name: string;
  /**
   * This feature REMOVES material. It matters because `body` scope's two
   * inference rules only ever flip on a cut (§1.1/§1.2), so a subtractive
   * subject is the one case where the legacy reading is a coin toss.
   */
  subtractive: boolean;
}

/** The subject a newly-opened editor proposes, and where it came from. */
export interface ScopeSeed extends ScopeFeature {
  /**
   * The user named this row in the tree (rather than it being the tip we
   * inferred). Only an explicit selection is loud enough to rename the verb in
   * the Create strip — inferring the tip would make the toolbar twitch.
   */
  fromSelection: boolean;
}

/** True where a cut/removal is what this feature contributes. */
function isSubtractive(feature: FeatureResponse["feature"]): boolean {
  if (feature.type === "hole") return true;
  if (
    feature.type === "extrude" ||
    feature.type === "revolve" ||
    feature.type === "sweep" ||
    feature.type === "loft"
  ) {
    return feature.params.operation === "cut";
  }
  return false;
}

/**
 * The scope entry for a tree row, or null when it cannot be a subject.
 *
 * Refused: an unsupported kind, a row held out of the build (rolled back or
 * suppressed — it contributes nothing to repeat), and a `body`-scope mirror or
 * pattern, which records no tool of its own and would come back as
 * `pattern_feature_unsupported`. Rule 4 of §7: a refused kind is not selectable,
 * never a post-OK error.
 */
export function scopeFeature(row: FeatureResponse): ScopeFeature | null {
  const feature = row.feature;
  if (!REPEATABLE_FEATURE_TYPES.has(feature.type)) return null;
  if (row.rolled_back || (feature.suppressed ?? false)) return null;
  if (feature.type === "mirror" || feature.type === "pattern") {
    if (feature.params.scope?.kind !== "features") return null;
  }
  return {
    id: row.id,
    name: row.name,
    subtractive: isSubtractive(feature),
  };
}

/**
 * The subject a pattern/mirror opened right now would propose.
 *
 * The selected row wins — that is the whole point of "the tree selection is the
 * scope". With nothing selected we fall back to the TIP repeatable feature, which
 * is what the user just built and almost always what they mean; it is offered in
 * the editor's scope row but does NOT rename the toolbar verb (see
 * {@link ScopeSeed.fromSelection}).
 */
export function scopeSeed(
  features: readonly FeatureResponse[],
  selectedFeatureId: string | null,
): ScopeSeed | null {
  if (selectedFeatureId !== null) {
    const row = features.find((f) => f.id === selectedFeatureId);
    const picked = row === undefined ? null : scopeFeature(row);
    if (picked !== null) return { ...picked, fromSelection: true };
  }
  for (let i = features.length - 1; i >= 0; i -= 1) {
    const tip = scopeFeature(features[i] as FeatureResponse);
    if (tip !== null) return { ...tip, fromSelection: false };
  }
  return null;
}

/**
 * Which reading a NEW pattern/mirror opens on.
 *
 * `features` when the user named a row (they said what the subject is), and also
 * when the proposed subject is a CUT — that is precisely §1's coin flip, where
 * `body` means "a hole today, the whole plate once a fillet lands in between",
 * so the tool proposes the reading that can only mean one thing. Everything else
 * opens on `body`: an additive tip reads the same either way, and the legacy
 * spelling is the one every existing part carries.
 */
export function defaultScopeMode(seed: ScopeSeed | null): ScopeMode {
  if (seed === null) return "body";
  return seed.fromSelection || seed.subtractive ? "features" : "body";
}

/**
 * The `scope` to send, or null when the form is not submittable.
 *
 * ALWAYS sent, on every new feature: an omitted `scope` means `body` forever
 * (§2.1), so a dialog that leaves it out is authoring the §1 defect. Null for an
 * empty `features` selection — `min_length=1`, because an empty selection is
 * authoring nonsense rather than a no-op.
 */
export function buildScope(
  mode: ScopeMode,
  features: readonly ScopeFeature[],
): FeatureScope | null {
  if (mode === "body") return { kind: "body" };
  if (features.length === 0) return null;
  const refs: FeatureRef[] = features.map((f) => ({
    kind: "feature",
    feature_id: f.id,
  }));
  return { kind: "features", features: refs };
}

/**
 * The same value typed for the mirror. The two unions are structurally
 * identical by design ("two verbs that ask the same question of the user should
 * not ask it two different ways" — §2), so this is a re-type and never a second
 * builder; it exists so a mirror call site never needs a cast.
 */
export function asMirrorScope(
  scope: FeatureScope,
): NonNullable<MirrorParams["scope"]> {
  return scope;
}

/**
 * Read a persisted `scope` back into form state, naming each id from the tree.
 *
 * An absent key reads `body`, exactly as the server reads it (§2.1), so opening
 * a pre-v2 pattern shows the reading it actually has rather than a guess.
 */
export function scopeFromParams(
  scope: FeatureScope | null | undefined,
  features: readonly FeatureResponse[],
): { mode: ScopeMode; features: readonly ScopeFeature[] } {
  if (scope === null || scope === undefined || scope.kind === "body") {
    return { mode: "body", features: [] };
  }
  const named: ScopeFeature[] = [];
  for (const ref of scope.features) {
    const row = features.find((f) => f.id === ref.feature_id);
    if (row === undefined) continue;
    named.push({
      id: row.id,
      name: row.name,
      subtractive: isSubtractive(row.feature),
    });
  }
  return { mode: "features", features: named };
}

/**
 * How the `features` state reads on the two-state row: the feature's own name
 * when it is one (the overwhelmingly common case, and the only shape this UI
 * authors today), a count when a persisted selection carries several.
 */
export function scopeSubject(features: readonly ScopeFeature[]): string {
  if (features.length === 1) return (features[0] as ScopeFeature).name;
  if (features.length === 0) return "Features";
  return `${features.length} features`;
}

/**
 * The tree row's badge suffix for a scoped pattern/mirror — `pattern · Hole1` —
 * or null where the row repeats the whole body and the type says everything.
 *
 * The exact precedent is the TAPPED HOLE badge (`hole · M10x1.5`): a parameter
 * the viewport cannot show earns the pixels, because the tree is the only place
 * a modeller can tell two otherwise identical rows apart. A whole-body pattern
 * and a hole pattern render as different bodies, but `Pattern1` beside
 * `Pattern1` says nothing about WHICH, and that is the whole defect.
 *
 * Derived at render from the params plus the tree, never baked into the
 * feature's NAME: names are user-editable with no rename propagation, so a name
 * carrying "of Hole1" would quietly lie the first time Hole1 is renamed.
 */
export function scopeBadgeSuffix(
  feature: FeatureResponse["feature"],
  features: readonly FeatureResponse[],
): string | null {
  if (feature.type !== "pattern" && feature.type !== "mirror") return null;
  const scope = scopeFromParams(feature.params.scope, features);
  if (scope.mode === "body" || scope.features.length === 0) return null;
  return scopeSubject(scope.features);
}

/** The verb's word — "Repeats" states a fact about what will happen. */
const VERB_WORD: Record<ScopeVerb, string> = {
  pattern: "Repeats",
  mirror: "Reflects",
};

/**
 * WHERE the subject ends up. A pattern has many placements; a mirror has one
 * reflection, so "at every placement" would be quietly false there — the kind of
 * shared-copy seam that reads fine until you look at the other verb's card.
 */
const VERB_WHERE: Record<ScopeVerb, string> = {
  pattern: "at every placement",
  mirror: "about the plane",
};

/**
 * The sentence under the scope row: what this reading will actually do.
 *
 * The `body` + cut case earns the longest sentence in the editor, and it is the
 * whole reason this module exists. `body` there is not wrong, it is UNSTABLE:
 * today the tree hands the pattern the hole's cut, and the day someone adds a
 * fillet above it the identical feature repeats the whole plate (§1.1). Both
 * results report `ok`. So the editor says so, in place, instead of letting the
 * user discover it as a silently doubled part months later.
 */
export function scopeNote(
  verb: ScopeVerb,
  mode: ScopeMode,
  features: readonly ScopeFeature[],
): string {
  const word = VERB_WORD[verb];
  const subject = scopeSubject(features);
  const cut = features.length > 0 && features.every((f) => f.subtractive);
  if (mode === "features") {
    if (features.length === 0) return scopeRefusal();
    const where = VERB_WHERE[verb];
    return cut
      ? `${word} ${subject}'s cut ${where}. Nothing else about the body moves.`
      : `${word} ${subject} ${where} and re-applies its own join or cut.`;
  }
  if (cut) {
    return `${word} whatever the tree hands it here — ${subject}'s cut today, the whole body once another feature lands between them. Name ${subject} to say which you mean.`;
  }
  return verb === "pattern"
    ? "Repeats the whole body and fuses the copies into one solid."
    : "Reflects the whole body and joins the reflection to it.";
}

/**
 * Why the `features` state is unavailable. Shown instead of a disabled control
 * with no explanation — an empty state is an instruction, not a shrug.
 */
export function scopeRefusal(): string {
  return "No feature here can be repeated on its own — fillets, chamfers, shells, drafts, folds and booleans have a result and no tool.";
}

/**
 * The Create-strip verb, renamed by the subject the user selected.
 *
 * "Repeat Hole1" is the tool PROPOSING (CLAUDE.md flow rule #1: the next step is
 * visible from the current state). With nothing selected the verb keeps its
 * plain name — a toolbar that renamed itself on every tree change would be
 * noise, not guidance.
 */
export function verbLabel(verb: ScopeVerb, subject: string | null): string {
  if (subject === null) return verb === "pattern" ? "Pattern" : "Mirror";
  return verb === "pattern" ? `Repeat ${subject}` : `Mirror ${subject}`;
}

/** The verb's accessible name, teaching the accelerator and naming the subject. */
export function verbHint(verb: ScopeVerb, subject: string | null): string {
  if (verb === "pattern") {
    return subject === null
      ? "Pattern — repeat the body in a linear or circular array (P)"
      : `Repeat ${subject} — place it in a linear or circular array (P)`;
  }
  return subject === null
    ? "Mirror — reflect the body about a plane and union the copy in (I)"
    : `Mirror ${subject} — reflect it about a plane (I)`;
}
