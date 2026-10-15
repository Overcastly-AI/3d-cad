"""In-context references (ASM-A3-IN-CONTEXT, RESEARCH §24).

A sketch entity of one part projected from an edge of ANOTHER component of an
assembly: Fusion 360's Edit in Place projection, SolidWorks' external
reference. The link lives on the entity (``SketchProjection.in_context``), so
it is stored, versioned, undone and exported with the sketch, and no table
changes.

Who does what (CLAUDE.md boundaries): geometry resolves a link inside an
assembly evaluation and reports it (:class:`InContextStatus`); documents owns
the stored link and its last resolved value (:class:`InContextResolvedWrite`);
the gateway carries one to the other.

The last resolved value (``resolved``) is a 3D curve in the EDITED part's own
frame. The sketch rebuild projects it onto the sketch plane, so the part
rebuilds the same way inside its context assembly and outside it (SolidWorks'
"out of context": the last values are kept until the context is opened again).
"""

import uuid
from typing import Annotated, Any, Literal, cast

from pydantic import BaseModel, Field

from loft_wire.geometry import Vec3
from loft_wire.signatures import EdgeSignature

#: How many in-context links one request may report (a work bound, like the
#: entity bound of a sketch: one per projected entity of every placed part).
MAX_IN_CONTEXT_LINKS = 2000


def _absent(value: object) -> bool:
    """``exclude_if``: an unset optional is not serialized."""
    return value is None


class InContextLine(BaseModel):
    """A resolved straight edge: ``start`` is the end the entity's ``start``
    follows."""

    kind: Literal["line"]
    start: Vec3
    end: Vec3


class InContextCircle(BaseModel):
    """A resolved full circle."""

    kind: Literal["circle"]
    center: Vec3
    normal: Vec3 = Field(description="Unit axis of the circle")
    radius: float = Field(gt=0, description="Radius (mm)")


class InContextArc(BaseModel):
    """A resolved circular arc through three of its points, in curve order."""

    kind: Literal["arc"]
    start: Vec3
    mid: Vec3
    end: Vec3


#: The edge as last resolved, in the edited part's frame (mm).
InContextCurve = Annotated[
    InContextLine | InContextCircle | InContextArc, Field(discriminator="kind")
]


class InContextLink(BaseModel):
    """An associative reference to an edge of another component.

    ``assembly_id`` is the context: only an evaluation of that assembly
    resolves the link. ``host_occurrence_id`` is the occurrence of the edited
    part the sketch was drawn in (the part may be placed more than once; this
    one is the frame). ``occurrence_id`` is the referenced component and
    ``part_id`` the part it placed when picked, so a replaced component is an
    error, never a silent re-attachment. Occurrence ids are the ASM-A3 chain
    (:func:`loft_wire.assemblies.occurrence_id`). ``edge`` is the picked
    edge's signature in the referenced part's own frame.
    """

    assembly_id: uuid.UUID
    host_occurrence_id: uuid.UUID
    occurrence_id: uuid.UUID
    part_id: uuid.UUID
    edge: EdgeSignature
    resolved: InContextCurve | None = Field(
        default=None,
        exclude_if=_absent,
        description=(
            "The edge as the context assembly last resolved it, in the edited "
            "part's frame. The sketch rebuild projects it, in and out of "
            "context. Written by the assembly evaluation (through the "
            "gateway); absent until the first one, when the entity keeps the "
            "coordinates it was drawn with."
        ),
    )


#: Why a link did not resolve in its context assembly. ``component_missing``:
#: the referenced occurrence is no longer in the assembly; ``component_replaced``:
#: it now places another part; ``component_failed``: its part made no body;
#: ``host_missing``: the edited part is no longer at its host occurrence;
#: ``edge_unresolved`` / ``edge_ambiguous``: the edge is gone, or matches more
#: than one; ``unsupported_curve``: it is no longer a line or a circle;
#: ``cycle``: the link is part of a loop of links; ``not_converged``: the
#: assembly kept moving as the links updated.
InContextReason = Literal[
    "component_missing",
    "component_replaced",
    "component_failed",
    "host_missing",
    "edge_unresolved",
    "edge_ambiguous",
    "unsupported_curve",
    "cycle",
    "not_converged",
]


