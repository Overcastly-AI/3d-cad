"""A coincident mate MOVES the instance — asserted on the POSE, never the status.

MATE-1 reported that a coincident mate could be authored, shown in the tree and
reported solved while the instance did not move: ``UNDER CONSTRAINED, Free DOF
6`` with the free instance still at its seed. If that were true of the kernel,
assemblies would be broken at the core. Nothing in the suite could answer the
question, which is why this module exists.

**What was already gated, and why none of it covers this.** The two assembly
goldens (``assembly-two-plates-bolted``, ``assembly-two-plates-gap``) are
FULLY-CONSTRAINED joints: a face mate plus two concentric mates through distinct
holes, ``well_constrained``, zero remaining DOF. :mod:`tests.test_assembly_evaluate`
asserts statuses, mesh dedup and the per-mate error posture.
:mod:`tests.test_assembly_mate_candidates` proves the offered face set is the
accepted face set. So the pick side was gated, the resolve side was gated, and
the fully-mated pose was gated — but **a coincident mate acting ALONE, which is
the first mate anybody authors and the only mate in the MATE-1 report, was
gated by nothing.** That gap is the reason a wrong answer could be believed.

**The rule this module encodes: assert on the pose, never on the solve's own
status.** :func:`test_status_alone_cannot_distinguish_the_two` makes it
executable — the working solve and the constraint-free solve BOTH report
``under_constrained``, so any gate keyed on status passes in both worlds. The
report's numbers are not evidence of a lost constraint at all: they are the
ZERO-MATE evaluation of this fixture verbatim (``remaining_dof`` 6, bracket at
its seed), which :func:`test_zero_mates_reproduces_the_reported_reading` pins so
that a future regression which silently drops a mate produces the control's
numbers and fails :func:`test_coincident_alone_seats_the_free_instance`.

**The fixture is MATE-1's own** (``apps/web/e2e/mate-buried-face.spec.ts``): a
grounded 60 x 40 x 6 plate at the origin and a free 24 x 16 x 4 bracket dropped
in roughly at (18, 12, 3) so its body is half-sunk through the plate's top. The
mate joins the bracket's underside to the plate's top face, flush.

**What is asserted, and what is deliberately not.** One coincident mate removes
three of the bracket's six DOF; the along-normal seat is pinned, the two in-plane
translations and the spin about the normal are NOT, and the solver is entitled to
leave them anywhere in that null space. So this locks the hand-derivable
consequences only — the mated face's world plane and the assembly's z extent —
and states the free directions rather than snapshotting them. (Measured, the LM
does slide the bracket ~0.015 mm laterally inside that null space, deterministic
across runs; asserting it would enshrine recorded output, which the
geometry-gates skill forbids. For the same reason this is a test module rather
than a golden: the golden harness compares the FULL ``Placement`` against
hand-derived values, which a deliberately under-constrained joint does not have.)
"""

from __future__ import annotations

import uuid

import numpy as np
from geometry.assembly import evaluate_assembly
from geometry.assembly.transform import Pose
from geometry.features import evaluate_tree
from geometry.kernel.faces import face_signature_dto, planar_faces
from py_kit.schemas.assemblies import (
    CoincidentMate,
    EvaluateAssemblyRequest,
    EvaluateAssemblyResult,
    EvaluatedInstance,
    EvaluatedMate,
    MateFaceRef,
    Placement,
    Quat,
)
from py_kit.schemas.features import (
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    ExtrudeFeature,
    PlanarFaceSignature,
    SketchFeature,
)
from py_kit.schemas.geometry import Vec3

#: Solver-convergence bound for the pose assertions, measured first then set
#: (geometry-gates skill: never copy a bound blindly). Worst observed deviation
#: from the hand-derived values on this fixture (2026-08-27, build123d 0.11.1 /
#: OCCT 7.9, numpy BLAS pinned to 1 thread): mated-face seat plane 2.9e-11 mm,
#: bracket z 4.9e-9 mm, assembly bbox max z 4.8e-9 mm. 1e-6 is ~200x that worst
#: case, headroom for libm/BLAS/platform variation across CI hosts, and is the
#: SAME bound the two assembly goldens and ``test_assembly_resolve``'s
#: ``RESOLVE_TOL`` already document for a numeric mate solve — not a new epsilon
#: invented here. Loosening it is a reviewed decision requiring justification
#: here and in docs/GEOMETRY-QA.md, never a way to make a red run green.
SOLVER_TOL = 1e-6

