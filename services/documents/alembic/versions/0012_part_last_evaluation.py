"""parts: add the last-evaluate record (status + timestamp + tree version)

Adds three NULLABLE columns to ``parts`` — ``last_eval_status VARCHAR(16)``,
``last_eval_at TIMESTAMPTZ``, ``last_eval_tree_version BIGINT`` — the bounded,
fixed-size record behind a register's rebuild-health column
(docs/design/feature-tree.md §4.4a; UI review 2026-07-30). All-NULL is the
honest ``never evaluated`` state, so every pre-existing part backfills to "we
have never asked" with no data migration and no server default: there is no
value that would be true of a part nobody evaluated.

``last_eval_tree_version`` is the load-bearing one. A bare status would be a
claim about a tree that has since moved — the "confidently wrong" failure mode
stored BOM item numbers were rejected for (docs/design/drawings.md §8a.1) — so
the version the result belongs to is stored beside it and
``py_kit.schemas.parts.derive_part_eval_state`` folds the pair against the
part's CURRENT ``tree_version`` into ``never``/``ok``/``failed``/``stale``.
Nothing is stored that could go stale unnoticed: staleness is derived.

Evaluation RESULTS are still not persisted (§4.4 stands — they are a pure
function of the tree and stay derivable/disposable); this is only the verdict.

Nullable columns need no rewrite on Postgres (catalog-only ALTER), and the ORM
metadata renders the same three columns on SQLite, so the ``create_all`` path
the native boot and ``just e2e`` use picks them up too (the dialect split is
documented in documents/db.py).

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("parts", sa.Column("last_eval_status", sa.String(16), nullable=True))
    op.add_column(
        "parts",
        sa.Column("last_eval_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "parts", sa.Column("last_eval_tree_version", sa.BigInteger(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("parts", "last_eval_tree_version")
    op.drop_column("parts", "last_eval_at")
    op.drop_column("parts", "last_eval_status")
