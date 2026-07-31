#!/usr/bin/env bash
# Contract drift check (`just gen-check` — what CI calls).
#
# Regenerates contracts + TS client into a tempdir and diffs against the
# committed output, so the working tree is never dirtied. Non-zero exit on
# drift; the diff itself is the error report. The TS client is regenerated
# from the *freshly exported* contracts so drift at either layer is caught.
#
# TWO MODES, because the default one has a blind spot that bit us on
# 2026-07-31 (see `--from-index` below and the CLAUDE.md recipe):
#
#   (default)      generate from the WORKING TREE. Fast, and correct for the
#                  local edit loop — you changed a pydantic model and want to
#                  know whether the committed JSON is stale.
#   --from-index   generate from the tree your NEXT COMMIT will have (the git
#                  index). Slower (it materialises a worktree and syncs an env
#                  there) and it is the one that answers "will CI be green on
#                  my commit", which is the standing rule.
set -euo pipefail
cd "$(dirname "$0")/.."

from_index=0
for arg in "$@"; do
  case "$arg" in
    --from-index) from_index=1 ;;
    *) echo >&2 "gen-check: unknown argument: $arg"; exit 2 ;;
  esac
done

tmp="$(mktemp -d)"
src="."
cleanup() {
  if [ "$from_index" -eq 1 ] && [ -d "$tmp/src" ]; then
    git worktree remove --force "$tmp/src" >/dev/null 2>&1 || true
  fi
  rm -rf "$tmp"
}
trap cleanup EXIT

if [ "$from_index" -eq 1 ]; then
  # WHY THIS MODE EXISTS. `gen-contracts.py` imports the LIVE source, so in the
  # default mode the generator's input is whatever is on disk — including other
  # agents' UNCOMMITTED routers and schemas. The check then passes locally while
  # the commit it blesses contains contracts describing source that is not in
  # it, which is gen-check-RED in CI on that commit. That is not hypothetical:
  # on 2026-07-31 an agent's `just gen` captured a sibling's uncommitted gateway
  # duplicate-routes work, committed `gateway.openapi.json` + `gateway/
  # schema.ts` describing routes with no committed source, and had to rebuild
  # the contracts in a clean worktree and force-push over it. The default mode
  # could not have caught it *by construction* — it was measuring the wrong
  # thing, confidently.
  #
  # So: materialise the INDEX (what `git commit` would write) into a throwaway
  # worktree and generate there. `uv run` in that worktree builds its own
  # environment; with a warm uv cache that is seconds, not minutes.
  tree="$(git write-tree)"
  git worktree add -q --detach "$tmp/src" HEAD
  git -C "$tmp/src" read-tree -u --reset "$tree"
  src="$tmp/src"
  echo "gen-check: generating from the INDEX (tree $tree), not the working tree."
fi

(cd "$src" && uv run scripts/gen-contracts.py --out "$tmp/contracts") >/dev/null
node scripts/gen-ts-client.mjs --contracts "$tmp/contracts" --out "$tmp/ts-client-src" >/dev/null

fail=0
# Hand-written plumbing (package.json/README) lives beside the generated JSON.
if ! diff -ru --exclude=package.json --exclude=README.md \
    "$src/packages/contracts" "$tmp/contracts"; then
  fail=1
fi
if ! diff -ru "$src/packages/ts-client/src" "$tmp/ts-client-src"; then
  fail=1
fi

if [ "$fail" -ne 0 ]; then
  echo >&2
  if [ "$from_index" -eq 1 ]; then
    echo "gen-check: DRIFT in the tree your next commit would have." >&2
    echo "gen-check: the committed contracts do not match the committed SOURCE." >&2
    echo "gen-check: if you ran \`just gen\` in a tree holding another agent's" >&2
    echo "gen-check: uncommitted schema work, regenerate from a clean worktree." >&2
  else
    echo "gen-check: DRIFT — committed contracts/ts-client are stale." >&2
    echo "gen-check: run \`just gen\` and commit the result." >&2
  fi
  exit 1
fi

if [ "$from_index" -eq 1 ]; then
  echo "gen-check: contracts + ts-client match the INDEX's source."
else
  echo "gen-check: contracts + ts-client match generated output."
fi
