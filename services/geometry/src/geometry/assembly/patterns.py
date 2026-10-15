"""Component patterns: the copies a pattern places, after the solve (ASM-A3).

A pattern (:mod:`loft_wire.component_patterns`) is expanded AFTER the mate
solve, from the solved poses: each copy is its seed's solved pose moved by the
pattern's transform, so a copy is fixed relative to its seed and to the
pattern's reference geometry, the way Fusion 360 places pattern copies. Copies
are not solver bodies and nothing can be jointed to them.

The transforms are world-frame rigid motions, one per copy, shared by every
seed of the pattern:

- **linear**: ``k * spacing`` along the direction (``k = 1 .. count-1``);
- **circular**: a turn of ``k * step`` about the axis, ``step = angle/count``
  for a full 360 degree ring and ``angle/(count-1)`` otherwise;
- **hole** (pattern-driven): for each matching hole ``h`` of each driving
  instance ``j``, ``W_j o T(c_h - c_0) o W_d^-1``, where ``W`` are the driving
  instances' solved poses, ``c_0`` the seed hole's centre and ``c_h`` the
  hole's, both in the part's own frame. The seed hole on the first driver is
  the identity and is skipped.

A direction or axis comes from a straight edge (its line, start to end in the
joint-origin convention), a circular edge (its axis through the centre, out of
the face it bounds), or an origin axis. Edges resolve through the same tiered
resolvers as joint origins, so a pattern follows a part edit.

Every failure is a typed per-pattern error and the pattern places nothing; the
rest of the assembly is unaffected (the never-500 posture of §4).

The OCP wheel ships no type stubs; the directives scope that to this file.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false

from __future__ import annotations

import math
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from build123d import GeomType
from loft_wire.assemblies import (
    MAX_ASSEMBLY_INSTANCES,
    occurrence_id,
)
from loft_wire.component_patterns import (
    CircularComponentPattern,
    EdgeAxisRef,
    EvaluatedPattern,
    HoleComponentPattern,
    LinearComponentPattern,
    OriginAxisRef,
    PatternCopyRef,
    PatternCount,
    pattern_copy_id,
)
from loft_wire.joints import JointOrigin
from numpy.typing import NDArray
from OCP.BRepAdaptor import BRepAdaptor_Curve

from geometry.assembly.joint_origins import FaceNames, resolve_joint_origin
from geometry.assembly.protocol import AssemblyDefinitionError
from geometry.assembly.transform import Pose, as_vector, quat_normalize
from geometry.kernel.edges import resolve_edge_durable
from geometry.kernel.faces import SubshapeAmbiguousError, SubshapeUnresolvedError
from geometry.kernel.types import BodyShape

Vector = NDArray[np.float64]

#: Two hole centres, radii or plane offsets closer than this (mm) are the same.
#: Far above float64 noise on model coordinates, far below any real hole pitch.
HOLE_MATCH_TOL_MM = 1e-6

#: |a.b| above this treats two hole axes as parallel.
_PARALLEL_COS = 1.0 - 1e-9

#: A full ring: the angle at which the last copy would land on the seed.
_FULL_TURN_DEG = 360.0

_ORIGIN_AXES: dict[str, Vector] = {
    "x": np.array([1.0, 0.0, 0.0], dtype=np.float64),
    "y": np.array([0.0, 1.0, 0.0], dtype=np.float64),
    "z": np.array([0.0, 0.0, 1.0], dtype=np.float64),
}


@dataclass(frozen=True)
class PatternTarget:
    """What a pattern may read: one placed part occurrence (service-internal)."""

    body: BodyShape | None
    placement: Pose
    part_key: str
    face_names: Callable[[], FaceNames]


@dataclass(frozen=True)
class SeedPart:
    """One part a seed places: the whole seed for a part instance, or one part
    of a sub-assembly seed (``inner`` is its path below the seed instance)."""

    inner: tuple[uuid.UUID, ...]
    placement: Pose


@dataclass(frozen=True)
class PatternCopy:
    """One part a pattern copy places (service-internal)."""

    occurrence_id: uuid.UUID
    path: tuple[uuid.UUID, ...]
    group_id: uuid.UUID
    placement: Pose
    ref: PatternCopyRef
    #: The seed part this copies (its path below the seed instance).
    inner: tuple[uuid.UUID, ...]


class PatternError(Exception):
    """A pattern that cannot be placed, with its typed code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _unit(vec: Vector, what: str) -> Vector:
    norm = float(np.linalg.norm(vec))
    if norm == 0.0:
        raise PatternError("pattern_axis_degenerate", f"the {what} has no direction")
    return vec / norm


