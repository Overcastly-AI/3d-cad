"""Mirror components in an assembly (ASM-MIRROR-COMPONENT).

SolidWorks' Mirror Components and Fusion 360's Mirror on components: pick
instances of the assembly (parts or rigid sub-assemblies) and a mirror plane,
and each one gets a mirrored twin on the other side of the plane. Per seed,
the twin is one of:

- a **mirrored copy** (the default): the SAME part, placed by a rigid motion.
  This is only a true mirror image of a part that is symmetric about one of
  its own planes, which is what SolidWorks' "copy" orientation assumes (a
  washer, a bolt, a flat crank arm); geometry tests the part against its own
  reflection, and reports a seed whose part is not symmetric so the user can
  switch it to an opposite hand;
- an **opposite-hand version** (``opposite_hand_instance_ids``, part seeds
  only): a DERIVED part whose geometry is the source part reflected, rebuilt
  from the source on every evaluation so it follows the source's edits
  (SolidWorks' "Create opposite hand version"). The bill of materials lists it
  as its own line, "<part> (opposite hand)".

The geometry rule (and why there are two kinds): a reflection has determinant
-1, so a reflected PLACEMENT is not a rigid motion, and a STEP file or a mesh
placed by one would be inside out. Geometry never emits one. With the mirror
``M`` (about the plane), the seed's pose ``(R, t)``, the seed's local axis
``e_k`` most aligned with the plane normal and ``c`` its local bounding-box
centre, the twin's pose is the PROPER rigid motion ``(M R D_k, M(R(c - D_k c) +
t - p) + p)`` with ``D_k`` the reflection of axis ``k``. Placed on the source
body that is the true mirror image when the body is symmetric about its plane
``x_k = c_k`` (a copy); placed on the body reflected about that plane it is the
true mirror image of any body (an opposite hand).

A mirror is ONE entry of the assembly holding its definition, like a component
pattern: its twins are placed by geometry after the solve, from the seeds'
solved poses, so they follow a seed's edits and moves. Twins are not solver
bodies and cannot carry joints; each is named by :func:`mirror_copy_id`.

The plane is an origin plane of the assembly (optionally offset along its
normal: an offset construction plane) or a planar face picked on a part.
Assemblies have no datum planes of their own yet.

Pure pydantic: no kernel type crosses the boundary (CLAUDE.md).
"""

import uuid
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator

from loft_wire.signatures import PlanarFaceSignature

#: Most seed instances one mirror reflects.
MAX_MIRROR_SEEDS = 50

#: Most mirrors one assembly may hold.
MAX_ASSEMBLY_MIRRORS = 200

#: Bound on an origin plane's offset (100 m), the joint length bound.
MAX_MIRROR_OFFSET_MM = 100_000.0

#: The assembly origin planes a mirror may use: XY (normal Z), YZ (normal X)
#: and ZX (normal Y).
OriginPlane = Literal["xy", "yz", "zx"]


class MirrorOriginPlaneRef(BaseModel):
    """An origin plane of the assembly, moved ``offset_mm`` along its normal."""

    kind: Literal["origin_plane"] = "origin_plane"
    plane: OriginPlane = Field(description="'xy', 'yz' or 'zx'")
    offset_mm: float = Field(
        default=0.0,
        ge=-MAX_MIRROR_OFFSET_MM,
        le=MAX_MIRROR_OFFSET_MM,
        allow_inf_nan=False,
        description="Distance (mm) the plane is moved along its normal (+Z for "
        "XY, +X for YZ, +Y for ZX)",
    )


class MirrorFaceRef(BaseModel):
    """A planar face picked on a part of the assembly: the plane it lies in.

    ``instance_id`` may be a part instance of this assembly or a part inside one
    of its sub-assemblies (an occurrence id, as joints use). It may not be a copy
    placed by a pattern or a mirror.
    """

    kind: Literal["face"] = "face"
    instance_id: uuid.UUID = Field(
        description="The instance (or nested occurrence) whose part carries the face"
    )
    signature: PlanarFaceSignature = Field(
        description="Stage-1 signature of the picked planar face"
    )


#: A mirror plane: an origin plane or a picked planar face.
MirrorPlaneRef = Annotated[
    MirrorOriginPlaneRef | MirrorFaceRef, Field(discriminator="kind")
]


