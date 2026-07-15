"""Assembly boundary DTOs — placement, mates, and the assembly CRUD contract.

Implements docs/design/assemblies.md §1.5 (the persisted shapes) — the single
source of truth (CLAUDE.md DRY rule): the documents service validates writes
and serves its assembly CRUD API with these models, the geometry service parses
the evaluation request with the SAME models (§4, a later item), and ``just gen``
exports them to ``packages/contracts`` / ``packages/ts-client``. Pure pydantic
only — kernel types never appear here (CLAUDE.md service boundaries).

An assembly is a GRAPH — a set of instances + a set of mates — not an ordered
single-body feature history (design §1.1). Mates name part geometry with the
EXACT stage-1 signature machinery topological naming already ships
(:class:`~py_kit.schemas.features.PlanarFaceSignature` /
:class:`~py_kit.schemas.features.EdgeSignature`, reused VERBATIM — a mate is not
a parallel taxonomy, design §1.5). Units are fixed per field, never tagged per
value: lengths are millimetres, encoded in field names (``distance_mm``) exactly
as :mod:`py_kit.schemas.geometry` does.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from py_kit.schemas.features import EdgeSignature, PlanarFaceSignature
from py_kit.schemas.geometry import Vec3

#: Upper bound for a user-facing assembly name ("Gearbox", "Bracket Stack").
ASSEMBLY_NAME_MAX_LENGTH = 200

#: Upper bound for a per-instance name ("Bracket <1>", "Bolt <3>").
INSTANCE_NAME_MAX_LENGTH = 200

#: Non-empty (post-strip), bounded assembly name.
AssemblyName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=ASSEMBLY_NAME_MAX_LENGTH
    ),
]

#: Non-empty (post-strip), bounded instance name.
InstanceName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=INSTANCE_NAME_MAX_LENGTH
    ),
]

#: The document kinds an instance may reference (design §1.2): a part, or a
#: sub-assembly (rigid nesting, §1.4). ``sub-assembly`` is deliberately kept
#: distinct so the acyclicity walk (documents-side) knows which references to
#: recurse into.
RefDocumentKind = Literal["part", "assembly"]


# --- placement + orientation (§1.5) ---------------------------------------------


class Quat(BaseModel):
    """Unit quaternion — the solver's internal orientation representation (§2.3).

    Gimbal-free, minimal, and renormalises cleanly under iteration (design
    §2.3), so no lossy Euler/matrix conversion crosses the boundary. All four
    components are required — a partial quaternion is a request-validation 422,
    never a silently-defaulted rotation. Identity is ``(0, 0, 0, 1)``; the
    solver renormalises to the unit sphere, so an authored value need not be
    exactly unit-length.
    """

    x: float = Field(description="Vector part i-component (full precision)")
    y: float = Field(description="Vector part j-component (full precision)")
    z: float = Field(description="Vector part k-component (full precision)")
    w: float = Field(description="Scalar part (full precision); 1 for identity")


class Placement(BaseModel):
    """A rigid pose — translation + orientation — of an instance (design §2.3).

    ``position`` is the world-mm translation; ``orientation`` defaults to the
    identity quaternion so an authored instance with no rotation carries a
    minimal placement. On the wire everywhere (authored seed AND solved result,
    §4) so the solver never converts representation at the boundary.
    """

    position: Vec3 = Field(description="Translation, world mm")
    orientation: Quat = Field(
        default=Quat(x=0.0, y=0.0, z=0.0, w=1.0),
        description="Unit quaternion orientation; identity (0,0,0,1) by default",
    )


#: The identity placement — origin, unrotated. The default authored seed.
IDENTITY_PLACEMENT = Placement(position=Vec3(x=0.0, y=0.0, z=0.0))


# --- how a mate names part geometry (§2.1) --------------------------------------


class MateFaceRef(BaseModel):
    """A planar face of an instance's part body (design §1.5/§2.1).

    ``signature`` is the SAME :class:`~py_kit.schemas.features.PlanarFaceSignature`
    the ``on_face`` datum resolves (topological-naming.md §9) — reused verbatim,
    not a parallel taxonomy. ``instance_id`` scopes the face to one instance's
    resolved part body (the geometry service resolves the signature against that
    body in the part's local frame, §4).
    """

    kind: Literal["face"] = "face"
    instance_id: uuid.UUID = Field(
        description="The instance whose part body carries this face"
    )
    signature: PlanarFaceSignature = Field(
        description="Stage-1 planar-face signature (reused from features)"
    )


class MateAxisRef(BaseModel):
    """An axis derived from a CIRCULAR edge of an instance's part body (§2.1).

    v1 derives an axis from a circular edge (``curve == "circle"``) — reusing
    :class:`~py_kit.schemas.features.EdgeSignature`, whose seam-point centre and
    plane give the axis (design §2.1). This deliberately avoids needing a
    cylindrical-face signature (a clean additive future member): a hole rim and
    a shaft rim are both circular edges, enough for the canonical bolt joint.
    """

    kind: Literal["axis"] = "axis"
    instance_id: uuid.UUID = Field(
        description="The instance whose part body carries this axis edge"
    )
    signature: EdgeSignature = Field(
        description="Stage-1 edge signature (curve == 'circle'; reused from "
        "features) whose centre + plane define the axis"
    )


#: Discriminated mate-geometry reference: a planar face OR a circular-edge axis.
MateGeometryRef = Annotated[MateFaceRef | MateAxisRef, Field(discriminator="kind")]


# --- the v1 mate set (§2.1) -----------------------------------------------------
#
# The schema carries ALL FIVE mate kinds even though the v1 solver ships three
# (`lock`, `coincident`, `concentric` — design §2.1): `distance`/`angle` are the
# immediate fast-follow (§5, "the same solver, one extra scalar"), so they live
# in the discriminated union now and join the solver additively with no schema
# churn (the feature-tree.md §1.4 additive-union discipline). A mate names part
# geometry ONLY through the reused signature refs — no kernel type appears.


class CoincidentMate(BaseModel):
    """Two planar faces made coplanar + flush (design §2.1/§2.3).

    ``flush`` chooses the normal sense: ``True`` = normals anti-parallel (the
    mating faces touch, the common bolted-flush case); ``False`` = normals
    parallel (faces back-to-back). The residual is a coplanar gap of zero plus
    the (anti)parallel normal constraint (§2.3).
    """

    type: Literal["coincident"] = "coincident"
    a: MateFaceRef = Field(description="First planar face")
    b: MateFaceRef = Field(description="Second planar face")
    flush: bool = Field(
        default=True,
        description="True = normals anti-parallel (mating faces touch); False = "
        "normals parallel (back-to-back)",
    )


class ConcentricMate(BaseModel):
    """Two axes (from circular edges) made collinear (design §2.1/§2.3).

    The bolt/pin half of the canonical joint: hole and shaft axes aligned. The
    residual makes the two directions parallel and the two lines coincident
    (§2.3).
    """

    type: Literal["concentric"] = "concentric"
    a: MateAxisRef = Field(description="First axis")
    b: MateAxisRef = Field(description="Second axis")


class DistanceMate(BaseModel):
    """Two planar faces held a fixed distance apart (fast-follow, design §5).

    ``coincident`` with a non-zero offset in the residual (§2.3) — the same
    solver, one extra scalar. In the schema now so it joins the solver
    additively; not v1-solver scope.
    """

    type: Literal["distance"] = "distance"
    a: MateFaceRef = Field(description="First planar face")
    b: MateFaceRef = Field(description="Second planar face")
    distance_mm: float = Field(
        allow_inf_nan=False,
        description="Signed gap between the two faces along the normal (mm)",
    )


class AngleMate(BaseModel):
    """Two planar faces held at a fixed angle (fast-follow, design §5).

    The angular sibling of :class:`DistanceMate`: the coincident residual with
    the angle between the two normals targeted at ``angle_deg`` (§2.3). In the
    schema now; not v1-solver scope.
    """

    type: Literal["angle"] = "angle"
    a: MateFaceRef = Field(description="First planar face")
    b: MateFaceRef = Field(description="Second planar face")
    angle_deg: float = Field(
        allow_inf_nan=False,
        description="Target angle between the two face normals (degrees)",
    )


class LockMate(BaseModel):
    """Rigidly fix two instances' relative pose — 0 DOF (design §2.1/§2.3).

    Trivial for the solver (it fixes a relative pose, 0 iterative work) and
    covers weldments/press-fits. References two instances directly by id (no
    picked geometry) — the relative-pose residual drives ``b``'s pose to a fixed
    transform of ``a``'s (§2.3).
    """

    type: Literal["lock"] = "lock"
    a_instance_id: uuid.UUID = Field(description="First (anchor) instance")
    b_instance_id: uuid.UUID = Field(description="Second (locked) instance")


#: Discriminated v1 mate union (design §1.5). All five kinds are present; the v1
#: solver evaluates `lock`/`coincident`/`concentric`, with `distance`/`angle`
#: the immediate additive fast-follow (§5). A richer axis source / new mate kind
#: joins additively (the feature-tree.md §1.4 rule) with no version churn.
Mate = Annotated[
    CoincidentMate | ConcentricMate | DistanceMate | AngleMate | LockMate,
    Field(discriminator="type"),
]

#: Plain (non-annotated) union alias for type annotations of validated values.
MateParams = CoincidentMate | ConcentricMate | DistanceMate | AngleMate | LockMate


def mate_instance_ids(mate: MateParams) -> tuple[uuid.UUID, ...]:
    """The instance ids a mate constrains — for write-time membership checks.

    A :class:`LockMate` names two instances directly; every geometry-ref mate
    names them through its two :class:`MateGeometryRef` slots. Centralised here
    (beside the schema) so documents validates mate membership from one place
    and can never drift from a new mate kind's shape.
    """
    if isinstance(mate, LockMate):
        return (mate.a_instance_id, mate.b_instance_id)
    return (mate.a.instance_id, mate.b.instance_id)


# --- CRUD / response DTOs (documents API + gateway aggregation) ------------------
#
# Mirror the feature-CRUD DTOs (FeatureCreate/FeatureResponse, …) including the
# `expected_version` optimistic-concurrency guard (422 on stale — the
# feature-tree.md §1.2 pattern applied to an assembly's `doc_version`).


class AssemblyCreate(BaseModel):
    """Create an assembly owned by the calling user (design §1.2)."""

    name: AssemblyName = Field(
        description="Assembly name; unique per owner, whitespace-trimmed, "
        f"1-{ASSEMBLY_NAME_MAX_LENGTH} characters"
    )


class AssemblyUpdate(BaseModel):
    """Rename an assembly. Bumps ``doc_version`` (any mutation bumps — §1.2)."""

    expected_version: int = Field(
        ge=0,
        description="Optimistic-concurrency guard: the doc_version the client "
        "last saw; a stale value is rejected 422 (design §1.2)",
    )
    name: AssemblyName = Field(description="New assembly name")


class InstanceCreate(BaseModel):
    """Add an instance referencing a part/sub-assembly by id (design §1.2).

    ``ref_document_id`` is a cross-document reference, not an FK (design §1.2):
    documents enforces its integrity at write time (existence, acyclicity), not
    the DB. ``placement`` defaults to identity; ``grounded`` fixes the instance
    at its placement (0 DOF) — the solver's anchor (v1 wants at least one
    grounded instance per assembly, §1.2). ``order_index`` is a stable
    display/BOM order, appended at the tip when omitted.
    """

    expected_version: int = Field(
        ge=0, description="Optimistic-concurrency guard (design §1.2)"
    )
    ref_document_id: uuid.UUID = Field(
        description="The part / sub-assembly document this instance references"
    )
    ref_document_kind: RefDocumentKind = Field(
        description="'part' or 'assembly' (a rigid sub-assembly nests, §1.4)"
    )
    name: InstanceName = Field(description='Instance name ("Bracket <1>")')
    placement: Placement = Field(
        default=IDENTITY_PLACEMENT, description="Authored seed pose (§2.3)"
    )
    grounded: bool = Field(
        default=False,
        description="Fix this instance at its placement (0 DOF) — the solver "
        "anchor; v1 wants >= 1 grounded instance per assembly (§1.2)",
    )


class InstanceUpdate(BaseModel):
    """Re-place / rename / (un)ground an instance (design §1.2).

    Every field is optional; at least one must be provided. Any mutation bumps
    ``doc_version``. Re-pointing the referenced document is NOT an update — that
    is a delete + recreate (it changes the graph edge the acyclicity walk sees).
    """

    expected_version: int = Field(
        ge=0, description="Optimistic-concurrency guard (design §1.2)"
    )
    name: InstanceName | None = None
    placement: Placement | None = None
    grounded: bool | None = None
    order_index: int | None = Field(
        default=None,
        ge=0,
        description="New stable display/BOM position (reorder). Renumbered "
        "dense by the service.",
    )


class InstanceResponse(BaseModel):
    """An instance as stored (design §1.2)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assembly_id: uuid.UUID
    ref_document_id: uuid.UUID
    ref_document_kind: RefDocumentKind
    ref_pinned_version: int | None = Field(
        description="Pinned referenced-document version, or null = track tip. "
        "NULL in v1 (design §1.3 — the schema is pin-ready)."
    )
    name: str
    placement: Placement
    grounded: bool
    order_index: int = Field(
        description="Stable display/BOM order (NOT an evaluation order — an "
        "assembly is a graph, design §1.1)"
    )
    created_at: datetime
    updated_at: datetime


