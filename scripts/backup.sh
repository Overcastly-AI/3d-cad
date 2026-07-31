#!/usr/bin/env bash
# backup.sh — take a restorable backup of a running Loft stack.
#
#   scripts/backup.sh                 # -> backups/loft-<UTC timestamp>/
#   scripts/backup.sh /srv/loft-backups/nightly
#   just backup
#
# WHAT IS IN THE BACKUP, AND WHY THAT IS EVERYTHING
# -------------------------------------------------
# Loft keeps ALL durable state in Postgres, in two databases that are
# deliberately separate (both alembic trees start at revision "0001" in the
# default `alembic_version` table — see deploy/docker/postgres-init):
#
#   loft_gateway    identity: users + password hashes
#   loft_documents  parts, FEATURE TREES, assemblies, instances, mates,
#                   drawings, sheets, views, dimensions, snapshots — and the
#                   inline STEP text of any IMPORTED body (import rides the
#                   ordinary feature-tree persistence, docs/design/step-import.md
#                   §2b), so an imported part is inside the dump too.
#
# The MinIO/S3 bucket is NOT backed up, on purpose. It holds only
# content-addressed DERIVED artifacts — `meshes/sha256/<hex>.glb` and composed
# drawing artifacts keyed on a hash of the compose inputs. Both are pure
# functions of data that IS in Postgres (RESEARCH §9 determinism), so copying
# them would spend gigabytes to save re-deriving what the first evaluate
# re-derives anyway — and the drill PROVES that rather than assuming it:
# scripts/backup-restore-drill.sh destroys the bucket, restores, and demands the
# SAME `mesh_glb_id` (a SHA-256 of the GLB) back out of a rebuild. Restore-time
# cost, and the opt-in mirror command for operators who want the cache warm
# anyway, are in docs/OPERATIONS.md.
#
# Redis is a queue / rate-limit cache, not a store of record: nothing to back up.
#
# Requirements: a RUNNING stack. Everything goes through `docker compose exec
# db`, so there is no host Postgres client to install and the dump is always
# taken by the same pg_dump major version that wrote the data. Each database is
# dumped in ONE transaction (pg_dump's guarantee), live, with no downtime.
#
# Output layout (plain files, inspectable, `sha256sum -c`-verifiable):
#
#   <dest>/manifest.json   format, timestamp, per-database alembic revision,
#                          exact per-table row counts, dump sha256s
#   <dest>/gateway.dump    pg_dump -Fc (custom format, compressed)
#   <dest>/documents.dump  pg_dump -Fc
#   <dest>/SHA256SUMS
#
# Restore it with: scripts/restore.sh <dest>

set -euo pipefail
cd "$(dirname "$0")/.."

SCRIPT_NAME="backup"
# shellcheck source=scripts/_compose_pg.sh
source "scripts/_compose_pg.sh"

BACKUP_FORMAT="loft-backup/1"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="${1:-backups/loft-${TIMESTAMP}}"

step "1/4 preflight"
require_db_running

if [[ -e "$DEST" ]] && [[ -n "$(ls -A "$DEST" 2>/dev/null)" ]]; then
  fail "$DEST already exists and is not empty — refusing to overwrite a backup"
fi
mkdir -p "$DEST"
echo "  destination: $DEST"

SERVER_VERSION="$(psql_q postgres <<<'SHOW server_version;' | tr -d ' ')"
echo "  postgres: $SERVER_VERSION"

step "2/4 dump both databases (pg_dump -Fc, one consistent transaction each)"
for service in gateway documents; do
  database="$(database_for "$service")"

  # The schema version this backup was taken at. A database with no
  # alembic_version was never migrated, and a dump of it cannot be restored
  # honestly (restore.sh would have nothing to check against), so refuse HERE
  # rather than write a file that only fails at the worst possible moment.
  revision="$(alembic_revision_of "$database")" ||
    fail "$database has no alembic_version table — it was never migrated. Run:
  docker compose run --rm $service alembic -c /app/migrations/alembic.ini upgrade head"
  [[ -n "$revision" ]] || fail "$database: alembic_version is empty"
  printf -v "revision_$service" '%s' "$revision"
  printf -v "counts_$service" '%s' "$(table_counts "$database")"

  # -Fc: custom format — compressed, and pg_restore can be selective.
  # --no-owner / --no-privileges: restorable into whatever role the target
  # install uses, instead of demanding the source role name exist there.
  docker compose exec -T -e PGPASSWORD="${POSTGRES_PASSWORD:-}" db \
    pg_dump -U "$POSTGRES_USER" -d "$database" -Fc --no-owner --no-privileges \
    >"$DEST/$service.dump" ||
    fail "pg_dump of $database failed"

  bytes="$(wc -c <"$DEST/$service.dump" | tr -d ' ')"
  printf -v "bytes_$service" '%s' "$bytes"
  printf -v "digest_$service" '%s' "$(sha256_of "$DEST/$service.dump")"
  printf '  %-10s %s @ %s — %s bytes\n' "$service" "$database" "$revision" "$bytes"
