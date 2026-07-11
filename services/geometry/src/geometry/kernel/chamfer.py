"""Symmetric edge chamfer — bevel selected edges of the body chain.

The chamfer sibling of :mod:`geometry.kernel.fillet` (feature-tree design
§4.3): the feature layer hands in the current body (a service-internal
:class:`Solid`) plus the resolved edge set (from
:func:`geometry.kernel.edges.select_edges` — the SAME shared geometric
edge-selection plumbing fillet uses, design §2.4, NOT topological naming) and
the validated distance. This module owns only the OCCT/build123d chamfer call.
Failure raises the typed exception below with a **sanitized message** (no
kernel internals), which the feature layer maps 1:1 onto the ``chamfer_failed``
``FeatureError`` code so geometry outcomes stay values at the boundary.

A chamfer replaces a convex edge with a flat bevel face — PLANAR geometry,
unlike the fillet's cylindrical surface. ``distance_mm`` is the symmetric
setback along each adjacent face (a 45° bevel), passed as build123d's
``length`` with ``length2=None``.

Determinism (RESEARCH §9): the OCCT chamfer is a pure function of
``(body, edges, distance)``.
"""

from build123d import Edge, Solid


class ChamferError(RuntimeError):
    """The OCCT chamfer failed or produced an unsupported result (e.g. a
    distance too large for the local geometry, self-intersecting the body)."""


def chamfer_body(body: Solid, edges: list[Edge], distance_mm: float) -> Solid:
    """Bevel *edges* of *body* with a symmetric *distance_mm*; new single solid.

    Raises:
        ChamferError: the OCCT chamfer failed or left other than exactly one
            solid (single body chain per part in v1, design §7.6) — e.g. a
            distance too large for the adjacent faces.
    """
    if distance_mm <= 0:
        raise ValueError(f"distance_mm must be > 0, got {distance_mm}")
    try:
        # chamfer(length, length2, edge_list): length2=None → symmetric bevel
        # (both setbacks == length). Carries Shape[Unknown] type params
        # upstream (same gap tessellate.py documents) — scoped ignore only.
        result = body.chamfer(distance_mm, None, edges)  # pyright: ignore[reportUnknownMemberType]
        solids = result.solids()
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise ChamferError(
            f"Chamfer failed in the kernel ({type(exc).__name__}); the distance "
            f"({distance_mm} mm) may be too large for an adjacent face."
        ) from exc

    if len(solids) != 1:
        raise ChamferError(
            f"Chamfer produced {len(solids)} solids; parts are a single body "
            "in v1 (design §7.6)."
        )
    # clean() removes redundant seam faces/edges the operation can leave
    # behind, keeping topology counts meaningful (and golden-assertable).
    return solids[0].clean()
