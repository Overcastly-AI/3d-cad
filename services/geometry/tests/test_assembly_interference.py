"""Assembly interference/collision detection (``POST /api/v1/assembly/interference``).

The clash gate for the assembly pillar (BACKLOG P1; design ``assemblies.md`` §4):
pairwise ``BRepAlgoAPI_Common`` over the solved world-placed instance bodies →
a typed clash list ``[{instance_a, instance_b, overlap_volume_mm3}]``.

Requests are built programmatically from the committed plain-box golden
(``sketch-extrude-40x25x10`` — a 40×25×10 box at x∈[0,40], y∈[0,25], z∈[0,10]),
placed at authored offsets whose overlap volume is computed BY HAND, so the
measured overlap is checked against an analytic value, not a self-consistent
snapshot. Covers the four acceptance cases: empty (nothing to pair /
non-overlapping → ``clashes: []``), a real clash with analytic volume, a
repeated-part clash (three instances of one part), and a just-touching
(coincident-face, zero-volume) pair that must NOT report a clash.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from geometry.assembly import check_interference
from geometry.kernel.interference import CLASH_VOLUME_FLOOR_MM3
from geometry.main import app
from py_kit.schemas.assemblies import (
    EvaluateAssemblyRequest,
    EvaluatedInstance,
    InterferenceResult,
    Placement,
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
    """The committed 40×25×10 plain-box part's ordered feature list."""
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
    """B translated +30 in x → overlap box 10×25×10 = 2500 mm³ (hand-computed).

    A at x∈[0,40], B at x∈[30,70]; the overlap is x∈[30,40] (10 mm) × the full
    25 mm depth × 10 mm height = 2500 mm³. The measured B-rep common volume must
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
    assert CLASH_VOLUME_FLOOR_MM3 == pytest.approx(1e-12)


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
