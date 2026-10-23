"""CRAWL-SPACE through documents: a Foundation under B7's floor.

B9 (docs/reference-parts/buildings.md): B7's 288 x 192 outline, its
``loft.floor`` 1.3.0 on it, then ``loft.foundation`` 1.0.0 on the outline
with Floor on it set to that floor. The floor is stored and built exactly as
before; the cut-list request carries two pours with their allowance, the
footing's two #4 loops and the stem's bolts for the floor's four sills; a
crawl under 18 in carries IRC R317.1's ``crawl_height_low`` warning and
still builds;
and the 288 dimension set to 336 re-lays the foundation in one write.
"""

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient
from loft_wire.cut_list import CutListMember, CutListPartRequest

sys.path.insert(0, str(Path(__file__).parent))
from test_slab_feature import (  # pyright: ignore[reportPrivateUsage]
    HEADERS,
    IN,
    _custom,  # pyright: ignore[reportPrivateUsage]
    _outline,  # pyright: ignore[reportPrivateUsage]
    _Part,  # pyright: ignore[reportPrivateUsage]
    _ref,  # pyright: ignore[reportPrivateUsage]
)


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    with TestClient(build_app(DocumentsSettings(postgres_url=any_db_url))) as c:
        yield c


def _b9(client: TestClient, **raw: Any) -> tuple[_Part, str, str, str]:
    part = _Part(client)
    sketch = part.add("Outline", _outline(288))
    floor = part.add(
        "Floor",
        _custom("loft.floor", "1.3.0", outline=_ref(sketch), joist_profile="us_2x10"),
    )
    foundation = part.add(
        "Foundation",
        _custom(
            "loft.foundation",
            "1.0.0",
            outline=_ref(sketch),
            floor=_ref(floor),
            **raw,
        ),
    )
    return part, sketch, floor, foundation


def _cut_list_request(client: TestClient, part: _Part) -> CutListPartRequest:
    response = client.get(f"/api/v1/parts/{part.id}/cut-list-request", headers=HEADERS)
    assert response.status_code == 200, response.text
    return CutListPartRequest.model_validate_json(response.content)


def _pours(request: CutListPartRequest) -> tuple[CutListMember, CutListMember]:
    """The footing's and the stem's members, a pour each."""
    footing, stem = [m for m in request.members if m.plugin_id == "loft.foundation"]
    assert (footing.role, stem.role) == ("footing", "stem")
    return footing, stem


def _warnings(client: TestClient, part: _Part, name: str) -> Any:
    response = client.get(f"/api/v1/parts/{part.id}/features", headers=HEADERS)
    assert response.status_code == 200, response.text
    (row,) = [f for f in response.json()["features"] if f["name"] == name]
    return row.get("plugin_warnings")


def test_the_stem_lists_its_pour_rebar_and_the_sills_bolts(client: TestClient) -> None:
    part, _, _, _ = _b9(client)
    stored = part.stored()["Foundation"]["params"]["inputs"]
    assert stored["crawl_height_mm"] == pytest.approx(24 * IN)
    assert stored["waste_percent"] == 5
    request = _cut_list_request(client, part)
    footing, stem = _pours(request)
    assert (footing.title, stem.title) == ("Footing", "Stem wall")
    for pour in (footing, stem):
        assert pour.metadata.concrete is not None
        assert pour.metadata.concrete.waste_percent == 5
    rebar = footing.metadata.rebar or []
    assert [round(r.length_mm / IN, 6) for r in rebar] == [968.0, 888.0]
    meta = stem.metadata
    assert meta.anchor_bolts is not None
    sills = [round(mm / IN, 6) for mm in meta.anchor_bolts.plates_mm or []]
    assert sills == [288.0, 288.0, 181.0, 181.0]
    assert meta.anchor_bolts.count(0.0) == 18
    # The floor's own members carry no bolts: loft.floor is unchanged.
    floor = [m for m in request.members if m.plugin_id == "loft.floor"]
    assert floor and not any(m.metadata.anchor_bolts for m in floor)
    # Five vents and one access, each a cut scoped to the stem's body.
    cuts = [
        e.feature
        for e in request.evaluation.features
        if e.feature.type == "extrude" and e.feature.params.operation == "cut"  # type: ignore[union-attr]
    ]
    assert len(cuts) == 6
    for cut in cuts:
        scope = cut.params.cut_bodies  # type: ignore[union-attr]
        assert isinstance(scope, list) and scope[0].feature_id == stem.feature_id
    assert _warnings(client, part, "Foundation") is None


def test_a_crawl_under_18_in_warns_and_builds(client: TestClient) -> None:
    part, _, _, _ = _b9(client, crawl_height_mm=17.5 * IN)
    (warning,) = _warnings(client, part, "Foundation")
    assert warning["code"] == "crawl_height_low"
    assert "17.5 in" in warning["message"] and "R317.1" in warning["message"]
    assert warning["update_to"] is None
    assert all(e.input_error is None for e in part.request().features)


def test_one_dimension_edit_re_lays_the_foundation(client: TestClient) -> None:
    part, sketch, _, _ = _b9(client)
    part.edit(sketch, _outline(336))
    request = _cut_list_request(client, part)
    footing, stem = _pours(request)
    rebar = footing.metadata.rebar or []
    assert [round(r.length_mm / IN, 6) for r in rebar] == [1064.0, 984.0]
    meta = stem.metadata
    assert meta.anchor_bolts is not None
    assert meta.anchor_bolts.count(0.0) == 20
    cuts = [
        e
        for e in request.evaluation.features
        if e.feature.type == "extrude" and e.feature.params.operation == "cut"  # type: ignore[union-attr]
    ]
    assert len(cuts) == 7  # six vents and the access
    assert all(e.input_error is None for e in part.request().features)


def test_a_floor_on_another_outline_is_refused(client: TestClient) -> None:
    part = _Part(client)
    sketch = part.add("Outline", _outline(288))
    other = part.add("Other", _outline(240))
    floor = part.add("Floor", _custom("loft.floor", "1.3.0", outline=_ref(other)))
    response = client.post(
        f"/api/v1/parts/{part.id}/features",
        json={
            "name": "Foundation",
            "feature": _custom(
                "loft.foundation", "1.0.0", outline=_ref(sketch), floor=_ref(floor)
            ),
            "expected_tree_version": part.version,
        },
        headers=HEADERS,
    )
    assert response.status_code == 422, response.text
    assert "same outline" in response.json()["error"]["message"]
