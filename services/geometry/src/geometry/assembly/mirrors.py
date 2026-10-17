"""Mirror components: the twins a mirror places, after the solve
(ASM-MIRROR-COMPONENT).

A mirror (:mod:`loft_wire.component_mirrors`) reflects seed instances about a
plane. It is placed AFTER the mate solve (and after the component patterns),
from the seeds' solved poses, so a twin follows its seed's edits and moves the
way Fusion 360's mirrored components do. Twins are not solver bodies.

**Never an improper placement.** A reflection ``M = I - 2 n n^T`` has
determinant -1: applied to a placement it would turn the body inside out in a
STEP file and in the viewport's meshes. So with the seed's solved pose
``(R, t)``, its local axis ``e_k`` most aligned with the plane normal (``R^T n``,
the lowest index on a tie) and its local bounding-box centre ``c``, every twin
is placed by the PROPER rigid motion

    R' = M R D_k,    t' = M (R (2 c_k e_k) + t - p) + p

(``D_k`` reflects local axis ``k``; ``det R' = (-1)(-1) = +1``). That pose maps
the body reflected about its own plane ``x_k = c_k`` onto the exact mirror image
of the seed, for any body and any ``k``:

- a **mirrored copy** places the seed's own body there, which is the mirror
  image exactly when the body is symmetric about that plane (SolidWorks'
  bounding-box-centre copy orientation). A part whose centroid is off the plane
  cannot be, and is reported in ``MirrorState.asymmetric``;
- an **opposite-hand version** places the body reflected about its own plane
  ``x = c_x`` (always local X, whatever the pose, so a part has ONE opposite
  hand: one body, mesh and STEP product however its twins are oriented). OCCT
  reflects with ``BRepBuilderAPI_Transform``, which reverses the faces, so the
  result is a valid solid of positive volume. It is a DERIVED part keyed
  ``<part_key>#opposite``, rebuilt with the source on every evaluation. Its mass
  properties are the source's, reflected (same volume, area and mass; the
  centroid reflected; the box unchanged, since it is reflected about its own
  centre).

A sub-assembly seed is mirrored as one rigid body: its twin's frame is the
seed's frame mirrored the same way (its box is the union of its parts' exact
boxes in its own frame), and each of its parts keeps its pose in that frame.
Opposite hands are for part seeds only.

Every failure is a typed per-mirror error and the mirror places nothing; the
rest of the assembly is unaffected (the never-500 posture of §4).

The OCP wheel ships no type stubs; the directives scope that to this file.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from build123d import Location, Plane
from loft_wire.assemblies import MAX_ASSEMBLY_INSTANCES, occurrence_id
from loft_wire.component_mirrors import (
    EvaluatedMirror,
    MirrorCopyRef,
    MirrorFaceRef,
    MirrorOriginPlaneRef,
    MirrorState,
    mirror_copy_id,
)
from loft_wire.geometry import BoundingBox, ShapeProperties, Vec3
from loft_wire.joints import JointOrigin
from numpy.typing import NDArray

from geometry.assembly.joint_origins import FaceNames, resolve_joint_origin
from geometry.assembly.protocol import AssemblyDefinitionError
from geometry.assembly.transform import Pose, as_vector, matrix_to_quat
from geometry.kernel.export import placement_trsf
from geometry.kernel.faces import SubshapeAmbiguousError
from geometry.kernel.tessellate import tessellate_glb
from geometry.kernel.types import BodyShape
from geometry.mesh_store import store_mesh_glb

Vector = NDArray[np.float64]

#: A copy's part counts as symmetric when its centroid is within this distance
#: (mm) of the plane the copy assumes it is symmetric about: far above the
#: integration noise of a symmetric body's centroid (measured below 1e-9 mm on
#: the goldens), far below any asymmetry an engineer would build.
SYMMETRY_TOL_MM = 1e-4

_PLANE_NORMALS: dict[str, Vector] = {
    "xy": np.array([0.0, 0.0, 1.0], dtype=np.float64),
    "yz": np.array([1.0, 0.0, 0.0], dtype=np.float64),
    "zx": np.array([0.0, 1.0, 0.0], dtype=np.float64),
}

_INSTANCE_SUFFIX = re.compile(r"\s*<\d+>$")


@dataclass(frozen=True)
class MirrorSource:
    """One part a seed places, as a mirror reads it (service-internal)."""

    #: Its path below the seed instance (empty for a part seed).
    inner: tuple[uuid.UUID, ...]
    #: Its pose in the seed's frame (identity for a part seed).
    offset: Pose
    part_key: str
    body: BodyShape | None
    #: The part's own mass properties (its local box and centroid).
    properties: ShapeProperties | None


@dataclass(frozen=True)
class MirrorSeed:
    """One instance a mirror may reflect: its solved pose and its parts."""

    pose: Pose
    is_part: bool
    parts: tuple[MirrorSource, ...]


@dataclass(frozen=True)
class MirrorTarget:
    """A placed part a mirror plane may be picked on (service-internal)."""

    body: BodyShape | None
    placement: Pose
    face_names: Callable[[], FaceNames]


#: The local axis an opposite hand is reflected along (module docstring).
OPPOSITE_HAND_AXIS = 0


@dataclass(frozen=True)
class OppositeHand:
    """The derived part an opposite-hand twin places: the source part
    reflected about its own plane ``x = centre``."""

    source_key: str
    centre: float
    axis: int = OPPOSITE_HAND_AXIS

    @property
    def part_key(self) -> str:
        return opposite_hand_key(self.source_key)


@dataclass(frozen=True)
class MirrorTwin:
    """One part a mirror twin places (service-internal)."""

    occurrence_id: uuid.UUID
    path: tuple[uuid.UUID, ...]
    group_id: uuid.UUID
    placement: Pose
    ref: MirrorCopyRef
    #: The seed part this mirrors (its path below the seed instance).
    inner: tuple[uuid.UUID, ...]
    #: Set for an opposite-hand twin: the derived part it places.
    opposite: OppositeHand | None


class MirrorError(Exception):
    """A mirror that cannot be placed, with its typed code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def opposite_hand_key(part_key: str) -> str:
    """The derived part key of *part_key*'s opposite hand."""
    return f"{part_key}#opposite"


