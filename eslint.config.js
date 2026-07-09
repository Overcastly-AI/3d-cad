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
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
);