def _target(
    targets: dict[uuid.UUID, PatternTarget], instance_id: uuid.UUID
) -> PatternTarget:
    found = targets.get(instance_id)
    if found is None:
        raise PatternError(
            "pattern_reference_missing",
            f"the pattern reads geometry from {instance_id}, which is not a part "
            "placed by this assembly",
        )
    if found.body is None:
        raise PatternError(
            "pattern_reference_missing",
            f"the part the pattern reads geometry from ({instance_id}) has no body",
        )
    return found


def _resolve_origin(
    target: PatternTarget, origin: JointOrigin
) -> tuple[Vector, Vector]:
    """A joint-origin-style point + Z on *target*, in WORLD coordinates."""
    assert target.body is not None
    try:
        frame = resolve_joint_origin(
            target.body, origin, face_names=target.face_names()
        )
    except AssemblyDefinitionError as exc:
        cause = exc.__cause__
        code = (
            "subshape_ambiguous"
            if isinstance(cause, SubshapeAmbiguousError)
            else "subshape_unresolved"
        )
        raise PatternError(code, f"pattern reference: {exc}") from exc
    point = target.placement.apply_point(as_vector(frame.origin))
    z = target.placement.apply_direction(as_vector(frame.z))
    return point, _unit(z, "picked edge")


def resolve_axis(
    ref: EdgeAxisRef | OriginAxisRef, targets: dict[uuid.UUID, PatternTarget]
) -> tuple[Vector, Vector]:
    """A pattern direction / axis as a world point and unit direction."""
    if isinstance(ref, OriginAxisRef):
        return np.zeros(3, dtype=np.float64), _ORIGIN_AXES[ref.axis].copy()
    target = _target(targets, ref.instance_id)
    if ref.signature.curve == "circle":
        origin = JointOrigin(
            instance_id=ref.instance_id, kind="circle_centre", signature=ref.signature
        )
    else:
        origin = JointOrigin(
            instance_id=ref.instance_id,
            kind="edge_point",
            signature=ref.signature,
            at="start",
        )
    return _resolve_origin(target, origin)


def _rotation(axis: Vector, angle_rad: float) -> Vector:
    half = 0.5 * angle_rad
    s = math.sin(half)
    return quat_normalize(
        np.array([axis[0] * s, axis[1] * s, axis[2] * s, math.cos(half)])
    )


def linear_transforms(
    pattern: LinearComponentPattern, targets: dict[uuid.UUID, PatternTarget]
) -> list[Pose]:
    _point, direction = resolve_axis(pattern.direction, targets)
    if pattern.flip:
        direction = -direction
    identity = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float64)
    return [
        Pose(t=direction * (pattern.spacing_mm * k), q=identity.copy())
        for k in range(1, pattern.count)
    ]


def circular_step_deg(pattern: CircularComponentPattern) -> float:
    """The angle between neighbouring copies (degrees)."""
    if abs(pattern.angle_deg - _FULL_TURN_DEG) <= 1e-9:
        return _FULL_TURN_DEG / pattern.count
    return pattern.angle_deg / (pattern.count - 1)


def circular_transforms(
    pattern: CircularComponentPattern, targets: dict[uuid.UUID, PatternTarget]
) -> list[Pose]:
    point, axis = resolve_axis(pattern.axis, targets)
    if pattern.flip:
        axis = -axis
    step = math.radians(circular_step_deg(pattern))
    out: list[Pose] = []
    for k in range(1, pattern.count):
        rotation = Pose(t=np.zeros(3, dtype=np.float64), q=_rotation(axis, k * step))
        # About the axis through `point`: p -> R (p - point) + point.
        out.append(Pose(t=point - rotation.apply_direction(point), q=rotation.q))
    return out


def _circle(edge_wrapped: object) -> tuple[Vector, Vector, float]:
    circle = BRepAdaptor_Curve(edge_wrapped).Circle()
    loc = circle.Location()
    d = circle.Axis().Direction()
    centre = np.array([loc.X(), loc.Y(), loc.Z()], dtype=np.float64)
    axis = np.array([d.X(), d.Y(), d.Z()], dtype=np.float64)
    return centre, axis, float(circle.Radius())


def matching_holes(
    body: BodyShape, centre: Vector, axis: Vector, radius: float
) -> list[Vector]:
    """Centres (part frame) of every circle of *body* like the seed hole: the
    same radius, a parallel axis, its centre on the seed hole's plane.

    Deduplicated by centre and sorted, so the order is a pure function of the
    geometry.
    """
    found: list[Vector] = []
    for edge in body.edges():
        if edge.geom_type != GeomType.CIRCLE:
            continue
        c, a, r = _circle(edge.wrapped)
        if abs(r - radius) > HOLE_MATCH_TOL_MM:
            continue
        if abs(float(np.dot(a, axis))) < _PARALLEL_COS:
            continue
        if abs(float(np.dot(c - centre, axis))) > HOLE_MATCH_TOL_MM:
            continue
        if any(float(np.linalg.norm(c - seen)) <= HOLE_MATCH_TOL_MM for seen in found):
            continue
        found.append(c)
    return sorted(
        found,
        key=lambda c: tuple(round(float(v) / HOLE_MATCH_TOL_MM) for v in c),
    )