def source_part_key(part_key: str) -> str:
    """The part key an (opposite-hand) part key derives from; itself otherwise."""
    return part_key.split("#", 1)[0]


def mirrored_name(name: str | None, opposite: bool) -> str | None:
    """A twin's name: "Crank arm <1> (mirror)" for a copy, and "Crank arm
    (opposite hand) <1>" for an opposite hand, so the STEP product (the name
    without its ``<n>``) names the derived part."""
    if name is None:
        return None
    if not opposite:
        return f"{name} (mirror)"
    match = _INSTANCE_SUFFIX.search(name)
    suffix = match.group(0) if match else ""
    base = name[: len(name) - len(suffix)] if suffix else name
    return f"{base} (opposite hand){suffix}"


def _reflection(normal: Vector) -> NDArray[np.float64]:
    return np.eye(3, dtype=np.float64) - 2.0 * np.outer(normal, normal)


def _unit(vec: Vector) -> Vector:
    norm = float(np.linalg.norm(vec))
    if norm == 0.0:
        raise MirrorError("mirror_plane_degenerate", "the mirror plane has no normal")
    return vec / norm


def resolve_plane(
    evaluated: EvaluatedMirror, targets: dict[uuid.UUID, MirrorTarget]
) -> tuple[Vector, Vector]:
    """The mirror plane as a world point and unit normal."""
    plane = evaluated.mirror.plane
    if isinstance(plane, MirrorOriginPlaneRef):
        normal = _PLANE_NORMALS[plane.plane].copy()
        return normal * plane.offset_mm, normal
    assert isinstance(plane, MirrorFaceRef)
    target = targets.get(plane.instance_id)
    if target is None or target.body is None:
        raise MirrorError(
            "mirror_reference_missing",
            f"the mirror plane is picked on {plane.instance_id}, which is not a "
            "part with a body placed by this assembly",
        )
    origin = JointOrigin(
        instance_id=plane.instance_id, kind="face_centre", signature=plane.signature
    )
    try:
        frame = resolve_joint_origin(
            target.body, origin, face_names=target.face_names()
        )
    except AssemblyDefinitionError as exc:
        code = (
            "subshape_ambiguous"
            if isinstance(exc.__cause__, SubshapeAmbiguousError)
            else "subshape_unresolved"
        )
        raise MirrorError(code, f"mirror plane: {exc}") from exc
    point = target.placement.apply_point(as_vector(frame.origin))
    normal = target.placement.apply_direction(as_vector(frame.z))
    return point, _unit(normal)


