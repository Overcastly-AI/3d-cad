"""parts: record HOW MUCH of the tree the last evaluate looked at

Adds one NULLABLE column, ``parts.last_eval_scope VARCHAR(16)`` — ``'whole'`` or
``'rolled_back'`` — completing the last-evaluate record 0012 started
(docs/design/feature-tree.md §4.4a; engineering audit J3, 2026-07-30).

The defect it closes: documents applies the rollback bar BEFORE the evaluate
request leaves (§3), so a part rolled back to feature 2 of 9 evaluates two
features, succeeds, and the stored status is ``ok`` — a verdict on a PREFIX,
which the register then rendered as "Clean", a claim about a part whose
remaining seven features nobody looked at. The status column cannot be made to
say this: "did what ran build?" and "how much ran?" are independent (a
rolled-back tree can also fail), so the scope is a second column, not a fifth
status value.

Written by DOCUMENTS, not by the caller: the gateway never learns that rollback
exists (that is the point of applying the bar upstream of it), so there is no
honest way to make this a field on the record request.

NULL is "unknown", and deliberately not backfilled to ``'whole'``: a row written
before this column existed genuinely does not know its scope, and defaulting it
would re-create the exact over-claim above. Consumers read null as unqualified
(``derive_part_eval_scope`` returns it only alongside a live verdict), and the
part's next evaluate — which every open triggers — writes the real value.

Nullable column, no server default: catalog-only ALTER on Postgres, no rewrite,
and the ORM metadata renders the same column on SQLite so the ``create_all``
path the native boot and ``just e2e`` use picks it up too (dialect split
documented in documents/db.py).

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("parts", sa.Column("last_eval_scope", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("parts", "last_eval_scope")
