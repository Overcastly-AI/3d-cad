# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
"""EXTRUDE-SYMMETRIC: an extrude that reaches half its depth each side of the plane.

The golden ``extrude-cut-symmetric-pocket-offset-xz-40x40x20`` runs the
parametrized gates (mass properties, topology, determinism, STEP round trip).
This file adds what a golden cannot say, each against a number derived
outside the code under test:

* the moto frame's four cross tubes, sketched on the XZ ORIGIN plane and
  extruded symmetric 208, give the frame golden's volume (the backlog's
  acceptance), where the golden itself reaches them from an offset datum at
  y = +104 extruded one-sided;
* the symmetric cut golden against an independent build123d build;
* a symmetric extrude builds one solid whichever ``direction``; its faces are
  named like a one-sided extrude's, and the default leaves a stored
  extrude's dump alone (the caps' sides: test_extrude_symmetric_caps.py).
"""

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from build123d import Box, Location, Plane, Solid
from geometry.features import evaluate_tree
from geometry.features.naming_hooks import prism_names
from geometry.harness import load_model_request
from geometry.kernel import (
    build_profile_face,
    extrude_face,
    measure_shape,
    symmetric_start,
)
from geometry.kernel.naming import OpHistory, carry_names, face_name
from loft_wire.features import EvaluateTreeRequest, ExtrudeParamsV1, SketchFeature
from pydantic import ValidationError

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
FRAME = GOLDENS / "frame-moto-cradle-tube-od25.4-t1.6"
POCKET = GOLDENS / "extrude-cut-symmetric-pocket-offset-xz-40x40x20"

#: The frame's cross-tube sketches sit on this datum (XZ offset -104, y = +104).
CROSS_TUBE_DATUM = "00000000-0000-0000-0000-000000000004"


def _request(golden: Path) -> EvaluateTreeRequest:
    request = load_model_request((golden / "model.json").read_text(encoding="utf-8"))
    assert isinstance(request, EvaluateTreeRequest)
    return request


def _expected(golden: Path) -> dict[str, Any]:
    return json.loads((golden / "expected.json").read_text(encoding="utf-8"))


def _symmetric_frame() -> EvaluateTreeRequest:
    """The frame golden with each cross tube sketched on XZ and extruded symmetric."""
    data = _request(FRAME).model_dump(mode="json")
    sketches: set[str] = set()
    for item in data["features"]:
        params = item["feature"]["params"]
        if item["feature"]["type"] == "sketch" and params["plane"] == {
            "kind": "feature",
            "feature_id": CROSS_TUBE_DATUM,
        }:
            params["plane"] = {"kind": "datum_plane", "plane": "XZ"}
            sketches.add(item["id"])
    extrudes = 0
    for item in data["features"]:
        params = item["feature"]["params"]
        if item["feature"]["type"] == "extrude":
            assert params["profile"]["feature_id"] in sketches
            assert params["distance_mm"] == 208.0
            params["extent"] = "symmetric"
            # No geometry change while symmetric: `normal` would build the same.
            params["direction"] = "reverse"
            extrudes += 1
    assert extrudes == 4 and len(sketches) == 4
    return EvaluateTreeRequest.model_validate(data)


def test_moto_frame_cross_tubes_extruded_symmetric_from_xz_match_the_golden() -> None:
    expected = _expected(FRAME)
    evaluation = evaluate_tree(_symmetric_frame())
    assert all(r.status == "ok" for r in evaluation.result.features)
    assert evaluation.body is not None
    props = measure_shape(evaluation.body)
    tolerance = expected["tolerance"]
    assert props.volume == pytest.approx(
        expected["properties"]["volume"], abs=tolerance
    )
    assert props.centroid.x == pytest.approx(
        expected["properties"]["centroid"]["x"], abs=tolerance
    )
    assert props.centroid.y == pytest.approx(0.0, abs=tolerance)
    assert props.centroid.z == pytest.approx(
        expected["properties"]["centroid"]["z"], abs=tolerance
    )
    # The same solid as the one-sided golden build: the two-way difference is empty.
    golden_body = evaluate_tree(_request(FRAME)).body
    assert golden_body is not None
    assert float(evaluation.body.cut(golden_body).volume) <= tolerance
    assert float(golden_body.cut(evaluation.body).volume) <= tolerance


def _independent_pocket() -> Solid:
    """The pocket golden in plain build123d: a box minus a box.

    Block x, y in [-20, 20], z in [0, 20]; pocket x in [-5, 5], z in [15, 25]
    (clear of the top), y from 4 - 15 to 4 + 15 (the plane at y = +4, 30 whole).
    """
    block = Box(40, 40, 20).moved(Location((0, 0, 10)))
    pocket = Box(10, 30, 10).moved(Location((0, 4, 20)))
    solids = block.cut(pocket).solids()
    assert len(solids) == 1
    return solids[0]