class MateCreate(BaseModel):
    """Add a mate to an assembly (design §1.2/§2.1).

    ``mate`` is the discriminated :data:`Mate` union; the instances it names
    (via :func:`mate_instance_ids`) must belong to this assembly (documents
    checks membership at write time). ``order_index`` is a stable order for
    determinism (§2.2), appended at the tip when omitted.
    """

    expected_version: int = Field(
        ge=0, description="Optimistic-concurrency guard (design §1.2)"
    )
    mate: Mate = Field(description="The mate (discriminated on `type`)")


class MateResponse(BaseModel):
    """A mate as stored, with its params envelope reassembled (design §1.2)."""

    id: uuid.UUID
    assembly_id: uuid.UUID
    order_index: int = Field(
        description="Stable order (determinism, §2.2); relative position only"
    )
    mate: Mate


class AssemblyResponse(BaseModel):
    """An assembly as stored — identity, ownership, and its concurrency token.

    Mirrors :class:`~py_kit.schemas.parts.PartResponse` plus the ``doc_version``
    OCC counter. The full instance/mate graph rides :class:`AssemblyGraphResponse`.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    owner_id: uuid.UUID = Field(description="Owning user id (gateway-verified)")
    doc_version: int = Field(
        description="Monotonic optimistic-concurrency counter (design §1.2)"
    )
    created_at: datetime
    updated_at: datetime


class AssemblyListResponse(BaseModel):
    """The caller's assemblies, oldest first (wrapper leaves room for paging)."""

    assemblies: list[AssemblyResponse]


class AssemblyGraphResponse(BaseModel):
    """An assembly plus its full instance + mate graph and concurrency token.

    The read model a client renders (design §1.2): the assembly header, its
    instances in ``order_index`` order, its mates in ``order_index`` order, and
    the ``doc_version`` the client echoes as its next ``expected_version``.
    """

    assembly: AssemblyResponse
    doc_version: int = Field(description="Echoed OCC token (== assembly.doc_version)")
    instances: list[InstanceResponse]
    mates: list[MateResponse]


class InstanceMutationResponse(BaseModel):
    """Result of a single-instance mutation: the instance + the new version."""

    instance: InstanceResponse
    doc_version: int


class MateMutationResponse(BaseModel):
    """Result of a single-mate mutation: the mate + the new version."""

    mate: MateResponse
    doc_version: int
