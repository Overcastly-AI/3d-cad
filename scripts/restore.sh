#!/usr/bin/env bash
# restore.sh — rebuild a Loft install from a scripts/backup.sh backup.
#
#   scripts/restore.sh backups/loft-20260731T120000Z
#   scripts/restore.sh <dir> --force      # target databases are NOT empty
#   just restore DIR
#
# Works FROM NOTHING: fresh volumes, `docker compose up -d db`, this script, and
# the stack comes back with every part, assembly and drawing in it. The object
# store is deliberately not restored (it is a derived cache — see
# scripts/backup.sh and docs/OPERATIONS.md); the bucket is re-created empty and
# the first evaluate of each part re-derives its mesh byte-identically.
#
# VERSION SKEW — the question every restore tool gets wrong
# ---------------------------------------------------------
# A backup carries the alembic revision it was taken at. Three cases, all LOUD,
# all decided BEFORE anything is written:
#
#   backup revision == this image's head    restore, nothing else, and say so.
#   backup revision is an ANCESTOR of head  restore, then `alembic upgrade head`
#                                           and print `MIGRATED <svc>: A -> B`.
#                                           A backup from an older Loft restores
#                                           onto a newer one.
#   backup revision is UNKNOWN to this      REFUSE (exit 3) before touching a
#   image's migration tree                  single database. That backup came
#                                           from a NEWER Loft than the code you
#                                           are restoring with; rolling its
#                                           schema back would silently drop
#                                           columns and the data in them.
#
# After the data lands, and BEFORE any migration runs, the restore is CHECKED:
# the restored `alembic_version` must equal the manifest's, and the exact
# per-table row counts must equal the manifest's, table for table. A silent
# partial restore is this repo's recurring defect class wearing an ops costume,
# so it is caught by arithmetic (exit 4), not by hoping.
#
# Exit codes: 0 restored · 1 usage/environment · 2 target not empty (use
# --force) · 3 version skew, nothing changed · 4 post-restore verification
# failed.

set -euo pipefail
cd "$(dirname "$0")/.."

SCRIPT_NAME="restore"
# shellcheck source=scripts/_compose_pg.sh
source "scripts/_compose_pg.sh"

BACKUP_FORMAT="loft-backup/1"
ALEMBIC_INI="/app/migrations/alembic.ini"

SOURCE="${1:-}"
FORCE=0
shift || true
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    *)
      echo "restore: unknown argument '$arg'" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$SOURCE" ]]; then
  echo "usage: scripts/restore.sh <backup-dir> [--force]" >&2
  exit 1
fi
[[ -d "$SOURCE" ]] || fail "$SOURCE is not a directory"
[[ -f "$SOURCE/manifest.json" ]] ||
  fail "$SOURCE/manifest.json is missing — that is not a scripts/backup.sh backup"

# One dotted field out of the manifest (stdlib python3, same floor as the rest).
manifest_field() {
  python3 - "$SOURCE/manifest.json" "$1" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    value = json.load(handle)
for key in sys.argv[2].split("."):
    value = value[key]
print(value)
PY
}

# The image's OWN migration tree — no host alembic, no host Python.
# `heads`/`show` load the script directory only and never touch the database,
# so both are safe to ask before a single byte is restored.
alembic_in_image() {
  local service="$1"
  shift
  docker compose run --rm -T --no-deps "$service" alembic -c "$ALEMBIC_INI" "$@"
}

step "1/6 preflight — the backup itself"
format="$(manifest_field format)"
[[ "$format" == "$BACKUP_FORMAT" ]] ||
  fail "manifest format is '$format', expected '$BACKUP_FORMAT'"
echo "  manifest: $format taken $(manifest_field created_at)"
echo "  taken by Loft commit $(manifest_field loft_commit)"

# Checksums FIRST: a truncated dump must fail here, not halfway through a
# restore that has already dropped the live database.
if [[ -f "$SOURCE/SHA256SUMS" ]]; then
  (cd "$SOURCE" && sha256sums_check) || fail "checksum mismatch in $SOURCE"
  echo "  ok  SHA256SUMS verified"
else
  echo "  !!  no SHA256SUMS in $SOURCE — integrity unverified" >&2
fi

require_db_running

step "2/6 version skew — is this backup restorable with THIS Loft?"
for service in gateway documents; do
  backup_revision="$(manifest_field "databases.$service.alembic_revision")"
  head_revision="$(alembic_in_image "$service" heads | awk 'NR==1{print $1}')"
  [[ -n "$head_revision" ]] ||
    fail "could not read $service's migration head from its image"
  printf -v "backup_rev_$service" '%s' "$backup_revision"
  printf -v "head_rev_$service" '%s' "$head_revision"

  if [[ "$backup_revision" == "$head_revision" ]]; then
    echo "  ok  $service: backup is at head ($head_revision) — no migration needed"
    printf -v "plan_$service" '%s' "current"
  elif alembic_in_image "$service" show "$backup_revision" >/dev/null 2>&1; then
    echo "  ok  $service: backup at $backup_revision, this Loft is at $head_revision"
    echo "      -> will MIGRATE FORWARD after restoring"
    printf -v "plan_$service" '%s' "upgrade"
  else
    fail "$service: the backup was taken at alembic revision '$backup_revision',
  which is NOT in this Loft's migration tree (head: $head_revision).

  That means the backup came from a NEWER Loft than the one you are restoring
  with. Restoring it here would leave a schema this code cannot read, and
  migrating it 'back' would drop columns and the data in them.

  Fix: restore with a Loft at least as new as the one that took the backup
  (the manifest records its commit: $(manifest_field loft_commit)).

  NOTHING HAS BEEN CHANGED." 3
  fi
