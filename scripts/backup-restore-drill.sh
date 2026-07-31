#!/usr/bin/env bash
# backup-restore-drill.sh — prove the backup by RESTORING it, on a real daemon.
#
#   scripts/backup-restore-drill.sh
#   just backup-drill
#
# A backup nobody has restored is not a backup. This drill is the only thing in
# the repo entitled to call ours one, and it is deliberately built on the same
# harness as scripts/compose-smoke.sh (base compose file only, ephemeral
# non-default credentials, logs dumped on failure).
#
# The sequence, and what each step is for:
#
#   1. build + boot the base stack, migrate both schemas from the images
#   2. SEED REAL DATA through the gateway API: a user, a part with a feature
#      tree, an assembly with an instance of it, a drawing with a sheet and a
#      view — then evaluate the part and record its VOLUME and its
#      content-addressed `mesh_glb_id`
#   3. scripts/backup.sh
#   4. DESTROY EVERYTHING: `docker compose down -v` — every named volume goes,
#      including the Postgres data directory and the MinIO bucket. The drill
#      then asserts the volumes are really gone, because a step that silently
#      no-ops is how a suspiciously fast green happens.
#   5. boot from nothing (fresh volumes) and prove the install is EMPTY: the
#      seeded user cannot log in
#   6. scripts/restore.sh
#   7. VERIFY through the API: log in as the pre-backup user with the
#      pre-backup password, re-read the part/assembly/drawing, confirm the old
#      mesh is a 404 (the object store really was destroyed), then RE-EVALUATE
#      and demand the SAME volume and the SAME `mesh_glb_id` — i.e. the
#      restored feature tree rebuilds a bit-identical solid.
#
# Runs in CI (.github/workflows/deploy-path.yml) and on any Docker-capable
# machine — same script, same proof.

set -euo pipefail
cd "$(dirname "$0")/.."

GATEWAY_PORT="${GATEWAY_PORT:-8000}"
KEEP_STACK="${KEEP_STACK:-0}"
WORK="${WORK_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/loft-drill.XXXXXX")}"
BACKUP_DIR="$WORK/backup"
STATE="$WORK/state.json"

# EPHEMERAL, NON-DEFAULT datastore credentials, for the reason spelled out in
# scripts/compose-smoke.sh: a proof that only ever runs on the repo-public
# defaults cannot tell a service that reads its configuration from one that
# hardcodes the literal everybody knows. Exported once — compose interpolates
# them at load for EVERY later `docker compose` call here, INCLUDING the ones
# inside backup.sh and restore.sh.
rand_secret() { od -An -tx1 -N18 /dev/urandom | tr -d ' \n'; }
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-pg-$(rand_secret)}"
export MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-minio-$(rand_secret)}"
for var in POSTGRES_PASSWORD MINIO_ROOT_PASSWORD; do
  case "${!var}" in
    loft-dev-only | loft-minio-dev-only)
      echo "drill: $var is the repo-public dev default — use a real value." >&2
      exit 2
      ;;
  esac
done

SERVICES=(db redis minio gateway documents geometry)

step() { printf '\n== %s ==\n' "$*"; }

dump_logs() {
  echo
  echo "drill: FAILED — container state and logs follow" >&2
  docker compose ps --all >&2 || true
  df -h / >&2 || true
  docker compose logs --no-color --tail 200 >&2 || true
}

teardown() {
  local status=$?
  if ((status != 0)); then dump_logs; fi
  if [[ "$KEEP_STACK" == "1" ]]; then
    echo "drill: KEEP_STACK=1 — leaving the stack up and $WORK in place."
  else
    step "teardown"
    docker compose down -v --remove-orphans || true
    rm -rf "$WORK"
  fi
  exit "$status"
}
trap teardown EXIT

boot_stack() {
  docker compose up -d --wait "${SERVICES[@]}"
  # One-shot: NEVER in a --wait list (`--wait` treats a container that EXITS as
  # a failure, so the bucket bootstrap succeeding would fail the step).
  docker compose run --rm -T minio-init
}

migrate() {
  for service in gateway documents; do
    docker compose run --rm -T --no-deps "$service" \
      alembic -c /app/migrations/alembic.ini upgrade head
  done
}

wait_for_gateway() {
  SMOKE_SERVICES=gateway SMOKE_RETRIES="${SMOKE_RETRIES:-60}" \
    scripts/smoke-healthz.sh "$GATEWAY_PORT"
}

BASE_URL="http://127.0.0.1:${GATEWAY_PORT}"

step "1/7 build + boot + migrate"
docker compose build gateway documents geometry
boot_stack
migrate
wait_for_gateway

step "2/7 seed real data through the API"
python3 scripts/backup-verify.py seed --base-url "$BASE_URL" --state-out "$STATE"

step "3/7 back it up"
scripts/backup.sh "$BACKUP_DIR"
echo "  manifest:"
sed 's/^/    /' "$BACKUP_DIR/manifest.json"

step "4/7 DESTROY the volumes (docker compose down -v)"
docker compose down -v --remove-orphans
# Assert the destruction really happened. Without this, a `down -v` that
# silently did nothing would leave the rest of the drill passing against data
# that never went away — the "suspiciously fast green" failure mode, in the one
# step whose whole purpose is to remove things.
surviving="$(docker volume ls --format '{{.Name}}' | grep -E '^loft_(db|minio|redis)-data$' || true)"
if [[ -n "$surviving" ]]; then
  echo "drill: FAILED — these volumes survived 'down -v': $surviving" >&2
  exit 1
fi
echo "  ok  loft_db-data, loft_minio-data, loft_redis-data are gone"

step "5/7 boot from NOTHING, and prove the install is empty"
boot_stack
wait_for_gateway
# No migrate: the restore brings the schema with it. The fresh databases exist
# (deploy/docker/postgres-init creates them on an empty volume) and are bare,
# which is exactly the state a self-hoster is in after losing a disk.
python3 scripts/backup-verify.py expect-empty --base-url "$BASE_URL" --state-in "$STATE"

step "6/7 restore"
scripts/restore.sh "$BACKUP_DIR"
wait_for_gateway

step "7/7 verify the data is genuinely back"
python3 scripts/backup-verify.py verify \
  --base-url "$BASE_URL" --state-in "$STATE" --assert-cold-object-store

echo
echo "drill: backup → destroy → restore round-trips. The restored feature tree"
echo "       re-evaluates to the same solid, byte for byte."