class ComponentMirror(BaseModel):
    """Reflect ``seed_instance_ids`` about ``plane`` (see the module docstring).

    A seed listed in ``opposite_hand_instance_ids`` gets an opposite-hand
    version; every other seed gets a mirrored copy of itself.
    """

    seed_instance_ids: list[uuid.UUID] = Field(
        min_length=1,
        max_length=MAX_MIRROR_SEEDS,
        description="The instances to mirror (instances of this assembly: parts "
        "or rigid sub-assemblies), in order",
    )
    plane: MirrorPlaneRef = Field(description="The mirror plane")
    opposite_hand_instance_ids: list[uuid.UUID] = Field(
        default_factory=list["uuid.UUID"],
        max_length=MAX_MIRROR_SEEDS,
        description="The seeds (parts only) that get an opposite-hand version "
        "rather than a mirrored copy of themselves",
    )

    @model_validator(mode="after")
    def _seeds(self) -> Self:
        if len(set(self.seed_instance_ids)) != len(self.seed_instance_ids):
            raise ValueError("a seed instance is named twice")
        opposite = self.opposite_hand_instance_ids
        if len(set(opposite)) != len(opposite):
            raise ValueError("an opposite-hand instance is named twice")
        if not set(opposite) <= set(self.seed_instance_ids):
            raise ValueError("an opposite-hand instance must be one of the seeds")
        return self


def mirror_reference_ids(mirror: ComponentMirror) -> tuple[uuid.UUID, ...]:
    """The instance (or occurrence) ids a mirror READS geometry from (its
    plane face). Seeds are not included."""
    if isinstance(mirror.plane, MirrorFaceRef):
        return (mirror.plane.instance_id,)
    return ()


def mirror_copy_id(mirror_id: uuid.UUID, seed_instance_id: uuid.UUID) -> uuid.UUID:
    """The id of the twin *mirror_id* places for *seed_instance_id*.

    ``uuid5`` keyed on the mirror, as :func:`~loft_wire.component_patterns.
    pattern_copy_id` is, so documents, geometry and the web derive the same id.
    A twin of a sub-assembly seed stands in for that instance: its parts are
    :func:`~loft_wire.assemblies.nested_occurrence_id` of it.
    """
    return uuid.uuid5(mirror_id, f"{seed_instance_id}/mirror")


# --- CRUD DTOs ---------------------------------------------------------------------


class MirrorCreate(BaseModel):
    """Add a component mirror to an assembly."""

    expected_version: int = Field(
        ge=0, description="Optimistic-concurrency guard (design §1.2)"
    )
    mirror: ComponentMirror = Field(description="The mirror")


class MirrorUpdate(BaseModel):
    """Replace a mirror's definition (its id and position stay)."""

    expected_version: int = Field(
        ge=0, description="Optimistic-concurrency guard (design §1.2)"
    )
    mirror: ComponentMirror = Field(description="The new definition")


class MirrorResponse(BaseModel):
    """A mirror as stored."""

    id: uuid.UUID
    assembly_id: uuid.UUID
    order_index: int = Field(description="Stable order in the assembly's tree")
    mirror: ComponentMirror


class MirrorMutationResponse(BaseModel):
    """Result of a mirror write: the mirror + the new version."""

    mirror: MirrorResponse
    doc_version: int


class EvaluatedMirror(BaseModel):
    """One mirror as the evaluator sees it: its stored id names its twins."""

    mirror_id: uuid.UUID
    order_index: int = Field(ge=0, description="Expansion order (determinism)")
    mirror: ComponentMirror


class MirrorCopyRef(BaseModel):
    """Marks a result row as a mirror twin: which mirror, which seed, and
    whether it is an opposite-hand version (its mesh is then the reflected
    part's own)."""

    mirror_id: uuid.UUID
    seed_instance_id: uuid.UUID
    opposite_hand: bool = Field(
        default=False, description="An opposite-hand version, not a copy"
    )


class MirrorState(BaseModel):
    """How a mirror evaluated: the twins it placed, or why it placed none."""

    mirror_id: uuid.UUID
    placed: int = Field(ge=0, description="Twins placed (one per seed), or 0")
    error_code: str | None = Field(
        default=None, description="Why the mirror placed nothing, if it did not"
    )
    error_message: str | None = Field(default=None, description="The same, in words")
    asymmetric: list[uuid.UUID] = Field(
        default_factory=list["uuid.UUID"],
        description="Seeds mirrored as copies whose part (or sub-assembly) "
        "is not symmetric about any of its own mid-planes (checked by "
        "reflecting it): the copy is not a mirror image, and the seed wants an "
        "opposite hand instead",
    )
