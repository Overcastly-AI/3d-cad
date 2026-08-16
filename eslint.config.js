// Root flat ESLint config — TS-ready; app-specific configs extend this.
import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "**/node_modules/**",
      "**/dist/**",
      "**/.venv/**",
      // Generated — never hand-edited, never linted (CLAUDE.md DRY rule).
      "packages/contracts/**",
      "packages/ts-client/**",
      // Agent worktrees. `isolation: 'worktree'` is MANDATED for every parallel
      // builder, and each worktree is a full checkout — so without this, the
      // isolation mechanism the loop depends on turns the SHARED gate red for
      // everyone, on a colleague's in-flight bytes, in a path that will not
      // exist by the time anyone looks. Measured 2026-08-16
      // (AUDIT-ENGINEERING L2): `just lint` failed on
      // `.claude/worktrees/<agent>/scripts/gen-ts-client.mjs`, a file already
      // green in its real location, because the `scripts/**/*.mjs` globals
      // block below does not match under a worktree prefix.
      ".claude/worktrees/**",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    // Node codegen/tooling scripts (run via `just gen`) — declare the Node
    // globals they use; extend the list as scripts grow.
    // Workflow scripts (`.claude/workflows/*.js`) are executed by the Claude
    // Code harness, which injects `agent`/`log`/`phase`/`pipeline`/`parallel`/
    // `args`/`budget`/`workflow` as globals. They are not app code and not Node
    // scripts. Vendoring `loft-dev-loop.js` into the repo on 2026-08-16 —
    // correctly, so the loop definition is reviewable and survives the
    // container — turned `just lint` red on 36 no-undef errors, which is how
    // AUDIT-ENGINEERING L1 found HEAD lint-red.
    files: [".claude/workflows/**/*.js"],
    languageOptions: {
      globals: {
        agent: "readonly",
        log: "readonly",
        phase: "readonly",
        parallel: "readonly",
        pipeline: "readonly",
        workflow: "readonly",
        args: "readonly",
        budget: "readonly",
      },
    },
  },
  {
    files: ["scripts/**/*.mjs"],
    languageOptions: {
      globals: {
        console: "readonly",
        process: "readonly",
        URL: "readonly",
      },
    },
  },
);