done

step "3/4 verify the archives are readable and carry real tables"
# A dump nobody can read is not a backup. `pg_restore -l` reads the archive TOC
# (from stdin, in the same image that wrote it) and fails on a truncated or
# corrupt file; grepping that TOC for the tables holding the product's value
# catches the other failure mode — a perfectly valid archive of the WRONG
# database.
for service in gateway documents; do
  toc="$(docker compose exec -T db pg_restore -l <"$DEST/$service.dump")" ||
    fail "$DEST/$service.dump is not a readable pg_restore archive"
  case "$service" in
    gateway) required=(users) ;;
    documents) required=(parts features assemblies drawings) ;;
  esac
  for table in "${required[@]}"; do
    grep -qE "TABLE DATA public ${table}( |\$)" <<<"$toc" ||
      fail "$service.dump has no TABLE DATA entry for '$table' — wrong database?"
  done
  echo "  ok  $service.dump: readable archive, carries ${required[*]}"
done

step "4/4 write the manifest"
# Stdlib python3 only (the same dependency floor as scripts/compose-roundtrip.py).
GATEWAY_DB="$GATEWAY_DB" DOCUMENTS_DB="$DOCUMENTS_DB" \
  BACKUP_FORMAT="$BACKUP_FORMAT" TIMESTAMP="$TIMESTAMP" \
  SERVER_VERSION="$SERVER_VERSION" \
  GATEWAY_REV="$revision_gateway" DOCUMENTS_REV="$revision_documents" \
  GATEWAY_COUNTS="$counts_gateway" DOCUMENTS_COUNTS="$counts_documents" \
  GATEWAY_SHA="$digest_gateway" DOCUMENTS_SHA="$digest_documents" \
  GATEWAY_BYTES="$bytes_gateway" DOCUMENTS_BYTES="$bytes_documents" \
  LOFT_COMMIT="$(git rev-parse HEAD 2>/dev/null || echo unknown)" \
  python3 - "$DEST/manifest.json" <<'PY'
import json
import os
import sys


def database(name: str) -> dict[str, object]:
    key = name.upper()
    return {
        "database": os.environ[f"{key}_DB"],
        "dump": f"{name}.dump",
        "bytes": int(os.environ[f"{key}_BYTES"]),
        "sha256": os.environ[f"{key}_SHA"],
        # The schema version the dump was taken at. restore.sh REFUSES a
        # revision its own migration tree does not know (a backup from a NEWER
        # Loft) and migrates forward LOUDLY when it is an ancestor of head.
        "alembic_revision": os.environ[f"{key}_REV"],
        # Exact per-table row counts, re-checked after restore: a partial
        # restore that lost rows is caught by arithmetic, not by hoping.
        "row_counts": json.loads(os.environ[f"{key}_COUNTS"]),
    }


manifest = {
    "format": os.environ["BACKUP_FORMAT"],
    "created_at": os.environ["TIMESTAMP"],
    "loft_commit": os.environ["LOFT_COMMIT"],
    "postgres_server_version": os.environ["SERVER_VERSION"],
    "databases": {name: database(name) for name in ("gateway", "documents")},
    "object_storage": {
        "included": False,
        "reason": (
            "derived: the bucket holds only content-addressed artifacts "
            "(meshes/sha256/*.glb, composed drawing artifacts) that are pure "
            "functions of the feature trees in loft_documents. The first "
            "evaluate after a restore re-derives them byte-identically."
        ),
    },
}
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(manifest, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY

(cd "$DEST" && sha256sums_write gateway.dump documents.dump manifest.json >SHA256SUMS)

echo
echo "backup: wrote $DEST"
echo "  gateway   @ $revision_gateway  $bytes_gateway bytes"
echo "  documents @ $revision_documents  $bytes_documents bytes"
echo "  object storage: NOT included (derived — docs/OPERATIONS.md)"
echo
echo "Restore it with:  scripts/restore.sh $DEST"
