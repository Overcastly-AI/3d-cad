"""Sketch profile → face → linear extrusion → boolean against the body.

The kernel half of the extrude feature (feature-tree design §4.3): the
feature layer hands in *solved* sketch entities (pydantic DTOs from
:mod:`py_kit.schemas.sketch` — positions already through the solver) plus the
datum plane and scalar parameters; this module owns every OCCT/build123d
call. Failures raise the typed exceptions below with **sanitized messages**
(no kernel internals) — the feature layer maps them 1:1 onto ``FeatureError``
codes, so geometry outcomes stay values at the boundary.

Determinism (RESEARCH §9): profile edges are built in the entity list order,
wire assembly and booleans are pure OCCT algorithms on identical inputs, and
no iteration over unordered containers participates.

v1 profile rules (documented limits, not accidents):

- ``point`` entities are **construction geometry** — ignored for the profile.
- All curve entities together must form exactly **one closed wire**. An open
  or broken chain raises :class:`ProfileNotClosedError`; multiple disjoint
  closed loops (including hole-in-profile nesting) raise
  :class:`ProfileUnsupportedError` until a multi-loop face design lands.
- The extrusion is a single body chain (design §7.6): a boolean whose result
  is not exactly one solid raises :class:`BooleanError`.
"""

import math
from collections.abc import Sequence
from typing import Literal

from build123d import Edge, Face, Plane, Solid, Vector, Wire
from py_kit.schemas.sketch import (
    Point2D,
    SketchArc,
    SketchCircle,
    SketchEntity,
    SketchLine,
    SketchPoint,
)

#: The three origin datum planes (design §2.1), by their wire name. Local
#: sketch (x, y) coordinates map through ``x_dir``/``y_dir``; the extrusion
#: normal is ``z_dir``. Single source for plane orientation — the sketch and
#: extrude features must agree on it.
DATUM_PLANES: dict[str, Plane] = {
    "XY": Plane.XY,
    "XZ": Plane.XZ,
    "YZ": Plane.YZ,
}

#: Wire-assembly tolerance (mm) for chaining profile edges. Solved coincident
#: endpoints are bitwise identical (solver gate, RESEARCH §2), so this is a
#: numerical formality, aligned with the kernel linear tolerance (1e-7 m,
#: CLAUDE.md — model units are mm).
PROFILE_WIRE_TOLERANCE = 1e-4


class ProfileNotClosedError(ValueError):
    """The sketch's curve entities do not form a closed wire."""


class ProfileUnsupportedError(ValueError):
    """The profile is closed but outside v1 support (multiple loops)."""


class BooleanError(RuntimeError):
    """A boolean against the body failed or left an unsupported result."""


def _to_world(plane: Plane, point: Point2D) -> Vector:
    """Map sketch-local (x, y) mm onto *plane* in world coordinates."""
    return plane.origin + plane.x_dir * point.x + plane.y_dir * point.y


def _entity_edges(plane: Plane, entity: SketchEntity) -> list[Edge]:
    """The profile edge(s) contributed by one solved sketch entity."""
    match entity:
        case SketchPoint():
            return []  # construction geometry — never part of the profile
        case SketchLine():
            return [
                Edge.make_line(
                    _to_world(plane, entity.start), _to_world(plane, entity.end)
                )
            ]
        case SketchCircle():
            return [
                Edge.make_circle(
                    entity.radius,
                    Plane(
                        origin=_to_world(plane, entity.center),
                        x_dir=plane.x_dir,
                        z_dir=plane.z_dir,
                    ),
                )
            ]
        case SketchArc():
            radius = math.hypot(
                entity.start.x - entity.center.x, entity.start.y - entity.center.y
            )
            if radius <= 0.0:
                raise ProfileNotClosedError(
                    f"Arc '{entity.id}' is degenerate (zero radius) and cannot "
                    "bound a profile."
                )
            start_angle = math.degrees(
                math.atan2(
                    entity.start.y - entity.center.y, entity.start.x - entity.center.x
                )
            )
            end_angle = math.degrees(
                math.atan2(
                    entity.end.y - entity.center.y, entity.end.x - entity.center.x
                )
            )
            return [
                Edge.make_circle(
                    radius,
                    Plane(
                        origin=_to_world(plane, entity.center),
                        x_dir=plane.x_dir,
                        z_dir=plane.z_dir,
                    ),
                    start_angle=start_angle,
                    end_angle=end_angle,
                )
            ]


