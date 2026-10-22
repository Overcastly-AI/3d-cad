"""A drawing's bill of materials (design §7 BOM), split from
:mod:`loft_wire.drawings` (FILE-SIZE-RATCHET), which re-exports both models."""

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from loft_wire.assemblies import IndentedBomLine

#: Which of the assembly BOM's three views a sheet's parts list shows
#: (DRAWING-PARTS-LIST-LEVEL; SolidWorks' BOM types). ``top_level`` is the
#: default, as in SolidWorks and Fusion; the choice is stored on the sheet.
PartsListStructure = Literal["top_level", "indented", "parts_only"]

#: A new sheet's parts-list structure.
DEFAULT_PARTS_LIST_STRUCTURE: PartsListStructure = "top_level"

# --- §7 BOM — a drawing's item list, DERIVED from the assembly it drafts ----------
#
# THE identity decision (design §7.1, Drawings #4 BOM slice): an item number is
# **derived, never stored**. A drawing does not persist "part X is item 3" — it
# persists nothing at all about the BOM; the numbered list is recomputed from the
# assembly's own stable instance order on every read. This is §3.3's rejected-(A)
# argument applied one document up: storing an index into a list somebody else owns
# is the silent-drift defect class. The consequences are stated, not hidden:
#
# * numbering is FIRST-APPEARANCE over the assembly's `order_index` (its stable
#   display/BOM order), NOT the name-sorted order `GET /assemblies/{id}/bom`
#   reports — so RENAMING a part never renumbers a released print, while adding /
#   removing / reordering an instance does (a real change the drafter made);
# * the assembly is tracked at TIP (§2.3, `ref_pinned_version` is NULL in v1), so
#   `assembly_version` is echoed on every read: a client that cached a BOM can see
#   the source moved under it. Pinning flips this additively with the versioning
#   item, exactly as views/assemblies do;
# * a document deleted while still instanced stays a line with `missing` true and a
#   null name (the shipped `BomLine` honesty, reused verbatim) — the quantity never
#   silently vanishes.


class DrawingBomLine(IndentedBomLine):
    """One NUMBERED line of a drawing's bill of materials (design §7 BOM).

    The shipped assembly :class:`~loft_wire.assemblies.IndentedBomLine` (group
    key + resolved name + `missing` + quantity, and the outline ``item`` /
    ``level`` / ``total_quantity``, reused VERBATIM — no parallel taxonomy)
    plus the one thing a *drawing* adds: the ``item_number`` a balloon stamps.
    ``item`` is the full number shown ('4' or '4.3' in the indented structure);
    ``item_number`` is its last part, the number within the parent line. On a
    top-level or parts-only line ``level`` is 0 and ``item`` is
    ``str(item_number)``.

    ``item_number`` is **derived**, not authored: lines are numbered 1..n in the
    order each referenced document FIRST appears in the assembly's stable instance
    ``order_index``. It is therefore a pure function of the assembly graph — two
    reads of an unchanged assembly number identically, and a part RENAME (which
    re-sorts the name-ordered assembly BOM) leaves every number untouched.
    """

    item_number: int = Field(
        ge=1,
        description="1-based item number within the parent line, DERIVED from "
        "the assembly's stable instance order (first appearance of this "
        "referenced document) — never stored on the drawing, so it can never "
        "drift from the assembly",
    )


def _is_empty_list(value: object) -> bool:
    """``exclude_if`` predicate: an empty list is not serialized."""
    return value == []


def _drop_default(schema: dict[str, Any]) -> None:
    """Keep a defaulted field optional in the generated ts-client."""
    schema.pop("default", None)


class DrawingBomResponse(BaseModel):
    """A drawing sheet's bill of materials — the item list a balloon numbers (§7).

    A pure READ MODEL (no table, no migration): the sheet's single source document
    (the enforced one-sheet-one-source invariant, §2.2) must be an ASSEMBLY, and its
    DIRECT instances are rolled up into numbered :class:`DrawingBomLine` s. TOP
    LEVEL — the assembly BOM's ``lines`` (SolidWorks' default drawing parts list):
    a rigid sub-assembly instance is one ``kind: "assembly"`` line.

    A sheet drafting a PART has no bill of materials: that is a typed
    ``drawing_bom_source_not_assembly`` 422, not a 200 with an empty list — an empty
    BOM would read as "this assembly has no parts", which is a different and false
    statement (the honest-degradation posture the whole drawings pillar takes).

    ``assembly_version`` is the source assembly's ``doc_version`` AT READ TIME. v1
    tracks the assembly TIP (§2.3), so this is the staleness handle: a client that
    balloons a sheet and later reads a different ``assembly_version`` knows the item
    list may have renumbered, without the numbers themselves ever having been stored
    and gone quietly wrong.
    """

    drawing_id: uuid.UUID
    sheet_id: uuid.UUID = Field(description="The sheet whose source was rolled up")
    assembly_id: uuid.UUID = Field(description="The assembly this sheet drafts")
    assembly_version: int = Field(
        ge=0,
        description="The source assembly's `doc_version` at read time — the "
        "staleness handle for a tip-tracking (unpinned) view, §2.3",
    )
    structure: PartsListStructure = Field(
        description="The structure the `lines` are in: the sheet's stored "
        "`parts_list_structure`"
    )
    lines: list[DrawingBomLine] = Field(
        default_factory=list["DrawingBomLine"],
        description="The numbered lines in the sheet's structure: one per "
        "directly-referenced document (top_level), those with every "
        "sub-assembly's lines beneath it, depth first (indented), or one per "
        "part at every level (parts_only). Derived `item` order; an assembly "
        "with no instances yields an empty list",
    )
    total_instances: int = Field(
        ge=0, description="Sum of the top-level quantities (direct-instance count)"
    )
    total_parts: int = Field(
        ge=0,
        description="Every placed part at every level (the parts-only total)",
    )
    unresolved_patterns: list[uuid.UUID] = Field(
        default_factory=list["uuid.UUID"],
        exclude_if=_is_empty_list,
        json_schema_extra=_drop_default,
        description="Hole-driven component patterns whose count could not be "
        "resolved: only their seeds are counted. Omitted while empty.",
    )


class SheetPartsList(BaseModel):
    """A stored sheet's parts-list choice, mixed into ``SheetResponse``."""

    parts_list_structure: PartsListStructure = Field(
        description="Which BOM structure the sheet's parts list shows "
        "(top_level by default; DRAWING-PARTS-LIST-LEVEL)"
    )


class SheetPartsListUpdate(BaseModel):
    """The parts-list choice a sheet update may carry, mixed into ``SheetUpdate``."""

    parts_list_structure: PartsListStructure | None = Field(
        default=None,
        description="The parts list's structure: top_level, indented or "
        "parts_only (None leaves it unchanged)",
    )
