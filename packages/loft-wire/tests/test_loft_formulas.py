"""``.loft`` 1.2: parameters and formulas in every tree (RESEARCH §20).

``golden-v1.2.loft`` is FROZEN: a parametric part exported by the real chain
(services/gateway/tests/test_loft_parametric_chain.py, which wrote it once and
re-drives it). Here, without a kernel:

* read -> pack gives the fixture's bytes back;
* ``tree.json`` and the version tree carry ``parameters``, feature
  ``expressions`` and ``dimension_expressions``, and a sketch formula that
  names a parameter is out of the dimension, whose number stands;
* what a 1.1 reader keeps (the three keys ignored) is numbers and formulas
  over a sketch's own dimensions only, which every Loft evaluates;
* a ``dimension_expressions`` entry that does not fit its sketch is refused.
"""

import copy
import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from loft_wire.feature_expressions import outside_dimension_names
from loft_wire.loft_file import (
    BODY_STEP_PATH,
    TREE_PATH,
    LoftFileError,
    LoftTree,
    encode_tree,
    pack_part,
    read_loft,
)
from loft_wire.loft_formulas import move_out
from loft_wire.sketch import SketchDefinition

GOLDEN = Path(__file__).parent / "fixtures" / "golden-v1.2.loft"
WIDTH = "/constraints/9/expression"


def _members(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def _rezip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _raw_tree(member: str = TREE_PATH) -> Any:
    return json.loads(_members(GOLDEN.read_bytes())[member])


def test_the_1_2_fixture_repacks_byte_for_byte() -> None:
    original = GOLDEN.read_bytes()
    archive = read_loft(original)
    assert archive.manifest.format_version == "1.2"
    assert archive.warnings == ()
    repacked = pack_part(
        document_id=archive.manifest.document_id,
        tree=archive.tree,
        loft_version=archive.manifest.loft_version,
        body_step=_members(original)[BODY_STEP_PATH],
        properties=archive.cache.properties if archive.cache else None,
        versions=archive.versions,
    )
    assert repacked == original


def test_the_trees_carry_the_table_and_the_formulas() -> None:
    for member, width in (("tree.json", 50.0), ("versions/1.tree.json", 40.0)):
        raw = _raw_tree(member)
        assert [(p["name"], p["value"]) for p in raw["parameters"]] == [
            ("W", width),
            ("D", 5.0),
        ]
        sketch, extrude = raw["features"]
        assert extrude["expressions"] == {"/distance_mm": "D * 2"}
        assert extrude["params"]["distance_mm"] == 10.0
        assert sketch["dimension_expressions"] == {WIDTH: "W"}
        dims = [c for c in sketch["params"]["constraints"] if "value_mm" in c]
        assert [(d["expression"], d["value_mm"]) for d in dims] == [
            (None, width),
            ("width / 2", width / 2),
        ]

    archive = read_loft(GOLDEN.read_bytes())
    for tree in (archive.tree, archive.versions[0].tree):
        sketch = tree.features[0]
        assert "dimension_expressions" not in sketch.model_dump()
        assert sketch.params["constraints"][9]["expression"] == "W"
        assert tree.features[1].expressions == {"/distance_mm": "D * 2"}


def test_a_1_1_reader_keeps_numbers_and_sketch_own_formulas_only() -> None:
    """The keys 1.2 added, ignored as ``extra="ignore"`` ignores them: no
    formula is left that names anything outside its sketch, so a Loft from
    before parameters (whose sketch formulas see only the sketch) rebuilds
    the resolved numbers."""
    for member in ("tree.json", "versions/1.tree.json"):
        raw = _raw_tree(member)
        raw.pop("parameters")
        for feature in raw["features"]:
            feature.pop("expressions", None)
            feature.pop("dimension_expressions", None)
        tree = LoftTree.model_validate(raw)
        sketch = SketchDefinition.model_validate(tree.features[0].params)
        feature = SimpleNamespace(type="sketch", params=sketch)
        assert outside_dimension_names(feature) == {}


def test_a_sketch_formula_over_its_own_dimensions_stays_put() -> None:
    raw = _raw_tree()
    sketch = raw["features"][0]
    sketch.pop("dimension_expressions")
    assert move_out(sketch) is sketch  # nothing names a parameter
    sketch["params"]["constraints"][9]["expression"] = "W"
    moved = move_out(sketch)
    assert moved["dimension_expressions"] == {WIDTH: "W"}
    assert moved["params"]["constraints"][9]["expression"] is None
    assert moved["params"]["constraints"][10]["expression"] == "width / 2"
    assert sketch["params"]["constraints"][9]["expression"] == "W"  # not mutated


def test_encoding_a_read_tree_gives_the_member_back() -> None:
    members = _members(GOLDEN.read_bytes())
    archive = read_loft(GOLDEN.read_bytes())
    assert encode_tree(archive.tree)[0] == members[TREE_PATH]
    assert encode_tree(archive.versions[0].tree)[0] == members["versions/1.tree.json"]


def _with_tree(edit: Any) -> bytes:
    members = _members(GOLDEN.read_bytes())
    raw = json.loads(members[TREE_PATH])
    edit(raw)
    members[TREE_PATH] = json.dumps(raw).encode()
    return _rezip(members)


def _set_formulas(value: Any, feature: int = 0) -> Any:
    def edit(raw: Any) -> None:
        raw["features"][feature]["dimension_expressions"] = copy.deepcopy(value)

    return edit


def _width_formula(text: str) -> Any:
    def edit(raw: Any) -> None:
        raw["features"][0]["params"]["constraints"][9]["expression"] = text

    return edit


@pytest.mark.parametrize(
    "edit",
    [
        _set_formulas("W"),
        _set_formulas({"/constraints/99/expression": "W"}),
        _set_formulas({"/constraints/09/expression": "W"}),
        _set_formulas({"/constraints/9/value_mm": "W"}),
        _set_formulas({"/constraints/0/expression": "W"}),  # a coincident
        _set_formulas({WIDTH: ""}),
        _set_formulas({WIDTH: "W" * 257}),
        _set_formulas({WIDTH: 7}),
        _set_formulas({"/distance_mm": "D"}, feature=1),  # not a sketch
        _width_formula("2 * W"),  # the dimension already has a formula
    ],
)
def test_a_formula_that_does_not_fit_its_sketch_is_refused(edit: Any) -> None:
    with pytest.raises(LoftFileError) as caught:
        read_loft(_with_tree(edit))
    assert caught.value.code == "loft_tree_invalid"
    assert caught.value.details["member"] == TREE_PATH


def test_a_null_formula_map_reads_as_none() -> None:
    archive = read_loft(_with_tree(_set_formulas(None)))
    assert archive.tree.features[0].params["constraints"][9]["expression"] is None


def test_a_refusal_repeats_at_most_64_characters_of_the_pointer() -> None:
    with pytest.raises(LoftFileError) as caught:
        read_loft(_with_tree(_set_formulas({"/x" * 5000: "W"})))
    assert len(caught.value.details["pointer"]) == 64
    assert len(caught.value.message) < 200
