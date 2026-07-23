"""Assembly interference/collision detection — pairwise B-rep clash over a solve.

The clash-detection sibling of :mod:`geometry.assembly.evaluate` /
:mod:`geometry.assembly.export` (BACKLOG P1; design ``assemblies.md`` §4): where
``evaluate_assembly`` returns per-instance ``{shared mesh, solved placement}``
and the export composes them into one file, this path answers "do any two
instances physically overlap?" over the EXACT same solved world-placed bodies.

Pipeline (reusing the shipped solve VERBATIM):

1. :func:`~geometry.assembly.evaluate.solve_assembly` — evaluate each unique part
   once + solve the mate graph → each bodied instance's resolved kernel body
   paired with its SOLVED world placement (the identical input the STEP export
   composes, so a clash is checked on exactly what a user would export/see).
2. Place every bodied instance at its solved world pose
   (:func:`geometry.kernel.export.place_body` — the shared placement transform,
   NOT reinvented) and scan every unordered instance pair once, computing the
   overlap via :func:`geometry.kernel.interference.probe_overlap`
   (``BRepAlgoAPI_Common``). A pair whose exact overlap exceeds the
   kernel-tolerance clash floor is reported; a merely-touching (coincident-face,
   zero-volume) pair is NOT. When the exact boolean *fails* on a pair whose
   solved-world bounding boxes overlap (an OCCT robustness limit that would
   otherwise masquerade as "clear"), the pair is surfaced as an ``unresolved``
   clash for inspection — never silently dropped — and the failure is logged with
   both instance ids.

**Cost — accepted v1 bound.** The scan is O(N²) in the number of bodied
instances (every unordered pair booleaned). That is the deliberate v1 bound: it
is exact and simple, and an assembly's bodied-instance count is small in
practice. A broad-phase AABB pre-filter (skip pairs whose solved-world bounding
boxes are disjoint before the expensive boolean) is the obvious v2 optimisation
and joins additively without changing this contract.

Never-500 (design §4, mirroring ``evaluate_assembly``): the whole function is a
pure, total function of the request — a bodyless part, an unresolvable mate, an
ungrounded/conflicting solve is absorbed by ``solve_assembly`` into a typed
status/diagnosis + a (possibly empty) clash list, never a raise. No kernel type
crosses the boundary — the result is plain floats/uuids. Deterministic
(RESEARCH §9): the fixed request-instance-order pairwise scan over the
BLAS-pinned solve yields an identical clash list across interpreter restarts.
"""

from __future__ import annotations

from py_kit import get_logger
from py_kit.schemas.assemblies import (
    ClashPair,
    EvaluateAssemblyRequest,
    InterferenceResult,
)

from geometry.assembly.evaluate import PlacedInstance, solve_assembly
from geometry.assembly.transform import Pose
from geometry.kernel import place_body, probe_overlap
from geometry.kernel.interference import CLASH_VOLUME_FLOOR_MM3
from geometry.kernel.types import BodyShape

_logger = get_logger("geometry.assembly.interference")


def _world_body(placed: PlacedInstance) -> BodyShape:
    """A solved instance's part body copied to its SOLVED world placement.

    Decomposes the placement into a translation + unit quaternion via the same
    :class:`Pose` the solver/export use, then positions the body through the
    shared kernel transform, so no representation drift happens between solve,
    export, and clash check.
    """
    pose = Pose.from_placement(placed.placement)
    return place_body(
        placed.body,
        (float(pose.t[0]), float(pose.t[1]), float(pose.t[2])),
        (float(pose.q[0]), float(pose.q[1]), float(pose.q[2]), float(pose.q[3])),
    )


def check_interference(request: EvaluateAssemblyRequest) -> InterferenceResult:
    """Solve *request* and report every interfering instance pair (design §4).

    Reuses :func:`solve_assembly` (identical to the evaluate/export path), places
    every bodied instance at its solved world pose, and returns the pairwise
    clash list — each unordered pair whose solved-world bodies overlap with
    volume above the kernel-tolerance floor — alongside the solve's own status /
    diagnosis / per-mate errors (the caller gets the same solve context evaluate
    reports). A clash-free assembly is ``clashes: []``. O(N²) over bodied
    instances (module docstring). Total — never raises for an evaluation outcome
    (the never-500 contract, §4).
    """
    solved = solve_assembly(request)
    world_bodies = [
        (placed.instance_id, _world_body(placed)) for placed in solved.placed
    ]

    clashes: list[ClashPair] = []
    for i in range(len(world_bodies)):
        id_a, body_a = world_bodies[i]
        for j in range(i + 1, len(world_bodies)):
            id_b, body_b = world_bodies[j]
            probe = probe_overlap(body_a, body_b)
            if probe.boolean_failed:
                # Observability: a raised boolean is never silent, whatever the
                # AABB fallback then decided (unresolved vs genuinely-clear).
                _logger.warning(
                    "interference_boolean_failed",
                    instance_a=str(id_a),
                    instance_b=str(id_b),
                    unresolved=probe.unresolved,
                    aabb_overlap_mm3=probe.volume_mm3 if probe.unresolved else 0.0,
                )
            if probe.unresolved:
                # Boolean failed but the solved-world AABBs overlap: a real
                # interference is possible and could not be measured → surface it
                # for inspection rather than hide it as clear (the dangerous FN).
                clashes.append(
                    ClashPair(
                        instance_a=id_a,
                        instance_b=id_b,
                        overlap_volume_mm3=probe.volume_mm3,
                        unresolved=True,
                    )
                )
            elif probe.volume_mm3 > CLASH_VOLUME_FLOOR_MM3:
                clashes.append(
                    ClashPair(
                        instance_a=id_a,
                        instance_b=id_b,
                        overlap_volume_mm3=probe.volume_mm3,
                    )
                )

    return InterferenceResult(
        assembly_id=request.assembly_id,
        version=request.version,
        clashes=clashes,
        status=solved.status,
        diagnosis=solved.diagnosis,
        mate_errors=solved.mate_errors,
    )
