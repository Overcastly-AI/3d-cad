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

import re
import uuid
from dataclasses import dataclass, field, replace

import numpy as np
from loft_wire.assemblies import (
    MAX_ASSEMBLY_INSTANCES,
    AssemblySolveDiagnosis,
    AssemblySolveStatus,
    EvaluateAssemblyRequest,
    EvaluateAssemblyResult,
    EvaluatedInstance,
    InstancePlacementResult,
    MateEvaluationError,
    Placement,
    SubAssemblyPlacement,
    mate_instance_ids,
    nested_occurrence_id,
)
from loft_wire.component_mirrors import MirrorCopyRef, MirrorState
from loft_wire.component_patterns import (
    PatternCopyRef,
    PatternCount,
    PatternCountsResult,
)
from loft_wire.features import (
    EvaluateTreeRequest,
    EvaluateTreeResult,
    FeatureError,
)
from loft_wire.geometry import (
    BoundingBox,
    ShapeProperties,
    TopologyCounts,
    Vec3,
)
from loft_wire.in_context import InContextStatus
from loft_wire.joints import JointState
from loft_wire.omitted_occurrences import (
    OmittedOccurrences,
    OmittedPart,
)
from py_kit.errors import ValidationApiError

from geometry.assembly.in_context import solve_in_context
from geometry.assembly.mirrors import (
    MirrorSeed,
    MirrorSource,
    MirrorTarget,
    OppositeHand,
    expand_mirror,
    mirrored_name,
    opposite_hand_body,
    opposite_hand_mesh,
    opposite_hand_properties,
    source_part_key,
)
from geometry.assembly.patterns import PatternTarget, SeedPart, expand_pattern
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
from geometry.features.evaluate import TreeEvaluation, features_have_twist
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

    ``evaluation`` is retained for ONE reason and must not be dropped as
    "unused": a ``TreeEvaluation`` is the ownership handle on the kernel shapes
    it produced (see its docstring, docs/PERF.md fix #1). The rebuild cache
    offers a tree's state as a resume point only once its evaluation is
    unreachable, and a resuming rebuild MUTATES those shapes in place — so
    keeping ``body`` while dropping the evaluation would let a concurrent
    rebuild of the same part tree modify a body this assembly is still placing,
    measuring and exporting.
    """

    body: BodyShape | None
    mesh_glb_id: str | None
    properties: ShapeProperties | None
    error: FeatureError | None
    evaluation: TreeEvaluation | None = None

    def face_names(self) -> list[str | None] | None:
        """The body's history-based face names (aligned with ``body.faces()``),
        which let a mate follow a face or hole a part edit moved; ``None``
        without an evaluation."""
        return None if self.evaluation is None else self.evaluation.face_names()


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


def _evaluate_unique_parts(
    request: EvaluateAssemblyRequest, cache: dict[str, _PartResult]
) -> dict[str, _PartResult]:
    """Evaluate each UNIQUE part exactly once, keyed by ``part_key`` (§4 step 1).

    Reuses :func:`~geometry.features.evaluate_tree` verbatim (which tessellates +
    ``store_mesh_glb``s the body), so two instances of one part share a single
    evaluation and a single content-addressed mesh (the §6.4 dedup contract).
    *cache* is shared with every sub-assembly of the request, so a part used at
    two levels is still evaluated once. Sub-assembly instances are skipped: their
    parts are evaluated by their own solve.
    """
    for inst in request.instances:
        if inst.sub_assembly is not None or inst.part_key in cache:
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
            evaluation=evaluation,
            body=evaluation.body,
            mesh_glb_id=evaluation.result.mesh_glb_id,
            properties=evaluation.result.properties,
            error=error,
        )
    return cache


def iter_part_instances(
    instances: list[EvaluatedInstance],
) -> list[EvaluatedInstance]:
    """Every PART instance in *instances*, through every sub-assembly, in order."""
    out: list[EvaluatedInstance] = []
    for inst in instances:
        if inst.sub_assembly is None:
            out.append(inst)
        else:
            out.extend(iter_part_instances(inst.sub_assembly.instances))
    return out


def _resolve_mates(
    evaluable: list[ResolvableInstance],
    occurrences: list[ResolvableInstance],
    request: EvaluateAssemblyRequest,
) -> tuple[AssemblySolveInput, list[MateEvaluationError]]:
    """Build the solve input, resolving each mate individually (§4 step 2).

    Reuses #3's :func:`build_assembly_solve_input` per mate so an unresolvable
    mate (stale/ambiguous signature, or a reference to an unavailable instance)
    is reported as a per-mate error and DROPPED — the assembly still solves the
    mates it can, degrading to under-constrained rather than failing whole (§4).
    The kept mates are re-sorted deterministically by the solver.

    *occurrences* are the parts inside rigid sub-assemblies: a mate may name
    one, and is then solved against the sub-assembly it moves with. Two parts of
    the SAME rigid sub-assembly cannot move relative to each other, so a mate
    between them is dropped with ``mate_within_sub_assembly``.
    """
    solve_instances = build_assembly_solve_input(evaluable, []).instances
    group_of = {inst.instance_id: inst.solver_id for inst in [*evaluable, *occurrences]}
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
        if len({group_of.get(i, i) for i in ids}) < len(ids):
            mate_errors.append(_mate_within_sub_assembly_error(evaluated.mate_id))
            continue
        resolvable = ResolvableMate(
            mate_id=evaluated.mate_id,
            order_index=evaluated.order_index,
            mate=evaluated.mate,
        )
        try:
            built = build_assembly_solve_input(evaluable, [resolvable], occurrences)
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


def _mate_within_sub_assembly_error(mate_id: uuid.UUID) -> MateEvaluationError:
    """A per-mate error for a mate between two parts of one rigid sub-assembly."""
    return MateEvaluationError(
        mate_id=mate_id,
        error=FeatureError(
            code="mate_within_sub_assembly",
            message=(
                f"mate {mate_id} joins two parts of the same rigid sub-assembly, "
                "which cannot move relative to each other; join them in the "
                "sub-assembly itself"
            ),
        ),
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
    #: Instance ids from the top-level sub-assembly instance down to this part
    #: (``instance_id`` is then that path's occurrence id); empty for a part
    #: instanced directly in the assembly.
    path: tuple[uuid.UUID, ...] = ()


@dataclass(frozen=True)
class Occurrence:
    """One PART placed by the assembly, at any depth (service-internal).

    A part instanced directly is its own occurrence (``path`` empty,
    ``group_id`` its own id, ``offset`` None). A part inside a rigid
    sub-assembly carries the path to it, the top-level sub-assembly instance it
    moves with (``group_id``) and its pose in that instance's frame
    (``offset``). ``placement`` is the SOLVED world pose (the seed when
    unsolved); ``error`` is set, and ``body`` None, when its part made no body.
    """

    occurrence_id: uuid.UUID
    path: tuple[uuid.UUID, ...]
    group_id: uuid.UUID
    offset: Pose | None
    part_key: str
    name: str | None
    seed: Placement
    placement: Placement
    body: BodyShape | None
    error: FeatureError | None
    #: Set on a copy placed by one of THIS assembly's component patterns.
    pattern: PatternCopyRef | None = None
    #: Set on a twin placed by one of THIS assembly's component mirrors.
    mirror: MirrorCopyRef | None = None


@dataclass(frozen=True)
class SolvedAssembly:
    """The service-internal solve outcome — solved placements + KERNEL bodies.

    The shared core of :func:`evaluate_assembly` (which serialises it to the
    boundary DTO) and :func:`geometry.assembly.export.export_assembly` (which
    composes the bodies into one multi-instance CAD file). ``parts`` /
    ``placed`` hold kernel :class:`~geometry.kernel.types.BodyShape` solids, so
    this type is NEVER serialised or crossed over a service boundary (CLAUDE.md).

    ``placed`` is the export-ready view: one entry per part occurrence that
    produced a body (sub-assemblies opened, depth first), each carrying its
    resolved part body and its SOLVED world placement (the authored seed for an
    un-solved instance). ``occurrences`` is the same list including the parts
    that made no body; ``instance_errors`` is keyed by occurrence id.
    ``sub_assembly_poses`` holds each top-level sub-assembly instance's solved
    pose.
    """

    parts: dict[str, _PartResult]
    solved: dict[uuid.UUID, Placement]
    instance_errors: dict[uuid.UUID, FeatureError]
    placed: list[PlacedInstance]
    status: AssemblySolveStatus
    diagnosis: AssemblySolveDiagnosis | None
    mate_errors: list[MateEvaluationError]
    joint_states: list[JointState]
    occurrences: list[Occurrence]
    sub_assembly_poses: dict[uuid.UUID, Placement]
    #: Each of this assembly's own patterns: its count, or why it placed none.
    pattern_states: list[PatternCount]
    #: The same for every pattern at every level (sub-assemblies' too), once
    #: each, in first-seen order.
    all_pattern_states: list[PatternCount]
    #: How each in-context link whose context is this assembly resolved.
    in_context: list[InContextStatus] = field(default_factory=list["InContextStatus"])
    #: Each of this assembly's own mirrors: its twins, or why it placed none.
    mirror_states: list[MirrorState] = field(default_factory=list["MirrorState"])
    #: Every sub-assembly solved for this tree, at any depth, keyed by its
    #: ``part_key`` (one document at one version, solved once however often it
    #: is instanced). The STEP export rebuilds the product tree from it.
    subs: dict[str, SolvedAssembly] = field(default_factory=dict[str, "SolvedAssembly"])

    def omitted(self) -> OmittedOccurrences | None:
        """The occurrences with no body — the ones an export leaves out.

        See :func:`omitted_occurrences`; None when every occurrence has a body.
        """
        return omitted_occurrences(self.occurrences)


#: An instance's trailing ``<n>``.
_INSTANCE_SUFFIX = re.compile(r"\s*<\d+>$")


def part_name_of(instance_name: str | None) -> str:
    """The part's name of an instance: "Crank arm <2>" -> "Crank arm".

    The web's ``partNameOf`` rule; a request without a name gives "Part" (as
    the web does). A pattern copy is never the first occurrence of its part
    met (its seed precedes it), so the part is named from the seed.
    """
    if instance_name is None:
        return "Part"
    return _INSTANCE_SUFFIX.sub("", instance_name).strip() or instance_name


def omitted_occurrences(occurrences: list[Occurrence]) -> OmittedOccurrences | None:
    """Fold the bodiless *occurrences* into one entry per part (ASM-FAILED-PART-API).

    *occurrences* is :attr:`SolvedAssembly.occurrences`: every part placed at
    any depth (sub-assemblies opened, each one's own pattern copies included)
    plus this assembly's pattern copies — so the bodiless ones are exactly the
    occurrences ``placed`` (and with it every export) leaves out. Grouped by part
    document (the ``part_key`` before ``@``), in first-seen order, which is
    deterministic because the occurrence order is.
    """
    by_part: dict[str, OmittedPart] = {}
    count = 0
    for occ in occurrences:
        if occ.body is not None:
            continue
        count += 1
        document = occ.part_key.split("@", 1)[0] or None
        key = document if document is not None else f"name:{occ.name}"
        known = by_part.get(key)
        if known is not None:
            by_part[key] = known.model_copy(
                update={"occurrences": known.occurrences + 1}
            )
            continue
        by_part[key] = OmittedPart(
            name=part_name_of(occ.name),
            part_document_id=document,
            code=occ.error.code if occ.error is not None else "no_body",
            message=(
                occ.error.message
                if occ.error is not None
                else "The part produced no body."
            ),
            occurrences=1,
        )
    if count == 0:
        return None
    return OmittedOccurrences(count=count, parts=list(by_part.values()))


def solve_assembly(request: EvaluateAssemblyRequest) -> SolvedAssembly:
    """Evaluate + solve an assembly to placements + KERNEL bodies (design §4).

    The shared pipeline behind :func:`evaluate_assembly` and the assembly
    export: evaluate each unique part once (§4 step 1), resolve every mate
    individually (§4 step 2), solve the mate graph (§4 step 3), and pair each
    instance's resolved body with its solved world placement. Total — never
    raises for an evaluation outcome (a bad part/mate/solve is a typed per-entry
    error or a non-``well_constrained`` status, the never-500 contract, §4).
    Deterministic (RESEARCH §9): the BLAS-pinned solver + fixed instance order.

    A RIGID SUB-ASSEMBLY (``EvaluatedInstance.sub_assembly``) is solved first, in
    its own frame and by its own mates (once per distinct sub-assembly, however
    often it is instanced), then enters this solve as ONE body: its parts keep
    their solved poses relative to each other and move with the instance. A
    mate here may name one of those parts by occurrence id.

    In-context links whose context is this assembly are kept current
    (:mod:`geometry.assembly.in_context`): the bodies, meshes and poses
    returned use their resolved curves, and ``in_context`` says how each
    resolved. Without such links the assembly is solved once, as before.
    """
    parts: dict[str, _PartResult] = {}

    def solve(current: EvaluateAssemblyRequest, stale: set[str]) -> SolvedAssembly:
        # An opposite-hand part derives from its source: stale with it.
        for key in [k for k in parts if source_part_key(k) in stale]:
            parts.pop(key, None)
        return _solve(current, parts, {})

    run = solve_in_context(
        request,
        solve,
        lambda solved: solved.occurrences,
        lambda solved, key: solved.parts[key].face_names(),
    )
    if not run.statuses:
        return run.solved
    return replace(run.solved, in_context=run.statuses)


def _solve(
    request: EvaluateAssemblyRequest,
    parts: dict[str, _PartResult],
    subs: dict[str, SolvedAssembly],
) -> SolvedAssembly:
    """:func:`solve_assembly` with the part and sub-assembly caches threaded
    through every level (both keyed by ``part_key``, which names one document
    at one version)."""
    _evaluate_unique_parts(request, parts)
    occurrences = _seed_occurrences(request, parts, subs)

    # Once per unique part, like its evaluation; only a part some mate names
    # needs them, and an unmated assembly pays nothing.
    mated = {
        i for evaluated in request.mates for i in mate_instance_ids(evaluated.mate)
    }
    names_of: dict[str, list[str | None] | None] = {}
    for occ in occurrences:
        if occ.occurrence_id in mated and occ.part_key not in names_of:
            names_of[occ.part_key] = parts[occ.part_key].face_names()

    instance_errors: dict[uuid.UUID, FeatureError] = {}
    nested: list[ResolvableInstance] = []
    direct_bodies: dict[uuid.UUID, BodyShape] = {}
    bodied_groups: set[uuid.UUID] = set()
    for occ in occurrences:
        if occ.body is None:
            assert occ.error is not None
            instance_errors[occ.occurrence_id] = occ.error
            continue
        bodied_groups.add(occ.group_id)
        if not occ.path:
            direct_bodies[occ.occurrence_id] = occ.body
            continue
        nested.append(
            ResolvableInstance(
                instance_id=occ.occurrence_id,
                body=occ.body,
                placement=occ.seed,
                face_names=names_of.get(occ.part_key),
                group_id=occ.group_id,
                offset=occ.offset,
            )
        )

    # The solver bodies: each top-level instance that places anything — a part
    # with a body, or a sub-assembly with at least one (it has no B-rep of its
    # own; mates reach it through its parts).
    evaluable = [
        ResolvableInstance(
            instance_id=inst.instance_id,
            body=direct_bodies.get(inst.instance_id),
            placement=inst.placement,
            grounded=inst.grounded,
            face_names=names_of.get(inst.part_key),
        )
        for inst in request.instances
        if inst.instance_id in bodied_groups
    ]

    status: AssemblySolveStatus = "under_constrained"
    diagnosis: AssemblySolveDiagnosis | None = None
    mate_errors: list[MateEvaluationError] = []
    solved: dict[uuid.UUID, Placement] = {}
    joint_states: list[JointState] = []

    if evaluable:
        try:
            # Belt-and-braces: the per-mate resolve loop and the self-mate guard
            # already convert bad mates into typed per-mate errors, but the
            # pre-solve instance build (a duplicate instance id) and the solver
            # itself may still raise AssemblyDefinitionError. Map ANY residual to
            # a clean assembly-level status — solve_assembly never raises for an
            # evaluation outcome (§4, the never-500 contract).
            problem, mate_errors = _resolve_mates(evaluable, nested, request)
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
            joint_states = result.joint_states
    else:
        diagnosis = AssemblySolveDiagnosis(
            remaining_dof=0,
            message="No instance produced a body to place; nothing to solve.",
        )

    sub_assembly_poses = {
        inst.instance_id: solved.get(inst.instance_id, inst.placement)
        for inst in request.instances
        if inst.sub_assembly is not None
    }
    placed_occurrences = [_placed(occ, solved) for occ in occurrences]
    # Patterns are placed from the SOLVED poses: each copy is fixed relative to
    # its seed and to the pattern's reference geometry.
    copies, pattern_states = _expand_patterns(request, placed_occurrences, parts)
    for copy in copies:
        if copy.error is not None:
            instance_errors[copy.occurrence_id] = copy.error
    placed_occurrences.extend(copies)
    twins, mirror_states = _expand_mirrors(
        request, placed_occurrences, parts, sub_assembly_poses
    )
    for twin in twins:
        if twin.error is not None:
            instance_errors[twin.occurrence_id] = twin.error
    placed_occurrences.extend(twins)
    placed = [
        PlacedInstance(
            instance_id=occ.occurrence_id,
            part_key=occ.part_key,
            body=occ.body,
            placement=occ.placement,
            name=occ.name,
            path=occ.path,
        )
        for occ in placed_occurrences
        if occ.body is not None
    ]

    return SolvedAssembly(
        parts=parts,
        solved=solved,
        instance_errors=instance_errors,
        placed=placed,
        status=status,
        diagnosis=diagnosis,
        mate_errors=mate_errors,
        joint_states=joint_states,
        occurrences=placed_occurrences,
        sub_assembly_poses=sub_assembly_poses,
        pattern_states=pattern_states,
        all_pattern_states=_all_pattern_states(request, pattern_states, subs),
        mirror_states=mirror_states,
        subs=subs,
    )


def _all_pattern_states(
    request: EvaluateAssemblyRequest,
    own: list[PatternCount],
    subs: dict[str, SolvedAssembly],
) -> list[PatternCount]:
    """*own* plus every sub-assembly's patterns, each pattern once."""
    out = list(own)
    seen = {state.pattern_id for state in own}
    for inst in request.instances:
        child = subs.get(inst.part_key) if inst.sub_assembly is not None else None
        if child is None:
            continue
        for state in child.all_pattern_states:
            if state.pattern_id not in seen:
                seen.add(state.pattern_id)
                out.append(state)
    return out


def _copy_name(name: str | None, index: int) -> str | None:
    """A copy's name: its seed's, numbered within the pattern (the seed is 1)."""
    return None if name is None else f"{name} ({index + 1})"


def _expand_patterns(
    request: EvaluateAssemblyRequest,
    occurrences: list[Occurrence],
    parts: dict[str, _PartResult],
) -> tuple[list[Occurrence], list[PatternCount]]:
    """The copies *request*'s patterns place, from the solved *occurrences*.

    Bounded: the copies may take the assembly up to the instance bound and no
    further; a pattern that would pass it places nothing and says so.
    """
    if not request.patterns:
        return [], []
    targets = {
        occ.occurrence_id: PatternTarget(
            body=occ.body,
            placement=Pose.from_placement(occ.placement),
            part_key=occ.part_key,
            face_names=parts[occ.part_key].face_names,
        )
        for occ in occurrences
    }
    seeds: dict[uuid.UUID, list[SeedPart]] = {
        inst.instance_id: [] for inst in request.instances
    }
    source: dict[tuple[uuid.UUID, tuple[uuid.UUID, ...]], Occurrence] = {}
    for occ in occurrences:
        if occ.group_id not in seeds:
            continue
        inner = occ.path[1:]
        seeds[occ.group_id].append(
            SeedPart(inner=inner, placement=Pose.from_placement(occ.placement))
        )
        source[(occ.group_id, inner)] = occ
    budget = MAX_ASSEMBLY_INSTANCES - len(occurrences)
    copies: list[Occurrence] = []
    states: list[PatternCount] = []
    for evaluated in sorted(
        request.patterns, key=lambda p: (p.order_index, str(p.pattern_id))
    ):
        placed, state = expand_pattern(evaluated, seeds, targets, budget)
        budget -= len(placed)
        states.append(state)
        for copy in placed:
            seed_part = source[(copy.ref.seed_instance_id, copy.inner)]
            placement = copy.placement.to_placement()
            copies.append(
                Occurrence(
                    occurrence_id=copy.occurrence_id,
                    path=copy.path,
                    group_id=copy.group_id,
                    offset=seed_part.offset,
                    part_key=seed_part.part_key,
                    name=_copy_name(seed_part.name, copy.ref.index),
                    seed=placement,
                    placement=placement,
                    body=seed_part.body,
                    error=seed_part.error,
                    pattern=copy.ref,
                )
            )
    return copies, states


def _mirror_seeds(
    request: EvaluateAssemblyRequest,
    occurrences: list[Occurrence],
    parts: dict[str, _PartResult],
    sub_poses: dict[uuid.UUID, Placement],
) -> dict[uuid.UUID, MirrorSeed]:
    """Each instance of *request* as a mirror may reflect it: its solved pose
    and the parts it places (pattern copies excluded)."""
    members: dict[uuid.UUID, list[Occurrence]] = {}
    for occ in occurrences:
        if occ.pattern is None:
            members.setdefault(occ.group_id, []).append(occ)
    seeds: dict[uuid.UUID, MirrorSeed] = {}
    for inst in request.instances:
        own = members.get(inst.instance_id, [])
        if inst.sub_assembly is None:
            if not own:
                continue
            pose = Pose.from_placement(own[0].placement)
        else:
            pose = Pose.from_placement(sub_poses[inst.instance_id])
        seeds[inst.instance_id] = MirrorSeed(
            pose=pose,
            is_part=inst.sub_assembly is None,
            parts=tuple(
                MirrorSource(
                    inner=occ.path[1:],
                    offset=occ.offset if occ.offset is not None else Pose.identity(),
                    part_key=occ.part_key,
                    body=occ.body,
                    properties=parts[occ.part_key].properties,
                )
                for occ in own
            ),
        )
    return seeds


def _opposite_part(
    source: _PartResult, hand: OppositeHand, deflection: float, twisted: bool
) -> _PartResult:
    """The derived opposite-hand part of *source* (``mirrors`` docstring)."""
    assert source.body is not None
    body = opposite_hand_body(source.body, hand.axis, hand.centre)
    return _PartResult(
        body=body,
        mesh_glb_id=opposite_hand_mesh(body, deflection, twisted=twisted),
        properties=(
            None
            if source.properties is None
            else opposite_hand_properties(source.properties, hand.axis, hand.centre)
        ),
        error=None,
    )


def _expand_mirrors(
    request: EvaluateAssemblyRequest,
    occurrences: list[Occurrence],
    parts: dict[str, _PartResult],
    sub_poses: dict[uuid.UUID, Placement],
) -> tuple[list[Occurrence], list[MirrorState]]:
    """The twins *request*'s mirrors place, from the solved *occurrences*
    (pattern copies count toward the bound but are not mirrored). An
    opposite-hand twin's derived part joins the *parts* cache under its key."""
    if not request.mirrors:
        return [], []
    targets = {
        occ.occurrence_id: MirrorTarget(
            body=occ.body,
            placement=Pose.from_placement(occ.placement),
            face_names=parts[occ.part_key].face_names,
        )
        for occ in occurrences
        if occ.pattern is None
    }
    seeds = _mirror_seeds(request, occurrences, parts, sub_poses)
    source = {
        (occ.group_id, occ.path[1:]): occ for occ in occurrences if occ.pattern is None
    }
    twisted = {
        inst.part_key
        for inst in iter_part_instances(request.instances)
        if features_have_twist(inst.features)
    }
    budget = MAX_ASSEMBLY_INSTANCES - len(occurrences)
    twins: list[Occurrence] = []
    states: list[MirrorState] = []
    for evaluated in sorted(
        request.mirrors, key=lambda m: (m.order_index, str(m.mirror_id))
    ):
        placed, state = expand_mirror(evaluated, seeds, targets, budget)
        budget -= len(placed)
        states.append(state)
        for twin in placed:
            seed_part = source[(twin.ref.seed_instance_id, twin.inner)]
            part_key, body = seed_part.part_key, seed_part.body
            if twin.opposite is not None and body is not None:
                part_key = twin.opposite.part_key
                if part_key not in parts:
                    parts[part_key] = _opposite_part(
                        parts[seed_part.part_key],
                        twin.opposite,
                        request.linear_deflection,
                        seed_part.part_key in twisted,
                    )
                body = parts[part_key].body
            placement = twin.placement.to_placement()
            twins.append(
                Occurrence(
                    occurrence_id=twin.occurrence_id,
                    path=twin.path,
                    group_id=twin.group_id,
                    offset=seed_part.offset,
                    part_key=part_key,
                    name=mirrored_name(seed_part.name, twin.opposite is not None),
                    seed=placement,
                    placement=placement,
                    body=body,
                    error=seed_part.error,
                    mirror=twin.ref,
                )
            )
    return twins, states


def _seed_occurrences(
    request: EvaluateAssemblyRequest,
    parts: dict[str, _PartResult],
    subs: dict[str, SolvedAssembly],
) -> list[Occurrence]:
    """Every part *request* places, at its SEED pose, sub-assemblies opened.

    A sub-assembly is solved (once per ``part_key``) in its own frame; each of
    its parts becomes an occurrence of this assembly whose ``offset`` is its
    solved pose in that frame and whose seed is the instance's seed composed
    with it.
    """
    occurrences: list[Occurrence] = []
    for inst in request.instances:
        if inst.sub_assembly is None:
            # Parts listed after a large sub-assembly count toward the same
            # bound as its contents.
            if len(occurrences) >= MAX_ASSEMBLY_INSTANCES:
                raise assembly_too_large()
            part = parts[inst.part_key]
            occurrences.append(
                Occurrence(
                    occurrence_id=inst.instance_id,
                    path=(),
                    group_id=inst.instance_id,
                    offset=None,
                    part_key=inst.part_key,
                    name=inst.name,
                    seed=inst.placement,
                    placement=inst.placement,
                    body=part.body,
                    error=part.error,
                )
            )
            continue
        child = subs.get(inst.part_key)
        if child is None:
            child = _solve(inst.sub_assembly, parts, subs)
            subs[inst.part_key] = child
        # The bound is on the parts the WHOLE tree places: a sub-assembly
        # within it on its own (its patterns' counts can grow when a driving
        # part gains holes) can still push this level past it, so refuse
        # before materialising more than the bound allows.
        if len(occurrences) + len(child.occurrences) > MAX_ASSEMBLY_INSTANCES:
            raise assembly_too_large()
        frame = Pose.from_placement(inst.placement)
        for occ in child.occurrences:
            offset = Pose.from_placement(occ.placement)
            seed = frame.compose(offset).to_placement()
            occurrences.append(
                Occurrence(
                    occurrence_id=nested_occurrence_id(
                        inst.instance_id, occ.occurrence_id
                    ),
                    path=(inst.instance_id, *(occ.path or (occ.occurrence_id,))),
                    group_id=inst.instance_id,
                    offset=offset,
                    part_key=occ.part_key,
                    name=occ.name,
                    seed=seed,
                    placement=seed,
                    body=occ.body,
                    error=occ.error,
                )
            )
    return occurrences


def assembly_too_large() -> ValidationApiError:
    """The typed refusal for a tree that places more than the bound.

    Raised (never folded into a 200) because nothing about such a tree can be
    evaluated within the work bound: it is refused before any per-part result,
    clash pair or STEP occurrence is built (audit G2).
    """
    return ValidationApiError(
        f"This assembly places more than {MAX_ASSEMBLY_INSTANCES} parts across "
        "its sub-assemblies and patterns; at most that many can be evaluated "
        "at once.",
        code="assembly_too_large",
        details={"max_instances": MAX_ASSEMBLY_INSTANCES},
    )


def _placed(occ: Occurrence, solved: dict[uuid.UUID, Placement]) -> Occurrence:
    """*occ* at its solved world pose: its group's solved pose, composed with
    its offset inside the group (the seed when its group did not solve)."""
    group_pose = solved.get(occ.group_id)
    if group_pose is None:
        return occ
    if occ.offset is None:
        return replace(occ, placement=group_pose)
    pose = Pose.from_placement(group_pose).compose(occ.offset)
    return replace(occ, placement=pose.to_placement())


def evaluate_assembly(request: EvaluateAssemblyRequest) -> EvaluateAssemblyResult:
    """Evaluate an assembly to solved placements + shared meshes (design §4).

    Deterministic (RESEARCH §9): the same request yields an identical result —
    bitwise-stable ``part_mesh_glb_id``s (content hashes of deterministic GLBs)
    and solved transforms (the BLAS-pinned solver). Never raises for an
    evaluation outcome — a bad part/mate/solve is a typed per-entry error or a
    non-``well_constrained`` status inside the result envelope. The one refusal
    is the work bound: a tree whose sub-assemblies and patterns place more than
    ``MAX_ASSEMBLY_INSTANCES`` parts raises the typed ``assembly_too_large``
    (:func:`assembly_too_large`) before any per-part work. One result row per
    placed part: a sub-assembly contributes its parts, each with its path.
    """
    solved_assembly = solve_assembly(request)
    parts = solved_assembly.parts

    instances_out: list[InstancePlacementResult] = []
    roll_up: list[tuple[ShapeProperties, Placement]] = []
    for occ in solved_assembly.occurrences:
        path = list(occ.path)
        if occ.error is not None:
            instances_out.append(
                InstancePlacementResult(
                    instance_id=occ.occurrence_id,
                    part_mesh_glb_id=None,
                    placement=occ.seed,
                    properties=None,
                    error=occ.error,
                    path=path,
                    pattern=occ.pattern,
                    mirror=occ.mirror,
                )
            )
            continue
        part = parts[occ.part_key]
        instances_out.append(
            InstancePlacementResult(
                instance_id=occ.occurrence_id,
                part_mesh_glb_id=part.mesh_glb_id,
                placement=occ.placement,
                properties=part.properties,
                error=None,
                path=path,
                pattern=occ.pattern,
                mirror=occ.mirror,
            )
        )
        if part.properties is not None:
            roll_up.append((part.properties, occ.placement))

    combined = _combine_properties(roll_up)
    return EvaluateAssemblyResult(
        assembly_id=request.assembly_id,
        version=request.version,
        instances=instances_out,
        status=solved_assembly.status,
        diagnosis=solved_assembly.diagnosis,
        mate_errors=solved_assembly.mate_errors,
        properties=combined,
        bounding_box=combined.bounding_box if combined is not None else None,
        joint_states=solved_assembly.joint_states,
        sub_assemblies=[
            SubAssemblyPlacement(instance_id=instance_id, placement=placement)
            for instance_id, placement in solved_assembly.sub_assembly_poses.items()
        ],
        pattern_states=solved_assembly.pattern_states,
        mirror_states=solved_assembly.mirror_states,
        in_context=solved_assembly.in_context,
        omitted=solved_assembly.omitted(),
    )


def count_patterns(request: EvaluateAssemblyRequest) -> PatternCountsResult:
    """How many each pattern of *request* places, at every level (ASM-A3).

    The BOM and the instance bound need a hole-driven pattern's count, which
    only the evaluated driving part knows. Runs the same solve as evaluation
    (patterns are placed from solved poses), so the counts are exactly what an
    evaluation places.
    """
    return PatternCountsResult(counts=solve_assembly(request).all_pattern_states)