class InContextStatus(BaseModel):
    """How one in-context link resolved in this assembly evaluation.

    ``error`` keeps the entity at its last resolved geometry; the dependent
    sketch (``feature_id``) shows it. ``changed`` says ``resolved`` differs
    from what the request carried, so the gateway writes it back.
    """

    part_id: uuid.UUID = Field(description="The edited (dependent) part")
    feature_id: uuid.UUID = Field(description="The dependent sketch")
    entity_id: str
    occurrence_id: uuid.UUID = Field(description="The referenced component")
    state: Literal["ok", "error"]
    reason: InContextReason | None = None
    message: str | None = None
    resolved: InContextCurve | None = None
    changed: bool = False


class InContextResolvedItem(BaseModel):
    """One link's new last-resolved value, for documents to store."""

    feature_id: uuid.UUID
    entity_id: str = Field(min_length=1, max_length=64)
    assembly_id: uuid.UUID
    occurrence_id: uuid.UUID
    resolved: InContextCurve


class InContextResolvedWrite(BaseModel):
    """``POST /api/v1/parts/{part_id}/in-context/resolved`` (documents).

    Metadata, not an edit: no undo step and no ``tree_version`` bump (the
    DESIGN-INTENT-BACKFILL rule). An item is written only where the entity
    still carries a link to the same assembly and occurrence.
    """

    items: list[InContextResolvedItem] = Field(max_length=MAX_IN_CONTEXT_LINKS)


class InContextResolvedResult(BaseModel):
    """How many of the items were written (the rest no longer matched)."""

    written: int
    skipped: int


def _dict(value: Any) -> dict[str, Any] | None:
    return cast(dict[str, Any], value) if isinstance(value, dict) else None


def _links_of(params: Any) -> dict[str, dict[str, Any]]:
    """``entity id -> in_context link`` of a sketch's JSON params."""
    out: dict[str, dict[str, Any]] = {}
    sketch = _dict(params)
    entities: Any = None if sketch is None else sketch.get("entities")
    if not isinstance(entities, list):
        return out
    for item in cast(list[Any], entities):
        entity = _dict(item)
        projection = None if entity is None else _dict(entity.get("projection"))
        link = None if projection is None else _dict(projection.get("in_context"))
        if entity is not None and link is not None:
            out[str(entity.get("id"))] = link
    return out


def _same_link(a: dict[str, Any], b: dict[str, Any]) -> bool:
    keys = ("assembly_id", "host_occurrence_id", "occurrence_id", "part_id", "edge")
    return all(a.get(k) == b.get(k) for k in keys)


def carry_resolved(stored: Any, incoming: Any) -> Any:
    """*incoming* sketch params with each unchanged link's ``resolved`` taken
    from *stored*.

    ``resolved`` is the context assembly's to write: a client that read the
    sketch before a write-back must not save the older value over it. A link
    the client changed (another edge, another component) keeps its own.
    Mutates and returns *incoming* (JSON params).
    """
    before = _links_of(stored)
    if not before:
        return incoming
    for entity_id, link in _links_of(incoming).items():
        old = before.get(entity_id)
        if old is None or not _same_link(old, link):
            continue
        if "resolved" in old:
            link["resolved"] = old["resolved"]
    return incoming


def apply_resolved(params: Any, item: InContextResolvedItem) -> bool:
    """Write *item* into the JSON sketch *params* in place; whether it applied
    (the entity still links to the same assembly and occurrence)."""
    link = _links_of(params).get(item.entity_id)
    if link is None:
        return False
    if link.get("assembly_id") != str(item.assembly_id) or link.get(
        "occurrence_id"
    ) != str(item.occurrence_id):
        return False
    value = item.resolved.model_dump(mode="json")
    if link.get("resolved") == value:
        return False
    link["resolved"] = value
    return True


def linked_parts(params: Any) -> set[uuid.UUID]:
    """The part ids a sketch's JSON *params* link to in context."""
    out: set[uuid.UUID] = set()
    for link in _links_of(params).values():
        try:
            out.add(uuid.UUID(str(link.get("part_id"))))
        except ValueError:
            continue
    return out
