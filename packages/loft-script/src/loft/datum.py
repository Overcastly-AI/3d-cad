"""Datum planes from a script: the plane at an angle (DATUM-PLANE-ANGLE).

:meth:`loft.Part.plane_at_angle` is Fusion 360's *Plane at Angle* /
SolidWorks' Plane "At angle": a plane through a line, turned about it by a
typed angle from a reference plane. This module turns the handles a script
holds into the wire params (:class:`~loft_wire.datum_angle.DatumAngleParams`),
validated here by the same pydantic models the server runs, so a bad angle is
a ``ValueError`` before anything is sent.

Accepted handles:

* ``line``: ``"X"``/``"Y"``/``"Z"`` (an origin axis); ``(sketch, entity_id)``
  for a line of a sketch (a :class:`~loft.sketch.Sketch`, its ``FeatureRef``
  or its id); or any wire :data:`~loft_wire.datum_angle.DatumAngleLine`
  (e.g. a picked edge's ``EdgeSubshapeRef``).
* ``reference``: ``"XY"``/``"XZ"``/``"YZ"``, a datum's ``FeatureRef``, or a
  face ``SubshapeRef``. Omitted, a sketch line's own sketch plane is used
  (Fusion's implicit reference); an axis or an edge needs one.
"""

from __future__ import annotations

import uuid
from typing import Literal

from loft_wire.features import (
    DatumAngleLine,
    DatumAngleParams,
    DatumFeature,
    DatumOriginAxisRef,
    DatumPlaneRef,
    DatumSketchLineRef,
    FeatureRef,
    MidplaneSide,
    SubshapeRef,
)

from loft.sketch import Sketch, resolve_plane

__all__ = ["LineLike", "ReferenceLike", "plane_at_angle_feature"]

SketchHandle = Sketch | FeatureRef | uuid.UUID

#: What :meth:`loft.Part.plane_at_angle` takes as its line.
LineLike = Literal["X", "Y", "Z"] | tuple[SketchHandle, str] | DatumAngleLine

#: What it takes as its reference plane.
ReferenceLike = Literal["XY", "XZ", "YZ"] | DatumPlaneRef | FeatureRef | SubshapeRef


def _sketch_ref(handle: SketchHandle) -> FeatureRef:
    if isinstance(handle, Sketch):
        return handle.ref()
    if isinstance(handle, FeatureRef):
        return handle
    return FeatureRef(kind="feature", feature_id=handle)


def _line(line: LineLike) -> DatumAngleLine:
    if isinstance(line, str):
        if line not in ("X", "Y", "Z"):
            raise ValueError(f"unknown origin axis {line!r}; expected X, Y or Z")
        return DatumOriginAxisRef(kind="origin_axis", axis=line)
    if isinstance(line, tuple):
        handle, entity = line
        return DatumSketchLineRef(
            kind="sketch_line", sketch=_sketch_ref(handle), entity=entity
        )
    return line


def _reference(reference: ReferenceLike | None, line: LineLike) -> MidplaneSide:
    if reference is None:
        if isinstance(line, tuple) and isinstance(line[0], Sketch):
            return line[0].plane
        raise ValueError(
            "a reference plane is needed: pass reference='XY' (or a datum / face "
            "ref); only a line given as (Sketch, entity) defaults to its sketch's "
            "plane"
        )
    if isinstance(reference, str):
        return resolve_plane(reference)
    return reference


def plane_at_angle_feature(
    line: LineLike,
    angle_deg: float,
    *,
    reference: ReferenceLike | None = None,
    flip: bool = False,
    expressions: dict[str, str] | None = None,
) -> DatumFeature:
    """The ``datum`` feature for a plane through *line* at *angle_deg* from
    *reference* (positive turns the reference normal right-handed about the
    line's direction; RESEARCH §18). *expressions* is the envelope's formulas
    (``{"/angle_deg": "A"}``), with *angle_deg* their resolved number."""
    return DatumFeature(
        expressions=expressions,
        type="datum",
        version=1,
        params=DatumAngleParams(
            kind="angle",
            line=_line(line),
            reference=_reference(reference, line),
            angle_deg=angle_deg,
            flip=flip,
        ),
    )
