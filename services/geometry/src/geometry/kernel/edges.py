"""Geometric edge selection — the shared edge-reference plumbing for
body-modifying features (fillet, chamfer).

Both fillet and chamfer must name edges of the CURRENT body chain. v1 resolves
that reference by a **deterministic geometric predicate**, NOT topological
naming (design §2.4 — that is Phase 2's ``SubshapeRef``). ``all_edges`` selects
every edge; ``axis_parallel`` selects every straight edge parallel to a world
axis (the vertical edges of an upright prism are ``axis: "Z"``). The predicate
is evaluated against the body that exists at the feature's point in the tree,
so it survives rebuilds without a name map — and it is honestly limited: "the
edge I clicked" is Phase 2.

This module is the single home of that resolution (CLAUDE.md DRY rule — the
second real consumer, chamfer, made the extraction from fillet earned rather
than speculative). The kernel feature modules (:mod:`geometry.kernel.fillet`,
:mod:`geometry.kernel.chamfer`) own only the OCCT modeling call; the feature
layer maps the neutral :class:`NoEdgesSelectedError` onto each feature's own
``no_fillet_edges`` / ``no_chamfer_edges`` code.

Determinism (RESEARCH §9): selection filters ``body.edges()`` (OCCT's
deterministic traversal) by a pure predicate, so the selected set and its
order are a pure function of the body.
"""

from build123d import Edge, GeomType, Solid, Vector
from py_kit.schemas.features import (
    AllEdgesSelector,
    AxisParallelEdgesSelector,
    EdgeSelector,
)

#: World-axis direction vectors for the ``axis_parallel`` selector.
_AXIS_DIRECTIONS: dict[str, Vector] = {
    "X": Vector(1.0, 0.0, 0.0),
    "Y": Vector(0.0, 1.0, 0.0),
    "Z": Vector(0.0, 0.0, 1.0),
}

#: Parallelism tolerance for the ``axis_parallel`` predicate: a unit edge
#: tangent counts as parallel to an axis when the perpendicular component is
#: below this bound. Prism edges are exactly axis-aligned; the bound absorbs
#: only ulp-scale construction noise (aligned with the kernel linear tolerance,
#: 1e-7 m — model units are mm).
_EDGE_DIRECTION_TOLERANCE = 1e-7


class NoEdgesSelectedError(ValueError):
    """The edge selector matched no edge of the body — nothing to modify.

    The honest "your selector picked no edges" outcome, distinct from a kernel
    modeling failure. The feature layer maps it onto the per-feature
    ``no_fillet_edges`` / ``no_chamfer_edges`` code (design §4.3)."""


def _is_axis_parallel(edge: Edge, axis: Vector) -> bool:
    """True when *edge* is a straight line parallel to *axis*.

    Curved edges never match (an arc has no single direction). The tangent of a
    line is constant, so sampling it at the midpoint is exact.
    """
    if edge.geom_type != GeomType.LINE:
        return False
    tangent: Vector = edge.tangent_at(0.5)
    # |tangent x axis| == sin(angle); both are unit vectors, so the cross
    # magnitude is the perpendicular component. Parallel (either orientation)
    # ⇔ that component is ~0.
    return tangent.cross(axis).length <= _EDGE_DIRECTION_TOLERANCE


def select_edges(body: Solid, selector: EdgeSelector) -> list[Edge]:
    """Resolve the geometric edge selector against *body* (design §2.4).

    Deterministic: filters ``body.edges()`` (OCCT's deterministic order) by a
    pure predicate. Raises :class:`NoEdgesSelectedError` when nothing matches.
    """
    match selector:
        case AllEdgesSelector():
            edges = list(body.edges())
        case AxisParallelEdgesSelector():
            axis = _AXIS_DIRECTIONS[selector.axis]
            edges = [e for e in body.edges() if _is_axis_parallel(e, axis)]

    if not edges:
        raise NoEdgesSelectedError(
            "The edge selector matched no edge of the body; nothing to modify "
            "(v1 selects edges geometrically, not by picking — design §2.4)."
        )
    return edges
