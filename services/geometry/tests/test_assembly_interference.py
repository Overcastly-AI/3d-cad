"""Assembly interference/collision detection (``POST /api/v1/assembly/interference``).

The clash gate for the assembly pillar (BACKLOG P1; design ``assemblies.md`` §4):
pairwise ``BRepAlgoAPI_Common`` over the solved world-placed instance bodies →
a typed clash list ``[{instance_a, instance_b, overlap_volume_mm3}]``.

Requests are built programmatically from the committed plain-box golden
(``sketch-extrude-40x25x10`` — a 40x25x10 box at x∈[0,40], y∈[0,25], z∈[0,10]),
placed at authored offsets whose overlap volume is computed BY HAND, so the
measured overlap is checked against an analytic value, not a self-consistent
snapshot. Covers the four acceptance cases: empty (nothing to pair /
non-overlapping → ``clashes: []``), a real clash with analytic volume, a
repeated-part clash (three instances of one part), and a just-touching
(coincident-face, zero-volume) pair that must NOT report a clash.
"""

from __future__ import annotations

import math
import uuid
from pathlib import Path

import numpy as np
import pytest
from build123d import Solid
from fastapi.testclient import TestClient
from geometry.assembly import check_interference
from geometry.assembly.transform import Pose
from geometry.kernel.interference import CLASH_VOLUME_FLOOR_MM3
from geometry.main import app
from py_kit.schemas.assemblies import (
    EvaluateAssemblyRequest,
    EvaluatedInstance,
    InterferenceResult,
    Placement,
    Quat,
)
from py_kit.schemas.features import EvaluatedFeatureInput, EvaluateTreeRequest
from py_kit.schemas.geometry import Vec3

client = TestClient(app)

_BOX_MODEL = (
    Path(__file__).resolve().parent.parent
    / "goldens/sketch-extrude-40x25x10/model.json"
)

#: The plain box's extents (mm): x∈[0,40], y∈[0,25], z∈[0,10] (extruded +Z).
BOX_X, BOX_Y, BOX_Z = 40.0, 25.0, 10.0

#: Overlap volumes are the exact intersection of two axis-aligned PLANAR boxes,
#: so ``BRepAlgoAPI_Common`` + GProp integrate them analytically. This relative
#: bound is a ceiling for OCCT boolean/GProp round-off on planar solids at
#: kernel precision (the placements are exact), NOT a fitted epsilon.
OVERLAP_REL_TOL = 1e-6

_PART_KEY = "box@1"


def iid(n: int) -> uuid.UUID:
    return uuid.UUID(int=n)


def _box_features() -> list[EvaluatedFeatureInput]:
    """The committed 40x25x10 plain-box part's ordered feature list."""
    return EvaluateTreeRequest.model_validate_json(
        _BOX_MODEL.read_text(encoding="utf-8")
    ).features


def _instance(n: int, x: float, y: float = 0.0, z: float = 0.0) -> EvaluatedInstance:
    """One grounded box instance translated to ``(x, y, z)`` (no rotation).

    Grounded + no mates ⇒ the solve keeps every instance at its authored seed, so
    the world placement equals the offset here — the clash geometry is exactly
    the hand-computed box overlap.
    """
    return EvaluatedInstance(
        instance_id=iid(n),
        part_key=_PART_KEY,
        features=_box_features(),
        placement=Placement(position=Vec3(x=x, y=y, z=z)),
        grounded=True,
    )


#: A committed MULTI-LUMP (Compound) part: two disjoint 20x20x20 cubes — cube A
#: at x∈[0,20] and cube B at x∈[30,50], both y∈[0,20], z∈[0,20]. Used to prove
#: the pairwise ``Common`` sums the overlap across BOTH lumps of a part instance.
_MULTI_MODEL = (
    Path(__file__).resolve().parent.parent
    / "goldens/multibody-two-disjoint-boxes/model.json"
)


def _multi_features() -> list[EvaluatedFeatureInput]:
    """The committed two-disjoint-cubes multi-body part's ordered feature list."""
    return EvaluateTreeRequest.model_validate_json(
        _MULTI_MODEL.read_text(encoding="utf-8")
    ).features


def _rotated_instance(
    n: int,
    quat: tuple[float, float, float, float],
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
) -> EvaluatedInstance:
    """One grounded box instance at ``(x, y, z)`` with an authored orientation.

    Grounded + no mates ⇒ the solve returns the authored seed verbatim, so this
    exercises the rotated ``place_body`` path (``world = R(q)·local + t``) on
    exactly the pose the clash check sees — the part of the pipeline the shipped
    identity/translation-only tests never touch.
    """
    qx, qy, qz, qw = quat
    return EvaluatedInstance(
        instance_id=iid(n),
        part_key=_PART_KEY,
        features=_box_features(),
        placement=Placement(
            position=Vec3(x=x, y=y, z=z),
            orientation=Quat(x=qx, y=qy, z=qz, w=qw),
        ),
        grounded=True,
    )


