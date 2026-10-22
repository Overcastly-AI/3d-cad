"""Pipe and Plane Along Path from a script (PIPE-ALONG-PATH).

:meth:`loft.Part.pipe` is Fusion 360's *Pipe*: a circle (or, with a wall, a
ring) swept along picked curves; :meth:`loft.Part.plane_along_path` is its
*Plane Along Path*. This module turns the handles a script holds into the wire
params, validated by the same pydantic models the server runs, so a wall that
leaves no bore is a ``ValueError`` before anything is sent.

A curve is ``(sketch, entity_id)`` (a :class:`~loft.sketch.Sketch`, its
``FeatureRef`` or its id, and the id of a line, arc, circle or spline in it)
or any wire :data:`~loft_wire.pipe.PathSegment` (e.g. a picked edge's
``EdgeSubshapeRef``).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Literal

from loft_wire.cut_bodies import CutBodies
from loft_wire.features import (
    DatumAlongPathParams,
    DatumFeature,
    FeatureRef,
    PathSegment,
    PathSketchCurve,
    PipeFeature,
    PipeParamsV1,
)

from loft.sketch import Sketch

__all__ = ["CurveLike", "pipe_feature", "plane_along_path_feature"]

SketchHandle = Sketch | FeatureRef | uuid.UUID

#: One picked curve of a path.
CurveLike = tuple[SketchHandle, str] | PathSegment


def _segment(curve: CurveLike) -> PathSegment:
    if not isinstance(curve, tuple):
        return curve
    handle, entity = curve
    if isinstance(handle, Sketch):
        if handle.solved is None:
            handle.save()
        sketch = handle.ref()
    elif isinstance(handle, FeatureRef):
        sketch = handle
    else:
        sketch = FeatureRef(kind="feature", feature_id=handle)
    return PathSketchCurve(kind="sketch_curve", sketch=sketch, entity=entity)


#: The bodies a new cut removes material from: ``"all"`` (every body the tool
#: meets, Fusion 360's Objects To Cut default), or the bodies, each by its
#: base feature's ref or id (:mod:`loft_wire.cut_bodies`).
BodiesToCut = Literal["all"] | Sequence[FeatureRef | uuid.UUID]


def cut_scope(
    operation: Literal["add", "cut"], bodies: BodiesToCut
) -> CutBodies | None:
    """The wire ``cut_bodies`` of a new feature: absent on an add."""
    if operation != "cut":
        return None
    if bodies == "all":
        return "all"
    return [
        body
        if isinstance(body, FeatureRef)
        else FeatureRef(kind="feature", feature_id=body)
        for body in bodies
    ]


def pipe_feature(
    path: Sequence[CurveLike],
    outer_diameter_mm: float,
    *,
    wall_thickness_mm: float | None = None,
    operation: Literal["add", "cut"] = "add",
    merge: bool = True,
    cut_bodies: CutBodies | None = None,
    expressions: dict[str, str] | None = None,
) -> PipeFeature:
    """The ``pipe`` feature along *path* (picked curves, any order)."""
    return PipeFeature(
        expressions=expressions,
        type="pipe",
        version=1,
        params=PipeParamsV1(
            path=[_segment(curve) for curve in path],
            outer_diameter_mm=outer_diameter_mm,
            wall_thickness_mm=wall_thickness_mm,
            operation=operation,
            merge=merge,
            cut_bodies=cut_bodies,
        ),
    )


def plane_along_path_feature(
    curve: CurveLike,
    *,
    ratio: float | None = None,
    distance_mm: float | None = None,
    flip: bool = False,
    expressions: dict[str, str] | None = None,
) -> DatumFeature:
    """The ``datum`` normal to *curve* at *ratio* of its length or
    *distance_mm* along it (exactly one; neither is the start)."""
    if ratio is not None and distance_mm is not None:
        raise ValueError("give a ratio or a distance along the path, not both")
    if distance_mm is not None:
        params = DatumAlongPathParams(
            kind="along_path",
            path=_segment(curve),
            measure="distance",
            distance_mm=distance_mm,
            flip=flip,
        )
    else:
        params = DatumAlongPathParams(
            kind="along_path",
            path=_segment(curve),
            measure="ratio",
            ratio=0.0 if ratio is None else ratio,
            flip=flip,
        )
    return DatumFeature(expressions=expressions, type="datum", version=1, params=params)
