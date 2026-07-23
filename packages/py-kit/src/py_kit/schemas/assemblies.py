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

from py_kit.schemas.features import (
    EdgeSignature,
    EvaluatedFeatureInput,
    FeatureError,
    PlanarFaceSignature,
)
from py_kit.schemas.geometry import (
    DEFAULT_ANGULAR_DEFLECTION,
    DEFAULT_LINEAR_DEFLECTION,
    BoundingBox,
    ExportFormat,
    ShapeProperties,
    Vec3,
)
from py_kit.schemas.units import DEFAULT_LENGTH_UNIT, LengthUnit

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
    length_unit: LengthUnit = Field(
        default=DEFAULT_LENGTH_UNIT,
        description="Document display unit (docs/design/units.md §1); DISPLAY "
        "metadata only — storage stays canonical mm. Defaults to 'mm'.",
    )


class AssemblyUpdate(BaseModel):
    """Rename and/or re-unit an assembly. Bumps ``doc_version`` (any mutation
    bumps — §1.2).

    Both mutable fields are optional; at least one must be provided (mirroring
    :class:`InstanceUpdate`). Changing the display unit is a document edit
    (docs/design/units.md §U1) — metadata only, no stored ``*_mm`` value moves.
    """

    expected_version: int = Field(
        ge=0,
        description="Optimistic-concurrency guard: the doc_version the client "
        "last saw; a stale value is rejected 422 (design §1.2)",
    )
    name: AssemblyName | None = Field(default=None, description="New assembly name")
    length_unit: LengthUnit | None = Field(
        default=None, description="New document display unit (metadata only)"
    )


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
    length_unit: LengthUnit = Field(
        description="Document display unit (docs/design/units.md §1); DISPLAY "
        "metadata only — storage stays canonical mm."
    )
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
    can_undo: bool = Field(
        description="True when an earlier history snapshot exists to restore "
        "(docs/design/undo-redo.md UR3) — lets the toolbar disable undo "
        "without a second call (the part tree's can_undo, applied here)"
    )
    can_redo: bool = Field(
        description="True when a later history snapshot exists to restore "
        "(the history cursor is below the ring's top)"
    )


class AssemblyUndoRedoRequest(BaseModel):
    """Restore the adjacent assembly history snapshot (undo-redo.md UR3).

    The assembly sibling of the part's
    :class:`~py_kit.schemas.features.UndoRedoRequest`: undo/redo ARE document
    edits — each bumps ``doc_version`` under the same optimistic-concurrency
    guard as every other assembly write (stale → 422,
    ``stale_assembly_version``), and the response is the restored graph
    (instance/mate ids preserved VERBATIM — the load-bearing snapshot
    decision). At a boundary — undo at the ring's floor, redo at its top —
    the op is a CLEAN no-op, not an error: 200 with the current graph,
    version unchanged. ``can_undo``/``can_redo`` on
    :class:`AssemblyGraphResponse` let the UI disable the controls, so a
    click racing that state is harmless.
    """

    expected_version: int = Field(
        ge=0, description="Optimistic-concurrency guard (design §1.2)"
    )


class BomLine(BaseModel):
    """One line of an assembly's bill of materials (a flat, direct-instance BOM).

    A BOM line GROUPS the assembly's DIRECT instances by the document they
    reference: ``quantity`` is the count of instances sharing this
    ``ref_document_id``, ``name`` is the referenced document's CURRENT name, and
    ``ref_document_kind`` is ``part`` or ``assembly``. This is the FLAT v1 —
    direct instances only, NOT recursive into rigid sub-assemblies (an explicit
    follow-up; a sub-assembly instance appears as a single ``kind: "assembly"``
    line, never expanded).

    A referenced document that was DELETED while still instanced surfaces
    honestly, not silently: the line stays (its instances still exist and still
    count), with ``name`` null and ``missing`` true, so a client can flag the
    dangling reference rather than the read 500-ing or the quantity vanishing.
    """

    ref_document_id: uuid.UUID = Field(
        description="The referenced part / sub-assembly document (the group key)"
    )
    ref_document_kind: RefDocumentKind = Field(
        description="'part' or 'assembly' (a rigid sub-assembly, not expanded)"
    )
    name: str | None = Field(
        description="The referenced document's CURRENT name, or null when it has "
        "been deleted while still instanced (see `missing`)"
    )
    missing: bool = Field(
        default=False,
        description="True when the referenced document no longer exists (deleted "
        "while still instanced) — the line and its quantity are still reported so "
        "the dangling reference is visible, never silently dropped",
    )
    quantity: int = Field(
        ge=1, description="Count of direct instances referencing this document"
    )


