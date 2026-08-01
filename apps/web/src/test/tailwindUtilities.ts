/**
 * Tailwind utility resolver — the machinery behind the guard test that keeps
 * `packages/design`'s CLOSED token scales from silently deleting utilities.
 *
 * Why this exists (UI-REVIEW 2026-07-30 P1): `tailwind-preset.ts` *replaces*
 * `theme.spacing` (and `fontSize`/`borderRadius`/…) with the token scales, on
 * purpose — only token values may exist in the DOM theme. But when a source
 * file asks for a step the scale does not have, Tailwind emits **no rule at
 * all**: no warning, no build error, no fallback. `h-px grow bg-brass` becomes
 * a 0px-tall element; `py-1.5` becomes `padding: 0`. The intent evaporates and
 * the result photographs as "dense and quiet", which is why three consecutive
 * audits missed ~118 dead classes across 40 files.
 *
 * So the guard runs the app's REAL Tailwind config over candidate class names
 * harvested from the same source roots the config's `content` globs scan, and
 * asserts each candidate produces a rule. Node-only (fs + postcss); imported
 * by `tailwindUtilities.test.ts`, never by app code.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import postcss from "postcss";
import tailwind from "tailwindcss";
import type { Config } from "tailwindcss";

const HERE = path.dirname(fileURLToPath(import.meta.url));
/** `apps/web` — the package that owns `tailwind.config.ts`. */
export const WEB_ROOT = path.resolve(HERE, "../..");
export const REPO_ROOT = path.resolve(WEB_ROOT, "../..");

/**
 * The utility families driven by a token scale we deliberately closed, i.e.
 * exactly the families where a missing step fails silently. Layout/geometry
 * only — colour and font utilities fail loudly enough (an unknown colour is
 * visible), and their scales are already asserted by the token tests.
 */
const SPACING_FAMILIES = [
  "p",
  "px",
  "py",
  "pt",
  "pr",
  "pb",
  "pl",
  "m",
  "mx",
  "my",
  "mt",
  "mr",
  "mb",
  "ml",
  "gap",
  "gap-x",
  "gap-y",
  "space-x",
  "space-y",
  "w",
  "h",
  "size",
  "min-w",
  "min-h",
  "max-w",
  "max-h",
  "inset",
  "inset-x",
  "inset-y",
  "top",
  "right",
  "bottom",
  "left",
  "translate-x",
  "translate-y",
  "text",
  "rounded",
  "rounded-t",
  "rounded-r",
  "rounded-b",
  "rounded-l",
  "duration",
  "z",
] as const;

const FAMILY_RE = new RegExp(`^-?(?:${SPACING_FAMILIES.join("|")})-(.*)$`);

/**
 * Values we can tell apart from prose with certainty: a scale step (`1.5`,
 * `16`), a fraction (`1/2`), the hairline (`px`), a CSS keyword, or an
 * arbitrary value. That shape filter is what keeps `data-testid="top-toolbar"`
 * and `"right-click"` out of the candidate set.
 *
 * The cost is that NAMED token utilities (`h-band`, `bottom-hud-lane`) are not
 * harvested — `top-toolbar` and `bottom-hud-lane` are indistinguishable from
 * the outside. They are covered instead by the explicit vocabulary fixture in
 * the test, which is small and curated. The silent-size class of bug this guard
 * exists for lives entirely in the numeric steps.
 */
const VALUE_RE =
  /^(?:\d+(?:\.\d+)?|\d+\/\d+|px|auto|full|screen|min|max|fit|\[[^\]]*\])$/;

/** String literals: the only place a Tailwind class can legitimately live. */
const STRING_LITERAL_RE = /"([^"\\\n]*)"|'([^'\\\n]*)'|`([^`\\$\n]*)`/g;

/**
 * Comments are prose — and prose talks ABOUT dead classes (this repo's token
 * docs name `w-72`/`bottom-16` as cautionary tales), which would make the guard
 * fail on its own documentation.
 */
