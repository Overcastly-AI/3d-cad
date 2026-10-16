"""An assembly export names the occurrences it leaves out (ASM-FAILED-PART-API).

A part that fails to build has no body, so every export writes only the other
occurrences. The web says so with its Partial gate; ``POST /assembly/export``
says so in ``X-Loft-Omitted-Occurrences`` (count + part names, ASCII JSON), and
the evaluate result carries the same fold as ``omitted`` (the drawing's check
strip reads it through the extents route). A file holding every occurrence
sends no header.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from geometry.assembly import evaluate_assembly
from geometry.assembly.export import export_assembly_reporting
from geometry.main import app
from loft_wire.assemblies import (
    EvaluateAssemblyRequest,
    ExportAssemblyRequest,
)
from loft_wire.omitted_occurrences import (
    OMITTED_OCCURRENCES_HEADER,
    OmittedOccurrences,
    OmittedPart,
    decode_omitted_header,
)

client = TestClient(app)

_GOLDEN = Path(__file__).resolve().parent.parent / "goldens-assembly"
_PATTERNS = EvaluateAssemblyRequest.model_validate_json(
    (_GOLDEN / "assembly-component-patterns" / "model.json").read_text("utf-8")
)
_NAUO = re.compile(rb"NEXT_ASSEMBLY_USAGE_OCCURRENCE\(")

A = uuid.UUID(int=0xC1)
P = uuid.UUID(int=0xC2)
L = uuid.UUID(int=0xC3)
C = uuid.UUID(int=0xC4)
ROW = uuid.UUID(int=0xD2)
RING = uuid.UUID(int=0xD3)
CRANK = "7a0c2a52-0000-4000-8000-00000000c0a7"


def _bike() -> dict[str, Any]:
    """Five plates, no patterns; P and L are two instances of a crank arm whose
    tree builds nothing (the bike's `profile_unsupported`, as a bodiless part)."""
    model = _PATTERNS.model_dump(mode="json")
    model["patterns"] = []
    for inst in model["instances"]:
        inst["name"] = "Frame plate <1>"
    for n, inst_id in enumerate((P, L), start=1):
        [inst] = [i for i in model["instances"] if i["instance_id"] == str(inst_id)]
        inst["features"] = []
        inst["part_key"] = f"{CRANK}@tip"
        inst["name"] = f"Crank arm <{n}>"
    return model


def _export(model: dict[str, Any]) -> Any:
    response = client.post(
        "/api/v1/assembly/export",
        json={**model, "format": "step", "name": "Bike"},
    )
    assert response.status_code == 200, response.text
    return response


def test_the_export_names_both_failed_crank_arms() -> None:
    response = _export(_bike())
    omitted = decode_omitted_header(response.headers[OMITTED_OCCURRENCES_HEADER])
    assert omitted == OmittedOccurrences(
        count=2,
        parts=[
            OmittedPart(
                name="Crank arm",
                part_document_id=CRANK,
                code="no_body",
                occurrences=2,
            )
        ],
    )
    # Exactly the occurrences the file lacks: 5 placed, 3 written.
    assert len(_NAUO.findall(response.content)) == 3


def test_a_healthy_assembly_sends_no_header() -> None:
    model = _PATTERNS.model_dump(mode="json")
    response = _export(model)
    assert OMITTED_OCCURRENCES_HEADER not in response.headers
    result = evaluate_assembly(EvaluateAssemblyRequest.model_validate(model))
    assert result.omitted is None
    assert "omitted" not in result.model_dump(mode="json")


def test_the_evaluate_result_carries_the_same_fold_with_the_sentence() -> None:
    result = evaluate_assembly(EvaluateAssemblyRequest.model_validate(_bike()))
    assert result.omitted is not None
    assert result.omitted.count == 2
    [part] = result.omitted.parts
    assert (part.name, part.occurrences, part.code) == ("Crank arm", 2, "no_body")
    assert part.message != ""  # the header drops it; the result keeps it


def test_occurrences_inside_sub_assemblies_and_pattern_copies_are_counted() -> None:
    """A wheel sub-assembly whose spoke fails, ringed 4 times inside the wheel,
    and the wheel copied by a linear pattern: 8 occurrences, one part."""
    wheel_model = _PATTERNS.model_dump(mode="json")
    wheel_model["patterns"] = [
        p for p in wheel_model["patterns"] if p["pattern_id"] == str(RING)
    ]
    [spoke] = [i for i in wheel_model["instances"] if i["instance_id"] == str(C)]
    spoke["features"] = []
    spoke["part_key"] = "spoke@1"
    spoke["name"] = "Spoke <1>"
    wheel = uuid.UUID(int=0x77)
    parent: dict[str, Any] = {
        "assembly_id": str(uuid.UUID(int=0xFA)),
        "version": 1,
        "instances": [
            {
                "instance_id": str(wheel),
                "part_key": "wheel@tip",
                "features": [],
                "grounded": True,
                "sub_assembly": wheel_model,
            }
        ],
        "patterns": [
            {
                "pattern_id": str(ROW),
                "order_index": 0,
                "pattern": {
                    "type": "linear",
                    "seed_instance_ids": [str(wheel)],
                    "direction": {"kind": "origin_axis", "axis": "z"},
                    "count": 2,
                    "spacing_mm": 500.0,
                },
            }
        ],
    }
    result = evaluate_assembly(EvaluateAssemblyRequest.model_validate(parent))
    bodiless = [row for row in result.instances if row.part_mesh_glb_id is None]
    data, omitted = export_assembly_reporting(
        ExportAssemblyRequest.model_validate({**parent, "format": "step"})
    )
    assert omitted is not None
    assert omitted == result.omitted
    assert omitted.count == len(bodiless) == 8
    [part] = omitted.parts
    assert (part.name, part.part_document_id) == ("Spoke", "spoke")
    assert part.occurrences == omitted.count
    assert len(_NAUO.findall(data)) > 0