class AssemblyBomResponse(BaseModel):
    """An assembly's flat bill of materials (design: assemblies.md residual).

    A pure documents-side READ MODEL — no writes, no migration: it aggregates
    the assembly's DIRECT instances into one :class:`BomLine` per referenced
    document (quantity = shared-reference count), resolving each document's
    current name from the ``parts`` / ``assemblies`` tables. Deterministically
    ordered (resolved name, then ``ref_document_id``) so the list is stable
    across reads. ``total_instances`` is the sum of every line's quantity (the
    assembly's direct-instance count), so an empty assembly is
    ``{lines: [], total_instances: 0}``.
    """

    assembly_id: uuid.UUID
    lines: list[BomLine] = Field(
        description="One line per referenced document, deterministically ordered"
    )
    total_instances: int = Field(
        ge=0, description="Sum of all line quantities (direct instance count)"
    )


class InstanceMutationResponse(BaseModel):
    """Result of a single-instance mutation: the instance + the new version."""

    instance: InstanceResponse
    doc_version: int


class MateMutationResponse(BaseModel):
    """Result of a single-mate mutation: the mate + the new version."""

    mate: MateResponse
    doc_version: int


# --- solve status + diagnosis (§2.4) --------------------------------------------
#
# THE boundary source of truth for the solve outcome (CLAUDE.md DRY rule): the
# geometry service's ``AssemblySolver`` (``geometry.assembly.protocol``) imports
# these back rather than defining a parallel copy, so the solver's status and the
# evaluation result's status are the SAME type. They mirror the sketch solver's
# ``SketchOverconstraintClass`` / ``SketchConstraintDiagnosis`` vocabulary so the
# UI and tests share one mental model across the 2D and 3D solvers (design §2.4).

#: Solve outcome, mirroring the sketch solver's status vocabulary (design §2.4).
#: Only ``conflicting`` / ``not_converged`` are fatal (a per-mate error at the
#: evaluation layer); ``under_constrained`` and ``over_constrained`` still return
#: a valid best-fit placement (an ungrounded assembly is a non-fatal
#: ``under_constrained`` by its 6 free rigid-body DOF, design §1.2).
AssemblySolveStatus = Literal[
    "well_constrained",
    "under_constrained",
    "over_constrained",
    "conflicting",
    "not_converged",
]

#: Over-constraint kind, mirroring ``SketchOverconstraintClass`` (design §2.4).
AssemblyOverconstraintClass = Literal["redundant", "conflicting"]


class AssemblySolveDiagnosis(BaseModel):
    """Structured diagnosis, mirroring ``SketchConstraintDiagnosis`` (design §2.4).

    Read by field, never a parsed message. ``remaining_dof`` is first-class for
    the under-constrained case; ``conflicting_mates`` / ``redundant_mates`` name
    offending mates by id for the over/conflict cases.
    """

    classification: AssemblyOverconstraintClass | None = Field(
        default=None,
        description="'redundant' (removable, still solves) or 'conflicting' "
        "(contradictory); None for a purely under-constrained diagnosis.",
    )
    remaining_dof: int = Field(
        default=0,
        ge=0,
        description="Degrees of freedom left free at the seed (0 = fully located).",
    )
    removable: bool = Field(
        default=False,
        description="True when the assembly still solves after removing the named "
        "redundant mates (the redundant case); False for a genuine conflict.",
    )
    conflicting_mates: list[uuid.UUID] = Field(
        default_factory=list["uuid.UUID"],
        description="Ids of mutually-unsatisfiable mates (conflicting case).",
    )
    redundant_mates: list[uuid.UUID] = Field(
        default_factory=list["uuid.UUID"],
        description="Ids of consistent-but-superfluous, removable mates.",
    )
    message: str = Field(description="Human-readable diagnosis.")
    suggested_fix: str | None = Field(
        default=None, description="Actionable hint, e.g. 'Remove mate <id>'."
    )


# --- §4 evaluation contract (documents → geometry → gateway → web) --------------
#
# Mirrors ``EvaluateTreeRequest`` / ``EvaluateTreeResult`` (feature-tree.md §4):
# one transport-agnostic request/response pair, pure pydantic (no kernel type
# crosses the boundary — CLAUDE.md). documents sends INTENT (each part's feature
# list + the mate graph), geometry is the sole evaluator, and the response is
# per-instance {content-addressed mesh + solved transform} + an analytic
# combined-property roll-up. The SOLVED transform is applied at RENDER time (a
# per-instance transform over a SHARED part mesh), never baked into the GLB
# (design §4) — two instances of one part share a single content-addressed mesh.


