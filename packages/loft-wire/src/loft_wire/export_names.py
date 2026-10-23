"""The names an export carries: a document's name and its download slug.

Moved out of :mod:`loft_wire.features` (which re-exports them) to keep that
module from growing; the rule and its decision are unchanged.
"""

import re
from typing import Annotated

from pydantic import StringConstraints

#: Upper bound for a document name carried on an export request (matches
#: ``PartName`` / ``AssemblyName``, which is where these values come from).
EXPORT_DOCUMENT_NAME_MAX_LENGTH = 200

#: A document's human-readable name, carried on an EXPORT request only.
#:
#: **Why export-only** (the decision, since it looks like it belongs on the
#: evaluate request): a name is presentation metadata, and the evaluation
#: contract deliberately carries only INTENT plus the one non-geometric input
#: mass is derived from (``materials``, materials.md §9a) — length units are kept
#: off it for exactly this reason. But a FILE outlives the screen that explained
#: it: a shop that receives ``a3f2c1e8-....step`` containing ``PRODUCT('SOLID')``
#: cannot tell what it is, and exporting five parts to quote a job means five
#: hand-renames (audit N4). So the name rides the request that produces a file,
#: where it can change the file's NAME and its PRODUCT and nothing else — the
#: kernel never sees it, and evaluation stays byte-identical with or without it.
DocumentName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=EXPORT_DOCUMENT_NAME_MAX_LENGTH,
    ),
]


def document_slug(name: str) -> str:
    """A safe download basename component from a document name.

    THE one slug rule for every download this product names after a document
    (CLAUDE.md DRY): lower-case, non-alphanumeric runs collapsed to a single
    hyphen, edges trimmed. Ported from ``apps/web/src/drawing/exportSvg.ts``
    ``sanitizeDrawingFilename`` and shared by the drawing artifact
    (``artifact_filename``), the part export (:func:`export_tree_filename`) and
    the assembly export (``assembly_export_filename``), so all three name a file
    identically. Returns ``""`` for a name with no alphanumerics at all — the
    caller decides its own fallback, because "drawing" is not a sensible default
    for a part.
    """
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
