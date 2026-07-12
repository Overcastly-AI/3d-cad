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

- Entities flagged ``construction`` are reference-only (centerlines, symmetry
  axes, diagonals): they solve and can be constrained/referenced upstream, but
  are **excluded here** — the single profile-exclusion point for every
  body-affecting feature. ``point`` entities never bound a profile either.
- All remaining curve entities together must form exactly **one closed wire**.
  Marking a real profile edge construction opens the loop, so an open
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
    SketchSpline,
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


def plane_point_to_world(
    plane_name: Literal["XY", "XZ", "YZ"], point: Point2D
) -> Vector:
    """Map a solved sketch (x, y) mm onto its datum plane in world coordinates.

    The single public entry to the plane→world mapping the profile builder uses
    internally, so a feature that needs a sketch point in world space (e.g.
    revolve's axis endpoints) shares the EXACT mapping the profile is built with
    (CLAUDE.md DRY rule) — the axis and the profile can never disagree on where
    the sketch plane sits in the world.
    """
    return _to_world(DATUM_PLANES[plane_name], point)


def entity_edges(plane: Plane, entity: SketchEntity) -> list[Edge]:
    """The kernel edge(s) contributed by one solved sketch entity.

    THE single per-entity edge-construction point (CLAUDE.md DRY rule): the
    profile builder (:func:`build_profile_face`, closed wire) and the sweep path
    builder (:func:`geometry.kernel.sweep.build_path_wire`, open wire) both go
    through here, so a profile and a path can never disagree on how a sketch
    entity becomes a kernel edge. Construction geometry is excluded by each
    caller BEFORE this point (the single profile/path-exclusion points), so
    points map to no edges here only as a defensive default.
    """
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
        case SketchSpline():
            # Fit-point spline: an interpolating C2 B-spline through the ordered
            # fit points (OCCT GeomAPI_Interpolate via Edge.make_spline), so a
            # closed profile wire containing a spline edge extrudes/revolves like
            # any curve. Deterministic across processes (OCCT interpolation is
            # seed-free; verified in-process AND across interpreter restart by the
            # spline golden's determinism gates). Coincident consecutive fit
            # points make interpolation degenerate: reject with a legible profile
            # error (the degenerate-arc precedent above) rather than let OCCT
            # raise an opaque kernel failure.
            for prev, nxt in zip(entity.points, entity.points[1:], strict=False):
                if math.isclose(prev.x, nxt.x, abs_tol=1e-9) and math.isclose(
                    prev.y, nxt.y, abs_tol=1e-9
                ):
                    raise ProfileNotClosedError(
                        f"Spline '{entity.id}' has coincident consecutive fit "
                        f"points at ({prev.x}, {prev.y}); each fit point must be "
                        "distinct from the previous one."
                    )
            return [
                Edge.make_spline([_to_world(plane, point) for point in entity.points])
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
        # THE single profile-exclusion point (design §2.4 semantics): every
        # body-affecting feature that consumes a sketch profile builds it via
        # this function, so construction geometry is dropped here exactly once,
        # never per-feature. Input list order is preserved (determinism,
        # RESEARCH §9) — filtering does not reorder.
        if entity.construction:
            continue
        edges.extend(entity_edges(plane, entity))

    if not edges:
        raise ProfileNotClosedError(
            "Sketch contains no profile curves (only construction geometry "
            "and/or points); nothing to extrude."
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