class EvaluatedMate(BaseModel):
    """One mate plus the persisted-row identity the solver + diagnosis need.

    ``mate_id`` names the mate in the diagnosis (offending / redundant sets) and
    in a per-mate resolution error; ``order_index`` fixes the deterministic
    processing order (design §2.2). ``mate`` is the discriminated
    :data:`Mate` union member. Mirrors :class:`MateResponse` minus the
    assembly id (the request already scopes one assembly).
    """

    mate_id: uuid.UUID = Field(description="Persisted mate id (names it in diagnosis)")
    order_index: int = Field(
        ge=0, description="Deterministic processing order (design §2.2)"
    )
    mate: Mate = Field(description="The mate (discriminated on `type`)")


class EvaluatedInstance(BaseModel):
    """One assembly instance as the evaluator sees it (design §4).

    ``part_key`` is the DEDUP key — ``f"{ref_document_id}@{version-or-tip}"`` —
    so two instances of the SAME part evaluate once and share one
    content-addressed mesh (the central perf win, design §4 step 1). ``features``
    is the part's ordered feature prefix (reuses the feature-tree §4 contract
    VERBATIM), so geometry stays the sole evaluator and documents sends intent,
    never a kernel body. ``placement`` is the authored seed pose the solver
    starts from; ``grounded`` fixes it at that pose (0 DOF — the solver anchor).
    """

    instance_id: uuid.UUID = Field(description="Instance identity (result keying)")
    part_key: str = Field(
        description="Dedup key f'{ref_document_id}@{version-or-tip}': instances "
        "sharing it evaluate once and share one content-addressed mesh (§4)"
    )
    features: list[EvaluatedFeatureInput] = Field(
        description="The part's ordered feature prefix (feature-tree §4 contract)"
    )
    placement: Placement = Field(
        default=IDENTITY_PLACEMENT, description="Authored seed pose (§2.3)"
    )
    grounded: bool = Field(
        default=False,
        description="Fix this instance at its placement (0 DOF) — the solver "
        "anchor; an assembly with none grounded floats (under_constrained, §1.2)",
    )


class EvaluateAssemblyRequest(BaseModel):
    """Evaluate an assembly graph to solved placements + shared meshes (§4).

    Documents flattens rigid sub-assemblies into this recursive structure
    before sending (or geometry recurses — the rigid-group result is identical,
    §1.4/§4). Deterministic (RESEARCH §9): the same request yields an identical
    result — bitwise-stable mesh ids AND solved transforms — in-process and
    across an interpreter restart.
    """

    assembly_id: uuid.UUID
    version: int = Field(description="Echoed back; cache/correlation key")
    instances: list[EvaluatedInstance] = Field(
        description="The assembly's instances (result order preserved)"
    )
    mates: list[EvaluatedMate] = Field(
        default_factory=list["EvaluatedMate"],
        description="The mate graph; processed in order_index order (determinism)",
    )
    linear_deflection: float = Field(
        default=DEFAULT_LINEAR_DEFLECTION,
        gt=0,
        description="Presentation tessellation parameter (mm), never persisted",
    )


class InstancePlacementResult(BaseModel):
    """One instance's evaluation output: its shared mesh + solved pose (§4).

    ``part_mesh_glb_id`` is a content address SHARED across every instance of a
    part (the dedup contract, §4/§6.4) — ``None`` only when the instance's part
    produced no body (``error`` then explains why). ``placement`` is the SOLVED
    world pose (the authored seed for a failed / un-solved instance).
    ``properties`` are the part's OWN mass properties (for BOM / inspection).
    ``error`` is a typed per-instance failure inside a 200 (design §4, mirroring
    feature-tree §4.3) — e.g. the part's failing feature error — never a 4xx.
    """

    instance_id: uuid.UUID
    part_mesh_glb_id: str | None = Field(
        description="Content-addressed shared part mesh (sha256:<hex>), or null "
        "when the part produced no body"
    )
    placement: Placement = Field(description="SOLVED world pose (seed if unsolved)")
    properties: ShapeProperties | None = Field(
        default=None, description="The part's own mass properties (BOM/inspection)"
    )
    error: FeatureError | None = Field(
        default=None,
        description="Typed per-instance failure inside a 200 (the part's failing "
        "feature error / no_body), never a transport 4xx (design §4)",
    )


