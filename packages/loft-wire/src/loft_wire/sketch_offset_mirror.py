"""Sketch offset and mirror — request and result DTOs.

Split out of :mod:`loft_wire.sketch` (FILE-SIZE-RATCHET, SKETCH-POINT-DISTANCE)
as :mod:`loft_wire.sketch_corner` was: the shapes are unchanged, so the
generated contracts are too.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from loft_wire.sketch import MAX_SKETCH_ENTITIES, EntityId, Point2D, SketchEntity

# ---------------------------------------------------------------------------
# Sketch editing — offset (BACKLOG #3, backend)
# ---------------------------------------------------------------------------
#
# Offset is the standard rib/web/wall-profile tool: a **parallel copy** of a
# curve at a signed distance. Like trim/extend it is a **server-side geometry
# operation** (RESEARCH §3 + CLAUDE.md service boundaries) — the frontend must
# not reimplement offset math — served at ``POST /api/v1/sketch/offset`` and
# gateway-proxied auth-gated at ``/api/v1/geometry/sketch/offset``. It is
# stateless and deterministic (RESEARCH §9): identical input yields
# coordinate-identical output, computed by **exact closed-form analytic**
# geometry (no solver iteration), matching the trim/extend choice.
#
# Unlike trim (which *rewrites* the target), offset **ADDS** geometry: the
# source entity is returned unchanged in the caller's set and the result
# carries only the NEW offset entity, with a fresh deterministic id
# ``f"{target}.{n}"`` (lowest ``n`` >= 2 not already in use) and the source's
# construction flag inherited. Re-mapping/constraining the new entity is the
# caller's job (the geometry op is constraint-free by design, same as
# trim/extend).
#
# **Sign convention (documented, uniform across kinds).** The copy is displaced
# along the target curve's **left-hand normal** — the curve's forward direction
# rotated +90° (counter-clockwise). ``+distance`` = left of the directed curve,
# ``-distance`` = right. For a line directed start→end this is the familiar
# perpendicular offset, e.g. ``(0,0)→(10,0)`` offset ``+2`` → ``(0,2)→(10,2)``.
# Because a circle/arc is traversed **counter-clockwise**, its left-hand normal
# points **inward** (toward the center), so ``+distance`` shrinks the radius
# (``radius - distance``, same center/angular span) and ``-distance`` grows it;
# an inward offset that would drive the radius to ≤ 0 is a degenerate error.
#
# **v1 scope (honest).** Single-entity offset (line / arc / circle) is shipped.
# Chain offset — a connected run of curves offset together with miter/arc join
# handling — is DEFERRED (it is more than a clean increment: it needs join
# construction and self-intersection trimming). Callers offset one entity at a
# time in v1.


class SketchOffsetRequest(BaseModel):
    """Input for a sketch offset (stateless, one-shot).

    ``entities`` is the whole sketch's entity list — passed so the new offset
    entity gets a fresh id that cannot collide with an existing one (and to
    mirror the trim/extend contract). ``target`` names the entity to offset; it
    MUST be present in ``entities`` (else a 422 ``sketch_target_not_found``).
    ``distance`` is the **signed** offset distance in millimetres (see the
    module comment above for the left-hand-normal sign convention); it must be
    a nonzero, finite value (else 422 ``sketch_offset_zero_distance``).
    """

    entities: list[SketchEntity] = Field(
        max_length=MAX_SKETCH_ENTITIES,
        description="The whole sketch's entities (offset ADDS to this set; the "
        "source stays unchanged), bounded by MAX_SKETCH_ENTITIES (work bound, "
        "audit G2).",
    )
    target: EntityId = Field(
        description="Id of the entity to offset; must be in `entities`."
    )
    distance: float = Field(
        description="Signed offset distance (mm): +distance = left of the "
        "directed curve (a CCW arc/circle's left normal points inward, so "
        "+distance shrinks its radius). Must be nonzero and finite."
    )

    @model_validator(mode="after")
    def _unique_entity_ids(self) -> "SketchOffsetRequest":
        seen: set[str] = set()
        for entity in self.entities:
            if entity.id in seen:
                raise ValueError(f"Duplicate sketch entity id: {entity.id!r}")
            seen.add(entity.id)
        return self


class SketchOffsetResult(BaseModel):
    """Output of an offset: the NEW offset entity/entities (source unchanged).

    Offset **adds** geometry, so — unlike :class:`SketchEditResult` (which
    returns the whole rewritten set) — this carries ONLY the newly created
    offset entities. In v1 that is exactly one entity, with a fresh
    deterministic id ``f"{target}.{n}"`` and the source's construction flag
    inherited. The caller appends these to its own entity list. Deterministic:
    identical input yields identical output entities, coordinates included
    (RESEARCH §9).
    """

    entities: list[SketchEntity] = Field(
        description="The newly created offset entities (source entities are "
        "unchanged and NOT echoed here). One entity in v1 (single-entity "
        'offset); fresh id `f"{target}.{n}"`, construction flag inherited.'
    )

    @model_validator(mode="after")
    def _unique_entity_ids(self) -> "SketchOffsetResult":
        # Internal-uniqueness guard for the returned batch (trivial at one
        # entity in v1; future-proofs chain offset, which returns several).
        seen: set[str] = set()
        for entity in self.entities:
            if entity.id in seen:
                raise ValueError(f"Duplicate sketch entity id: {entity.id!r}")
            seen.add(entity.id)
        return self


# ---------------------------------------------------------------------------
# Sketch editing — mirror (BACKLOG #4, backend)
# ---------------------------------------------------------------------------
#
# Mirror is the standard symmetric-profile tool: reflect selected entities
# about an axis line, appending the reflected COPIES. Like trim/extend/offset
# it is a **server-side geometry operation** (RESEARCH §3 + CLAUDE.md service
# boundaries) — the frontend must not reimplement reflection math — served at
# ``POST /api/v1/sketch/mirror`` and gateway-proxied auth-gated at
# ``/api/v1/geometry/sketch/mirror``. It is stateless and deterministic
# (RESEARCH §9): identical input yields coordinate-identical output, computed
# by **exact closed-form analytic** reflection (a rational foot-of-perpendicular
# — no sqrt, no trig, no solver iteration), matching the trim/extend/offset
# choice.
#
# **Mirror the OP is not the ``symmetric`` CONSTRAINT.** They are deliberately
# distinct concepts and must not be conflated:
#
# * :class:`SymmetricConstraint` is a *constraint* the solver enforces on two
#   points that ALREADY exist — it keeps them mirror images as the sketch is
#   dragged/dimensioned. It creates no geometry.
# * The mirror *operation* here CREATES new reflected copies of whole entities
#   in one shot. A named ❌ Sketching-scorecard blocker (docs/COMPETITIVE.md):
#   symmetric profiles with more than a couple of point-pairs need this op, not
#   one ``symmetric`` constraint per pair.
#
# **v1 scope (honest).** Mirror is **geometry-only**: it appends the reflected
# copies and does NOT auto-add ``symmetric`` constraints between each source and
# its copy. Pairing source↔copy with symmetric constraints (a live-linked
# mirror) is deferred; callers who want that add the constraints themselves. The
# op mints a fresh deterministic id ``f"{source}.{n}"`` per copy (seeded from the
# WHOLE sketch's id set so a copy id can never collide with an existing entity or
# another copy) and inherits each source's construction flag.
#
# **Axis representation (documented decision).** The axis is a tagged union so
# both real-world gestures are first-class and DRY (one op, one reflection):
#
# * :class:`MirrorAxisEntity` — mirror about an existing **line** entity, named
#   by id. The common "mirror about this construction centerline" case; the
#   entity must be a line (a circle/arc/point axis is ``sketch_mirror_axis_not_line``).
# * :class:`MirrorAxisPoints` — mirror about the infinite line through two given
#   points ``a``/``b``. More general (no axis entity need exist in the sketch).
#
# Either way a zero-length axis (coincident points / degenerate line) is
# ``sketch_mirror_degenerate_axis``. An entity lying ON the axis reflects to
# itself — a coincident copy with a fresh id (identity reflection is
# well-defined; we do NOT special-case or reject it, avoiding a fragile
# on-axis epsilon test).


class MirrorAxisEntity(BaseModel):
    """Mirror axis named by an existing **line** entity id.

    The cleanest "mirror about this construction centerline" case: ``entity``
    must resolve to a :class:`SketchLine` in the request's ``entities`` (else
    ``sketch_target_not_found``; a non-line axis entity is
    ``sketch_mirror_axis_not_line``). The line's start/end define the axis.
    """

    kind: Literal["entity"]
    entity: EntityId = Field(
        description="Id of the line entity to mirror about; must be in `entities`."
    )


class MirrorAxisPoints(BaseModel):
    """Mirror axis given directly as the infinite line through two points.

    More general than :class:`MirrorAxisEntity` — no axis entity need exist in
    the sketch. ``a`` and ``b`` must be distinct (a zero-length axis is
    ``sketch_mirror_degenerate_axis``).
    """

    kind: Literal["points"]
    a: Point2D = Field(description="First point on the mirror axis line (mm).")
    b: Point2D = Field(description="Second point on the mirror axis line (mm).")


#: The mirror axis: an existing line entity (by id) or two points defining the
#: infinite axis line. Discriminated on ``kind`` (``"entity"`` / ``"points"``).
MirrorAxis = Annotated[
    MirrorAxisEntity | MirrorAxisPoints,
    Field(discriminator="kind"),
]


class SketchMirrorRequest(BaseModel):
    """Input for a sketch mirror (stateless, one-shot).

    ``entities`` is the whole sketch's entity list — passed so each new copy
    gets a fresh id that cannot collide with an existing one (and to resolve a
    :class:`MirrorAxisEntity` axis). ``targets`` names the entities to reflect;
    each MUST be present in ``entities`` (else ``sketch_target_not_found``) and
    at least one is required. ``axis`` is the mirror line (see :data:`MirrorAxis`).

    Mirror **adds** geometry: the sources are untouched and the response carries
    only the NEW reflected copies (see :class:`SketchMirrorResult`). Every entity
    kind is reflectable (point, line, circle, arc). Units are millimetres
    (:mod:`loft_wire.sketch` convention).
    """

    entities: list[SketchEntity] = Field(
        max_length=MAX_SKETCH_ENTITIES,
        description="The whole sketch's entities (mirror ADDS to this set; the "
        "sources stay unchanged), bounded by MAX_SKETCH_ENTITIES (work bound, "
        "audit G2).",
    )
    targets: list[EntityId] = Field(
        min_length=1,
        max_length=MAX_SKETCH_ENTITIES,
        description="Ids of the entities to reflect; each must be in `entities` "
        "(so the list shares its MAX_SKETCH_ENTITIES bound — audit G2).",
    )
    axis: MirrorAxis = Field(
        description="The mirror axis: a line entity id or two points (see MirrorAxis)."
    )

    @model_validator(mode="after")
    def _unique_entity_ids(self) -> "SketchMirrorRequest":
        seen: set[str] = set()
        for entity in self.entities:
            if entity.id in seen:
                raise ValueError(f"Duplicate sketch entity id: {entity.id!r}")
            seen.add(entity.id)
        return self


class SketchMirrorResult(BaseModel):
    """Output of a mirror: the NEW reflected copies (sources unchanged).

    Like :class:`SketchOffsetResult` (and unlike :class:`SketchEditResult`),
    mirror **adds** geometry, so this carries ONLY the newly created copies —
    one per ``target``, in ``targets`` order — each with a fresh deterministic
    id ``f"{source}.{n}"`` (lowest ``n`` >= 2 not already in use, seeded from the
    whole sketch AND the copies already minted) and the source's construction
    flag inherited. The caller appends these to its own entity list.

    Reflection reverses orientation, so a mirrored **arc** has its start/end
    **swapped** (``start`` = reflected source ``end``, ``end`` = reflected source
    ``start``) to preserve the CCW-from-start invariant :class:`SketchArc`
    documents. Deterministic: identical input yields identical output entities,
    coordinates included (RESEARCH §9).
    """

    entities: list[SketchEntity] = Field(
        description="The newly created mirrored copies (sources are unchanged and "
        'NOT echoed here). One per target; fresh id `f"{source}.{n}"`, '
        "construction flag inherited, arcs start/end-swapped for CCW."
    )

    @model_validator(mode="after")
    def _unique_entity_ids(self) -> "SketchMirrorResult":
        # Defense in depth (same posture as SketchEditResult/SketchOffsetResult):
        # a minted copy id must never collide with another copy's. The op seeds
        # its id generator from the whole sketch plus the copies already minted;
        # enforcing uniqueness here fails a regression loudly at the boundary.
        seen: set[str] = set()
        for entity in self.entities:
            if entity.id in seen:
                raise ValueError(f"Duplicate sketch entity id: {entity.id!r}")
            seen.add(entity.id)
        return self
