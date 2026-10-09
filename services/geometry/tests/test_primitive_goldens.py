"""The box and cylinder goldens are feature trees; the primitives still match them.

``box-10x20x30`` and ``cylinder-r10-h25`` were ``{shape, params}`` primitive
requests until 2026-10-09; they are now modelled the way an engineer models
them (a sketch, extruded), with every expected value unchanged. This module is
the proof, kept as a test: the primitive request the web's dimension form and
``/tessellate`` / ``/export`` still serve builds the SAME body as the golden
tree (empty two-way boolean difference, coincident vertices, identical topology
and mesh counts), and it meets the golden's own expected values within the
golden's own tolerance, so the primitive path keeps its tight assertions.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from build123d import Solid
from geometry.harness import build_model_solid, evaluate_model, load_model_request
from geometry.schemas import TessellateRequest

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"

#: The former golden models, kept as the parametric export inventory too.
PRIMITIVES_DIR = Path(__file__).resolve().parent / "fixtures" / "primitives"
PRIMITIVES = sorted(path.parent.name for path in PRIMITIVES_DIR.glob("*/model.json"))


def test_the_primitives_are_the_two_former_goldens() -> None:
    assert PRIMITIVES == ["box-10x20x30", "cylinder-r10-h25"]


def _vertices(body: Any) -> list[tuple[float, float, float]]:
    return sorted(
        (round(v.X, 9), round(v.Y, 9), round(v.Z, 9)) for v in body.vertices()
    )


@pytest.mark.parametrize("golden", PRIMITIVES)
def test_the_primitive_is_the_golden_tree_body(golden: str) -> None:
    tree = load_model_request((GOLDENS / golden / "model.json").read_text())
    assert not isinstance(tree, TessellateRequest), "golden must be a feature tree"
    primitive = load_model_request((PRIMITIVES_DIR / golden / "model.json").read_text())
    assert isinstance(primitive, TessellateRequest)

    tree_body = build_model_solid(tree)
    primitive_body = build_model_solid(primitive)
    assert isinstance(tree_body, Solid) and isinstance(primitive_body, Solid)
    assert tree_body.cut(primitive_body).volume == 0.0  # pyright: ignore[reportUnknownMemberType]
    assert primitive_body.cut(tree_body).volume == 0.0  # pyright: ignore[reportUnknownMemberType]
    assert _vertices(tree_body) == _vertices(primitive_body)

    _, tree_meta = evaluate_model(tree)
    _, primitive_meta = evaluate_model(primitive)
    assert primitive_meta.properties.topology == tree_meta.properties.topology
    assert primitive_meta.mesh.vertices == tree_meta.mesh.vertices
    assert primitive_meta.mesh.triangles == tree_meta.mesh.triangles

    expected = json.loads((GOLDENS / golden / "expected.json").read_text())
    tol = expected["tolerance"]
    props = primitive_meta.properties
    want = expected["properties"]
    assert props.volume == pytest.approx(want["volume"], abs=tol)
    assert props.surface_area == pytest.approx(want["surface_area"], abs=tol)
    for axis in ("x", "y", "z"):
        assert getattr(props.centroid, axis) == pytest.approx(
            want["centroid"][axis], abs=tol
        )
        for end in ("min", "max"):
            assert getattr(getattr(props.bounding_box, end), axis) == pytest.approx(
                want["bounding_box"][end][axis], abs=tol
            )
