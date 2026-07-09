#!/usr/bin/env bash
# dev-instance.sh — per-agent isolated dev stack (parallel worktrees depend
# on this; see CLAUDE.md "Parallel by default").
#
# Usage:   scripts/dev-instance.sh <N> [compose args...]
#          scripts/dev-instance.sh 2              # up --build (default)
#          scripts/dev-instance.sh 2 up -d --build
#          scripts/dev-instance.sh 2 down -v
#          scripts/dev-instance.sh 2 logs -f geometry
#
# Instance N gets:
#   - compose project `loft-<N>` (own containers, network, named volumes)
#   - host ports offset by N*100:
#       gateway 8000+N*100 · documents 8001+N*100 · geometry 8002+N*100
#       db 5432+N*100 · redis 6379+N*100 · minio 9000/9001+N*100
#   e.g. N=2 → gateway :8200, db :5632, minio :9200.
# N=0 is the plain default stack. Smoke an instance with:
#   scripts/smoke-healthz.sh $((8000 + N*100))

set -euo pipefail

usage() {
  echo "usage: scripts/dev-instance.sh <N> [compose args...]" >&2
  exit 2
}

[[ $# -ge 1 ]] || usage
N="$1"
shift
[[ "$N" =~ ^[0-9]+$ ]] || usage

OFFSET=$((N * 100))
export GATEWAY_PORT=$((8000 + OFFSET))
export DOCUMENTS_PORT=$((8001 + OFFSET))
export GEOMETRY_PORT=$((8002 + OFFSET))
export DB_PORT=$((5432 + OFFSET))
export REDIS_PORT=$((6379 + OFFSET))
export MINIO_PORT=$((9000 + OFFSET))
export MINIO_CONSOLE_PORT=$((9001 + OFFSET))

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Default action: foreground dev stack with hot reload.
if [[ $# -eq 0 ]]; then
  set -- up --build
fi

exec docker compose \
  --project-name "loft-${N}" \
  --project-directory "$REPO_ROOT" \
  -f "$REPO_ROOT/docker-compose.yml" \
  -f "$REPO_ROOT/docker-compose.dev.yml" \
  "$@"
