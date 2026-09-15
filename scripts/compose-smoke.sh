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
#   1. the four images BUILD from the two committed Dockerfiles (the three
#      Python services, and the web app);
#   2. `docker compose up` reaches healthy on a real daemon;
#   3. the baked-in alembic trees create both schemas with no host toolchain;
#   4. the gateway is live (/healthz + /readyz via scripts/smoke-healthz.sh);
#   5. a genuine modeling round-trip works over the published gateway port —
#      register → part → sketch → extrude → evaluate → FETCH THE MESH (the
#      MinIO credential path, audit G1) → export STEP;
#   6. documents/geometry are unreachable from the host (audit G3);
#   7. THE APP IS SERVED and the published ports carry no CDN-loading API
#      explorer (scripts/web-smoke.sh — entry document, hashed bundle, SPA
#      fallback, a transparent /api proxy, and /docs + /redoc gone).
#
# Runs in CI (.github/workflows/deploy-path.yml) and on any
# Docker-capable machine — same script, same proof. Failures dump
# `docker compose logs` before exiting so the cause is in the output.

set -euo pipefail
cd "$(dirname "$0")/.."

GATEWAY_PORT="${GATEWAY_PORT:-8000}"
WEB_PORT="${WEB_PORT:-8080}"
KEEP_STACK="${KEEP_STACK:-0}"

# EPHEMERAL, NON-DEFAULT datastore credentials for this run.
#
# Until 2026-07-30 this proof booted on the compose defaults — POSTGRES_PASSWORD
# `loft-dev-only` and MINIO_ROOT_PASSWORD `loft-minio-dev-only`, both published
# in our own repo. So step 5's "the MinIO credential path works (audit G1)"
# claim was only ever exercised with the ONE password every reader of the repo
# already knows, and a service that ignored its env and hardcoded that literal
# would have passed this gate silently. A real self-hoster sets their own
# credentials, so the proof has to run the way they run it.
#
# These are generated per run, so they are also non-default in a way nobody can
# accidentally depend on. Exported (not passed per-command) because compose
# interpolates them at load for EVERY subsequent `docker compose` call here —
# up, run, logs, down — and a mismatch mid-run would look like a credential bug
# in the app rather than in this script.
rand_secret() {
  # /dev/urandom via od: no openssl dependency, no base64 padding characters
  # that a URL-embedded DSN would need escaped.
  od -An -tx1 -N18 /dev/urandom | tr -d ' \n'
}
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-pg-$(rand_secret)}"
export MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-minio-$(rand_secret)}"

# Fail loudly rather than quietly re-testing the known-password path: if a
# caller (or a stray .env) pins these back to the repo-public defaults, the
# stronger proof silently weakens back to what it was before.
for var in POSTGRES_PASSWORD MINIO_ROOT_PASSWORD; do
  case "${!var}" in
    loft-dev-only | loft-minio-dev-only)
      echo "compose-smoke: $var is the repo-public dev default." >&2
      echo "  This proof must run on credentials a real deploy would use." >&2
      echo "  Unset it (the script generates one) or set a real value." >&2
      exit 2
      ;;
  esac
done

# Long-running services only. NEVER name a one-shot (minio-init) in a --wait
# list: `--wait` treats a container that EXITS as a failure, so the bucket
# bootstrap succeeding would fail the step. One-shots run separately, where
# their own exit code is the gate.
SERVICES=(db redis minio gateway documents geometry web)

# THE STEP CURRENTLY RUNNING, so the verdict can name it without the reader
# having to locate the failure inside ~150 lines of service logs.
CURRENT_STEP="startup (credential posture checks)"
step() {
  CURRENT_STEP="$*"
  printf '\n== %s ==\n' "$*"
}

dump_logs() {
  echo
  echo "compose-smoke: FAILED — container state and logs follow" >&2
  docker compose ps --all >&2 || true
  # Disk is a real failure mode: the geometry image carries the ~700MB OCP
  # wheel, so an out-of-space build must not look like a mystery.
  df -h / >&2 || true
  docker compose logs --no-color --tail 200 >&2 || true
}

