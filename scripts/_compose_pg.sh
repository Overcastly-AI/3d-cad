# shellcheck shell=bash
# Shared plumbing for the backup/restore scripts. SOURCED, never executed.
#
#   source "$(dirname "$0")/_compose_pg.sh"
#
# One implementation of "talk to the stack's Postgres" for scripts/backup.sh and
# scripts/restore.sh, because the two MUST agree: the row counts the backup
# records and the row counts the restore re-checks are the same query, and a
# drift between them would silently weaken the only arithmetic that can catch a
# partial restore (CLAUDE.md DRY rule).
#
# Everything runs INSIDE the db container via `docker compose exec`, so a
# self-hoster needs no host Postgres client and the client major version always
# matches the server that wrote the data.
#
# bash 3.2-compatible on purpose (no `declare -A`, no `${x^^}`): the system bash
# on macOS is 3.2 and Docker Desktop is a real self-host target.

POSTGRES_USER="${POSTGRES_USER:-loft}"
GATEWAY_DB="${GATEWAY_DB:-loft_gateway}"
DOCUMENTS_DB="${DOCUMENTS_DB:-loft_documents}"

#: Prefix for every message; each script sets it before sourcing or after.
SCRIPT_NAME="${SCRIPT_NAME:-$(basename "${BASH_SOURCE[1]:-loft}")}"

step() { printf '\n== %s ==\n' "$*"; }

# fail "message" [exit-code]
fail() {
  echo "$SCRIPT_NAME: FAILED — $1" >&2
  exit "${2:-1}"
}

# The database a schema-owning service owns.
database_for() {
  case "$1" in
    gateway) echo "$GATEWAY_DB" ;;
    documents) echo "$DOCUMENTS_DB" ;;
    *) fail "unknown service '$1'" ;;
  esac
}

# psql inside the db container: tuples-only, unaligned, no psqlrc, script read
# from stdin so SQL can carry quotes without shell-escaping games.
# ON_ERROR_STOP is not optional — without it psql exits 0 on a failed query and
# a missing table looks exactly like an empty answer. PGPASSWORD is forwarded
# when the caller has it; the official postgres image trusts the local unix
# socket, so it usually is not needed.
psql_q() {
  docker compose exec -T -e PGPASSWORD="${POSTGRES_PASSWORD:-}" db \
    psql -U "$POSTGRES_USER" -d "$1" -tAXq -v ON_ERROR_STOP=1 -f -
}

require_db_running() {
  docker compose exec -T db pg_isready -U "$POSTGRES_USER" >/dev/null 2>&1 || fail \
    "the 'db' service is not accepting connections. Bring it up first:
  docker compose up -d db"
}

#: The alembic revision a database is at ('' and non-zero exit if unmigrated).
alembic_revision_of() {
  psql_q "$1" <<<'SELECT version_num FROM alembic_version;' | tr -d ' '
}

# EXACT row counts for every base table in the public schema, as a JSON object.
# Generic, so it keeps working across schema changes instead of pinning today's
# table list — and exact, because `n_live_tup` in pg_stat_user_tables is an
# ESTIMATE, which would make the backup-vs-restore comparison meaningless.
table_counts() {
  psql_q "$1" <<'SQL'
SELECT coalesce(json_object_agg(t.name, t.rows), '{}'::json)::text
FROM (
  SELECT c.relname AS name,
         (xpath(
            '/row/c/text()',
            query_to_xml(
              format('SELECT count(*) AS c FROM %I.%I', n.nspname, c.relname),
              false, true, ''
            )
          ))[1]::text::bigint AS rows
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE c.relkind = 'r' AND n.nspname = 'public'
) t;
SQL
}

# sha256sum (coreutils) or shasum -a 256 (macOS).
sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | cut -d' ' -f1
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | cut -d' ' -f1
  else
    fail "no sha256sum or shasum on PATH — cannot checksum the dumps"
  fi
}

sha256sums_write() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$@"
  else
    shasum -a 256 "$@"
  fi
}

sha256sums_check() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum -c --quiet SHA256SUMS
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 -c -s SHA256SUMS
  else
    echo "$SCRIPT_NAME: no sha256 tool on PATH — integrity unverified" >&2
  fi
}
