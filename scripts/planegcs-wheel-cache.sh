#!/usr/bin/env bash
# Does `uv sync` need to COMPILE planegcs here, or does uv's cache already
# hold the wheel it built from vendor/planegcs? Only a compile needs the Eigen
# and Boost headers, so .github/actions/planegcs-build-deps asks this first and
# skips the headers entirely on a hit.
#
#   scripts/planegcs-wheel-cache.sh probe   # exit 0: cached wheel; 1: must build
#
# It reads uv's own plan from a dry run (`-v` names each distribution as
# "already cached" or "uncached") because the obvious probe does not work:
# `uv sync --no-build-package planegcs` refuses a cached build too (uv 0.11:
# "marked as --no-build but has no binary distribution").
#
# MEASURED 2026-10-23 (uv 0.11.32): uv keys a directory source's built wheel
# on the CTIME of its pyproject.toml and src/ ("Computed cache info" in
# `uv sync -v`). Pinning the mtimes with `touch -d` does not move that key,
# and actions/checkout writes every file fresh, so on a hosted runner this
# probe is expected to report a miss on every job: the wheel setup-uv restores
# was built under another checkout's ctimes. It costs ~1 s, and the
# step log then states what happened instead of the action assuming it. The
# headers come from the .deb cache in the action, not from apt, either way.
set -euo pipefail

case "${1:-}" in
  probe)
    log=$(uv sync --locked --dry-run -v 2>&1) || {
      echo "uv dry run failed; treating planegcs as uncached:"
      tail -5 <<<"$log"
      exit 1
    }
    if grep -q 'already cached: planegcs' <<<"$log"; then
      echo "planegcs: uv's cache holds the built wheel; no compile, no headers"
      exit 0
    fi
    if grep -q 'uncached distribution: planegcs' <<<"$log"; then
      # uv logs the key it computed on the line before the verdict.
      grep -B1 'uncached distribution: planegcs' <<<"$log" | grep 'cache info' || true
      echo "planegcs: no built wheel uv will reuse; it will be compiled"
      exit 1
    fi
    if grep -qE '(already installed|installed and fresh).*: planegcs' <<<"$log"; then
      echo "planegcs: already installed in the environment; no compile"
      exit 0
    fi
    # None of the three: a uv bump moved the wording. Fail towards installing
    # the headers, which is slower but never red.
    echo "::warning::planegcs-wheel-cache: could not read uv's plan for planegcs; assuming a compile"
    exit 1
    ;;
  *)
    echo "usage: $0 probe" >&2
    exit 2
    ;;
esac
