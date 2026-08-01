"""folders: a per-drawer filing tree, and per-FOLDER document name uniqueness

Backs #WS2 — the half of the workspace row #WS1 deliberately did not ship,
because a folder rail in front of nothing is the over-claiming defect this repo
keeps closing. Contract and the four decisions behind it:
:mod:`py_kit.schemas.folders`.

Three changes, in one revision because the third is only correct alongside the
first two:

1. **``folders``** — id / owner_id / kind / name / parent_id (self-FK,
   ``ON DELETE RESTRICT``) / timestamps. ``kind`` pins the drawer: the registers
   are per-kind surfaces, so a shared tree would put folders in the parts drawer
   that hold no parts. Sibling-name uniqueness is a PAIR of partial unique
   indexes (below).

2. **``folder_id`` on parts / assemblies / drawings** — NULLABLE, ``ON DELETE
   RESTRICT``. NULL is "unfiled": every existing row backfills to it for free,
   it needs no per-owner root row to be minted (and therefore cannot be
   missing), and RESTRICT is what makes "delete a folder" structurally unable to
   delete a document. Nullable column + FK = catalog-only ALTER on Postgres, no
   table rewrite.

3. **``UNIQUE (owner_id, name)`` → per-folder uniqueness**, on all three tables.
   Without this, two folders could not each hold a "Bracket", which is most of
   the point of folders. It is a PAIR of PARTIAL unique indexes, not one
   composite UNIQUE, because SQL treats NULLs as distinct:
   ``UNIQUE (owner_id, folder_id, name)`` would refuse two "Bracket"s in one
   folder while silently permitting two *unfiled* ones — uniqueness that stops
   applying in the state most documents are in. Postgres 15's ``NULLS NOT
   DISTINCT`` would also work but is Postgres-only, and the unit suite and the
   native boot run on SQLite; partial indexes render identically on both, so the
   rule under test is the rule in production. A third, plain index on
   ``owner_id`` replaces the owner-scoped list scan the dropped constraint's
   backing index used to provide for free — a partial index cannot serve it.

DOWNGRADE re-creates the old ``UNIQUE (owner_id, name)``. That can fail if two
same-named documents exist in different folders — which is exactly the state
this migration exists to permit. It is left to fail loudly rather than resolved
by renaming or deleting a user's documents behind their back.

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from py_kit.schemas.folders import FOLDER_NAME_MAX_LENGTH

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The three tables that gain a ``folder_id`` and per-folder name uniqueness.
_FILED_TABLES = ("parts", "assemblies", "drawings")

#: Old per-owner unique constraint names, dropped in favour of the pair above.
_OLD_UNIQUE = {
    "parts": "uq_parts_owner_name",
    "assemblies": "uq_assemblies_owner_name",
    "drawings": "uq_drawings_owner_name",
}


def upgrade() -> None:
    op.create_table(
        "folders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(FOLDER_NAME_MAX_LENGTH), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["folders.id"],
            name="fk_folders_parent",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "uq_folders_parent_name",
        "folders",
        ["owner_id", "kind", "parent_id", "name"],
        unique=True,
        postgresql_where=sa.text("parent_id IS NOT NULL"),
        sqlite_where=sa.text("parent_id IS NOT NULL"),
    )
    op.create_index(
        "uq_folders_root_name",
        "folders",
        ["owner_id", "kind", "name"],
        unique=True,
        postgresql_where=sa.text("parent_id IS NULL"),
        sqlite_where=sa.text("parent_id IS NULL"),
    )
    op.create_index("ix_folders_owner_kind", "folders", ["owner_id", "kind"])

    for table in _FILED_TABLES:
        op.add_column(table, sa.Column("folder_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_folder",
            table,
            "folders",
            ["folder_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.drop_constraint(_OLD_UNIQUE[table], table, type_="unique")
        op.create_index(
            f"uq_{table}_folder_name",
            table,
            ["owner_id", "folder_id", "name"],
            unique=True,
            postgresql_where=sa.text("folder_id IS NOT NULL"),
            sqlite_where=sa.text("folder_id IS NOT NULL"),
        )
        op.create_index(
            f"uq_{table}_unfiled_name",
            table,
            ["owner_id", "name"],
            unique=True,
            postgresql_where=sa.text("folder_id IS NULL"),
            sqlite_where=sa.text("folder_id IS NULL"),
        )
        op.create_index(f"ix_{table}_owner", table, ["owner_id"])


def downgrade() -> None:
    for table in _FILED_TABLES:
        op.drop_index(f"ix_{table}_owner", table_name=table)
        op.drop_index(f"uq_{table}_unfiled_name", table_name=table)
        op.drop_index(f"uq_{table}_folder_name", table_name=table)
        # Can fail by design when two folders each hold a same-named document —
        # see the module docstring; nothing here silently renames user data.
        op.create_unique_constraint(_OLD_UNIQUE[table], table, ["owner_id", "name"])
        op.drop_constraint(f"fk_{table}_folder", table, type_="foreignkey")
        op.drop_column(table, "folder_id")
    op.drop_index("ix_folders_owner_kind", table_name="folders")
    op.drop_index("uq_folders_root_name", table_name="folders")
    op.drop_index("uq_folders_parent_name", table_name="folders")
    op.drop_table("folders")
