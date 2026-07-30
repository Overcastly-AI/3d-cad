"""Assembly evaluation — the end-to-end §4 pipeline (design ``assemblies.md`` §4).

The v1 DoD: turn an assembly (instances referencing parts + a mate graph) into
solved per-instance world transforms + SHARED content-addressed meshes for the
viewport — "bolt two parts together and see it." Mirrors
:func:`geometry.features.evaluate_tree` in shape and idioms; a stateless pure
function of the request (RESEARCH §9 — same request in, bitwise-identical result
out, in-process AND across an interpreter restart).

Pipeline (design §4):

1. **Evaluate each UNIQUE part once**, keyed by ``part_key`` — reusing the
   existing :func:`~geometry.features.evaluate_tree` dispatch (NOT reimplemented)
   → a kernel body + a content-addressed part mesh (:mod:`geometry.mesh_store`,
   reused) + the part's :class:`ShapeProperties`. Two instances of the same part
   share one evaluation and one cached mesh — the central perf win (§4 step 1,
   the §6.4 dedup contract).
2. **Resolve every mate** against the instances' evaluated bodies via #3's
   :func:`~geometry.assembly.resolve.build_assembly_solve_input`, one mate at a
   time so an unresolvable mate becomes a per-mate error and is DROPPED from the
   solve rather than failing the whole evaluation (§4 error posture).
3. **Solve** (the shipped :class:`~geometry.assembly.solver.RigidBodyAssemblySolver`)
   → a solved world :class:`Placement` per instance (grounded held fixed).
4. **Compose mass properties analytically** — Σ volumes, VOLUME-weighted
   centroid, plus (when every part has a material) Σ masses and a genuinely
   MASS-weighted centre of mass, transformed-bbox union, summed topology — NO
   re-meshing, NO boolean (§4 step 4). The solved transform is applied at RENDER
   time (per-instance transform over the shared mesh), never baked into the GLB
   (§4). NB the pre-materials code called its volume-weighted centroid
   "mass-weighted", which was only true when every body shared one density
   (docs/design/materials.md §3).

Error posture (design §4, mirroring feature-tree §4.3): a dangling / bodyless
part, an unresolvable mate (``subshape_unresolved`` / ``subshape_ambiguous`` from
#3's chained error), a self-mate (``mate_self_reference`` — both slots naming the
same instance, dropped per-mate), an ungrounded assembly, or a conflicting solve
is a **200 with a typed per-entry error / status**, never a 500 or a hang. Even a
malformed request the per-mate guards miss (a duplicate instance id, or any
residual :class:`AssemblyDefinitionError` from the pre-solve build or the solver)
maps to a clean assembly-level status — :func:`evaluate_assembly` is **total**,
it never raises for an evaluation outcome. Under-constrained
(including a fully ungrounded assembly, free by its 6 rigid-body DOF) is
NON-fatal: a valid seed-consistent placement with the remaining DOF reported.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import numpy as np
from py_kit.schemas.assemblies import (
    AssemblySolveDiagnosis,
    AssemblySolveStatus,
    EvaluateAssemblyRequest,
    EvaluateAssemblyResult,
    InstancePlacementResult,
    MateEvaluationError,
    Placement,
    mate_instance_ids,
)
from py_kit.schemas.features import (
    EvaluateTreeRequest,
    EvaluateTreeResult,
    FeatureError,
)
from py_kit.schemas.geometry import (
    BoundingBox,
    ShapeProperties,
    TopologyCounts,
    Vec3,
)

from geometry.assembly.protocol import (
    AssemblyDefinitionError,
    AssemblySolveInput,
    SolverMate,
)
from geometry.assembly.resolve import (
    ResolvableInstance,
    ResolvableMate,
    build_assembly_solve_input,
)
from geometry.assembly.solver import RigidBodyAssemblySolver
from geometry.assembly.transform import Pose, as_vector
from geometry.features import evaluate_tree
from geometry.kernel.faces import SubshapeAmbiguousError, SubshapeUnresolvedError
from geometry.kernel.types import BodyShape

#: The solver backend, typed as the protocol implementation. ``solve`` is
#: stateless (a fresh system + a scoped BLAS pin per call), so one shared
#: instance is safe — the same posture as the sketch solver in ``evaluate_tree``.
_SOLVER = RigidBodyAssemblySolver()

#: Namespace for the deterministic per-part id handed to ``evaluate_tree``. The
#: part id only echoes back in ``EvaluateTreeResult`` — it never affects the mesh
#: or properties (those are a pure function of features + deflection) — so a
#: stable ``uuid5(part_key)`` keeps the whole pipeline deterministic without
#: needing the real document id (which the ``part_key`` already encodes, §4).
_PART_NS = uuid.UUID("6f6c6674-0000-0000-0000-617373656d62")  # "loft…assemb"


@dataclass(frozen=True)
class _PartResult:
    """One unique part's evaluated artifacts (cached by ``part_key``, §4 step 1).

    ``body`` is the kernel solid (service-internal, never serialized). ``error``
    is set only when the part produced no body — the failing feature error or an
    honest ``no_body`` — so every instance of that part reports the same reason.
    """

    body: BodyShape | None
    mesh_glb_id: str | None
    properties: ShapeProperties | None
    error: FeatureError | None


def _part_no_body_error(result: EvaluateTreeResult) -> FeatureError:
    """The per-instance error for a part that evaluated to no body (§4).

    Surfaces the strict-prefix failing feature's own error when present (e.g.
    ``profile_not_closed``), else the honest ``no_body`` — a sketch-only /
    empty tree, or a dangling reference documents forwarded with no features.
    """
    failed = next(
        (f for f in result.features if f.status == "error" and f.error is not None),
        None,
    )
    if failed is not None and failed.error is not None:
        return failed.error
    return FeatureError(
        code="no_body",
        message=(
            "The instance's part evaluated to no body (no body-affecting "
            "feature); there is nothing to place."
        ),
    )


def _mate_resolution_error(exc: AssemblyDefinitionError) -> FeatureError:
    """Map a mate-resolution :class:`AssemblyDefinitionError` to a typed code (§4).

    #3 chains the originating subshape error (``__cause__``) so the specific
    ``subshape_unresolved`` / ``subshape_ambiguous`` code is recoverable here;
    anything else (an unknown-instance reference) is a generic ``mate_unresolved``.
    """
    cause = exc.__cause__
    if isinstance(cause, SubshapeAmbiguousError):
        code = "subshape_ambiguous"
    elif isinstance(cause, SubshapeUnresolvedError):
        code = "subshape_unresolved"
    else:
        code = "mate_unresolved"
    return FeatureError(code=code, message=str(exc))


def _mate_self_reference_error(
    mate_id: uuid.UUID, instance_id: uuid.UUID
) -> MateEvaluationError:
    """A per-mate error for a mate that constrains an instance to itself (§4).

    Both slots (or a lock mate's two instance ids) name the SAME instance — the
    solver's :func:`compile_mate` would reject this as malformed input; caught
    here first so it is DROPPED like any other bad mate (a typed per-mate error)
    and the rest of the assembly still solves, never a 500.
    """
    return MateEvaluationError(
        mate_id=mate_id,
        error=FeatureError(
            code="mate_self_reference",
            message=(
                f"mate {mate_id} constrains instance {instance_id} to itself; a "
                "mate must relate two distinct instances"
            ),
        ),
    )


def _evaluate_unique_parts(request: EvaluateAssemblyRequest) -> dict[str, _PartResult]:
    """Evaluate each UNIQUE part exactly once, keyed by ``part_key`` (§4 step 1).

    Reuses :func:`~geometry.features.evaluate_tree` verbatim (which tessellates +
    ``store_mesh_glb``s the body), so two instances of one part share a single
    evaluation and a single content-addressed mesh (the §6.4 dedup contract).
    """
    cache: dict[str, _PartResult] = {}
    for inst in request.instances:
        if inst.part_key in cache:
            continue
        tree_request = EvaluateTreeRequest(
            part_id=uuid.uuid5(_PART_NS, inst.part_key),
            tree_version=request.version,
            features=inst.features,
            linear_deflection=request.linear_deflection,
            # The instanced part's material assignment rides into ITS evaluation
            # (materials.md §3) so each part's mass is derived from its own
            # volume by the one kernel path. Cached per ``part_key`` with the
            # rest of the evaluation: a part_key names one part at one version,
            # so every instance of it shares one assignment by construction.
            materials=inst.materials,
        )
        evaluation = evaluate_tree(tree_request)
        error = (
            None
            if evaluation.body is not None
            else _part_no_body_error(evaluation.result)
        )
        cache[inst.part_key] = _PartResult(
            body=evaluation.body,
            mesh_glb_id=evaluation.result.mesh_glb_id,
            properties=evaluation.result.properties,
            error=error,
        )
    return cache


def _resolve_mates(
    evaluable: list[ResolvableInstance], request: EvaluateAssemblyRequest
) -> tuple[AssemblySolveInput, list[MateEvaluationError]]:
    """Build the solve input, resolving each mate individually (§4 step 2).

    Reuses #3's :func:`build_assembly_solve_input` per mate so an unresolvable
    mate (stale/ambiguous signature, or a reference to an unavailable instance)
    is reported as a per-mate error and DROPPED — the assembly still solves the
    mates it can, degrading to under-constrained rather than failing whole (§4).
    The kept mates are re-sorted deterministically by the solver.
    """
    solve_instances = build_assembly_solve_input(evaluable, []).instances
    solver_mates: list[SolverMate] = []
    mate_errors: list[MateEvaluationError] = []
    for evaluated in request.mates:
        ids = mate_instance_ids(evaluated.mate)
        if len(set(ids)) < len(ids):
            # A self-mate resolves against the one body (so it would pass the
            # per-mate resolve guard) but the solver rejects it — drop it here as
            # a typed per-mate error instead of letting it raise (§4).
            mate_errors.append(_mate_self_reference_error(evaluated.mate_id, ids[0]))
            continue
        resolvable = ResolvableMate(
            mate_id=evaluated.mate_id,
            order_index=evaluated.order_index,
            mate=evaluated.mate,
        )
        try:
            built = build_assembly_solve_input(evaluable, [resolvable])
        except AssemblyDefinitionError as exc:
            mate_errors.append(
                MateEvaluationError(
                    mate_id=evaluated.mate_id, error=_mate_resolution_error(exc)
                )
            )
            continue
        solver_mates.extend(built.mates)
    return (
        AssemblySolveInput(instances=solve_instances, mates=solver_mates),
        mate_errors,
    )


def _bbox_corners(box: BoundingBox) -> list[np.ndarray]:
    """The eight corners of an axis-aligned box (for a transformed-bbox union)."""
    return [
        np.array([x, y, z], dtype=np.float64)
        for x in (box.min.x, box.max.x)
        for y in (box.min.y, box.max.y)
        for z in (box.min.z, box.max.z)
    ]


def _combine_properties(
    items: list[tuple[ShapeProperties, Placement]],
) -> ShapeProperties | None:
    """Analytic combined mass-property roll-up over placed instances (§4 step 4).

    Total volume = Σ part volumes; combined ``centroid`` = VOLUME-weighted Σ of
    each part's centroid transformed by its SOLVED placement; combined AABB =
    union of the eight transformed corners of each part's local AABB (exact for
    translation / axis-aligned poses, a tight over-approximation under an
    off-axis rotation); surface area + topology counts are summed. NO re-meshing,
    NO boolean (design §4). Deterministic: a fixed instance-order reduction of
    float64 ops.

    Mass composes the same analytic way (docs/design/materials.md §3): total
    ``mass_g`` = Σ per-part masses and ``center_of_mass`` is weighted by MASS —
    genuinely, which the pre-materials code only *called* it. That distinction is
    the point of the field: an assembly of a steel pin and an aluminium housing
    does not balance where its volume does, and the two coincide only in the
    degenerate case where every part shares one density. Both mass fields are
    ``None`` unless EVERY placed instance has a material: a partial sum would
    silently under-report the assembly's mass.
    """
    if not items:
        return None
    total_volume = 0.0
    total_area = 0.0
    weighted_centroid = np.zeros(3, dtype=np.float64)
    total_mass: float | None = 0.0
    mass_weighted_centre = np.zeros(3, dtype=np.float64)
    faces = edges = shells = 0
    mins = np.full(3, np.inf, dtype=np.float64)
    maxs = np.full(3, -np.inf, dtype=np.float64)
    for props, placement in items:
        pose = Pose.from_placement(placement)
        total_volume += props.volume
        total_area += props.surface_area
        weighted_centroid += props.volume * pose.apply_point(as_vector(props.centroid))
        if props.mass_g is None or props.center_of_mass is None:
            total_mass = None
        elif total_mass is not None:
            total_mass += props.mass_g
            mass_weighted_centre += props.mass_g * pose.apply_point(
                as_vector(props.center_of_mass)
            )
        faces += props.topology.faces
        edges += props.topology.edges
        shells += props.topology.shells
        for corner in _bbox_corners(props.bounding_box):
            world = pose.apply_point(corner)
            mins = np.minimum(mins, world)
            maxs = np.maximum(maxs, world)
    centroid = (
        weighted_centroid / total_volume if total_volume != 0.0 else weighted_centroid
    )
    center_of_mass: Vec3 | None = None
    if total_mass is not None:
        # Zero total mass implies zero total volume (densities are > 0), where a
        # mass-weighted average is undefined — fall back to the volume centroid
        # rather than dividing by zero.
        centre = mass_weighted_centre / total_mass if total_mass != 0.0 else centroid
        center_of_mass = Vec3(
            x=float(centre[0]), y=float(centre[1]), z=float(centre[2])
        )
    return ShapeProperties(
        volume=total_volume,
        surface_area=total_area,
        centroid=Vec3(x=float(centroid[0]), y=float(centroid[1]), z=float(centroid[2])),
        mass_g=total_mass,
        center_of_mass=center_of_mass,
        bounding_box=BoundingBox(
            min=Vec3(x=float(mins[0]), y=float(mins[1]), z=float(mins[2])),
            max=Vec3(x=float(maxs[0]), y=float(maxs[1]), z=float(maxs[2])),
        ),
        topology=TopologyCounts(faces=faces, edges=edges, shells=shells),
    )


@dataclass(frozen=True)
class PlacedInstance:
    """One instance's resolved KERNEL body at its solved world placement (§4).

    Service-internal (``body`` is a kernel solid, never serialised). Produced
    only for instances that evaluated to a body; the export path applies
    ``placement`` to ``body`` to compose the assembly file. ``name`` is the
    instance's human-readable name (``None`` when the request carried none) — the
    export threads it into the STEP PRODUCT name for round-trip identity (FINDINGS
    #7), falling back to the instance id when absent.
    """

    instance_id: uuid.UUID
    part_key: str
    body: BodyShape
    placement: Placement
    name: str | None


@dataclass(frozen=True)
class SolvedAssembly:
    """The service-internal solve outcome — solved placements + KERNEL bodies.

    The shared core of :func:`evaluate_assembly` (which serialises it to the
    boundary DTO) and :func:`geometry.assembly.export.export_assembly` (which
    composes the bodies into one multi-instance CAD file). ``parts`` /
    ``placed`` hold kernel :class:`~geometry.kernel.types.BodyShape` solids, so
    this type is NEVER serialised or crossed over a service boundary (CLAUDE.md).

    ``placed`` is the export-ready view: one entry per instance that produced a
    body, in request-instance order, each carrying its resolved part body and
    its SOLVED world placement (the authored seed for an un-solved instance).
    """

    parts: dict[str, _PartResult]
    solved: dict[uuid.UUID, Placement]
    instance_errors: dict[uuid.UUID, FeatureError]
    placed: list[PlacedInstance]
    status: AssemblySolveStatus
    diagnosis: AssemblySolveDiagnosis | None
    mate_errors: list[MateEvaluationError]


def solve_assembly(request: EvaluateAssemblyRequest) -> SolvedAssembly:
    """Evaluate + solve an assembly to placements + KERNEL bodies (design §4).

    The shared pipeline behind :func:`evaluate_assembly` and the assembly
    export: evaluate each unique part once (§4 step 1), resolve every mate
    individually (§4 step 2), solve the mate graph (§4 step 3), and pair each
    instance's resolved body with its solved world placement. Total — never
    raises for an evaluation outcome (a bad part/mate/solve is a typed per-entry
    error or a non-``well_constrained`` status, the never-500 contract, §4).
    Deterministic (RESEARCH §9): the BLAS-pinned solver + fixed instance order.
    """
    parts = _evaluate_unique_parts(request)

    evaluable: list[ResolvableInstance] = []
    instance_errors: dict[uuid.UUID, FeatureError] = {}
    for inst in request.instances:
        part = parts[inst.part_key]
        if part.body is None:
            assert part.error is not None
            instance_errors[inst.instance_id] = part.error
        else:
            evaluable.append(
                ResolvableInstance(
                    instance_id=inst.instance_id,
                    body=part.body,
                    placement=inst.placement,
                    grounded=inst.grounded,
                )
            )

    status: AssemblySolveStatus = "under_constrained"
    diagnosis: AssemblySolveDiagnosis | None = None
    mate_errors: list[MateEvaluationError] = []
    solved: dict[uuid.UUID, Placement] = {}

    if evaluable:
        try:
            # Belt-and-braces: the per-mate resolve loop and the self-mate guard
            # already convert bad mates into typed per-mate errors, but the
            # pre-solve instance build (a duplicate instance id) and the solver
            # itself may still raise AssemblyDefinitionError. Map ANY residual to
            # a clean assembly-level status — solve_assembly never raises for an
            # evaluation outcome (§4, the never-500 contract).
            problem, mate_errors = _resolve_mates(evaluable, request)
            result = _SOLVER.solve(problem)
        except AssemblyDefinitionError as exc:
            status = "not_converged"
            diagnosis = AssemblySolveDiagnosis(
                remaining_dof=0,
                message=f"Assembly could not be evaluated: {exc}",
            )
        else:
            status = result.status
            diagnosis = result.diagnosis
            solved = {p.instance_id: p.placement for p in result.placements}
    else:
        diagnosis = AssemblySolveDiagnosis(
            remaining_dof=0,
            message="No instance produced a body to place; nothing to solve.",
        )

    placed: list[PlacedInstance] = []
    for inst in request.instances:
        part = parts[inst.part_key]
        if part.body is None:
            continue
        placed.append(
            PlacedInstance(
                instance_id=inst.instance_id,
                part_key=inst.part_key,
                body=part.body,
                placement=solved.get(inst.instance_id, inst.placement),
                name=inst.name,
            )
        )

    return SolvedAssembly(
        parts=parts,
        solved=solved,
        instance_errors=instance_errors,
        placed=placed,
        status=status,
        diagnosis=diagnosis,
        mate_errors=mate_errors,
    )


def evaluate_assembly(request: EvaluateAssemblyRequest) -> EvaluateAssemblyResult:
    """Evaluate an assembly to solved placements + shared meshes (design §4).

    Deterministic (RESEARCH §9): the same request yields an identical result —
    bitwise-stable ``part_mesh_glb_id``s (content hashes of deterministic GLBs)
    and solved transforms (the BLAS-pinned solver). Never raises for an
    evaluation outcome — a bad part/mate/solve is a typed per-entry error or a
    non-``well_constrained`` status inside the result envelope.
    """
    solved_assembly = solve_assembly(request)
    parts = solved_assembly.parts
    solved = solved_assembly.solved
    instance_errors = solved_assembly.instance_errors
    status = solved_assembly.status
    diagnosis = solved_assembly.diagnosis
    mate_errors = solved_assembly.mate_errors

    instances_out: list[InstancePlacementResult] = []
    roll_up: list[tuple[ShapeProperties, Placement]] = []
    for inst in request.instances:
        error = instance_errors.get(inst.instance_id)
        if error is not None:
            instances_out.append(
                InstancePlacementResult(
                    instance_id=inst.instance_id,
                    part_mesh_glb_id=None,
                    placement=inst.placement,
                    properties=None,
                    error=error,
                )
            )
            continue
        part = parts[inst.part_key]
        placement = solved.get(inst.instance_id, inst.placement)
        instances_out.append(
            InstancePlacementResult(
                instance_id=inst.instance_id,
                part_mesh_glb_id=part.mesh_glb_id,
                placement=placement,
                properties=part.properties,
                error=None,
            )
        )
        if part.properties is not None:
            roll_up.append((part.properties, placement))

    combined = _combine_properties(roll_up)
    return EvaluateAssemblyResult(
        assembly_id=request.assembly_id,
        version=request.version,
        instances=instances_out,
        status=status,
        diagnosis=diagnosis,
        mate_errors=mate_errors,
        properties=combined,
        bounding_box=combined.bounding_box if combined is not None else None,
    )