#: Face-matching tolerance when locating a fixture face by its centroid. A
#: construction detail of the fixture, not an assertion bound.
_PICK_TOL = 1e-6

# --- the fixture's hand-derived geometry ----------------------------------------

PLATE_W, PLATE_D, PLATE_H = 60.0, 40.0, 6.0
BRACKET_W, BRACKET_D, BRACKET_H = 24.0, 16.0, 4.0

#: The bracket's authored seed — half-sunk through the plate's 6 mm top.
SEED_Z = 3.0

#: Where a flush coincident mate must put the bracket's underside: ON the
#: plate's top face, which for a 6 mm plate grounded at the origin is z = 6.
SEAT_Z = PLATE_H

#: The plate's top-face centroid, in the PLATE's local frame.
PLATE_TOP_CENTROID = (PLATE_W / 2, PLATE_D / 2, PLATE_H)

#: The bracket's underside centroid, in the BRACKET's local frame.
BRACKET_UNDERSIDE_CENTROID = (BRACKET_W / 2, BRACKET_D / 2, 0.0)

PLATE_INSTANCE = uuid.UUID(int=101)
BRACKET_INSTANCE = uuid.UUID(int=102)
MATE_ID = uuid.UUID(int=1001)


def _iid(n: int) -> uuid.UUID:
    return uuid.UUID(int=n)


def _block_features(
    width: float, depth: float, height: float, seed: int
) -> list[EvaluatedFeatureInput]:
    """A ``width`` x ``depth`` rectangle on XY extruded ``height``.

    The programmatic twin of the e2e spec's ``createBlockViaApi``, so the gate
    exercises the same part shape the UI reproduction builds.
    """
    corners = [(0.0, 0.0), (width, 0.0), (width, depth), (0.0, depth)]
    entities = [
        {
            "id": f"e{index + 1}",
            "kind": "line",
            "start": {"x": corner[0], "y": corner[1]},
            "end": {
                "x": corners[(index + 1) % len(corners)][0],
                "y": corners[(index + 1) % len(corners)][1],
            },
        }
        for index, corner in enumerate(corners)
    ]
    sketch_id = _iid(seed)
    return [
        EvaluatedFeatureInput(
            id=sketch_id,
            feature=SketchFeature.model_validate(
                {
                    "type": "sketch",
                    "version": 1,
                    "params": {
                        "plane": {"kind": "datum_plane", "plane": "XY"},
                        "entities": entities,
                        "constraints": [],
                    },
                }
            ),
        ),
        EvaluatedFeatureInput(
            id=_iid(seed + 1),
            feature=ExtrudeFeature.model_validate(
                {
                    "type": "extrude",
                    "version": 1,
                    "params": {
                        "profile": {"kind": "feature", "feature_id": str(sketch_id)},
                        "distance_mm": height,
                        "operation": "add",
                        "direction": "normal",
                    },
                }
            ),
        ),
    ]


PLATE_FEATURES = _block_features(PLATE_W, PLATE_D, PLATE_H, 10)
BRACKET_FEATURES = _block_features(BRACKET_W, BRACKET_D, BRACKET_H, 20)


def _face_signature(
    features: list[EvaluatedFeatureInput],
    part_id: int,
    centroid: tuple[float, float, float],
) -> PlanarFaceSignature:
    """The planar face at ``centroid``, derived from the evaluated body.

    Derived the way the mate-authoring overlay derives it (pick side ==
    resolve side, the property :mod:`tests.test_assembly_mate_candidates`
    locks), so no signature is hand-authored. Requires EXACTLY one match — two
    faces sharing a centroid would make the fixture ambiguous rather than the
    solve wrong, and that is worth failing on loudly.
    """
    body = evaluate_tree(
        EvaluateTreeRequest(part_id=_iid(part_id), tree_version=1, features=features)
    ).body
    assert body is not None
    matches: list[PlanarFaceSignature] = []
    for record in planar_faces(body):
        found = record.signature.centroid
        if (
            abs(found.x - centroid[0]) < _PICK_TOL
            and abs(found.y - centroid[1]) < _PICK_TOL
            and abs(found.z - centroid[2]) < _PICK_TOL
        ):
            signature = face_signature_dto(record.face)
            assert signature is not None
            matches.append(signature)
    assert len(matches) == 1, f"{len(matches)} planar faces centred at {centroid}"
    return matches[0]


