"""Sketch corner edits (fillet / chamfer) — request and result DTOs.

Split out of :mod:`loft_wire.sketch` (FILE-SIZE-RATCHET): the shapes are
unchanged, so the generated contracts are too.
"""

from pydantic import BaseModel, Field, model_validator

from loft_wire.sketch import MAX_SKETCH_ENTITIES, EntityId, SketchEntity

# ---------------------------------------------------------------------------
# Sketch editing — corner fillet / chamfer (BACKLOG #5, backend)
# ---------------------------------------------------------------------------
#
# The one-click corner-round an engineer expects instead of hand-placing a
# tangent arc and constraining it twice (a named ❌ Sketching-scorecard blocker,
# docs/COMPETITIVE.md). Two entities that meet at (or extend/trim to) a shared
# corner are replaced at that corner by:
#
# * **fillet** — a tangent **arc** of radius ``radius``; both curves are trimmed
#   back to their tangent points and the arc bridges them.
# * **chamfer** — a straight **line** across the corner between two equal-setback
#   points at distance ``distance`` along each curve; both curves are trimmed
#   back to those points and the line bridges them.
#
# Like trim/extend/offset/mirror these are **server-side geometry operations**
# (RESEARCH §3 + CLAUDE.md service boundaries) — the frontend must not
# reimplement the tangent-point/bisector math — served at
# ``POST /api/v1/sketch/{fillet,chamfer}`` and gateway-proxied auth-gated at
# ``/api/v1/geometry/sketch/{fillet,chamfer}``. They are stateless and
# deterministic (RESEARCH §9): identical input yields coordinate-identical
# output, computed by **exact closed-form analytic** geometry (no solver
# iteration), matching the trim/extend/offset/mirror choice. Fillet and chamfer
# share one request shape per op and one result type (:class:`SketchCornerResult`)
# — DRY: the corner-resolution, setback, and trim math is one code path, the only
# difference is the bridging entity (arc vs. line) and the size parameter's role.
#
# Unlike offset/mirror (which only ADD), a corner op both **rewrites** the two
# source curves (shortened to the tangent/setback points, **ids preserved**) AND
# **adds** the bridging entity (fresh deterministic id ``f"{a}.{n}"`` seeded from
# the WHOLE entity set, construction flag inherited from the first curve). The
# result therefore returns the whole rewritten entity set (like
# :class:`SketchEditResult`), with the two sources replaced in place and the
# bridge appended at the end.
#
# **v1 scope (honest).** **Line-line** corners only — the tangent-point/bisector
# geometry is fully closed-form. The corner is the intersection of the two lines'
# infinite supports; for each line the endpoint **farther** from that corner is
# kept and the nearer endpoint is moved to the tangent/setback point (so an
# under-length leg is extended and an over-length leg is trimmed — "extend/trim
# to the corner"). A line-arc or arc-arc corner needs a tangent-circle
# construction and is **DEFERRED**: such a target pair is rejected
# ``sketch_unsupported_entity`` (message names the deferred kinds), never
# mis-filleted. Ambiguous X-crossings are not pick-disambiguated in v1 (the
# farther-endpoint rule selects the longer legs).


class SketchFilletRequest(BaseModel):
    """Input for a sketch **fillet** (round a corner with a tangent arc).

    ``entities`` is the whole sketch's entity list (so the new arc gets a fresh
    id that cannot collide, and to mirror the trim/offset contract). ``a`` and
    ``b`` name the two curves forming the corner; each MUST be present in
    ``entities`` (else ``sketch_target_not_found``), be **distinct**, and — in
    v1 — be **lines** (a non-line, or a line-arc/arc-arc pair, is
    ``sketch_unsupported_entity``). ``radius`` is the tangent-arc radius (mm),
    strictly positive and finite.

    Both lines are trimmed to their tangent points (``radius`` from the corner
    along each leg, scaled by the corner half-angle) and a tangent arc is added.
    Errors are 422s, never 500s: ``sketch_corner_not_found`` (the supports are
    parallel/collinear, or ``a``/``b`` name the same entity — no isolated
    corner), ``sketch_corner_too_large`` (the tangent point falls past a leg's
    far end — radius too large for the available length),
    ``sketch_degenerate_result`` (a zero-length result), plus the target/kind
    codes above.
    """

    entities: list[SketchEntity] = Field(
        max_length=MAX_SKETCH_ENTITIES,
        description="The whole sketch's entities (fillet rewrites the two "
        "corner curves and ADDS the arc), bounded by MAX_SKETCH_ENTITIES "
        "(work bound, audit G2).",
    )
    a: EntityId = Field(
        description="Id of the first corner line; must be in `entities`."
    )
    b: EntityId = Field(
        description="Id of the second corner line; must be in `entities`, "
        "distinct from `a`."
    )
    radius: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Fillet (tangent-arc) radius (mm); strictly positive and finite.",
    )

    @model_validator(mode="after")
    def _unique_entity_ids(self) -> "SketchFilletRequest":
        seen: set[str] = set()
        for entity in self.entities:
            if entity.id in seen:
                raise ValueError(f"Duplicate sketch entity id: {entity.id!r}")
            seen.add(entity.id)
        return self


