"""The twisted prism plugin builds the legacy twisted extrude (PLUGIN-REGISTRY).

``goldens/plugin-twisted-prism-v1-square20-hole-r3-h30-30deg/model.json`` is
the expansion of one stored twisted prism (``loft.twisted_prism`` 1.0.0), as
documents sends it: base features only. Geometry never learns plugins exist,
so this module reads the golden's JSON and imports nothing from
``loft_plugins`` (``packages/loft-plugins/tests/test_twisted_prism.py`` pins
the JSON to the plugin).

Acceptance (BACKLOG PLUGIN-REGISTRY): the twisted prism matches the legacy
twisted-extrude golden, a stored extrude row carrying ``twist_angle_deg``
over the same profile: the two-way boolean difference is EMPTY, and every
reported number and the GLB are bit-identical. A 29 deg control proves the
difference is a real boolean, not one that silently returned nothing.
"""

import json
from pathlib import Path
from typing import Any

from build123d import Solid
from geometry.harness import build_model_solid, evaluate_model, load_model_request
from loft_wire.features import EvaluateTreeRequest

GOLDENS = Path(__file__).resolve().parent.parent / "goldens"
PRISM = GOLDENS / "plugin-twisted-prism-v1-square20-hole-r3-h30-30deg"


def _prism() -> EvaluateTreeRequest:
    request = load_model_request((PRISM / "model.json").read_text())
    assert isinstance(request, EvaluateTreeRequest)
    return request


def _legacy_extrude(twist_angle_deg: float) -> EvaluateTreeRequest:
    """The same part as a stored pre-deprecation row has it: the profile and
    ONE extrude carrying the legacy twist, under the sweep member's id."""
    golden: dict[str, Any] = json.loads((PRISM / "model.json").read_text())
    profile, sweep = golden["features"][0], golden["features"][-1]
    golden["features"] = [
        profile,
        {
            "id": sweep["id"],
            "feature": {
                "type": "extrude",
                "version": 1,
                "params": {
                    "profile": {"kind": "feature", "feature_id": profile["id"]},
                    "distance_mm": 30.0,
                    "operation": "add",
                    "direction": "normal",
                    "twist_angle_deg": twist_angle_deg,
                },
            },
        },
    ]
    return EvaluateTreeRequest.model_validate(golden)


def test_the_twisted_prism_is_the_legacy_twisted_extrude() -> None:
    prism_glb, prism_meta = evaluate_model(_prism())
    legacy_glb, legacy_meta = evaluate_model(_legacy_extrude(30.0))
    assert legacy_glb == prism_glb
    assert legacy_meta == prism_meta

    prism = build_model_solid(_prism())
    legacy = build_model_solid(_legacy_extrude(30.0))
    control = build_model_solid(_legacy_extrude(29.0))
    assert isinstance(prism, Solid)
    assert isinstance(legacy, Solid) and isinstance(control, Solid)
    assert legacy.cut(prism).volume == 0.0  # pyright: ignore[reportUnknownMemberType]
    assert prism.cut(legacy).volume == 0.0  # pyright: ignore[reportUnknownMemberType]
    assert control.cut(prism).volume > 1.0  # pyright: ignore[reportUnknownMemberType]
    assert prism.cut(control).volume > 1.0  # pyright: ignore[reportUnknownMemberType]
