# pyright: reportPrivateUsage=false
"""A roof 1.9.0 with Roofing picked on eaves with no overhang warns (ROOFING).

The fascia hangs on the rafter tails, so a gable cut flush at its walls
takes no roofing. Asphalt shingles picked on such a gable is not dropped
silently: the stored roof carries ``roof_roofing_no_overhang``, which says
to give the eaves an overhang, and still builds (advice, never a refusal),
as a wall's ``wall_finish_no_sheathing`` does. A roof with an overhang, at
the default None, or at 1.8.0 (no Roofing input) carries no such warning.
"""

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from documents.main import DocumentsSettings, build_app
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent))
from test_building_outline import (
    IN,
    _custom,
    _outline,
    _Part,
    _ref,
)


@pytest.fixture
def client(any_db_url: str) -> Iterator[TestClient]:
    with TestClient(build_app(DocumentsSettings(postgres_url=any_db_url))) as c:
        yield c


def _roof(client: TestClient, version: str, **inputs: Any) -> dict[str, Any]:
    """B7's outline, floor and sheathed 2x6 walls, then its gable at
    *version* with *inputs*; the roof's stored row."""
    part = _Part(client)
    sketch = part.add("Outline", _outline(288))
    floor = part.add(
        "Floor",
        _custom("loft.floor", "1.3.0", outline=_ref(sketch), joist_profile="us_2x10"),
    )
    walls = part.add(
        "Walls",
        _custom(
            "loft.wall",
            "1.5.0",
            outline=_ref(sketch),
            floor=_ref(floor),
            stud_profile="us_2x6",
            sheathing="osb_7_16",
        ),
    )
    part.add(
        "Roof",
        _custom(
            "loft.roof",
            version,
            walls=[_ref(walls)],
            slope_walls=["e1", "e3"],
            rafter_profile="us_2x8",
            ridge_profile="us_2x10",
            **inputs,
        ),
    )
    return part.rows()["Roof"]


def test_roofing_on_a_flush_eave_warns_and_builds(client: TestClient) -> None:
    roof = _roof(client, "1.9.0", roofing="asphalt_shingles", overhang_mm=0.0)
    (warning,) = roof["plugin_warnings"]
    assert warning["code"] == "roof_roofing_no_overhang"
    assert "no roofing without rafter tails" in warning["message"]
    assert "give the eaves an overhang" in warning["message"]
    assert warning["update_to"] is None
    assert (warning["overlap_in3"], warning["pairs"]) == (0.0, 0)
    roles = {m["role"] for m in roof["feature"]["params"]["expansion"]}
    assert "rafter" in roles and "deck" not in roles


@pytest.mark.parametrize(
    ("version", "inputs"),
    [
        ("1.9.0", {"roofing": "asphalt_shingles", "overhang_mm": 12 * IN}),
        ("1.9.0", {"overhang_mm": 0.0}),  # Roofing None, the default
        ("1.8.0", {"overhang_mm": 0.0}),
    ],
)
def test_no_warning_when_roofed_or_unasked(
    client: TestClient, version: str, inputs: dict[str, Any]
) -> None:
    roof = _roof(client, version, **inputs)
    assert roof.get("plugin_warnings") is None
