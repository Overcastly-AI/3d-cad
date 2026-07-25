"""views: one view per projection per sheet

Adds ``uq_views_sheet_projection`` UNIQUE ``(sheet_id, projection)`` — the
schema statement of what the whole drawing stack already assumed (engineering
audit **H3**). Views are keyed by PROJECTION everywhere downstream: the
composer accumulates anchors into a ``dict[ViewProjection, Vec2]`` and dedupes
``layout.views`` through a set, and the frontend builds
``viewIdByProjection``/``viewByProjection`` maps. A second view of the same
projection on one sheet therefore (a) never composed — it was silently dropped
from the sheet — and (b) made the drag-to-place ``PATCH /views/{id}`` persist
the dragged position onto the OTHER view's row: corruption of a persisted
document from a UI gesture.

Pre-existing duplicates are removed before the constraint is added, keeping the
LOWEST ``order_index`` per ``(sheet_id, projection)`` — the view that was
legally created; the shadowed rows were invisible in every composed sheet and
every export, so nothing that was ever drawn is lost. Deleting mid-scope leaves
holes in ``views.order_index``, and the append position is ``count(*)``, so the
remaining views are renumbered dense afterwards. The renumber parks every index
above any legitimate value first (``+ 1000000``) so no intermediate row can
collide with a not-yet-updated one under the IMMEDIATE ``uq_views_sheet_order``
check (the constraint is NOT deferrable — documents/db.py).

The ORM twin lives in ``documents.db.View.__table_args__``, so the
``metadata.create_all`` path used by the native boot / unit suites (the dialect
split documented in documents/db.py) enforces it too.

Downgrade drops the constraint only — the de-duplication is not reversible, and
the dropped rows were never renderable.

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Offset that parks in-flight ``order_index`` values above any real one during
#: the dense renumber (a sheet holds at most ``MAX_DRAWING_VIEWS`` == 32 views).
_RENUMBER_OFFSET = 1000000


def upgrade() -> None:
    # 1. Drop the shadowed duplicates (keep the lowest order_index per projection).
    op.execute(
        sa.text(
            "DELETE FROM views WHERE id IN ("
            "  SELECT id FROM ("
            "    SELECT id, row_number() OVER ("
            "      PARTITION BY sheet_id, projection ORDER BY order_index, id"
            "    ) AS rn FROM views"
            "  ) ranked WHERE ranked.rn > 1"
            ")"
        )
    )
    # 2. Park every remaining index out of the way, then renumber dense — the
    #    delete above can leave holes, and the append position is count(*).
    op.execute(
        sa.text(f"UPDATE views SET order_index = order_index + {_RENUMBER_OFFSET}")
    )
    op.execute(
        sa.text(
            "UPDATE views SET order_index = ranked.new_index FROM ("
            "  SELECT id, (row_number() OVER ("
            "    PARTITION BY sheet_id ORDER BY order_index, id"
            "  ) - 1) AS new_index FROM views"
            ") AS ranked WHERE views.id = ranked.id"
        )
    )
    # 3. The invariant itself.
    op.create_unique_constraint(
        "uq_views_sheet_projection", "views", ["sheet_id", "projection"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_views_sheet_projection", "views", type_="unique")
