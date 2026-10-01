"""Stage-1 subshape signatures: the planar-face and edge fingerprints.

Split out of :mod:`loft_wire.features` (which re-exports both) so that module
stays under the file-size ratchet; the topological-naming commentary that
introduces them is still there, beside the selectors that carry them. Pure
pydantic, no kernel types (CLAUDE.md service boundaries).
"""

from typing import Literal

from pydantic import BaseModel, Field

from loft_wire.geometry import Vec3

#: Upper bound on a stored ``topo_name``. Names are built by
#: ``geometry.kernel.naming``, which digests any face name over 256 characters,
#: so an edge name (two face names) stays well inside this.
TOPO_NAME_MAX_LENGTH = 1024

_TOPO_NAME_DESCRIPTION = (
    "History-based name of the picked subshape (DESIGN-INTENT-REFS): which "
    "feature made it and from what, never where it is, so it survives a "
    "dimension edit that moves it. The resolver tries it after the exact "
    "signature and before the geometric tiers, and only when exactly one "
    "current subshape holds it. Absent on selectors authored before 2026-10-01 "
    "and on subshapes the kernel could not name; resolution is then unchanged."
)


class PlanarFaceSignature(BaseModel):
    """§2b stage-1 geometric fingerprint of a PLANAR face — typed, kernel-free.

    Full-precision invariants (§7.2 forbids quantizing the stored identity): the
    outward unit ``normal``, the area ``centroid`` (world mm), and the
    ``area_mm2``. A planar face is uniquely fixed among a body's faces by
    (normal, centroid, area) in the common case; congruent twins of a symmetric
    part tie and resolve to an honest ``subshape_ambiguous`` (§5), never a guess.
    Matching is nearest-within-tolerance at the documented subshape tolerance
    (geometry.kernel.faces / docs/GEOMETRY-QA.md), never an ad-hoc epsilon.

    OUTER-BOUNDARY INVARIANTS (§12b, GEOM-3 — the three ``outer_*`` fields).
    ``centroid`` and ``area_mm2`` are functions of what has been CUT INTO the
    face, not of the face's identity, so on a face carrying more than one feature
    they go stale the moment any earlier feature on it changes (§12a). Tier 4 of
    the resolver worked around that by INFERRING a bound on the missing quantity
    from the three numbers above, and the bound degrades linearly with how
    perforated the face is — on an ordinary vented plate it admitted a deleted
    boss top covering a quarter of the plate, i.e. silent wrong geometry. These
    three fields carry the missing quantity outright: the area, the area centroid
    and the perimeter of the region the face's OUTER WIRE encloses, all of them
    pure functions of that wire and therefore untouched by any interior edit
    (drilling, enlarging, moving or adding a hole).

    They are OPTIONAL because every selector persisted before they existed must
    keep resolving: the resolver DUAL-READS (``geometry.kernel.faces``), taking
    the exact outer-wire comparison when they are present and the §12a inferred
    band when they are not. The pick side emits them for every planar face from
    2026-08-16 on, so the legacy population is closed. Emit all three or none —
    a signature carrying some but not all is refused rather than downgraded.
    """

    subshape_type: Literal["face"] = "face"
    surface: Literal["plane"] = "plane"
    normal: Vec3 = Field(
        description="Outward unit normal of the planar face (full precision)"
    )
    centroid: Vec3 = Field(
        description="Area centroid of the face, world mm (full precision)"
    )
    area_mm2: float = Field(gt=0, description="Face area (mm^2), full precision")
    outer_area_mm2: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Area (mm^2) of the region the face's OUTER wire encloses — the face "
            "with its holes plugged. Invariant under any interior boundary edit "
            "(topological-naming §12b). Absent on selectors authored before "
            "2026-08-16, which fall back to the §12a inferred band."
        ),
    )
    outer_centroid: Vec3 | None = Field(
        default=None,
        description=(
            "Area centroid of the outer-wire region, world mm (full precision). "
            "Absent on selectors authored before 2026-08-16."
        ),
    )
    outer_perimeter_mm: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Length (mm) of the face's OUTER wire. Separates two outer regions "
            "that share an area and a centroid but not a shape. Absent on "
            "selectors authored before 2026-08-16."
        ),
    )
    topo_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=TOPO_NAME_MAX_LENGTH,
        description=_TOPO_NAME_DESCRIPTION,
    )


