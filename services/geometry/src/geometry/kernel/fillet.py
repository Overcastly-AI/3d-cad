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

from build123d import Edge

from geometry.kernel.lumps import assemble_lumps
from geometry.kernel.types import BodyShape


class FilletError(RuntimeError):
    """The OCCT fillet failed or produced an unsupported result (e.g. a radius
    too large for the local geometry, self-intersecting the body)."""


def fillet_body(body: BodyShape, edges: list[Edge], radius_mm: float) -> BodyShape:
    """Round *edges* of *body* with a constant *radius_mm*; LUMP-COUNT-PRESERVING.

    *body* is a single :class:`~build123d.Solid` (the common case — byte-identical
    to before) OR a multi-lump :class:`~build123d.Compound` (§MB-4). OCCT's
    ``BRepFilletAPI`` fillets the named edges of whichever lumps own them and
    leaves the rest untouched, so a fillet on one lump of a k-lump body keeps all
    k lumps. A result whose lump count differs from the input is a merge/sever
    (unsupported) → :class:`FilletError`.

    Raises:
        FilletError: the OCCT fillet failed, or changed the body's lump count
            (a radius too large for an adjacent face — design §7.6 / §MB-4).
    """
    if radius_mm <= 0:
        raise ValueError(f"radius_mm must be > 0, got {radius_mm}")
    lump_count = len(body.solids())
    try:
        # fillet() carries Shape[Unknown] type params upstream (same gap
        # tessellate.py documents for export_gltf) — scoped ignore only.
        result = body.fillet(radius_mm, edges)  # pyright: ignore[reportUnknownMemberType]
        solids = list(result.solids())
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise FilletError(
            f"Fillet failed in the kernel ({type(exc).__name__}); the radius "
            f"({radius_mm} mm) may be too large for an adjacent face."
        ) from exc

    if len(solids) != lump_count:
        raise FilletError(
            f"Fillet produced {len(solids)} lumps from a {lump_count}-lump body "
            "(it merged or severed a lump); the radius may be too large for an "
            "adjacent face (design §7.6 / §MB-4)."
        )
    # clean() removes redundant seam faces/edges the operation can leave behind,
    # keeping topology counts meaningful (and golden-assertable). k==1 returns a
    # bare cleaned Solid (byte-identical); a multi-lump body reassembles in the
    # explicit lump order (RESEARCH §9).
    if lump_count == 1:
        return solids[0].clean()
    return assemble_lumps([solid.clean() for solid in solids])