const stripComments = (src: string): string =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`\\])\/\/.*$/gm, "$1");

/** The guard's own files: their fixtures name classes that must NOT resolve. */
const SELF_RE = /tailwindUtilities(?:\.test)?\.ts$/;

/**
 * Strip Tailwind variant prefixes (`hover:`, `group-hover/tt:`,
 * `[[data-band-tier=icon]_&]:`) — the last top-level `:`, ignoring any inside
 * `[]` arbitrary values/selectors.
 */
const stripVariants = (token: string): string => {
  let depth = 0;
  let cut = -1;
  for (let i = 0; i < token.length; i += 1) {
    const c = token[i];
    if (c === "[" || c === "(") depth += 1;
    else if (c === "]" || c === ")") depth -= 1;
    else if (c === ":" && depth === 0) cut = i;
  }
  const bare = cut >= 0 ? token.slice(cut + 1) : token;
  return bare.startsWith("!") ? bare.slice(1) : bare;
};

const SOURCE_RE = /\.(?:tsx?|html)$/;

const walk = (dir: string, out: string[] = []): string[] => {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(p, out);
    else if (SOURCE_RE.test(entry.name)) out.push(p);
  }
  return out;
};

export interface Candidate {
  /** The bare utility, variants stripped (e.g. `py-1.5`). */
  readonly utility: string;
  /** Repo-relative files that mention it, for a readable failure message. */
  readonly files: readonly string[];
}

/**
 * Harvest utility candidates from every source file under `roots`.
 *
 * Deliberately conservative: only tokens inside string literals, only the
 * families above, so a prose mention in a comment or a `data-*` value can't
 * masquerade as a class.
 */
export const harvestCandidates = (roots: readonly string[]): Candidate[] => {
  const seen = new Map<string, Set<string>>();
  for (const root of roots) {
    for (const file of walk(root)) {
      if (SELF_RE.test(file)) continue;
      const src = stripComments(fs.readFileSync(file, "utf8"));
      for (const match of src.matchAll(STRING_LITERAL_RE)) {
        const literal = match[1] ?? match[2] ?? match[3] ?? "";
        for (const raw of literal.split(/\s+/)) {
          if (!raw) continue;
          const utility = stripVariants(raw);
          const family = FAMILY_RE.exec(utility);
          if (family === null || !VALUE_RE.test(family[1] ?? "")) continue;
          const files = seen.get(utility) ?? new Set<string>();
          files.add(path.relative(REPO_ROOT, file));
          seen.set(utility, files);
        }
      }
    }
  }
  return [...seen.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([utility, files]) => ({ utility, files: [...files].sort() }));
};

/**
 * Compile `utilities` against a Tailwind config and return the subset that
 * produced **no rule** — i.e. the classes the theme cannot emit.
 */
export const findUnresolvable = async (
  utilities: readonly string[],
  config: Config,
): Promise<string[]> => {
  const result = await postcss([
    tailwind({
      ...config,
      // `raw` content: ask for exactly these candidates, nothing else.
      content: [{ raw: utilities.join(" "), extension: "html" }],
      // Preflight is base CSS, irrelevant to whether a utility resolves.
      corePlugins: { preflight: false },
    }),
  ]).process("@tailwind utilities;", { from: undefined });

  const emitted = new Set<string>();
  result.root.walkRules((rule) => {
    for (const selector of rule.selectors) {
      // Leading class of the selector, un-escaping Tailwind's `\.` / `\[` etc.
      const m = /^\.((?:\\.|[^\s:>+~,[.])+)/.exec(selector);
      if (m?.[1] !== undefined) emitted.add(m[1].replace(/\\/g, ""));
    }
  });

  return utilities.filter((u) => !emitted.has(u));
};

/** Load `apps/web/tailwind.config.ts` — the config the app actually builds. */
export const loadWebConfig = async (): Promise<Config> => {
  const mod: { default: Config } = await import(
    path.join(WEB_ROOT, "tailwind.config.ts")
  );
  return mod.default;
};

/** The source roots `apps/web/tailwind.config.ts` scans. */
export const scannedRoots = (): string[] => [
  path.join(WEB_ROOT, "src"),
  path.join(REPO_ROOT, "packages/design/src"),
];
