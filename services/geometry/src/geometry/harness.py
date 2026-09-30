"""Golden-harness support — one model-request vocabulary for the QA gates.

The golden suite (RESEARCH §9; ``services/geometry/tests/``) discovers
``goldens/<name>/model.json`` files that are EITHER a serialized
``TessellateRequest`` (single-shape goldens: box, cylinder) OR a serialized
``EvaluateTreeRequest`` (feature-tree goldens: sketch+extrude, …). This
module is the single source of that dispatch — the in-process runner, the
STEP round-trip gate, and the fresh-interpreter determinism probe all load
and evaluate models through it, so adding a golden of either kind requires
**zero runner changes** (geometry-gates skill).

Service code proper never imports this module; it exists so the three gate
entry points cannot drift from each other (CLAUDE.md DRY rule).
"""

import json
from collections.abc import Mapping
from pathlib import Path

from loft_wire.features import EvaluateTreeRequest

from geometry.features import evaluate_tree
from geometry.kernel import build_shape, evaluate_tessellation
from geometry.kernel.types import BodyShape
from geometry.schemas import TessellateRequest, TessellationMetadata

#: Everything a golden's ``model.json`` may deserialize to.
ModelRequest = TessellateRequest | EvaluateTreeRequest


def load_model_request(text: str) -> ModelRequest:
    """Parse a golden's ``model.json`` payload into its request type.

    Discrimination is structural: only ``EvaluateTreeRequest`` carries a
    ``features`` list. Validation is strict pydantic either way — a malformed
    golden fails loudly at collection, never silently passes.
    """
    if "features" in json.loads(text):
        return EvaluateTreeRequest.model_validate_json(text)
    return TessellateRequest.model_validate_json(text)


def golden_refusals(model_path: Path) -> dict[str, str]:
    """feature id -> error code, for the features a REFUSAL golden must fail.

    Read from the ``refusals`` list of the ``expected.json`` beside
    *model_path*; empty for every other golden (and for a model with no
    expected.json). Every suite that rebuilds the golden inventory and demands
    a clean evaluation holds a refusal golden to exactly these failures instead.
    """
    expected = model_path.parent / "expected.json"
    if not expected.is_file():
        return {}
    refusals = json.loads(expected.read_text(encoding="utf-8")).get("refusals", [])
    return {str(r["feature_id"]): str(r["code"]) for r in refusals}


def evaluate_model(
    request: ModelRequest, refusals: Mapping[str, str] | None = None
) -> tuple[bytes, TessellationMetadata]:
    """Rebuild a golden model to its ``(glb, metadata)`` artifact.

    Tree goldens must evaluate fully ``ok`` and produce a body — a golden
    exists to lock working capability, so any per-feature error here is a
    gate failure with the offending statuses in the message.

    The one exception is a REFUSAL golden, which locks a typed refusal (a
    feature id -> error code map in its expected.json, *refusals*): exactly
    those features must fail, each with exactly that code, and every other
    feature must be ``ok``. Its body is the last good one (strict-prefix rule),
    whose numbers the golden asserts as usual.
    """
    if isinstance(request, TessellateRequest):
        return evaluate_tessellation(request)

    evaluation = evaluate_tree(request)
    failures = sorted(
        (str(r.feature_id), r.status, r.error.code if r.error else None)
        for r in evaluation.result.features
        if r.status != "ok"
    )
    expected = sorted(
        (feature_id, "error", code) for feature_id, code in (refusals or {}).items()
    )
    if failures != expected:
        raise ValueError(
            f"golden tree did not evaluate as expected: got {failures}, "
            f"expected {expected}"
        )
    if (
        evaluation.glb is None
        or evaluation.mesh is None
        or evaluation.result.properties is None
    ):
        raise ValueError("golden tree evaluated ok but produced no body artifact")
    return evaluation.glb, TessellationMetadata(
        properties=evaluation.result.properties, mesh=evaluation.mesh
    )


def build_model_solid(request: ModelRequest) -> BodyShape:
    """Rebuild a golden model to its B-rep solid (STEP round-trip gate)."""
    if isinstance(request, TessellateRequest):
        return build_shape(request)
    evaluation = evaluate_tree(request)
    if evaluation.body is None:
        raise ValueError("golden tree evaluated to no body; nothing to round-trip")
    return evaluation.body