# The verdict block — see scripts/compose-verdict.sh for why it exists and why
# it must be built before teardown. Sourced rather than copied: the drill needs
# the identical block, and a copy-paste pair is how the two would drift.
VERDICT_LABEL="compose-smoke"
VERDICT_FILE="${COMPOSE_SMOKE_VERDICT:-}"
# shellcheck source=scripts/compose-verdict.sh
. "$(dirname "$0")/compose-verdict.sh"

teardown() {
  local status=$?
  # `if`, not `((…)) && …`: under `set -e` a false arithmetic test as a
  # standalone list would abort the trap and skip the teardown below.
  if ((status != 0)); then dump_logs; fi

  # BEFORE the teardown: `docker compose down` removes the containers this
  # reads, so a verdict built afterwards could only ever say "nothing here".
  local verdict
  verdict="$(mktemp)"
  build_verdict "$status" "$verdict" || true

  if [[ "$KEEP_STACK" == "1" ]]; then
    echo "compose-smoke: KEEP_STACK=1 — leaving the stack up (docker compose down -v to clean)."
  else
    step "teardown"
    docker compose down -v --remove-orphans || true
  fi

  # LAST, after the teardown chatter, so a small fixed `tail` always reaches it.
  emit_verdict "$verdict"
  exit "$status"
}
trap teardown EXIT

step "1/6 build + boot (docker compose up -d --build)"
docker compose up -d --build --wait "${SERVICES[@]}"

step "2/6 provision the mesh bucket (one-shot)"
docker compose run --rm -T minio-init

# Each schema-owning service migrates its OWN database with the alembic tree
# baked into its image — no host Python, no host DB port. --no-deps: the
# stack is already up, this must not restart it. `current` afterwards is the
# evidence line (upgrade itself is silent: env.py configures no logging).
step "3/6 create the schemas (alembic, from the service images)"
for service in gateway documents; do
  docker compose run --rm -T --no-deps "$service" \
    alembic -c /app/migrations/alembic.ini upgrade head
  printf '%s schema at revision: ' "$service"
  docker compose run --rm -T --no-deps "$service" \
    alembic -c /app/migrations/alembic.ini current
done

# Of the SERVICES, the base stack publishes only `web` and `gateway` (audit
# G3/G4); documents and geometry are internal, and step 5 asserts a host-side
# probe cannot reach them. This probe is the gateway's, because smoke-healthz.sh
# speaks the py-kit /healthz + /readyz contract — the web service is nginx and
# has no upstream of its own to report on; step 6 is what checks it.
step "4/6 gateway readiness"
SMOKE_SERVICES=gateway SMOKE_RETRIES="${SMOKE_RETRIES:-60}" \
  scripts/smoke-healthz.sh "$GATEWAY_PORT"

step "5/6 modeling round-trip over the gateway"
python3 scripts/compose-roundtrip.py --base-url "http://127.0.0.1:${GATEWAY_PORT}"

# ---------------------------------------------------------------------------
# 6+7 — THE APP IS SERVED, AND THE PUBLISHED PORTS CARRY NO CDN-LOADING
# EXPLORER. docs/QUICKSTART.md's first paragraph promises "a browser at a
# modeling viewport"; until 2026-09-15 no compose file defined a web service at
# all, so that sentence described something the self-host path could not do —
# and every step above this line would have passed unchanged.
#
# Delegated to scripts/web-smoke.sh, which is plain HTTP + bash and therefore
# can be REHEARSED without a Docker daemon: `scripts/web-smoke.sh --self-test`
# runs it against stub servers that reproduce the serving rules and then
# against one stub per defect, demanding a failure each time. That matters
# because this script can only ever run on a CI runner (the Docker registry is
# policy-denied in the dev container), so without the split, a typo in these
# assertions would be discovered twenty minutes at a time. It found one
# immediately: a `set -o pipefail` interaction that aborted the whole script
# with an empty stderr when the entry document named no bundle.
# ---------------------------------------------------------------------------
step "6/6 the app is served, and no API explorer is published"
WEB_PORT="$WEB_PORT" GATEWAY_PORT="$GATEWAY_PORT" scripts/web-smoke.sh

echo
echo "compose-smoke: the documented self-host path works, and it ends at the app."
