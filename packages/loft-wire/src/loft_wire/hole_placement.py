"""A hole's face-frame coordinates (HOLE-POSITION-FORMULA, RESEARCH §20).

Kept out of :mod:`loft_wire.features` (FILE-SIZE-RATCHET); ``HoleParamsV1``
takes its two optional fields and its validator from here.

A hole is dialled in at X/Y in its face's frame, as Fusion 360 places a hole
by offsets that take expressions. The stored ``position`` is a WORLD point, so
no JSON pointer can hold a formula for X or Y. ``face_x_mm``/``face_y_mm``
store those two numbers beside it; a formula drives them by pointer
(``{"/face_x_mm": "W - 20"}``) and every validation re-derives ``position``
from them, so documents' resolve on write, a parameter-table PUT and each
evaluation request all move the hole. Geometry still reads ``position`` only.

THE FRAME is the web's (``apps/web/src/features/facePlacement.ts``): axes are
the kernel's on-face axes (``geometry.kernel.faces._deterministic_x_dir`` and
``normal x u``), and the origin is the PART origin projected onto the face
plane, which does not move when the face's outline does. Both are functions of
the stored face signature's normal and plane alone.

Both fields are optional and omitted from a dump while null, so a hole stored
before them keeps its world ``position`` and its bytes.
"""

import math
from typing import Any, Final, Protocol

from pydantic import Field

from loft_wire.geometry import Vec3
from loft_wire.twist import is_none

_AXES: Final = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))

type _V = tuple[float, float, float]


def _dot(a: _V, b: _V) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _unit(v: _V) -> _V:
    length = math.hypot(*v)
    return (
        (0.0, 0.0, 0.0)
        if length == 0
        else (v[0] / length, v[1] / length, v[2] / length)
    )


def deterministic_x_dir(normal: _V) -> _V:
    """The kernel's on-face x axis: the world axis least aligned with the
    normal (ties to the earlier axis), its normal component removed."""
    axis = min(enumerate(_AXES), key=lambda ia: (abs(_dot(ia[1], normal)), ia[0]))[1]
    k = _dot(axis, normal)
    return _unit(
        (axis[0] - normal[0] * k, axis[1] - normal[1] * k, axis[2] - normal[2] * k)
    )


def face_frame(normal: Vec3, centroid: Vec3) -> tuple[_V, _V, _V]:
    """``(origin, u, v)`` of a planar face's frame, all world mm."""
    n = _unit((normal.x, normal.y, normal.z))
    u = deterministic_x_dir(n)
    v = (
        n[1] * u[2] - n[2] * u[1],
        n[2] * u[0] - n[0] * u[2],
        n[0] * u[1] - n[1] * u[0],
    )
    d = _dot((centroid.x, centroid.y, centroid.z), n)
    return (n[0] * d, n[1] * d, n[2] * d), u, v


def face_point_to_world(normal: Vec3, centroid: Vec3, x: float, y: float) -> Vec3:
    """Face-frame mm to the world point ON the face plane (``origin + u x + v y``)."""
    o, u, v = face_frame(normal, centroid)
    return Vec3(
        x=o[0] + u[0] * x + v[0] * y,
        y=o[1] + u[1] * x + v[1] * y,
        z=o[2] + u[2] * x + v[2] * y,
    )


def _coordinate_field(axis: str) -> Any:
    return Field(
        default=None,
        exclude_if=is_none,
        allow_inf_nan=False,
        description=f"Drill {axis.upper()} in the face's frame (mm): origin at the "
        "part origin projected onto the face plane, axes the kernel's on-face axes. "
        "Set together with the other coordinate; `position` is then derived from "
        f"them on every write, so an expression at `/face_{axis}_mm` moves the hole. "
        "Omitted on holes placed by world `position` alone.",
    )


FACE_X_FIELD: Final[Any] = _coordinate_field("x")
FACE_Y_FIELD: Final[Any] = _coordinate_field("y")


class _Signature(Protocol):
    normal: Vec3
    centroid: Vec3


class _Selector(Protocol):
    signature: _Signature


class _Face(Protocol):
    selector: _Selector


class _Hole(Protocol):
    face: _Face
    position: Vec3
    face_x_mm: float | None
    face_y_mm: float | None


def derive_hole_position[H: _Hole](hole: H) -> H:
    """``HoleParamsV1``'s after-validator: with face coordinates, ``position``
    is the world point they name; without, it stands as stored."""
    x, y = hole.face_x_mm, hole.face_y_mm
    if x is None and y is None:
        return hole
    if x is None or y is None:
        raise ValueError("face_x_mm and face_y_mm are set together, or neither")
    signature = hole.face.selector.signature
    hole.position = face_point_to_world(signature.normal, signature.centroid, x, y)
    return hole