def _seed_hole(
    pattern: HoleComponentPattern, driver: PatternTarget
) -> tuple[Vector, Vector, float]:
    """The seed hole's centre, axis and radius in the driving PART's frame,
    resolved through the durable edge resolver (so it follows a part edit)."""
    assert driver.body is not None
    try:
        edge = resolve_edge_durable(
            driver.body, pattern.seed_hole.signature, face_names=driver.face_names()
        ).edge
    except SubshapeAmbiguousError as exc:
        raise PatternError("subshape_ambiguous", f"seed hole: {exc}") from exc
    except SubshapeUnresolvedError as exc:
        raise PatternError("subshape_unresolved", f"seed hole: {exc}") from exc
    if edge.geom_type != GeomType.CIRCLE:
        raise PatternError(
            "pattern_hole_not_circle",
            "the seed hole resolved to an edge that is not a circle",
        )
    return _circle(edge.wrapped)


def hole_transforms(
    pattern: HoleComponentPattern, targets: dict[uuid.UUID, PatternTarget]
) -> list[Pose]:
    driver = _target(targets, pattern.seed_hole.instance_id)
    assert driver.body is not None
    centre, axis, radius = _seed_hole(pattern, driver)
    holes = matching_holes(driver.body, centre, axis, radius)
    drivers = [driver]
    for other_id in pattern.also_on:
        other = _target(targets, other_id)
        if other.part_key != driver.part_key:
            raise PatternError(
                "pattern_driver_mismatch",
                f"{other_id} is not an instance of the driving part, so it has "
                "no matching holes",
            )
        drivers.append(other)
    to_driver_frame = driver.placement.inverse()
    identity = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float64)
    out: list[Pose] = []
    for index, target in enumerate(drivers):
        for hole in holes:
            shift = hole - centre
            if index == 0 and float(np.linalg.norm(shift)) <= HOLE_MATCH_TOL_MM:
                continue  # the seed's own hole
            move = Pose(t=shift, q=identity.copy())
            out.append(target.placement.compose(move).compose(to_driver_frame))
    return out


def pattern_transforms(
    evaluated: EvaluatedPattern, targets: dict[uuid.UUID, PatternTarget]
) -> list[Pose]:
    """One world transform per copy (the seed itself excluded)."""
    pattern = evaluated.pattern
    if isinstance(pattern, LinearComponentPattern):
        return linear_transforms(pattern, targets)
    if isinstance(pattern, CircularComponentPattern):
        return circular_transforms(pattern, targets)
    return hole_transforms(pattern, targets)


def expand_pattern(
    evaluated: EvaluatedPattern,
    seeds: dict[uuid.UUID, list[SeedPart]],
    targets: dict[uuid.UUID, PatternTarget],
    budget: int,
) -> tuple[list[PatternCopy], PatternCount]:
    """The parts *evaluated* adds, and its count, within *budget* parts.

    *seeds* maps each instance of the assembly to the parts it places.
    """
    pattern_id = evaluated.pattern_id
    try:
        for seed_id in evaluated.pattern.seed_instance_ids:
            if seed_id not in seeds:
                raise PatternError(
                    "pattern_seed_missing",
                    f"seed {seed_id} is not an instance of this assembly",
                )
        transforms = pattern_transforms(evaluated, targets)
        per_copy = sum(len(seeds[s]) for s in evaluated.pattern.seed_instance_ids)
        adds = per_copy * len(transforms)
        if adds > budget:
            raise PatternError(
                "pattern_too_large",
                f"the pattern would place {adds} more parts; at most "
                f"{MAX_ASSEMBLY_INSTANCES} can be evaluated at once",
            )
    except PatternError as exc:
        return [], PatternCount(
            pattern_id=pattern_id,
            count=None,
            error_code=exc.code,
            error_message=exc.message,
        )
    copies: list[PatternCopy] = []
    for seed_id in evaluated.pattern.seed_instance_ids:
        for index, transform in enumerate(transforms, start=1):
            copy_id = pattern_copy_id(pattern_id, seed_id, index)
            ref = PatternCopyRef(
                pattern_id=pattern_id, seed_instance_id=seed_id, index=index
            )
            for part in seeds[seed_id]:
                path = (copy_id, *part.inner)
                copies.append(
                    PatternCopy(
                        occurrence_id=occurrence_id(path) if part.inner else copy_id,
                        path=path if part.inner else (),
                        group_id=copy_id,
                        placement=transform.compose(part.placement),
                        ref=ref,
                        inner=part.inner,
                    )
                )
    return copies, PatternCount(pattern_id=pattern_id, count=len(transforms) + 1)