def _multi_instance(n: int, x: float, y: float, z: float) -> EvaluatedInstance:
    """One grounded instance of the two-disjoint-cubes multi-lump part."""
    return EvaluatedInstance(
        instance_id=iid(n),
        part_key="multibody@1",
        features=_multi_features(),
        placement=Placement(position=Vec3(x=x, y=y, z=z)),
        grounded=True,
    )


def _request(*instances: EvaluatedInstance) -> EvaluateAssemblyRequest:
    return EvaluateAssemblyRequest(
        assembly_id=iid(1000), version=1, instances=list(instances), mates=[]
    )


def _clash_between(result: InterferenceResult, a: int, b: int) -> float | None:
    """The overlap volume of the (a, b) pair, or ``None`` if not reported."""
    want = {iid(a), iid(b)}
    for clash in result.clashes:
        if {clash.instance_a, clash.instance_b} == want:
            return clash.overlap_volume_mm3
    return None


def test_single_instance_has_nothing_to_clash() -> None:
    """One instance → no pairs → empty clash list (the trivial empty case)."""
    result = check_interference(_request(_instance(1, x=0.0)))
    assert result.clashes == []
    assert result.assembly_id == iid(1000)
    assert result.version == 1


def test_non_overlapping_pair_reports_no_clash() -> None:
    """Two boxes with a 10 mm gap (B at x=50, box ends at x=40) → clashes []."""
    result = check_interference(_request(_instance(1, x=0.0), _instance(2, x=50.0)))
    assert result.clashes == []


def test_overlapping_pair_matches_analytic_volume() -> None:
    """B translated +30 in x → overlap box 10x25x10 = 2500 mm³ (hand-computed).

    A at x∈[0,40], B at x∈[30,70]; the overlap is x∈[30,40] (10 mm) x the full
    25 mm depth x 10 mm height = 2500 mm³. The measured B-rep common volume must
    match that analytic value within ``OVERLAP_REL_TOL``.
    """
    result = check_interference(_request(_instance(1, x=0.0), _instance(2, x=30.0)))
    assert len(result.clashes) == 1
    overlap_x = BOX_X - 30.0  # 10 mm
    analytic = overlap_x * BOX_Y * BOX_Z  # 10 * 25 * 10 = 2500 mm³
    assert analytic == 2500.0  # guards the hand computation itself
    measured = _clash_between(result, 1, 2)
    assert measured is not None
    assert measured == pytest.approx(analytic, rel=OVERLAP_REL_TOL)


def test_repeated_part_clash_pairs_correctly() -> None:
    """Three instances of ONE part: A∩B clash, C isolated → exactly one pair.

    A at x=0, B at x=30 (overlaps A by 2500 mm³), C at x=100 (box x∈[100,140],
    clear of both). Dedup evaluates the part once but the pairwise scan must
    still treat all three placements independently: exactly the (A, B) clash,
    reported ONCE, with the correct analytic volume — never a self-pair, never a
    C clash, never a double-listed (B, A).
    """
    result = check_interference(
        _request(_instance(1, x=0.0), _instance(2, x=30.0), _instance(3, x=100.0))
    )
    assert len(result.clashes) == 1
    measured = _clash_between(result, 1, 2)
    assert measured is not None
    assert measured == pytest.approx(2500.0, rel=OVERLAP_REL_TOL)
    assert _clash_between(result, 1, 3) is None
    assert _clash_between(result, 2, 3) is None


def test_just_touching_coincident_face_is_not_a_clash() -> None:
    """B at x=40 shares the x=40 face with A (zero-volume contact) → no clash.

    A at x∈[0,40], B at x∈[40,80] meet exactly at the plane x=40: the B-rep
    common has no interior (zero volume), well below the kernel-tolerance clash
    floor, so a just-touching pair is NOT reported as interfering.
    """
    result = check_interference(_request(_instance(1, x=0.0), _instance(2, x=BOX_X)))
    assert result.clashes == []
    # The floor is one kernel-tolerance cube (1e-12 mm³) — a sanity anchor that
    # the guard is principled, not an ad-hoc epsilon.
    assert pytest.approx(1e-12) == CLASH_VOLUME_FLOOR_MM3