def build_profile_face(
    plane_name: Literal["XY", "XZ", "YZ"], entities: Sequence[SketchEntity]
) -> Face:
    """Assemble solved sketch entities into the single closed profile face.

    Raises:
        ProfileNotClosedError: no curve entities, or the chained edges do not
            close into a loop.
        ProfileUnsupportedError: more than one closed loop (v1 supports a
            single-loop profile; holes/multi-loop faces are a later item).
    """
    plane = DATUM_PLANES[plane_name]
    edges: list[Edge] = []
    for entity in entities:
        edges.extend(_entity_edges(plane, entity))

    if not edges:
        raise ProfileNotClosedError(
            "Sketch contains no profile curves (points are construction "
            "geometry); nothing to extrude."
        )

    wires = Wire.combine(edges, tol=PROFILE_WIRE_TOLERANCE)
    if len(wires) > 1:
        raise ProfileUnsupportedError(
            f"Sketch profile forms {len(wires)} separate loops; extrude "
            "supports exactly one closed loop in v1."
        )
    wire = wires[0]
    if not wire.is_closed:
        raise ProfileNotClosedError(
            "Sketch profile is not a closed loop; close the boundary (e.g. "
            "with coincident constraints) before extruding."
        )
    return Face(wire)


def extrude_face(
    face: Face,
    plane_name: Literal["XY", "XZ", "YZ"],
    distance_mm: float,
    reverse: bool,
) -> Solid:
    """Linear-extrude *face* along the sketch plane normal (mm).

    ``reverse`` extrudes along the negative normal (``direction: "reverse"``).
    """
    if distance_mm <= 0:
        raise ValueError(f"distance_mm must be > 0, got {distance_mm}")
    normal = DATUM_PLANES[plane_name].z_dir
    direction = normal * (-distance_mm if reverse else distance_mm)
    return Solid.extrude(face, direction)


def combine_body(
    body: Solid | None, tool: Solid, operation: Literal["add", "cut"]
) -> Solid:
    """Boolean *tool* against *body*; returns the new single-solid body.

    ``add`` with no prior body starts the body chain with *tool*. ``cut``
    with no prior body is a **feature-layer** error (``no_prior_body``) and
    never reaches here — asserting that keeps the contract explicit.

    Raises:
        BooleanError: the kernel boolean failed, produced no solid (e.g. a
            cut that consumed the whole body), or produced multiple disjoint
            solids (single body chain per part in v1, design §7.6).
    """
    if body is None:
        assert operation == "add", "cut without a body is handled by the caller"
        return tool

    try:
        # fuse/cut signatures carry Shape[Unknown] type params upstream (same
        # gap tessellate.py documents for export_gltf) — scoped ignores only.
        result = (
            body.fuse(tool)  # pyright: ignore[reportUnknownMemberType]
            if operation == "add"
            else body.cut(tool)  # pyright: ignore[reportUnknownMemberType]
        )
        solids = result.solids()
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        raise BooleanError(
            f"Boolean {operation} failed in the kernel "
            f"({type(exc).__name__}); the profile may self-intersect or "
            "graze the body."
        ) from exc

    if len(solids) == 0:
        raise BooleanError(
            f"Boolean {operation} left no material — the cut consumed the entire body."
        )
    if len(solids) > 1:
        raise BooleanError(
            f"Boolean {operation} produced {len(solids)} disjoint solids; "
            "parts are a single body in v1."
        )
    # clean() removes redundant seam faces/edges a boolean can leave behind,
    # keeping topology counts meaningful (and golden-assertable).
    return solids[0].clean()