class SketchChamferRequest(BaseModel):
    """Input for a sketch **chamfer** (bevel a corner with a straight line).

    Same corner contract as :class:`SketchFilletRequest` (``a``/``b`` two
    distinct line curves present in ``entities``). ``distance`` is the equal
    setback (mm) measured along each leg from the corner; strictly positive and
    finite. Both lines are trimmed to their setback points and a straight
    chamfer line is added between them. Errors are the same 422 codes as fillet
    (``sketch_corner_not_found``, ``sketch_corner_too_large`` when ``distance``
    exceeds a leg's available length, ``sketch_degenerate_result``,
    ``sketch_target_not_found``, ``sketch_unsupported_entity``).
    """

    entities: list[SketchEntity] = Field(
        max_length=MAX_SKETCH_ENTITIES,
        description="The whole sketch's entities (chamfer rewrites the two "
        "corner curves and ADDS the bevel line), bounded by "
        "MAX_SKETCH_ENTITIES (work bound, audit G2).",
    )
    a: EntityId = Field(
        description="Id of the first corner line; must be in `entities`."
    )
    b: EntityId = Field(
        description="Id of the second corner line; must be in `entities`, "
        "distinct from `a`."
    )
    distance: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Equal setback distance (mm) along each leg from the corner; "
        "strictly positive and finite.",
    )

    @model_validator(mode="after")
    def _unique_entity_ids(self) -> "SketchChamferRequest":
        seen: set[str] = set()
        for entity in self.entities:
            if entity.id in seen:
                raise ValueError(f"Duplicate sketch entity id: {entity.id!r}")
            seen.add(entity.id)
        return self


class SketchCornerResult(BaseModel):
    """Output of a fillet/chamfer: the whole rewritten entity list.

    Like :class:`SketchEditResult` (and unlike the additive offset/mirror
    results), a corner op returns the FULL entity set: order is preserved, the
    two corner curves are replaced **in place** by their trimmed selves (ids and
    construction flags unchanged, only the corner-side endpoint moved to the
    tangent/setback point), and the bridging entity — a tangent arc (fillet) or
    straight line (chamfer) — is **appended at the end** with a fresh
    deterministic id ``f"{a}.{n}"`` (lowest ``n`` >= 2 not already in use, seeded
    from the whole input set) inheriting the first curve's construction flag. A
    fillet arc is emitted CCW-from-start (the minor corner arc), honouring the
    :class:`SketchArc` invariant. Deterministic: identical input yields identical
    output entities, coordinates included (RESEARCH §9).
    """

    entities: list[SketchEntity] = Field(
        description="The sketch entities after the corner op: the two source "
        "curves trimmed in place (ids preserved) plus the appended bridge "
        '(fresh id `f"{a}.{n}"`).'
    )

    @model_validator(mode="after")
    def _unique_entity_ids(self) -> "SketchCornerResult":
        # Defense in depth (same posture as SketchEditResult): the appended
        # bridge id must never collide with an existing entity. The op seeds its
        # id generator from the whole input set; enforcing uniqueness here fails
        # a regression loudly at the boundary instead of corrupting the sketch.
        seen: set[str] = set()
        for entity in self.entities:
            if entity.id in seen:
                raise ValueError(f"Duplicate sketch entity id: {entity.id!r}")
            seen.add(entity.id)
        return self