done

step "3/6 preflight — the target databases"
for service in gateway documents; do
  database="$(manifest_field "databases.$service.database")"
  printf -v "database_$service" '%s' "$database"
  exists="$(psql_q postgres <<SQL
SELECT count(*) FROM pg_database WHERE datname = '$database';
SQL
  )"
  tables=0
  if [[ "$exists" != "0" ]]; then
    tables="$(psql_q "$database" <<'SQL'
SELECT count(*) FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
SQL
    )"
  fi
  if [[ "$tables" != "0" ]] && [[ "$FORCE" != "1" ]]; then
    fail "$database already holds $tables tables. Restoring DESTROYS them.
  Re-run with --force if that is what you want." 2
  fi
  if [[ "$tables" == "0" ]]; then
    printf '  %-10s %s: empty — ready\n' "$service" "$database"
  else
    printf '  %-10s %s: %s tables, --force given — they will be DROPPED\n' \
      "$service" "$database" "$tables"
  fi
done

# The services must not hold connections while their database is dropped, and a
# half-restored install has no business serving requests. They come back at the
# end. geometry owns no schema and is stateless, so it stays up.
step "4/6 stop the schema-owning services"
docker compose stop gateway documents >/dev/null 2>&1 || true
echo "  gateway, documents stopped"

step "5/6 restore"
for service in gateway documents; do
  database_ref="database_$service"
  database="${!database_ref}"

  psql_q postgres <<SQL
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
WHERE datname = '$database' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS "$database";
CREATE DATABASE "$database" OWNER "$POSTGRES_USER";
SQL

  # --single-transaction: all-or-nothing. WITHOUT it pg_restore logs errors,
  # keeps going, and EXITS 0 — a half-populated database reported as success,
  # which is exactly the silent partial restore this script exists to make
  # impossible. (-1 implies --exit-on-error.)
  docker compose exec -T -e PGPASSWORD="${POSTGRES_PASSWORD:-}" db \
    pg_restore -U "$POSTGRES_USER" -d "$database" \
    --single-transaction --no-owner --no-privileges \
    <"$SOURCE/$service.dump" ||
    fail "pg_restore into $database failed — it ran in ONE transaction, so the
  database was left empty rather than half-applied"
  echo "  ok  $service: restored into $database"
done

step "6/6 verify, then migrate forward if the backup is older than this Loft"
for service in gateway documents; do
  database_ref="database_$service"
  database="${!database_ref}"
  backup_ref="backup_rev_$service"
  head_ref="head_rev_$service"
  plan_ref="plan_$service"

  # (a) the schema version that actually landed
  restored_revision="$(alembic_revision_of "$database")"
  [[ "$restored_revision" == "${!backup_ref}" ]] || fail \
    "$database restored at revision '$restored_revision' but the manifest says
  '${!backup_ref}' — the dump does not match its manifest. Do not trust this
  restore." 4

  # (b) exact per-table row counts, checked BEFORE any migration can move them
  if ! RESTORED_COUNTS="$(table_counts "$database")" \
    python3 - "$SOURCE/manifest.json" "$service" <<'PY'
import json
import os
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    expected = json.load(handle)["databases"][sys.argv[2]]["row_counts"]
actual = json.loads(os.environ["RESTORED_COUNTS"])
differences = [
    f"    {table}: backup {expected.get(table, 'absent')}"
    f" -> restored {actual.get(table, 'absent')}"
    for table in sorted(set(expected) | set(actual))
    if expected.get(table) != actual.get(table)
]
if differences:
    print(f"  row counts DIFFER for {sys.argv[2]}:", file=sys.stderr)
    print("\n".join(differences), file=sys.stderr)
    raise SystemExit(1)
print(
    f"  ok  {sys.argv[2]}: {sum(expected.values())} rows across "
    f"{len(expected)} tables, counts identical to the backup"
)
PY
  then
    fail "$database: the restored row counts do not match the backup manifest.
  This is a PARTIAL restore. Do not put this install into service." 4
  fi

  # (c) forward migration, loudly
  if [[ "${!plan_ref}" == "upgrade" ]]; then
    echo "  MIGRATING $service: ${!backup_ref} -> ${!head_ref}"
    alembic_in_image "$service" upgrade head
    now="$(alembic_revision_of "$database")"
    [[ "$now" == "${!head_ref}" ]] ||
      fail "$service: migration ended at '$now', expected head '${!head_ref}'" 4
    echo "  MIGRATED  $service: ${!backup_ref} -> $now"
  fi
done

# The bucket is a cache, but it has to EXIST or geometry's first mesh put fails.
# `mc mb --ignore-existing`, so this is safe on a bucket that survived.
step "object storage — ensure the (empty) bucket exists"
docker compose run --rm -T minio-init ||
  echo "  !!  could not run minio-init; create the bucket before evaluating" >&2
echo "  meshes and composed drawings are DERIVED: the first evaluate of each"
echo "  part re-derives them (docs/OPERATIONS.md, 'What is not backed up')."

step "bring the stack back up"
docker compose up -d gateway documents geometry >/dev/null
echo "  gateway, documents, geometry started"

echo
echo "restore: $SOURCE is live."
echo "  Check it: scripts/smoke-healthz.sh \${GATEWAY_PORT:-8000}"