class MateEvaluationError(BaseModel):
    """A per-mate resolution failure inside a 200 (design §4).

    A mate whose geometry could not be resolved against the evaluated bodies —
    ``subshape_unresolved`` / ``subshape_ambiguous`` (from the reused stage-1
    resolver, #3's chained error) or a reference to an unavailable instance — is
    reported here and DROPPED from the solve (the assembly still renders every
    instance it can place, degrading to under-constrained rather than failing
    the whole evaluation, design §4). A CONFLICTING (unsatisfiable) mate is not
    here — it is named in :attr:`AssemblySolveDiagnosis.conflicting_mates`.
    """

    mate_id: uuid.UUID
    error: FeatureError = Field(description="Typed per-mate failure (code + message)")


class EvaluateAssemblyResult(BaseModel):
    """Per-instance shared-mesh + solved transform, plus the analytic roll-up (§4).

    The output is per-instance ``{content-addressed mesh, solved transform}``,
    NOT a baked combined GLB (design §4): the viewport instances the shared part
    meshes with the solved transforms (r3f instancing). ``properties`` /
    ``bounding_box`` are a closed-form roll-up over instances (Σ volumes,
    mass-weighted centroid, transformed-bbox union — no re-meshing, no boolean),
    ``None`` when no instance produced a body. A feature/mate failure is a 200
    with typed per-entry errors; the envelope stays reserved for
    transport/validation failures (design §4).
    """

    assembly_id: uuid.UUID
    version: int
    instances: list[InstancePlacementResult] = Field(
        description="Same order as the request instances"
    )
    status: AssemblySolveStatus = Field(description="Assembly-level solve outcome")
    diagnosis: AssemblySolveDiagnosis | None = Field(
        default=None,
        description="Remaining DOF + offending mate ids; None for a clean "
        "well_constrained solve (design §2.4)",
    )
    mate_errors: list[MateEvaluationError] = Field(
        default_factory=list["MateEvaluationError"],
        description="Per-mate resolution failures (dropped from the solve, §4)",
    )
    properties: ShapeProperties | None = Field(
        default=None, description="Combined assembly mass properties (roll-up, §4)"
    )
    bounding_box: BoundingBox | None = Field(
        default=None, description="Combined assembly AABB (transformed-bbox union)"
    )


# --- assembly export contract (documents → geometry → gateway → web) ------------
#
# The interop sibling of the part-level ``ExportRequest`` (schemas.geometry): the
# SAME evaluate-assembly graph, exported to ONE multi-instance CAD file instead of
# per-instance meshes. Reuses ``EvaluateAssemblyRequest`` VERBATIM (the solver runs
# the identical pipeline) and only adds the export ``format`` + the STL faceting
# knob, so a request that evaluates can always be exported (the ShapeRequest →
# ExportRequest discipline, applied to assemblies). STEP writes AP214 product
# structure — each instance is a named PRODUCT at its SOLVED world placement
# (RESEARCH §10/§11); STL bakes the placements into one faceted compound.


class ExportAssemblyRequest(EvaluateAssemblyRequest):
    """Evaluate an assembly graph and export it as one multi-instance CAD file.

    Extends :class:`EvaluateAssemblyRequest` (the solver runs the identical
    evaluate pipeline — same solved world placements), adding only the export
    ``format`` and the STL faceting parameter. STEP exports the exact B-rep as
    **AP214 product structure**: every instance that produced a body becomes a
    named PRODUCT positioned at its SOLVED world placement, so a downstream tool
    (or a re-import) recovers each part traceable to its instance. STL bakes the
    solved placements into a single faceted compound (no product names — the
    format carries none). Byte-deterministic for identical requests (RESEARCH
    §9): the STEP creation timestamp is pinned kernel-side and the assembly's
    per-occurrence ids are canonicalised, so the same graph in yields identical
    bytes out, in-process and across an interpreter restart.
    """

    format: ExportFormat = Field(
        description="Export file format: STEP (exact B-rep, AP214 product "
        "structure) or STL (faceted mesh, placements baked into one compound)"
    )
    angular_deflection: float = Field(
        default=DEFAULT_ANGULAR_DEFLECTION,
        gt=0,
        description="STL facet angular deflection (rad) between adjacent "
        "segments; ignored for STEP (exact B-rep)",
    )


def assembly_export_filename(request: ExportAssemblyRequest) -> str:
    """Deterministic download filename for an assembly export (Content-Disposition)."""
    return f"assembly.{request.format}"
