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

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportAttributeAccessIssue=false

from build123d import Edge, Face, Solid
from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer
from OCP.Standard import Standard_Failure
from OCP.StdFail import StdFail_NotDone
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

from geometry.kernel.healing import clean_shape
from geometry.kernel.lumps import assemble_lumps
from geometry.kernel.naming import OpHistory
from geometry.kernel.types import BodyShape


class ChamferError(RuntimeError):
    """The OCCT chamfer failed or produced an unsupported result (e.g. a
    distance too large for the local geometry, self-intersecting the body)."""


def chamfer_body(
    body: BodyShape,
    edges: list[Edge],
    distance_mm: float,
    *,
    history: OpHistory | None = None,
) -> BodyShape:
    """Bevel *edges* of *body* with a symmetric *distance_mm*; LUMP-COUNT-PRESERVING.

    The chamfer twin of :func:`geometry.kernel.fillet.fillet_body` (§MB-4): *body*
    is a single :class:`~build123d.Solid` (byte-identical to before) OR a
    multi-lump :class:`~build123d.Compound`. OCCT bevels the named edges of
    whichever lumps own them and leaves the rest untouched, so a chamfer on one
    lump of a k-lump body keeps all k lumps; a lump-count change is a merge/sever
    → :class:`ChamferError`.

    *history*, when given, receives each edge paired with the bevel face(s) it
    generated (``BRepFilletAPI_MakeChamfer::Generated``), for face naming
    (:mod:`geometry.kernel.naming`).

    Raises:
        ChamferError: the OCCT chamfer failed, or changed the body's lump count
            (a distance too large for an adjacent face — design §7.6 / §MB-4).
    """
    if distance_mm <= 0:
        raise ValueError(f"distance_mm must be > 0, got {distance_mm}")
    lump_count = len(body.solids())
    try:
        # chamfer(length, length2, edge_list): length2=None → symmetric bevel
        # (both setbacks == length). Carries Shape[Unknown] type params
        # upstream (same gap tessellate.py documents) — scoped ignore only.
        result = (
            body.chamfer(distance_mm, None, edges)
            if history is None
            else _chamfer_with_history(body, edges, distance_mm, history)
        )
        solids = list(result.solids())
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise ChamferError(
            f"Chamfer failed in the kernel ({type(exc).__name__}); the distance "
            f"({distance_mm} mm) may be too large for an adjacent face."
        ) from exc

    if len(solids) != lump_count:
        raise ChamferError(
            f"Chamfer produced {len(solids)} lumps from a {lump_count}-lump body "
            "(it merged or severed a lump); the distance may be too large for an "
            "adjacent face (design §7.6 / §MB-4)."
        )
    # clean() removes redundant seam faces/edges the operation can leave behind,
    # keeping topology counts meaningful (and golden-assertable). k==1 returns a
    # bare cleaned Solid (byte-identical); a multi-lump body reassembles in the
    # explicit lump order (RESEARCH §9).
    if lump_count == 1:
        return clean_shape(solids[0])
    return assemble_lumps([clean_shape(solid) for solid in solids])


def _chamfer_with_history(
    body: BodyShape, edges: list[Edge], distance_mm: float, history: OpHistory
) -> BodyShape:
    """``Mixin3D.chamfer(length, None, edges)`` (build123d 0.11), call for call,
    keeping the builder so its ``Generated`` history can be read. Raises what
    it raises."""
    edge_face_map = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(
        body.wrapped, TopAbs_EDGE, TopAbs_FACE, edge_face_map
    )
    builder = BRepFilletAPI_MakeChamfer(body.wrapped)
    for edge in edges:
        face = edge_face_map.FindFromKey(edge.wrapped).First()
        builder.Add(distance_mm, distance_mm, edge.wrapped, TopoDS.Face_s(face))
    try:
        result = Solid._make_3d_result(builder.Shape())  # pyright: ignore[reportPrivateUsage]
        if not result.is_valid:
            raise Standard_Failure
    except (StdFail_NotDone, Standard_Failure) as err:
        raise ValueError(
            "Failed creating a chamfer, try a smaller length value(s)"
        ) from err
    for edge in edges:
        for produced in builder.Generated(edge.wrapped):
            history.generated.append((edge, Face(TopoDS.Face_s(produced))))
    return result