def test_symmetric_cut_golden_matches_an_independent_build() -> None:
    expected = _expected(POCKET)
    evaluation = evaluate_tree(_request(POCKET))
    assert evaluation.body is not None
    independent = _independent_pocket()
    mine, theirs = measure_shape(evaluation.body), measure_shape(independent)
    tolerance = expected["tolerance"]
    assert theirs.volume == pytest.approx(
        expected["properties"]["volume"], abs=tolerance
    )
    assert mine.volume == pytest.approx(theirs.volume, abs=tolerance)
    assert mine.centroid.y == pytest.approx(theirs.centroid.y, abs=tolerance)
    assert mine.centroid.z == pytest.approx(theirs.centroid.z, abs=tolerance)
    assert float(evaluation.body.cut(independent).volume) <= tolerance
    assert float(independent.cut(evaluation.body).volume) <= tolerance


@pytest.mark.parametrize(
    ("extent", "direction", "volume"),
    [
        # One-sided along XZ's normal (-y): y in [-26, 4], clipped at -20 -> 24.
        ("one_side", "normal", 32000.0 - 10 * 5 * 24),
        # Against it: y in [4, 34], clipped at 20 -> 16.
        ("one_side", "reverse", 32000.0 - 10 * 5 * 16),
        # Symmetric, either sense: y in [-11, 19] -> 30.
        ("symmetric", "normal", 32000.0 - 10 * 5 * 30),
        ("symmetric", "reverse", 32000.0 - 10 * 5 * 30),
    ],
)
def test_symmetric_volume_is_direction_free_and_differs_from_one_side(
    extent: str, direction: str, volume: float
) -> None:
    data = _request(POCKET).model_dump(mode="json")
    cut = data["features"][-1]["feature"]["params"]
    assert cut["operation"] == "cut"
    cut["extent"], cut["direction"] = extent, direction
    evaluation = evaluate_tree(EvaluateTreeRequest.model_validate(data))
    assert evaluation.body is not None
    assert measure_shape(evaluation.body).volume == pytest.approx(volume, abs=1e-6)


def test_symmetric_prism_names_its_faces_like_a_one_sided_one() -> None:
    """Every face of the slid prism is named from the sketch: 4 sides, 2 caps.

    The naming hook rebuilds the sketch edges on the plane it is handed, so the
    symmetric path must hand it the SLID plane; given the sketch plane, no side
    edge would match and all four walls would go unnamed.
    """
    pocket = _request(POCKET).features[-2].feature
    assert isinstance(pocket, SketchFeature)
    entities = pocket.params.entities
    plane = Plane.XZ.offset(-4.0)
    face, slid = symmetric_start(build_profile_face(plane, entities), plane, 30.0)
    history = OpHistory()
    solid = extrude_face(face, slid, 30.0, False, history=history)
    feature = uuid.UUID(int=0x5E3)
    hook = prism_names(feature, history, slid, entities, region=False)
    carried = carry_names(solid, [], hook).face_names(solid)
    expected = {face_name(feature, f"side:p{i}") for i in range(1, 5)}
    expected |= {face_name(feature, "start"), face_name(feature, "end")}
    assert set(carried) == expected
    # Half the depth each side of the plane at y = +4 (XZ's normal is -y).
    box = solid.bounding_box()
    assert pytest.approx((4.0 - 15.0, 4.0 + 15.0)) == (box.min.Y, box.max.Y)


def test_one_side_is_absent_from_the_dump_and_twist_is_refused() -> None:
    ref = {"kind": "feature", "feature_id": CROSS_TUBE_DATUM}
    stored = {"profile": ref, "distance_mm": 5.0, "operation": "add"}
    one_side = ExtrudeParamsV1.model_validate({**stored, "extent": "one_side"})
    assert one_side.model_dump() == ExtrudeParamsV1.model_validate(stored).model_dump()
    assert "extent" not in one_side.model_dump(mode="json")
    with pytest.raises(ValidationError, match="symmetric"):
        ExtrudeParamsV1.model_validate(
            {**stored, "extent": "symmetric", "twist_angle_deg": 15.0}
        )


def test_plane_xz_normal_is_minus_y() -> None:
    """The derivation's premise: XZ's normal is -y, so `normal` runs to -y."""
    assert tuple(Plane.XZ.z_dir) == pytest.approx((0.0, -1.0, 0.0))