def mirror_axis(pose: Pose, normal: Vector) -> int:
    """The seed's local axis most aligned with the plane *normal* (the lowest
    index on a tie): the axis its twin is reflected along."""
    local = pose.matrix().T @ normal
    return int(np.argmax(np.abs(local)))


def _box_centre(box: BoundingBox, axis: int) -> float:
    lo = (box.min.x, box.min.y, box.min.z)[axis]
    hi = (box.max.x, box.max.y, box.max.z)[axis]
    return 0.5 * (lo + hi)


def _seed_centre(seed: MirrorSeed, axis: int) -> float:
    """The seed's bounding-box centre along local *axis*, in its own frame.

    A part's exact box is in its properties; a sub-assembly's is the union of
    its parts' exact boxes, each part moved to its pose in the seed's frame.
    A seed with no body at all mirrors about its origin.
    """
    if seed.is_part:
        props = seed.parts[0].properties
        return 0.0 if props is None else _box_centre(props.bounding_box, axis)
    lo, hi = np.inf, -np.inf
    for part in seed.parts:
        if part.body is None:
            continue
        trsf = placement_trsf(
            (float(part.offset.t[0]), float(part.offset.t[1]), float(part.offset.t[2])),
            (
                float(part.offset.q[0]),
                float(part.offset.q[1]),
                float(part.offset.q[2]),
                float(part.offset.q[3]),
            ),
        )
        box = part.body.moved(Location(trsf)).bounding_box(optimal=True)
        lo = min(lo, (box.min.X, box.min.Y, box.min.Z)[axis])
        hi = max(hi, (box.max.X, box.max.Y, box.max.Z)[axis])
    return 0.0 if lo > hi else 0.5 * (lo + hi)


def twin_pose(
    seed_pose: Pose, point: Vector, normal: Vector, axis: int, centre: float
) -> Pose:
    """The proper rigid pose of a seed's twin (module docstring)."""
    reflect = _reflection(normal)
    flip = np.ones(3, dtype=np.float64)
    flip[axis] = -1.0
    rotation = reflect @ seed_pose.matrix() @ np.diag(flip)
    shift = np.zeros(3, dtype=np.float64)
    shift[axis] = 2.0 * centre
    t = reflect @ (seed_pose.matrix() @ shift + seed_pose.t - point) + point
    return Pose(t=t, q=matrix_to_quat(rotation))


def is_symmetric(props: ShapeProperties | None, axis: int, centre: float) -> bool:
    """Whether a part's centroid lies on its plane ``x_axis = centre`` (a
    necessary condition for symmetry about it; a bodiless part says nothing)."""
    if props is None:
        return True
    c = props.centroid
    return abs((c.x, c.y, c.z)[axis] - centre) <= SYMMETRY_TOL_MM


