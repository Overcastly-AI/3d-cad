"""Constant-radius edge fillet — round selected edges of the body chain.

The kernel half of the fillet feature (feature-tree design §4.3): the feature
layer hands in the current body (a service-internal :class:`Solid`) plus the
resolved edge set (from :func:`geometry.kernel.edges.select_edges` — the shared
geometric edge-selection plumbing, design §2.4, NOT topological naming) and the
validated radius. This module owns only the OCCT/build123d fillet call. Failure
raises the typed exception below with a **sanitized message** (no kernel
internals), which the feature layer maps 1:1 onto the ``fillet_failed``
``FeatureError`` code so geometry outcomes stay values at the boundary.

Determinism (RESEARCH §9): the OCCT fillet is a pure function of
``(body, edges, radius)``.
"""

from build123d import Edge, Solid


class FilletError(RuntimeError):
    """The OCCT fillet failed or produced an unsupported result (e.g. a radius
    too large for the local geometry, self-intersecting the body)."""


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
