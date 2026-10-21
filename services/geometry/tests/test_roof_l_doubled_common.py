"""ROOF-L-DOUBLED-COMMON acceptance: ``loft.roof`` 1.2.0 on an L whose wing
jacks reach the flush ridge-end common an ulp off it frames ONE common there.

``goldens/l-hip-16oc-v1.2-one-common`` is the plugin's 1.2.0 expansion on
six walls round the L (0, 51.1) (0, 144.8) (157, 144.8) (157, 0) (95.3, 0)
(95.3, 51.1), Style Hip, 6/12, 2x6 at 16 in o.c., 12 in overhang, plates at
97.125; ``fixtures/l-hip-16oc-v1.2-doubled.json.gz`` is the expansion 1.2.0
gave before the fix. Both are pinned to the plugin by
``packages/loft-plugins/tests/test_roof_l_doubled_common.py``; geometry never
learns plugins exist, so this module reads JSON only. Checked here:

1. before the fix two bodies were the same common (an overlap of the whole
   common); that common is an INDEPENDENT build123d script's (its plan prism
   cut to its plane's slab, less everything below the plate inside the
   walls), whose volume is the closed form 1.5 x (P x (30.1 + 12) - 3.5 x
   1.75 / 2) = 383.727405 in^3;
2. after it the roof is the same bodies less that one: one solid fewer and
   exactly that volume less, and no two bodies share any volume;
3. the cut list counts one Common fewer, every other line unchanged;
4. a Boolean that named the dropped twin is ``reference_unresolved`` on that
   twin (SolidWorks' dangling reference), never rebound to its survivor.
"""

import gzip
import itertools
import json
import math
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from build123d import (
    Box,
    Plane,
    Polygon,
    Pos,
    Solid,
    Vector,
    extrude,
)
from fastapi.testclient import TestClient
from geometry.harness import build_model_solid
from geometry.kernel import measure_shape
from geometry.kernel.interference import probe_overlap
from geometry.main import app
from loft_wire.cut_list import (
    BodyExtentsResult,
    CutListMember,
    cut_list_response,
    part_pieces,
)
from loft_wire.features import (
    BooleanFeature,
    BooleanParamsV1,
    EvaluatedFeatureInput,
    EvaluateTreeRequest,
    FeatureRef,
)
from loft_wire.plugins import member_id

client = TestClient(app)

NAME = "l-hip-16oc-v1.2-one-common"
GOLDEN = Path(__file__).resolve().parent.parent / "goldens" / NAME
FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "l-hip-16oc-v1.2-doubled.json.gz"
)
IN = 25.4
K = 0.5
PLATE = 97.125
SEAT = 3.5
PLUMB = 5.5 * math.hypot(12, 6) / 12  # 6.149187
TOP0 = PLATE + PLUMB - SEAT * K  # a plane's top at its wall's outer face
#: The walls' outer faces round the L.
FOOTPRINT = [(0, 51.1), (0, 144.8), (157, 144.8), (157, 0), (95.3, 0), (95.3, 51.1)]
#: The doubled common: the right wall's (X 157), centred on Y 81.95, from the
#: fascia (X 169) to the wing ridge's face (X 126.9): a 30.1 in run.
COMMON_IN3 = 1.5 * (PLUMB * (30.1 + 12) - SEAT * 1.75 / 2)
#: The twin's member id, ``member_id(roof, "common", 17)`` (the plugin test
#: pins it): its survivor is ``common/16``.
ROOF_ID = uuid.UUID("00000000-0000-0000-0000-0000000000f1")


def _golden() -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    request = EvaluateTreeRequest.model_validate_json(
        (GOLDEN / "model.json").read_text()
    )
    raw: list[dict[str, Any]] = json.loads((GOLDEN / "members.json").read_text())
    return request, [CutListMember.model_validate(item) for item in raw]


def _before() -> tuple[EvaluateTreeRequest, list[CutListMember]]:
    data = json.loads(gzip.decompress(FIXTURE.read_bytes()))
    return (
        EvaluateTreeRequest.model_validate(data["request"]),
        [CutListMember.model_validate(item) for item in data["members"]],
    )


def _solids(request: EvaluateTreeRequest) -> list[Solid]:
    return list(build_model_solid(request).solids())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


def _volume(shape: Any) -> float:
    return float(measure_shape(shape).volume) if shape else 0.0


def _prism(points: Sequence[tuple[float, float]], z0: float, h: float) -> Solid:
    polygon = Polygon(*[(x * IN, y * IN) for x, y in points], align=None)
    return Pos(0, 0, z0 * IN) * extrude(polygon, h * IN, dir=(0, 0, 1)).solid()


def script_common() -> Solid:
    """The right wall's common on Y 81.95, every coordinate typed here."""
    plan = [(126.9, 81.2), (169, 81.2), (169, 82.7), (126.9, 82.7)]
    normal = Vector(K, 0, 1).normalized()  # falls K per X toward the right wall
    top = Plane(origin=(157 * IN, 0, TOP0 * IN), z_dir=normal)
    thick = PLUMB * normal.Z * IN
    slab = (top.location * Pos(0, 0, -thick / 2) * Box(2e5, 2e5, thick)).solid()
    common = _prism(plan, -200, 600) & slab
    assert common is not None
    body = common - _prism(FOOTPRINT, -200, PLATE + 200)
    solids = list(body.solids())
    assert len(solids) == 1
    return solids[0]


