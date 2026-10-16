"""The multi-body ``merge`` field every additive body feature shares.

Moved out of :mod:`loft_wire.features` unchanged (FILE-SIZE-RATCHET); that
module re-exports it, so ``from loft_wire.features import MERGE_FIELD`` keeps
working.
"""

from pydantic import Field

#: The multi-body "Merge result" flag (docs/design/multi-body.md §MB-0,
#: Decision 2), shared by every ADDITIVE body-affecting feature
#: (extrude/revolve/sweep/loft) — CLAUDE.md DRY rule, one definition. It applies
#: to the ADD operation only: ``True`` fuses the new solid into the ACTIVE body
#: (the historical single-body behaviour, and the "create the first body if none
#: exists yet" case); ``False`` STARTS a new active body — the second-body path
#: that lets a part end with more than one lump. Ignored for a CUT (which always
#: modifies the active body). Additive-optional and defaulting ``True``, so
#: legacy rows (persisted with no ``merge`` key) read ``True`` and behave exactly
#: as before — the ``flip``/``direction`` idiom, NO ``param_version`` bump.
MERGE_FIELD = Field(
    default=True,
    description=(
        "Merge result (ADD only): True fuses the new solid into the active body "
        "(default, historical single-body behaviour / starts the first body); "
        "False starts a NEW body (multi-body, design multi-body.md §MB-0). "
        "Ignored for a CUT. Additive — absent reads True, no param_version bump."
    ),
)
