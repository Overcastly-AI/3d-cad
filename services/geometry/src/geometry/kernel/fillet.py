"""Constant-radius edge fillet — round selected edges of the body chain.

The kernel half of the fillet feature (feature-tree design §4.3): the feature
layer hands in the current body (a service-internal :class:`Solid`) plus the
validated ``FilletParamsV1`` (edge selector + radius); this module owns every
OCCT/build123d call and resolves the *geometric* edge selector to concrete
edges. Failures raise the typed exceptions below with **sanitized messages**
(no kernel internals), which the feature layer maps 1:1 onto ``FeatureError``
codes so geometry outcomes stay values at the boundary.

Edge selection is a **deterministic geometric predicate**, NOT topological
naming (design §2.4 — that is Phase 2). ``all_edges`` rounds every edge;
``axis_parallel`` rounds every straight edge parallel to a world axis (the
vertical edges of an upright prism are ``axis: "Z"``). The predicate is
evaluated against the body that exists at the feature's point in the tree, so
it survives rebuilds without a name map — and it is honestly limited: "the
edge I clicked" is Phase 2.

Determinism (RESEARCH §9): selection filters ``body.edges()`` (OCCT's
deterministic traversal) by a pure predicate, so the selected set and its
order are a pure function of the body; the OCCT fillet algorithm is likewise a
pure function of ``(body, edges, radius)``.
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


class NoFilletEdgesError(ValueError):
    """The edge selector matched no edge of the body — nothing to round."""


class FilletError(RuntimeError):
    """The OCCT fillet failed or produced an unsupported result (e.g. a radius
    too large for the local geometry, self-intersecting the body)."""


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


def select_fillet_edges(body: Solid, selector: EdgeSelector) -> list[Edge]:
    """Resolve the geometric edge selector against *body* (design §2.4).

    Deterministic: filters ``body.edges()`` (OCCT's deterministic order) by a
    pure predicate. Raises :class:`NoFilletEdgesError` when nothing matches —
    the honest "your selector picked no edges" outcome, distinct from a kernel
    failure.
    """
    match selector:
        case AllEdgesSelector():
            edges = list(body.edges())
        case AxisParallelEdgesSelector():
            axis = _AXIS_DIRECTIONS[selector.axis]
            edges = [e for e in body.edges() if _is_axis_parallel(e, axis)]

    if not edges:
        raise NoFilletEdgesError(
            "The fillet edge selector matched no edge of the body; nothing to "
            "round (v1 selects edges geometrically, not by picking — design §2.4)."
        )
    return edges


def fillet_body(body: Solid, edges: list[Edge], radius_mm: float) -> Solid:
    """Round *edges* of *body* with a constant *radius_mm*; new single solid.

    Raises:
        FilletError: the OCCT fillet failed or left other than exactly one
            solid (single body chain per part in v1, design §7.6) — e.g. a
            radius too large for the adjacent faces.
    """
    if radius_mm <= 0:
        raise ValueError(f"radius_mm must be > 0, got {radius_mm}")
    try:
        # fillet() carries Shape[Unknown] type params upstream (same gap
        # tessellate.py documents for export_gltf) — scoped ignore only.
        result = body.fillet(radius_mm, edges)  # pyright: ignore[reportUnknownMemberType]
        solids = result.solids()
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise FilletError(
            f"Fillet failed in the kernel ({type(exc).__name__}); the radius "
            f"({radius_mm} mm) may be too large for an adjacent face."
        ) from exc

    if len(solids) != 1:
        raise FilletError(
            f"Fillet produced {len(solids)} solids; parts are a single body "
            "in v1 (design §7.6)."
        )
    # clean() removes redundant seam faces/edges the operation can leave
    # behind, keeping topology counts meaningful (and golden-assertable).
    return solids[0].clean()
