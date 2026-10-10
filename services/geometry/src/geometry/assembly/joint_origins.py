"""Joint-origin resolution: a :class:`~loft_wire.joints.JointOrigin` to a frame.

The kernel half of S4a joints (the numeric half is
:mod:`geometry.assembly.joint_math`). Each origin kind resolves against the
instance's part body, in its LOCAL part frame, through the SAME tiered resolvers
the feature tree uses for a picked face or edge (strict signature, then the
history-based ``topo_name`` and the geometric re-matches,
:func:`~geometry.kernel.edges.resolve_edge_durable` /
:func:`~geometry.kernel.faces.resolve_faces` with the part's face names), so a
hole that moves when its part is edited keeps its joint, as in Fusion 360
(RESEARCH §21). Exactly one match or an honest
:class:`~geometry.assembly.protocol.AssemblyDefinitionError`, the subshape error
chained so evaluation can name ``subshape_unresolved`` / ``subshape_ambiguous``:
an origin whose face or edge is gone never slides onto another one.
Rules, as in Fusion 360 joint origins and Onshape mate connectors (RESEARCH §21):

- ``face_centre``: the matched planar face's own area centroid, Z its OUTWARD
  normal. After a resilient re-match (the face was resized or moved) the
  origin follows the face's CURRENT centre, unlike a sketch plane, which stays
  at the stored centroid.
- ``circle_centre``: the ``gp_Circ`` centre, Z along the circle's axis, pointing
  OUT of the body: when the circle bounds a planar face perpendicular to its axis
  (a hole rim, a shaft end), Z is that face's outward normal. A circle with no
  such face (between two curved faces) keeps the ``gp_Circ`` axis sense.
- ``edge_point``: the edge's ``start`` / ``mid`` / ``end``, Z the unit tangent
  there. Start is the endpoint with the smaller ``(x, y, z)`` (the signature's
  canonical ``end_a`` ordering, with a 1e-6 mm tie band), so it is independent
  of OCCT's edge orientation; the tangent points from start toward end, and
  ``mid`` is the arc-length midpoint.

X is :func:`~geometry.assembly.joint_math.reference_x` of Z, then the origin's
``flip`` and ``quarter_turns`` reorient the frame
(:func:`~geometry.assembly.joint_math.build_frame`).

The OCP wheel ships no type stubs; the directives scope that to this file.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from build123d import Edge, Face, GeomType
from loft_wire.features import EdgeSignature, PlanarFaceSignature
from loft_wire.joints import JointOrigin
from numpy.typing import NDArray
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GCPnts import GCPnts_AbscissaPoint
from OCP.gp import gp_Pnt, gp_Vec
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

from geometry.assembly.joint_math import build_frame
from geometry.assembly.protocol import AssemblyDefinitionError, ResolvedFrame
from geometry.assembly.transform import as_vec3
from geometry.kernel.edges import resolve_edge_durable
from geometry.kernel.faces import (
    SubshapeAmbiguousError,
    SubshapeUnresolvedError,
    planar_face_signature,
    resolve_faces,
)
from geometry.kernel.types import BodyShape

Vector = NDArray[np.float64]

_SUBSHAPE_ERRORS = (SubshapeUnresolvedError, SubshapeAmbiguousError)

#: |n·a| above this treats a planar face's normal as parallel to a circle's
#: axis (a face the circle bounds is perpendicular to the axis by construction;
#: this only rejects a face the circle merely lies on at a slant, which a valid
#: solid cannot have, without trusting an exact 1.0).
_PARALLEL_COS = 1.0 - 1e-9


#: Endpoint coordinates closer than this (mm) compare as equal when picking an
#: edge's canonical start (:func:`_canonical_forward`): far above float64 noise
#: on model coordinates, far below any real edge length.
_ENDPOINT_TIE_MM = 1e-6


def _arr(x: float, y: float, z: float) -> Vector:
    return np.array([x, y, z], dtype=np.float64)


#: The history-based name of each face of a part body, aligned with
#: ``body.faces()`` (``None`` where a face has none), or ``None`` when the
#: caller has no names; then only the geometric tiers run.
FaceNames = Sequence[str | None] | None


def _resolve_edge(body: BodyShape, origin: JointOrigin, face_names: FaceNames) -> Edge:
    signature = origin.signature
    assert isinstance(signature, EdgeSignature)
    try:
        return resolve_edge_durable(body, signature, face_names=face_names).edge
    except _SUBSHAPE_ERRORS as exc:
        raise AssemblyDefinitionError(
            f"joint origin on instance {origin.instance_id} did not resolve to "
            f"exactly one edge: {exc}"
        ) from exc


def _face_centre(
    body: BodyShape, origin: JointOrigin, face_names: FaceNames
) -> tuple[Vector, Vector]:
    """The matched face's OWN area centroid and outward normal.

    Deliberately not :func:`resolve_face_plane`'s origin: after a resilient
    re-match (the face grew, shrank or moved) that plane is re-anchored at the
    STORED centroid, which keeps a sketch where it was drawn, while a joint
    origin at a face centre follows the face's current centre, as a Fusion /
    Onshape face-centre origin does.
    """
    signature = origin.signature
    assert isinstance(signature, PlanarFaceSignature)
    try:
        (face,) = resolve_faces(body, [signature], face_names=face_names)
    except _SUBSHAPE_ERRORS as exc:
        raise AssemblyDefinitionError(
            f"joint origin on instance {origin.instance_id} did not resolve to "
            f"exactly one planar face: {exc}"
        ) from exc
    measured = planar_face_signature(face)
    assert measured is not None  # resolve_faces matches planar faces only
    normal, centroid, _area = measured
    return _arr(centroid.X, centroid.Y, centroid.Z), _arr(normal.X, normal.Y, normal.Z)


def _outward_planar_normal(body: BodyShape, edge: Edge, axis: Vector) -> Vector | None:
    """The outward normal of the planar face(s) ``edge`` bounds perpendicular to
    ``axis``; ``None`` when there is no such face or two disagree."""
    ancestors = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(body.wrapped, TopAbs_EDGE, TopAbs_FACE, ancestors)
    if not ancestors.Contains(edge.wrapped):
        return None
    found: Vector | None = None
    for shape in ancestors.FindFromKey(edge.wrapped):
        face = Face(TopoDS.Face_s(shape))
        if face.geom_type != GeomType.PLANE:
            continue
        n = face.normal_at()
        normal = _arr(n.X, n.Y, n.Z)
        if abs(float(np.dot(normal, axis))) < _PARALLEL_COS:
            continue
        if found is not None and float(np.dot(found, normal)) < 0.0:
            return None  # two perpendicular planar faces facing apart: no "out"
        found = normal
    return found


def _circle_centre(
    body: BodyShape, origin: JointOrigin, face_names: FaceNames
) -> tuple[Vector, Vector]:
    edge = _resolve_edge(body, origin, face_names)
    if edge.geom_type != GeomType.CIRCLE:
        raise AssemblyDefinitionError(
            f"joint origin on instance {origin.instance_id} resolved to a "
            f"{edge.geom_type.name.lower()} edge, not a circle"
        )
    circle = BRepAdaptor_Curve(edge.wrapped).Circle()
    loc = circle.Location()
    d = circle.Axis().Direction()
    axis = _arr(d.X(), d.Y(), d.Z())
    outward = _outward_planar_normal(body, edge, axis)
    if outward is not None:
        axis = axis if float(np.dot(axis, outward)) > 0.0 else -axis
    return _arr(loc.X(), loc.Y(), loc.Z()), axis


def _canonical_forward(p_first: gp_Pnt, p_last: gp_Pnt) -> bool:
    """True when the curve's first point is the canonical START: the endpoint
    with the smaller ``(x, y, z)``, coordinates within :data:`_ENDPOINT_TIE_MM`
    compared as equal (so round-off cannot swap the ends). A closed edge is
    forward."""
    for a, b in (
        (p_first.X(), p_last.X()),
        (p_first.Y(), p_last.Y()),
        (p_first.Z(), p_last.Z()),
    ):
        if abs(a - b) > _ENDPOINT_TIE_MM:
            return a < b
    return True


def _edge_point(
    body: BodyShape, origin: JointOrigin, face_names: FaceNames
) -> tuple[Vector, Vector]:
    edge = _resolve_edge(body, origin, face_names)
    curve = BRepAdaptor_Curve(edge.wrapped)
    first, last = curve.FirstParameter(), curve.LastParameter()
    forward = _canonical_forward(curve.Value(first), curve.Value(last))
    start, end = (first, last) if forward else (last, first)
    if origin.at == "start":
        param = start
    elif origin.at == "end":
        param = end
    else:
        length = GCPnts_AbscissaPoint.Length_s(curve)
        param = GCPnts_AbscissaPoint(curve, 0.5 * length, first).Parameter()
    point = gp_Pnt()
    tangent = gp_Vec()
    curve.D1(param, point, tangent)
    if tangent.Magnitude() == 0.0:
        raise AssemblyDefinitionError(
            f"joint origin on instance {origin.instance_id}: the edge has no "
            f"tangent at its {origin.at}"
        )
    z = _arr(tangent.X(), tangent.Y(), tangent.Z())
    if not forward:
        z = -z
    return _arr(point.X(), point.Y(), point.Z()), z


def resolve_joint_origin(
    body: BodyShape, origin: JointOrigin, *, face_names: FaceNames = None
) -> ResolvedFrame:
    """Resolve one joint origin against its instance's part body (LOCAL frame).

    *face_names* (the part evaluation's history-based face names, aligned with
    ``body.faces()``) enables the named tier, which is what carries an origin
    through an edit that moves its face or edge off every stored coordinate (a
    hole re-centred by a width change). Without names the strict and geometric
    tiers still run.

    Raises:
        AssemblyDefinitionError: the face/edge did not resolve to exactly one
            subshape, or a circle_centre edge is not a circle.
    """
    if origin.kind == "face_centre":
        point, z = _face_centre(body, origin, face_names)
    elif origin.kind == "circle_centre":
        point, z = _circle_centre(body, origin, face_names)
    else:
        point, z = _edge_point(body, origin, face_names)
    frame = build_frame(point, z, flip=origin.flip, quarter_turns=origin.quarter_turns)
    return ResolvedFrame(
        origin=as_vec3(frame.origin), z=as_vec3(frame.z), x=as_vec3(frame.x)
    )