def _request(*, with_mate: bool) -> EvaluateAssemblyRequest:
    """The MATE-1 fixture, with or without its one coincident mate.

    ``with_mate=False`` is the CONTROL: the identical assembly with nothing
    constraining it, which is what the reported reading turns out to be.
    """
    mates: list[EvaluatedMate] = []
    if with_mate:
        mates = [
            EvaluatedMate(
                mate_id=MATE_ID,
                order_index=0,
                mate=CoincidentMate(
                    a=MateFaceRef(
                        instance_id=BRACKET_INSTANCE,
                        signature=_face_signature(
                            BRACKET_FEATURES, 2, BRACKET_UNDERSIDE_CENTROID
                        ),
                    ),
                    b=MateFaceRef(
                        instance_id=PLATE_INSTANCE,
                        signature=_face_signature(
                            PLATE_FEATURES, 1, PLATE_TOP_CENTROID
                        ),
                    ),
                    flush=True,
                ),
            )
        ]
    return EvaluateAssemblyRequest(
        assembly_id=_iid(9000),
        version=1,
        instances=[
            EvaluatedInstance(
                instance_id=PLATE_INSTANCE,
                part_key="plate@tip",
                features=PLATE_FEATURES,
                placement=Placement(position=Vec3(x=0.0, y=0.0, z=0.0)),
                grounded=True,
            ),
            EvaluatedInstance(
                instance_id=BRACKET_INSTANCE,
                part_key="bracket@tip",
                features=BRACKET_FEATURES,
                placement=Placement(
                    position=Vec3(x=18.0, y=12.0, z=SEED_Z),
                    orientation=Quat(x=0.0, y=0.0, z=0.0, w=1.0),
                ),
                grounded=False,
            ),
        ],
        mates=mates,
    )


def _bracket_placement(result: EvaluateAssemblyResult) -> Placement:
    """The free instance's solved placement, insisting it actually evaluated."""
    bracket = next(i for i in result.instances if i.instance_id == BRACKET_INSTANCE)
    assert bracket.error is None, f"bracket errored: {bracket.error}"
    return bracket.placement


def _underside_world_z(placement: Placement) -> float:
    """The mated face's world height — the geometry the mate is ABOUT.

    Read by applying the SOLVED pose to the bracket's underside centroid, so
    this is a statement about where the face ended up, not about the pose
    field. It is also the honest quantity to bound at ``SOLVER_TOL``: the
    instance's ``position`` carries a lever-arm term (a residual tilt of ~1e-10
    over a ~23 mm arm moves the frame origin by ~1e-7 while the mated faces stay
    coplanar to 1e-11), so bounding the raw position at the kernel's linear
    tolerance would be measuring the wrong thing.
    """
    point = np.array(BRACKET_UNDERSIDE_CENTROID, dtype=np.float64)
    return float(Pose.from_placement(placement).apply_point(point)[2])


# --- the gate -------------------------------------------------------------------


def test_coincident_alone_seats_the_free_instance() -> None:
    """ONE coincident mate seats the bracket ON the plate — the pose, measured.

    The claim MATE-1 could not verify. Every assertion here is on where the
    geometry ENDED UP; none of them consults ``status``.
    """
    result = evaluate_assembly(_request(with_mate=True))

    # The mate survived resolution — a dropped mate is reported here, and a
    # dropped mate is one of the two shapes that would produce the report.
    assert result.mate_errors == [], (
        f"the mate was dropped before the solve: {result.mate_errors}"
    )

    placement = _bracket_placement(result)

    # 1. IT MOVED. Coarse on purpose: a 3 mm displacement is not a tolerance
    #    argument, so this assertion cannot be explained away by convergence.
    assert abs(placement.position.z - SEED_Z) > 1.0, (
        "the bracket is still at its authored seed — the mate did nothing "
        f"(z = {placement.position.z})"
    )

    # 2. IT MOVED TO THE RIGHT PLACE. The mated face lands ON the plate's top.
    seat = _underside_world_z(placement)
    assert abs(seat - SEAT_Z) < SOLVER_TOL, (
        f"the bracket's underside settled at z = {seat}, not on the plate's "
        f"top face at z = {SEAT_Z}"
    )

    # 3. THE RESULTING ASSEMBLY IS THE RIGHT SHAPE. The roll-up bbox is computed
    #    from the SOLVED placements, so this is the same claim read off a second,
    #    independent quantity: plate 0..6 with the bracket's 4 mm now stacked on
    #    top of it, not sunk through it.
    box = result.bounding_box
    assert box is not None
    assert abs(box.min.z - 0.0) < SOLVER_TOL, box.min.z
    assert abs(box.max.z - (SEAT_Z + BRACKET_H)) < SOLVER_TOL, (
        f"assembly spans z up to {box.max.z}; seated it must reach {SEAT_Z + BRACKET_H}"
    )

    # 4. THE FACES ARE FLUSH, not merely at the right height: the bracket is
    #    unrotated, so its underside is parallel to the plate's top.
    orientation = placement.orientation
    assert abs(abs(orientation.w) - 1.0) < SOLVER_TOL, orientation


