#!/bin/sh
# Create one database PER SCHEMA-OWNING SERVICE on first boot of the volume.
#
# WHY (found by scripts/compose-smoke.sh, the first real run of the compose
# stack): gateway and documents each own an independent alembic tree, and both
# trees start at revision "0001" and use alembic's DEFAULT `alembic_version`
# table. Pointed at ONE database they collide — the service migrated second
# reads the other's "0001" as its own, skips its first revision, and either
# leaves tables missing or dies on a foreign key to a table that was never
# created. Separate databases are also the correct boundary (CLAUDE.md: a
# service owns its schema), so the split is the fix, not a workaround.
#
# The postgres image runs /docker-entrypoint-initdb.d/*.sh exactly once, on an
# EMPTY data directory. An existing `db-data` volume is NOT re-initialised:
# wipe it (`docker compose down -v`) or create the databases by hand.
set -eu

for database in "${GATEWAY_DB:-loft_gateway}" "${DOCUMENTS_DB:-loft_documents}"; do
  echo "init: creating database ${database}"
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -c "CREATE DATABASE \"${database}\" OWNER \"${POSTGRES_USER}\""
done