def expand_mirror(
    evaluated: EvaluatedMirror,
    seeds: dict[uuid.UUID, MirrorSeed],
    targets: dict[uuid.UUID, MirrorTarget],
    budget: int,
) -> tuple[list[MirrorTwin], MirrorState]:
    """The parts *evaluated* adds, and its state, within *budget* parts."""
    mirror = evaluated.mirror
    mirror_id = evaluated.mirror_id
    opposite = set(mirror.opposite_hand_instance_ids)
    try:
        for seed_id in mirror.seed_instance_ids:
            seed = seeds.get(seed_id)
            if seed is None:
                raise MirrorError(
                    "mirror_seed_missing",
                    f"seed {seed_id} is not an instance of this assembly",
                )
            if seed_id in opposite and not seed.is_part:
                raise MirrorError(
                    "mirror_opposite_hand_needs_part",
                    "an opposite-hand version is made of a part; mirror a "
                    "sub-assembly as a copy",
                )
        adds = sum(len(seeds[s].parts) for s in mirror.seed_instance_ids)
        if adds > budget:
            raise MirrorError(
                "mirror_too_large",
                f"the mirror would place {adds} more parts; at most "
                f"{MAX_ASSEMBLY_INSTANCES} can be evaluated at once",
            )
        point, normal = resolve_plane(evaluated, targets)
    except MirrorError as exc:
        return [], MirrorState(
            mirror_id=mirror_id,
            placed=0,
            error_code=exc.code,
            error_message=exc.message,
        )
    twins: list[MirrorTwin] = []
    asymmetric: list[uuid.UUID] = []
    for seed_id in mirror.seed_instance_ids:
        seed = seeds[seed_id]
        hand = seed_id in opposite
        axis = OPPOSITE_HAND_AXIS if hand else mirror_axis(seed.pose, normal)
        centre = _seed_centre(seed, axis)
        pose = twin_pose(seed.pose, point, normal, axis, centre)
        if (
            seed.is_part
            and not hand
            and not is_symmetric(seed.parts[0].properties, axis, centre)
        ):
            asymmetric.append(seed_id)
        copy_id = mirror_copy_id(mirror_id, seed_id)
        ref = MirrorCopyRef(
            mirror_id=mirror_id, seed_instance_id=seed_id, opposite_hand=hand
        )
        for part in seed.parts:
            path = (copy_id, *part.inner)
            twins.append(
                MirrorTwin(
                    occurrence_id=occurrence_id(path) if part.inner else copy_id,
                    path=path if part.inner else (),
                    group_id=copy_id,
                    placement=pose.compose(part.offset),
                    ref=ref,
                    inner=part.inner,
                    opposite=(
                        OppositeHand(source_key=part.part_key, centre=centre)
                        if hand
                        else None
                    ),
                )
            )
    return twins, MirrorState(
        mirror_id=mirror_id, placed=len(mirror.seed_instance_ids), asymmetric=asymmetric
    )


def _reflect_coordinate(vec: Vec3, axis: int, centre: float) -> Vec3:
    values = [vec.x, vec.y, vec.z]
    values[axis] = 2.0 * centre - values[axis]
    return Vec3(x=values[0], y=values[1], z=values[2])


def opposite_hand_properties(
    props: ShapeProperties, axis: int, centre: float
) -> ShapeProperties:
    """The source part's mass properties, reflected about ``x_axis = centre``:
    a reflection is an isometry, so volume, area, mass and topology are equal;
    the centroid (and centre of mass) reflect; the box, reflected about its
    own centre, is unchanged."""
    return props.model_copy(
        update={
            "centroid": _reflect_coordinate(props.centroid, axis, centre),
            "center_of_mass": (
                None
                if props.center_of_mass is None
                else _reflect_coordinate(props.center_of_mass, axis, centre)
            ),
        }
    )


def opposite_hand_body(body: BodyShape, axis: int, centre: float) -> BodyShape:
    """*body* reflected about its own plane ``x_axis = centre``."""
    origin = [0.0, 0.0, 0.0]
    origin[axis] = centre
    normal = [0.0, 0.0, 0.0]
    normal[axis] = 1.0
    return body.mirror(Plane(origin=tuple(origin), z_dir=tuple(normal)))


def opposite_hand_mesh(
    body: BodyShape, linear_deflection: float, *, twisted: bool
) -> str:
    """Tessellate and store an opposite-hand body: its content-addressed id."""
    glb, _stats = tessellate_glb(body, linear_deflection, twisted=twisted)
    return store_mesh_glb(glb)
