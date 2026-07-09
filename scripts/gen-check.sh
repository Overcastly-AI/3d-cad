#!/usr/bin/env bash
# Contract drift check (`just gen-check` — what CI calls).
#
# Regenerates contracts + TS client into a tempdir and diffs against the
# committed output, so the working tree is never dirtied. Non-zero exit on
# drift; the diff itself is the error report. The TS client is regenerated
# from the *freshly exported* contracts so drift at either layer is caught.
set -euo pipefail
cd "$(dirname "$0")/.."

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

uv run scripts/gen-contracts.py --out "$tmp/contracts" >/dev/null
node scripts/gen-ts-client.mjs --contracts "$tmp/contracts" --out "$tmp/ts-client-src" >/dev/null

fail=0
# Hand-written plumbing (package.json/README) lives beside the generated JSON.
if ! diff -ru --exclude=package.json --exclude=README.md \
    packages/contracts "$tmp/contracts"; then
  fail=1
fi
if ! diff -ru packages/ts-client/src "$tmp/ts-client-src"; then
  fail=1
fi

if [ "$fail" -ne 0 ]; then
  echo >&2
  echo "gen-check: DRIFT — committed contracts/ts-client are stale." >&2
  echo "gen-check: run \`just gen\` and commit the result." >&2
  exit 1
fi
echo "gen-check: contracts + ts-client match generated output."