def test_endpoint_returns_clash_list() -> None:
    """The HTTP route returns the same typed clash list (never-500 envelope)."""
    request = _request(_instance(1, x=0.0), _instance(2, x=30.0))
    response = client.post(
        "/api/v1/assembly/interference", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200
    result = InterferenceResult.model_validate(response.json())
    assert len(result.clashes) == 1
    assert result.clashes[0].overlap_volume_mm3 == pytest.approx(
        2500.0, rel=OVERLAP_REL_TOL
    )


# --- geometry-QA guard tests (2026-07-23, commit e46db16 adversarial pass) ------
# The shipped suite exercised only axis-aligned boxes at identity/translation, so
# the rotated placement path, multi-lump parts, N>2 completeness, thin-but-real
# interpenetration, and determinism were UNCOVERED. These lock in the numbers a
# geometry-QA probe measured against hand-derived analytics; a transpose/order
# regression in the shared place_body, a dropped clash, or a lump missed by
# Common all fail here. Test-code only (geometry-qa territory).

#: 90° rotation about +Z as a unit quaternion (x, y, z, w).
_Q90Z = (0.0, 0.0, math.sin(math.pi / 4), math.cos(math.pi / 4))


def test_rotated_placement_matches_analytic_and_catches_transpose() -> None:
    """B rotated +90° about Z then +30 in x → analytic 6250 mm³ overlap.

    THE highest-value adversarial check: the box (local x∈[0,40], y∈[0,25],
    z∈[0,10]) under a correct +90° Z rotation maps local (lx, ly) → (-ly, lx),
    so B spans x∈[-25,0], y∈[0,40] before the +30 x-shift → x∈[5,30], y∈[0,40],
    z∈[0,10]. Overlap with A (x∈[0,40], y∈[0,25], z∈[0,10]) is x∈[5,30] (25) x
    y∈[0,25] (25) x z (10) = 6250 mm³ — hand-derived, exact.

    Discriminator: a transposed/inverted rotation in ``place_body`` (applying
    R(q)ᵀ = the -90° rotation) would map the box to x∈[30,55], y∈[-40,0] → ZERO
    overlap with A, i.e. no clash. Reporting 6250 mm³ proves the shared
    quaternion→gp_Trsf transform's handedness/order is correct on the clash path.
    Measured 2026-07-23 (build123d 0.11.1 / OCCT 7.9): 6250.0 exactly.
    """
    result = check_interference(
        _request(_instance(1, x=0.0), _rotated_instance(2, _Q90Z, x=30.0))
    )
    assert len(result.clashes) == 1
    measured = _clash_between(result, 1, 2)
    assert measured is not None
    assert measured == pytest.approx(6250.0, rel=OVERLAP_REL_TOL)


def test_non_axis_aligned_rotation_preserves_overlap_volume() -> None:
    """Rigid-invariance under a tilted (non-axis-aligned) quaternion → 2500 mm³.

    Both instances share a rotation about the (1,1,1) body diagonal (a genuinely
    non-axis-aligned quaternion), and B's translation is that SAME rotation
    applied to the (30, 0, 0) offset that yields the shipped 2500 mm³ overlap.
    Rotating a rigid pair about the origin cannot change the volume of their
    intersection, so the measured overlap must stay 2500 mm³. A rotation that
    silently dropped/reordered a component (a bug the axis-aligned tests can't
    see) would perturb the shared body relative to B and shift the volume.
    Measured 2026-07-23: 2500.000000000001 (err 9.1e-13 mm³, ≪ rel-tol 1e-6).
    """
    ang = math.radians(37.0)
    s = math.sin(ang / 2.0) / math.sqrt(3.0)
    qt = (s, s, s, math.cos(ang / 2.0))
    # Rotate the (30,0,0) seed offset by the SAME orientation (reusing the shared
    # transform), so the pair is a rigid rotation of the un-rotated 2500 case.
    rot = Pose.from_placement(
        Placement(
            position=Vec3(x=0.0, y=0.0, z=0.0),
            orientation=Quat(x=qt[0], y=qt[1], z=qt[2], w=qt[3]),
        )
    ).matrix()
    offset = rot @ np.array([30.0, 0.0, 0.0])
    result = check_interference(
        _request(
            _rotated_instance(1, qt),
            _rotated_instance(
                2, qt, x=float(offset[0]), y=float(offset[1]), z=float(offset[2])
            ),
        )
    )
    assert len(result.clashes) == 1
    measured = _clash_between(result, 1, 2)
    assert measured is not None
    assert measured == pytest.approx(2500.0, rel=OVERLAP_REL_TOL)


def test_thin_but_real_interpenetration_is_reported() -> None:
    """A 0.001 mm interpenetration on the 25x10 face (0.25 mm³) IS a clash.

    B shifted so it overlaps A by 0.001 mm in x → 0.001 x 25 x 10 = 0.25 mm³,
    ten orders of magnitude above the 1e-12 mm³ floor and an order of magnitude
    above the kernel linear tolerance (1e-4 mm) in depth: a genuine, resolvable
    interference that must NOT be swallowed by the floor. Measured 2026-07-23:
    0.24999999999941733 mm³. Guards against the floor being widened to hide real
    thin overlaps.
    """
    result = check_interference(
        _request(_instance(1, x=0.0), _instance(2, x=BOX_X - 0.001))
    )
    assert len(result.clashes) == 1
    measured = _clash_between(result, 1, 2)
    assert measured is not None
    assert measured == pytest.approx(0.25, rel=1e-3)
    assert measured > CLASH_VOLUME_FLOOR_MM3


def test_multi_lump_part_sums_overlap_across_both_lumps() -> None:
    """A box overlapping BOTH cubes of a two-lump part → summed 4500 mm³.

    The multi-lump part is cube A (x∈[0,20]) + cube B (x∈[30,50]), both
    y∈[0,20], z∈[0,20]. A 40x25x10 box placed at (10, 5, 5) spans x∈[10,50],
    y∈[5,30], z∈[5,15] and pierces BOTH cubes: overlap with A = x∈[10,20] (10) x
    y∈[5,20] (15) x z∈[5,15] (10) = 1500 mm³; with B = x∈[30,50] (20) x 15 x 10 =
    3000 mm³. ``BRepAlgoAPI_Common`` over the Compound must integrate BOTH lumps →
    1500 + 3000 = 4500 mm³. A version that measured only the first solid of the
    common would report 1500 (or 3000) and fail. Measured 2026-07-23: 4500.0.
    """
    result = check_interference(
        _request(
            _multi_instance(1, x=0.0, y=0.0, z=0.0), _instance(2, x=10.0, y=5.0, z=5.0)
        )
    )
    assert len(result.clashes) == 1
    measured = _clash_between(result, 1, 2)
    assert measured is not None
    assert measured == pytest.approx(4500.0, rel=OVERLAP_REL_TOL)


def test_four_instances_report_every_clashing_pair_once() -> None:
    """4 instances, 3 simultaneous clashes → all three reported, each once.

    A@x=0, B@x=30, C@x=35, D@x=200. Pairs and hand-derived overlaps:
      (A,B) x∈[30,40] → 10x25x10 = 2500 mm³
      (A,C) x∈[35,40] → 5x25x10 = 1250 mm³
      (B,C) x∈[35,70] → 35x25x10 = 8750 mm³
    D is clear of all. The O(N²) scan must report EXACTLY these three, each once,
    never a D pair, never a self-pair, never a duplicate. Measured 2026-07-23:
    the three volumes to <1e-6 rel. Guards N-pairwise completeness.
    """
    result = check_interference(
        _request(
            _instance(1, x=0.0),
            _instance(2, x=30.0),
            _instance(3, x=35.0),
            _instance(4, x=200.0),
        )
    )
    assert len(result.clashes) == 3
    assert _clash_between(result, 1, 2) == pytest.approx(2500.0, rel=OVERLAP_REL_TOL)
    assert _clash_between(result, 1, 3) == pytest.approx(1250.0, rel=OVERLAP_REL_TOL)
    assert _clash_between(result, 2, 3) == pytest.approx(8750.0, rel=OVERLAP_REL_TOL)
    # D (instance 4) touches nothing.
    assert _clash_between(result, 1, 4) is None
    assert _clash_between(result, 2, 4) is None
    assert _clash_between(result, 3, 4) is None


def test_clash_list_is_deterministic_across_repeated_calls() -> None:
    """Repeated solves of one request → byte-identical ordering AND volumes.

    Ordering must follow the fixed request-instance pair order and every overlap
    volume must be bit-identical run to run (RESEARCH §9 determinism), including
    a rotated pair. A cross-interpreter run of this same graph (geometry-QA
    2026-07-23) produced the identical (1,2)=6250.0 / (1,3)=1249.9999999999998,
    so the in-process equality here stands in for the restart guarantee.
    """
    request = _request(
        _instance(1, x=0.0),
        _rotated_instance(2, _Q90Z, x=30.0),
        _instance(3, x=35.0),
        _instance(4, x=200.0),
    )
    baseline = [
        (c.instance_a, c.instance_b, c.overlap_volume_mm3)
        for c in check_interference(request).clashes
    ]
    for _ in range(2):
        again = [
            (c.instance_a, c.instance_b, c.overlap_volume_mm3)
            for c in check_interference(request).clashes
        ]
        # Exact equality (not approx): determinism means identical bytes.
        assert again == baseline


# --- robustness guard: a boolean FAILURE must never be reported as "clear" ------
# code-review 🟡 (e46db16): BRepAlgoAPI_Common can RAISE on two deeply
# interpenetrating solids (an OCCT robustness limit), sharing an exception surface
# with a harmless grazing degeneracy. The old `except Exception: return 0.0`
# swallowed both to zero overlap → a false "no clash" for parts that physically
# collide (the DANGEROUS direction for a collision check). The fix falls back to a
# robust solved-world AABB-overlap test: disjoint AABBs stay no-clash; overlapping
# AABBs surface the pair as `unresolved`, never hidden as clear. These force the
# exception path (monkeypatching the exact boolean to raise) so the AABB fallback
# and the assembly surfacing run for real.


def _forced_boolean_failure(*_args: object, **_kwargs: object) -> object:
    """Stand-in for ``Shape.intersect`` that raises like an OCCT robustness fault."""
    raise RuntimeError("forced BRepAlgoAPI_Common robustness failure")


def test_boolean_failure_on_overlapping_bodies_is_surfaced_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exact boolean RAISES on a deeply overlapping pair → an `unresolved` clash.

    A at x∈[0,40], B at x∈[30,70] deeply interpenetrate. With the exact
    ``Common`` forced to raise (the robustness fault this guards), the pair must
    NOT vanish to "clear": the AABB fallback sees the boxes overlap and the pair
    is reported with ``unresolved=True`` and the AABB-overlap magnitude hint
    (10x25x10 = 2500 mm³ for these axis-aligned boxes). This is the dangerous
    false-negative the fix closes.
    """
    monkeypatch.setattr(Solid, "intersect", _forced_boolean_failure)
    result = check_interference(_request(_instance(1, x=0.0), _instance(2, x=30.0)))
    assert len(result.clashes) == 1
    clash = result.clashes[0]
    assert clash.unresolved is True
    assert {clash.instance_a, clash.instance_b} == {iid(1), iid(2)}
    # The magnitude hint is the overlapping-AABB volume, not an exact common.
    assert clash.overlap_volume_mm3 == pytest.approx(2500.0, rel=OVERLAP_REL_TOL)


def test_boolean_failure_on_disjoint_bodies_stays_no_clash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exact boolean RAISES on a non-overlapping pair → genuinely no clash.

    A at x∈[0,40], B at x∈[50,90] have a 10 mm gap, so their bounding boxes are
    disjoint and a real interference is geometrically impossible. Even with the
    boolean forced to raise, the AABB fallback resolves this to "no clash" — the
    grazing/degenerate case must stay clear, not spuriously flag.
    """
    monkeypatch.setattr(Solid, "intersect", _forced_boolean_failure)
    result = check_interference(_request(_instance(1, x=0.0), _instance(2, x=50.0)))
    assert result.clashes == []


def test_probe_overlap_tri_state_resolved_vs_forced_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Directly lock the kernel probe's tri-state on one deeply-overlapping pair.

    Two identical boxes offset +30 in x (real overlap 2500 mm³). The RESOLVED
    probe carries the exact volume with no failure flags. When the exact boolean
    is forced to raise, the SAME pair (overlapping AABBs) comes back
    ``unresolved`` + ``boolean_failed`` with the positive AABB hint — never a
    false 0.0. The hint is >= the true overlap (the AABB bounds it from above),
    the SAFE direction for a collision check.
    """
    from geometry.kernel.export import place_body
    from geometry.kernel.interference import probe_overlap
    from geometry.kernel.shapes import build_box

    box = build_box(40.0, 25.0, 10.0)
    a = place_body(box, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))
    b = place_body(box, (30.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))

    resolved = probe_overlap(a, b)
    assert resolved.unresolved is False
    assert resolved.boolean_failed is False
    assert resolved.volume_mm3 == pytest.approx(2500.0, rel=OVERLAP_REL_TOL)

    monkeypatch.setattr(Solid, "intersect", _forced_boolean_failure)
    failed = probe_overlap(a, b)
    assert failed.boolean_failed is True
    assert failed.unresolved is True
    assert failed.volume_mm3 >= resolved.volume_mm3  # AABB hint bounds from above