class EdgeSignature(BaseModel):
    """§2b stage-1 geometric fingerprint of an EDGE — typed, kernel-free.

    Full-precision invariants (§7.2 forbids quantizing the stored identity),
    chosen to distinguish the edges of a manifold solid: the ``curve`` family
    (line/circle/other — a straight edge and an arc of equal length never
    collide), the two canonically-ordered endpoints ``end_a``/``end_b`` (sorted
    lexicographically so the signature is INDEPENDENT of the topological edge
    orientation OCCT happens to assign), the ``midpoint`` (curve param 0.5 — it
    separates two collinear edges that share an endpoint, and pins a full-circle
    seam edge whose endpoints coincide), and the ``length_mm``. Two DISTINCT
    edges of an authored part differ in at least one field (endpoints/midpoint
    by whole mm, or length, or curve kind) — including the mirror-congruent
    edges of a symmetric part, which have DISTINCT absolute positions and so do
    NOT tie. Only edges that truly coincide in space (a boolean seam, a
    non-manifold duplicate) resolve to an honest ``subshape_ambiguous`` (§5),
    never a guess. Matching is nearest-within-tolerance at the documented
    subshape tolerance (geometry.kernel.edges / docs/GEOMETRY-QA.md), never an
    ad-hoc epsilon.

    ADJACENCY (§14 — the ``adjacent_faces`` field). Every field above is an
    ABSOLUTE WORLD COORDINATE, so a dimension edit that RESIZES the part — the
    single most ordinary thing anyone does to a model — translates the edge off
    every one of them, and §13's durable tier cannot help because it re-matches a
    straight edge on its own SUPPORTING LINE, which a translation leaves behind.
    §13 recorded the reason that looked unfixable: *"a face's area and in-plane
    centroid carry an identity that an edge's direction and length do not."* True
    of an edge's OWN geometry, and the escape is that an edge of a manifold solid
    is the intersection of exactly TWO FACES — and a face's identity survives,
    through four tiers, precisely because it has an area and an in-plane centroid.
    So the identity an edge lacks in itself, it borrows from its neighbours: this
    field stores the two adjacent planar faces' full
    :class:`PlanarFaceSignature`\\ s, canonically ordered, and the resolver's tier
    3 re-resolves THEM through the face matcher and takes the edge they share.

    OPTIONAL, for the same dual-read reason as the ``outer_*`` face fields: every
    edge selector persisted before this field existed must keep resolving, and it
    does — tiers 1 and 2 are untouched, and tier 3 simply does not fire for a
    signature that carries no adjacency. Emitted by the pick side (the selection
    overlay) from 2026-09-18 on, and ONLY when the edge has exactly two DISTINCT
    PLANAR neighbours: a cylinder's seam (one face twice), a non-manifold edge, or
    any edge bounded by a curved face carries no adjacency and is honestly left
    without it rather than given a partial one.
    """

    subshape_type: Literal["edge"] = "edge"
    curve: Literal["line", "circle", "other"] = Field(
        description="Curve family — line | circle | other (spline/ellipse/…)"
    )
    end_a: Vec3 = Field(
        description="One endpoint, world mm; the lexicographically SMALLER of the "
        "two so the pair is orientation-independent (full precision)"
    )
    end_b: Vec3 = Field(
        description="The other endpoint, world mm; the lexicographically LARGER. "
        "Equals end_a for a closed edge (a full circle's coincident seam)."
    )
    midpoint: Vec3 = Field(
        description="Curve midpoint (param 0.5), world mm (full precision)"
    )
    length_mm: float = Field(gt=0, description="Edge arc length (mm), full precision")
    adjacent_faces: list[PlanarFaceSignature] | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        description=(
            "The two PLANAR faces this edge bounds, canonically ordered by "
            "(normal, centroid) — the identity the edge's own absolute "
            "coordinates lose when a dimension edit RESIZES the part "
            "(topological-naming §14). The resolver's tier 3 re-resolves both "
            "through the four-tier face matcher and takes the edge they share, "
            "requiring exactly one. Absent on selectors authored before "
            "2026-09-18, and on any edge without exactly two distinct planar "
            "neighbours; tier 3 then does not fire and the older tiers are "
            "unchanged."
        ),
    )
    topo_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=TOPO_NAME_MAX_LENGTH,
        description=_TOPO_NAME_DESCRIPTION,
    )
