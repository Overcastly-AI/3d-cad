"""Goldens whose analytic truth needs a script re-derive it in the suite.

A golden's expected.json is only as good as the derivation behind it. Where
that derivation is more than arithmetic in its notes, the script is committed
beside the golden and re-run here against the committed value, so the pinned
number can never drift from the derivation that justified it (review N3 of
``a0a70ec``). Each script reads the golden's own model.json and uses no OCCT
mass-property integrator.
"""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"

#: Golden directories that carry a ``derive.py``. Listed, not discovered, so a
#: deleted script fails here instead of silently dropping out.
DERIVED_GOLDENS = (
    "extrude-cut-spline-slots-6x-disc-r20-h10",
    "shell-spline-prism-30x10-t1",
)


def _load(name: str) -> ModuleType:
    path = GOLDENS / name / "derive.py"
    spec = importlib.util.spec_from_file_location(
        f"derive_{name.replace('-', '_')}", path
    )
    assert spec is not None and spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", DERIVED_GOLDENS)
def test_the_pinned_volume_is_the_derived_one(name: str) -> None:
    module = _load(name)
    model = json.loads((GOLDENS / name / "model.json").read_text())
    expected = json.loads((GOLDENS / name / "expected.json").read_text())
    derived = module.derive(model)
    tolerance = expected["tolerance"]
    assert derived.volume == pytest.approx(
        expected["properties"]["volume"], abs=tolerance
    )
    centroid = getattr(derived, "centroid", None)
    if centroid is not None:
        pinned = expected["properties"]["centroid"]
        assert centroid == pytest.approx(
            (pinned["x"], pinned["y"], pinned["z"]), abs=tolerance
        )
