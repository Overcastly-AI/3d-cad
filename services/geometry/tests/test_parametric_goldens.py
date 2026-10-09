"""Parametric goldens: re-drive a part's parameters and rebuild (RESEARCH §20).

A golden directory may carry a ``parametric.json`` beside its ``model.json``
and ``expected.json`` (PART-PARAMETERS step 4). It holds:

* ``parameters`` -- the part's table, as ``PUT /parts/{id}/parameters`` takes
  it;
* ``tree`` -- the features as documents STORES them: formulas kept
  (``expressions``, sketch dimension ``expression``), numbers resolved at that
  table;
* ``steps`` -- cumulative re-drives (``set``: parameter name -> new
  expression), each with hand-derived mass properties.

The runner resolves the tree with the SAME code documents composes an
evaluation request with (:func:`loft_wire.feature_resolve.evaluation_input`),
so a golden here proves the whole path a parameter edit takes: table ->
feature formulas -> numbers -> planegcs re-solve -> prism -> GProp.

* the tree resolved at the stored table must BE ``model.json`` (the request
  the ordinary golden gates in ``test_goldens.py`` already rebuild, hold to
  ``expected.json`` and check for determinism across a restart);
* every step must rebuild ok, to its hand values within ``expected.json``'s
  documented tolerance, with the golden's topology and mesh counts, and
  byte-identically twice in a row; and its request must differ from the
  previous step's exactly where a value changed (the rebuild-cache key).
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from geometry.harness import evaluate_model
from geometry.rebuild_cache import prefix_keys
from geometry.schemas import BoundingBox, TopologyCounts, Vec3
from loft_wire.feature_resolve import evaluation_input, parameter_values
from loft_wire.features import EvaluatedFeatureInput, EvaluateTreeRequest
from loft_wire.parameters import PartParameterInput, resolve_parameters
from pydantic import BaseModel, ConfigDict, Field

GOLDENS_DIR = Path(__file__).resolve().parent.parent / "goldens"


class StepProperties(BaseModel):
    model_config = ConfigDict(extra="forbid")

    volume: float = Field(gt=0)
    surface_area: float = Field(gt=0)
    centroid: Vec3
    bounding_box: BoundingBox


class RedriveStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    set: dict[str, str] = Field(min_length=1)
    derivation: list[str] = Field(min_length=1)
    properties: StepProperties


class GoldenBounds(BaseModel):
    """What a step shares with the golden's ``expected.json`` (validated in
    full by ``test_goldens.py``): its documented tolerance and exact counts."""

    tolerance: float = Field(gt=0)
    topology: TopologyCounts
    mesh: dict[str, int]


class ParametricGolden(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    parameters: list[PartParameterInput] = Field(min_length=1)
    tree: list[dict[str, Any]] = Field(min_length=1)
    steps: list[RedriveStep] = Field(min_length=1)


@dataclass(frozen=True)
class Case:
    name: str
    golden: ParametricGolden
    model: EvaluateTreeRequest
    expected: GoldenBounds

    def request(self, table: list[PartParameterInput]) -> EvaluateTreeRequest:
        """What documents sends geometry for the stored tree at *table*."""
        values = parameter_values(
            row.model_dump(mode="json") for row in resolve_parameters(table)
        )
        features: list[EvaluatedFeatureInput] = []
        for stored in self.golden.tree:
            item = EvaluatedFeatureInput.model_validate(stored)
            feature, error = evaluation_input(item.feature, values)
            assert error is None, f"{self.name}: {item.id}: {error}"
            features.append(EvaluatedFeatureInput(id=item.id, feature=feature))
        return self.model.model_copy(update={"features": features})


def _cases() -> list[Case]:
    cases: list[Case] = []
    for path in sorted(GOLDENS_DIR.glob("*/parametric.json")):
        directory = path.parent
        cases.append(
            Case(
                name=directory.name,
                golden=ParametricGolden.model_validate_json(path.read_text("utf-8")),
                model=EvaluateTreeRequest.model_validate_json(
                    (directory / "model.json").read_text("utf-8")
                ),
                expected=GoldenBounds.model_validate_json(
                    (directory / "expected.json").read_text("utf-8")
                ),
            )
        )
    return cases


CASES = _cases()
each_case = pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])


def test_there_is_a_parametric_golden() -> None:
    assert CASES, f"no parametric.json under {GOLDENS_DIR}"


@each_case
def test_the_stored_tree_resolves_to_model_json(case: Case) -> None:
    """The tree carries formulas; geometry is sent numbers only, and for the
    stored table those numbers are exactly the committed model.json."""
    sent = case.request(case.golden.parameters)
    assert sent.model_dump_json() == case.model.model_dump_json()
    assert "expression" not in json.dumps(sent.model_dump(mode="json")).replace(
        '"expression": null', ""
    )


def _redriven(case: Case) -> list[tuple[RedriveStep, EvaluateTreeRequest]]:
    table = [row.model_copy() for row in case.golden.parameters]
    out: list[tuple[RedriveStep, EvaluateTreeRequest]] = []
    for step in case.golden.steps:
        names = {row.name for row in table}
        assert set(step.set) <= names, f"{case.name}: unknown {set(step.set) - names}"
        table = [
            row.model_copy(
                update={"expression": step.set.get(row.name, row.expression)}
            )
            for row in table
        ]
        out.append((step, case.request(table)))
    return out


@each_case
def test_every_redrive_rebuilds_to_its_hand_values(case: Case) -> None:
    tolerance = case.expected.tolerance
    for index, (step, request) in enumerate(_redriven(case)):
        glb, metadata = evaluate_model(request)
        again, metadata_again = evaluate_model(request)
        label = f"{case.name} step {index} {step.set}"
        assert glb == again and metadata == metadata_again, (
            f"{label}: not deterministic"
        )
        got = metadata.properties
        want = step.properties
        pairs = [
            ("volume", got.volume, want.volume),
            ("surface_area", got.surface_area, want.surface_area),
            *(
                (f"centroid.{a}", getattr(got.centroid, a), getattr(want.centroid, a))
                for a in "xyz"
            ),
            *(
                (
                    f"bbox.{end}.{a}",
                    getattr(getattr(got.bounding_box, end), a),
                    getattr(getattr(want.bounding_box, end), a),
                )
                for end in ("min", "max")
                for a in "xyz"
            ),
        ]
        for what, actual, expected in pairs:
            assert actual == pytest.approx(expected, abs=tolerance), (
                f"{label}: {what} expected {expected!r}, got {actual!r} "
                f"(documented tolerance {tolerance!r}; never loosen to go green)"
            )
        assert got.topology == case.expected.topology, label
        assert metadata.mesh.vertices == case.expected.mesh["vertices"], label
        assert metadata.mesh.triangles == case.expected.mesh["triangles"], label


@each_case
def test_a_redrive_changes_the_rebuild_cache_key_and_a_repeat_does_not(
    case: Case,
) -> None:
    """The cache key follows the resolved numbers: a new value is a new key
    from the first feature it reaches, and the same values give the same key."""
    previous = case.request(case.golden.parameters)
    assert prefix_keys(previous, capture_scope=()) == prefix_keys(
        case.model, capture_scope=()
    )
    for step, request in _redriven(case):
        keys = prefix_keys(request, capture_scope=())
        old = prefix_keys(previous, capture_scope=())
        # The first feature whose resolved numbers moved is where keys part.
        first = next(
            i
            for i, (a, b) in enumerate(
                zip(previous.features, request.features, strict=True)
            )
            if a != b
        )
        assert keys[: first + 1] == old[: first + 1], step.set
        assert keys[first + 1] != old[first + 1], step.set
        # The same values give the same key, however they arrive.
        assert keys == prefix_keys(
            EvaluateTreeRequest.model_validate_json(request.model_dump_json()),
            capture_scope=(),
        )
        previous = request