def test_zero_mates_reproduces_the_reported_reading() -> None:
    """The CONTROL: the same assembly with no mate gives MATE-1's numbers exactly.

    ``under_constrained`` with ``remaining_dof`` 6 and the bracket at its seed —
    which is what the report described. Pinned here so the reading has a name:
    any future regression that silently drops the mate lands on these numbers,
    and the test above fails.
    """
    result = evaluate_assembly(_request(with_mate=False))

    assert result.diagnosis is not None
    assert result.diagnosis.remaining_dof == 6, (
        "an unmated free instance has all six rigid-body DOF; if this is not 6 "
        "the fixture has drifted and the control below proves nothing"
    )

    placement = _bracket_placement(result)
    assert placement.position.z == SEED_Z
    assert _underside_world_z(placement) == SEED_Z

    box = result.bounding_box
    assert box is not None
    assert abs(box.max.z - (SEED_Z + BRACKET_H)) < SOLVER_TOL


def test_the_mate_removes_three_degrees_of_freedom() -> None:
    """The mate is IN the system: it takes the bracket from 6 free DOF to 3.

    A coincident mate pins the along-normal translation and two rotations,
    leaving the two in-plane translations and the spin about the normal. Six
    remaining DOF on a mated instance means the constraint never entered the
    system at all — the distinction the report's ``Free DOF 6`` could not make.
    """
    mated = evaluate_assembly(_request(with_mate=True))
    control = evaluate_assembly(_request(with_mate=False))

    assert mated.diagnosis is not None
    assert control.diagnosis is not None
    assert control.diagnosis.remaining_dof == 6
    assert mated.diagnosis.remaining_dof == 3, (
        "the coincident mate must remove exactly three degrees of freedom; "
        f"got {mated.diagnosis.remaining_dof}"
    )


def test_status_alone_cannot_distinguish_the_two() -> None:
    """Why every assertion above is on the pose: the STATUS is identical.

    The solve that seats the bracket and the solve with no constraint at all
    both report ``under_constrained``. A gate keyed on the solve's own status
    therefore passes in a world where mates do nothing — which is precisely how
    a mate that did nothing came to be reported as solved.
    """
    mated = evaluate_assembly(_request(with_mate=True))
    control = evaluate_assembly(_request(with_mate=False))

    assert mated.status == control.status == "under_constrained"

    # ...while the geometry differs by the full 3 mm the mate is worth.
    seated = _underside_world_z(_bracket_placement(mated))
    unseated = _underside_world_z(_bracket_placement(control))
    assert abs(seated - unseated) > 1.0, (
        f"seated {seated} vs unmated {unseated}: the two solves are "
        "indistinguishable by pose as well, which would make this gate blind"
    )


def test_the_seated_pose_is_deterministic() -> None:
    """Same request in, identical pose out (RESEARCH §9).

    The pose this module asserts on is only a gate if it is reproducible; an
    under-constrained solve leaves a null space, and a non-deterministic walk
    through it would make every assertion above a coin flip.
    """
    first = _bracket_placement(evaluate_assembly(_request(with_mate=True)))
    second = _bracket_placement(evaluate_assembly(_request(with_mate=True)))
    assert first.model_dump() == second.model_dump()