def _overlaps(solids: Sequence[Solid]) -> list[tuple[int, int, float]]:
    """Pairs whose boxes overlap and that share volume, probed exactly."""
    boxes = [s.bounding_box() for s in solids]
    bad: list[tuple[int, int, float]] = []
    for i, j in itertools.combinations(range(len(solids)), 2):
        a, b = boxes[i], boxes[j]
        if all(
            min(getattr(a.max, k), getattr(b.max, k))
            - max(getattr(a.min, k), getattr(b.min, k))
            > 1e-6
            for k in ("X", "Y", "Z")
        ):
            probe = probe_overlap(solids[i], solids[j])
            if probe.unresolved or probe.volume_mm3 != 0.0:
                bad.append((i, j, probe.volume_mm3))
    return bad


def test_the_closed_form_is_b4s_common_formula() -> None:
    """B4's full common, run 59.25, is 652.600604 in^3 by the same formula."""
    assert pytest.approx(652.600604, abs=1e-6) == 1.5 * (
        PLUMB * (59.25 + 12) - SEAT * 1.75 / 2
    )
    assert pytest.approx(383.727405, abs=1e-6) == COMMON_IN3


def test_before_the_fix_two_bodies_were_the_scripts_common() -> None:
    before = _solids(_before()[0])
    common = script_common()
    assert _volume(common) / IN**3 == pytest.approx(COMMON_IN3, abs=1e-6)
    overlaps = _overlaps(before)
    assert len(overlaps) == 1
    i, j, shared = overlaps[0]
    assert shared / IN**3 == pytest.approx(COMMON_IN3, abs=1e-6)
    for k in (i, j):
        difference = _volume(before[k].cut(common)) + _volume(common.cut(before[k]))  # pyright: ignore[reportUnknownMemberType]
        assert difference < 1e-4, (k, difference)


def test_the_roof_frames_that_common_once() -> None:
    before = _solids(_before()[0])
    after = _solids(_golden()[0])
    assert len(after) == len(before) - 1 == 45
    assert _overlaps(after) == []
    lost = sum(_volume(s) for s in before) - sum(_volume(s) for s in after)
    assert lost / IN**3 == pytest.approx(COMMON_IN3, abs=1e-6)
    # The fixed roof still has the common there, once.
    common = script_common()
    matches = [
        s
        for s in after
        if _volume(s.cut(common)) + _volume(common.cut(s)) < 1e-4  # pyright: ignore[reportUnknownMemberType]
    ]
    assert len(matches) == 1


def _cut_list(request: EvaluateTreeRequest, members: list[CutListMember]) -> list[Any]:
    response = client.post(
        "/api/v1/bodies/extents", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    cut_list = cut_list_response(
        document_id=request.part_id,
        document_kind="part",
        name="L roof",
        length_unit="in",
        pieces=part_pieces(
            BodyExtentsResult.model_validate_json(response.content),
            members,
            request.materials,
        ),
    )
    return [
        (line.member, line.profile, line.quantity, round(line.length_mm / IN, 3))
        for line in cut_list.lines
    ]


def test_the_cut_list_counts_one_common_fewer() -> None:
    before = _cut_list(*_before())
    after = _cut_list(*_golden())
    assert len(after) == len(before)
    changed = [(b, a) for b, a in zip(before, after, strict=True) if b != a]
    assert len(changed) == 1
    (member, profile, quantity, length), new = changed[0]
    assert member == "Common" and profile == "2x6"
    # Its overall length: the 42.1 in run plus the overhang on the slope,
    # plus the plumb cut's rise: 42.1 x sqrt(180)/12 + 5.5 x 6/12.
    assert length == round(42.1 * math.hypot(12, 6) / 12 + 2.75, 3)
    assert new == (member, profile, quantity - 1, length)
    assert sum(row[2] for row in after) == sum(row[2] for row in before) - 1 == 45


def test_a_feature_on_the_twin_is_flagged_never_rebound() -> None:
    """A Boolean whose target was the twin (``common/17``) is
    ``reference_unresolved`` on it; the survivor (``common/16``, its tool
    here) is left whole, so nothing was rebound to it."""
    request, _ = _golden()
    twin = member_id(ROOF_ID, "common", 17)
    survivor = member_id(ROOF_ID, "common", 16)
    assert twin not in {f.id for f in request.features}
    assert survivor in {f.id for f in request.features}
    cut = EvaluatedFeatureInput(
        id=uuid.UUID("00000000-0000-0000-0000-00000000c0de"),
        feature=BooleanFeature(
            type="boolean",
            version=1,
            params=BooleanParamsV1(
                operation="subtract",
                target=FeatureRef(kind="feature", feature_id=twin),
                tool=FeatureRef(kind="feature", feature_id=survivor),
            ),
        ),
    )
    edited = request.model_copy(update={"features": [*request.features, cut]})
    response = client.post("/api/v1/evaluate", json=edited.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    body = response.json()
    last = body["features"][-1]
    assert last["status"] == "error"
    assert last["error"]["code"] == "reference_unresolved"
    assert last["error"]["upstream_feature_id"] == str(twin)
    assert [f for f in body["features"][:-1] if f["status"] == "error"] == []
    assert str(survivor) in {b["base_feature_id"] for b in body["bodies"]}
    assert len(body["bodies"]) == 45
