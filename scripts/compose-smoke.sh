#!/usr/bin/env bash
# compose-smoke.sh — prove the DOCUMENTED SELF-HOST PATH, on a real daemon.
#
#   scripts/compose-smoke.sh            # build, boot, migrate, round-trip
#   KEEP_STACK=1 scripts/compose-smoke.sh   # leave the stack up afterwards
#
# The base compose file ONLY (never the dev overlay): the overlay publishes
# the internal services on loopback for debugging, which is exactly the
# posture this proof asserts is absent from a real deployment.
#
# What it proves, in order:
#   1. the three service images BUILD from the committed Dockerfile;
#   2. `docker compose up` reaches healthy on a real daemon;
#   3. the baked-in alembic trees create both schemas with no host toolchain;
#   4. the gateway is live (/healthz + /readyz via scripts/smoke-healthz.sh);
#   5. a genuine modeling round-trip works over the published gateway port —
#      register → part → sketch → extrude → evaluate → FETCH THE MESH (the
#      MinIO credential path, audit G1) → export STEP;
#   6. documents/geometry are unreachable from the host (audit G3).
#
# Runs in CI (.github/workflows/deploy-path.yml) and on any
# Docker-capable machine — same script, same proof. Failures dump
# `docker compose logs` before exiting so the cause is in the output.

set -euo pipefail
cd "$(dirname "$0")/.."

GATEWAY_PORT="${GATEWAY_PORT:-8000}"
KEEP_STACK="${KEEP_STACK:-0}"

# Long-running services only. NEVER name a one-shot (minio-init) in a --wait
# list: `--wait` treats a container that EXITS as a failure, so the bucket
# bootstrap succeeding would fail the step. One-shots run separately, where
# their own exit code is the gate.
SERVICES=(db redis minio gateway documents geometry)

step() { printf '\n== %s ==\n' "$*"; }

dump_logs() {
  echo
  echo "compose-smoke: FAILED — container state and logs follow" >&2
  docker compose ps --all >&2 || true
  # Disk is a real failure mode: the geometry image carries the ~700MB OCP
  # wheel, so an out-of-space build must not look like a mystery.
  df -h / >&2 || true
  docker compose logs --no-color --tail 200 >&2 || true
}

teardown() {
  local status=$?
  # `if`, not `((…)) && …`: under `set -e` a false arithmetic test as a
  # standalone list would abort the trap and skip the teardown below.
  if ((status != 0)); then dump_logs; fi
  if [[ "$KEEP_STACK" == "1" ]]; then
    echo "compose-smoke: KEEP_STACK=1 — leaving the stack up (docker compose down -v to clean)."
  else
    step "teardown"
    docker compose down -v --remove-orphans || true
  fi
  exit "$status"
}
trap teardown EXIT

step "1/5 build + boot (docker compose up -d --build)"
docker compose up -d --build --wait "${SERVICES[@]}"

step "2/5 provision the mesh bucket (one-shot)"
docker compose run --rm -T minio-init

# Each schema-owning service migrates its OWN database with the alembic tree
# baked into its image — no host Python, no host DB port. --no-deps: the
# stack is already up, this must not restart it. `current` afterwards is the
# evidence line (upgrade itself is silent: env.py configures no logging).
step "3/5 create the schemas (alembic, from the service images)"
for service in gateway documents; do
  docker compose run --rm -T --no-deps "$service" \
    alembic -c /app/migrations/alembic.ini upgrade head
  printf '%s schema at revision: ' "$service"
  docker compose run --rm -T --no-deps "$service" \
    alembic -c /app/migrations/alembic.ini current
done

# The base stack publishes ONLY the gateway (audit G3), so that is the only
# service a host-side probe can see — and the only one a self-hoster needs.
step "4/5 gateway readiness"
SMOKE_SERVICES=gateway SMOKE_RETRIES="${SMOKE_RETRIES:-60}" \
  scripts/smoke-healthz.sh "$GATEWAY_PORT"

step "5/5 modeling round-trip over the gateway"
python3 scripts/compose-roundtrip.py --base-url "http://127.0.0.1:${GATEWAY_PORT}"

echo
echo "compose-smoke: the documented self-host path works."
